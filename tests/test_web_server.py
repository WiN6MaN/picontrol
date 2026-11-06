"""The real HTTP(S) server on an ephemeral port, and the whole stack end to end."""

import http.client
import json
import shutil
import ssl
import threading
import time

import pytest

from fakes import Card
from picontrol import tagstore, webauth
from picontrol.errors import ConfigError
from picontrol.web import WebServer
from picontrol.webbackend import Backend

PASSWORD = "correct horse battery"


@pytest.fixture
def web_cfg(cfg, tmp_path):
    cfg.web.enabled, cfg.web.tls = True, False
    cfg.web.host, cfg.web.port = "127.0.0.1", 0
    cfg.web.password_file = str(tmp_path / "web.passwd")
    cfg.web.cert_file, cfg.web.key_file = str(tmp_path / "web.crt"), str(tmp_path / "web.key")
    with open(cfg.web.password_file, "w") as handle:
        handle.write(webauth.hash_password(PASSWORD, iterations=1000) + "\n")
    cfg.source = str(tmp_path / "picontrol.conf")
    (tmp_path / "picontrol.conf").write_text("[fan]\nthreshold_on = 60.0\n")
    return cfg


@pytest.fixture
def server(web_cfg, service):
    srv = WebServer(web_cfg, Backend(service))
    srv.start()
    yield srv
    srv.stop()


class Client:
    def __init__(self, server, tls=False):
        self.port, self.tls, self.cookie, self.csrf = server.port, tls, None, None

    def request(self, method, path, body=None, headers=None, raw=None):
        if self.tls:
            conn = http.client.HTTPSConnection("127.0.0.1", self.port, context=ssl._create_unverified_context(), timeout=10)
        else:
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        head = dict(headers or {})
        if body is not None or raw is not None:
            head.setdefault("Content-Type", "application/json")
        if self.cookie:
            head["Cookie"] = self.cookie
        if self.csrf and method == "POST":
            head["X-CSRF-Token"] = self.csrf
        data = raw if raw is not None else (json.dumps(body) if body is not None else None)
        conn.request(method, path, body=data, headers=head)
        response = conn.getresponse()
        text = response.read().decode()
        conn.close()
        try:
            return response.status, json.loads(text), response
        except ValueError:
            return response.status, text, response

    def login(self):
        status, payload, response = self.request("POST", "/api/login", {"password": PASSWORD})
        assert status == 200
        self.cookie, self.csrf = response.getheader("Set-Cookie").split(";")[0], payload["csrf"]
        return self


def test_serves_the_page_and_requires_login(server):
    client = Client(server)
    status, html, response = client.request("GET", "/")
    assert status == 200 and "Pi Control" in html and "default-src 'self'" in response.getheader("Content-Security-Policy")
    assert client.request("GET", "/api/state")[0] == 401
    assert client.request("GET", "/api/state")[2].getheader("Server") == "picontrol"  # no version details


def test_state_after_login(server):
    client = Client(server).login()
    status, state, _ = client.request("GET", "/api/state")
    assert status == 200 and state["nfc"]["enabled"] and state["fan"]["enabled"]


def test_oversized_body_is_refused_before_reading_it(server):
    client = Client(server)
    status, payload, _ = client.request("POST", "/api/login", raw="x" * 70000, headers={"Content-Type": "application/json"})
    assert status == 413


