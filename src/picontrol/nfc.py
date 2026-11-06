"""NFC service: detects tags and launches games. / Service NFC : détecte les tags et lance les jeux.

State machine (one ``step`` per poll)
  * a new tag appears      -> read it -> validate -> launch the game (once)
  * the tag stays          -> nothing (no relaunch when the game ends)
  * the tag is absent for ``remove_delay`` s -> "removed" (optionally quit the game)
  * the same tag comes back after a removal  -> launch again
Machine à états : insertion -> lecture -> lancement unique ; retrait confirmé après ``remove_delay`` s.

The service is the only owner of the reader while it runs. A long press on the reset button queues a
"write the current game to the next tag" request that is executed here, inside the same thread.
"""

import logging
import threading
import time

from . import tagstore
from .errors import BusyError, NotOurTag, ReaderError, TagError
from .lock import ReaderLock
from .pn532 import PN532, hexstr

log = logging.getLogger("picontrol.nfc")


def reader_from_config(cfg, gpio):
    p = cfg.pins
    return PN532(gpio, cs=p.nfc_cs, sclk=p.nfc_sclk, mosi=p.nfc_mosi, miso=p.nfc_miso,
                 rf_reset_each_poll=cfg.nfc.rf_reset_each_poll)


def write_and_verify(reader, uid, values, sleep=time.sleep):
    """Write ``values`` then read them back from a freshly detected tag. Raises on any mismatch."""
    tagstore.write_records(reader, uid, values)
    sleep(0.05)
    uid_again = reader.read_uid()
    if uid_again != uid or tagstore.read_records(reader, uid_again) != list(values):
        raise ReaderError("verification failed after writing")


class TagJob:
    """A request from another thread (reset button, web interface) executed by the NFC thread.

    kind "write": write ``values`` on the next tag presented; kind "read": read the next tag presented.
    The requester waits on ``done``; ``result`` or ``error`` is then set.
    Une demande venant d'un autre thread, exécutée par le thread NFC.
    """

    def __init__(self, kind, values=None, timeout=15.0, announce=True):
        self.kind, self.values, self.timeout, self.announce = kind, values, timeout, announce
        self.deadline = None
        self.done = threading.Event()
        self.result = None
        self.error = None
        self.timed_out = False

    def finish(self, result=None, error=None, timed_out=False):
        self.result, self.error, self.timed_out = result, error, timed_out
        self.done.set()

    def wait(self, timeout=None):
        return self.done.wait(timeout)


