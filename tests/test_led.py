from fakes import FakeGpio
from picontrol.led import Led


def test_on_off_and_blink_restore_the_steady_state():
    gpio = FakeGpio()
    led = Led(gpio, 14, sleep=lambda s: None)
    led.on()
    gpio.writes.clear()
    led.blink(2)
    assert [v for _, v in gpio.writes] == [0, 1, 0, 1]
    assert gpio.levels[14] == 1
    led.off()
    gpio.writes.clear()
    led.blink(1)
    assert gpio.levels[14] == 0 and [v for _, v in gpio.writes] == [1, 0]


def test_disabled_led_never_touches_the_pin():
    gpio = FakeGpio()
    led = Led(gpio, 14, enabled=False, sleep=lambda s: None)
    led.on()
    led.blink(3)
    led.error()
    assert 14 not in gpio.levels
