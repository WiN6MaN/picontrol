"""Runs the real install.sh / uninstall.sh inside a sandbox (every path overridden, no root needed)."""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTOSTART_ORIGINAL = "#!/bin/bash\n# RetroPie autostart\nemulationstation #auto\n"
RETROARCH_ORIGINAL = '# comment\nvideo_driver = "gl"\n# network_cmd_enable = false\nnetwork_cmd_port = "1234"\n'


@pytest.fixture
def box(tmp_path):
    configs = tmp_path / "retropie"
    configs.mkdir()
    (configs / "autostart.sh").write_text(AUTOSTART_ORIGINAL)
    (configs / "retroarch.cfg").write_text(RETROARCH_ORIGINAL)
    env = dict(os.environ,
               PICONTROL_SANDBOX="1", PICONTROL_USER="nobody-such-user",
               PICONTROL_PREFIX=str(tmp_path / "opt"), PICONTROL_ETC=str(tmp_path / "etc"),
               PICONTROL_BIN=str(tmp_path / "bin"), PICONTROL_LOGFILE=str(tmp_path / "picontrol.log"),
               PICONTROL_AUTOSTART=str(configs / "autostart.sh"),
               PICONTROL_RETROARCH_CFG=str(configs / "retroarch.cfg"))
    return tmp_path, configs, env


def sh(script, env, *args):
    extra = ["--skip-deps"] if script == "install.sh" else []  # never apt-get inside the tests
    return subprocess.run(["bash", os.path.join(ROOT, script)] + extra + list(args), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


def test_install_creates_everything(box):
    tmp, configs, env = box
    result = sh("install.sh", env)
    assert result.returncode == 0, result.stderr
    assert (tmp / "opt" / "lib" / "picontrol" / "cli.py").exists()
    assert not list((tmp / "opt").rglob("__pycache__"))
    assert (tmp / "etc" / "picontrol.conf").exists() and (tmp / "etc" / "picontrol.conf.dist").exists()
    assert (tmp / "picontrol.log").exists()
    launcher = tmp / "bin" / "picontrol"
    assert os.access(str(launcher), os.X_OK)

    autostart = (configs / "autostart.sh").read_text().splitlines()
    begin = autostart.index("# >>> picontrol (managed block) >>>")
    assert autostart.index("# <<< picontrol <<<") > begin
    assert begin < autostart.index("emulationstation #auto")  # before the (blocking) emulationstation line
    assert "(while true; do %s/picontrol run; sleep 3; done) &" % (tmp / "bin") in autostart
    assert (configs / "autostart.sh.picontrol-bak").read_text() == AUTOSTART_ORIGINAL

    ra = (configs / "retroarch.cfg").read_text().splitlines()
    assert ra.count('network_cmd_enable = "true"') == 1 and ra.count('network_cmd_port = "55355"') == 1
    assert 'video_driver = "gl"' in ra and "# network_cmd_enable = false" not in ra
    assert (configs / "retroarch.cfg.picontrol-bak").read_text() == RETROARCH_ORIGINAL


def test_the_installed_launcher_runs(box):
    tmp, _, env = box
    assert sh("install.sh", env).returncode == 0
    out = subprocess.run([str(tmp / "bin" / "picontrol"), "--version"], env=env, stdout=subprocess.PIPE,
                         universal_newlines=True)
    assert out.returncode == 0 and out.stdout.startswith("picontrol ")
    # the launcher picks up the sandboxed configuration
    (tmp / "etc" / "picontrol.conf").write_text("[nope]\n")
    bad = subprocess.run([str(tmp / "bin" / "picontrol"), "doctor"], env=env, stderr=subprocess.PIPE,
                         stdout=subprocess.PIPE, universal_newlines=True)
    assert bad.returncode == 2 and "unknown section" in bad.stderr


def test_install_is_idempotent_and_keeps_the_user_config(box):
    tmp, configs, env = box
    assert sh("install.sh", env).returncode == 0
    (tmp / "etc" / "picontrol.conf").write_text("[fan]\nthreshold_on = 70\n")
    first = ((configs / "autostart.sh").read_text(), (configs / "retroarch.cfg").read_text())
    result = sh("install.sh", env)
    assert result.returncode == 0
    assert ((configs / "autostart.sh").read_text(), (configs / "retroarch.cfg").read_text()) == first
    assert (tmp / "etc" / "picontrol.conf").read_text() == "[fan]\nthreshold_on = 70\n"  # untouched
    assert (configs / "autostart.sh").read_text().count("# >>> picontrol") == 1
    assert "Keeping your configuration" in result.stdout


def test_dry_run_changes_nothing(box):
    tmp, configs, env = box
    result = sh("install.sh", env, "--dry-run")
    assert result.returncode == 0 and "[dry-run]" in result.stdout
    assert not (tmp / "opt").exists() and not (tmp / "bin").exists() and not (tmp / "etc").exists()
    assert (configs / "autostart.sh").read_text() == AUTOSTART_ORIGINAL
    assert (configs / "retroarch.cfg").read_text() == RETROARCH_ORIGINAL


def test_install_options_can_skip_files(box):
    tmp, configs, env = box
    result = sh("install.sh", env, "--no-autostart", "--no-retroarch-config")
    assert result.returncode == 0
    assert (configs / "autostart.sh").read_text() == AUTOSTART_ORIGINAL
    assert (configs / "retroarch.cfg").read_text() == RETROARCH_ORIGINAL


def test_install_refuses_an_autostart_without_emulationstation(box):
    _, configs, env = box
    (configs / "autostart.sh").write_text("#!/bin/bash\necho hi\n")
    result = sh("install.sh", env)
    assert result.returncode != 0 and "emulationstation" in result.stderr


def test_unknown_option_is_rejected(box):
    _, _, env = box
    result = sh("install.sh", env, "--frobnicate")
    assert result.returncode != 0 and "unknown option" in result.stderr


def test_uninstall_removes_the_code_but_keeps_the_config(box):
    tmp, configs, env = box
    assert sh("install.sh", env).returncode == 0
    result = sh("uninstall.sh", env)
    assert result.returncode == 0, result.stderr
    assert (configs / "autostart.sh").read_text() == AUTOSTART_ORIGINAL  # block gone, nothing else changed
    assert not (tmp / "opt").exists() and not (tmp / "bin" / "picontrol").exists()
    assert (tmp / "etc" / "picontrol.conf").exists() and (tmp / "picontrol.log").exists()


def test_uninstall_purge(box):
    tmp, _, env = box
    assert sh("install.sh", env).returncode == 0
    assert sh("uninstall.sh", env, "--purge").returncode == 0
    assert not (tmp / "etc").exists() and not (tmp / "picontrol.log").exists()


def test_uninstall_dry_run(box):
    tmp, configs, env = box
    assert sh("install.sh", env).returncode == 0
    before = (configs / "autostart.sh").read_text()
    assert sh("uninstall.sh", env, "--dry-run").returncode == 0
    assert (configs / "autostart.sh").read_text() == before and (tmp / "opt").exists()
