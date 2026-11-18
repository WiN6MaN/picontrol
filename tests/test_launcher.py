import os
import subprocess

import pytest

from fakes import FakePopen, FakeProcs
from picontrol import session
from picontrol.errors import LaunchError
from picontrol.launcher import ES_PATTERN, Launcher
from picontrol.retroarch import RetroArch


class RecordingRetroArch(RetroArch):
    def __init__(self):
        super().__init__(dry_run=True)
        self.sent = []

    def send(self, command):
        self.sent.append(command)
        return True


@pytest.fixture
def launcher(cfg, procs, tmp_path):
    return Launcher(cfg, RecordingRetroArch(), procs=procs, popen=FakePopen, sleep=lambda s: None,
                    runtime_dir=str(tmp_path))


# ------------------------------------------------------------------ validation
def test_resolve_rom(launcher, cfg):
    path = launcher.resolve_rom("nes", "Super Mario Bros.nes")
    assert path == os.path.join(os.path.realpath(cfg.paths.roms_dir), "nes", "Super Mario Bros.nes")


@pytest.mark.parametrize("system, rom", [
    ("nes", "../arcade/Quake Arena.zip"), ("nes", "/etc/passwd"), ("nes", "a/b.nes"), ("nes", "a\\b.nes"),
    ("nes; reboot", "x.nes"), ("nes", "$(reboot).nes"), ("..", "x"), ("", "x"), ("nes", ""), ("nes", ".."),
    ("nes", "missing.nes"), ("nes", "x\x00y"), ("a" * 41, "x"), ("ne s", "x"),
])
def test_hostile_names_are_rejected(launcher, system, rom):
    with pytest.raises(LaunchError):
        launcher.resolve_rom(system, rom)


def test_symlink_escaping_the_system_folder_is_rejected(launcher, cfg):
    os.symlink("/etc/passwd", os.path.join(cfg.paths.roms_dir, "nes", "evil.nes"))
    with pytest.raises(LaunchError):
        launcher.resolve_rom("nes", "evil.nes")


# ------------------------------------------------------------------ current game
def write_info(cfg, text):
    with open(cfg.paths.runcommand_info, "w") as handle:
        handle.write(text)


def test_current_game(launcher, cfg, procs):
    procs.running.add(launcher._emulators)
    write_info(cfg, "nes\nlr-fceumm\n/home/pi/RetroPie/roms/nes/Zelda II.nes\nretroarch ...\n")
    assert launcher.current_game() == ("nes", "Zelda II.nes")


def test_current_game_requires_a_running_emulator(launcher, cfg):
    write_info(cfg, "nes\nx\n/home/pi/RetroPie/roms/nes/Zelda II.nes\n")
    with pytest.raises(LaunchError, match="no game"):
        launcher.current_game()


def test_current_game_with_missing_or_odd_info(launcher, cfg, procs):
    procs.running.add(launcher._emulators)
    with pytest.raises(LaunchError):
        launcher.current_game()
    write_info(cfg, "nes\n")
    with pytest.raises(LaunchError):
        launcher.current_game()
    write_info(cfg, "nes\nx\n/somewhere/else/Unknown.nes\n")
    with pytest.raises(LaunchError):
        launcher.current_game()


# ------------------------------------------------------------------ launching
def test_launch_uses_an_argument_list_never_a_shell(launcher, cfg):
    launcher.launch("nes", "/roms/nes/a; reboot.nes")
    proc = FakePopen.instances[-1]
    assert proc.argv == [cfg.paths.runcommand, "0", "_SYS_", "nes", "/roms/nes/a; reboot.nes"]
    assert "shell" not in proc.kwargs and launcher.es_stopped


def test_launch_stops_emulationstation_and_emulators_first(launcher, procs):
    procs.running.update({ES_PATTERN, launcher._emulators})
    launcher.launch("nes", "/roms/nes/x.nes")
    killed = [(call[1], call[2]) for call in procs.calls if call[0] == "pkill"]
    assert ("TERM", ES_PATTERN) in killed and ("TERM", launcher._emulators) in killed


