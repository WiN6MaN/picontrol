"""Configuration loading and validation. / Chargement et validation de la configuration.

The file is a plain INI file (see ``config/picontrol.conf``). Every key has a default, so an
empty file is valid. Unknown sections or keys are rejected to catch typos early.
Le fichier est un INI simple ; chaque clé a une valeur par défaut. Les clés inconnues sont refusées.
"""

import configparser
import ipaddress
import logging
import os
import shlex
from types import SimpleNamespace

from .errors import ConfigError

DEFAULT_CONFIG_PATH = "/etc/picontrol/picontrol.conf"

# section -> key -> (type, default).  Types: int, float, bool, str, cmd (shell-like words), list (comma separated)
SPEC = {
    "pins": {  # BCM numbering / numérotation BCM
        "power": ("int", 3),
        "reset": ("int", 23),
        "led": ("int", 14),
        "fan": ("int", 18),
        "nfc_sclk": ("int", 4),
        "nfc_miso": ("int", 17),
        "nfc_mosi": ("int", 27),
        "nfc_cs": ("int", 22),
    },
    "power": {
        "enabled": ("bool", True),
        "off_level": ("str", "high"),
        "debounce": ("float", 0.3),
        "poll_interval": ("float", 0.05),
        "quit_grace": ("float", 1.5),
        "shutdown_command": ("cmd", "sudo -n shutdown -h now"),
    },
    "reset": {
        "enabled": ("bool", True),
        "debounce": ("float", 0.05),
        "long_press": ("float", 2.0),
    },
    "fan": {
        "enabled": ("bool", True),
        "threshold_on": ("float", 60.0),
        "threshold_off": ("float", 50.0),
        "interval": ("float", 5.0),
        "min_run": ("float", 20.0),
        "temp_path": ("str", "/sys/class/thermal/thermal_zone0/temp"),
    },
    "led": {"enabled": ("bool", True)},
    "nfc": {
        "enabled": ("bool", True),
        "poll_interval": ("float", 0.5),
        "poll_interval_game": ("float", 1.0),
        "remove_delay": ("float", 2.0),
        "min_relaunch_interval": ("float", 3.0),
        "max_read_attempts": ("int", 3),
        "launch_at_start": ("bool", True),
        "quit_on_remove": ("bool", False),
        "rf_reset_each_poll": ("bool", True),
        "write_timeout": ("float", 15.0),
        "lock_file": ("str", "/tmp/picontrol_nfc.lock"),
    },
    "paths": {
        "roms_dir": ("str", "/home/pi/RetroPie/roms"),
        "runcommand": ("str", "/opt/retropie/supplementary/runcommand/runcommand.sh"),
        "runcommand_info": ("str", "/dev/shm/runcommand.info"),
        "retroarch_cfg": ("str", "/opt/retropie/configs/all/retroarch.cfg"),
        "emulationstation_command": ("cmd", "emulationstation --no-splash"),
        "extra_emulators": ("list", ()),
    },
    "retroarch": {"host": ("str", "127.0.0.1"), "port": ("int", 55355)},
    "logging": {"file": ("str", "/var/log/picontrol.log"), "level": ("str", "INFO")},
    "web": {
        "enabled": ("bool", False),
        "host": ("str", "0.0.0.0"),
        "port": ("int", 8443),
        "tls": ("bool", True),
        "cert_file": ("str", "/etc/picontrol/web.crt"),
        "key_file": ("str", "/etc/picontrol/web.key"),
        "password_file": ("str", "/etc/picontrol/web.passwd"),
        "session_timeout": ("float", 3600.0),
        "max_login_failures": ("int", 5),
        "lockout": ("float", 300.0),
        "allow_public": ("bool", False),
        "allowed_networks": ("list", ()),
        "allowed_hosts": ("list", ()),
    },
}

# Settings the web interface may change. Deliberately limited to numbers, switches and one choice:
# commands, paths, pins and web settings are NOT editable from the browser, so a stolen web session can
# never make the service run an arbitrary command or lock you out.
# Réglages modifiables depuis le web : seulement nombres, interrupteurs et un choix (jamais commandes,
# chemins, broches ni réglages web).
WEB_EDITABLE = frozenset([
    ("power", "enabled"), ("power", "off_level"), ("power", "debounce"), ("power", "quit_grace"),
    ("reset", "enabled"), ("reset", "long_press"),
    ("fan", "enabled"), ("fan", "threshold_on"), ("fan", "threshold_off"), ("fan", "interval"),
    ("fan", "min_run"),
    ("led", "enabled"),
    ("nfc", "enabled"), ("nfc", "poll_interval"), ("nfc", "poll_interval_game"), ("nfc", "remove_delay"),
    ("nfc", "min_relaunch_interval"), ("nfc", "max_read_attempts"), ("nfc", "launch_at_start"),
    ("nfc", "quit_on_remove"), ("nfc", "rf_reset_each_poll"), ("nfc", "write_timeout"),
])


