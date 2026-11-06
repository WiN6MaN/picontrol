# Security / Sécurité

## English

### Threat model

Pi Control runs on a console that usually sits on a home network, and it reads **NFC tags that anyone can write**. The design assumes:

- **Tag content is untrusted input.** A tag may carry hostile names. Names are validated (system: 1-40 characters from `A-Z a-z 0-9 _ + -`; ROM: a file name with no path separators), resolved inside the ROM folder (symbolic links that escape it are refused) and passed to `runcommand.sh` as an **argument list - never through a shell**. Tests cover path traversal, shell metacharacters and symlink escapes.
- **Small network surface.** By default there is no web server and no listening socket; the only network traffic is UDP to RetroArch on `127.0.0.1`. The optional web interface is described below.
- **Least privilege.** The service runs as the normal RetroPie user. The only privileged action is the shutdown command (`sudo -n shutdown -h now`), which relies on passwordless `sudo` - the RetroPie default.

### Web interface (optional, off by default)

If you turn it on, it is the only listening socket. It is designed for a trusted home network:

- It never starts without a password, and there is **no default password**. The password is stored as a salted PBKDF2-SHA256 hash; repeated failures lock the address out.
- It only answers clients on private networks (loopback, RFC 1918, link-local, plus `allowed_networks`) and only for expected `Host` names. This is a safety net against accidental port forwarding and DNS rebinding, **not** a reason to expose it: never forward its port.
- HTTPS with a self-signed certificate is the default; check the fingerprint printed in the log the first time.
- Sessions use `HttpOnly` + `SameSite=Strict` cookies, an idle timeout and a CSRF token on every change; a strict Content-Security-Policy applies and all text is inserted as text, never as HTML.
- A logged-in user can change only whitelisted numeric and on/off settings. Commands, paths, pins and web settings are file-only, so a stolen session cannot make the service run an arbitrary command (the shutdown command goes through `sudo`, so this matters).
- Restart, reboot and shutdown need an explicit confirmation in the request.

### What you should do

- If you enable the web interface, choose a long, unique password and keep `allow_public = false`.
- **Change the default `pi` password** (`raspi-config`), especially if SSH is enabled: passwordless `sudo` makes that account powerful.
- RetroArch's network commands (`network_cmd_enable`) accept **unauthenticated** UDP commands such as `QUIT` and `RESET`. Depending on the RetroArch version they may be reachable from other machines on your network; if the console is on an untrusted network, restrict the port with a firewall (for example `sudo iptables -A INPUT ! -i lo -p udp --dport 55355 -j DROP`).
- Foreign tags are ignored, but remember a tag can still start **any ROM you have installed**.

### Reporting a vulnerability

Please use GitHub's private vulnerability reporting ("Security" tab → "Report a vulnerability") rather than a public issue. Include the version (`picontrol --version`), what you did, and what you expected.

## Français

### Modèle de menace

Pi Control tourne sur une console généralement connectée à un réseau domestique, et il lit des **tags NFC que n'importe qui peut écrire**. La conception suppose :

- **Le contenu d'un tag est une entrée non fiable.** Un tag peut porter des noms hostiles. Les noms sont validés (système : 1 à 40 caractères parmi `A-Z a-z 0-9 _ + -` ; ROM : un nom de fichier sans séparateur de chemin), résolus dans le dossier des ROM (les liens symboliques qui en sortent sont refusés) et transmis à `runcommand.sh` comme une **liste d'arguments - jamais par un shell**. Des tests couvrent la traversée de chemin, les métacaractères shell et les évasions par lien symbolique.
- **Petite surface réseau.** Par défaut, pas de serveur web ni de socket en écoute ; le seul trafic réseau est de l'UDP vers RetroArch sur `127.0.0.1`. L'interface web optionnelle est décrite plus bas.
- **Moindre privilège.** Le service tourne avec l'utilisateur RetroPie normal. La seule action privilégiée est la commande d'arrêt (`sudo -n shutdown -h now`), qui repose sur `sudo` sans mot de passe - le réglage par défaut de RetroPie.

### Interface web (optionnelle, désactivée par défaut)

Si vous l'activez, c'est le seul socket en écoute. Elle est conçue pour un réseau domestique de confiance :

- Elle ne démarre jamais sans mot de passe, et il n'y a **aucun mot de passe par défaut**. Le mot de passe est stocké sous forme d'un hachage PBKDF2-SHA256 salé ; des échecs répétés bloquent l'adresse.
- Elle ne répond qu'aux clients des réseaux privés (boucle locale, RFC 1918, lien local, plus `allowed_networks`) et seulement pour les noms `Host` attendus. C'est un filet de sécurité contre une redirection de port accidentelle et le DNS rebinding, **pas** une raison de l'exposer : ne redirigez jamais son port.
- Le HTTPS avec certificat auto-signé est la valeur par défaut ; vérifiez l'empreinte affichée dans le journal la première fois.
- Les sessions utilisent des cookies `HttpOnly` + `SameSite=Strict`, un délai d'inactivité et un jeton CSRF à chaque modification ; une Content-Security-Policy stricte s'applique et tout le texte est inséré comme texte, jamais comme HTML.
- Un utilisateur connecté ne peut modifier que des réglages numériques et on/off autorisés. Les commandes, chemins, broches et réglages web ne se modifient que dans le fichier : une session volée ne peut donc pas faire exécuter une commande arbitraire au service (la commande d'arrêt passe par `sudo`, ce qui compte).
- Le redémarrage, le reboot et l'arrêt exigent une confirmation explicite dans la requête.

### Ce que vous devriez faire

- Si vous activez l'interface web, choisissez un mot de passe long et unique, et gardez `allow_public = false`.
- **Changez le mot de passe `pi` par défaut** (`raspi-config`), surtout si SSH est activé : un `sudo` sans mot de passe rend ce compte puissant.
- Les commandes réseau de RetroArch (`network_cmd_enable`) acceptent des commandes UDP **non authentifiées** comme `QUIT` et `RESET`. Selon la version de RetroArch, elles peuvent être joignables depuis d'autres machines du réseau ; si la console est sur un réseau peu sûr, restreignez le port avec un pare-feu (par exemple `sudo iptables -A INPUT ! -i lo -p udp --dport 55355 -j DROP`).
- Les tags étrangers sont ignorés, mais un tag peut tout de même lancer **n'importe quelle ROM installée**.

### Signaler une vulnérabilité

Utilisez le signalement privé de GitHub (onglet « Security » → « Report a vulnerability ») plutôt qu'un ticket public. Indiquez la version (`picontrol --version`), ce que vous avez fait et ce que vous attendiez.
