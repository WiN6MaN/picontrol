"""Foreground console session. / Session de console au premier plan.

Why this exists / Pourquoi cela existe
--------------------------------------
On RetroPie, ``autostart.sh`` runs EmulationStation (ES) in the *foreground* of the console (tty1). That is
what lets ES, ``runcommand.sh`` and the RetroPie menus (dialog screens: RetroPie Setup, Raspi-Config, Wi-Fi...)
read the controller and the keyboard. If something kills ES from the outside, ``autostart.sh`` ends, the login
shell takes the console back, and everything started later by a background service (the game, then ES again)
runs *behind* that shell: the menus then receive the wrong input and fall back to ES by themselves.
Sur RetroPie, ``autostart.sh`` exécute EmulationStation au premier plan de la console (tty1). Si on tue ES de
l'extérieur, ``autostart.sh`` se termine, le shell de connexion reprend la console, et tout ce qu'un service
d'arrière-plan lance ensuite (le jeu, puis ES) tourne *derrière* ce shell : les menus reçoivent alors de
mauvaises entrées et reviennent seuls à ES.

How it works / Fonctionnement
-----------------------------
``picontrol session`` replaces the ``emulationstation`` line of ``autostart.sh`` and stays in the foreground
for good. It runs ES; when the service wants a game started from a tag, it drops a small request file and
stops ES; the session then runs ``runcommand.sh`` itself (exactly as ES would) and starts ES again afterwards.
Every process therefore keeps the console, like a game started from ES.
``picontrol session`` remplace la ligne ``emulationstation`` de ``autostart.sh`` et reste au premier plan. Il
lance ES ; quand le service veut démarrer un jeu depuis un tag, il dépose un petit fichier de demande et arrête
ES ; la session lance alors ``runcommand.sh`` elle-même (comme ES) puis relance ES. Tous les processus gardent la
console, comme pour un jeu lancé depuis ES.

Security: the request file lives in ``/dev/shm`` (RAM, shared by all users), so it is created with
``O_EXCL``/``O_NOFOLLOW``, read only if it is a small regular file owned by the same user, and its names are
validated again before anything is run (no shell, argument lists only).
Sécurité : le fichier de demande est dans ``/dev/shm`` (partagé par tous les utilisateurs) : création avec
``O_EXCL``/``O_NOFOLLOW``, lecture seulement si c'est un petit fichier ordinaire appartenant au même
utilisateur, noms revalidés avant toute exécution (aucun shell).
"""

import json
import logging
import os
import stat
import subprocess
import time

from . import roms
from .errors import LaunchError

log = logging.getLogger("picontrol.session")

RUNTIME_DIR = "/dev/shm"
MAX_REQUEST_BYTES = 4096
MAX_REQUEST_AGE = 120.0  # seconds: an older request is stale and ignored
ES_PROGRAM = "emulationstation"


# ---------------------------------------------------------------------- request / pid files
def _runtime(runtime_dir):
    """Folder of the request and pid files: argument, then $PICONTROL_RUNTIME_DIR, then /dev/shm."""
    return runtime_dir or os.environ.get("PICONTROL_RUNTIME_DIR") or RUNTIME_DIR


def request_path(runtime_dir=None):
    return os.path.join(_runtime(runtime_dir), "picontrol-launch-%d" % os.geteuid())


def pid_path(runtime_dir=None):
    return os.path.join(_runtime(runtime_dir), "picontrol-session-%d.pid" % os.geteuid())


def _write_request(payload, runtime_dir=None):
    """Atomically create the request file (fails if it cannot be done safely)."""
    path = request_path(runtime_dir)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    data = json.dumps(payload).encode("utf-8")
    if len(data) > MAX_REQUEST_BYTES:
        raise LaunchError("launch request too large")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise LaunchError("cannot create the launch request: %s" % exc)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except OSError as exc:
        _unlink(tmp)
        raise LaunchError("cannot write the launch request: %s" % exc)


def request_launch(system, rom, runtime_dir=None):
    """Ask the session to play ``rom`` (names are validated by the session as well)."""
    _write_request({"action": "launch", "system": system, "rom": rom}, runtime_dir)


def request_exit(runtime_dir=None):
    """Ask the session to end instead of starting EmulationStation again (used when the system shuts down)."""
    _write_request({"action": "exit"}, runtime_dir)


