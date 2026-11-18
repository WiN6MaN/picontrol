# Changelog / Journal des modifications

Format based on [Keep a Changelog](https://keepachangelog.com/). / Format inspiré de Keep a Changelog.

## [0.3.1] - 2026-11-18

- Fixed: after a game started from an NFC tag, the RetroPie menus (RetroPie Setup, Raspi-Config, Wi-Fi...) misbehaved and jumped back to EmulationStation. The original Pi Control had the same defect. Cause: killing EmulationStation ended `autostart.sh`, the login shell took the console back, and the game and EmulationStation, started later by a background service, ran behind it. Now EmulationStation runs under a foreground `picontrol session`, which also runs the tag games, so everything keeps the console.
  / Corrigé : après un jeu lancé depuis un tag NFC, les menus RetroPie (RetroPie Setup, Raspi-Config, Wi-Fi...) se comportaient mal et revenaient à EmulationStation. Pi Control d'origine avait le même défaut. Cause : tuer EmulationStation terminait `autostart.sh`, le shell de connexion reprenait la console, et le jeu puis EmulationStation, lancés ensuite par un service d'arrière-plan, tournaient derrière lui. Désormais EmulationStation tourne sous une `picontrol session` au premier plan, qui lance aussi les jeux des tags : tout garde la console.
- The installer writes a new start-up block (a small `emulationstation()` function; plain EmulationStation starts if the session cannot run). **Reboot after upgrading.** Without a session the service falls back to the old method and logs a warning; `picontrol doctor` reports the state.
  / L'installateur écrit un nouveau bloc de démarrage (une petite fonction `emulationstation()` ; EmulationStation démarre normalement si la session ne peut pas tourner). **Redémarrez après la mise à jour.** Sans session, le service se rabat sur l'ancienne méthode et journalise un avertissement ; `picontrol doctor` signale l'état.
- On shutdown the session no longer restarts EmulationStation when the game quits. New command `picontrol session`; new module `roms.py`; `PICONTROL_RUNTIME_DIR` can move the request and pid files away from `/dev/shm`.
  / À l'arrêt, la session ne relance plus EmulationStation quand le jeu se ferme. Nouvelle commande `picontrol session` ; nouveau module `roms.py` ; `PICONTROL_RUNTIME_DIR` permet de déplacer les fichiers de demande et de pid hors de `/dev/shm`.
- 70+ new tests, among them a test with real processes on a pseudo-terminal that checks the game and EmulationStation stay in the terminal's foreground process group (and a control test that detects the old behaviour).
  / Plus de 70 nouveaux tests, dont un test avec de vrais processus sur un pseudo-terminal qui vérifie que le jeu et EmulationStation restent dans le groupe de processus au premier plan du terminal (et un test témoin qui détecte l'ancien comportement).

## [0.3.0] - 2026-11-10

- NTAG213 / NTAG215 / NTAG216 and MIFARE Ultralight tags (7-byte UID) are now supported, next to MIFARE Classic 1K; the family is detected automatically and protected areas are never written.
  / Les tags NTAG213 / NTAG215 / NTAG216 et MIFARE Ultralight (UID de 7 octets) sont désormais pris en charge, avec le MIFARE Classic 1K ; la famille est détectée automatiquement et les zones protégées ne sont jamais écrites.
- The tag decoder now follows the NDEF standard: Text records written by phone apps (any language code) are read, other NDEF content (a web address, for instance) is refused with a clear message.
  / Le décodeur de tags suit désormais le standard NDEF : les enregistrements Texte écrits par des applications de téléphone (tout code de langue) sont lus, les autres contenus NDEF (une adresse web, par exemple) sont refusés avec un message clair.
- Web interface, Settings tab redesigned: grouped by function, a label, an explanation, a unit and the default value for every setting, switches, "reset to default", a save bar with the number of unsaved changes; value ranges are now enforced by the server.
  / Interface web, onglet Réglages repensé : regroupé par fonction, un libellé, une explication, une unité et la valeur par défaut pour chaque réglage, interrupteurs, « valeur par défaut », barre d'enregistrement avec le nombre de changements non enregistrés ; les plages de valeurs sont désormais imposées par le serveur.

## [0.2.0] - 2026-11-04

- Optional web interface (off by default, no default password, local network only, HTTPS with a self-signed certificate): status, NFC tag read/write with game search, safe settings editor, restart/reboot/shutdown, log viewer; English and French.
  / Interface web optionnelle (désactivée par défaut, sans mot de passe par défaut, réseau local seulement, HTTPS auto-signé) : état, lecture/écriture de tags NFC avec recherche de jeux, éditeur de réglages sûrs, redémarrage/reboot/arrêt, journal ; en français et en anglais.
- Hardening: PBKDF2 password hash, login lockout, sessions with CSRF tokens, `Host` header validation, strict Content-Security-Policy, whitelisted editable settings (never commands, paths or pins).
  / Durcissement : mot de passe haché PBKDF2, blocage après échecs, sessions avec jetons CSRF, validation de l'en-tête `Host`, CSP stricte, réglages modifiables limités (jamais commandes, chemins ni broches).
- New commands: `picontrol web set-password`; `picontrol doctor` checks the web settings. NFC operations are now queued jobs handled by the NFC thread.
  / Nouvelle commande : `picontrol web set-password` ; `picontrol doctor` vérifie les réglages web. Les opérations NFC sont des tâches traitées par le thread NFC.
- 350+ tests, including a browser-level test of the page (jsdom) in CI.
  / Plus de 350 tests, dont un test de la page de type navigateur (jsdom) en CI.
- `scripts/personalize.sh` makes a downloaded copy yours (names, license holder, commit authors); `.gitattributes` pins Unix line endings.
  / `scripts/personalize.sh` personnalise une copie téléchargée (noms, titulaire de la licence, auteur des commits) ; `.gitattributes` impose les fins de ligne Unix.

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
