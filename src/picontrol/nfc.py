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
from .errors import LaunchError, ReaderError, TagError
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
        self._pending_write = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ write requests
    def request_write_current(self):
        """Queue 'write the running game on the next tag'. Raises LaunchError if no game is running."""
        system, rom = self.launcher.current_game()
        with self._lock:
            self._pending_write = (system, rom, self._clock() + self.cfg.nfc.write_timeout)
        log.info("Write request queued: %s / %s", system, rom)

    def _take_write(self):
        with self._lock:
            request, self._pending_write = self._pending_write, None
        return request

    def _do_write(self, system, rom, deadline):
        log.info("Present a tag to write %s / %s", system, rom)
        while self._clock() < deadline:
            uid = self.reader.read_uid()
            if uid is not None:
                try:
                    write_and_verify(self.reader, uid, [system, rom], self._sleep)
                except (TagError, ReaderError) as exc:
                    log.error("Writing failed: %s", exc)
                    self.led.error()
                    return
                self.uid, self.handled, self.last_seen = uid, True, self._clock()
                log.info("Tag %s written: %s / %s", hexstr(uid), system, rom)
                self.led.ok()
                return
            self._sleep(0.3)
        log.warning("No tag presented within %.0f s: nothing written", self.cfg.nfc.write_timeout)
        self.led.error()

    # ------------------------------------------------------------------ polling
    def step(self, now=None):
        """One poll cycle. Raises ReaderError when the reader misbehaves."""
        now = self._clock() if now is None else now
        request = self._take_write()
        if request:
            self._do_write(*request)
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
