import pytest

from picontrol.config import Config
from picontrol.errors import ConfigError


def write(tmp_path, text):
    path = tmp_path / "picontrol.conf"
    path.write_text(text)
    return str(path)


def test_defaults_are_valid():
    cfg = Config.defaults()
    cfg.validate()
    assert (cfg.pins.power, cfg.pins.reset, cfg.pins.led, cfg.pins.fan) == (3, 23, 14, 18)
    assert (cfg.pins.nfc_sclk, cfg.pins.nfc_miso, cfg.pins.nfc_mosi, cfg.pins.nfc_cs) == (4, 17, 27, 22)
    assert cfg.power_off_level == 1


def test_command_defaults_are_argument_lists_not_strings():
    # regression: a default such as "sudo -n shutdown -h now" must be split into words
    cfg = Config.defaults()
    assert cfg.power.shutdown_command == ["sudo", "-n", "shutdown", "-h", "now"]
    assert cfg.paths.emulationstation_command == ["emulationstation", "--no-splash"]


def test_load_overrides_and_types(tmp_path):
    cfg = Config.load(write(tmp_path, "[fan]\nthreshold_on = 65\nthreshold_off = 55 ; hysteresis\n"
                                      "[nfc]\nquit_on_remove = yes\n[power]\nshutdown_command = sudo -n poweroff\n"
                                      "[paths]\nextra_emulators = foo, bar\n"))
    assert cfg.fan.threshold_on == 65.0 and cfg.fan.threshold_off == 55.0
    assert cfg.nfc.quit_on_remove is True
    assert cfg.power.shutdown_command == ["sudo", "-n", "poweroff"]
    assert cfg.paths.extra_emulators == ("foo", "bar")
    assert cfg.pins.power == 3  # untouched keys keep their defaults


def test_empty_file_is_valid(tmp_path):
    Config.load(write(tmp_path, ""))


@pytest.mark.parametrize("text, fragment", [
    ("[nope]\nx = 1\n", "unknown section"),
    ("[pins]\nbutton = 3\n", "unknown key"),
    ("[pins]\nfan = 23\n", "duplicate"),
    ("[pins]\nfan = 40\n", "valid BCM pin"),
    ("[fan]\nthreshold_on = 40\nthreshold_off = 50\n", "greater"),
    ("[power]\noff_level = middle\n", "off_level"),
    ("[fan]\ninterval = 0\n", "> 0"),
    ("[nfc]\nmax_read_attempts = 0\n", "max_read_attempts"),
    ("[logging]\nlevel = LOUD\n", "level"),
    ("[pins]\nfan = abc\n", "invalid literal"),
])
def test_invalid_configs_are_rejected(tmp_path, text, fragment):
    with pytest.raises(ConfigError) as info:
        Config.load(write(tmp_path, text))
    assert fragment in str(info.value)


def test_missing_explicit_file_is_an_error(tmp_path):
    with pytest.raises(ConfigError):
        Config.load(str(tmp_path / "absent.conf"))


def test_missing_default_file_falls_back_to_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("PICONTROL_CONFIG", raising=False)
    monkeypatch.setattr("picontrol.config.DEFAULT_CONFIG_PATH", str(tmp_path / "none.conf"))
    assert Config.load().pins.power == 3


def test_environment_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("PICONTROL_CONFIG", write(tmp_path, "[pins]\nled = 15\n"))
    assert Config.load().pins.led == 15


def test_shipped_example_config_is_valid():
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "config", "picontrol.conf")
    if os.path.exists(path):
        Config.load(path)


def test_shipped_example_config_matches_the_defaults_exactly():
    # keeps config/picontrol.conf and the code in sync: the example must list every key with its default
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "config", "picontrol.conf")
    loaded, defaults = Config.load(path), Config.defaults()
    from picontrol.config import SPEC
    for section in SPEC:
        assert vars(getattr(loaded, section)) == vars(getattr(defaults, section)), section


def test_version_is_consistent_with_pyproject():
    import os
    import re
    import picontrol
    text = open(os.path.join(os.path.dirname(__file__), "..", "pyproject.toml"), encoding="utf-8").read()
    assert re.search(r'^version = "%s"$' % re.escape(picontrol.__version__), text, re.M)
