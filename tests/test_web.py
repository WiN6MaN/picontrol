"""The request logic (``web.App``) without sockets: authentication, CSRF, guards, routing."""

import json

import pytest

from conftest import FakeClock
from picontrol import webauth
from picontrol.errors import ApiError
from picontrol.web import MAX_BODY, SECURITY_HEADERS, App

PASSWORD = "correct horse battery"


class StubBackend:
    def __init__(self):
        self.calls = []

    def status(self):
        return {"version": "x"}

    def systems(self):
        return [{"name": "nes", "count": 2}]

    def roms(self, system, query, offset, limit):
        self.calls.append(("roms", system, query, offset, limit))
        return {"system": system, "total": 0, "offset": offset, "items": []}

    def tag(self, kind, system=None, rom=None):
        self.calls.append(("tag", kind, system, rom))
        if rom == "boom":
            raise ApiError(408, "no tag was presented in time")
        return {"uid": "01020304"}

    def config_view(self):
        return {"settings": [], "restart_required": False}

    def config_update(self, changes):
        self.calls.append(("config", changes))
        return {"ok": True, "restart_required": True}

    def restart_service(self):
        self.calls.append(("restart",))
        return {"ok": True}

    def reboot(self):
        self.calls.append(("reboot",))
        return {"ok": True}

    def shutdown(self):
        self.calls.append(("shutdown",))
        return {"ok": True}

    def log_tail(self, lines):
        self.calls.append(("log", lines))
        return {"lines": ["a"]}


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def backend():
    return StubBackend()


@pytest.fixture
def app(cfg, tmp_path, backend, clock):
    cfg.web.enabled, cfg.web.tls = True, False
    cfg.web.password_file = str(tmp_path / "web.passwd")
    with open(cfg.web.password_file, "w") as handle:
        handle.write(webauth.hash_password(PASSWORD, iterations=1000) + "\n")
    return App(cfg, backend, clock=clock, hostname="picontrol")


def call(app, method, path, body=None, cookie=None, csrf=None, ip="192.168.1.20", host="192.168.1.5:8443",
         content_type="application/json", raw=None):
    headers = {"Host": host}
    if content_type:
        headers["Content-Type"] = content_type
    if cookie:
        headers["Cookie"] = cookie
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
    response = app.handle(method, path, headers, data, ip)
    try:
        payload = json.loads(response.body.decode())
    except ValueError:
        payload = response.body.decode()
    return response.status, payload, response.headers


def login(app, **kwargs):
    status, payload, headers = call(app, "POST", "/api/login", {"password": PASSWORD}, **kwargs)
    assert status == 200, payload
    return headers["Set-Cookie"].split(";")[0], payload["csrf"]


PROTECTED = [("GET", "/api/state"), ("GET", "/api/systems"), ("GET", "/api/roms?system=nes"), ("POST", "/api/tag/read"),
             ("POST", "/api/tag/write"), ("POST", "/api/tag/write-current"), ("GET", "/api/config"), ("POST", "/api/config"),
             ("POST", "/api/service/restart"), ("POST", "/api/system/reboot"), ("POST", "/api/system/shutdown"),
             ("GET", "/api/log"), ("POST", "/api/logout")]


# ------------------------------------------------------------------ authentication
@pytest.mark.parametrize("method, path", PROTECTED)
def test_every_protected_route_requires_a_session(app, backend, method, path):
    status, payload, _ = call(app, method, path, {} if method == "POST" else None)
    assert status == 401 and payload == {"error": "login required"} and backend.calls == []


def test_login_sets_a_hardened_cookie(app):
    status, payload, headers = call(app, "POST", "/api/login", {"password": PASSWORD})
    cookie = headers["Set-Cookie"]
    assert status == 200 and payload["csrf"] and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert "Path=/" in cookie and "Max-Age=3600" in cookie and "Secure" not in cookie  # no TLS in this test
    assert PASSWORD not in json.dumps(payload) + cookie


def test_cookie_is_secure_with_tls(app):
    app.web.tls = True
    assert "Secure" in call(app, "POST", "/api/login", {"password": PASSWORD})[2]["Set-Cookie"]


@pytest.mark.parametrize("body", [{"password": "wrong"}, {"password": ""}, {}, {"password": 123}, {"password": None}])
def test_wrong_or_missing_password(app, body):
    status, payload, headers = call(app, "POST", "/api/login", body)
    assert status == 401 and "Set-Cookie" not in headers and "csrf" not in payload


def test_login_without_a_password_file_never_succeeds(app, cfg):
    cfg.web.password_file = "/nonexistent/web.passwd"
    assert call(app, "POST", "/api/login", {"password": PASSWORD})[0] == 401


