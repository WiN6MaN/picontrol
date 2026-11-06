"""Web interface server (standard library only). / Serveur de l'interface web (bibliothèque standard).

Security model (see SECURITY.md)
  * OFF by default; never starts without a password; serves private-network clients only
  * HTTPS with a self-signed certificate by default; password hashed (PBKDF2); login rate limiting
  * session cookie HttpOnly + SameSite=Strict (+ Secure with HTTPS) and a CSRF token on every POST
  * strict Content-Security-Policy, ``Host`` header validation, request size limits, no shell anywhere
  * the browser can change only whitelisted numeric/boolean settings (``config.WEB_EDITABLE``)
Hors-ligne par défaut, jamais sans mot de passe, clients du réseau privé seulement ; HTTPS auto-signé ;
cookie de session HttpOnly + SameSite=Strict, jeton CSRF sur chaque POST ; CSP stricte ; réglages limités.
"""

import hashlib
import hmac
import http.server
import json
import logging
import os
import shutil
import socket
import ssl
import subprocess
import threading
import time
from collections import namedtuple
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

from . import webauth
from .errors import ApiError, ConfigError

log = logging.getLogger("picontrol.web")

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webui")
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
}
MAX_BODY = 65536
COOKIE = "picontrol_session"
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}

Response = namedtuple("Response", "status headers body")
Context = namedtuple("Context", "ip query body session token")


class App:
    """The request logic, independent of sockets: ``handle`` maps a request to a Response."""

    def __init__(self, cfg, backend, clock=time.monotonic, hostname=None):
        self.web, self.backend = cfg.web, backend
        self.hostname = hostname or socket.gethostname()
        self.sessions = webauth.SessionStore(self.web.session_timeout, clock)
        self.limiter = webauth.LoginLimiter(self.web.max_login_failures, self.web.lockout, clock)
        self._assets = {}
        self.routes = {
            ("POST", "/api/login"): (False, self.login),
            ("GET", "/api/session"): (False, self.session_info),
            ("POST", "/api/logout"): (True, self.logout),
            ("GET", "/api/state"): (True, lambda c: (200, self.backend.status())),
            ("GET", "/api/systems"): (True, lambda c: (200, {"systems": self.backend.systems()})),
            ("GET", "/api/roms"): (True, self.roms),
            ("POST", "/api/tag/read"): (True, lambda c: (200, self.backend.tag("read"))),
            ("POST", "/api/tag/write"): (True, self.tag_write),
            ("POST", "/api/tag/write-current"): (True, lambda c: (200, self.backend.tag("write-current"))),
            ("GET", "/api/config"): (True, lambda c: (200, self.backend.config_view())),
            ("POST", "/api/config"): (True, self.config_set),
            ("POST", "/api/service/restart"): (True, lambda c: self.confirmed(c, self.backend.restart_service)),
            ("POST", "/api/system/reboot"): (True, lambda c: self.confirmed(c, self.backend.reboot)),
            ("POST", "/api/system/shutdown"): (True, lambda c: self.confirmed(c, self.backend.shutdown)),
            ("GET", "/api/log"): (True, self.log_tail),
        }

    # ------------------------------------------------------------------ request handling
    def handle(self, method, target, headers, body, ip):
        try:
            if not webauth.client_allowed(ip, self.web):
                log.warning("Refused a request from outside the local network: %s", ip)
                return self.error(403, "access is limited to the local network")
            if not webauth.host_allowed(headers.get("Host", ""), self.web, self.hostname):
                return self.error(403, "unexpected Host header")
            parts = urlsplit(target)
            if method == "GET" and parts.path in STATIC:
                return self.static(parts.path)
            route = self.routes.get((method, parts.path))
            if route is None:
                known = any(path == parts.path for _, path in self.routes)
                return self.error(405 if known else 404, "method not allowed" if known else "not found")
            needs_auth, func = route
            token = self.cookie_token(headers)
            session = self.sessions.get(token)
            if needs_auth and session is None:
                return self.error(401, "login required")
            data = {}
            if method == "POST":
                if headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                    return self.error(415, "send application/json")
                if needs_auth and not hmac.compare_digest(headers.get("X-CSRF-Token", ""), session["csrf"]):
                    return self.error(403, "bad or missing CSRF token")
                data = self.parse_json(body)
            result = func(Context(ip, parse_qs(parts.query), data, session, token))
            status, payload = result[0], result[1]
            return self.json(status, payload, result[2] if len(result) > 2 else None)
        except ApiError as exc:
            return self.error(exc.status, str(exc))
        except Exception:  # noqa: BLE001
            log.exception("Unhandled error in the web interface")
            return self.error(500, "internal error")

    # ------------------------------------------------------------------ responses
    def json(self, status, payload, extra=None):
        headers = dict(SECURITY_HEADERS, **{"Content-Type": "application/json; charset=utf-8"})
        headers.update(extra or {})
        return Response(status, headers, json.dumps(payload).encode("utf-8"))

    def error(self, status, message):
        return self.json(status, {"error": message})

    def static(self, path):
        name, content_type = STATIC[path]
        if name not in self._assets:
            with open(os.path.join(ASSETS, name), "rb") as handle:
                self._assets[name] = handle.read()
        headers = dict(SECURITY_HEADERS, **{"Content-Type": content_type, "Cache-Control": "no-cache"})
        return Response(200, headers, self._assets[name])

    @staticmethod
    def parse_json(body):
        if not body:
            return {}
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "invalid JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "a JSON object is expected")
        return data

    @staticmethod
    def cookie_token(headers):
        try:
            cookie = SimpleCookie(headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001 - malformed cookie header
            return None
        morsel = cookie.get(COOKIE)
        return morsel.value if morsel else None

    def cookie(self, value, max_age):
        secure = "; Secure" if self.web.tls else ""
        return "%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=%d%s" % (COOKIE, value, max_age, secure)

    # ------------------------------------------------------------------ routes
    def login(self, ctx):
        wait = self.limiter.locked_for(ctx.ip)
        if wait > 0:
            raise ApiError(429, "too many failed attempts: try again in %d seconds" % (int(wait) + 1))
        password = ctx.body.get("password")
        stored = webauth.load_password(self.web.password_file)
        if not (isinstance(password, str) and stored and webauth.verify_password(password, stored)):
            self.limiter.failed(ctx.ip)
            log.warning("Failed web login from %s", ctx.ip)
            raise ApiError(401, "wrong password")
        self.limiter.succeeded(ctx.ip)
        token, csrf = self.sessions.create()
        log.info("Web login from %s", ctx.ip)
        return 200, {"ok": True, "csrf": csrf}, {"Set-Cookie": self.cookie(token, int(self.web.session_timeout))}

    def session_info(self, ctx):
        if ctx.session is None:
            return 200, {"authenticated": False}
        return 200, {"authenticated": True, "csrf": ctx.session["csrf"]}

    def logout(self, ctx):
        self.sessions.delete(ctx.token)
        return 200, {"ok": True}, {"Set-Cookie": self.cookie("", 0)}

    def roms(self, ctx):
        def one(name, default):
            return ctx.query.get(name, [default])[0]
        try:
            offset, limit = int(one("offset", "0")), int(one("limit", "50"))
        except ValueError:
            raise ApiError(400, "offset and limit must be numbers")
        return 200, self.backend.roms(one("system", ""), one("q", ""), offset, limit)

    def tag_write(self, ctx):
        system, rom = ctx.body.get("system"), ctx.body.get("rom")
        if not isinstance(system, str) or not isinstance(rom, str):
            raise ApiError(400, "system and rom are required")
        return 200, self.backend.tag("write", system, rom)

    def config_set(self, ctx):
        return 200, self.backend.config_update(ctx.body.get("changes"))

    @staticmethod
    def confirmed(ctx, action):
        if ctx.body.get("confirm") is not True:
            raise ApiError(400, "confirmation required")
        return 202, action()

    def log_tail(self, ctx):
        try:
            lines = int(ctx.query.get("lines", ["100"])[0])
        except ValueError:
            raise ApiError(400, "lines must be a number")
        return 200, self.backend.log_tail(lines)


class _Handler(http.server.BaseHTTPRequestHandler):
    timeout = 20  # a stalled client cannot hold a thread forever
    server_version = "picontrol"
    sys_version = ""

    def version_string(self):
        return "picontrol"  # no Python or library version in the Server header

    def do_GET(self):
        self._serve("GET")

    def do_POST(self):
        self._serve("POST")

    def _serve(self, method):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            response = self.server.app.error(413 if length > 0 else 400, "request body too large or invalid")
            self.close_connection = True
        else:
            body = self.rfile.read(length) if length else b""
            response = self.server.app.handle(method, self.path, self.headers, body, self.client_address[0])
        self.send_response(response.status)
        for name, value in response.headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)

    def log_message(self, fmt, *args):
        log.debug("%s - %s", self.client_address[0], fmt % args)


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):  # TLS handshake failures, resets, scanners...
        log.debug("connection error from %s", client_address[0], exc_info=True)


