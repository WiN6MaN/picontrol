# Configuration and behaviour

The configuration is a plain INI file: `/etc/picontrol/picontrol.conf` (or the file given with `-c`, or `$PICONTROL_CONFIG`). Every key has a default, so an empty file is valid; unknown sections and keys are rejected so typos do not go unnoticed. The annotated reference is [`config/picontrol.conf`](../../config/picontrol.conf). Changes apply when the service restarts (see [installation](installation.md)).

## Behaviour

### Power switch

| You do | The service does |
|---|---|
| Flip the switch **OFF** (and keep it off longer than `debounce`) | Blinks the LED, asks RetroArch to quit (so it saves), waits `quit_grace` seconds, turns the LED off, runs `shutdown_command` |
| Flip it back **ON** after the Pi has halted | Nothing in software: closing the switch pulls GPIO3 low, which wakes the Pi |

The switch position is authoritative: if the Pi boots with the switch OFF, it shuts down again.

### Reset button

| You do | The service does |
|---|---|
| Short press | Sends `RESET` to RetroArch (resets the running game) |
| Hold for `long_press` seconds | Writes the running game to the next tag you present (see [NFC tags](nfc-tags.md)) |

Reset and quit use RetroArch's network commands, so they only affect RetroArch-based emulators.

### Fan

On at `threshold_on` °C, off at `threshold_off` °C, and never off before it has run `min_run` seconds. If the temperature cannot be read three times in a row - or the controller stops for any reason - the fan is switched **on**: a spinning fan is harmless, a hot Pi is not.

### NFC

Presenting a tag launches its game once. Leaving it in place does nothing (the game is not relaunched when it ends). A tag counts as removed after it has been absent for `remove_delay` seconds; presenting it again launches again. Details in [NFC tags](nfc-tags.md).

### LED

| Pattern | Meaning |
|---|---|
| Steady on | The service is running |
| One short blink | Reset button pressed |
| Three fast blinks | Long press recognised: present a tag |
| Three slow blinks | Tag written and verified |
| Six very fast blinks | Error (nothing to write, no tag in time, write failed) |
| Three medium blinks, then off | Shutting down |

## Settings

| Section | Key | Default | Meaning |
|---|---|---|---|
| `[pins]` | `power`, `reset`, `led`, `fan`, `nfc_sclk`, `nfc_miso`, `nfc_mosi`, `nfc_cs` | 3, 23, 14, 18, 4, 17, 27, 22 | BCM pin numbers; each signal needs its own |
| `[power]` | `enabled` | `true` | |
| | `off_level` | `high` | Level meaning "switch OFF" (`high` or `low`) |
| | `debounce` | `0.3` | Seconds the switch must stay OFF |
| | `quit_grace` | `1.5` | Seconds given to RetroArch before shutdown |
| | `shutdown_command` | `sudo -n shutdown -h now` | Run as the RetroPie user |
| `[reset]` | `long_press` | `2.0` | Seconds for a long press |
| `[fan]` | `threshold_on` / `threshold_off` | `60` / `50` | °C; `on` must exceed `off` |
| | `interval`, `min_run` | `5`, `20` | Seconds between readings; minimum run time |
| | `temp_path` | `/sys/class/thermal/thermal_zone0/temp` | Kernel temperature file |
| `[nfc]` | `poll_interval`, `poll_interval_game` | `0.5`, `1.0` | Seconds between polls (idle / game running) |
| | `remove_delay` | `2.0` | Absence needed to count as removed |
| | `launch_at_start` | `true` | Launch the tag already present at start-up |
| | `quit_on_remove` | `false` | Quit the game when its tag is removed |
| | `rf_reset_each_poll` | `true` | Cut the RF field before each poll (see [architecture](architecture.md)) |
| | `write_timeout` | `15` | Seconds to present a tag after a long press |
| `[paths]` | `roms_dir`, `runcommand`, `retroarch_cfg`, `emulationstation_command`, `extra_emulators` | RetroPie defaults | Where things live |
| `[retroarch]` | `host`, `port` | `127.0.0.1`, `55355` | Must match `network_cmd_port` |
| `[logging]` | `file`, `level` | `/var/log/picontrol.log`, `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

Every component has an `enabled` switch: for example, `[nfc] enabled = false` runs the buttons and fan without NFC.

## Commands

```
picontrol run [--dry-run]           # the service; --dry-run logs instead of acting
picontrol tag read                  # show the tag in the field
picontrol tag write nes "Super Mario Bros.nes"
picontrol tag write --current       # write the game that is running now
picontrol test led|fan|buttons|nfc  # hardware tests
picontrol doctor                    # check the installation
picontrol --debug ...               # verbose log on the terminal
```
