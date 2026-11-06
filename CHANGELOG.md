# Changelog / Journal des modifications

Format based on [Keep a Changelog](https://keepachangelog.com/). / Format inspiré de Keep a Changelog.

## [0.2.0] - 2026-11-04

- Optional web interface (off by default, no default password, local network only, HTTPS with a self-signed certificate): status, NFC tag read/write with game search, safe settings editor, restart/reboot/shutdown, log viewer; English and French.
  / Interface web optionnelle (désactivée par défaut, sans mot de passe par défaut, réseau local seulement, HTTPS auto-signé) : état, lecture/écriture de tags NFC avec recherche de jeux, éditeur de réglages sûrs, redémarrage/reboot/arrêt, journal ; en français et en anglais.
- Hardening: PBKDF2 password hash, login lockout, sessions with CSRF tokens, `Host` header validation, strict Content-Security-Policy, whitelisted editable settings (never commands, paths or pins).
  / Durcissement : mot de passe haché PBKDF2, blocage après échecs, sessions avec jetons CSRF, validation de l'en-tête `Host`, CSP stricte, réglages modifiables limités (jamais commandes, chemins ni broches).
- New commands: `picontrol web set-password`; `picontrol doctor` checks the web settings. NFC operations are now queued jobs handled by the NFC thread.
  / Nouvelle commande : `picontrol web set-password` ; `picontrol doctor` vérifie les réglages web. Les opérations NFC sont des tâches traitées par le thread NFC.
- 350+ tests, including a browser-level test of the page (jsdom) in CI.
  / Plus de 350 tests, dont un test de la page de type navigateur (jsdom) en CI.

## [0.1.0] - 2026-11-04

First release. / Première version.

- Single Python 3.7+ service with supervised threads: power switch, reset button, fan, LED, NFC.
  / Service Python 3.7+ unique avec threads supervisés : interrupteur power, bouton reset, ventilateur, LED, NFC.
- PN532 driver over software SPI; live tag detection; tag format compatible with the original Pi Control, with a decoder that reads records by length.
  / Pilote PN532 en SPI logiciel ; détection de tags en direct ; format de tag compatible avec Pi Control d'origine, décodage des enregistrements par longueur.
- Commands: `run`, `tag read|write`, `test led|fan|buttons|nfc`, `doctor`.
  / Commandes : `run`, `tag read|write`, `test led|fan|buttons|nfc`, `doctor`.
- Idempotent installer and uninstaller with backups and a dry-run mode.
  / Installateur et désinstallateur idempotents, avec sauvegardes et mode simulation.
- 150+ tests against a PN532 / MIFARE simulator; CI on Python 3.7-3.12.
  / Plus de 150 tests contre un simulateur PN532 / MIFARE ; CI sur Python 3.7-3.12.
- Bilingual documentation (English / français).
  / Documentation bilingue (English / français).
- **Not yet validated on real hardware. / Pas encore validé sur du vrai matériel.**
