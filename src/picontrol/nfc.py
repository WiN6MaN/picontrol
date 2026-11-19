"""NFC service: detects tags and launches games. / Service NFC : détecte les tags et lance les jeux.

State machine (one ``step`` per poll)
  * a new tag appears      -> read it -> validate -> launch the game (once); a running game is not replaced
                              unless ``replace_running_game`` is on
                              (``launch_on_reset_press``: the game waits for a short press of the Reset button)
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

from . import session, tagstore
from .errors import BusyError, NotOurTag, ReaderError, TagError
from .lock import ReaderLock
from .pn532 import PN532, hexstr

log = logging.getLogger("picontrol.nfc")

PRESS_MAX_AGE = 10.0  # seconds: a Reset press older than this no longer launches a cassette


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
    def __init__(self, cfg, reader, launcher, led, clock=time.monotonic, sleep=time.sleep, runtime_dir=None):
        self.cfg, self.reader, self.launcher, self.led = cfg, reader, launcher, led
        self.runtime_dir = runtime_dir
        self._announced = False  # the console session is told once that the first scan is done
        self._clock, self._sleep = clock, sleep
        self.uid = None
        self.last_seen = 0.0
        self.handled = False
        self.attempts = 0
        self.last_launch = -1e9
        self.first_cycle = True
        self.ready = False
        self._job = None
        self._pending = None  # (system, rom path, uid) of a cassette waiting for the Reset button
        self._press_at = None  # when the Reset button asked to launch it
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

    # ------------------------------------------------------------------ launch with the Reset button
    def _press_mode(self):
        """Cassettes wait for the Reset button (never without a Reset button: nothing could start them)."""
        return self.cfg.nfc.launch_on_reset_press and self.cfg.reset.enabled

    def take_reset_press(self):
        """Called by the Reset button's thread on a short press.

        True = the press launches the cassette that is waiting, so the caller must NOT reset the game.
        False = no cassette is waiting (or a game must not be replaced): Reset keeps its usual meaning.
        Appelé par le thread du bouton Reset : True = l'appui lance la cassette en attente (pas de reset du jeu).
        """
        if not self._press_mode():
            return False
        with self._lock:
            if self._pending is None:
                return False
            if self._press_at is not None:
                return True  # a press is already on its way: swallow this one too
        if not self.cfg.nfc.replace_running_game and self._a_game_is_running():
            return False  # a game is running and must not be cut: Reset resets it, as usual
        with self._lock:
            if self._pending is None:
                return False
            self._press_at = self._clock()
        return True

    def _launch_waiting(self, now):
        """In the NFC thread: start the waiting cassette if the Reset button was pressed for it."""
        with self._lock:
            pressed_at, pending = self._press_at, self._pending
        if pressed_at is None or pending is None:
            return
        system, path, uid = pending
        if self._clock() - pressed_at > PRESS_MAX_AGE:
            log.info("Reset press too old (the reader was busy): not launching")
            self._forget_press()
            return
        if uid != self.uid or self.last_seen != now:
            return  # the cassette is not in the field at this poll: wait for the next one (or for its removal)
        with self._lock:
            self._pending = self._press_at = None
        log.info("Reset button pressed: launching %s / %s", system, path)
        self.last_launch = now
        self.launcher.launch(system, path)

    def _forget_press(self):
        with self._lock:
            self._press_at = None

    def _forget_waiting(self):
        with self._lock:
            self._pending = self._press_at = None

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
        self._forget_waiting()
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
                self._forget_waiting()
                if self.first_cycle and not self.cfg.nfc.launch_at_start:
                    self.handled = True
            if not self.handled:
                self._handle(uid, now)
        elif self.uid is not None and now - self.last_seen >= self.cfg.nfc.remove_delay:
            log.info("Tag removed: %s", hexstr(self.uid))
            self.uid, self.handled, self.attempts = None, False, 0
            self._forget_waiting()
            if self.cfg.nfc.quit_on_remove:
                self.launcher.quit_game()
        self._launch_waiting(now)
        self.first_cycle = False

    def _a_game_is_running(self):
        """A game of ours (even one still loading) or one started from EmulationStation."""
        return self.launcher.game_running() or self.launcher.any_game_running()

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
        if not self.cfg.nfc.replace_running_game and self._a_game_is_running():
            log.info("A game is running: tag ignored (replace_running_game is off). "
                     "Quit the game, then remove the tag and present it again.")
            return
        if self._press_mode():
            with self._lock:
                self._pending = (records[0], path, uid)
            log.info("Cassette %s / %s is waiting: press the Reset button to launch it", records[0], records[1])
            self.led.blink(2, 0.1, 0.1)
            return
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
            if not self._announced:  # success or not: the console session must not wait for us any longer
                self._announced = True
                session.announce_ready(self.runtime_dir)
            stop.wait(interval)
