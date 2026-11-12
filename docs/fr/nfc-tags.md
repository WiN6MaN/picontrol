# Tags NFC (« cartouches »)

## Le NFC en quelques mots

Un tag NFC est une minuscule puce passive, sans pile. Le lecteur (le module PN532) produit en permanence un champ magnétique à 13,56 MHz. Quand un tag s'approche à environ 3 ou 4 cm, le champ l'alimente par induction - comme un chargeur sans fil - et il répond par son identifiant unique (l'**UID**). Le lecteur peut alors lire et écrire la mémoire du tag, après s'être authentifié avec une clé. Les tags MIFARE Classic 1K du kit ont 1 Ko, organisé en blocs.

Ici, le tag ne contient **pas** le jeu. Il porte deux petits textes - le système et le nom de la ROM - et le logiciel cherche le jeu sur votre carte SD. Un tag fonctionne donc sur toute console qui a la même ROM sous le même nom.

## Fonctionnement

Un tag contient deux textes : un **système** (le nom du dossier RetroPie, par exemple `nes`, `snes`, `megadrive`) et un **nom de fichier ROM** (par exemple `Super Mario Bros.nes`). Quand vous présentez un tag, le service le lit, vérifie que la ROM existe et la lance avec le `runcommand.sh` de RetroPie.

Règles pour les noms :

- Le système fait de 1 à 40 caractères : lettres, chiffres, `_`, `+`, `-`.
- La ROM est un **nom de fichier seul** (pas de dossier), situé directement dans `roms_dir/<système>/`.
- Tout le reste est refusé - voir [SECURITY](../../SECURITY.md) : le contenu d'un tag est une entrée non fiable.

## Écrire et lire des tags

```
picontrol tag write nes "Super Mario Bros.nes"   # puis présentez le tag
picontrol tag write --current                    # le jeu en cours à l'instant
picontrol tag read                               # affiche l'UID, le système et la ROM
```

`write` refuse une ROM inexistante (`--force` pour passer outre) et **relit toujours le tag** pour vérifier. Vous pouvez aussi maintenir le bouton reset pendant un jeu, puis présenter un tag, ou utiliser l'[interface web](web.md), qui ajoute une recherche de jeux.

Les commandes attendent le lecteur (le service le libère entre deux sondages) : elles s'utilisent donc pendant que le service tourne.

## Compatibilité des tags

- Les tags écrits par Pi Control d'origine **fonctionnent tels quels**, et ceux écrits ici fonctionnent avec lui.
- Types pris en charge, détectés automatiquement : **MIFARE Classic 1K** (UID de 4 octets, les tags du kit, clés par défaut) et **NTAG213 / NTAG215 / NTAG216 / MIFARE Ultralight** (UID de 7 octets). Les tags vierges, ceux qui contiennent autre chose (une adresse web écrite par un téléphone, par exemple) et les familles non prises en charge (tags à autres clés, NTAG 424 DNA, DESFire) sont détectés et **ignorés**, jamais lancés.
- Seules les données utilisateur sont écrites. Sur un MIFARE Classic, le secteur 0 et les « trailers » de secteur (clés et droits d'accès) ne sont jamais modifiés ; sur un NTAG, l'UID, les octets de verrouillage, le conteneur de capacités et les pages de configuration ne le sont jamais.
- Capacité : un NTAG213 contient 144 octets, un NTAG215 496, un NTAG216 872 - largement assez pour un système et un nom de ROM (environ 40 octets). Si un nom est trop long pour le tag, l'écriture est refusée avec un message clair.

### Format sur le tag

Le contenu est un message NDEF standard (NFC Forum) formé de deux enregistrements Texte (le système, puis la ROM) : n'importe quelle application NFC peut le lire - et écrire des tags compatibles :

```
03 <longueur>                                        TLV NDEF (longueur = le message ci-dessous)
<en-tête> 01 <n+3> 54 02 'e' 'n' <système, n octets>   premier enregistrement Texte (en-tête 91 ; D1 s'il est seul)
<en-tête> 01 <m+3> 54 02 'e' 'n' <ROM, m octets>       dernier enregistrement Texte (en-tête 51 ; 11 pour un enregistrement intermédiaire)
FE                                                   terminateur
```

`<en-tête>` est l'en-tête d'enregistrement NDEF, `54` le type « T » (Texte) et `02` l'octet d'état (UTF-8, code de langue de deux lettres). Les enregistrements Texte écrits par d'autres applications avec un autre code de langue sont lus aussi. Sur un MIFARE Classic, les données commencent au bloc 4 et sautent un bloc sur quatre (les trailers) ; sur un NTAG, elles commencent à la page 4. Le message est limité à 254 octets.

Une amélioration par rapport au décodeur d'origine : celui-ci repérait les enregistrements en cherchant les **valeurs d'octet** des en-têtes dans le texte, si bien qu'un « Q » majuscule (0x51) dans un nom coupait l'enregistrement. Ce lecteur parcourt les enregistrements selon leur longueur déclarée : tous les caractères sont sûrs.

## Comportement pendant un jeu

- Un jeu lancé par un tag arrête EmulationStation et le relance ensuite. On ne peut pas demander à EmulationStation de lancer un jeu depuis l'extérieur, et il doit d'abord libérer l'écran et les manettes. Les jeux lancés depuis EmulationStation lui-même ne sont pas concernés. Pour accélérer ce redémarrage : [installation](installation.md#emulationstation-plus-rapide).
- Présenter un autre tag pendant un jeu arrête le jeu et lance le nouveau.
- `quit_on_remove = true` quitte le jeu quand son tag est retiré.
- Retirer puis représenter le même tag relance le jeu ; le laisser en place ne le relance pas.

## Non pris en charge

Les tags à clés non standard, les NTAG 424 DNA et DESFire, et l'écriture sur des tags verrouillés (en lecture seule). Un téléphone reste un bon complément : n'importe quelle application NFC lit ces tags et en écrit de compatibles.
