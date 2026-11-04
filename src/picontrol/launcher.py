"""Game launching and EmulationStation lifecycle. / Lancement des jeux et cycle de vie d'EmulationStation.

EmulationStation (ES) cannot be asked to start a game from outside, so a tag-triggered launch has
to stop ES, run RetroPie's ``runcommand.sh`` and start ES again when the game ends. Games started
from ES itself never go through here (ES keeps its lists in memory and returns instantly).
ES ne peut pas lancer un jeu depuis l'extérieur : un lancement par tag arrête ES puis le relance à la
fin du jeu. Les jeux lancés depuis ES ne passent jamais par ici.

Security: tag content is untrusted input. Names are validated, resolved inside the ROM folder and
passed as an argument list - never through a shell.
Sécurité : le contenu d'un tag est une entrée non fiable (noms validés, aucun shell).
"""

import logging
import os
import re
import subprocess
import time

from .errors import LaunchError

log = logging.getLogger("picontrol.launcher")

ES_PATTERN = r"/opt/retropie/supplementary/.*/emulationstation([^.]|$)"
SYSTEM_RE = re.compile(r"^[A-Za-z0-9_+-]{1,40}$")
EMULATOR_PROCESSES = (
    "retroarch", "ags", "uae4all2", "uae4arm", "capricerpi", "linapple", "hatari", "stella",
    "atari800", "xroar", "vice", "daphne", "reicast", "pifba", "osmose", "gpsp", "jzintv",
    "basiliskll", "mame", "advmame", "dgen", "openmsx", "mupen64plus", "gngeo", "dosbox",
    "ppsspp", "simcoupe", "scummvm", "snes9x", "pisnes", "frotz", "fbzx", "fuse", "gemrb",
    "cgenesis", "zdoom", "eduke32", "lincity", "love", "alephone", "micropolis", "openbor",
    "openttd", "opentyrian", "cannonball", "tyrquake", "ioquake3", "residualvm", "xrick",
    "sdlpop", "uqm", "stratagus", "wolf4sdl", "solarus",
)


class Procs:
    """pkill/pgrep wrapper (replaced by a fake in tests)."""

    @staticmethod
    def pkill(sig, pattern, full=False):
        cmd = ["pkill", "-" + sig] + (["-f"] if full else ["-x"]) + [pattern]
        subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def pgrep(pattern, full=False):
        cmd = ["pgrep"] + (["-f"] if full else ["-x"]) + [pattern]
        return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


class Launcher:
    def __init__(self, cfg, retroarch, procs=None, popen=subprocess.Popen, sleep=time.sleep, dry_run=False):
        self.cfg, self.retroarch = cfg, retroarch
        self.procs, self._popen, self._sleep, self.dry_run = procs or Procs(), popen, sleep, dry_run
        self.proc = None  # the runcommand process we started
        self.es_stopped = False  # we stopped ES: it must be restarted
        self.shutting_down = False
        self._emulators = "|".join(EMULATOR_PROCESSES + tuple(cfg.paths.extra_emulators))

    # ------------------------------------------------------------------ validation
    def resolve_rom(self, system, rom):
        """Return the absolute path of a ROM after validating both names."""
        if not SYSTEM_RE.match(system):
            raise LaunchError("invalid system name: %r" % system)
        if not rom or rom in (".", "..") or "/" in rom or "\\" in rom or "\x00" in rom:
            raise LaunchError("invalid ROM name: %r" % rom)
        base = os.path.realpath(os.path.join(self.cfg.paths.roms_dir, system))
        path = os.path.realpath(os.path.join(base, rom))
        if os.path.dirname(path) != base:
            raise LaunchError("path escapes the system folder: %r" % rom)
        if not os.path.exists(path):
            raise LaunchError("ROM not found: %s" % path)
        return path

    def current_game(self):
        """(system, rom) of the running game, from RetroPie's runcommand info file."""
        if not self.any_game_running():
            raise LaunchError("no game is running")
        try:
            with open(self.cfg.paths.runcommand_info, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
        except OSError as exc:
            raise LaunchError("cannot read %s: %s" % (self.cfg.paths.runcommand_info, exc))
        if len(lines) < 3:
            raise LaunchError("unexpected runcommand info file")
        system, rom = lines[0].strip(), os.path.basename(lines[2].strip())
        self.resolve_rom(system, rom)
        return system, rom

    # ------------------------------------------------------------------ state
    def game_running(self):
        """True while the game we launched is still running."""
        return self.proc is not None and self.proc.poll() is None

    def any_game_running(self):
        return self.procs.pgrep(self._emulators)

    # ------------------------------------------------------------------ actions
    def _stop_all(self):
        for sig in ("TERM", "KILL"):
            self.procs.pkill(sig, ES_PATTERN, full=True)
            self.procs.pkill(sig, self._emulators)
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                if not (self.procs.pgrep(ES_PATTERN, full=True) or self.procs.pgrep(self._emulators)):
                    return
                self._sleep(0.2)

    def launch(self, system, rom_path):
        if self.shutting_down:
            return
        log.info("Launching %s / %s", system, rom_path)
        if self.dry_run:
            log.info("[dry-run] nothing is stopped or started")
            return
        self._stop_all()
        if self.proc is not None:
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                log.warning("previous runcommand still running")
        self.es_stopped = True
        self.proc = self._popen([self.cfg.paths.runcommand, "0", "_SYS_", system, rom_path])

    def quit_game(self):
        """Ask RetroArch to quit (it saves), then fall back to terminating the emulator."""
        if self.dry_run or not self.game_running():
            return
        log.info("Closing the game")
        self.retroarch.quit()
        try:
            self.proc.wait(4)
            return
        except subprocess.TimeoutExpired:
            pass
        self.procs.pkill("TERM", self._emulators)

    def poll(self):
        """Call regularly: restart ES when a game we launched has ended."""
        if self.proc is not None and self.proc.poll() is not None:
            log.info("Game ended (exit code %s)", self.proc.returncode)
            self.proc = None
        if self.es_stopped and self.proc is None and not self.dry_run and not self.shutting_down:
            self.es_stopped = False
            if not self.procs.pgrep(ES_PATTERN, full=True):
                log.info("Restarting EmulationStation")
                self._popen(list(self.cfg.paths.emulationstation_command))
