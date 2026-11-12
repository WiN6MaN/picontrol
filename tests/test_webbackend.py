import os
import threading
import time

import pytest

from fakes import Card, NtagCard
from picontrol import tagstore
from picontrol.config import Config
from picontrol.errors import ApiError
from picontrol.nfc import TagJob
from picontrol.webbackend import Backend


class ImmediateTimer:
    """Stands in for threading.Timer: runs the action as soon as it is started."""
    started = []

    def __init__(self, delay, action):
        self.delay, self.action = delay, action

    def start(self):
        ImmediateTimer.started.append(self.delay)
        self.action()


@pytest.fixture
def backend(service, clock):
    ImmediateTimer.started = []
    return Backend(service, clock=clock, timer=ImmediateTimer)


@pytest.fixture
def library(cfg):
    roms = cfg.paths.roms_dir
    for name in (".hidden", "gamelist.xml", "Mario Kart.nes", "mario bros 3.nes", "Metroid.nes", "Zelda.nes"):
        open(os.path.join(roms, "nes", name), "w").close()
    os.makedirs(os.path.join(roms, "nes", "media"))
    os.makedirs(os.path.join(roms, "snes"))
    os.makedirs(os.path.join(roms, "Bad Name"))
    return roms


# ------------------------------------------------------------------ status
def test_status_snapshot(backend, service, cfg, gpio, tmp_path):
    (tmp_path / "temp").write_text("47500")
    cfg.fan.temp_path = str(tmp_path / "temp")
    gpio.levels[cfg.pins.power] = 0
    status = backend.status()
    assert status["temperature"] == 47.5 and status["power_switch"] == "on" and status["version"]
    assert status["fan"] == {"enabled": True, "on": False, "threshold_on": 60.0, "threshold_off": 50.0}
    assert status["game"] == {"running": False, "system": None, "rom": None}
    assert status["nfc"]["enabled"] and status["nfc"]["tag"] is None and status["restart_required"] is False
    gpio.levels[cfg.pins.power] = 1
    assert backend.status()["power_switch"] == "off"


def test_status_with_a_running_game(backend, service, procs, cfg):
    procs.running.add(service.launcher._emulators)
    with open(cfg.paths.runcommand_info, "w") as handle:
        handle.write("nes\nlr\n/x/nes/Zelda II.nes\n")
    assert backend.status()["game"] == {"running": True, "system": "nes", "rom": "Zelda II.nes"}


def test_status_with_components_disabled(cfg, gpio, reader, procs):
    from picontrol.service import Service
    from fakes import FakePopen
    cfg.nfc.enabled = cfg.fan.enabled = cfg.power.enabled = False
    svc = Service(cfg, gpio=gpio, popen=FakePopen, procs=procs)
    status = Backend(svc).status()
    assert status["nfc"] == {"enabled": False} and status["power_switch"] is None and status["fan"]["on"] is None


# ------------------------------------------------------------------ ROM browsing
def test_systems_listing(backend, library):
    systems = {s["name"]: s["count"] for s in backend.systems()}
    assert systems == {"arcade": 1, "nes": 6, "snes": 0}  # hidden files, gamelist.xml, media/ and odd folder names are skipped


def test_rom_search_and_pagination(backend, library):
    everything = backend.roms("nes")
    assert everything["total"] == 6 and everything["items"] == sorted(everything["items"], key=str.casefold)
    assert backend.roms("nes", "MARIO")["items"] == ["mario bros 3.nes", "Mario Kart.nes", "Super Mario Bros.nes"]
    assert backend.roms("nes", "mario 3")["items"] == ["mario bros 3.nes"]  # every word must match
    page = backend.roms("nes", "", offset=1, limit=2)
    assert page["items"] == everything["items"][1:3] and page["total"] == 6 and page["offset"] == 1
    assert len(backend.roms("nes", "", 0, 10 ** 6)["items"]) == 6  # limit is clamped, never an error