def test_invalid_content_length(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.putrequest("POST", "/api/login")
    conn.putheader("Content-Length", "abc")
    conn.endheaders()
    assert conn.getresponse().status == 400


def test_foreign_host_header_is_refused_over_real_http(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/api/session", headers={"Host": "evil.example.com"})
    assert conn.getresponse().status == 403


def test_server_refuses_to_start_without_a_password(web_cfg, service, tmp_path):
    web_cfg.web.password_file = str(tmp_path / "absent")
    with pytest.raises(ConfigError, match="set-password"):
        WebServer(web_cfg, Backend(service))


def test_service_keeps_running_when_the_web_part_cannot_start(web_cfg, gpio, reader, procs):
    from fakes import FakePopen
    from picontrol.service import Service
    web_cfg.web.password_file = "/nonexistent/web.passwd"
    service = Service(web_cfg, gpio=gpio, popen=FakePopen, procs=procs, reader=reader)
    assert service.web is None and service.nfc is not None  # the console works; the error is only logged


def test_service_builds_the_web_server_when_configured(web_cfg, gpio, reader, procs):
    from fakes import FakePopen
    from picontrol.service import Service
    assert isinstance(Service(web_cfg, gpio=gpio, popen=FakePopen, procs=procs, reader=reader).web, WebServer)


def test_server_runs_as_a_worker_and_stops_with_the_event(web_cfg, service):
    srv = WebServer(web_cfg, Backend(service))
    stop = threading.Event()
    thread = threading.Thread(target=srv.run, args=(stop,))
    thread.start()
    end = time.monotonic() + 5
    while srv.port is None and time.monotonic() < end:
        time.sleep(0.02)
    assert Client(srv).request("GET", "/")[0] == 200
    stop.set()
    thread.join(5)
    assert not thread.is_alive() and srv.httpd is None


# ------------------------------------------------------------------ end to end: HTTP -> backend -> NFC thread -> simulator
@pytest.fixture
def running_nfc(service):
    stop = threading.Event()
    thread = threading.Thread(target=service.nfc.run, args=(stop,))
    thread.start()
    yield
    stop.set()
    thread.join(5)


def test_write_and_read_a_tag_through_the_web_api(server, running_nfc, sim, cfg, service):
    sim.place(Card([1, 2, 3, 4]))
    client = Client(server).login()
    status, payload, _ = client.request("POST", "/api/tag/write", {"system": "nes", "rom": "Zelda II.nes"})
    assert status == 200 and payload == {"uid": "01020304", "system": "nes", "rom": "Zelda II.nes"}
    sim.card_state = "idle"
    assert tagstore.read_records(service.nfc.reader, service.nfc.reader.read_uid()) == ["nes", "Zelda II.nes"]
    sim.card_state = "idle"
    assert client.request("POST", "/api/tag/read", {})[1]["records"] == ["nes", "Zelda II.nes"]
    status, payload, _ = client.request("POST", "/api/tag/write", {"system": "nes", "rom": "../../etc/passwd"})
    assert status == 400
    assert sim.card.trailers_intact()


def test_browse_roms_through_the_api(server, cfg):
    client = Client(server).login()
    systems = client.request("GET", "/api/systems")[1]["systems"]
    assert {"name": "nes", "count": 2} in systems
    assert client.request("GET", "/api/roms?system=nes&q=zelda")[1]["items"] == ["Zelda II.nes"]
    assert client.request("GET", "/api/roms?system=..%2F..")[0] == 400


def test_save_settings_then_restart_through_the_api(server, service, web_cfg):
    client = Client(server).login()
    assert client.request("POST", "/api/config", {"changes": {"fan.threshold_on": 66}})[1]["restart_required"]
    assert "66.0" in open(web_cfg.source).read()
    assert client.request("POST", "/api/config", {"changes": {"power.shutdown_command": "touch /tmp/pwned"}})[0] == 400
    assert "pwned" not in open(web_cfg.source).read()
    assert client.request("GET", "/api/state")[1]["restart_required"] is True
    assert client.request("POST", "/api/service/restart", {})[0] == 400  # needs the explicit confirmation


@pytest.mark.skipif(not shutil.which("openssl"), reason="openssl is needed to create the certificate")
def test_https_with_a_self_signed_certificate(web_cfg, service, tmp_path):
    web_cfg.web.tls = True
    srv = WebServer(web_cfg, Backend(service))
    srv.start()
    try:
        client = Client(srv, tls=True)
        assert client.request("GET", "/")[0] == 200
        status, payload, response = client.request("POST", "/api/login", {"password": PASSWORD})
        assert status == 200 and "Secure" in response.getheader("Set-Cookie")
        import os
        assert oct(os.stat(web_cfg.web.key_file).st_mode & 0o777) == "0o600"
        with pytest.raises((http.client.HTTPException, ConnectionError, OSError)):  # plain HTTP on the TLS port fails
            plain = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=3)
            plain.request("GET", "/")
            plain.getresponse().read()
        assert srv.httpd is not None
    finally:
        srv.stop()
