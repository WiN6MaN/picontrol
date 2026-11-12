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

def _info(label, label_fr, text, text_fr, unit=None, minimum=None, maximum=None):
    return {"label": {"en": label, "fr": label_fr}, "description": {"en": text, "fr": text_fr},
            "unit": unit, "min": minimum, "max": maximum}


# What the web form shows for each editable setting (English and French) and the range the server enforces.
# Ce que le formulaire web affiche pour chaque réglage modifiable (anglais et français) et la plage imposée.
SETTING_INFO = {
    "power.enabled": _info(
        "Power switch", "Interrupteur power",
        "When the switch is flipped OFF the Pi shuts down cleanly: the game saves first. Turn this off only if your console has no power switch.",
        "Quand l'interrupteur passe sur OFF, le Pi s'éteint proprement : le jeu est sauvegardé d'abord. Ne le désactivez que si votre console n'a pas d'interrupteur."),
    "power.off_level": _info(
        "Switch OFF level", "Niveau « interrupteur OFF »",
        "Electrical level read when the switch is OFF. Keep 'high' for the standard Pi Control board; choose 'low' only if the switch seems inverted.",
        "Niveau électrique lu quand l'interrupteur est sur OFF. Gardez « high » pour la carte Pi Control standard ; choisissez « low » seulement si l'interrupteur semble inversé."),
    "power.debounce": _info(
        "Debounce time", "Délai anti-rebond",
        "How long the switch must stay OFF before the shutdown starts. Filters out contact glitches.",
        "Durée pendant laquelle l'interrupteur doit rester sur OFF avant l'arrêt. Filtre les parasites de contact.", "s", 0.05, 5),
    "power.quit_grace": _info(
        "Save time before shutdown", "Temps de sauvegarde avant l'arrêt",
        "Seconds given to the game (RetroArch) to save and quit before the Pi powers off.",
        "Secondes laissées au jeu (RetroArch) pour sauvegarder et quitter avant l'extinction du Pi.", "s", 0, 30),
    "reset.enabled": _info(
        "Reset button", "Bouton reset",
        "A short press resets the running game; a long press writes the running game to a tag.",
        "Un appui court relance le jeu en cours ; un appui long écrit le jeu en cours sur un tag."),
    "reset.long_press": _info(
        "Long press duration", "Durée de l'appui long",
        "How long to hold the reset button for it to count as a long press.",
        "Durée pendant laquelle il faut maintenir le bouton reset pour compter comme un appui long.", "s", 0.5, 10),
    "fan.enabled": _info(
        "Automatic fan control", "Contrôle automatique du ventilateur",
        "Pi Control switches the fan on and off according to the CPU temperature. When off, the software never drives the fan.",
        "Pi Control allume et éteint le ventilateur selon la température du processeur. Désactivé, le logiciel ne pilote jamais le ventilateur."),
    "fan.threshold_on": _info(
        "Start temperature", "Température de démarrage",
        "The fan starts when the CPU reaches this temperature.",
        "Le ventilateur démarre quand le processeur atteint cette température.", "°C", 30, 85),
    "fan.threshold_off": _info(
        "Stop temperature", "Température d'arrêt",
        "The fan stops when the CPU has cooled down to this temperature. It must be lower than the start temperature.",
        "Le ventilateur s'arrête quand le processeur est redescendu à cette température. Elle doit être inférieure à la température de démarrage.", "°C", 20, 80),
    "fan.interval": _info(
        "Check interval", "Fréquence de mesure",
        "How often the temperature is read.",
        "Fréquence de lecture de la température.", "s", 1, 60),
    "fan.min_run": _info(
        "Minimum run time", "Durée de marche minimale",
        "Once started, the fan keeps running at least this long, so it does not switch on and off repeatedly.",
        "Une fois démarré, le ventilateur tourne au moins cette durée, pour qu'il ne s'allume pas et ne s'éteigne pas sans cesse.", "s", 0, 600),
    "led.enabled": _info(
        "Front-panel LED", "LED de façade",
        "The LED is lit while the service runs and blinks to give feedback (reset, tag written, error, shutdown).",
        "La LED est allumée tant que le service tourne et clignote pour donner un retour (reset, tag écrit, erreur, arrêt)."),
    "nfc.enabled": _info(
        "NFC reader", "Lecteur NFC",
        "Presenting a tag starts its game. When off, the reader is never used (the tag commands and the web tag tools stop working too).",
        "Présenter un tag lance son jeu. Désactivé, le lecteur n'est jamais utilisé (les commandes et les outils web pour les tags cessent aussi de fonctionner)."),
    "nfc.poll_interval": _info(
        "Detection interval", "Fréquence de détection",
        "How often the reader looks for a tag. Lower is more responsive but uses slightly more CPU.",
        "Fréquence à laquelle le lecteur cherche un tag. Plus bas = plus réactif, mais un peu plus de processeur.", "s", 0.1, 5),
    "nfc.poll_interval_game": _info(
        "Detection interval during a game", "Fréquence de détection pendant un jeu",
        "Same, while a game started by a tag is running. A higher value spares the CPU during play.",
        "Idem, pendant qu'un jeu lancé par un tag tourne. Une valeur plus haute ménage le processeur pendant le jeu.", "s", 0.2, 10),
    "nfc.remove_delay": _info(
        "Removal delay", "Délai de retrait",
        "A tag must be missing this long to count as removed. Avoids relaunching the game if the tag wobbles on the reader.",
        "Un tag doit être absent aussi longtemps pour compter comme retiré. Évite de relancer le jeu si le tag bouge sur le lecteur.", "s", 0.5, 30),
    "nfc.min_relaunch_interval": _info(
        "Minimum time between launches", "Délai minimal entre deux lancements",
        "Safety delay between two game launches.",
        "Délai de sécurité entre deux lancements de jeu.", "s", 0, 60),
    "nfc.max_read_attempts": _info(
        "Read attempts", "Tentatives de lecture",
        "How many times to retry reading a tag before giving up on it.",
        "Nombre d'essais de lecture d'un tag avant d'abandonner.", None, 1, 10),
    "nfc.launch_at_start": _info(
        "Launch at start-up", "Lancer au démarrage",
        "If a tag is already on the reader when the service starts, launch its game.",
        "Si un tag est déjà sur le lecteur au démarrage du service, lance son jeu."),
    "nfc.quit_on_remove": _info(
        "Quit the game when the tag is removed", "Quitter le jeu au retrait du tag",
        "Like pulling a cartridge out: removing the tag closes the game.",
        "Comme retirer une cartouche : retirer le tag ferme le jeu."),
    "nfc.rf_reset_each_poll": _info(
        "Radio reset before each detection (advanced)", "Réinitialisation radio avant chaque détection (avancé)",
        "Briefly cuts the radio field before each check so a tag is always detected. Leave on unless you are troubleshooting.",
        "Coupe brièvement le champ radio avant chaque détection pour que le tag soit toujours vu. Laissez activé, sauf pour un dépannage."),
    "nfc.write_timeout": _info(
        "Time to present a tag", "Temps pour présenter un tag",
        "Seconds you have to present a tag when reading or writing one.",
        "Secondes dont vous disposez pour présenter un tag lors d'une lecture ou d'une écriture.", "s", 3, 120),
}

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


def _check_range(dotted, number):
    info = SETTING_INFO.get(dotted, {})
    low, high = info.get("min"), info.get("max")
    if low is not None and not low <= number <= high:
        raise ConfigError("%s must be between %s and %s" % (dotted, low, high))


def normalise(changes):
    """{'fan.threshold_on': 65} -> {'fan': {'threshold_on': '65.0'}}; rejects anything not editable."""
    if not isinstance(changes, dict) or not changes:
        raise ConfigError("no changes given")
    out = {}
    for dotted, value in changes.items():
        section, _, key = str(dotted).partition(".")
        if (section, key) not in WEB_EDITABLE:
            raise ConfigError("'%s' cannot be changed from the web interface" % dotted)
        text = _format(SPEC[section][key][0], value, dotted)
        if SPEC[section][key][0] in ("int", "float"):
            _check_range(dotted, value)
        out.setdefault(section, {})[key] = text
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
                name = "%s.%s" % (section, key)
                info = SETTING_INFO[name]
                item = {"name": name, "type": kind, "default": default, "value": getattr(getattr(cfg, section), key),
                        "label": info["label"], "description": info["description"],
                        "unit": info["unit"], "min": info["min"], "max": info["max"]}
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
