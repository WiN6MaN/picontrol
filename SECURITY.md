# Security / Sécurité

## English

### Threat model

Pi Control runs on a console that usually sits on a home network, and it reads **NFC tags that anyone can write**. The design assumes:

- **Tag content is untrusted input.** A tag may carry hostile names. Names are validated (system: 1-40 characters from `A-Z a-z 0-9 _ + -`; ROM: a file name with no path separators), resolved inside the ROM folder (symbolic links that escape it are refused) and passed to `runcommand.sh` as an **argument list - never through a shell**. Tests cover path traversal, shell metacharacters and symlink escapes.
- **No network surface of its own.** There is no web server and no listening socket. The only network traffic is UDP to RetroArch on `127.0.0.1`.
- **Least privilege.** The service runs as the normal RetroPie user. The only privileged action is the shutdown command (`sudo -n shutdown -h now`), which relies on passwordless `sudo` - the RetroPie default.

### What you should do

- **Change the default `pi` password** (`raspi-config`), especially if SSH is enabled: passwordless `sudo` makes that account powerful.
- RetroArch's network commands (`network_cmd_enable`) accept **unauthenticated** UDP commands such as `QUIT` and `RESET`. Depending on the RetroArch version they may be reachable from other machines on your network; if the console is on an untrusted network, restrict the port with a firewall (for example `sudo iptables -A INPUT ! -i lo -p udp --dport 55355 -j DROP`).
- Foreign tags are ignored, but remember a tag can still start **any ROM you have installed**.

### Reporting a vulnerability

Please use GitHub's private vulnerability reporting ("Security" tab → "Report a vulnerability") rather than a public issue. Include the version (`picontrol --version`), what you did, and what you expected.

## Français

### Modèle de menace

Pi Control tourne sur une console généralement connectée à un réseau domestique, et il lit des **tags NFC que n'importe qui peut écrire**. La conception suppose :

- **Le contenu d'un tag est une entrée non fiable.** Un tag peut porter des noms hostiles. Les noms sont validés (système : 1 à 40 caractères parmi `A-Z a-z 0-9 _ + -` ; ROM : un nom de fichier sans séparateur de chemin), résolus dans le dossier des ROM (les liens symboliques qui en sortent sont refusés) et transmis à `runcommand.sh` comme une **liste d'arguments - jamais par un shell**. Des tests couvrent la traversée de chemin, les métacaractères shell et les évasions par lien symbolique.
- **Aucune surface réseau propre.** Pas de serveur web, pas de socket en écoute. Le seul trafic réseau est de l'UDP vers RetroArch sur `127.0.0.1`.
- **Moindre privilège.** Le service tourne avec l'utilisateur RetroPie normal. La seule action privilégiée est la commande d'arrêt (`sudo -n shutdown -h now`), qui repose sur `sudo` sans mot de passe - le réglage par défaut de RetroPie.

### Ce que vous devriez faire

- **Changez le mot de passe `pi` par défaut** (`raspi-config`), surtout si SSH est activé : un `sudo` sans mot de passe rend ce compte puissant.
- Les commandes réseau de RetroArch (`network_cmd_enable`) acceptent des commandes UDP **non authentifiées** comme `QUIT` et `RESET`. Selon la version de RetroArch, elles peuvent être joignables depuis d'autres machines du réseau ; si la console est sur un réseau peu sûr, restreignez le port avec un pare-feu (par exemple `sudo iptables -A INPUT ! -i lo -p udp --dport 55355 -j DROP`).
- Les tags étrangers sont ignorés, mais un tag peut tout de même lancer **n'importe quelle ROM installée**.

### Signaler une vulnérabilité

Utilisez le signalement privé de GitHub (onglet « Security » → « Report a vulnerability ») plutôt qu'un ticket public. Indiquez la version (`picontrol --version`), ce que vous avez fait et ce que vous attendiez.
