"""Service wiring and supervision. / Assemblage et supervision du service.

One process, several worker threads (buttons, fan, NFC). Each worker is supervised on its own: if one
raises, it is logged and restarted with a growing delay while the others keep running - a crash in the
NFC code can never stop the power button.
Un processus, plusieurs threads supervisés indépendamment : un plantage du NFC n'arrête pas le bouton power.
"""

import logging
import signal
import subprocess
import threading
import time

from .buttons import PowerSwitch, ResetButton
from .errors import LaunchError, PicontrolError
from .fan import FanController, read_temperature
from .gpio import Gpio
from .launcher import Launcher
from .led import Led
from .nfc import NfcService, reader_from_config
from .retroarch import RetroArch

log = logging.getLogger("picontrol.service")

REBOOT_COMMAND = ["sudo", "-n", "reboot"]


class Worker(threading.Thread):
    """Run ``target(stop)``; restart it with backoff if it raises."""

    INITIAL_DELAY = 1.0

    def __init__(self, name, target, stop):
        super().__init__(name=name, daemon=True)
        self.target, self.stop_event = target, stop

    def run(self):
        delay = self.INITIAL_DELAY
        while not self.stop_event.is_set():
            try:
                self.target(self.stop_event)
                return
            except Exception:  # noqa: BLE001 - isolate every failure
                log.exception("Worker '%s' crashed; restarting in %.0f s", self.name, delay)
                self.stop_event.wait(delay)
                delay = min(delay * 2, 30.0)


class Service:
    def __init__(self, cfg, gpio=None, dry_run=False, run_command=None, popen=subprocess.Popen,
                 procs=None, reader=None, sleep=time.sleep):
        self.cfg, self.dry_run, self._sleep = cfg, dry_run, sleep
        self._run_command = run_command or subprocess.call
        self._shutting_down = False
        self._stop_event = None
        self.restart_requested = False
        self.started = time.monotonic()
        self.gpio = gpio or Gpio()
        self.led = Led(self.gpio, cfg.pins.led, cfg.led.enabled)
        self.retroarch = RetroArch(cfg.retroarch.host, cfg.retroarch.port, dry_run=dry_run)
        self.launcher = Launcher(cfg, self.retroarch, procs=procs, popen=popen, dry_run=dry_run)
        self.nfc = (NfcService(cfg, reader or reader_from_config(cfg, self.gpio), self.launcher, self.led)
                    if cfg.nfc.enabled else None)
        self.fan = None
        if cfg.fan.enabled:
            self.fan = FanController(self.gpio, cfg.pins.fan, cfg.fan.threshold_on, cfg.fan.threshold_off,
                                     cfg.fan.min_run, lambda: read_temperature(cfg.fan.temp_path))
        self.power = (PowerSwitch(self.gpio, cfg.pins.power, cfg.power_off_level, cfg.power.debounce,
                                  self.on_power_off) if cfg.power.enabled else None)
        self.reset = (ResetButton(self.gpio, cfg.pins.reset, cfg.reset.debounce, cfg.reset.long_press,
                                  self.on_reset_short, self.on_reset_long) if cfg.reset.enabled else None)
        self.web = None
        if cfg.web.enabled:
            try:
                from .web import WebServer
                from .webbackend import Backend
                self.web = WebServer(cfg, Backend(self))
            except PicontrolError as exc:  # a web problem must never stop the console from working
                log.error("Web interface not started: %s", exc)

    # ------------------------------------------------------------------ button actions
    def _graceful_stop(self, command, label):
        """Quit the game (RetroArch saves), then run ``command`` (shutdown or reboot)."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self.launcher.shutting_down = True  # do not restart ES while the system goes down
        log.warning("%s", label)
        self.led.blink(3)
        self.retroarch.quit()  # RetroArch saves on quit
        self._sleep(self.cfg.power.quit_grace)
        self.led.off()
        if self.dry_run:
            log.info("[dry-run] would run: %s", " ".join(command))
        elif self._run_command(command) == 0:
            return
        else:
            log.error("Command failed: %s", " ".join(command))
        self._shutting_down = False  # dry-run or failure: allow another attempt
        self.launcher.shutting_down = False
        self.led.on()

    def shutdown(self, reason="Shutdown requested"):
        self._graceful_stop(self.cfg.power.shutdown_command, reason)

    def reboot(self):
        self._graceful_stop(REBOOT_COMMAND, "Reboot requested")

    def on_power_off(self):
        self.shutdown("Power switch is OFF: shutting down")

    def request_restart(self):
        """Stop the service; the autostart loop starts it again with the new configuration."""
        log.info("Service restart requested")
        self.restart_requested = True
        if self._stop_event is not None:
            self._stop_event.set()

    def on_reset_short(self):
        log.info("Reset button: reset game")
        self.retroarch.reset()
        self.led.blink(1)

    def on_reset_long(self):
        log.info("Reset button held: write current game to a tag")
        if self.nfc is None:
            self.led.error()
            return
        try:
            self.nfc.request_write_current()
        except LaunchError as exc:
            log.warning("Cannot write a tag: %s", exc)
            self.led.error()
            return
        self.led.blink(3, 0.1, 0.1)

    # ------------------------------------------------------------------ running
    def _buttons_loop(self, stop):
        watchers = [w for w in (self.power, self.reset) if w]
        while not stop.is_set():
            now = time.monotonic()
            for watcher in watchers:
                watcher.step(now)
            stop.wait(self.cfg.power.poll_interval)

    def run(self, stop=None, install_signals=True):
        stop = stop or threading.Event()
        self._stop_event = stop
        if install_signals:
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *_: stop.set())
        self.led.on()
        workers = []
        if self.power or self.reset:
            workers.append(Worker("buttons", self._buttons_loop, stop))
        if self.fan:
            workers.append(Worker("fan", lambda s: self.fan.run(s, self.cfg.fan.interval), stop))
        if self.nfc:
            workers.append(Worker("nfc", self.nfc.run, stop))
        if self.web:
            workers.append(Worker("web", self.web.run, stop))
        for worker in workers:
            worker.start()
        log.info("picontrol running: %s%s", ", ".join(w.name for w in workers) or "nothing enabled",
                 " (dry-run)" if self.dry_run else "")
        while not stop.wait(1.0):
            pass
        log.info("Stopping")
        for worker in workers:
            worker.join(timeout=5)
        self.led.off()
