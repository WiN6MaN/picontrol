from fakes import FakeGpio
from picontrol.buttons import PowerSwitch, ResetButton

POWER, RESET = 3, 23


def make_power(gpio, calls, debounce=0.3):
    switch = PowerSwitch(gpio, POWER, 1, debounce, lambda: calls.append("off"))
    gpio.levels[POWER] = 0  # latching switch closed = ON
    return switch


def test_switch_on_does_nothing():
    gpio, calls = FakeGpio(), []
    switch = make_power(gpio, calls)
    for t in (0, 1, 2, 3):
        switch.step(t)
    assert calls == []


def test_a_glitch_shorter_than_the_debounce_is_ignored():
    gpio, calls = FakeGpio(), []
    switch = make_power(gpio, calls)
    gpio.levels[POWER] = 1
    switch.step(0.0)
    switch.step(0.1)
    gpio.levels[POWER] = 0
    switch.step(0.2)
    switch.step(0.6)
    assert calls == []


def test_switching_off_fires_once_and_rearms_when_switched_on():
    gpio, calls = FakeGpio(), []
    switch = make_power(gpio, calls)
    gpio.levels[POWER] = 1
    for t in (0.0, 0.2, 0.4, 0.6, 5.0):
        switch.step(t)
    assert calls == ["off"]  # exactly once, however long it stays off
    gpio.levels[POWER] = 0
    switch.step(6.0)
    gpio.levels[POWER] = 1
    switch.step(7.0)
    switch.step(7.4)
    assert calls == ["off", "off"]


def test_active_low_variant():
    gpio, calls = FakeGpio(), []
    switch = PowerSwitch(gpio, POWER, 0, 0.1, lambda: calls.append("off"))
    gpio.levels[POWER] = 0
    switch.step(0)
    switch.step(0.2)
    assert calls == ["off"]


def make_reset(gpio, events):
    button = ResetButton(gpio, RESET, 0.05, 2.0, lambda: events.append("short"), lambda: events.append("long"))
    gpio.levels[RESET] = 1  # released (pull-up)
    return button


def press(gpio, button, start, end, step=0.05):
    gpio.levels[RESET] = 0
    t = start
    while t < end:
        button.step(t)
        t += step
    gpio.levels[RESET] = 1
    button.step(end)


def test_short_press_fires_on_release():
    gpio, events = FakeGpio(), []
    button = make_reset(gpio, events)
    press(gpio, button, 0, 0.3)
    assert events == ["short"]


def test_contact_bounce_is_ignored():
    gpio, events = FakeGpio(), []
    button = make_reset(gpio, events)
    gpio.levels[RESET] = 0
    button.step(0.0)
    gpio.levels[RESET] = 1
    button.step(0.01)
    assert events == []


def test_long_press_fires_while_held_and_not_a_short_press_on_release():
    gpio, events = FakeGpio(), []
    button = make_reset(gpio, events)
    gpio.levels[RESET] = 0
    t = 0.0
    while t < 1.95:
        button.step(t)
        t += 0.05
    assert events == []
    while t < 2.3:
        button.step(t)
        t += 0.05
    assert events == ["long"]  # fired once, while still held
    gpio.levels[RESET] = 1
    button.step(t)
    assert events == ["long"]


def test_two_consecutive_presses():
    gpio, events = FakeGpio(), []
    button = make_reset(gpio, events)
    press(gpio, button, 0, 0.3)
    press(gpio, button, 1, 1.3)
    assert events == ["short", "short"]
