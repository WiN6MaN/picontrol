import threading

from fakes import FakeGpio
from picontrol.fan import FanController, read_temperature

PIN = 18


def make(temps, min_run=20.0):
    gpio = FakeGpio()
    values = list(temps)
    fan = FanController(gpio, PIN, 60, 50, min_run, lambda: values.pop(0) if values else None)
    return fan, gpio


def drive(fan, readings):
    states = []
    for now, temp in readings:
        fan._read_temp = lambda t=temp: t
        fan.step(now)
        states.append(fan.is_on)
    return states


def test_hysteresis():
    fan, gpio = make([])
    states = drive(fan, [(0, 40), (10, 59.9), (20, 60), (30, 55), (40, 51), (50, 50), (60, 45)])
    assert states == [False, False, True, True, True, False, False]
    assert gpio.levels[PIN] == 0


def test_minimum_run_time_prevents_chatter():
    fan, _ = make([], min_run=30)
    states = drive(fan, [(0, 61), (5, 45), (29, 45), (31, 45)])
    assert states == [True, True, True, False]


def test_failsafe_turns_the_fan_on_when_the_sensor_is_unreadable():
    fan, gpio = make([None, None, None, None])
    for now in (0, 1, 2):
        fan.step(now)
    assert fan.is_on and gpio.levels[PIN] == 1


def test_a_single_bad_reading_is_tolerated():
    fan, _ = make([None])
    fan.step(0)
    assert not fan.is_on


def test_fan_is_forced_on_when_the_controller_stops():
    fan, gpio = make([40, 40])
    stop = threading.Event()
    stop.set()
    fan.run(stop, 0.01)
    assert gpio.levels[PIN] == 1


def test_read_temperature(tmp_path):
    good = tmp_path / "temp"
    good.write_text("45123\n")
    assert read_temperature(str(good)) == 45.123
    good.write_text("garbage")
    assert read_temperature(str(good)) is None
    assert read_temperature(str(tmp_path / "missing")) is None
