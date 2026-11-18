"""The console session: request files (unit tests) and the session loop (scripted fakes)."""

import collections
import json
import os

import pytest

from picontrol import roms, session
from picontrol.errors import LaunchError
from picontrol.session import Session


@pytest.fixture
def rt(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    return str(folder)


# ------------------------------------------------------------------ roms.py
@pytest.mark.parametrize("system, rom", [
    (None, "x.nes"), ("nes", None), (5, "x"), ("nes", 5), ("nes", ["x"]), ("nes; id", "x"), ("nes", "../x"),
])
def test_resolve_rom_rejects_values_that_are_not_names(cfg, system, rom):
    with pytest.raises(LaunchError):
        roms.resolve_rom(cfg.paths.roms_dir, system, rom)


# ------------------------------------------------------------------ request files
def test_request_round_trip(rt):
    assert not session.request_pending(rt)
    session.request_launch("nes", "Zelda II.nes", rt)
    assert session.request_pending(rt)
    path = session.request_path(rt)
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert session.take_request(rt) == {"action": "launch", "system": "nes", "rom": "Zelda II.nes"}
    assert not os.path.exists(path) and session.take_request(rt) is None


def test_exit_request(rt):
    session.request_exit(rt)
    assert session.take_request(rt) == {"action": "exit"}


def test_a_newer_request_replaces_the_older_one(rt):
    session.request_launch("nes", "a.nes", rt)
    session.request_launch("nes", "b.nes", rt)
    assert session.take_request(rt)["rom"] == "b.nes"


def test_no_temporary_file_is_left_behind(rt):
    session.request_launch("nes", "a.nes", rt)
    session.take_request(rt)
    assert os.listdir(rt) == []


def test_writing_never_follows_a_planted_symlink(rt, tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("precious")
    path = session.request_path(rt)
    os.symlink(str(victim), path)
    session.request_launch("nes", "a.nes", rt)  # replaces the link itself, not its target
    assert victim.read_text() == "precious" and not os.path.islink(path)
    assert session.take_request(rt)["rom"] == "a.nes"


def test_a_planted_temporary_file_makes_the_write_fail_safely(rt, tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("precious")
    os.symlink(str(victim), "%s.%d.tmp" % (session.request_path(rt), os.getpid()))
    with pytest.raises(LaunchError):
        session.request_launch("nes", "a.nes", rt)
    assert victim.read_text() == "precious"


def test_unwritable_folder_is_a_launch_error(tmp_path):
    with pytest.raises(LaunchError):
        session.request_launch("nes", "a.nes", str(tmp_path / "missing"))


def test_oversized_request_is_refused(rt):
    with pytest.raises(LaunchError):
        session.request_launch("nes", "x" * 5000, rt)


@pytest.mark.parametrize("content", [
    b"", b"not json", b"[]", b"null", b'{"action": "launch"}', b'{"action": "launch", "system": 1, "rom": "x"}',
    b'{"action": "launch", "system": "nes", "rom": ["x"]}', b'{"action": "format"}', b'{"system": "nes", "rom": "x"}',
    b"\xff\xfe\x00", b'{"action": "launch", "system": "nes"',
])
def test_malformed_requests_are_ignored_and_removed(rt, content):
    path = session.request_path(rt)
    with open(path, "wb") as handle:
        handle.write(content)
    assert session.take_request(rt) is None
    assert not os.path.exists(path)


def test_oversized_file_is_ignored_and_removed(rt):
    path = session.request_path(rt)
    with open(path, "wb") as handle:
        handle.write(b" " * 5000)
    assert session.take_request(rt) is None and not os.path.exists(path)


def test_stale_request_is_ignored(rt):
    session.request_launch("nes", "a.nes", rt)
    mtime = os.stat(session.request_path(rt)).st_mtime
    assert session.take_request(rt, now=mtime + session.MAX_REQUEST_AGE + 1) is None
    assert not session.request_pending(rt)


def test_a_symlink_is_never_read(rt, tmp_path):
    target = tmp_path / "t"
    target.write_text(json.dumps({"action": "exit"}))
    os.symlink(str(target), session.request_path(rt))
    assert not session.request_pending(rt) and session.take_request(rt) is None
    assert target.exists()


def test_a_directory_or_fifo_is_never_read(rt):
    os.mkdir(session.request_path(rt))
    assert not session.request_pending(rt) and session.take_request(rt) is None
    os.rmdir(session.request_path(rt))
    os.mkfifo(session.request_path(rt))
    assert not session.request_pending(rt) and session.take_request(rt) is None  # does not block


def test_a_file_of_someone_else_is_ignored_and_left_alone(rt, monkeypatch):
    session.request_launch("nes", "a.nes", rt)
    monkeypatch.setattr(session, "_ours", lambda st: False)
    assert not session.request_pending(rt) and session.take_request(rt) is None
    assert os.path.exists(session.request_path(rt))


def test_ours_checks_type_and_owner():
    Stat = collections.namedtuple("Stat", "st_mode st_uid")
    assert session._ours(Stat(0o100600, os.geteuid()))
    assert not session._ours(Stat(0o100600, os.geteuid() + 1))
    assert not session._ours(Stat(0o040700, os.geteuid()))


def test_clear_request(rt):
    session.request_launch("nes", "a.nes", rt)
    session.clear_request(rt)
    session.clear_request(rt)  # nothing left: no error
    assert not session.request_pending(rt)


def test_runtime_dir_can_come_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PICONTROL_RUNTIME_DIR", str(tmp_path))
    assert os.path.dirname(session.request_path()) == str(tmp_path)
    assert os.path.dirname(session.pid_path()) == str(tmp_path)
    monkeypatch.delenv("PICONTROL_RUNTIME_DIR")
    assert os.path.dirname(session.request_path()) == session.RUNTIME_DIR


# ------------------------------------------------------------------ is a session alive?
@pytest.fixture
def fake_proc(tmp_path):
    root = tmp_path / "proc"
    root.mkdir()

    def add(pid, *words):
        (root / str(pid)).mkdir(exist_ok=True)
        (root / str(pid) / "cmdline").write_bytes(b"\0".join(w.encode() for w in words) + b"\0")

    return str(root), add


def test_session_running(rt, fake_proc):
    root, add = fake_proc
    assert not session.session_running(rt, root)  # no pid file
    with open(session.pid_path(rt), "w") as handle:
        handle.write("4242\n")
    assert not session.session_running(rt, root)  # process gone
    add(4242, "python3", "-m", "picontrol", "session", "--", "--no-splash")
    assert session.session_running(rt, root)
    add(4242, "python3", "-m", "picontrol", "run")  # the pid was reused by something else
    assert not session.session_running(rt, root)
    add(4242, "vim", "notes.txt")
    assert not session.session_running(rt, root)


def test_session_running_with_a_garbage_pid_file(rt, fake_proc):
    root, _ = fake_proc
    with open(session.pid_path(rt), "w") as handle:
        handle.write("not a number")
    assert not session.session_running(rt, root)


# ------------------------------------------------------------------ the loop
class Script:
    """Stands in for subprocess.call: records commands, runs scripted side effects, returns scripted codes."""

    def __init__(self, rt, *steps):
        self.rt, self.steps, self.commands, self.pid_seen = rt, list(steps), [], []

    def __call__(self, argv):
        self.commands.append(list(argv))
        self.pid_seen.append(os.path.exists(session.pid_path(self.rt)))
        action, code = self.steps.pop(0) if self.steps else (None, 0)
        if isinstance(code, Exception):
            raise code
        if action:
            action()
        return code


@pytest.fixture
def make(cfg, rt):
    def build(*steps):
        script = Script(rt, *steps)
        return Session(cfg, call=script, runtime_dir=rt), script

    return build


def rom(cfg, system="nes", name="Zelda II.nes"):
    return os.path.join(os.path.realpath(cfg.paths.roms_dir), system, name)


def test_plain_start_uses_the_arguments_of_the_autostart_line(make, rt):
    sess, script = make((None, 0))
    assert sess.run(["--no-splash", "--debug"]) == 0
    assert script.commands == [["emulationstation", "--no-splash", "--debug"]]
    assert script.pid_seen == [True] and not os.path.exists(session.pid_path(rt))  # registered, then removed


def test_a_clean_exit_status_is_passed_on(make):
    sess, _ = make((None, 3))
    assert sess.run() == 3


def test_a_tag_game_is_played_in_the_session_then_emulationstation_returns(make, cfg, rt):
    sess, script = make((lambda: session.request_launch("nes", "Zelda II.nes", rt), -15), (None, 0), (None, 7))
    assert sess.run() == 7
    assert script.commands == [
        ["emulationstation"],
        [cfg.paths.runcommand, "0", "_SYS_", "nes", rom(cfg)],
        list(cfg.paths.emulationstation_command),  # the fast restart (--no-splash) after a game
    ]


def test_a_request_waiting_at_start_is_played_first(make, cfg, rt):
    session.request_launch("nes", "Zelda II.nes", rt)
    sess, script = make((None, 0), (None, 0))
    sess.run(["--x"])
    assert script.commands[0][-2:] == ["nes", rom(cfg)]
    assert script.commands[1] == list(cfg.paths.emulationstation_command)


def test_two_requests_in_a_row(make, cfg, rt):
    sess, script = make((lambda: session.request_launch("nes", "Zelda II.nes", rt), 0),
                        (lambda: session.request_launch("arcade", "Quake Arena.zip", rt), 0),
                        (None, 0), (None, 0))
    sess.run()
    assert [c[-2] for c in script.commands[1:3]] == ["nes", "arcade"] and len(script.commands) == 4


def test_a_refused_request_never_runs_and_emulationstation_still_starts(make, cfg, rt):
    hostile = [("nes; reboot", "x.nes"), ("nes", "../arcade/Quake Arena.zip"), ("nes", "missing.nes"), ("..", "x")]
    for system, name in hostile:
        sess, script = make((lambda s=system, n=name: session.request_launch(s, n, rt), 0), (None, 5))
        assert sess.run() == 5
        assert all(cfg.paths.runcommand not in command for command in script.commands), (system, name)


def test_exit_request_ends_the_session_without_starting_emulationstation(make, rt):
    session.request_exit(rt)
    sess, script = make()
    assert sess.run() == 0 and script.commands == []
    sess, script = make((lambda: session.request_launch("nes", "Zelda II.nes", rt), 0), (lambda: session.request_exit(rt), 0))
    assert sess.run() == 0 and len(script.commands) == 2  # ES, then the game; no second ES


def test_a_crash_inside_the_session_falls_back_to_plain_emulationstation(cfg, rt, monkeypatch):
    calls = []

    def call(argv):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(session, "take_request", lambda *a, **k: 1 / 0)
    assert Session(cfg, call=call, runtime_dir=rt).run(["--x"]) == 0
    assert calls == [["emulationstation", "--x"]] and not os.path.exists(session.pid_path(rt))


def test_missing_program_is_reported_not_raised(make):
    sess, script = make((None, OSError("not found")))
    assert sess.run() == 127


def test_an_unwritable_pid_folder_does_not_stop_the_console(cfg, tmp_path):
    calls = []
    sess = Session(cfg, call=lambda argv: calls.append(argv) or 0, runtime_dir=str(tmp_path / "missing"))
    assert sess.run() == 0 and calls


def test_stale_pid_file_is_replaced(make, rt):
    with open(session.pid_path(rt), "w") as handle:
        handle.write("1\n")
    sess, script = make((None, 0))
    sess.run()
    assert script.pid_seen == [True]
