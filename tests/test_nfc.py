import os
import threading
import time

import pytest

from fakes import Card, FakePopen, FakeProcs, NtagCard
from picontrol import tagstore
from picontrol.errors import BusyError, LaunchError, ReaderError
from picontrol.launcher import Launcher
from picontrol.nfc import NfcService, write_and_verify
from picontrol.retroarch import RetroArch


class RecordingLauncher(Launcher):
    """Real validation, recorded launches."""

    def __init__(self, cfg):
        super().__init__(cfg, RetroArch(dry_run=True), procs=FakeProcs(), popen=FakePopen)
        self.launched, self.quits, self.running, self.current = [], 0, False, ("nes", "Zelda II.nes")

    def launch(self, system, rom_path):
        self.launched.append((system, os.path.basename(rom_path)))

    def quit_game(self):
        self.quits += 1

    def poll(self):
        pass

    def game_running(self):
        return self.running

    def current_game(self):
        if self.current is None:
            raise LaunchError("no game is running")
        return self.current


@pytest.fixture
def launcher(cfg):
    return RecordingLauncher(cfg)


@pytest.fixture
def service(cfg, reader, launcher, led):
    return NfcService(cfg, reader, launcher, led, sleep=lambda s: None)


def tagged(reader, sim, values, uid=(1, 2, 3, 4)):
    sim.place(Card(uid))
    tagstore.write_records(reader, reader.read_uid(), values)
    sim.card_state = "idle"
    return sim.card


def test_launches_once_then_again_after_removal_and_reinsertion(service, reader, sim, launcher):
    card = tagged(reader, sim, ["nes", "Super Mario Bros.nes"])
    for t in (0.0, 0.05, 0.1):
        service.step(now=t)
    assert launcher.launched == [("nes", "Super Mario Bros.nes")]  # one launch although the tag stayed
    sim.remove()
    service.step(now=0.2)
    assert service.uid is not None  # absence not yet confirmed
    service.step(now=0.4)
    assert service.uid is None  # removal confirmed
    sim.place(card)
    service.step(now=0.5)
    assert len(launcher.launched) == 2


def test_capital_q_game_names_launch(service, reader, sim, launcher):
    tagged(reader, sim, ["arcade", "Quake Arena.zip"])
    service.step(now=0)
    assert launcher.launched == [("arcade", "Quake Arena.zip")]


def test_blank_and_foreign_tags_are_ignored_without_retries(service, sim, launcher):
    sim.place(Card([7, 7, 7, 7]))
    for t in (0.0, 0.01, 0.02):
        service.step(now=t)
    assert launcher.launched == [] and service.handled and service.attempts == 1


@pytest.mark.parametrize("values", [["nes", "../arcade/Quake Arena.zip"], ["nes", "/etc/passwd"],
                                    ["nes; reboot", "x.nes"], ["nes", "missing.nes"], ["nes"]])
def test_hostile_or_invalid_tag_content_is_never_launched(service, reader, sim, launcher, values):
    tagged(reader, sim, values)
    service.step(now=0)
    assert launcher.launched == [] and service.handled


def test_launch_at_start_can_be_disabled(service, reader, sim, launcher, cfg):
    cfg.nfc.launch_at_start = False
    card = tagged(reader, sim, ["nes", "Zelda II.nes"])
    service.step(now=0)
    assert launcher.launched == []  # tag already there at boot: not launched
    sim.remove()
    service.step(now=0.1)
    service.step(now=0.5)
    sim.place(card)
    service.step(now=0.6)
    assert launcher.launched == [("nes", "Zelda II.nes")]


def test_quit_on_remove(service, reader, sim, launcher, cfg):
    cfg.nfc.quit_on_remove = True
    tagged(reader, sim, ["nes", "Zelda II.nes"])
    service.step(now=0)
    sim.remove()
    service.step(now=0.05)
    assert launcher.quits == 0
    service.step(now=0.3)
    assert launcher.quits == 1


def test_quit_on_remove_is_off_by_default(service, reader, sim, launcher):
    tagged(reader, sim, ["nes", "Zelda II.nes"])
    service.step(now=0)
    sim.remove()
    service.step(now=0.05)
    service.step(now=0.3)
    assert launcher.quits == 0


def test_min_relaunch_interval(service, reader, sim, launcher, cfg):
    cfg.nfc.min_relaunch_interval = 5.0
    tagged(reader, sim, ["nes", "Zelda II.nes"])
    service.step(now=0)
    service.uid, service.handled = None, False  # as after a removal
    service.step(now=1.0)
    assert len(launcher.launched) == 1


