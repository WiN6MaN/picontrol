"""RetroArch network commands (UDP). / Commandes réseau de RetroArch (UDP).

RetroArch must run with ``network_cmd_enable = true``. UDP gives no acknowledgement, so
``send`` only reports whether the datagram could be sent.
RetroArch doit tourner avec ``network_cmd_enable = true`` ; UDP ne confirme rien.
"""

import logging
import socket

log = logging.getLogger("picontrol.retroarch")


class RetroArch:
    def __init__(self, host="127.0.0.1", port=55355, dry_run=False):
        self.address = (host, port)
        self.dry_run = dry_run

    def send(self, command):
        if self.dry_run:
            log.info("[dry-run] RetroArch <- %s", command)
            return True
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(command.encode("ascii"), self.address)
            return True
        except OSError as exc:
            log.warning("cannot send %s to RetroArch: %s", command, exc)
            return False

    def reset(self):
        return self.send("RESET")

    def quit(self):
        return self.send("QUIT")


def read_option(cfg_path, key):
    """Return the value of ``key`` in a retroarch.cfg file (quotes stripped), or None."""
    value = None
    try:
        with open(cfg_path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, raw = line.partition("=")
                if name.strip() == key:
                    value = raw.strip().strip('"')
    except OSError:
        return None
    return value