@pytest.mark.parametrize("system, status", [("../etc", 400), ("nes; rm", 400), ("", 400), (None, 400), ("nosuch", 404)])
def test_rom_browsing_rejects_bad_systems(backend, library, system, status):
    with pytest.raises(ApiError) as info:
        backend.roms(system)
    assert info.value.status == status


def test_listings_are_cached_briefly(backend, library, clock):
    assert backend.roms("snes")["total"] == 0
    open(os.path.join(library, "snes", "New Game.sfc"), "w").close()
    assert backend.roms("snes")["total"] == 0  # cached
    clock.advance(31)
    assert backend.roms("snes")["total"] == 1


# ------------------------------------------------------------------ NFC tags (real NFC thread + simulator)
@pytest.fixture
def nfc_thread(service):
    stop = threading.Event()
    thread = threading.Thread(target=service.nfc.run, args=(stop,))
    thread.start()
    yield service.nfc
    stop.set()
    thread.join(5)


def test_write_then_read_a_tag(backend, nfc_thread, sim, library):
    sim.place(Card([1, 2, 3, 4]))
    result = backend.tag("write", "nes", "Zelda.nes")
    assert result == {"uid": "01020304", "system": "nes", "rom": "Zelda.nes"}
    assert tagstore.read_records(backend.service.nfc.reader, sim_uid(sim, backend)) == ["nes", "Zelda.nes"]
    sim.card_state = "idle"
    read = backend.tag("read")
    assert read == {"uid": "01020304", "records": ["nes", "Zelda.nes"]}
    assert backend.service.launcher.proc is None  # reading/writing from the web never launches the game


def sim_uid(sim, backend):
    sim.card_state = "idle"
    return backend.service.nfc.reader.read_uid()


def test_write_then_read_an_ntag_through_the_web_backend(backend, nfc_thread, sim, library):
    sim.place(NtagCard([0x04, 0xAF, 0x38, 0x62, 0xA1, 0x48, 0x80]))
    assert backend.tag("write", "nes", "Zelda.nes")["uid"] == "04af3862a14880"
    sim.card_state = "idle"
    assert backend.tag("read") == {"uid": "04af3862a14880", "records": ["nes", "Zelda.nes"]}


def test_a_too_small_tag_is_reported_not_crashed(backend, nfc_thread, sim, library):
    sim.place(NtagCard([0x04, 1, 2, 3, 4, 5, 6], size=48))
    long_name = "L" * 100 + ".nes"
    open(os.path.join(library, "nes", long_name), "w").close()
    with pytest.raises(ApiError) as info:
        backend.tag("write", "nes", long_name)
    assert info.value.status == 422 and "too long for this tag" in str(info.value)


def test_reading_a_foreign_tag_reports_a_note(backend, nfc_thread, sim):
    sim.place(Card([7, 7, 7, 7]))
    result = backend.tag("read")
    assert result["records"] is None and result["uid"] == "07070707" and "NDEF" in result["note"]


def test_write_validates_the_rom_before_touching_the_reader(backend, nfc_thread, sim, library):
    sim.place(Card([1, 2, 3, 4]))
    for system, rom in [("nes", "../snes/x"), ("nes", "missing.nes"), ("nes; reboot", "Zelda.nes")]:
        with pytest.raises(ApiError) as info:
            backend.tag("write", system, rom)
        assert info.value.status == 400
    assert sim.card.mem[4] == bytearray(16)


def test_tag_operations_time_out_without_a_tag(backend, nfc_thread, cfg, library):
    cfg.nfc.write_timeout = 0.3
    with pytest.raises(ApiError) as info:
        backend.tag("read")
    assert info.value.status == 408


def test_a_second_operation_is_refused_while_one_is_pending(backend, service, library):
    service.nfc.submit(TagJob("read", timeout=30))  # nobody serves it: stays pending
    with pytest.raises(ApiError) as info:
        backend.tag("read")
    assert info.value.status == 409


