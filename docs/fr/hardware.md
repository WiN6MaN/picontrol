# Matériel

Pi Control est une petite carte d'extension pour un Raspberry Pi installé dans un boîtier de console rétro. Elle fournit un **interrupteur d'alimentation** à verrouillage, un **bouton reset**, une **LED d'alimentation**, un **pilote de ventilateur** et un **lecteur NFC** pour des « cartouches » de jeu.

Ce logiciel vise la carte **Pi Control Rev 5** sur un **Raspberry Pi 3B** sous **RetroPie 4.8**. Les autres modèles de Pi ont le même connecteur GPIO et devraient fonctionner, mais ils n'ont pas été testés.

## Ce que contient la carte

| Élément | Rôle |
|---|---|
| Connecteur 16 broches (2 × 8) | Se branche sur les 16 premières broches du connecteur 40 broches du Pi |
| Connecteur de façade 4 broches (`LED`, `GND`, `PWR`, `RST`) | LED d'alimentation, interrupteur à verrouillage, bouton reset momentané |
| Connecteur ventilateur 2 broches + MOSFET canal N, résistance 10 kΩ, diode de roue libre 1N4001 | Commande un ventilateur depuis un GPIO |
| Connecteur NFC 6 broches (`SCK`, `MISO`, `MOSI`, `SS`, `VCC`, `GND`) | Module NFC PN532 (carte V3) |

La carte et son logiciel d'origine sont l'œuvre d'Evan Wright et Jared Kirchgatter ; le boîtier est un design « Daft Mike ». Consultez les notes de montage de votre kit pour la liste des composants.

## Table des broches

Numéros BCM (ceux qu'utilise le logiciel) et broche physique correspondante sur le connecteur du Pi :

| Fonction | BCM | Broche physique | Direction | Remarques |
|---|---|---|---|---|
| Interrupteur power | 3 | 5 | entrée, pull-up | Fermé à la masse = **ON**. GPIO3 tiré à la masse réveille aussi un Pi en veille (halt) |
| Bouton reset | 23 | 16 | entrée, pull-up | Appuyé = masse |
| LED | 14 | 8 | sortie | Niveau haut = allumée |
| Ventilateur | 18 | 12 | sortie | Commande la grille du MOSFET : haut = ventilateur en marche |
| NFC horloge (SCLK) | 4 | 7 | sortie | SPI logiciel |
| NFC données entrantes (MISO) | 17 | 11 | entrée | SPI logiciel |
| NFC données sortantes (MOSI) | 27 | 13 | sortie | SPI logiciel |
| NFC sélection (SS) | 22 | 15 | sortie | SPI logiciel |

Les huit broches sont dans les 16 premières broches du connecteur, c'est-à-dire exactement ce que transporte le connecteur 16 broches de la carte.

> **Provenance.** Ces numéros viennent du logiciel Pi Control d'origine, pas d'un schéma. Si votre carte est câblée autrement, changez-les dans la section `[pins]` de la configuration, rien d'autre n'est à modifier. Validez toujours avec `picontrol test` (voir plus bas).

## Pourquoi un SPI logiciel ?

Le PN532 est relié à des broches GPIO ordinaires, pas au bus SPI matériel du Pi (GPIO 8 à 11). Le protocole SPI est donc généré par logiciel (mode 0, bit de poids faible en premier, comme l'exige le PN532). Conséquences :

- Il n'est **pas** nécessaire d'activer le SPI dans `raspi-config`.
- Les transferts sont plus lents qu'en SPI matériel, ce qui n'a aucune importance pour lire un tag.

## Le module PN532

- Réglez les **interrupteurs de mode du module sur SPI avant de le mettre sous tension** (ils sont lus à la mise sous tension). Sur la carte V3 courante, c'est généralement `S1 = OFF`, `S2 = ON` ; vérifiez la sérigraphie ou le manuel du vendeur pour votre module.
- Les vrais modules PN532 V3 sont recommandés : l'auteur du kit signale de mauvais clones, qui peuvent causer des défaillances intermittentes.
- Tags pris en charge : **MIFARE Classic 1K** (UID de 4 octets) avec les clés par défaut, comme dans le kit. Les NTAG et les autres types ne sont pas pris en charge.

## Interrupteur, réveil et LED

- L'interrupteur est un bouton-poussoir **à verrouillage**. En le fermant, on relie GPIO3 à la masse : c'est ce qui réveille un Pi arrêté (halt) après l'extinction, et c'est ce que le logiciel lit comme « ON ». L'ouvrir déclenche un arrêt propre.
- La LED est pilotée directement par son GPIO ; elle est allumée tant que le service tourne. Elle n'a **pas** besoin du port série. (Activer le mini-UART avec `enable_uart=1` est une astuce courante pour allumer cette LED tôt, mais sur un Pi 3 cela fixerait l'horloge du cœur à 250 MHz, ce qui peut coûter des performances graphiques : Pi Control l'évite.)
- Le ventilateur se branche sur le connecteur de la carte. Vérifiez le marquage `+` / `-` et utilisez un ventilateur 5 V.

## Tester le câblage

À lancer en SSH (le service n'a pas besoin d'être arrêté pour `nfc` : il libère le lecteur entre deux sondages) :

```
picontrol test led        # la LED clignote 5 fois
picontrol test fan        # le ventilateur tourne 5 secondes
picontrol test buttons    # basculez l'interrupteur, appuyez sur reset : les états s'affichent en direct
picontrol test nfc        # trouve le PN532, puis affiche l'UID d'un tag présenté
```

Si un test n'affiche rien, vérifiez la connexion physique et la broche correspondante dans `[pins]` au multimètre avant de soupçonner le logiciel. Voir le [dépannage](troubleshooting.md).
