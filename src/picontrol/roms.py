"""ROM name validation. / Validation des noms de ROM.

Shared by the service (which reads names from a tag) and the console session (which receives them from
the service): both check them, because the data crosses a process boundary.
Partagé par le service (noms lus sur un tag) et la session de console (noms reçus du service) : les deux
vérifient, car la donnée traverse une frontière entre processus.
"""

import os
import re

from .errors import LaunchError

SYSTEM_RE = re.compile(r"^[A-Za-z0-9_+-]{1,40}$")


def resolve_rom(roms_dir, system, rom):
    """Return the absolute path of a ROM after validating both names.

    The system must look like a folder name; the ROM must be a plain file name that, once symbolic links
    are resolved, still sits directly inside the system folder and exists.
    """
    if not isinstance(system, str) or not SYSTEM_RE.match(system):
        raise LaunchError("invalid system name: %r" % (system,))
    if not isinstance(rom, str) or not rom or rom in (".", "..") or "/" in rom or "\\" in rom or "\x00" in rom:
        raise LaunchError("invalid ROM name: %r" % (rom,))
    base = os.path.realpath(os.path.join(roms_dir, system))
    path = os.path.realpath(os.path.join(base, rom))
    if os.path.dirname(path) != base:
        raise LaunchError("path escapes the system folder: %r" % rom)
    if not os.path.exists(path):
        raise LaunchError("ROM not found: %s" % path)
    return path