def test_write_current_needs_a_running_game(backend, nfc_thread):
    with pytest.raises(ApiError) as info:
        backend.tag("write-current")
    assert info.value.status == 409


def test_write_current_game(backend, nfc_thread, sim, procs, service, cfg, library):
    procs.running.add(service.launcher._emulators)
    with open(cfg.paths.runcommand_info, "w") as handle:
        handle.write("nes\nlr\n%s/nes/Zelda.nes\n" % library)
    sim.place(Card([1, 2, 3, 4]))
    assert backend.tag("write-current")["rom"] == "Zelda.nes"


def test_nfc_disabled_and_unknown_operations(cfg, gpio, procs):
    from picontrol.service import Service
    from fakes import FakePopen
    cfg.nfc.enabled = False
    backend = Backend(Service(cfg, gpio=gpio, popen=FakePopen, procs=procs))
    with pytest.raises(ApiError) as info:
        backend.tag("read")
    assert info.value.status == 409


def test_unknown_tag_operation(backend, nfc_thread):
    with pytest.raises(ApiError) as info:
        backend.tag("format")
    assert info.value.status == 400


# ------------------------------------------------------------------ configuration
@pytest.fixture
def conf_file(cfg, tmp_path):
    path = tmp_path / "picontrol.conf"
    path.write_text("[fan]\n; comment kept\nthreshold_on = 60.0\n")
    cfg.source = str(path)
    return path


def test_config_view_and_update(backend, conf_file):
    view = backend.config_view()
    assert view["restart_required"] is False
    assert {s["name"]: s["value"] for s in view["settings"]}["fan.threshold_on"] == 60.0
    assert backend.config_update({"fan.threshold_on": 65, "nfc.quit_on_remove": True}) == {"ok": True, "restart_required": True}
    assert "; comment kept" in conf_file.read_text() and Config.load(str(conf_file)).nfc.quit_on_remove
    assert {s["name"]: s["value"] for s in backend.config_view()["settings"]}["fan.threshold_on"] == 65.0
    assert backend.config_view()["restart_required"] and backend.status()["restart_required"]


def test_config_update_errors(backend, conf_file):
    before = conf_file.read_text()
    for changes in ({"power.shutdown_command": "rm -rf /"}, {"fan.threshold_on": 10}, {"fan.interval": "x"}, {}):
        with pytest.raises(ApiError) as info:
            backend.config_update(changes)
        assert info.value.status == 400
    assert conf_file.read_text() == before and not backend.pending_restart


def test_config_update_when_the_file_cannot_be_written(backend, cfg, tmp_path):
    cfg.source = str(tmp_path / "no" / "such" / "dir" / "picontrol.conf")
    with pytest.raises(ApiError) as info:
        backend.config_update({"led.enabled": False})
    assert info.value.status == 500


# ------------------------------------------------------------------ system actions
def test_restart_reboot_and_shutdown(backend, service):
    assert backend.restart_service() == {"ok": True} and service.restart_requested
    backend.reboot()
    backend.shutdown()
    assert service.commands == [["sudo", "-n", "reboot"]]  # a second graceful stop is ignored (already stopping)
    assert ImmediateTimer.started == [0.5, 0.5, 0.5]  # always after a short delay, so the HTTP answer gets out first


def test_shutdown_uses_the_configured_command(backend, service):
    backend.shutdown()
    assert service.commands == [["sudo", "-n", "shutdown", "-h", "now"]] and service.sent == ["QUIT"]


def test_log_tail(backend, cfg, tmp_path):
    assert backend.log_tail() == {"lines": []}
    with open(cfg.logging.file, "w") as handle:
        handle.write("\n".join("line %d" % i for i in range(300)) + "\n")
    assert backend.log_tail(3)["lines"] == ["line 297", "line 298", "line 299"]
    assert len(backend.log_tail(10 ** 6)["lines"]) == 300  # capped at 500, here the whole file
