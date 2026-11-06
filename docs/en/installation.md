# Installation

## Requirements

- A Raspberry Pi 3B (or similar) with the Pi Control board assembled and tested.
- **RetroPie 4.8** installed from the official image (it is based on Raspberry Pi OS Buster, which provides Python 3.7), with RetroPie updated. The installer needs Python 3.7 or newer.
- Network access (Ethernet is simplest), and `sudo` rights - the default `pi` user has them.

## Install

```
git clone https://github.com/<you>/picontrol.git
cd picontrol
sudo ./install.sh --dry-run      # shows exactly what would change
sudo ./install.sh
picontrol doctor                 # checks the installation
picontrol test buttons           # then: led, fan, nfc (see hardware.md)
sudo reboot
```

If `git` is missing: `sudo apt install git`. The installer is **idempotent**: running it again updates the code and never overwrites your configuration.

### What the installer changes

| What | Where | Notes |
|---|---|---|
| Code | `/opt/picontrol/lib/picontrol` | Replaced on each install |
| Launcher | `/usr/local/bin/picontrol` | Small shell wrapper |
| Configuration | `/etc/picontrol/picontrol.conf` | Created once; new defaults land in `picontrol.conf.dist`. The folder belongs to the RetroPie user so the web interface can save settings |
| Log file | `/var/log/picontrol.log` | Owned by the RetroPie user; rotated at 200 kB |
| Dependency | `python3-rpi.gpio` | Installed with `apt` only if missing |
| RetroArch | `/opt/retropie/configs/all/retroarch.cfg` | Sets `network_cmd_enable = "true"` and the port, after saving a copy as `retroarch.cfg.picontrol-bak` |
| Start-up | `/opt/retropie/configs/all/autostart.sh` | Adds one marked block **before** the `emulationstation` line (copy saved as `autostart.sh.picontrol-bak`) |

Options: `--dry-run`, `--skip-deps`, `--no-retroarch-config`, `--no-autostart`, `--user NAME`.

### Optional: the web interface

It is off by default. To turn it on, see [web interface](web.md) (`picontrol web set-password`, then `enabled = true` in the `[web]` section).

### Manual start-up (if you used `--no-autostart`)

Add this to `/opt/retropie/configs/all/autostart.sh`, **before** the `emulationstation` line (that line blocks, so anything after it would never run):

```
(while true; do /usr/local/bin/picontrol run; sleep 3; done) &
```

The loop restarts the service if it ever exits. To apply a configuration change without rebooting: `pkill -f "python3 -m picontrol run"` - the loop starts it again three seconds later.

## Coming from the original Pi Control (or a hand-modified install)

Start from a clean RetroPie image if you can. Otherwise remove the old pieces first, so two programs do not fight over the same pins:

1. In `/etc/rc.local`, delete the lines that start `shutdown.py`, `reset.py` and `picontrol_fan.py` (or the original `picontrol.py`).
2. In `/opt/retropie/configs/all/autostart.sh`, delete any line that starts the original `picontrol.py`.
3. Remove the original hooks **if** they came from the original installer (check their content first): `/opt/retropie/configs/all/runcommand-onstart.sh` and `runcommand-onend.sh`. They stop EmulationStation for every game.
4. Delete the old folder (`/home/pi/RetroPie/nescontrol` or `picontrol`).
5. The serial-port trick for the LED is no longer needed. If you enabled the serial port only for the LED, you can disable it again (this also restores the core clock).

**Your existing tags keep working**: the on-tag format is unchanged (see [NFC tags](nfc-tags.md)).

## Upgrade and uninstall

```
cd picontrol && git pull && sudo ./install.sh     # upgrade
sudo ./uninstall.sh                               # remove code, launcher and the start-up block
sudo ./uninstall.sh --purge                       # ...and the configuration and log
```

`uninstall.sh` leaves `retroarch.cfg` alone (a backup, `retroarch.cfg.picontrol-bak`, exists).

## Faster EmulationStation

A game started by a tag stops EmulationStation and restarts it when the game ends (see [architecture](architecture.md) for why). With thousands of games, make that restart faster:

- Enable **Parse Gamelists Only** (EmulationStation menu, *Other settings*, or `ParseGamelistOnly` set to `true` in `es_settings.cfg`). Only games listed in a `gamelist.xml` are then shown, so make sure your lists are complete first.
- Turn off the automatic **Last Played** collection if you do not use it.
- Leave *Threaded loading* off: it is reported to cause crashes.
