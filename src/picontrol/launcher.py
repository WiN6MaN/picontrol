"""Game launching. / Lancement des jeux.

EmulationStation (ES) cannot be asked to start a game from outside, so a tag-triggered launch has to stop
ES, run RetroPie's ``runcommand.sh`` and start ES again when the game ends.
ES ne peut pas lancer un jeu depuis l'extérieur : un lancement par tag arrête ES, exécute ``runcommand.sh``
puis relance ES à la fin du jeu.

Normally the *console session* (``picontrol session``, see session.py) does the running: this module only
leaves it a request and stops ES, so the game and ES stay in the foreground of the console and the RetroPie
menus keep working. If no session is running (autostart.sh not updated yet), the old direct method is used as
a fallback, with a warning.
Normalement, c'est la *session de console* (``picontrol session``, voir session.py) qui exécute : ce module lui
laisse une demande et arrête ES, ainsi le jeu et ES restent au premier plan de la console et les menus RetroPie
fonctionnent. Sans session (autostart.sh pas encore mis à jour), l'ancienne méthode directe sert de repli.

Security: tag content is untrusted input. Names are validated, resolved inside the ROM folder and
passed as an argument list - never through a shell.
Sécurité : le contenu d'un tag est une entrée non fiable (noms validés, aucun shell).
"""

import logging
import os
import subprocess
import time

from . import roms, session
from .errors import LaunchError

log = logging.getLogger("picontrol.launcher")

ES_PATTERN = r"/opt/retropie/supplementary/.*/emulationstation([^.]|$)"
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


SESSION_WAIT = 15.0  # seconds to wait for the session to take a request
EMULATOR_WAIT = 20.0  # seconds before giving up waiting for the emulator of a session game to appear


class Launcher:
    def __init__(self, cfg, retroarch, procs=None, popen=subprocess.Popen, sleep=time.sleep, dry_run=False,
                 runtime_dir=None, clock=time.monotonic):
        self.cfg, self.retroarch = cfg, retroarch
        self.procs, self._popen, self._sleep, self.dry_run = procs or Procs(), popen, sleep, dry_run
        self.runtime_dir, self._clock = runtime_dir, clock
        self.proc = None  # the runcommand process we started (direct fallback only)
        self.es_stopped = False  # direct fallback: we stopped ES, it must be restarted
        self.shutting_down = False
        self._session_game = False  # a game started through the session may be running
        self._emulator_seen = False
        self._game_deadline = 0.0
        self._last_check = -1e9
        self._emulators = "|".join(EMULATOR_PROCESSES + tuple(cfg.paths.extra_emulators))

    # ------------------------------------------------------------------ validation
    def resolve_rom(self, system, rom):
        """Return the absolute path of a ROM after validating both names."""
        return roms.resolve_rom(self.cfg.paths.roms_dir, system, rom)

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
        if self._session_game:
            now = self._clock()
            if now - self._last_check >= 1.0:  # pgrep at most once a second
                self._last_check = now
                if self.any_game_running():
                    self._emulator_seen = True
                elif self._emulator_seen or now > self._game_deadline:
                    self._session_game = False
            return self._session_game
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
        if session.session_running(self.runtime_dir):
            if self._launch_through_session(system, os.path.basename(rom_path)):
                return
            log.warning("The console session did not answer; starting the game directly")
        else:
            log.warning("No console session is running, so the game is started directly and the RetroPie "
                        "menus may misbehave afterwards. Run install.sh again, then reboot.")
        self._launch_directly(system, rom_path)

    def _launch_through_session(self, system, rom):
        """Leave a request for the console session, then stop ES (and any game) so that it takes it."""
        try:
            session.request_launch(system, rom, self.runtime_dir)
        except LaunchError as exc:
            log.error("%s", exc)
            return False
        deadline = self._clock() + SESSION_WAIT
        attempt = 0
        # The session reads the request once EmulationStation (or the running game) has ended: keep asking
        # them to stop until that has happened. The emulator of the new game does not exist yet at that point.
        while session.request_pending(self.runtime_dir):
            if self._clock() > deadline:
                session.clear_request(self.runtime_dir)
                return False
            sig = "TERM" if attempt < 6 else "KILL"
            self.procs.pkill(sig, ES_PATTERN, full=True)
            self.procs.pkill(sig, self._emulators)
            self._sleep(0.5)
            attempt += 1
        self._session_game, self._emulator_seen = True, False
        self._game_deadline, self._last_check = self._clock() + EMULATOR_WAIT, -1e9
        return True

    def _launch_directly(self, system, rom_path):
        """Fallback without a console session: stop everything, run runcommand, restart ES in poll()."""
        self._session_game = False
        self._stop_all()
        if self.proc is not None:
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                log.warning("previous runcommand still running")
        self.es_stopped = True
        self.proc = self._popen([self.cfg.paths.runcommand, "0", "_SYS_", system, rom_path])

    def begin_shutdown(self):
        """The system is going down: do not start ES again when the running game ends."""
        self.shutting_down = True
        if not self.dry_run and session.session_running(self.runtime_dir):
            try:
                session.request_exit(self.runtime_dir)
            except LaunchError as exc:
                log.warning("%s", exc)

    def cancel_shutdown(self):
        self.shutting_down = False
        session.clear_request(self.runtime_dir)

    def quit_game(self):
        """Ask RetroArch to quit (it saves), then fall back to terminating the emulator."""
        if self.dry_run or not self.game_running():
            return
        log.info("Closing the game")
        self.retroarch.quit()
        if self._session_game:
            for _ in range(20):  # up to ~4 s for the emulator to save and exit
                self._sleep(0.2)
                if not self.any_game_running():
                    return
        else:
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
