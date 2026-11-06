import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from fakes import FakeGpio, FakePopen, FakeProcs, PN532Sim  # noqa: E402

from picontrol.config import Config  # noqa: E402
from picontrol.led import Led  # noqa: E402
from picontrol.pn532 import PN532  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    cfg = Config.defaults()
    roms = tmp_path / "roms"
    for system in ("nes", "arcade"):
        (roms / system).mkdir(parents=True)
    (roms / "nes" / "Super Mario Bros.nes").write_text("x")
    (roms / "nes" / "Zelda II.nes").write_text("x")
    (roms / "arcade" / "Quake Arena.zip").write_text("x")
    cfg.paths.roms_dir = str(roms)
    cfg.paths.runcommand_info = str(tmp_path / "runcommand.info")
    cfg.paths.retroarch_cfg = str(tmp_path / "retroarch.cfg")
    cfg.nfc.lock_file = str(tmp_path / "nfc.lock")
    cfg.nfc.poll_interval = cfg.nfc.poll_interval_game = 0.01
    cfg.nfc.remove_delay = 0.15
    cfg.nfc.min_relaunch_interval = 0.0
    cfg.nfc.write_timeout = 1.0
    cfg.logging.file = str(tmp_path / "picontrol.log")
    cfg.power.quit_grace = 0.0
    return cfg


@pytest.fixture
def sim():
    return PN532Sim()


@pytest.fixture
def gpio(sim):
    return FakeGpio(sim)


@pytest.fixture
def reader(gpio, cfg):
    pn = PN532(gpio, cs=cfg.pins.nfc_cs, sclk=cfg.pins.nfc_sclk, mosi=cfg.pins.nfc_mosi, miso=cfg.pins.nfc_miso,
               wake_delay=0, sleep=lambda s: None)
    pn.init()
    return pn


@pytest.fixture
def led(gpio, cfg):
    return Led(gpio, cfg.pins.led, sleep=lambda s: None)


@pytest.fixture
def procs():
    return FakeProcs()


@pytest.fixture(autouse=True)
def reset_popen():
    FakePopen.instances = []
    yield


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def service(cfg, gpio, reader, procs):
    """A real Service wired to the fakes (no web server started)."""
    from picontrol.service import Service
    svc = Service(cfg, gpio=gpio, run_command=lambda c: svc.commands.append(list(c)) or 0, popen=FakePopen,
                  procs=procs, reader=reader, sleep=lambda s: None)
    svc.commands, svc.sent = [], []
    svc.retroarch.send = lambda command: svc.sent.append(command) or True
    return svc
