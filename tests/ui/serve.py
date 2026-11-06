"""Starts the real web interface on fake hardware (PN532 simulator) for the browser-level smoke test.

Usage: PORT=8765 python3 tests/ui/serve.py   (prints READY once it listens)
"""
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, os.path.join(HERE, ".."))
from fakes import Card, FakeGpio, FakePopen, FakeProcs, PN532Sim
from picontrol import webauth
from picontrol.config import Config
from picontrol.pn532 import PN532
from picontrol.service import Service
from picontrol.web import WebServer
from picontrol.webbackend import Backend

tmp = tempfile.mkdtemp()
cfg = Config.defaults()
for system, names in {"nes": ["Super Mario Bros.nes", "Zelda II.nes", "Metroid.nes"], "snes": ["Chrono Trigger.sfc"]}.items():
    os.makedirs(os.path.join(tmp, "roms", system))
    for name in names:
        open(os.path.join(tmp, "roms", system, name), "w").close()
cfg.paths.roms_dir = os.path.join(tmp, "roms")
cfg.nfc.lock_file = os.path.join(tmp, "lock")
cfg.nfc.poll_interval = cfg.nfc.poll_interval_game = 0.05
cfg.nfc.write_timeout = 10
cfg.logging.file = os.path.join(tmp, "picontrol.log")
open(cfg.logging.file, "w").write("2026-11-04 10:00:00 INFO    picontrol.service: picontrol running\n")
cfg.fan.temp_path = os.path.join(tmp, "temp"); open(cfg.fan.temp_path, "w").write("47500")
cfg.web.enabled, cfg.web.tls, cfg.web.host = True, False, "127.0.0.1"
cfg.web.port = int(os.environ.get("PORT", "8765"))
cfg.web.password_file = os.path.join(tmp, "web.passwd")
open(cfg.web.password_file, "w").write(webauth.hash_password("correct horse battery", iterations=1000) + "\n")
cfg.source = os.path.join(tmp, "picontrol.conf"); open(cfg.source, "w").write("[fan]\n; kept\nthreshold_on = 60.0\n")

sim = PN532Sim(); gpio = FakeGpio(sim)
reader = PN532(gpio, cs=22, sclk=4, mosi=27, miso=17, wake_delay=0, sleep=lambda s: None)
service = Service(cfg, gpio=gpio, popen=FakePopen, procs=FakeProcs(), reader=reader, sleep=lambda s: None,
                  run_command=lambda c: 0)
gpio.levels[cfg.pins.power] = 0
sim.place(Card([1, 2, 3, 4]))
stop = threading.Event()
threading.Thread(target=service.nfc.run, args=(stop,), daemon=True).start()
web = WebServer(cfg, Backend(service)); web.start()
print("READY", flush=True)
while not stop.wait(0.5):
    if service.restart_requested:
        break
