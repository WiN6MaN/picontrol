"""Fan controller. / Contrôleur du ventilateur.

Hysteresis: switch on at ``threshold_on``, off at ``threshold_off`` (never in between), and keep it
running at least ``min_run`` seconds so it does not chatter around the threshold.
Fail-safe: if the temperature cannot be read several times in a row, or the controller stops for
any reason, the fan is switched ON - a spinning fan is harmless, a hot Pi is not.
Hystérésis + durée minimale de marche ; sécurité : ventilateur ALLUMÉ si la température est illisible.
"""

import logging
import time

log = logging.getLogger("picontrol.fan")


def read_temperature(path):
    """CPU temperature in degrees Celsius from the kernel thermal zone, or None."""
    try:
        with open(path, encoding="ascii") as handle:
            return int(handle.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


class FanController:
    FAILSAFE_AFTER = 3

    def __init__(self, gpio, pin, threshold_on, threshold_off, min_run, read_temp, clock=time.monotonic):
        self.gpio, self.pin, self.on_at, self.off_at = gpio, pin, threshold_on, threshold_off
        self.min_run, self._read_temp, self._clock = min_run, read_temp, clock
        self.is_on = False
        self._on_since = 0.0
        self._failures = 0
        gpio.setup_output(pin, 0)

    def _set(self, state):
        if state != self.is_on:
            log.info("Fan %s", "ON" if state else "OFF")
        self.is_on = state
        self.gpio.write(self.pin, 1 if state else 0)

    def step(self, now=None):
        now = self._clock() if now is None else now
        temp = self._read_temp()
        if temp is None:
            self._failures += 1
            if self._failures >= self.FAILSAFE_AFTER and not self.is_on:
                log.warning("Temperature unreadable: fan forced ON")
                self._set(True)
                self._on_since = now
            return
        self._failures = 0
        if not self.is_on and temp >= self.on_at:
            self._set(True)
            self._on_since = now
        elif self.is_on and temp <= self.off_at and now - self._on_since >= self.min_run:
            self._set(False)

    def run(self, stop, interval):
        try:
            while not stop.is_set():
                self.step()
                stop.wait(interval)
        finally:
            self._set(True)  # fail-safe on exit
