# Installation

## Prérequis

- Un Raspberry Pi 3B (ou similaire) avec la carte Pi Control montée et testée.
- **RetroPie 4.8** installé depuis l'image officielle (basée sur Raspberry Pi OS Buster, qui fournit Python 3.7), RetroPie étant à jour. L'installateur exige Python 3.7 ou plus récent.
- Un accès réseau (Ethernet est le plus simple) et les droits `sudo` - l'utilisateur `pi` par défaut les a.

## Installer

```
git clone https://github.com/<vous>/picontrol.git
cd picontrol
sudo ./install.sh --dry-run      # montre exactement ce qui serait modifié
sudo ./install.sh
picontrol doctor                 # vérifie l'installation
picontrol test buttons           # puis : led, fan, nfc (voir hardware.md)
sudo reboot
```

Si `git` manque : `sudo apt install git`. L'installateur est **idempotent** : le relancer met le code à jour et n'écrase jamais votre configuration.

### Ce que l'installateur modifie

| Quoi | Où | Remarques |
|---|---|---|
| Code | `/opt/picontrol/lib/picontrol` | Remplacé à chaque installation |
| Lanceur | `/usr/local/bin/picontrol` | Petit script shell |
| Configuration | `/etc/picontrol/picontrol.conf` | Créée une seule fois ; les nouvelles valeurs par défaut vont dans `picontrol.conf.dist`. Le dossier appartient à l'utilisateur RetroPie pour que l'interface web puisse enregistrer les réglages |
| Journal | `/var/log/picontrol.log` | Appartient à l'utilisateur RetroPie ; rotation à 200 ko |
| Dépendance | `python3-rpi.gpio` | Installée avec `apt` seulement si elle manque |
| RetroArch | `/opt/retropie/configs/all/retroarch.cfg` | Active `network_cmd_enable = "true"` et le port, après copie de sauvegarde `retroarch.cfg.picontrol-bak` |
| Démarrage | `/opt/retropie/configs/all/autostart.sh` | Ajoute un bloc balisé **avant** la ligne `emulationstation` (copie `autostart.sh.picontrol-bak`) |

Options : `--dry-run`, `--skip-deps`, `--no-retroarch-config`, `--no-autostart`, `--user NOM`.

### Facultatif : l'interface web

Elle est désactivée par défaut. Pour l'activer, voir [interface web](web.md) (`picontrol web set-password`, puis `enabled = true` dans la section `[web]`).

### Démarrage manuel (si vous avez utilisé `--no-autostart`)

Ajoutez ceci dans `/opt/retropie/configs/all/autostart.sh`, **avant** la ligne `emulationstation` (cette ligne est bloquante : tout ce qui la suit ne s'exécuterait jamais) :

```
(while true; do /usr/local/bin/picontrol run; sleep 3; done) &
```

La boucle relance le service s'il s'arrête. Pour appliquer un changement de configuration sans redémarrer : `pkill -f "python3 -m picontrol run"` - la boucle le relance trois secondes plus tard.

## Si vous venez de Pi Control d'origine (ou d'une installation modifiée à la main)

Repartez d'une image RetroPie propre si possible. Sinon, retirez d'abord les anciens éléments pour que deux programmes ne se disputent pas les mêmes broches :

1. Dans `/etc/rc.local`, supprimez les lignes qui lancent `shutdown.py`, `reset.py` et `picontrol_fan.py` (ou le `picontrol.py` d'origine).
2. Dans `/opt/retropie/configs/all/autostart.sh`, supprimez toute ligne qui lance le `picontrol.py` d'origine.
3. Retirez les hooks d'origine **s'ils viennent** de l'installateur d'origine (vérifiez leur contenu d'abord) : `/opt/retropie/configs/all/runcommand-onstart.sh` et `runcommand-onend.sh`. Ils arrêtent EmulationStation à chaque jeu.
4. Supprimez l'ancien dossier (`/home/pi/RetroPie/nescontrol` ou `picontrol`).
5. L'astuce du port série pour la LED n'est plus nécessaire. Si vous l'aviez activé uniquement pour la LED, vous pouvez le désactiver (cela rétablit aussi l'horloge du cœur).

**Vos tags existants continuent de fonctionner** : le format sur le tag n'a pas changé (voir [tags NFC](nfc-tags.md)).

## Mise à jour et désinstallation

```
cd picontrol && git pull && sudo ./install.sh     # mise à jour
sudo ./uninstall.sh                               # retire le code, le lanceur et le bloc de démarrage
sudo ./uninstall.sh --purge                       # ...et aussi la configuration et le journal
```

`uninstall.sh` ne touche pas à `retroarch.cfg` (une sauvegarde, `retroarch.cfg.picontrol-bak`, existe).

## EmulationStation plus rapide

Un jeu lancé par un tag arrête EmulationStation et le relance à la fin du jeu (voir l'[architecture](architecture.md) pour la raison). Avec des milliers de jeux, rendez ce redémarrage plus rapide :

- Activez **Parse Gamelists Only** (menu d'EmulationStation, *Other settings*, ou `ParseGamelistOnly` à `true` dans `es_settings.cfg`). Seuls les jeux listés dans un `gamelist.xml` sont alors affichés : assurez-vous d'abord que vos listes sont complètes.
- Désactivez la collection automatique **Last Played** si vous ne l'utilisez pas.
- Laissez *Threaded loading* désactivé : il est signalé comme source de plantages.
