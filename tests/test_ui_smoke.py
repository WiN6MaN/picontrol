"""Runs the browser-level smoke test (tests/ui) when Node.js and jsdom are available."""

import os
import shutil
import socket
import subprocess
import sys

import pytest

UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")

pytestmark = pytest.mark.skipif(
    not shutil.which("node") or not os.path.isdir(os.path.join(UI, "node_modules", "jsdom")),
    reason="needs Node.js and 'npm install' in tests/ui")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_web_interface_in_a_browser_like_environment():
    env = dict(os.environ, PORT=str(free_port()))
    server = subprocess.Popen([sys.executable, os.path.join(UI, "serve.py")], env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, universal_newlines=True)
    try:
        seen = []
        for _ in range(100):  # log lines may come first
            line = server.stdout.readline().strip()
            seen.append(line)
            if line == "READY" or not line:
                break
        assert "READY" in seen, "\n".join(seen)
        result = subprocess.run(["node", "ui.test.js"], cwd=UI, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, timeout=120)
        assert result.returncode == 0, result.stdout
        assert "UI SMOKE TEST PASSED" in result.stdout
    finally:
        server.kill()
        server.wait(10)
