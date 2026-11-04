"""Power switch and reset button. / Interrupteur power et bouton reset.

Both are small state machines driven by ``step(now)``; the caller supplies the clock, which makes
them trivial to test (no real waiting).
Deux petites machines à états pilotées par ``step(now)`` (horloge fournie par l'appelant : testable).

Power : a *latching* switch. Closed to ground = ON, open = OFF (pulled up). Opening it for longer
than the debounce time fires ``on_off`` once. (Closing it again is what wakes a halted Pi: GPIO3 low.)
Reset : short press -> ``on_short`` (on release); held for ``long_press`` s -> ``on_long`` (while held).
"""


class PowerSwitch:
    def __init__(self, gpio, pin, off_level, debounce, on_off):
        self.gpio, self.pin, self.off_level, self.debounce, self.on_off = gpio, pin, off_level, debounce, on_off
        self._since = None
        self._fired = False
        gpio.setup_input(pin, pull_up=True)

    def step(self, now):
        if self.gpio.read(self.pin) == self.off_level:
            if self._since is None:
                self._since = now
            elif not self._fired and now - self._since >= self.debounce:
                self._fired = True
                self.on_off()
        else:  # switch is ON: re-arm
            self._since, self._fired = None, False


class ResetButton:
    def __init__(self, gpio, pin, debounce, long_press, on_short, on_long):
        self.gpio, self.pin, self.debounce, self.long_press = gpio, pin, debounce, long_press
        self.on_short, self.on_long = on_short, on_long
        self._since = None
        self._long_done = False
        gpio.setup_input(pin, pull_up=True)

    def step(self, now):
        if self.gpio.read(self.pin) == 0:  # pressed (pulled to ground)
            if self._since is None:
                self._since, self._long_done = now, False
            elif not self._long_done and now - self._since >= self.long_press:
                self._long_done = True
                self.on_long()
        elif self._since is not None:
            held = now - self._since
            self._since = None
            if not self._long_done and held >= self.debounce:
                self.on_short()
