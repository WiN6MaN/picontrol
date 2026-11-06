"""What the web interface can see and do. / Ce que l'interface web peut voir et faire.

A thin facade over the running ``Service``: every method either returns plain data or raises
``ApiError`` with the HTTP status to report. The web layer (``web.py``) never touches the hardware,
the configuration file or the ROM folders directly - it goes through here.
Une façade au-dessus du ``Service`` : renvoie des données simples ou lève ``ApiError`` (statut HTTP).
"""

import logging
import os
import threading
import time

from . import __version__, configedit
from .config import DEFAULT_CONFIG_PATH, Config
from .errors import ApiError, BusyError, ConfigError, LaunchError
from .fan import read_temperature
from .launcher import SYSTEM_RE
from .nfc import TagJob

log = logging.getLogger("picontrol.web")

IGNORED_NAMES = frozenset(["gamelist.xml", "media", "images", "videos", "manuals"])
CACHE_SECONDS = 30.0
MAX_LIMIT = 200
LOG_CHUNK = 65536


def system_uptime():
    try:
        with open("/proc/uptime", encoding="ascii") as handle:
            return float(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


class Backend:
    def __init__(self, service, clock=time.monotonic, timer=threading.Timer):
        self.service, self.cfg = service, service.cfg
        self._clock, self._timer = clock, timer
        self.pending_restart = False
        self._cache = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ status
    def status(self):
        service, cfg = self.service, self.cfg
        game = {"running": service.launcher.any_game_running(), "system": None, "rom": None}
        if game["running"]:
            try:
                game["system"], game["rom"] = service.launcher.current_game()
            except LaunchError:
                pass
        power = None
        if service.power is not None:
            power = "off" if service.gpio.read(cfg.pins.power) == cfg.power_off_level else "on"
        return {
            "version": __version__,
            "dry_run": service.dry_run,
            "service_uptime": round(self._clock() - service.started),
            "system_uptime": system_uptime(),
            "temperature": read_temperature(cfg.fan.temp_path),
            "fan": {"enabled": service.fan is not None, "on": service.fan.is_on if service.fan else None,
                    "threshold_on": cfg.fan.threshold_on, "threshold_off": cfg.fan.threshold_off},
            "power_switch": power,
            "game": game,
            "nfc": service.nfc.status() if service.nfc else {"enabled": False},
            "restart_required": self.pending_restart,
        }

    # ------------------------------------------------------------------ ROM browsing
    def _system_dir(self, system):
        if not isinstance(system, str) or not SYSTEM_RE.match(system):
            raise ApiError(400, "invalid system name")
        path = os.path.join(self.cfg.paths.roms_dir, system)
        if not os.path.isdir(path):
            raise ApiError(404, "unknown system")
        return path

    def _names(self, system):
        """Sorted ROM names of a system, cached for a short time (folders can hold thousands of files)."""
        with self._lock:
            cached = self._cache.get(system)
            if cached and self._clock() - cached[0] < CACHE_SECONDS:
                return cached[1]
        names = []
        with os.scandir(self._system_dir(system)) as entries:
            for entry in entries:
                if not entry.name.startswith(".") and entry.name.lower() not in IGNORED_NAMES:
                    names.append(entry.name)
        names.sort(key=str.casefold)
        with self._lock:
            self._cache[system] = (self._clock(), names)
        return names

    def systems(self):
        found = []
        try:
            with os.scandir(self.cfg.paths.roms_dir) as entries:
                for entry in entries:
                    if entry.is_dir() and SYSTEM_RE.match(entry.name):
                        found.append(entry.name)
        except OSError:
            raise ApiError(500, "the ROM folder cannot be read")
        return [{"name": name, "count": len(self._names(name))} for name in sorted(found, key=str.casefold)]

    def roms(self, system, query="", offset=0, limit=50):
        names = self._names(system)
        words = (query or "").casefold().split()
        if words:
            names = [n for n in names if all(word in n.casefold() for word in words)]
        limit = max(1, min(int(limit), MAX_LIMIT))
        offset = max(0, int(offset))
        return {"system": system, "total": len(names), "offset": offset, "items": names[offset:offset + limit]}

    # ------------------------------------------------------------------ NFC tags
    def tag(self, kind, system=None, rom=None):
        """Run a tag operation on the NFC thread and wait for the person to present a tag."""
        nfc, launcher = self.service.nfc, self.service.launcher
        if nfc is None:
            raise ApiError(409, "NFC is disabled in the configuration")
        timeout = self.cfg.nfc.write_timeout
        try:
            if kind == "read":
                job = TagJob("read", timeout=timeout, announce=False)
            elif kind == "write":
                launcher.resolve_rom(system, rom)
                job = TagJob("write", [system, rom], timeout=timeout)
            elif kind == "write-current":
                system, rom = launcher.current_game()
                job = TagJob("write", [system, rom], timeout=timeout)
            else:
                raise ApiError(400, "unknown tag operation")
            nfc.submit(job)
        except LaunchError as exc:
            raise ApiError(400 if kind == "write" else 409, str(exc))
        except BusyError as exc:
            raise ApiError(409, str(exc))
        if not job.wait(timeout + 5):
            raise ApiError(504, "the NFC service did not answer")
        if job.timed_out:
            raise ApiError(408, job.error)
        if job.error:
            raise ApiError(422, job.error)
        return job.result

    # ------------------------------------------------------------------ configuration
    def _config_path(self):
        return self.cfg.source or DEFAULT_CONFIG_PATH

    def config_view(self):
        path = self._config_path()
        try:
            current = Config.load(path) if os.path.exists(path) else self.cfg
        except ConfigError:
            current = self.cfg
        return {"settings": configedit.editable_settings(current), "restart_required": self.pending_restart}

    def config_update(self, changes):
        try:
            configedit.apply(self._config_path(), changes)
        except ConfigError as exc:
            raise ApiError(400, str(exc))
        except OSError as exc:
            log.error("Cannot write the configuration: %s", exc)
            raise ApiError(500, "the configuration file cannot be written (check its permissions)")
        self.pending_restart = True
        log.info("Configuration changed from the web interface: %s", ", ".join(sorted(changes)))
        return {"ok": True, "restart_required": True}

    # ------------------------------------------------------------------ system actions
    def _later(self, action, label):
        log.warning("%s requested from the web interface", label)
        self._timer(0.5, action).start()  # answer the request first, then act
        return {"ok": True}

    def restart_service(self):
        return self._later(self.service.request_restart, "Service restart")

    def reboot(self):
        return self._later(self.service.reboot, "Reboot")

    def shutdown(self):
        return self._later(lambda: self.service.shutdown("Shutdown requested from the web interface"), "Shutdown")

    def log_tail(self, lines=100):
        lines = max(1, min(int(lines), 500))
        try:
            with open(self.cfg.logging.file, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                handle.seek(max(0, handle.tell() - LOG_CHUNK))
                text = handle.read().decode("utf-8", errors="replace")
        except OSError:
            return {"lines": []}
        return {"lines": text.splitlines()[-lines:]}