def test_session_and_state(app):
    assert call(app, "GET", "/api/session")[1] == {"authenticated": False}
    cookie, csrf = login(app)
    assert call(app, "GET", "/api/session", cookie=cookie)[1] == {"authenticated": True, "csrf": csrf}
    assert call(app, "GET", "/api/state", cookie=cookie)[:2] == (200, {"version": "x"})


def test_a_forged_or_stale_cookie_is_rejected(app):
    assert call(app, "GET", "/api/state", cookie="picontrol_session=forged")[0] == 401
    assert call(app, "GET", "/api/state", cookie="garbage;;;=")[0] == 401


def test_session_expires_when_idle(app, clock):
    cookie, _ = login(app)
    clock.advance(3601)
    assert call(app, "GET", "/api/state", cookie=cookie)[0] == 401


def test_logout_invalidates_the_session(app):
    cookie, csrf = login(app)
    status, _, headers = call(app, "POST", "/api/logout", {}, cookie=cookie, csrf=csrf)
    assert status == 200 and "Max-Age=0" in headers["Set-Cookie"]
    assert call(app, "GET", "/api/state", cookie=cookie)[0] == 401


def test_lockout_after_repeated_failures(app, clock):
    for _ in range(5):
        assert call(app, "POST", "/api/login", {"password": "nope"})[0] == 401
    status, payload, _ = call(app, "POST", "/api/login", {"password": PASSWORD})  # even the right one
    assert status == 429 and "try again" in payload["error"]
    assert call(app, "POST", "/api/login", {"password": PASSWORD}, ip="192.168.1.99")[0] == 200  # another address
    clock.advance(301)
    assert call(app, "POST", "/api/login", {"password": PASSWORD})[0] == 200


# ------------------------------------------------------------------ CSRF and request format
@pytest.mark.parametrize("csrf", [None, "", "wrong-token"])
def test_posts_need_the_csrf_token(app, backend, csrf):
    cookie, _ = login(app)
    status, payload, _ = call(app, "POST", "/api/tag/read", {}, cookie=cookie, csrf=csrf)
    assert status == 403 and "CSRF" in payload["error"] and backend.calls == []


def test_csrf_token_of_another_session_is_rejected(app, backend):
    cookie, _ = login(app)
    _, other_csrf = login(app)
    assert call(app, "POST", "/api/tag/read", {}, cookie=cookie, csrf=other_csrf)[0] == 403


def test_gets_do_not_need_csrf(app):
    cookie, _ = login(app)
    assert call(app, "GET", "/api/state", cookie=cookie)[0] == 200


def test_only_json_is_accepted(app, backend):
    cookie, csrf = login(app)
    for ctype in ("application/x-www-form-urlencoded", "text/plain", None):
        assert call(app, "POST", "/api/tag/read", {}, cookie=cookie, csrf=csrf, content_type=ctype)[0] == 415
    assert call(app, "POST", "/api/login", {"password": PASSWORD}, content_type="text/plain")[0] == 415
    assert backend.calls == []


def test_malformed_bodies(app):
    cookie, csrf = login(app)
    for raw in (b"{not json", b"[1, 2]", b'"text"', b"\xff\xfe"):
        assert call(app, "POST", "/api/tag/write", cookie=cookie, csrf=csrf, raw=raw)[0] == 400


def test_unknown_routes_and_methods(app):
    cookie, csrf = login(app)
    assert call(app, "GET", "/api/nothing", cookie=cookie)[0] == 404
    assert call(app, "GET", "/api/tag/read", cookie=cookie)[0] == 405
    assert call(app, "POST", "/api/state", {}, cookie=cookie, csrf=csrf)[0] == 405
    assert call(app, "DELETE", "/api/state", cookie=cookie)[0] == 405  # known path, wrong method
    assert call(app, "DELETE", "/api/nothing", cookie=cookie)[0] == 404


# ------------------------------------------------------------------ network guards
@pytest.mark.parametrize("path", ["/", "/static/app.js", "/api/session", "/api/login"])
def test_clients_outside_the_local_network_get_nothing(app, path):
    status, payload, _ = call(app, "POST" if path == "/api/login" else "GET", path,
                              {"password": PASSWORD} if path == "/api/login" else None, ip="8.8.8.8")
    assert status == 403 and payload == {"error": "access is limited to the local network"}


def test_allow_public_and_allowed_networks(app):
    assert call(app, "GET", "/api/session", ip="100.64.1.1")[0] == 403
    app.web.allowed_networks = ("100.64.0.0/10",)
    assert call(app, "GET", "/api/session", ip="100.64.1.1")[0] == 200
    app.web.allowed_networks = ()
    app.web.allow_public = True
    assert call(app, "GET", "/api/session", ip="8.8.8.8")[0] == 200


@pytest.mark.parametrize("host", ["evil.example.com", "attacker.com:8443", ""])
def test_unexpected_host_headers_are_refused(app, host):
    assert call(app, "GET", "/api/session", host=host)[0] == 403


