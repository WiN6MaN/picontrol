# Pi Control

**Power and reset buttons, fan, LED and NFC game cartridges for a RetroPie console built on the Pi Control board.**
A clean, documented and tested rewrite.

🇫🇷 [Lire en français](README.fr.md)

Present an NFC "cartridge" and its game starts. Flip the power switch and the console saves and shuts down cleanly. Press reset to restart the game; hold it to write the game you are playing to a new cartridge. The fan keeps the Pi cool. One small Python 3 program does all of it.

## Features

- **Power switch** - graceful shutdown: RetroArch is asked to quit (and save) before the Pi powers off.
- **Reset button** - short press resets the game, long press writes the running game to the next NFC tag.
- **NFC cartridges** - live tag detection (PN532 over software SPI), compatible with tags written by the original Pi Control.
- **Fan** - temperature hysteresis with a minimum run time, and a fail-safe: fan ON if the temperature cannot be read.
- **LED** - driven straight from its GPIO (no serial port, no `config.txt` change).
- **Web interface (optional)** - status, NFC tags with game search, settings, restart/shutdown, from any device on your local network. Off by default, no default password, refuses anything from outside your network.
- **Robust by design** - supervised worker threads (a crash in one cannot stop the power switch), a single owner for the NFC reader, timeouts everywhere, automatic reader recovery.
- **Safe by design** - tag content is untrusted input: validated, never passed to a shell. No listening socket unless you turn the optional web interface on.
- **Operable** - `picontrol doctor`, `picontrol test led|fan|buttons|nfc`, a dry-run mode, an idempotent installer with backups, one annotated configuration file.
- **Tested** - 350+ tests against a PN532 / MIFARE hardware simulator, on Python 3.7 to 3.12 (3.7 is what RetroPie 4.8 ships), plus a browser-level test of the web page.

## Status

**Alpha (0.1.0).** The whole stack is tested against a simulator of the PN532 and of a MIFARE Classic tag, but it has **not yet been validated on real hardware**. Run `picontrol doctor` and `picontrol test ...` after installing, and please report what you observe. See [architecture](docs/en/architecture.md) for the known limits.

## Quick start

On a Raspberry Pi 3B with **RetroPie 4.8** and the Pi Control board assembled:

```
git clone https://github.com/<you>/picontrol.git
cd picontrol
sudo ./install.sh --dry-run    # see what would change
sudo ./install.sh
picontrol doctor
picontrol test buttons         # then: led, fan, nfc
sudo reboot
```

Write a cartridge:

```
picontrol tag write nes "Super Mario Bros.nes"    # then present the tag
picontrol web set-password                        # optional web interface: see docs/en/web.md
```

## Documentation

| | |
|---|---|
| [Hardware](docs/en/hardware.md) | Board, pin map, PN532 module, wiring tests |
| [Installation](docs/en/installation.md) | Install, upgrade, uninstall, migrating from the original, faster EmulationStation |
| [Web interface](docs/en/web.md) | Turning it on, what it does, security model, API |
| [Configuration](docs/en/configuration.md) | Behaviour, LED patterns, every setting, commands |
| [NFC tags](docs/en/nfc-tags.md) | Writing/reading tags, format, compatibility |
| [Architecture](docs/en/architecture.md) | Design decisions, modules, testing strategy, limits |
| [Troubleshooting](docs/en/troubleshooting.md) | Symptoms, causes, fixes |
| [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) | |

## How it differs from the original

This project is inspired by the original Pi Control software but shares none of its code.

| Original | Here |
|---|---|
| Python 2 scripts, several processes | One Python 3.7+ program, supervised threads |
| Buttons and web server both talk to the NFC reader | A single owner for the reader, plus an inter-process lock for the CLI |
| NFC read only at boot, on reset, or when the switch is cycled | Live detection |
| Web interface with a default password | Optional web interface: off by default, no default password, local network only, hardened (see [security](SECURITY.md)) |
| Game names built into shell commands | Validated names, argument lists, no shell |
| A capital `Q` in a game name truncated the tag record | Records decoded by length |
| `runcommand` hooks stop EmulationStation for every game | No hooks: only tag launches restart EmulationStation |
| Serial port enabled to light the LED | LED on its GPIO |
| No automated tests in the package | 350+ tests with a hardware simulator, plus a browser-level test |

## Repository layout

```
src/picontrol/   the program          tests/    pytest suite and hardware simulator
config/          annotated example    docs/     documentation (en/, fr/)
install.sh, uninstall.sh, scripts/    installer
```

## Credits

The Pi Control board and its original software are by Evan Wright and Jared Kirchgatter ([jetekteam/picontrol](https://github.com/jetekteam/picontrol)); the case design is by "Daft Mike". This rewrite keeps the board's pin assignments and the on-tag format so that existing hardware and tags keep working. The PN532 protocol is implemented from NXP's public documentation (UM0701-02), informed by the MIT-licensed Adafruit PN532 libraries.

## License

[MIT](LICENSE)
