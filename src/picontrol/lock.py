"""Inter-process lock for the NFC reader. / Verrou inter-processus pour le lecteur NFC.

The service and the ``picontrol tag`` commands must never talk to the PN532 at the same time
(interleaved frames corrupt each other - a classic source of random failures).
Le service et les commandes ``picontrol tag`` ne doivent jamais parler au PN532 simultanément.
"""

import fcntl
import os
import time


class ReaderLock:
    def __init__(self, path, wait=0.0):
        self.path, self.wait, self.fd = path, wait, None

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o666)
        try:
            os.chmod(self.path, 0o666)  # usable by any user (sudo or not)
        except OSError:
            pass
        deadline = time.monotonic() + self.wait
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.1)

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
