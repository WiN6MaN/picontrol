# Changelog / Journal des modifications

Format based on [Keep a Changelog](https://keepachangelog.com/). / Format inspiré de Keep a Changelog.

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
