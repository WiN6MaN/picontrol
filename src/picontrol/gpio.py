"""Thin GPIO wrapper (BCM numbering). / Mince couche d'accès aux GPIO (numérotation BCM).

``RPi.GPIO`` is imported lazily so the package can be imported (and tested) on any machine.
Tests inject a fake backend with the same four methods.
"""


class Gpio:
    def __init__(self, backend=None):
        if backend is None:
            import RPi.GPIO as backend  # noqa: N813 - only available on a Raspberry Pi
        self._g = backend
        self._g.setwarnings(False)
        self._g.setmode(self._g.BCM)

    def setup_input(self, pin, pull_up=False):
        pull = self._g.PUD_UP if pull_up else self._g.PUD_OFF
        self._g.setup(pin, self._g.IN, pull_up_down=pull)

    def setup_output(self, pin, initial=0):
        self._g.setup(pin, self._g.OUT, initial=initial)

    def read(self, pin):
        return self._g.input(pin)

    def write(self, pin, value):
        self._g.output(pin, value)