def test_launching_over_a_running_game_waits_for_it(launcher):
    launcher.launch("nes", "/roms/nes/a.nes")
    first = FakePopen.instances[-1]
    first.wait = lambda timeout=None: setattr(first, "returncode", 0)
    launcher.launch("nes", "/roms/nes/b.nes")
    assert first.returncode == 0 and len(FakePopen.instances) == 2


def test_emulationstation_comes_back_when_the_game_ends(launcher, cfg):
    launcher.launch("nes", "/roms/nes/a.nes")
    launcher.poll()
    assert len(FakePopen.instances) == 1  # game still running: ES stays stopped
    FakePopen.instances[0].finish(0)
    launcher.poll()
    assert FakePopen.instances[-1].argv == list(cfg.paths.emulationstation_command)
    launcher.poll()
    assert len(FakePopen.instances) == 2  # restarted exactly once


def test_no_restart_if_es_is_already_running_or_shutting_down(launcher, procs):
    launcher.launch("nes", "/roms/nes/a.nes")
    FakePopen.instances[0].finish(0)
    procs.running.add(ES_PATTERN)
    launcher.poll()
    assert len(FakePopen.instances) == 1
    launcher.launch("nes", "/roms/nes/a.nes")
    FakePopen.instances[-1].finish(0)
    procs.running.discard(ES_PATTERN)
    launcher.shutting_down = True
    launcher.poll()
    assert len(FakePopen.instances) == 2


def test_nothing_launches_while_shutting_down(launcher):
    launcher.shutting_down = True
    launcher.launch("nes", "/roms/nes/a.nes")
    assert FakePopen.instances == []


def test_dry_run_does_nothing(cfg, procs, tmp_path):
    launcher = Launcher(cfg, RecordingRetroArch(), procs=procs, popen=FakePopen, dry_run=True,
                        runtime_dir=str(tmp_path))
    launcher.launch("nes", "/roms/nes/a.nes")
    launcher.poll()
    assert FakePopen.instances == [] and procs.calls == []


def test_quit_game_asks_retroarch_then_falls_back_to_terminating(launcher, procs):
    launcher.launch("nes", "/roms/nes/a.nes")
    proc = FakePopen.instances[-1]

    def stubborn(timeout=None):
        raise subprocess.TimeoutExpired("x", timeout)

    proc.wait = stubborn
    launcher.quit_game()
    assert launcher.retroarch.sent == ["QUIT"]
    assert ("pkill", "TERM", launcher._emulators, False) in procs.calls


def test_quit_game_when_nothing_runs(launcher):
    launcher.quit_game()
    assert launcher.retroarch.sent == []


def test_extra_emulators_from_config(cfg, procs):
    cfg.paths.extra_emulators = ("myemu",)
    assert "myemu" in Launcher(cfg, RecordingRetroArch(), procs=procs)._emulators


# ------------------------------------------------------------------ through the console session
class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def with_session(monkeypatch):
    """Pretend a console session is running."""
    monkeypatch.setattr(session, "session_running", lambda *a, **k: True)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def sess_launcher(cfg, procs, tmp_path, clock, with_session):
    """A launcher whose 'session' takes the request after the first pkill round, like the real one would."""
    state = {"rounds": 0}

    def sleep(seconds):
        clock.now += seconds
        state["rounds"] += 1
        if state["rounds"] == state.get("take_after", 2):
            session.take_request(str(tmp_path))

    launcher = Launcher(cfg, RecordingRetroArch(), procs=procs, popen=FakePopen, sleep=sleep,
                        runtime_dir=str(tmp_path), clock=clock)
    launcher.state = state
    return launcher


def test_launch_hands_the_game_to_the_session(sess_launcher, procs, tmp_path):
    procs.running.update({ES_PATTERN, sess_launcher._emulators})
    seen = []
    original = session.request_launch
    session.request_launch = lambda *a, **k: (seen.append(a), original(*a, **k))[1]
    try:
        sess_launcher.launch("nes", os.path.join(sess_launcher.cfg.paths.roms_dir, "nes", "Zelda II.nes"))
    finally:
        session.request_launch = original
    assert seen[0][:2] == ("nes", "Zelda II.nes")
    assert FakePopen.instances == []  # nothing is started behind the console's back
    assert not sess_launcher.es_stopped and not session.request_pending(str(tmp_path))
    killed = {(call[1], call[2]) for call in procs.calls if call[0] == "pkill"}
    assert ("TERM", ES_PATTERN) in killed and ("TERM", sess_launcher._emulators) in killed
    assert sess_launcher.game_running()


