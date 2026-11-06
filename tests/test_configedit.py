import os

import pytest

from picontrol import configedit
from picontrol.config import SPEC, WEB_EDITABLE, Config
from picontrol.errors import ConfigError

SAMPLE = "; my notes\n[fan]\n; hysteresis\nthreshold_on = 60.0   ; summer\nthreshold_off = 50.0\n\n[nfc]\nenabled = true\n"


def test_web_editable_keys_exist_and_are_simple_types():
    for section, key in WEB_EDITABLE:
        assert SPEC[section][key][0] in ("bool", "int", "float", "str")
    kinds = {SPEC[s][k][0] for s, k in WEB_EDITABLE if SPEC[s][k][0] == "str"}
    assert [(s, k) for s, k in WEB_EDITABLE if SPEC[s][k][0] == "str"] == [("power", "off_level")]


@pytest.mark.parametrize("name", ["power.shutdown_command", "paths.runcommand", "paths.emulationstation_command",
                                  "paths.roms_dir", "pins.power", "web.enabled", "web.allow_public",
                                  "web.password_file", "retroarch.port", "logging.file", "nfc.lock_file", "nope.x", "x"])
def test_dangerous_or_unknown_settings_are_refused(name):
    with pytest.raises(ConfigError, match="cannot be changed"):
        configedit.normalise({name: 1})


@pytest.mark.parametrize("changes", [{"fan.threshold_on": "hot"}, {"fan.enabled": 1}, {"nfc.max_read_attempts": 2.5},
                                     {"nfc.enabled": "yes"}, {"power.off_level": "a\nb"}, {"power.off_level": 5},
                                     {"fan.interval": True}, {}, None, ["fan.interval"]])
def test_wrong_types_are_refused(changes):
    with pytest.raises(ConfigError):
        configedit.normalise(changes)


def test_values_are_normalised():
    assert configedit.normalise({"fan.threshold_on": 65, "nfc.enabled": False, "nfc.max_read_attempts": 4,
                                 "power.off_level": "low"}) == {
        "fan": {"threshold_on": "65.0"}, "nfc": {"enabled": "false", "max_read_attempts": "4"},
        "power": {"off_level": "low"}}


def test_update_text_keeps_comments_and_layout():
    out = configedit.update_text(SAMPLE, configedit.normalise({"fan.threshold_on": 65}))
    assert out == SAMPLE.replace("threshold_on = 60.0   ; summer", "threshold_on = 65.0")


def test_update_text_adds_missing_keys_and_sections():
    out = configedit.update_text(SAMPLE, configedit.normalise({"nfc.quit_on_remove": True, "led.enabled": False}))
    lines = out.splitlines()
    assert lines.index("quit_on_remove = true") == lines.index("enabled = true") + 1  # right after the section's content
    assert lines[-2:] == ["[led]", "enabled = false"]
    assert out.endswith("\n") and "; my notes" in out and "; hysteresis" in out


def test_update_text_on_an_empty_file():
    out = configedit.update_text("", configedit.normalise({"fan.interval": 3}))
    assert "[fan]" in out and "interval = 3.0" in out


def test_apply_writes_a_backup_and_a_valid_file(tmp_path):
    path = tmp_path / "picontrol.conf"
    path.write_text(SAMPLE)
    configedit.apply(str(path), {"fan.threshold_on": 70, "fan.threshold_off": 55})
    assert Config.load(str(path)).fan.threshold_on == 70.0
    assert (tmp_path / "picontrol.conf.bak").read_text() == SAMPLE


def test_apply_refuses_a_result_that_is_not_a_valid_configuration(tmp_path):
    path = tmp_path / "picontrol.conf"
    path.write_text(SAMPLE)
    with pytest.raises(ConfigError, match="greater"):
        configedit.apply(str(path), {"fan.threshold_on": 40})  # would be below threshold_off
    assert path.read_text() == SAMPLE and not (tmp_path / "picontrol.conf.bak").exists()


def test_apply_creates_the_file_when_missing(tmp_path):
    path = tmp_path / "new.conf"
    configedit.apply(str(path), {"led.enabled": False})
    assert Config.load(str(path)).led.enabled is False


def test_editable_settings_listing():
    cfg = Config.defaults()
    items = {i["name"]: i for i in configedit.editable_settings(cfg)}
    assert len(items) == len(WEB_EDITABLE)
    assert items["fan.threshold_on"]["value"] == 60.0 and items["fan.threshold_on"]["type"] == "float"
    assert items["power.off_level"]["choices"] == ["high", "low"]
    assert "power.shutdown_command" not in items and "pins.power" not in items
