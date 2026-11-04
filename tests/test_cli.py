import functools

import pytest

from fakes import Card
from picontrol import cli, tagstore
from picontrol.pn532 import PN532


@pytest.fixture
def conf(tmp_path, cfg):
    path = tmp_path / "picontrol.conf"
    path.write_text("[paths]\nroms_dir = %s\nruncommand_info = %s\n[nfc]\nlock_file = %s\n[logging]\nfile = %s\n"
                    % (cfg.paths.roms_dir, cfg.paths.runcommand_info, cfg.nfc.lock_file, cfg.logging.file))
    return str(path)


@pytest.fixture
def fast_reader(monkeypatch, gpio):
    monkeypatch.setattr("picontrol.nfc.PN532", functools.partial(PN532, wake_delay=0, sleep=lambda s: None))
    monkeypatch.setattr(cli, "_gpio", lambda: gpio)


def test_version(capsys):
    with pytest.raises(SystemExit) as info:
        cli.main(["--version"])
    assert info.value.code == 0 and "picontrol" in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert cli.main([]) == 0
    assert "COMMAND" in capsys.readouterr().out


def test_invalid_config_exits_with_2(tmp_path, capsys):
    bad = tmp_path / "bad.conf"
    bad.write_text("[nope]\n")
    assert cli.main(["-c", str(bad), "doctor"]) == 2
    assert "unknown section" in capsys.readouterr().err


def test_doctor_reports_and_sets_exit_code(conf, capsys):
    code = cli.main(["-c", conf, "doctor"])
    out = capsys.readouterr().out
    assert "ROM folder" in out and "RetroArch network commands" in out
    assert code in (0, 1)


def test_tag_write_needs_arguments(conf, capsys):
    assert cli.main(["-c", conf, "tag", "write"]) == 2


def test_tag_write_refuses_an_unknown_rom_without_force(conf, capsys):
    assert cli.main(["-c", conf, "tag", "write", "nes", "missing.nes"]) == 2
    assert "Refused" in capsys.readouterr().out


def test_tag_write_then_read(conf, sim, fast_reader, capsys, reader):
    sim.place(Card([4, 3, 2, 1]))
    assert cli.main(["-c", conf, "tag", "write", "nes", "Zelda II.nes"]) == 0
    assert "Written and verified" in capsys.readouterr().out
    sim.card_state = "idle"
    assert cli.main(["-c", conf, "tag", "read"]) == 0
    out = capsys.readouterr().out
    assert "04030201" in out and "Zelda II.nes" in out


def test_tag_read_without_a_tag(conf, sim, fast_reader, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_wait_for_tag", lambda reader, timeout=0: None)
    assert cli.main(["-c", conf, "tag", "read"]) == 1


def test_tag_read_of_a_foreign_tag(conf, sim, fast_reader, capsys):
    sim.place(Card([8, 8, 8, 8]))
    assert cli.main(["-c", conf, "tag", "read"]) == 0
    assert "no Pi Control data" in capsys.readouterr().out
