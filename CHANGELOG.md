# Changelog / Journal des modifications

Format based on [Keep a Changelog](https://keepachangelog.com/). / Format inspiré de Keep a Changelog.

## [0.3.3] - 2026-11-18

- New: setting `[nfc] replace_running_game` (default `true`, so nothing changes unless you switch it). With `false`, a tag presented while a game is running is ignored, whether the game was started from a tag or from EmulationStation: the running game is no longer cut. The tag is then considered handled: after quitting the game, remove the tag and present it again to launch it. Available in the web interface (Settings, NFC) and in `picontrol.conf`. Combine it with `quit_on_remove = true` for a "swap cartridges" feel: remove the cartridge to close the game, wait for EmulationStation to come back, insert another to play it.
  / Nouveau : réglage `[nfc] replace_running_game` (`true` par défaut : rien ne change tant que vous ne le modifiez pas). À `false`, un tag présenté pendant qu'un jeu tourne est ignoré, que le jeu ait été lancé depuis un tag ou depuis EmulationStation : le jeu en cours n'est plus coupé. Le tag est alors considéré comme traité : après avoir quitté le jeu, retirez le tag et présentez-le de nouveau pour le lancer. Disponible dans l'interface web (Réglages, NFC) et dans `picontrol.conf`. À combiner avec `quit_on_remove = true` pour l'effet « changer de cartouche » : retirer la cassette ferme le jeu, attendre le retour d'EmulationStation, en insérer une autre pour la lancer.
- 7 new tests (including the case of a game still loading, the rule that an ignored tag does not start the relaunch delay, and the web interface setting).
  / 7 nouveaux tests (dont le cas d'un jeu encore en chargement, et la règle qu'un tag ignoré ne déclenche pas le délai de relance et le réglage dans l'interface web).

## [0.3.2] - 2026-11-19

- Fixed: with a tag already in the reader at boot, the controller stopped responding in the RetroPie menus. The log showed why: EmulationStation was still loading, ignored the polite stop for 3 seconds and was then killed by force, which leaves the console keyboard in a broken state. Now the console session waits (12 s at most) for the NFC service's first scan at boot: a tag present at start launches its game before EmulationStation even starts. EmulationStation is no longer killed by force (only the emulators are, after 8 s; EmulationStation only after 2 minutes of being stuck), in the console session and in the direct fallback alike.
  / Corrigé : avec une cassette déjà dans le lecteur au démarrage, la manette ne répondait plus dans les menus RetroPie. Le journal montrait la cause : EmulationStation chargeait encore, ignorait l'arrêt poli pendant 3 secondes puis était tué de force, ce qui laisse le clavier de la console dans un état cassé. Désormais la session de console attend (12 s au maximum) le premier balayage du service NFC au démarrage : une cassette présente au démarrage lance son jeu avant même qu'EmulationStation démarre. EmulationStation n'est plus tué de force (seuls les émulateurs le sont, après 8 s ; EmulationStation seulement après 2 minutes de blocage), dans la session de console comme dans le repli direct.
- New: the service tells the session when its first scan is done (`picontrol-ready-<uid>` next to the request file); with NFC disabled or `launch_at_start = false` the session does not wait at all. A power-off during a launch no longer leaves the launcher waiting.
  / Nouveau : le service indique à la session que son premier balayage est fait (`picontrol-ready-<uid>`, à côté du fichier de demande) ; avec le NFC désactivé ou `launch_at_start = false`, la session n'attend pas du tout. Une extinction pendant un lancement ne laisse plus le lanceur en attente.
- 15+ new tests, including real processes on a pseudo-terminal for a tag present at boot.
  / Plus de 15 nouveaux tests, dont de vrais processus sur un pseudo-terminal pour une cassette présente au démarrage.

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