def test_read_failures_are_retried_then_abandoned(service, reader, sim, launcher, cfg):
    tagged(reader, sim, ["nes", "Zelda II.nes"])
    orig = tagstore.read_records
    calls = []

    def flaky(*args):
        calls.append(1)
        raise ReaderError("boom")

    tagstore_read = tagstore.read_records
    tagstore.read_records = flaky
    try:
        for t in (0.0, 0.01, 0.02, 0.03, 0.04):
            service.step(now=t)
    finally:
        tagstore.read_records = orig
    assert len(calls) == cfg.nfc.max_read_attempts and service.handled and launcher.launched == []
    assert tagstore.read_records is tagstore_read


def test_reader_errors_propagate_from_step(service, sim):
    sim.fail_next = 1
    with pytest.raises(ReaderError):
        service.step(now=0)


# ---------------------------------------------------------------- writing the current game
def test_write_current_game_to_a_tag(service, reader, sim, launcher, gpio, cfg):
    sim.place(Card([4, 3, 2, 1]))
    service.request_write_current()
    service.step()
    sim.card_state = "idle"
    assert tagstore.read_records(reader, reader.read_uid()) == ["nes", "Zelda II.nes"]
    assert service.handled and launcher.launched == []  # the freshly written tag must not relaunch the game
    assert sim.card.trailers_intact()


def test_write_request_without_a_running_game(service, launcher):
    launcher.current = None
    with pytest.raises(LaunchError):
        service.request_write_current()


def test_write_times_out_without_a_tag(service, cfg, gpio):
    cfg.nfc.write_timeout = 0.1
    service.request_write_current()
    service.step()
    assert service.uid is None
    assert any(pin == cfg.pins.led for pin, _ in gpio.writes)  # error blink


def test_write_and_verify_detects_a_failed_verification(reader, sim):
    sim.place(Card([1, 2, 3, 4]))
    uid = reader.read_uid()
    real = tagstore.read_records
    tagstore.read_records = lambda *a: ["wrong", "content"]
    try:
        with pytest.raises(ReaderError, match="verification"):
            write_and_verify(reader, uid, ["nes", "Zelda II.nes"], sleep=lambda s: None)
    finally:
        tagstore.read_records = real


# ---------------------------------------------------------------- the polling loop
def wait_until(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_run_loop_survives_reader_failures_and_reinitialises(service, reader, sim, launcher):
    tagged(reader, sim, ["nes", "Zelda II.nes"])
    stop = threading.Event()
    thread = threading.Thread(target=service.run, args=(stop,))
    thread.start()
    try:
        assert wait_until(lambda: len(launcher.launched) == 1)
        sim.fail_next = 4  # the reader "freezes": 4 unanswered commands
        assert wait_until(lambda: sim.fail_next == 0, 10)
        sim.garble_next = 2  # then corrupted answers
        assert wait_until(lambda: sim.garble_next == 0, 10)
        firmware_reads = sim.commands.count(0x02)
        assert wait_until(lambda: service.ready, 10)
        assert firmware_reads >= 2  # full re-initialisation happened
        time.sleep(0.3)
        assert len(launcher.launched) == 1  # and no double launch
    finally:
        stop.set()
        thread.join(5)
    assert not thread.is_alive()


def test_run_loop_yields_the_reader_to_other_processes(service, cfg, reader, sim, launcher):
    from picontrol.lock import ReaderLock
    stop = threading.Event()
    with ReaderLock(cfg.nfc.lock_file) as mine:
        assert mine
        thread = threading.Thread(target=service.run, args=(stop,))
        thread.start()
        before = len(sim.commands)
        time.sleep(0.2)
        assert len(sim.commands) == before  # the service did not touch the chip while the lock was held
    assert wait_until(lambda: len(sim.commands) > before)
    stop.set()
    thread.join(5)


# ---------------------------------------------------------------- NTAG tags end to end
UID7 = [0x04, 0xAF, 0x38, 0x62, 0xA1, 0x48, 0x80]


def test_an_ntag_cartridge_launches_its_game(service, reader, sim, launcher):
    sim.place(NtagCard(UID7))
    tagstore.write_records(reader, reader.read_uid(), ["nes", "Super Mario Bros.nes"])
    sim.card_state = "idle"
    for t in (0.0, 0.05, 0.1):
        service.step(now=t)
    assert launcher.launched == [("nes", "Super Mario Bros.nes")]  # once, although the tag stayed


def test_an_ntag_can_be_written_with_the_current_game(service, sim, launcher):
    sim.place(NtagCard(UID7))
    service.request_write_current()
    service.step()
    sim.card_state = "idle"
    assert tagstore.read_records(service.reader, service.reader.read_uid()) == ["nes", "Zelda II.nes"]
    assert launcher.launched == []


def test_a_blank_ntag_is_ignored_without_retries(service, sim, launcher):
    sim.place(NtagCard(UID7))
    for t in (0.0, 0.01, 0.02):
        service.step(now=t)
    assert launcher.launched == [] and service.handled and service.attempts == 1
