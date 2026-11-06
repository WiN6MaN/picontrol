"""Safe editing of the configuration file from the web interface. / Édition sûre du fichier de configuration.

Only the settings in ``config.WEB_EDITABLE`` can be changed. The file is edited *line by line* so your
comments survive; the result is validated by loading it as a real configuration before it replaces the
old file, and the previous version is kept as ``picontrol.conf.bak``.
Seuls les réglages de ``WEB_EDITABLE`` sont modifiables ; les commentaires sont conservés, le résultat est
validé avant d'écraser l'ancien fichier (copie ``.bak``).
"""

import os
import re
import shutil
import tempfile

from .config import SPEC, WEB_EDITABLE, Config
from .errors import ConfigError

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KEY_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=")
CHOICES = {("power", "off_level"): ["high", "low"]}


def _format(kind, value, name):
    if kind == "bool":
        if not isinstance(value, bool):
            raise ConfigError("%s must be true or false" % name)
        return "true" if value else "false"
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError("%s must be a whole number" % name)
        return str(value)
    if kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError("%s must be a number" % name)
        return repr(float(value))
    if kind == "str":
        if not isinstance(value, str) or "\n" in value or "\r" in value or ";" in value:
            raise ConfigError("%s has an invalid value" % name)
        return value
    raise ConfigError("%s cannot be edited" % name)


def normalise(changes):
    """{'fan.threshold_on': 65} -> {'fan': {'threshold_on': '65.0'}}; rejects anything not editable."""
    if not isinstance(changes, dict) or not changes:
        raise ConfigError("no changes given")
    out = {}
    for dotted, value in changes.items():
        section, _, key = str(dotted).partition(".")
        if (section, key) not in WEB_EDITABLE:
            raise ConfigError("'%s' cannot be changed from the web interface" % dotted)
        out.setdefault(section, {})[key] = _format(SPEC[section][key][0], value, dotted)
    return out


def update_text(text, changes):
    """Apply normalised changes to INI text, keeping every comment and the layout."""
    blocks = [[None, []]]  # [section name, lines]; block 0 is the preamble before any section
    for line in text.splitlines():
        match = SECTION_RE.match(line)
        if match:
            blocks.append([match.group(1).strip(), [line]])
        else:
            blocks[-1][1].append(line)
    pending = {section: dict(keys) for section, keys in changes.items()}
    for name, lines in blocks:
        todo = pending.get(name)
        if not todo:
            continue
        for index, line in enumerate(lines):
            match = KEY_RE.match(line)
            if match and match.group(1) in todo:
                key = match.group(1)
                lines[index] = "%s = %s" % (key, todo.pop(key))
        if todo:  # keys missing from this section: add them after its last non-blank line
            last = max((i for i, l in enumerate(lines) if l.strip()), default=len(lines) - 1)
            lines[last + 1:last + 1] = ["%s = %s" % (key, value) for key, value in todo.items()]
        pending[name] = {}
    for name, todo in pending.items():  # sections missing altogether
        if todo:
            blocks.append([name, ["", "[%s]" % name] + ["%s = %s" % kv for kv in todo.items()]])
    out = []
    for _, lines in blocks:
        out.extend(lines)
    return "\n".join(out).rstrip("\n") + "\n"


def editable_settings(cfg):
    """The editable settings with their current values, for the web form."""
    out = []
    for section, keys in SPEC.items():
        for key, (kind, default) in keys.items():
            if (section, key) in WEB_EDITABLE:
                item = {"name": "%s.%s" % (section, key), "type": kind, "default": default,
                        "value": getattr(getattr(cfg, section), key)}
                if (section, key) in CHOICES:
                    item["choices"] = CHOICES[(section, key)]
                out.append(item)
    return out


def apply(path, changes):
    """Validate and write ``changes`` into the configuration file at ``path``."""
    normalised = normalise(changes)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        text = ""
    new_text = update_text(text, normalised)
    fd, tmp = tempfile.mkstemp(suffix=".conf")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_text)
        Config.load(tmp)  # raises ConfigError if the result is not a valid configuration
    finally:
        os.unlink(tmp)
    if os.path.exists(path):
        shutil.copyfile(path, path + ".bak")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(new_text)
    return new_text
