"""Interactive hardware tests for assembly and debugging. / Tests matériels interactifs (montage, dépannage).

``picontrol test led|fan|buttons|nfc``. Each test drives or reads the real pins named in the
configuration and tells you what you should observe.
"""

import time

from .errors import ReaderError
from .lock import ReaderLock
from .nfc import reader_from_config
from .pn532 import hexstr


def test_led(cfg, gpio, out=print):
    pin = cfg.pins.led
    out("LED on GPIO %d: 5 blinks. You should see the front-panel LED blink." % pin)
    gpio.setup_output(pin, 0)
    for _ in range(5):
        gpio.write(pin, 1)
        time.sleep(0.3)
        gpio.write(pin, 0)
        time.sleep(0.3)
    gpio.write(pin, 1)
    return 0


def test_fan(cfg, gpio, out=print, seconds=5):
    pin = cfg.pins.fan
    out("Fan on GPIO %d: ON for %d s. The fan should spin, then stop." % (pin, seconds))
    gpio.setup_output(pin, 0)
    gpio.write(pin, 1)
    time.sleep(seconds)
    gpio.write(pin, 0)
    return 0


def test_buttons(cfg, gpio, out=print, seconds=20):
    out("Watching the buttons for %d s. Toggle the power switch and press reset (Ctrl+C to stop)." % seconds)
    gpio.setup_input(cfg.pins.power, pull_up=True)
    gpio.setup_input(cfg.pins.reset, pull_up=True)
    last = None
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            power_off = gpio.read(cfg.pins.power) == cfg.power_off_level
            reset_down = gpio.read(cfg.pins.reset) == 0
            state = (power_off, reset_down)
            if state != last:
                out("power switch: %-3s | reset: %s" % ("OFF" if power_off else "ON",
                                                         "PRESSED" if reset_down else "released"))
                last = state
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    return 0


def test_nfc(cfg, gpio, out=print, seconds=15):
    with ReaderLock(cfg.nfc.lock_file, wait=20) as got:
        if not got:
            out("The reader is busy (is the service running? it will release it between polls - retry).")
            return 1
        reader = reader_from_config(cfg, gpio)
        try:
            fw = reader.init()
        except ReaderError as exc:
            out("PN532 not found: %s" % exc)
            out("Check the module's mode switches (SPI), the 6-pin cable and the pins in [pins].")
            return 1
        out("PN532 found (firmware %d.%d). Present a tag (%d s)..." % (fw[1], fw[2], seconds))
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            uid = reader.read_uid()
            if uid:
                out("Tag detected: UID %s" % hexstr(uid))
                return 0
            time.sleep(0.3)
        out("No tag detected.")
        return 1
