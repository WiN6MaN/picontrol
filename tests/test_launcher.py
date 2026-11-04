import os
import subprocess

import pytest

from fakes import FakePopen, FakeProcs
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
def launcher(cfg, procs):
    return Launcher(cfg, RecordingRetroArch(), procs=procs, popen=FakePopen, sleep=lambda s: None)


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


def test_dry_run_does_nothing(cfg, procs):
    launcher = Launcher(cfg, RecordingRetroArch(), procs=procs, popen=FakePopen, dry_run=True)
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
