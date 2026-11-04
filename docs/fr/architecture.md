# Architecture

## Un processus, plusieurs threads supervisés

```
 picontrol run   (un processus, lancé depuis autostart.sh par l'utilisateur RetroPie)
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │ thread boutons ── interrupteur power (GPIO3) ──► arrêt propre                   │
 │                └─ bouton reset (GPIO23) ───────► RESET │ demande d'écriture     │
 │ thread ventilo ── /sys thermique ──► hystérésis ──► MOSFET ventilateur (GPIO18) │
 │ thread nfc ────── PN532 (GPIO 4/17/27/22) ──► tag ──► Launcher ──► runcommand   │
 │ LED (partagée, verrouillée) ◄── tous les composants                             │
 └────────────────────────────────────────────────────────────────────────────────┘
```

Chaque thread est supervisé séparément : une exception est journalisée et le thread repart avec un délai croissant pendant que les autres continuent. **Un bogue dans le code NFC ne peut pas arrêter l'interrupteur power.** (Un test le vérifie.)

## Modules (`src/picontrol/`)

| Module | Responsabilité |
|---|---|
| `config.py` | Lecture INI, valeurs par défaut, validation stricte |
| `gpio.py` | Mince enveloppe de `RPi.GPIO` (importée à la demande : tout est testable hors du Pi) |
| `pn532.py` | Pilote PN532 : SPI logiciel, trames, sommes de contrôle, auth/lecture/écriture MIFARE |
| `tagformat.py` | Encodage/décodage pur du conteneur sur le tag |
| `tagstore.py` | Lecture/écriture des enregistrements sur une disposition MIFARE Classic 1K |
| `nfc.py` | Machine à états des tags, demandes d'écriture, boucle de sondage supervisée |
| `launcher.py` | Validation des ROM, arrêt/lancement des jeux et d'EmulationStation |
| `buttons.py`, `fan.py`, `led.py` | Petites machines à états pilotées par une horloge injectée |
| `retroarch.py` | Commandes réseau UDP de RetroArch |
| `service.py` | Assemblage, supervision des threads, séquence d'arrêt |
| `cli.py`, `doctor.py`, `hwtest.py` | Ligne de commande, auto-diagnostic, tests matériels |

## Décisions de conception

- **SPI logiciel.** La carte relie le PN532 à des GPIO ordinaires. Le bus est généré en Python (mode 0, bit de poids faible en premier).
- **Lancé depuis `autostart.sh`, pas systemd.** Lancer un jeu doit se faire dans la session console de RetroPie (tty, affichage, entrées). Une boucle de relance autour de la commande assure la reprise après plantage.
- **Un seul propriétaire du lecteur.** Le programme d'origine laissait plusieurs processus (boutons, serveur web) parler au PN532 en même temps, et des trames entremêlées se corrompent. Ici, le thread NFC est le seul propriétaire ; les commandes `picontrol tag` prennent un verrou de fichier inter-processus (`ReaderLock`) que le service respecte entre deux sondages.
- **Chaque attente a un délai maximum, chaque échec est une exception.** Le pilote ne renvoie jamais `None` pour signaler une erreur. Après trois erreurs de lecteur consécutives, le service réinitialise complètement la puce (annulation de la commande en cours, réveil, vérification du firmware, configuration).
- **Tentatives d'activation finies.** Au démarrage, on indique à la puce de n'essayer qu'une fois par sondage : `InListPassiveTarget` revient vite avec zéro cible au lieu de rester occupée.
- **Coupure du champ RF avant chaque sondage** (`rf_reset_each_poll`). Un tag déjà sélectionné peut ne pas répondre à une deuxième demande de détection ; couper le champ d'abord fait voir le tag « à neuf » à chaque sondage. Le simulateur modélise ce pire cas. Ne désactivez cette option que si votre matériel prouve qu'elle est inutile.
- **Présence avec délai.** Un tag n'est « retiré » qu'après `remove_delay` secondes sans détection : un tag en bord de champ ne provoque pas de relances.
- **LED sur son GPIO.** Ni port série ni modification de `config.txt` (voir [matériel](hardware.md)).
- **Sécurités.** Ventilateur allumé si la température est illisible ou si le contrôleur s'arrête ; pas d'arrêt si la commande échoue (l'interrupteur se réarme) ; rien n'est lancé pendant l'arrêt.
- **Aucune surface réseau.** Pas de serveur web, pas de socket en écoute. Le seul trafic réseau est de l'UDP vers RetroArch sur localhost.

## Stratégie de test

La suite de tests (plus de 150 tests, pytest) exerce toute la pile contre un **simulateur** du PN532 et d'un tag MIFARE Classic branchés sur les mêmes broches de SPI logiciel : transferts bit à bit, trames et sommes de contrôle, ACK/réponse, authentification, lecture/écriture de blocs, pannes injectées (puce muette, réponses corrompues). L'installateur est exécuté pour de vrai dans un bac à sable. Les boutons et le ventilateur sont pilotés par une horloge injectée : aucun test n'attend en temps réel.

Le simulateur reproduit le protocole tel que l'utilisait le pilote d'origine, mais ce n'est pas la vraie puce : la validation sur le matériel reste l'étape finale, d'où `picontrol test` et `picontrol doctor`.

## Limites connues

- Un lancement par tag arrête et relance EmulationStation (inhérent au lancement depuis l'extérieur).
- Le reset et la fermeture n'agissent que sur les émulateurs basés sur RetroArch.
- MIFARE Classic 1K seulement ; 255 octets de charge utile par tag.
- L'interrupteur power n'a qu'un comportement (arrêt propre immédiat). Le mode « alimentation logicielle » de l'original (éteindre puis rallumer en quelques secondes pour recharger) n'est pas implémenté.
