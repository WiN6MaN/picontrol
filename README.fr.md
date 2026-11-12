# Pi Control

**Boutons power et reset, ventilateur, LED et cartouches de jeu NFC pour une console RetroPie construite sur la carte Pi Control.**
Une réécriture propre, documentée et testée.

🇬🇧 [Read in English](README.md)

Présentez une « cartouche » NFC et son jeu démarre. Basculez l'interrupteur et la console sauvegarde puis s'éteint proprement. Appuyez sur reset pour relancer le jeu ; maintenez-le pour écrire le jeu en cours sur une nouvelle cartouche. Le ventilateur garde le Pi au frais. Un seul petit programme Python 3 fait tout cela.

## Fonctionnalités

- **Interrupteur power** - arrêt propre : RetroArch est invité à quitter (et sauvegarder) avant l'extinction du Pi.
- **Bouton reset** - appui court : reset du jeu ; appui long : écrit le jeu en cours sur le prochain tag NFC.
- **Cartouches NFC** - détection en direct (PN532 en SPI logiciel) des tags MIFARE Classic et NTAG ; compatible avec les tags écrits par Pi Control d'origine, et lisibles par n'importe quelle application NFC de téléphone.
- **Ventilateur** - hystérésis en température avec durée de marche minimale, et sécurité : ventilateur ALLUMÉ si la température est illisible.
- **LED** - pilotée directement par son GPIO (pas de port série, aucune modification de `config.txt`).
- **Interface web (optionnelle)** - état, tags NFC avec recherche de jeux, réglages, redémarrage/arrêt, depuis n'importe quel appareil de votre réseau local. Désactivée par défaut, sans mot de passe par défaut, refuse tout ce qui vient de l'extérieur de votre réseau.
- **Robuste par conception** - threads supervisés (un plantage ne peut pas arrêter l'interrupteur power), un seul propriétaire du lecteur NFC, délais maximum partout, récupération automatique du lecteur.
- **Sûr par conception** - le contenu d'un tag est une entrée non fiable : validé, jamais passé à un shell. Aucun socket en écoute tant que vous n'activez pas l'interface web optionnelle.
- **Exploitable** - `picontrol doctor`, `picontrol test led|fan|buttons|nfc`, un mode simulation, un installateur idempotent avec sauvegardes, un fichier de configuration annoté.
- **Testé** - plus de 350 tests contre un simulateur de matériel PN532 / MIFARE, sur Python 3.7 à 3.12 (3.7 est la version livrée avec RetroPie 4.8), plus un test de la page web dans un environnement de type navigateur.

## État

**Bêta (0.3.0).** Les boutons, la LED, le ventilateur et l'interface web ont été validés sur un vrai Raspberry Pi 3B avec la carte Pi Control Rev 5. Le NFC est testé contre un simulateur du PN532 et de tags MIFARE Classic et NTAG ; la prise en charge des NTAG est nouvelle en 0.3.0 et **reste à confirmer sur de vrais tags**. Lancez `picontrol doctor` et `picontrol test ...` après l'installation, et signalez ce que vous observez. Voir l'[architecture](docs/fr/architecture.md) pour les limites connues.

## Démarrage rapide

Sur un Raspberry Pi 3B avec **RetroPie 4.8** et la carte Pi Control montée :

```
git clone https://github.com/WiN6MaN/picontrol.git
cd picontrol
sudo ./install.sh --dry-run    # voir ce qui serait modifié
sudo ./install.sh
picontrol doctor
picontrol test buttons         # puis : led, fan, nfc
sudo reboot
```

Écrire une cartouche :

```
picontrol tag write nes "Super Mario Bros.nes"    # puis présentez le tag
picontrol web set-password                        # interface web optionnelle : voir docs/fr/web.md
```

## Documentation

| | |
|---|---|
| [Matériel](docs/fr/hardware.md) | Carte, table des broches, module PN532, tests de câblage |
| [Installation](docs/fr/installation.md) | Installer, mettre à jour, désinstaller, migrer depuis l'original, EmulationStation plus rapide |
| [Interface web](docs/fr/web.md) | L'activer, ce qu'elle fait, modèle de sécurité, API |
| [Configuration](docs/fr/configuration.md) | Comportement, motifs de la LED, tous les réglages, commandes |
| [Tags NFC](docs/fr/nfc-tags.md) | Écrire/lire des tags, format, compatibilité |
| [Architecture](docs/fr/architecture.md) | Décisions de conception, modules, stratégie de test, limites |
| [Dépannage](docs/fr/troubleshooting.md) | Symptômes, causes, solutions |
| [Sécurité](SECURITY.md) · [Contribuer](CONTRIBUTING.md) · [Journal des modifications](CHANGELOG.md) | |

## Différences avec l'original

Ce projet s'inspire du logiciel Pi Control d'origine mais n'en partage aucun code.

| Original | Ici |
|---|---|
| Scripts Python 2, plusieurs processus | Un seul programme Python 3.7+, threads supervisés |
| Les boutons et le serveur web parlent tous deux au lecteur NFC | Un seul propriétaire du lecteur, plus un verrou inter-processus pour la CLI |
| NFC lu seulement au démarrage, au reset ou en cyclant l'interrupteur | Détection en direct |
| Interface web avec mot de passe par défaut | Interface web optionnelle : désactivée par défaut, sans mot de passe par défaut, réseau local seulement, durcie (voir [sécurité](SECURITY.md)) |
| Noms de jeux intégrés à des commandes shell | Noms validés, listes d'arguments, aucun shell |
| Un « Q » majuscule dans un nom de jeu tronquait l'enregistrement du tag | Enregistrements décodés par longueur |
| Des hooks `runcommand` arrêtent EmulationStation à chaque jeu | Aucun hook : seuls les lancements par tag relancent EmulationStation |
| Port série activé pour allumer la LED | LED sur son GPIO |
| Pas de tests automatisés dans le paquet | Plus de 350 tests avec simulateur de matériel, plus un test de type navigateur |

## Organisation du dépôt

```
src/picontrol/   le programme         tests/    suite pytest et simulateur de matériel
config/          exemple annoté       docs/     documentation (en/, fr/)
install.sh, uninstall.sh, scripts/    installateur
```

## Crédits

La carte Pi Control et son logiciel d'origine sont l'œuvre d'Evan Wright et Jared Kirchgatter ([jetekteam/picontrol](https://github.com/jetekteam/picontrol)) ; le boîtier est un design de « Daft Mike ». Cette réécriture conserve l'affectation des broches de la carte et le format des tags, pour que le matériel et les tags existants continuent de fonctionner. Le protocole PN532 est implémenté d'après la documentation publique de NXP (UM0701-02), en s'inspirant des bibliothèques PN532 d'Adafruit sous licence MIT.

## Licence

[MIT](LICENSE)