def test_the_request_is_repeated_until_the_session_takes_it_then_escalates(sess_launcher, procs):
    sess_launcher.state["take_after"] = 8
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    signals = [call[1] for call in procs.calls if call[0] == "pkill" and call[2] == ES_PATTERN]
    assert signals[:6] == ["TERM"] * 6 and signals[6:] == ["KILL"] * 2


def test_an_unresponsive_session_falls_back_to_the_direct_method(sess_launcher, tmp_path, procs):
    sess_launcher.state["take_after"] = 10 ** 6  # never
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    assert not session.request_pending(str(tmp_path))  # the stale request is withdrawn
    assert FakePopen.instances[-1].argv[-2:] == ["nes", "/roms/nes/x.nes"] and sess_launcher.es_stopped


def test_without_a_session_the_direct_method_is_used(launcher, caplog):
    with caplog.at_level("WARNING", logger="picontrol.launcher"):
        launcher.launch("nes", "/roms/nes/x.nes")
    assert FakePopen.instances and "No console session" in caplog.text


def test_a_failed_request_falls_back_too(sess_launcher, monkeypatch):
    def refuse(*args, **kwargs):
        raise LaunchError("no /dev/shm")

    monkeypatch.setattr(session, "request_launch", refuse)
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    assert FakePopen.instances


def test_session_game_is_tracked_through_the_emulator_process(sess_launcher, procs, clock):
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    assert sess_launcher.game_running()  # the emulator has not appeared yet: still considered running
    procs.running.add(sess_launcher._emulators)
    clock.now += 2
    assert sess_launcher.game_running()
    procs.running.discard(sess_launcher._emulators)
    clock.now += 2
    assert not sess_launcher.game_running()  # it was seen, now it is gone


def test_a_game_that_never_starts_stops_counting_after_a_while(sess_launcher, clock):
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    clock.now += 30
    assert not sess_launcher.game_running()


def test_poll_never_restarts_emulationstation_in_session_mode(sess_launcher, procs, clock):
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    clock.now += 40
    sess_launcher.poll()
    assert FakePopen.instances == []


def test_quit_game_in_session_mode(sess_launcher, procs, clock):
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    procs.running.add(sess_launcher._emulators)
    clock.now += 2
    procs.pkill = lambda *a, **k: procs.calls.append(("pkill",) + a)  # the emulator ignores us
    sess_launcher.quit_game()
    assert sess_launcher.retroarch.sent == ["QUIT"]
    assert ("pkill", "TERM", sess_launcher._emulators) in procs.calls


def test_quit_game_in_session_mode_when_the_emulator_exits_by_itself(sess_launcher, procs, clock):
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    procs.running.add(sess_launcher._emulators)
    clock.now += 2
    sess_launcher.retroarch.send = lambda command: procs.running.discard(sess_launcher._emulators) or True
    calls_before = len(procs.calls)
    sess_launcher.quit_game()
    assert len(procs.calls) == calls_before  # no pkill needed


def test_begin_and_cancel_shutdown(with_session, launcher, tmp_path):
    launcher.begin_shutdown()
    assert launcher.shutting_down and session.take_request(str(tmp_path)) == {"action": "exit"}
    launcher.begin_shutdown()
    launcher.cancel_shutdown()
    assert not launcher.shutting_down and not session.request_pending(str(tmp_path))


def test_begin_shutdown_without_session_or_in_dry_run_writes_nothing(launcher, cfg, procs, tmp_path, monkeypatch):
    launcher.begin_shutdown()
    assert launcher.shutting_down and not session.request_pending(str(tmp_path))
    monkeypatch.setattr(session, "session_running", lambda *a, **k: True)
    dry = Launcher(cfg, RecordingRetroArch(), procs=procs, dry_run=True, runtime_dir=str(tmp_path))
    dry.begin_shutdown()
    assert not session.request_pending(str(tmp_path))
