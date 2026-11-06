import os
import stat

import pytest

from conftest import FakeClock
from picontrol import webauth
from picontrol.config import Config
from picontrol.errors import ConfigError


def web(**overrides):
    cfg = Config.defaults().web
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


# ------------------------------------------------------------------ passwords
def test_password_round_trip():
    stored = webauth.hash_password("correct horse", iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert webauth.verify_password("correct horse", stored)
    assert not webauth.verify_password("wrong", stored)
    assert not webauth.verify_password("", stored)


def test_salts_differ_and_plaintext_is_not_stored():
    first, second = webauth.hash_password("same password", 1000), webauth.hash_password("same password", 1000)
    assert first != second and "same password" not in first


@pytest.mark.parametrize("bad", ["", "garbage", "pbkdf2_sha256$x$y$z", "md5$1$a$b", "pbkdf2_sha256$1000$!!$!!", None])
def test_malformed_hashes_never_verify(bad):
    assert not webauth.verify_password("anything", bad)


def test_save_and_load_password(tmp_path):
    path = str(tmp_path / "sub" / "web.passwd")
    webauth.save_password(path, "long enough password")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert webauth.verify_password("long enough password", webauth.load_password(path))
    assert webauth.load_password(str(tmp_path / "missing")) is None


def test_short_passwords_are_refused(tmp_path):
    with pytest.raises(ConfigError):
        webauth.save_password(str(tmp_path / "pw"), "short")
    assert not (tmp_path / "pw").exists()


# ------------------------------------------------------------------ sessions
def test_session_lifecycle_and_idle_timeout():
    clock = FakeClock()
    store = webauth.SessionStore(100, clock)
    token, csrf = store.create()
    assert store.get(token)["csrf"] == csrf
    clock.advance(60)
    assert store.get(token)  # activity renews the session
    clock.advance(60)
    assert store.get(token)
    clock.advance(101)
    assert store.get(token) is None  # idle too long
    assert store.get("unknown") is None and store.get(None) is None and store.get("") is None


def test_logout_removes_the_session():
    store = webauth.SessionStore(100, FakeClock())
    token, _ = store.create()
    store.delete(token)
    assert store.get(token) is None


def test_tokens_are_unique_and_long():
    store = webauth.SessionStore(100, FakeClock())
    tokens = {store.create()[0] for _ in range(50)}
    assert len(tokens) == 50 and all(len(t) >= 40 for t in tokens)


# ------------------------------------------------------------------ login limiter
def test_lockout_after_too_many_failures_then_release():
    clock = FakeClock()
    limiter = webauth.LoginLimiter(3, 300, clock)
    for _ in range(2):
        limiter.failed("192.168.1.9")
    assert limiter.locked_for("192.168.1.9") == 0
    limiter.failed("192.168.1.9")
    assert 0 < limiter.locked_for("192.168.1.9") <= 300
    assert limiter.locked_for("192.168.1.10") == 0  # another address is unaffected
    clock.advance(301)
    assert limiter.locked_for("192.168.1.9") == 0


def test_success_clears_the_failure_count():
    limiter = webauth.LoginLimiter(2, 300, FakeClock())
    limiter.failed("a")
    limiter.succeeded("a")
    limiter.failed("a")
    assert limiter.locked_for("a") == 0


# ------------------------------------------------------------------ network guards
@pytest.mark.parametrize("address", ["192.168.1.5", "10.0.0.2", "172.16.5.4", "127.0.0.1", "::1", "fe80::1",
                                     "::ffff:192.168.1.5", "169.254.1.1"])
def test_local_clients_are_allowed(address):
    assert webauth.client_allowed(address, web())


@pytest.mark.parametrize("address", ["8.8.8.8", "172.32.0.1", "2606:4700::1111", "::ffff:8.8.8.8", "not-an-ip", ""])
def test_public_or_invalid_clients_are_refused(address):
    assert not webauth.client_allowed(address, web())


def test_allowed_networks_and_allow_public():
    assert webauth.client_allowed("100.64.1.1", web(allowed_networks=("100.64.0.0/10",)))
    assert not webauth.client_allowed("100.128.1.1", web(allowed_networks=("100.64.0.0/10",)))
    assert not webauth.client_allowed("8.8.8.8", web(allowed_networks=("2001:db8::/32",)))  # no crash on mixed versions
    assert webauth.client_allowed("8.8.8.8", web(allow_public=True))


@pytest.mark.parametrize("host", ["192.168.1.5:8443", "[::1]:8443", "localhost", "localhost:8443", "picontrol",
                                  "PiControl.local", "anything.local:80", "10.0.0.2"])
def test_expected_host_headers_are_accepted(host):
    assert webauth.host_allowed(host, web(), "picontrol")


@pytest.mark.parametrize("host", ["", "evil.example.com", "attacker.com:8443", "192.168.1.5.evil.com", "picontrol.example.com"])
def test_unexpected_host_headers_are_refused(host):
    assert not webauth.host_allowed(host, web(), "picontrol")


def test_extra_allowed_hosts():
    assert webauth.host_allowed("pi.lan", web(allowed_hosts=("Pi.LAN",)), "picontrol")