def _unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def clear_request(runtime_dir=None):
    _unlink(request_path(runtime_dir))


def _ours(st):
    """A regular file owned by the current user."""
    return stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid()


def request_pending(runtime_dir=None):
    try:
        return _ours(os.lstat(request_path(runtime_dir)))
    except OSError:
        return False


def take_request(runtime_dir=None, now=None):
    """Return the pending request as a dict (and delete the file), or None.

    A file that is not ours, too big, stale or malformed is never executed; ours is always removed.
    """
    path = request_path(runtime_dir)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not _ours(st):
            log.warning("Ignoring a launch request that is not a regular file of ours")
            return None
        try:
            if st.st_size > MAX_REQUEST_BYTES:
                log.warning("Ignoring an oversized launch request")
                return None
            if (time.time() if now is None else now) - st.st_mtime > MAX_REQUEST_AGE:
                log.warning("Ignoring a stale launch request")
                return None
            raw = os.read(fd, MAX_REQUEST_BYTES + 1)
        finally:
            _unlink(path)
    finally:
        os.close(fd)
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        log.warning("Ignoring a malformed launch request")
        return None
    if isinstance(data, dict) and data.get("action") == "exit":
        return {"action": "exit"}
    if (isinstance(data, dict) and data.get("action") == "launch"
            and isinstance(data.get("system"), str) and isinstance(data.get("rom"), str)):
        return {"action": "launch", "system": data["system"], "rom": data["rom"]}
    log.warning("Ignoring an unknown launch request")
    return None


def session_running(runtime_dir=None, proc_root="/proc"):
    """True if a ``picontrol session`` of this user is alive (the pid file alone is not trusted)."""
    try:
        with open(pid_path(runtime_dir), encoding="ascii") as handle:
            pid = int(handle.read().strip())
        with open(os.path.join(proc_root, str(pid), "cmdline"), "rb") as handle:
            words = handle.read().decode("utf-8", "replace").split("\0")
    except (OSError, ValueError):
        return False
    return "picontrol" in words and "session" in words


# ---------------------------------------------------------------------- the session
class Session:
    """Runs EmulationStation, and tag-requested games, in the foreground of the console."""

    def __init__(self, cfg, call=subprocess.call, runtime_dir=None):
        self.cfg, self._call, self.runtime_dir = cfg, call, runtime_dir

    def _run(self, argv):
        try:
            return self._call(argv)
        except OSError as exc:
            log.error("Cannot run %s: %s", argv[0], exc)
            return 127

    def _play(self, system, rom):
        try:
            path = roms.resolve_rom(self.cfg.paths.roms_dir, system, rom)
        except LaunchError as exc:
            log.error("Launch request refused: %s", exc)
            return
        log.info("Starting %s / %s", system, path)
        status = self._run([self.cfg.paths.runcommand, "0", "_SYS_", system, path])
        log.info("Game ended (exit code %s)", status)

    def _register(self):
        path = pid_path(self.runtime_dir)
        _unlink(path)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write("%d\n" % os.getpid())
        except OSError as exc:
            log.warning("Cannot write the session pid file (tag launches will fall back): %s", exc)

    def _unregister(self):
        _unlink(pid_path(self.runtime_dir))

    def run(self, es_args=()):
        """Run until EmulationStation ends on its own; return its exit status.

        The first EmulationStation start uses exactly the arguments of the original ``autostart.sh`` line;
        later starts (after a tag game) use ``emulationstation_command`` from the configuration (``--no-splash``).
        """
        self._register()
        first = True
        status = 0
        try:
            while True:
                request = take_request(self.runtime_dir)
                if request is not None:
                    first = False
                    if request["action"] == "exit":
                        log.info("Session ends (shutdown)")
                        return 0
                    self._play(request["system"], request["rom"])
                    continue
                if first:
                    command = [ES_PROGRAM] + list(es_args)
                else:
                    command = list(self.cfg.paths.emulationstation_command)
                first = False
                log.info("Starting EmulationStation")
                status = self._run(command)
                if not request_pending(self.runtime_dir):
                    log.info("EmulationStation ended (exit code %s)", status)
                    return status
        except Exception:  # noqa: BLE001 - the console must never be left without EmulationStation
            log.exception("Session failed; starting plain EmulationStation")
            return self._run([ES_PROGRAM] + list(es_args))
        finally:
            self._unregister()