class Config(SimpleNamespace):
    """Typed configuration: ``cfg.pins.power``, ``cfg.fan.threshold_on``..."""

    @classmethod
    def defaults(cls):
        def default(kind, value):
            return shlex.split(value) if kind == "cmd" else value  # commands are stored as argument lists

        cfg = cls(**{s: SimpleNamespace(**{k: default(*v) for k, v in keys.items()}) for s, keys in SPEC.items()})
        cfg.source = None  # the file the settings came from (None = built-in defaults)
        return cfg

    @classmethod
    def load(cls, path=None):
        """Load ``path`` (or $PICONTROL_CONFIG, or the default location). Missing default file = defaults."""
        explicit = path or os.environ.get("PICONTROL_CONFIG")
        candidate = explicit or DEFAULT_CONFIG_PATH
        cfg = cls.defaults()
        if not os.path.exists(candidate):
            if explicit:
                raise ConfigError("config file not found: %s" % candidate)
            return cfg
        parser = configparser.ConfigParser(inline_comment_prefixes=(";",), interpolation=None)
        try:
            with open(candidate, encoding="utf-8") as handle:
                parser.read_file(handle)
        except (OSError, configparser.Error) as exc:
            raise ConfigError("cannot read %s: %s" % (candidate, exc))
        for section in parser.sections():
            if section not in SPEC:
                raise ConfigError("unknown section [%s]" % section)
            for key in parser.options(section):
                if key not in SPEC[section]:
                    raise ConfigError("unknown key '%s' in [%s]" % (key, section))
                setattr(getattr(cfg, section), key, _convert(parser, section, key))
        cfg.source = candidate
        cfg.validate()
        return cfg

    def validate(self):
        pins = vars(self.pins)
        for name, pin in pins.items():
            if not 0 <= pin <= 27:
                raise ConfigError("[pins] %s=%d is not a valid BCM pin (0-27)" % (name, pin))
        if len(set(pins.values())) != len(pins):
            raise ConfigError("[pins] each signal needs its own pin (duplicate pin numbers found)")
        if self.power.off_level not in ("high", "low"):
            raise ConfigError("[power] off_level must be 'high' or 'low'")
        if self.fan.threshold_on <= self.fan.threshold_off:
            raise ConfigError("[fan] threshold_on must be greater than threshold_off")
        positive = [("power", "debounce"), ("power", "poll_interval"), ("fan", "interval"),
                    ("nfc", "poll_interval"), ("nfc", "poll_interval_game"), ("nfc", "remove_delay"),
                    ("reset", "long_press"), ("nfc", "write_timeout")]
        for section, key in positive:
            if getattr(getattr(self, section), key) <= 0:
                raise ConfigError("[%s] %s must be > 0" % (section, key))
        if self.nfc.max_read_attempts < 1:
            raise ConfigError("[nfc] max_read_attempts must be >= 1")
        if not isinstance(logging.getLevelName(self.logging.level.upper()), int):
            raise ConfigError("[logging] unknown level '%s'" % self.logging.level)
        if not self.power.shutdown_command:
            raise ConfigError("[power] shutdown_command must not be empty")
        web = self.web
        if not 1 <= web.port <= 65535:
            raise ConfigError("[web] port must be between 1 and 65535")
        for key in ("session_timeout", "lockout"):
            if getattr(web, key) <= 0:
                raise ConfigError("[web] %s must be > 0" % key)
        if web.max_login_failures < 1:
            raise ConfigError("[web] max_login_failures must be >= 1")
        for network in web.allowed_networks:
            try:
                ipaddress.ip_network(network, strict=False)
            except ValueError:
                raise ConfigError("[web] allowed_networks: '%s' is not a network (e.g. 192.168.1.0/24)" % network)

    @property
    def power_off_level(self):
        """Pin level (0/1) that means 'switch is OFF'."""
        return 1 if self.power.off_level == "high" else 0


def _convert(parser, section, key):
    kind = SPEC[section][key][0]
    try:
        if kind == "int":
            return parser.getint(section, key)
        if kind == "float":
            return parser.getfloat(section, key)
        if kind == "bool":
            return parser.getboolean(section, key)
        raw = parser.get(section, key).strip()
        if kind == "cmd":
            return shlex.split(raw)
        if kind == "list":
            return tuple(item.strip() for item in raw.split(",") if item.strip())
        return raw
    except ValueError as exc:
        raise ConfigError("[%s] %s: %s" % (section, key, exc))
