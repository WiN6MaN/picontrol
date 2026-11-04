"""Front-panel LED. / LED du panneau avant.

Driven directly through its GPIO (no serial port needed). It stays lit once the service is up;
``blink`` gives short feedback and then restores the steady state.
Pilotée directement par son GPIO (pas besoin du port série) ; allumée en continu une fois le service lancé.
"""

import threading
import time


class Led:
    def __init__(self, gpio, pin, enabled=True, sleep=time.sleep):
        self._gpio, self._pin, self._enabled, self._sleep = gpio, pin, enabled, sleep
        self._lock = threading.Lock()
        self._steady = 0
        if enabled:
            gpio.setup_output(pin, 0)

    def _write(self, value):
        if self._enabled:
            self._gpio.write(self._pin, value)

    def on(self):
        with self._lock:
            self._steady = 1
            self._write(1)

    def off(self):
        with self._lock:
            self._steady = 0
            self._write(0)

    def blink(self, count=1, on_s=0.15, off_s=0.15):
        """Blink ``count`` times (blocking, short), then go back to the steady state."""
        with self._lock:
            for _ in range(count):
                self._write(1 - self._steady)
                self._sleep(on_s)
                self._write(self._steady)
                self._sleep(off_s)

    def ok(self):
        self.blink(3, 0.25, 0.25)

    def error(self):
        self.blink(6, 0.07, 0.07)