@pytest.mark.parametrize("host", ["picontrol.local", "picontrol", "localhost:8443", "192.168.1.5"])
def test_expected_host_headers_are_served(app, host):
    assert call(app, "GET", "/api/session", host=host)[0] == 200


# ------------------------------------------------------------------ static files and headers
def test_static_files_are_served_with_security_headers(app):
    status, html, headers = call(app, "GET", "/")
    assert status == 200 and "Pi Control" in html and headers["Content-Type"].startswith("text/html")
    for name, value in SECURITY_HEADERS.items():
        if name != "Cache-Control":
            assert headers[name] == value
    assert "script-src 'self'" in headers["Content-Security-Policy"] and "unsafe-inline" not in headers["Content-Security-Policy"]
    assert call(app, "GET", "/static/app.js")[2]["Content-Type"].startswith("application/javascript")
    assert call(app, "GET", "/static/style.css")[2]["Content-Type"].startswith("text/css")


@pytest.mark.parametrize("path", ["/static/../config.py", "/static/secret", "/static/", "/index.html", "/../etc/passwd",
                                  "/static/app.js/../../config.py", "/webui/app.js", "/src/picontrol/web.py"])
def test_nothing_else_is_served(app, path):
    assert call(app, "GET", path)[0] in (404, 405)


def test_api_responses_are_not_cached_and_carry_the_headers(app):
    _, _, headers = call(app, "GET", "/api/session")
    assert headers["Cache-Control"] == "no-store" and headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY" and headers["Referrer-Policy"] == "no-referrer"


# ------------------------------------------------------------------ route behaviour
def test_roms_query_parameters(app, backend):
    cookie, _ = login(app)
    assert call(app, "GET", "/api/roms?system=nes&q=mario+kart&offset=10&limit=5", cookie=cookie)[0] == 200
    assert backend.calls == [("roms", "nes", "mario kart", 10, 5)]
    assert call(app, "GET", "/api/roms?system=nes&offset=abc", cookie=cookie)[0] == 400
    assert call(app, "GET", "/api/roms", cookie=cookie)[0] == 200  # missing system: the backend rejects it


def test_tag_routes(app, backend):
    cookie, csrf = login(app)
    kw = dict(cookie=cookie, csrf=csrf)
    assert call(app, "POST", "/api/tag/read", {}, **kw)[1] == {"uid": "01020304"}
    assert call(app, "POST", "/api/tag/write", {"system": "nes", "rom": "Zelda.nes"}, **kw)[0] == 200
    assert call(app, "POST", "/api/tag/write", {"system": "nes"}, **kw)[0] == 400
    assert call(app, "POST", "/api/tag/write", {"system": 1, "rom": ["x"]}, **kw)[0] == 400
    assert call(app, "POST", "/api/tag/write", {"system": "nes", "rom": "boom"}, **kw)[0] == 408  # ApiError status is passed on
    assert call(app, "POST", "/api/tag/write-current", {}, **kw)[0] == 200
    assert ("tag", "write", "nes", "Zelda.nes") in backend.calls and ("tag", "write-current", None, None) in backend.calls


def test_config_routes(app, backend):
    cookie, csrf = login(app)
    kw = dict(cookie=cookie, csrf=csrf)
    assert call(app, "GET", "/api/config", cookie=cookie)[0] == 200
    assert call(app, "POST", "/api/config", {"changes": {"fan.interval": 3}}, **kw)[0] == 200
    assert backend.calls[-1] == ("config", {"fan.interval": 3})


@pytest.mark.parametrize("path, action", [("/api/service/restart", "restart"), ("/api/system/reboot", "reboot"),
                                          ("/api/system/shutdown", "shutdown")])
def test_dangerous_actions_need_explicit_confirmation(app, backend, path, action):
    cookie, csrf = login(app)
    kw = dict(cookie=cookie, csrf=csrf)
    for body in ({}, {"confirm": False}, {"confirm": "yes"}, {"confirm": 1}):
        assert call(app, "POST", path, body, **kw)[0] == 400
    assert backend.calls == []
    assert call(app, "POST", path, {"confirm": True}, **kw)[0] == 202
    assert backend.calls == [(action,)]


def test_log_route(app, backend):
    cookie, _ = login(app)
    assert call(app, "GET", "/api/log?lines=20", cookie=cookie)[1] == {"lines": ["a"]}
    assert call(app, "GET", "/api/log?lines=x", cookie=cookie)[0] == 400


def test_unexpected_errors_do_not_leak_details(app, backend):
    backend.status = lambda: (_ for _ in ()).throw(RuntimeError("secret internals /etc/shadow"))
    cookie, _ = login(app)
    status, payload, _ = call(app, "GET", "/api/state", cookie=cookie)
    assert status == 500 and payload == {"error": "internal error"}


def test_body_limit_constant_is_small():
    assert MAX_BODY <= 65536
