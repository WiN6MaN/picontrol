# Interface web

Une page optionnelle pour surveiller et piloter la console depuis un téléphone ou un portable sur votre **réseau domestique** : état, tags NFC (lecture et écriture, avec recherche de jeux), réglages, redémarrage ou arrêt. Elle repose uniquement sur la bibliothèque standard de Python - rien de plus à installer.

Elle est **désactivée par défaut**, n'a **aucun mot de passe par défaut**, et refuse toute requête qui ne vient pas de votre réseau local. Elle n'est pas faite pour être joignable depuis internet : ne redirigez jamais son port.

## L'activer

```
picontrol web set-password          # choisissez un mot de passe (8 caractères ou plus)
sudo nano /etc/picontrol/picontrol.conf     # dans [web], mettez : enabled = true
pkill -f "python3 -m picontrol run"         # la boucle de démarrage le relance ; le journal indique l'adresse
```

Ouvrez ensuite `https://<adresse-du-pi>:8443` dans un navigateur (par exemple `https://retropie.local:8443`). Le service journalise l'adresse et l'empreinte du certificat au démarrage (`tail /var/log/picontrol.log`).

Le HTTPS utilise un certificat auto-signé créé au premier démarrage (il faut `openssl`, présent sur RetroPie). Votre navigateur avertira qu'il ne peut pas vérifier le certificat : comparez l'empreinte affichée avec celle du journal, puis acceptez-le. Ne mettez `tls = false` que si vous acceptez que le mot de passe circule sans chiffrement sur votre réseau.

Le service refuse de démarrer la partie web sans mot de passe, et le journalise. La console, elle, continue de fonctionner.

## Ce que vous pouvez faire

| Onglet | Fonction |
|---|---|
| État | Température, ventilateur, interrupteur, jeu en cours, lecteur NFC et tag, durées de fonctionnement. Se rafraîchit toutes les 3 secondes |
| Tags NFC | Lire un tag ; écrire un tag en choisissant un système et en cherchant dans vos jeux ; écrire le jeu en cours |
| Réglages | Modifier les réglages sûrs (voir plus bas) ; un bandeau rappelle de redémarrer le service |
| Système | Redémarrer le service, redémarrer ou éteindre le Pi (chacun demande confirmation), lire le journal |

L'interface existe en français et en anglais (bouton en haut, mémorisé par le navigateur).

## Modèle de sécurité

- **Réseau local seulement.** Les clients ayant une adresse publique sont refusés, même avec le bon mot de passe (`allow_public = false`). `allowed_networks` ajoute des plages comme `100.64.0.0/10` (Tailscale).
- **Mot de passe.** Stocké uniquement sous forme d'un hachage PBKDF2-SHA256 salé, dans un fichier lisible par votre utilisateur seul. Après `max_login_failures` mauvais mots de passe, une adresse est bloquée `lockout` secondes.
- **Sessions.** Un cookie aléatoire marqué `HttpOnly` et `SameSite=Strict` (et `Secure` avec HTTPS), un délai d'inactivité, et un jeton CSRF distinct exigé à chaque modification.
- **Protections du navigateur.** Une Content-Security-Policy stricte (aucun script en ligne), pas d'intégration dans un cadre, validation de l'en-tête `Host` contre le DNS rebinding, limites de taille des requêtes, et tout le texte de la page inséré comme texte, jamais comme HTML.
- **Aucun shell.** Rien venant du navigateur n'est jamais exécuté comme commande ; les noms de jeux passent par la même validation que ceux des tags.
- **Actions destructrices** (redémarrage, reboot, arrêt) : une confirmation explicite est exigée dans la requête.

Voir [SECURITY](../../SECURITY.md) pour le modèle de menace complet.

## Ce que la page ne peut pas modifier

Seuls les nombres, les interrupteurs on/off et `power.off_level` sont modifiables depuis le navigateur. **Les commandes, chemins, broches et les réglages web eux-mêmes ne se modifient que dans le fichier.** C'est voulu : si quelqu'un entrait un jour dans la page, il ne pourrait toujours pas faire exécuter une commande arbitraire au service ni vous enfermer dehors. Modifiez-les dans `/etc/picontrol/picontrol.conf`.

L'enregistrement écrit le fichier (en gardant vos commentaires, et la version précédente dans `picontrol.conf.bak`) après l'avoir validé. Les réglages s'appliquent au redémarrage du service : utilisez l'onglet Système.

## Pour les scripts : l'API

La page utilise une petite API JSON que vous pouvez appeler vous-même. Connectez-vous d'abord (cela renvoie un jeton CSRF et pose le cookie) ; chaque `POST` exige `Content-Type: application/json` et l'en-tête `X-CSRF-Token`.

| Requête | Rôle |
|---|---|
| `POST /api/login`, `POST /api/logout`, `GET /api/session` | Se connecter avec `{"password": "..."}`, se déconnecter, vérifier la session |
| `GET /api/state` | État de la console |
| `GET /api/systems` | Systèmes avec leur nombre de jeux |
| `GET /api/roms?system=nes&q=mario&offset=0&limit=50` | Rechercher des jeux (200 par page au maximum) |
| `POST /api/tag/read` | Attendre un tag et le lire |
| `POST /api/tag/write` | Attendre un tag et y écrire `{"system": "nes", "rom": "Zelda.nes"}` |
| `POST /api/tag/write-current` | Écrire le jeu en cours sur le prochain tag |
| `GET /api/config`, `POST /api/config` | Lister les réglages modifiables ; en changer avec `{"changes": {"fan.threshold_on": 65}}` |
| `POST /api/service/restart`, `/api/system/reboot`, `/api/system/shutdown` | Corps `{"confirm": true}` |
| `GET /api/log?lines=100` | Dernières lignes du journal |

```
curl -k -c jar -H 'Content-Type: application/json' -d '{"password":"..."}' https://retropie.local:8443/api/login
curl -k -b jar https://retropie.local:8443/api/state
```

## En cas de problème

`picontrol doctor` vérifie les réglages web. Voir le [dépannage](troubleshooting.md) pour les causes habituelles : page injoignable, avertissement de certificat, « access is limited to the local network », blocage après trop d'essais.
