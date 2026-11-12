# Dépannage

Commencez par les deux outils qui répondent à la plupart des questions :

```
picontrol doctor          # vérifie l'installation (rien ne touche au matériel)
tail -n 50 /var/log/picontrol.log
picontrol --debug run     # exécution au premier plan avec un journal détaillé (arrêtez d'abord le service, voir ci-dessous)
```

Pour arrêter le service en cours pendant vos essais : `pkill -f "python3 -m picontrol run"`, puis `Ctrl+C` dans votre exécution au premier plan. (La boucle de démarrage relance le service trois secondes après son arrêt.)

| Symptôme | Cause probable | Que faire |
|---|---|---|
| `doctor` : RPi.GPIO manquant | Dépendance non installée | `sudo apt install python3-rpi.gpio` |
| `doctor` : commandes réseau RetroArch | `network_cmd_enable` désactivé | Relancez `sudo ./install.sh`, ou mettez `network_cmd_enable = "true"` dans `retroarch.cfg` |
| La LED ne s'allume jamais | Service arrêté, mauvaise broche, polarité de la LED | `picontrol test led` ; vérifiez `[pins] led` ; consultez le journal |
| Le ventilateur ne démarre jamais | Broche, câblage du MOSFET, ou le Pi est simplement frais | `picontrol test fan` ; comparez `cat /sys/class/thermal/thermal_zone0/temp` (en m°C) à `threshold_on` |
| Ventilateur toujours allumé | Température illisible (sécurité) ou seuil trop bas | Ligne « Temperature unreadable » dans le journal ; vérifiez `temp_path` |
| Interrupteur sur OFF sans arrêt | `sudo` demande un mot de passe, ou niveaux inversés | `doctor` (sudo sans mot de passe) ; `picontrol test buttons` affiche `ON/OFF` ; si c'est inversé, `[power] off_level = low` |
| Le Pi s'éteint juste après le démarrage | L'interrupteur était sur OFF au démarrage | Mettez-le d'abord sur ON ; c'est voulu |
| Le reset ne fait rien | Le jeu n'est pas un cœur RetroArch, ou les commandes réseau sont désactivées | `doctor` ; essayez un système basé sur RetroArch |
| `picontrol test nfc` : PN532 introuvable | Interrupteurs de mode pas sur SPI, câble mal branché, mauvaises broches, clone | Mettez les interrupteurs sur SPI **et remettez sous tension** ; vérifiez le câble 6 broches et `[pins]` |
| « authentication refused - foreign tag » | Le tag a des clés non standard | Utilisez un tag vierge ou écrit par Pi Control |
| Tag détecté mais « ignoré » | Tag vierge, tag contenant autre chose (une adresse web, par exemple) ou contenu invalide | Le journal explique pourquoi ; `picontrol tag read` |
| « unsupported tag type » | Une famille de tags que le lecteur ne gère pas (NTAG 424 DNA, DESFire, MIFARE Classic à 7 octets) | Utilisez des tags MIFARE Classic 1K ou NTAG213/215/216 |
| « too long for this tag » | Le nom de la ROM ne tient pas dans la mémoire de ce tag | Utilisez un NTAG plus grand (215 ou 216) ou un nom de fichier plus court |
| « is the tag locked? » | Le tag est en lecture seule | Utilisez un autre tag : un tag verrouillé ne peut pas être réécrit |
| « not NDEF-formatted » | Un tag non formaté (pas de conteneur de capacités) | Formatez-le une fois avec une application NFC de téléphone (« formater le tag »), puis réécrivez-le |
| « ROM not found » | Le système ou le nom de fichier ne correspond pas au dossier de ROM | Les noms sont sensibles à la casse : `picontrol tag read` puis comparez avec `ls ~/RetroPie/roms/<système>` |
| Le jeu se lance deux fois ou se relance sans cesse | Tag en bord de champ, détection instable | Placez bien le tag ; augmentez `remove_delay` ; envoyez un journal `--debug` si cela persiste |
| « The reader is busy » | Une autre commande ou le service tient le lecteur | Réessayez ; les commandes attendent jusqu'à 20 s |
| Erreurs NFC aléatoires | Fils longs ou mal serrés, module hors mode SPI, bruit d'alimentation | `picontrol --debug run` ; vérifiez le câblage et l'alimentation |
| Le retour d'un jeu lancé par tag est lent | EmulationStation recharge ses listes | Voir [installation](installation.md#emulationstation-plus-rapide) |
| La page web ne charge pas | Interface web désactivée, pas de mot de passe, mauvaise adresse ou mauvais port | `picontrol doctor` ; vérifiez `[web] enabled` ; le journal donne l'adresse (`tail /var/log/picontrol.log`) |
| Le navigateur avertit du certificat | Certificat auto-signé | Normal : comparez l'empreinte avec celle du journal, puis acceptez |
| « access is limited to the local network » | La requête vient d'une adresse publique | Utilisez-la depuis votre réseau domestique ; pour un VPN, ajoutez sa plage à `allowed_networks` ; ne redirigez jamais le port |
| « unexpected Host header » | Un nom que le Pi ne reconnaît pas | Utilisez son adresse IP ou `<nom-d'hôte>.local`, ou ajoutez le nom à `allowed_hosts` |
| « too many failed attempts » | Le blocage est actif pour votre adresse | Attendez `lockout` secondes (5 minutes par défaut) |
| Réglages enregistrés mais rien n'a changé | Le service n'a pas encore redémarré | Onglet Système, puis « Redémarrer le service » |
| L'enregistrement des réglages échoue (« cannot be written ») | Le fichier de configuration n'est pas modifiable par l'utilisateur RetroPie | `sudo chown -R pi /etc/picontrol`, ou relancez `install.sh` |
| Journal absent ou vide | Non inscriptible | Le service journalise alors sur stderr ; corrigez les droits de `/var/log/picontrol.log` |

## Signaler un problème

Ouvrez un ticket (issue) avec : la sortie de `picontrol doctor`, la partie utile de `/var/log/picontrol.log` (avec `[logging] level = DEBUG`), votre modèle de Pi, la version de RetroPie et ce que vous avez observé avec `picontrol test ...`.
