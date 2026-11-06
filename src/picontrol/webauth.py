"""Authentication helpers for the web interface. / Authentification de l'interface web.

  * passwords: PBKDF2-HMAC-SHA256 with a random salt (standard library only)
  * sessions: random tokens kept in memory, idle timeout, with a per-session CSRF token
  * login rate limiting per client address
  * network guards: only private-network clients and sane ``Host`` headers are served
Mots de passe hachés (PBKDF2), sessions en mémoire avec jeton CSRF, limitation des essais de connexion,
et filtrage des clients (réseau privé seulement) et de l'en-tête Host.
"""

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
import time
from urllib.parse import urlsplit

from .errors import ConfigError

MIN_PASSWORD_LENGTH = 8
ITERATIONS = 200000
SCHEME = "pbkdf2_sha256"


def hash_password(password, iterations=ITERATIONS, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "%s$%d$%s$%s" % (SCHEME, iterations, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password, stored):
    """Constant-time check of ``password`` against a stored hash string (False on anything malformed)."""
    try:
        scheme, iterations, salt, digest = stored.strip().split("$")
        if scheme != SCHEME:
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(iterations))
    except (ValueError, AttributeError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def load_password(path):
    try:
        with open(path, encoding="ascii") as handle:
            return handle.read().strip() or None
    except OSError:
        return None


def save_password(path, password):
    """Store the hash of ``password`` (mode 0600). Under sudo the file is handed to the invoking user."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ConfigError("the password must be at least %d characters long" % MIN_PASSWORD_LENGTH)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(hash_password(password) + "\n")
    os.chmod(path, 0o600)
    owner = os.environ.get("SUDO_USER")
    if owner and os.geteuid() == 0:
        try:
            import pwd
            entry = pwd.getpwnam(owner)
            os.chown(path, entry.pw_uid, entry.pw_gid)
        except (KeyError, OSError):
            pass


class SessionStore:
    """In-memory sessions with an idle timeout. A restart of the service logs everybody out."""

    def __init__(self, timeout, clock=time.monotonic):
        self.timeout, self._clock = timeout, clock
        self._sessions = {}
        self._lock = threading.Lock()

    def create(self):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self._lock:
            self._purge()
            self._sessions[token] = {"csrf": csrf, "last": self._clock()}
        return token, csrf

    def get(self, token):
        if not token:
            return None
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            now = self._clock()
            if now - session["last"] > self.timeout:
                del self._sessions[token]
                return None
            session["last"] = now
            return session

    def delete(self, token):
        with self._lock:
            self._sessions.pop(token, None)

    def _purge(self):
        now = self._clock()
        for token in [t for t, s in self._sessions.items() if now - s["last"] > self.timeout]:
            del self._sessions[token]


class LoginLimiter:
    """Lock an address out for ``lockout`` seconds after ``max_failures`` failures in that window."""

    def __init__(self, max_failures, lockout, clock=time.monotonic):
        self.max_failures, self.lockout, self._clock = max_failures, lockout, clock
        self._failures = {}
        self._lock = threading.Lock()

    def locked_for(self, address):
        """Seconds left on the lockout (0 = free to try)."""
        with self._lock:
            entry = self._failures.get(address)
            if not entry:
                return 0.0
            now = self._clock()
            if now - entry["first"] > self.lockout:
                del self._failures[address]
                return 0.0
            if entry["count"] >= self.max_failures:
                return self.lockout - (now - entry["first"])
            return 0.0

    def failed(self, address):
        with self._lock:
            now = self._clock()
            entry = self._failures.get(address)
            if entry is None or now - entry["first"] > self.lockout:
                entry = self._failures[address] = {"count": 0, "first": now}
            entry["count"] += 1
            if len(self._failures) > 1000:  # bounded memory
                self._failures.pop(next(iter(self._failures)))

    def succeeded(self, address):
        with self._lock:
            self._failures.pop(address, None)


def client_allowed(address, web):
    """Only loopback, private and link-local clients (plus ``allowed_networks``) unless allow_public."""
    if web.allow_public:
        return True
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return True
    return any(ip in ipaddress.ip_network(net, strict=False) for net in web.allowed_networks
               if ip.version == ipaddress.ip_network(net, strict=False).version)


def host_allowed(host_header, web, hostname):
    """Refuse unexpected ``Host`` names (defence against DNS rebinding): IPs, localhost, *.local, this machine."""
    if not host_header:
        return False
    name = (urlsplit("//" + host_header).hostname or "").lower()
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    allowed = {"localhost", hostname.lower(), hostname.lower() + ".local"} | {h.lower() for h in web.allowed_hosts}
    return name in allowed or name.endswith(".local")
