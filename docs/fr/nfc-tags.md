# Tags NFC (« cartouches »)

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

`write` refuse une ROM inexistante (`--force` pour passer outre) et **relit toujours le tag** pour vérifier. Vous pouvez aussi maintenir le bouton reset pendant un jeu, puis présenter un tag.

Les commandes attendent le lecteur (le service le libère entre deux sondages) : elles s'utilisent donc pendant que le service tourne.

## Compatibilité des tags

- Les tags écrits par Pi Control d'origine **fonctionnent tels quels**, et ceux écrits ici fonctionnent avec lui.
- Type : MIFARE Classic 1K avec les clés par défaut (UID de 4 octets). Les tags étrangers (autres clés), vierges ou NTAG sont détectés et **ignorés**, jamais lancés.
- Seuls les blocs de données sont écrits. Le secteur 0 et les « trailers » de secteur (clés et droits d'accès) ne sont jamais modifiés.

### Format sur le tag

```
03 <longueur de la charge> <91 | D1>         en-tête (91 = deux enregistrements ou plus)
par enregistrement :  01 <longueur+3> 54 02 'e' 'n' <texte> <terminateur>
terminateur :  11 ou 51 = un autre enregistrement suit, FE = dernier enregistrement
```

Les données commencent au bloc 4 et sautent un bloc sur quatre (les trailers) : la capacité est de 45 blocs = 720 octets, mais le conteneur est limité à 255 octets de charge utile.

Une amélioration par rapport au décodeur d'origine : celui-ci repérait les enregistrements en cherchant les **valeurs d'octet** des terminateurs dans le texte, si bien qu'un « Q » majuscule (0x51) dans un nom coupait l'enregistrement. Ce lecteur parcourt les enregistrements selon leur longueur déclarée : tous les caractères sont sûrs.

## Comportement pendant un jeu

- Un jeu lancé par un tag arrête EmulationStation et le relance ensuite. On ne peut pas demander à EmulationStation de lancer un jeu depuis l'extérieur, et il doit d'abord libérer l'écran et les manettes. Les jeux lancés depuis EmulationStation lui-même ne sont pas concernés. Pour accélérer ce redémarrage : [installation](installation.md#emulationstation-plus-rapide).
- Présenter un autre tag pendant un jeu arrête le jeu et lance le nouveau.
- `quit_on_remove = true` quitte le jeu quand son tag est retiré.
- Retirer puis représenter le même tag relance le jeu ; le laisser en place ne le relance pas.

## Non pris en charge

Les tags NTAG/Ultralight, les tags à clés non standard, une interface web de gestion des tags (utilisez les commandes ci-dessus) et l'écriture depuis un téléphone.
