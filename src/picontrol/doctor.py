"""Installation self-check. / Auto-diagnostic de l'installation.

Each check returns (status, title, detail) with status OK / WARN / FAIL. ``picontrol doctor`` prints them
and exits 1 if anything FAILs. Nothing here touches the hardware.
"""

import os
import shutil
import subprocess
import sys

from . import retroarch, webauth

AUTOSTART = "/opt/retropie/configs/all/autostart.sh"
MARKER = "# >>> picontrol"
OK, WARN, FAIL = "OK", "WARN", "FAIL"


def _writable_dir_for(path):
    folder = os.path.dirname(path) or "."
    return os.path.isdir(folder) and os.access(folder, os.W_OK)


def run_checks(cfg, config_path=None, autostart=AUTOSTART):
    checks = []
    add = lambda status, title, detail="": checks.append((status, title, detail))  # noqa: E731

    ok = sys.version_info >= (3, 7)
    add(OK if ok else FAIL, "Python >= 3.7", sys.version.split()[0])
    try:
        import RPi.GPIO  # noqa: F401
        add(OK, "RPi.GPIO available")
    except ImportError:
        add(FAIL, "RPi.GPIO available", "install it: sudo apt install python3-rpi.gpio")
    add(OK, "Configuration valid", config_path or "built-in defaults")

    roms = cfg.paths.roms_dir
    add(OK if os.path.isdir(roms) else FAIL, "ROM folder", roms)
    rc = cfg.paths.runcommand
    add(OK if os.access(rc, os.X_OK) else FAIL, "runcommand.sh", rc)

    enabled = retroarch.read_option(cfg.paths.retroarch_cfg, "network_cmd_enable")
    port = retroarch.read_option(cfg.paths.retroarch_cfg, "network_cmd_port")
    if enabled == "true" and (port in (None, str(cfg.retroarch.port))):
        add(OK, "RetroArch network commands", "enabled, port %s" % (port or "55355 (default)"))
    else:
        add(WARN, "RetroArch network commands",
            "set network_cmd_enable = true (and network_cmd_port = %d) in %s; reset/quit need it"
            % (cfg.retroarch.port, cfg.paths.retroarch_cfg))

    if cfg.fan.enabled:
        readable = os.access(cfg.fan.temp_path, os.R_OK)
        add(OK if readable else WARN, "CPU temperature sensor", cfg.fan.temp_path)

    if cfg.power.shutdown_command and cfg.power.shutdown_command[0] == "sudo":
        try:
            allowed = subprocess.call(["sudo", "-n", "true"], stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL) == 0
        except OSError:
            allowed = False
        add(OK if allowed else WARN, "Passwordless sudo (for shutdown)", "" if allowed else
            "the power switch cannot shut the Pi down without it")

    for tool in ("pkill", "pgrep"):
        add(OK if shutil.which(tool) else FAIL, "%s available" % tool)
    log_file = cfg.logging.file
    writable = os.access(log_file, os.W_OK) if os.path.exists(log_file) else _writable_dir_for(log_file)
    add(OK if writable else WARN, "Log file writable", log_file)

    if cfg.web.enabled:
        has_password = webauth.load_password(cfg.web.password_file) is not None
        add(OK if has_password else FAIL, "Web interface password",
            cfg.web.password_file if has_password else "run: picontrol web set-password")
        if cfg.web.tls:
            have_cert = os.path.exists(cfg.web.cert_file) and os.path.exists(cfg.web.key_file)
            if have_cert:
                add(OK, "Web interface certificate", cfg.web.cert_file)
            else:
                add(OK if shutil.which("openssl") else FAIL, "Web interface certificate",
                    "will be created on first start" if shutil.which("openssl") else "openssl is needed to create it")
        else:
            add(WARN, "Web interface without HTTPS", "the password travels in clear text on your network (tls = false)")
        if cfg.web.allow_public:
            add(WARN, "Web interface open to any address",
                "allow_public = true: never port-forward this service to the internet")
    try:
        with open(autostart, encoding="utf-8") as handle:
            present = MARKER in handle.read()
        add(OK if present else WARN, "Started from autostart.sh",
            "" if present else "run install.sh, or add the block described in docs/en/installation.md")
    except OSError:
        add(WARN, "Started from autostart.sh", "%s not found" % autostart)
    return checks
