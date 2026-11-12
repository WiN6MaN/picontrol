# Architecture

## One process, several supervised threads

```
 picontrol run   (one process, started from autostart.sh as the RetroPie user)
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │ buttons thread ── power switch (GPIO3) ──► graceful shutdown                    │
 │                └─ reset button (GPIO23) ─► RESET │ write-current-game request   │
 │ fan thread ────── /sys thermal ──► hysteresis ──► fan MOSFET (GPIO18)          │
 │ nfc thread ────── PN532 (GPIO 4/17/27/22) ──► tag ──► Launcher ──► runcommand  │
 │ web thread ────── HTTPS, local network only (optional) ──► Backend ──► the above │
 │ LED (shared, locked) ◄── every component                                       │
 └────────────────────────────────────────────────────────────────────────────────┘
```

Each worker thread is supervised on its own: an exception is logged and the worker restarts with a growing delay while the others keep running. **A bug in the NFC code cannot stop the power switch.** (A test enforces this.)

## Modules (`src/picontrol/`)

| Module | Responsibility |
|---|---|
| `config.py` | INI loading, defaults, strict validation |
| `gpio.py` | Thin `RPi.GPIO` wrapper (imported lazily, so everything is testable off-Pi) |
| `pn532.py` | PN532 driver: software SPI, frames, checksums, MIFARE auth/read/write, NTAG page write |
| `tagformat.py` | Pure encode/decode of the on-tag container |
| `tagstore.py` | Reading/writing records on MIFARE Classic 1K and NTAG/Ultralight tags (family detected automatically) |
| `nfc.py` | The tag state machine, write requests, the supervised polling loop |
| `launcher.py` | ROM validation, stopping/starting games and EmulationStation |
| `buttons.py`, `fan.py`, `led.py` | Small state machines driven by an injected clock |
| `retroarch.py` | RetroArch UDP network commands |
| `web.py`, `webauth.py` | Web server (standard library), request logic, passwords, sessions, network guards |
| `webbackend.py`, `configedit.py` | What the web interface can see and do; safe editing of the configuration file |
| `webui/` | The page itself: HTML, CSS and JavaScript, no framework, no inline code |
| `service.py` | Wiring, worker supervision, shutdown sequence |
| `cli.py`, `doctor.py`, `hwtest.py` | Command line, self-check, hardware tests |

## Design decisions

- **Software SPI.** The board wires the PN532 to ordinary GPIOs. The bus is generated in Python (mode 0, LSB first).
- **Started from `autostart.sh`, not systemd.** Launching a game must happen inside RetroPie's console session (tty, display, input). A restart loop around the command gives crash recovery.
- **One owner for the reader.** The original program let several processes (buttons, web server) talk to the PN532 at once, and interleaved frames corrupt each other. Here the NFC thread is the only owner; the `picontrol tag` commands take an inter-process file lock (`ReaderLock`) that the service honours between polls.
- **Every wait has a timeout, every failure is an exception.** The driver never returns `None` to signal an error. After three consecutive reader errors the service re-initialises the chip completely (abort pending command, wake, firmware check, configure).
- **Finite activation retries.** At start-up the chip is told to try once per poll, so `InListPassiveTarget` returns quickly with zero targets instead of staying busy.
- **RF reset before each poll** (`rf_reset_each_poll`). A tag that has been selected may not answer a second detection request; cutting the field first makes every poll see the tag "fresh". The simulator models that worst case. Disable it only if your hardware proves it unnecessary.
- **Debounced presence.** A tag is "removed" only after `remove_delay` seconds without detection, so a tag at the edge of the field does not cause relaunches.
- **LED on its GPIO.** No serial port and no change to `config.txt` (see [hardware](hardware.md)).
- **Fail-safes.** Fan on when the temperature is unreadable or the controller stops; no shutdown if the command fails (the switch re-arms); nothing is launched while shutting down.
- **Small network surface, off by default.** Without the web interface there is no listening socket at all (only UDP to RetroArch on localhost). The optional web interface is built on the standard library, hardened and restricted to the local network: see [web interface](web.md).
- **Tag operations are jobs.** The web interface and the reset button ask the NFC thread to read or write a tag and wait for the answer; the thread stays the single owner of the reader.

## Testing strategy

The test-suite (more than 350 tests, pytest) exercises the whole stack against a **simulator** of the PN532 and MIFARE Classic and NTAG tags wired to the same software-SPI pins: bit-banged transfers, frames and checksums, ACK/response, authentication, block read/write, injected faults (silent chip, corrupted answers). The installer is run for real in a sandbox, and the web page is driven in a browser-like environment (jsdom) against the real server on fake hardware - which caught a bug no Python test could see. Buttons and fan are driven by an injected clock, so no test waits in real time.

The simulator reproduces the protocol as the original driver used it, but it is not the real chip: hardware validation remains the final step, which is why `picontrol test` and `picontrol doctor` exist.

## Known limits

- A tag launch stops and restarts EmulationStation (inherent to launching from outside).
- Reset and quit only affect RetroArch-based emulators.
- MIFARE Classic 1K and NTAG/Ultralight tags only; 254 bytes of message per tag.
- The power switch has one behaviour (immediate graceful shutdown). The original's "soft power" mode (switch off and on again within seconds to reload) is not implemented.
