# Troubleshooting

Start with the two tools that answer most questions:

```
picontrol doctor          # checks the installation (nothing touches the hardware)
tail -n 50 /var/log/picontrol.log
picontrol --debug run     # run in the foreground with a verbose log (stop the service first, see below)
```

To stop the running service while you experiment: `pkill -f "python3 -m picontrol run"`, then press `Ctrl+C` in your foreground run. (The start-up loop restarts the service three seconds after you stop it.)

| Symptom | Likely cause | What to do |
|---|---|---|
| `doctor`: RPi.GPIO missing | Dependency not installed | `sudo apt install python3-rpi.gpio` |
| `doctor`: RetroArch network commands | `network_cmd_enable` is off | Re-run `sudo ./install.sh`, or set `network_cmd_enable = "true"` in `retroarch.cfg` |
| LED never lights | Service not running, wrong pin, LED polarity | `picontrol test led`; check `[pins] led`; check the log |
| Fan never starts | Pin, MOSFET wiring, or the Pi is simply cool | `picontrol test fan`; compare `cat /sys/class/thermal/thermal_zone0/temp` (in m°C) with `threshold_on` |
| Fan always on | Temperature unreadable (fail-safe) or threshold too low | Log line "Temperature unreadable"; check `temp_path` |
| Switch OFF does not shut down | `sudo` needs a password, or levels reversed | `doctor` (passwordless sudo); `picontrol test buttons` shows `ON/OFF`; if it is inverted set `[power] off_level = low` |
| Pi shuts down right after boot | The switch was OFF when the Pi started | Flip it ON first; this is deliberate |
| Reset does nothing | The game is not a RetroArch core, or network commands are off | `doctor`; try a RetroArch-based system |
| `picontrol test nfc`: PN532 not found | Mode switches not on SPI, loose cable, wrong pins, clone module | Set the switches to SPI **and power-cycle**; check the 6-pin cable and `[pins]` |
| "authentication refused - foreign tag" | The tag has non-default keys | Use a tag that is blank or written by Pi Control |
| Tag detected but "ignored" | Blank tag, NTAG, or invalid content | The log says why; `picontrol tag read` |
| "ROM not found" | System or file name does not match the ROM folder | Names are case-sensitive: `picontrol tag read` then compare with `ls ~/RetroPie/roms/<system>` |
| Game launches twice or keeps relaunching | Tag at the edge of the field, flickering | Seat the tag properly; raise `remove_delay`; send a `--debug` log if it persists |
| "The reader is busy" | Another command or the service holds the reader | Retry; commands wait up to 20 s |
| Random NFC errors | Long or loose wires, module not in SPI mode, supply noise | `picontrol --debug run`; check wiring and the supply |
| Returning from a tag game is slow | EmulationStation reloads its lists | See [installation](installation.md#faster-emulationstation) |
| The web page does not load | Web interface off, no password, wrong address or port | `picontrol doctor`; check `[web] enabled`; the log gives the address (`tail /var/log/picontrol.log`) |
| The browser warns about the certificate | Self-signed certificate | Expected: compare the fingerprint with the one in the log, then accept |
| "access is limited to the local network" | The request came from a public address | Use it from your home network; for a VPN add its range to `allowed_networks`; never port-forward |
| "unexpected Host header" | A name the Pi does not recognise | Use its IP address or `<hostname>.local`, or add the name to `allowed_hosts` |
| "too many failed attempts" | The lockout is active for your address | Wait `lockout` seconds (5 minutes by default) |
| Settings saved but nothing changed | The service has not restarted yet | System tab, then "Restart the service" |
| Saving settings fails ("cannot be written") | The configuration file is not writable by the RetroPie user | `sudo chown -R pi /etc/picontrol`, or run `install.sh` again |
| Log file missing or empty | Not writable | The service logs to stderr instead; fix permissions on `/var/log/picontrol.log` |

## Reporting a problem

Open an issue with: the output of `picontrol doctor`, the relevant part of `/var/log/picontrol.log` (run with `[logging] level = DEBUG`), your Pi model, the RetroPie version and what you observed with `picontrol test ...`.
