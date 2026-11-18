"""Real processes on a real (pseudo) terminal: a game started from a tag must keep the console.

This reproduces the bug of the original Pi Control: when a service kills EmulationStation and starts the game
itself, ``autostart.sh`` ends, the login shell takes the terminal back and the game (then EmulationStation
again) runs in the *background* of the terminal, so the RetroPie menus get the wrong input. Here the whole
chain is real: install.sh writes the autostart block, an interactive shell (the "login shell on tty1") runs
it, and a fake EmulationStation / runcommand stand in for RetroPie. The assertion that matters: every process
that runs after a tag launch is in the terminal's foreground process group.
"""

import os
import pty
import signal
import sys
import time

import pytest

from picontrol import session
from test_install import box, sh  # noqa: F401  (the sandboxed installer and its fixture)

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs Linux pseudo-terminals")

# Each fake program appends "<label> <pid> <arguments>" to the event log, then stays alive like the real one.
FAKE_PROGRAM = '#!/bin/bash\necho "%s $$ $*" >> "%s"\nexec sleep 600\n'


class Console:
    """A pseudo-terminal running an interactive shell, like tty1 after login."""

    def __init__(self, env):
        self.pid, self.master = pty.fork()
        if self.pid == 0:  # the child: the login shell
            os.execvpe("bash", ["bash", "--norc", "-i"], env)
        os.set_blocking(self.master, False)

    def type(self, line):
        os.write(self.master, (line + "\n").encode())

    def drain(self):
        try:
            while os.read(self.master, 4096):
                pass
        except OSError:  # nothing to read right now (or the shell has gone)
            pass

    def foreground(self):
        return os.tcgetpgrp(self.master)

    def close(self, pids=()):
        groups = set()
        try:
            groups.add(self.foreground())
        except OSError:
            pass
        for pid in pids:
            try:
                groups.add(os.getpgid(pid))
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        for group in groups | {self.pid}:
            try:
                os.killpg(group, signal.SIGKILL)
            except OSError:
                pass
        try:
            os.close(self.master)
            os.waitpid(self.pid, 0)
        except OSError:
            pass


def events(path):
    """[(label, pid, arguments)] from the event log."""
    try:
        with open(path) as handle:
            rows = [line.split(None, 2) for line in handle.read().splitlines() if line.strip()]
    except OSError:
        return []
    return [(row[0], int(row[1]), row[2] if len(row) > 2 else "") for row in rows]


def wait_for(console, predicate, what, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        console.drain()
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out waiting for " + what)


@pytest.fixture
def setup(box):  # noqa: F811
    tmp, configs, env = box
    assert sh("install.sh", env).returncode == 0
    fakes, run, log = tmp / "fakes", tmp / "run", tmp / "events.log"
    fakes.mkdir()
    run.mkdir()
    roms = tmp / "roms" / "nes"
    roms.mkdir(parents=True)
    (roms / "Zelda II.nes").write_text("x")
    for name, label in (("emulationstation", "es"), ("runcommand.sh", "game")):
        (fakes / name).write_text(FAKE_PROGRAM % (label, log))
        (fakes / name).chmod(0o755)
    (tmp / "etc" / "picontrol.conf").write_text(
        "[paths]\nroms_dir = %s\nruncommand = %s\nemulationstation_command = %s --no-splash\n[logging]\nfile = %s\n"
        % (tmp / "roms", fakes / "runcommand.sh", fakes / "emulationstation", tmp / "picontrol.log"))
    # the real autostart.sh written by the installer, minus the background service (it needs the GPIO hardware)
    text = [line for line in (configs / "autostart.sh").read_text().splitlines() if "picontrol run" not in line]
    (tmp / "autostart.sh").write_text("\n".join(text) + "\n")
    env = dict(env, PATH="%s:%s" % (fakes, os.environ["PATH"]), PICONTROL_RUNTIME_DIR=str(run), HOME=str(tmp))
    console = Console(env)
    info = {"autostart": str(tmp / "autostart.sh"), "log": str(log), "run": str(run),
            "rom": os.path.realpath(str(roms / "Zelda II.nes"))}
    yield console, info
    console.close([pid for _, pid, _ in events(info["log"])])


def test_a_game_started_from_a_tag_keeps_the_console(setup):
    console, info = setup
    log, run = info["log"], info["run"]
    console.type("bash %s" % info["autostart"])

    # 1. EmulationStation starts under the session, exactly like the original autostart line ('#auto' is a comment)
    label, es_pid, args = wait_for(console, lambda: events(log), "EmulationStation")[0]
    assert (label, args) == ("es", "")
    wait_for(console, lambda: session.session_running(run), "the console session")
    assert os.getpgid(es_pid) == console.foreground()

    # 2. the service's part: leave a request, stop EmulationStation
    session.request_launch("nes", "Zelda II.nes", run)
    os.kill(es_pid, signal.SIGTERM)
    label, game_pid, args = wait_for(console, lambda: [e for e in events(log) if e[0] == "game"], "the game")[0]
    assert args == "0 _SYS_ nes %s" % info["rom"]
    # THE regression check: the game is in the foreground process group of the terminal
    assert os.getpgid(game_pid) == console.foreground(), "the game runs behind the login shell"

    # 3. the game ends: EmulationStation comes back (fast start), again in the foreground, same session
    os.kill(game_pid, signal.SIGTERM)
    _, second_pid, args = wait_for(console, lambda: [e for e in events(log) if e[0] == "es"][1:], "EmulationStation again")[0]
    assert args == "--no-splash"
    assert os.getpgid(second_pid) == console.foreground(), "EmulationStation runs behind the login shell"
    assert session.session_running(run)

    # 4. if EmulationStation crashes, plain EmulationStation is started with the original arguments
    os.kill(second_pid, signal.SIGKILL)
    _, third_pid, args = wait_for(console, lambda: [e for e in events(log) if e[0] == "es"][2:], "the fallback start")[0]
    assert args == "" and os.getpgid(third_pid) == console.foreground()


def test_the_old_method_loses_the_console(setup):
    """Control experiment: what the original did (a background service kills ES and starts the game) is detected."""
    console, info = setup
    log, fakes = info["log"], os.path.join(os.path.dirname(info["log"]), "fakes")
    old = info["autostart"] + ".old"
    with open(old, "w") as handle:
        handle.write(
            "#!/bin/bash\n"
            "( while [ ! -s '%(log)s' ]; do sleep 0.1; done; sleep 0.5\n"
            "  kill $(awk '/^es /{print $2; exit}' '%(log)s')\n"
            "  '%(fakes)s/runcommand.sh' 0 _SYS_ nes x >/dev/null 2>&1 & wait ) &\n"
            "'%(fakes)s/emulationstation'\n" % {"log": log, "fakes": fakes})
    console.type("bash %s" % old)
    _, game_pid, _ = wait_for(console, lambda: [e for e in events(log) if e[0] == "game"], "the game")[0]
    time.sleep(0.5)
    console.drain()
    assert os.getpgid(game_pid) != console.foreground(), "the control experiment no longer detects the bug"
