# Contributing / Contribuer

## English

Thanks for helping! The project is small on purpose; please keep it that way.

### Set up

```
git clone https://github.com/<you>/picontrol.git && cd picontrol
python3 -m pip install pytest
python3 -m pytest -q            # the whole suite, no Raspberry Pi needed
shellcheck -x install.sh uninstall.sh scripts/common.sh
# optional browser-level test of the web page (needs Node.js):
(cd tests/ui && npm install) && python3 -m pytest tests/test_ui_smoke.py -q
```

Everything runs off-Pi: `RPi.GPIO` is imported lazily, and the tests use a fake GPIO plus a PN532 / MIFARE simulator (`tests/fakes.py`). CI runs the suite on Python 3.7, 3.9, 3.11 and 3.12 - **3.7 is what RetroPie 4.8 ships**, so avoid newer syntax and standard-library features.

### Guidelines

- **Test first.** A bug fix starts with a failing test; a feature comes with tests. Hardware behaviour you cannot test belongs in `picontrol test` or `picontrol doctor`.
- Every wait has a timeout; failures are exceptions, not `None`.
- Tag content is untrusted: never build shell commands from it.
- **Docs are bilingual.** Any change to `docs/en/` needs the matching change in `docs/fr/` (and the READMEs). `tests/test_docs.py` checks that the two trees stay in step and that links resolve.
- Code and comments are in English; module docstrings carry a short French line.
- Keep `config/picontrol.conf` in sync with `SPEC` in `config.py` (a test enforces it) and bump the version in both `__init__.py` and `pyproject.toml`.

### Pull requests

Describe what you observed on real hardware when relevant (Pi model, RetroPie version, `picontrol doctor` output).

## Français

Merci de votre aide ! Le projet est petit volontairement ; merci de le garder ainsi.

### Mise en place

```
git clone https://github.com/<vous>/picontrol.git && cd picontrol
python3 -m pip install pytest
python3 -m pytest -q            # toute la suite, aucun Raspberry Pi nécessaire
shellcheck -x install.sh uninstall.sh scripts/common.sh
# test optionnel de la page web dans un environnement de type navigateur (Node.js requis) :
(cd tests/ui && npm install) && python3 -m pytest tests/test_ui_smoke.py -q
```

Tout s'exécute hors du Pi : `RPi.GPIO` est importé à la demande, et les tests utilisent un faux GPIO et un simulateur PN532 / MIFARE (`tests/fakes.py`). La CI exécute la suite sur Python 3.7, 3.9, 3.11 et 3.12 - **3.7 est la version livrée avec RetroPie 4.8** : évitez les syntaxes et fonctions de bibliothèque plus récentes.

### Lignes directrices

- **Les tests d'abord.** Une correction commence par un test qui échoue ; une fonctionnalité vient avec ses tests. Ce qu'on ne peut pas tester sur le matériel relève de `picontrol test` ou `picontrol doctor`.
- Chaque attente a un délai maximum ; les échecs sont des exceptions, pas `None`.
- Le contenu d'un tag est non fiable : ne jamais en construire de commande shell.
- **La documentation est bilingue.** Toute modification de `docs/en/` demande la modification correspondante dans `docs/fr/` (et dans les README). `tests/test_docs.py` vérifie que les deux arborescences restent alignées et que les liens fonctionnent.
- Le code et les commentaires sont en anglais ; les docstrings de module portent une courte ligne en français.
- Gardez `config/picontrol.conf` synchronisé avec `SPEC` dans `config.py` (un test l'impose) et mettez à jour la version dans `__init__.py` et `pyproject.toml`.

### Demandes de fusion (pull requests)

Décrivez ce que vous avez observé sur du vrai matériel quand c'est pertinent (modèle de Pi, version de RetroPie, sortie de `picontrol doctor`).