def ensure_certificate(web):
    """Create a self-signed certificate on first start (needs the openssl command)."""
    if os.path.exists(web.cert_file) and os.path.exists(web.key_file):
        return
    openssl = shutil.which("openssl")
    if not openssl:
        raise ConfigError("tls = true but no certificate exists and openssl is not installed")
    for path in (web.cert_file, web.key_file):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    log.info("Creating a self-signed certificate")
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", web.key_file,
                    "-out", web.cert_file, "-days", "3650", "-subj", "/CN=picontrol"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.chmod(web.key_file, 0o600)


def certificate_fingerprint(cert_file):
    with open(cert_file, encoding="ascii") as handle:
        digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(handle.read())).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


class WebServer:
    def __init__(self, cfg, backend, clock=time.monotonic):
        self.cfg = cfg
        if webauth.load_password(cfg.web.password_file) is None:
            raise ConfigError("the web interface is enabled but no password is set: run 'picontrol web set-password'")
        self.app = App(cfg, backend, clock)
        self.httpd = None
        self._thread = None

    @property
    def port(self):
        return self.httpd.server_address[1] if self.httpd else None

    def start(self):
        web = self.cfg.web
        context = None
        if web.tls:
            ensure_certificate(web)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(web.cert_file, web.key_file)
        self.httpd = _Server((web.host, web.port), _Handler)
        self.httpd.app = self.app
        if context:  # the handshake then happens in the request thread, not in the accept loop
            self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True, do_handshake_on_connect=False)
        self._thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.5},
                                        name="web-server", daemon=True)
        self._thread.start()
        scheme = "https" if web.tls else "http"
        log.info("Web interface listening on port %d (private networks only). Open %s://%s.local:%d or use the Pi's IP address",
                 self.port, scheme, self.app.hostname, self.port)
        if web.tls:
            log.info("Certificate SHA-256 fingerprint: %s", certificate_fingerprint(web.cert_file))

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    def run(self, stop):
        """Worker entry point: serve until ``stop`` is set."""
        self.start()
        try:
            while not stop.wait(1.0):
                pass
        finally:
            self.stop()
