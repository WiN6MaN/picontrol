# Web interface

An optional page to watch and control the console from a phone or a laptop on your **home network**: status, NFC tags (read and write, with a game search), settings, and restart or shutdown. It is built on Python's standard library only - nothing extra to install.

It is **off by default**, has **no default password**, and refuses every request that does not come from your local network. It is not meant to be reachable from the internet: never port-forward it.

## Turn it on

```
picontrol web set-password          # choose a password (8 characters or more)
sudo nano /etc/picontrol/picontrol.conf     # in [web], set: enabled = true
pkill -f "python3 -m picontrol run"         # the start-up loop restarts it; the log shows the address
```

Then open `https://<address-of-the-pi>:8443` in a browser (for example `https://retropie.local:8443`). The service logs the address and the certificate fingerprint at start-up (`tail /var/log/picontrol.log`).

HTTPS uses a self-signed certificate created on first start (it needs `openssl`, which RetroPie has). Your browser will warn that it cannot verify the certificate: compare the fingerprint it shows with the one in the log, then accept it. Set `tls = false` only if you accept that the password travels unencrypted on your network.

The service refuses to start the web part without a password, and logs why. The console itself keeps working.

## What you can do

| Tab | What it does |
|---|---|
| Status | Temperature, fan, power switch, running game, NFC reader and tag, uptimes. Refreshes every 3 seconds |
| NFC tags | Read a tag; write a tag by choosing a system and searching your games; write the running game |
| Settings | Change the safe settings, grouped by function, each with an explanation, its unit and its default value; a bar shows the unsaved changes and offers to restart the service |
| System | Restart the service, reboot or shut down the Pi (each asks for confirmation), read the log |

The interface is in English or French (button at the top, remembered by the browser).

## Security model

- **Local network only.** Clients with a public address are refused, even with the right password (`allow_public = false`). `allowed_networks` adds ranges such as `100.64.0.0/10` (Tailscale).
- **Password.** Stored only as a salted PBKDF2-SHA256 hash, in a file readable by your user only. After `max_login_failures` wrong passwords an address is locked out for `lockout` seconds.
- **Sessions.** A random cookie marked `HttpOnly` and `SameSite=Strict` (and `Secure` with HTTPS), an idle timeout, and a separate CSRF token required on every change.
- **Browser protections.** A strict Content-Security-Policy (no inline scripts), no framing, `Host` header validation against DNS rebinding, request size limits, and all page text inserted as text, never as HTML.
- **No shell.** Nothing from the browser is ever run as a command; game names go through the same validation as tags.
- **Destructive actions** (restart, reboot, shutdown) need an explicit confirmation in the request.

See [SECURITY](../../SECURITY.md) for the full threat model.

## What the page cannot change

Only numbers, on/off switches and `power.off_level` can be edited from the browser. **Commands, paths, pins and the web settings themselves are file-only.** That is deliberate: if someone ever got into the page, they could still not make the service run an arbitrary command or lock you out. Edit those in `/etc/picontrol/picontrol.conf`.

Saving writes the file (keeping your comments, and the previous version as `picontrol.conf.bak`) after validating it. Settings apply when the service restarts: use the System tab.

## For scripts: the API

The page uses a small JSON API that you can call yourself. Log in first (it returns a CSRF token and sets the cookie); every `POST` needs `Content-Type: application/json` and the `X-CSRF-Token` header.

| Request | Purpose |
|---|---|
| `POST /api/login`, `POST /api/logout`, `GET /api/session` | Sign in with `{"password": "..."}`, sign out, check the session |
| `GET /api/state` | Status of the console |
| `GET /api/systems` | Systems with their game counts |
| `GET /api/roms?system=nes&q=mario&offset=0&limit=50` | Search games (at most 200 per page) |
| `POST /api/tag/read` | Wait for a tag and read it |
| `POST /api/tag/write` | Wait for a tag and write `{"system": "nes", "rom": "Zelda.nes"}` |
| `POST /api/tag/write-current` | Write the running game on the next tag |
| `GET /api/config`, `POST /api/config` | List the editable settings; change some with `{"changes": {"fan.threshold_on": 65}}` |
| `POST /api/service/restart`, `/api/system/reboot`, `/api/system/shutdown` | Body `{"confirm": true}` |
| `GET /api/log?lines=100` | Last lines of the log |

```
curl -k -c jar -H 'Content-Type: application/json' -d '{"password":"..."}' https://retropie.local:8443/api/login
curl -k -b jar https://retropie.local:8443/api/state
```

## If something goes wrong

`picontrol doctor` checks the web settings. See [troubleshooting](troubleshooting.md) for the usual causes: page unreachable, certificate warning, "access is limited to the local network", lockout.
