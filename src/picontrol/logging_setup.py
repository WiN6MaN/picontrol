"""Logging setup. / Configuration des journaux.

A small rotating file (the SD card is not written to per poll - only events are logged),
falling back to stderr when the file is not writable.
Petit fichier tournant (seuls les événements sont journalisés) ; repli sur stderr si le fichier est inaccessible.
"""

import logging
import logging.handlers
import sys

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(cfg, debug=False, to_stderr=None):
    root = logging.getLogger("picontrol")
    root.handlers[:] = []
    root.setLevel(logging.DEBUG if debug else getattr(logging, cfg.logging.level.upper()))
    formatter = logging.Formatter(FORMAT)
    file_ok = False
    try:
        handler = logging.handlers.RotatingFileHandler(cfg.logging.file, maxBytes=200000, backupCount=2)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        file_ok = True
    except OSError:
        pass
    if to_stderr is None:
        to_stderr = debug or not file_ok or sys.stderr.isatty()
    if to_stderr:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)
    return root