class NfcService:
    def __init__(self, cfg, reader, launcher, led, clock=time.monotonic, sleep=time.sleep):
        self.cfg, self.reader, self.launcher, self.led = cfg, reader, launcher, led
        self._clock, self._sleep = clock, sleep
        self.uid = None
        self.last_seen = 0.0
        self.handled = False
        self.attempts = 0
        self.last_launch = -1e9
        self.first_cycle = True
        self.ready = False
        self._job = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ requests from other threads
    def submit(self, job):
        """Queue a TagJob. Raises BusyError if another one is waiting or running."""
        with self._lock:
            if self._job is not None:
                raise BusyError("another tag operation is in progress")
            job.deadline = self._clock() + job.timeout
            self._job = job
        return job

    def request_write_current(self):
        """Queue 'write the running game on the next tag'. Raises LaunchError if no game is running."""
        system, rom = self.launcher.current_game()
        job = self.submit(TagJob("write", [system, rom], self.cfg.nfc.write_timeout))
        log.info("Write request queued: %s / %s", system, rom)
        return job

    def status(self):
        return {"enabled": True, "ready": self.ready, "busy": self._job is not None,
                "tag": hexstr(self.uid) if self.uid else None}

    def _take_job(self):
        with self._lock:
            job, self._job = self._job, None
        return job

    def _run_job(self, job):
        log.info("Tag %s requested: present a tag", job.kind)
        uid = None
        try:
            while self._clock() < job.deadline:
                uid = self.reader.read_uid()
                if uid is not None:
                    break
                self._sleep(0.3)
            if uid is None:
                log.warning("No tag presented within %.0f s", job.timeout)
                if job.kind == "write" and job.announce:
                    self.led.error()
                job.finish(error="no tag was presented in time", timed_out=True)
                return
            if job.kind == "write":
                write_and_verify(self.reader, uid, job.values, self._sleep)
                result = {"uid": hexstr(uid), "system": job.values[0], "rom": job.values[1]}
                log.info("Tag %s written: %s / %s", hexstr(uid), job.values[0], job.values[1])
                if job.announce:
                    self.led.ok()
            else:
                try:
                    records = tagstore.read_records(self.reader, uid)
                    result = {"uid": hexstr(uid), "records": records}
                except NotOurTag as exc:
                    result = {"uid": hexstr(uid), "records": None, "note": str(exc)}
        except ReaderError as exc:
            if job.kind == "write" and job.announce:
                self.led.error()
            job.finish(error=str(exc))
            raise  # let the polling loop count it and re-initialise the reader if needed
        except TagError as exc:
            log.error("Tag %s failed: %s", job.kind, exc)
            if job.kind == "write" and job.announce:
                self.led.error()
            job.finish(error=str(exc))
            return
        # the tag that was just read/written must not launch its game
        self.uid, self.handled, self.last_seen = uid, True, self._clock()
        job.finish(result=result)

    # ------------------------------------------------------------------ polling
    def step(self, now=None):
        """One poll cycle. Raises ReaderError when the reader misbehaves."""
        now = self._clock() if now is None else now
        job = self._take_job()
        if job is not None:
            self._run_job(job)
            self.first_cycle = False
            return
        uid = self.reader.read_uid()
        if uid is not None:
            self.last_seen = now
            if uid != self.uid:
                log.info("Tag detected: %s", hexstr(uid))
                self.uid, self.handled, self.attempts = uid, False, 0
                if self.first_cycle and not self.cfg.nfc.launch_at_start:
                    self.handled = True
            if not self.handled:
                self._handle(uid, now)
        elif self.uid is not None and now - self.last_seen >= self.cfg.nfc.remove_delay:
            log.info("Tag removed: %s", hexstr(self.uid))
            self.uid, self.handled, self.attempts = None, False, 0
            if self.cfg.nfc.quit_on_remove:
                self.launcher.quit_game()
        self.first_cycle = False

    def _handle(self, uid, now):
        if now - self.last_launch < self.cfg.nfc.min_relaunch_interval:
            return
        self.attempts += 1
        try:
            records = tagstore.read_records(self.reader, uid)
            if len(records) < 2:
                raise TagError("expected 2 records (system, rom)")
            path = self.launcher.resolve_rom(records[0], records[1])
        except TagError as exc:  # LaunchError / NotOurTag: retrying cannot help
            log.warning("Tag ignored: %s", exc)
            self.handled = True
            return
        except ReaderError as exc:
            log.warning("Cannot read the tag (attempt %d/%d): %s", self.attempts,
                        self.cfg.nfc.max_read_attempts, exc)
            if self.attempts >= self.cfg.nfc.max_read_attempts:
                log.error("Giving up on this tag (remove it and present it again)")
                self.handled = True
            return
        self.handled = True
        self.last_launch = now
        self.launcher.launch(records[0], path)

    # ------------------------------------------------------------------ main loop
    def run(self, stop):
        """Poll until ``stop`` is set. Reader failures are retried with a growing delay and a full re-init."""
        errors = 0
        cfg = self.cfg.nfc
        while not stop.is_set():
            try:
                self.launcher.poll()  # restart ES when a game ends, even if the reader is down
            except Exception:  # noqa: BLE001
                log.exception("Game supervision failed")
            interval = cfg.poll_interval_game if self.launcher.game_running() else cfg.poll_interval
            try:
                with ReaderLock(cfg.lock_file) as got:
                    if got:
                        if not self.ready:
                            fw = self.reader.init()
                            self.ready = True
                            log.info("PN532 ready (firmware %d.%d)", fw[1], fw[2])
                        self.step()
                        errors = 0
            except ReaderError as exc:
                errors += 1
                log.warning("Reader error (%d in a row): %s", errors, exc)
                if errors >= 3:
                    self.ready = False  # full re-initialisation on the next cycle
                interval = min(cfg.poll_interval * (2 ** min(errors, 4)), 5.0)
            except Exception:  # noqa: BLE001
                errors += 1
                log.exception("Unexpected NFC error")
                self.ready = False
                interval = 2.0
            stop.wait(interval)
