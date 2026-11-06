# Configuration et comportement

La configuration est un simple fichier INI : `/etc/picontrol/picontrol.conf` (ou le fichier donné avec `-c`, ou `$PICONTROL_CONFIG`). Chaque clé a une valeur par défaut, donc un fichier vide est valide ; les sections et clés inconnues sont refusées pour qu'une faute de frappe ne passe pas inaperçue. La référence annotée est [`config/picontrol.conf`](../../config/picontrol.conf). Les changements s'appliquent au redémarrage du service (voir l'[installation](installation.md)).

## Comportement

### Interrupteur power

| Vous faites | Le service fait |
|---|---|
| Basculer l'interrupteur sur **OFF** (plus longtemps que `debounce`) | Fait clignoter la LED, demande à RetroArch de quitter (il sauvegarde), attend `quit_grace` secondes, éteint la LED, exécute `shutdown_command` |
| Le remettre sur **ON** une fois le Pi arrêté | Rien côté logiciel : fermer l'interrupteur tire GPIO3 à la masse, ce qui réveille le Pi |

La position de l'interrupteur fait foi : si le Pi démarre alors qu'il est sur OFF, il s'éteint de nouveau.

### Bouton reset

| Vous faites | Le service fait |
|---|---|
| Appui court | Envoie `RESET` à RetroArch (redémarre le jeu en cours) |
| Appui maintenu `long_press` secondes | Écrit le jeu en cours sur le prochain tag présenté (voir [tags NFC](nfc-tags.md)) |

Le reset et la fermeture passent par les commandes réseau de RetroArch : ils n'agissent donc que sur les émulateurs basés sur RetroArch.

### Ventilateur

Allumé à `threshold_on` °C, éteint à `threshold_off` °C, et jamais éteint avant d'avoir tourné `min_run` secondes. Si la température est illisible trois fois de suite - ou si le contrôleur s'arrête pour une raison quelconque - le ventilateur est **allumé** : un ventilateur qui tourne est inoffensif, un Pi trop chaud ne l'est pas.

### NFC

Présenter un tag lance son jeu une seule fois. Le laisser en place ne fait rien (le jeu n'est pas relancé quand il se termine). Un tag est considéré retiré après `remove_delay` secondes d'absence ; le présenter de nouveau relance le jeu. Détails dans [tags NFC](nfc-tags.md).

### Interface web

Optionnelle et désactivée par défaut : état, tags NFC, quelques réglages sûrs et redémarrage/arrêt depuis un navigateur de votre réseau local. Tout est décrit dans [interface web](web.md).

### LED

| Motif | Signification |
|---|---|
| Allumée en continu | Le service tourne |
| Un clignotement court | Bouton reset pressé |
| Trois clignotements rapides | Appui long reconnu : présentez un tag |
| Trois clignotements lents | Tag écrit et vérifié |
| Six clignotements très rapides | Erreur (rien à écrire, aucun tag à temps, échec d'écriture) |
| Trois clignotements moyens, puis éteinte | Arrêt en cours |

## Paramètres

| Section | Clé | Défaut | Signification |
|---|---|---|---|
| `[pins]` | `power`, `reset`, `led`, `fan`, `nfc_sclk`, `nfc_miso`, `nfc_mosi`, `nfc_cs` | 3, 23, 14, 18, 4, 17, 27, 22 | Numéros BCM ; chaque signal a sa broche |
| `[power]` | `enabled` | `true` | |
| | `off_level` | `high` | Niveau signifiant « interrupteur OFF » (`high` ou `low`) |
| | `debounce` | `0.3` | Secondes pendant lesquelles l'interrupteur doit rester sur OFF |
| | `quit_grace` | `1.5` | Secondes laissées à RetroArch avant l'arrêt |
| | `shutdown_command` | `sudo -n shutdown -h now` | Exécutée avec l'utilisateur RetroPie |
| `[reset]` | `long_press` | `2.0` | Secondes pour un appui long |
| `[fan]` | `threshold_on` / `threshold_off` | `60` / `50` | °C ; `on` doit dépasser `off` |
| | `interval`, `min_run` | `5`, `20` | Secondes entre deux mesures ; durée de marche minimale |
| | `temp_path` | `/sys/class/thermal/thermal_zone0/temp` | Fichier de température du noyau |
| `[nfc]` | `poll_interval`, `poll_interval_game` | `0.5`, `1.0` | Secondes entre deux sondages (repos / jeu en cours) |
| | `remove_delay` | `2.0` | Absence nécessaire pour compter un retrait |
| | `launch_at_start` | `true` | Lancer le tag déjà présent au démarrage |
| | `quit_on_remove` | `false` | Quitter le jeu quand son tag est retiré |
| | `rf_reset_each_poll` | `true` | Couper le champ RF avant chaque sondage (voir [architecture](architecture.md)) |
| | `write_timeout` | `15` | Secondes pour présenter un tag après un appui long |
| `[paths]` | `roms_dir`, `runcommand`, `retroarch_cfg`, `emulationstation_command`, `extra_emulators` | valeurs RetroPie | Emplacements |
| `[retroarch]` | `host`, `port` | `127.0.0.1`, `55355` | Doit correspondre à `network_cmd_port` |
| `[logging]` | `file`, `level` | `/var/log/picontrol.log`, `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `[web]` | `enabled` | `false` | Active l'interface web (exige un mot de passe) |
| | `host`, `port`, `tls` | `0.0.0.0`, `8443`, `true` | Où elle écoute ; HTTPS avec un certificat auto-signé |
| | `cert_file`, `key_file`, `password_file` | dans `/etc/picontrol/` | Certificat, clé et hachage du mot de passe |
| | `session_timeout`, `max_login_failures`, `lockout` | `3600`, `5`, `300` | Secondes d'inactivité ; échecs avant blocage ; secondes de blocage |
| | `allow_public`, `allowed_networks`, `allowed_hosts` | `false`, aucun, aucun | Laissez `allow_public` désactivé : ne l'exposez jamais sur internet |

Chaque composant a un interrupteur `enabled` : par exemple, `[nfc] enabled = false` fait tourner les boutons et le ventilateur sans NFC.

## Commandes

```
picontrol run [--dry-run]           # le service ; --dry-run journalise au lieu d'agir
picontrol tag read                  # affiche le tag présent
picontrol tag write nes "Super Mario Bros.nes"
picontrol tag write --current       # écrit le jeu en cours
picontrol test led|fan|buttons|nfc  # tests matériels
picontrol web set-password          # définit le mot de passe de l'interface web
picontrol doctor                    # vérifie l'installation
picontrol --debug ...               # journal détaillé dans le terminal
```
