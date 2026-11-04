import threading
import time

import pytest

from fakes import Card, FakePopen
from picontrol import tagstore
from picontrol.errors import LaunchError
from picontrol.service import Service, Worker


@pytest.fixture
def svc_factory(cfg, gpio, reader, procs):
    made = {}

    def make(run_result=0, **kwargs):
        made["commands"] = []

        def run_command(cmd):
            made["commands"].append(list(cmd))
            return run_result

        service = Service(cfg, gpio=gpio, run_command=run_command, popen=FakePopen, procs=procs, reader=reader,
                          sleep=lambda s: None, **kwargs)
        made["sent"] = []
        service.retroarch.send = lambda command: made["sent"].append(command) or True
        gpio.levels[cfg.pins.power] = 0  # latching switch ON
        made["service"] = service
        return service, made

    return make


def test_power_off_shuts_down_gracefully(svc_factory, cfg, gpio):
    service, made = svc_factory()
    service.power.step(0.0)
    gpio.levels[cfg.pins.power] = 1  # switch flipped OFF
    service.power.step(1.0)
    service.power.step(1.4)
    assert made["sent"] == ["QUIT"]  # RetroArch gets the chance to save first
    assert made["commands"] == [["sudo", "-n", "shutdown", "-h", "now"]]
    assert service.launcher.shutting_down and gpio.levels[cfg.pins.led] == 0
    service.on_power_off()
    assert len(made["commands"]) == 1  # a second event cannot shut down twice


def test_failed_shutdown_command_rearms(svc_factory):
    service, made = svc_factory(run_result=1)
    service.on_power_off()
    assert not service.launcher.shutting_down
    service.on_power_off()
    assert len(made["commands"]) == 2


def test_dry_run_never_shuts_down(cfg, gpio, reader, procs):
    commands = []
    service = Service(cfg, gpio=gpio, dry_run=True, run_command=lambda c: commands.append(c) or 0, popen=FakePopen,
                      procs=procs, reader=reader, sleep=lambda s: None)
    service.on_power_off()
    assert commands == []


def test_reset_short_press_resets_the_game(svc_factory):
    service, made = svc_factory()
    service.on_reset_short()
    assert made["sent"] == ["RESET"]


def test_reset_long_press_requests_a_tag_write(svc_factory, cfg, procs):
    service, made = svc_factory()
    procs.running.add(service.launcher._emulators)
    with open(cfg.paths.runcommand_info, "w") as handle:
        handle.write("nes\nlr\n/home/pi/RetroPie/roms/nes/Zelda II.nes\n")
    service.on_reset_long()
    assert service.nfc._pending_write[:2] == ("nes", "Zelda II.nes")


def test_reset_long_press_without_a_game_is_refused(svc_factory, gpio, cfg):
    service, made = svc_factory()
    gpio.writes.clear()
    service.on_reset_long()
    assert service.nfc._pending_write is None
    assert any(pin == cfg.pins.led for pin, _ in gpio.writes)  # error blink


def test_disabled_components_are_not_created(cfg, gpio, reader, procs):
    cfg.nfc.enabled = cfg.fan.enabled = cfg.power.enabled = cfg.reset.enabled = False
    service = Service(cfg, gpio=gpio, popen=FakePopen, procs=procs)
    assert service.nfc is None and service.fan is None and service.power is None and service.reset is None
    service.on_reset_long()  # must not crash without NFC


def test_worker_restarts_a_crashing_target():
    stop = threading.Event()
    calls = []

    def flaky(event):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("crash")
        event.set()

    Worker.INITIAL_DELAY = 0.01
    try:
        worker = Worker("flaky", flaky, stop)
        worker.start()
        worker.join(5)
    finally:
        Worker.INITIAL_DELAY = 1.0
    assert len(calls) == 3 and not worker.is_alive()


def test_a_crashing_component_does_not_stop_the_others(svc_factory, cfg, gpio, sim, reader):
    service, made = svc_factory()
    Worker.INITIAL_DELAY = 0.01
    sim.place(Card([1, 2, 3, 4]))
    tagstore.write_records(reader, reader.read_uid(), ["nes", "Zelda II.nes"])
    sim.card_state = "idle"
    launched = []
    service.launcher.launch = lambda system, path: launched.append(system)
    service.nfc.reader.read_uid = lambda: (_ for _ in ()).throw(RuntimeError("bug in the NFC code"))
    stop = threading.Event()
    thread = threading.Thread(target=service.run, args=(stop, False))
    thread.start()
    try:
        time.sleep(0.3)
        gpio.levels[cfg.pins.power] = 1  # the power button still works
        end = time.monotonic() + 3
        while not made["commands"] and time.monotonic() < end:
            time.sleep(0.02)
        assert made["commands"] == [["sudo", "-n", "shutdown", "-h", "now"]]
    finally:
        Worker.INITIAL_DELAY = 1.0
        stop.set()
        thread.join(8)


def test_service_end_to_end(svc_factory, cfg, gpio, sim, reader):
    service, made = svc_factory()
    sim.place(Card([1, 2, 3, 4]))
    tagstore.write_records(reader, reader.read_uid(), ["arcade", "Quake Arena.zip"])
    sim.card_state = "idle"
    stop = threading.Event()
    thread = threading.Thread(target=service.run, args=(stop, False))
    thread.start()
    try:
        end = time.monotonic() + 5
        while not FakePopen.instances and time.monotonic() < end:
            time.sleep(0.02)
        assert FakePopen.instances[0].argv[2:4] == ["_SYS_", "arcade"]
        assert gpio.levels[cfg.pins.led] == 1  # LED lit while the service runs
    finally:
        stop.set()
        thread.join(8)
    assert gpio.levels[cfg.pins.led] == 0
    assert gpio.levels[cfg.pins.fan] == 1  # fail-safe: fan on when the controller stops
