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


def kills(procs, pattern, sig=None):
    return [call[1] for call in procs.calls if call[0] == "pkill" and call[2] == pattern
            and (sig is None or call[1] == sig)]


def test_emulationstation_is_never_killed_by_force_while_it_may_still_be_loading(sess_launcher, procs):
    """The boot bug: ES ignores SIGTERM while it loads; a SIGKILL after 3 s broke the console keyboard."""
    sess_launcher.state["take_after"] = 12  # 12 rounds of 0.5 s = 6 s: ES is still loading
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    assert kills(procs, ES_PATTERN, "KILL") == []
    assert kills(procs, ES_PATTERN, "TERM") == ["TERM"] * 3  # asked politely again every 2 s (t = 0, 2, 4)


def test_a_hung_emulator_is_killed_but_emulationstation_still_only_gets_term(sess_launcher, procs):
    sess_launcher.state["take_after"] = 40  # 20 s
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    assert kills(procs, sess_launcher._emulators, "KILL") and kills(procs, ES_PATTERN, "KILL") == []


def test_an_emulationstation_that_never_stops_is_finally_killed(sess_launcher, procs):
    sess_launcher.state["take_after"] = 10 ** 6
    sess_launcher.launch("nes", "/roms/nes/x.nes")  # gives up after SESSION_WAIT, then the direct method runs
    assert kills(procs, ES_PATTERN, "KILL")


def test_a_shutdown_during_the_wait_leaves_the_exit_request_alone(sess_launcher, tmp_path):
    def sleep(seconds):
        sess_launcher.begin_shutdown()  # the power switch is flipped: the 'exit' request replaces ours

    sess_launcher._sleep = sleep
    sess_launcher.launch("nes", "/roms/nes/x.nes")
    assert session.take_request(str(tmp_path)) == {"action": "exit"} and not sess_launcher.game_running()


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


# ------------------------------------------------------------------ direct fallback: same patience with ES
def test_direct_fallback_is_patient_with_emulationstation_too(cfg, procs, tmp_path):
    clock = Clock()

    def sleep(seconds):
        clock.now += seconds
        if clock.now > 100 + 7:  # ES finishes loading and obeys the stop after 7 s
            procs.running.discard(ES_PATTERN)

    procs.pkill = lambda sig, pattern, full=False: procs.calls.append(("pkill", sig, pattern, full))
    launcher = Launcher(cfg, RecordingRetroArch(), procs=procs, popen=FakePopen, sleep=sleep,
                        runtime_dir=str(tmp_path), clock=clock)
    procs.running.add(ES_PATTERN)
    launcher.launch("nes", "/roms/nes/x.nes")
    assert kills(procs, ES_PATTERN, "KILL") == [] and kills(procs, ES_PATTERN, "TERM")
    assert FakePopen.instances  # and the game then starts


def test_direct_fallback_gives_up_on_a_stuck_emulationstation_after_killing_it(cfg, procs, tmp_path):
    clock = Clock()
    procs.pkill = lambda sig, pattern, full=False: procs.calls.append(("pkill", sig, pattern, full))
    launcher = Launcher(cfg, RecordingRetroArch(), procs=procs, popen=FakePopen,
                        sleep=lambda s: setattr(clock, "now", clock.now + s), runtime_dir=str(tmp_path), clock=clock)
    procs.running.add(ES_PATTERN)
    launcher.launch("nes", "/roms/nes/x.nes")
    assert kills(procs, ES_PATTERN, "KILL") and FakePopen.instances
