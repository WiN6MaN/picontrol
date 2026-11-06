import os

from fakes import Card
from picontrol import doctor, hwtest
from picontrol.pn532 import PN532


def test_led_and_fan_tests_drive_the_configured_pins(cfg, gpio, monkeypatch):
    monkeypatch.setattr(hwtest.time, "sleep", lambda s: None)
    lines = []
    assert hwtest.test_led(cfg, gpio, out=lines.append) == 0
    assert [v for p, v in gpio.writes if p == cfg.pins.led].count(1) >= 5
    gpio.writes.clear()
    assert hwtest.test_fan(cfg, gpio, out=lines.append, seconds=0) == 0
    assert [v for p, v in gpio.writes if p == cfg.pins.fan] == [0, 1, 0]


def test_buttons_test_reports_changes(cfg, gpio):
    lines = []
    gpio.levels[cfg.pins.power] = 0
    gpio.levels[cfg.pins.reset] = 1
    hwtest.test_buttons(cfg, gpio, out=lines.append, seconds=0.2)
    assert any("power switch: ON" in line for line in lines)


def test_nfc_test(cfg, gpio, sim, monkeypatch):
    import functools
    monkeypatch.setattr("picontrol.nfc.PN532", functools.partial(PN532, wake_delay=0, sleep=lambda s: None))
    lines = []
    sim.place(Card([1, 2, 3, 4]))
    assert hwtest.test_nfc(cfg, gpio, out=lines.append, seconds=1) == 0
    assert any("01020304" in line for line in lines)
    sim.remove()
    assert hwtest.test_nfc(cfg, gpio, out=lines.append, seconds=0.2) == 1
    sim.fail_next = 99
    assert hwtest.test_nfc(cfg, gpio, out=lines.append, seconds=0.2) == 1
    assert any("PN532 not found" in line for line in lines)


def by_title(checks):
    return {title: status for status, title, _ in checks}


def test_doctor_on_a_complete_installation(cfg, tmp_path):
    runcommand = tmp_path / "runcommand.sh"
    runcommand.write_text("#!/bin/sh\n")
    runcommand.chmod(0o755)
    cfg.paths.runcommand = str(runcommand)
    with open(cfg.paths.retroarch_cfg, "w") as handle:
        handle.write('network_cmd_enable = "true"\n')
    autostart = tmp_path / "autostart.sh"
    autostart.write_text("# >>> picontrol (managed block) >>>\nx\n# <<< picontrol <<<\nemulationstation\n")
    cfg.fan.temp_path = str(tmp_path / "temp")
    (tmp_path / "temp").write_text("40000")
    status = by_title(doctor.run_checks(cfg, "x.conf", autostart=str(autostart)))
    assert status["ROM folder"] == doctor.OK
    assert status["runcommand.sh"] == doctor.OK
    assert status["RetroArch network commands"] == doctor.OK
    assert status["Started from autostart.sh"] == doctor.OK
    assert status["CPU temperature sensor"] == doctor.OK


def test_doctor_flags_problems(cfg, tmp_path):
    cfg.paths.roms_dir = str(tmp_path / "nowhere")
    cfg.paths.runcommand = str(tmp_path / "nothing.sh")
    status = by_title(doctor.run_checks(cfg, None, autostart=str(tmp_path / "missing")))
    assert status["ROM folder"] == doctor.FAIL
    assert status["runcommand.sh"] == doctor.FAIL
    assert status["RetroArch network commands"] == doctor.WARN
    assert status["Started from autostart.sh"] == doctor.WARN


def test_doctor_web_checks(cfg, tmp_path):
    cfg.web.enabled = True
    cfg.web.password_file = str(tmp_path / "web.passwd")
    cfg.web.cert_file, cfg.web.key_file = str(tmp_path / "c.crt"), str(tmp_path / "c.key")
    status = by_title(doctor.run_checks(cfg, None, autostart=str(tmp_path / "x")))
    assert status["Web interface password"] == doctor.FAIL  # enabled without a password
    (tmp_path / "web.passwd").write_text("pbkdf2_sha256$1$a$b\n")
    cfg.web.tls = False
    cfg.web.allow_public = True
    status = by_title(doctor.run_checks(cfg, None, autostart=str(tmp_path / "x")))
    assert status["Web interface password"] == doctor.OK
    assert status["Web interface without HTTPS"] == doctor.WARN
    assert status["Web interface open to any address"] == doctor.WARN


def test_doctor_is_silent_about_the_web_interface_when_it_is_off(cfg, tmp_path):
    assert not [t for t in by_title(doctor.run_checks(cfg, None, autostart=str(tmp_path / "x"))) if "Web" in t]
