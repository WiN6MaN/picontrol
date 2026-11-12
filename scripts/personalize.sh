#!/usr/bin/env bash
# Make this copy of the project yours: puts your GitHub user name, your name and your e-mail where they
# belong, and rewrites the author of every commit.
# Personnalise cette copie du projet : met votre nom GitHub, votre nom et votre courriel aux bons endroits
# et réécrit l'auteur de tous les commits.
#
# Usage: bash scripts/personalize.sh [--github NAME] [--name "Full Name"] [--email ADDRESS]
# Without options it asks the questions. / Sans option, il pose les questions.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# The identity must come from the values given here, not from the environment of the caller.
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL

GH_USER=""
FULL_NAME=""
EMAIL=""
FILES=(README.md README.fr.md CONTRIBUTING.md docs/en/installation.md docs/fr/installation.md)

die() { printf 'ERROR / ERREUR: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --github) [ $# -ge 2 ] || die "--github needs a value"; GH_USER=$2; shift ;;
    --name)   [ $# -ge 2 ] || die "--name needs a value"; FULL_NAME=$2; shift ;;
    --email)  [ $# -ge 2 ] || die "--email needs a value"; EMAIL=$2; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

ask() { # ask VARIABLE "question"
  local var=$1 question=$2 answer
  if [ -n "${!var}" ]; then return 0; fi
  [ -t 0 ] || die "missing value for $var and no terminal to ask it / valeur manquante : $var"
  read -r -p "$question " answer
  printf -v "$var" '%s' "$answer"
}

ask GH_USER "Your GitHub user name / Votre nom d'utilisateur GitHub :"
ask FULL_NAME "Your name (shown on your commits and in LICENSE) / Votre nom :"
ask EMAIL "Your e-mail (use your GitHub noreply address to keep your real one private) / Votre courriel :"

[[ $GH_USER =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,37}[A-Za-z0-9])?$ ]] || die "invalid GitHub user name (letters, digits and hyphens only): $GH_USER"
[[ $EMAIL =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || die "invalid e-mail address: $EMAIL"
[ -n "$FULL_NAME" ] || die "the name must not be empty"
case $FULL_NAME in *$'\n'*) die "the name must be on one line" ;; esac

git rev-parse --git-dir >/dev/null 2>&1 || die "this folder is not a git repository (is the hidden .git folder there?)"
# Some unzip tools drop the "executable" flag of the scripts: that alone must not count as a change.
git config core.fileMode false
if ! git diff --quiet || ! git diff --cached --quiet; then
  die "there are uncommitted changes: commit or discard them first"
fi

esc() { printf '%s' "$1" | sed -e 's/[\\|&]/\\&/g'; }   # safe inside s|...|...|

replace() { # replace FILE PATTERN VALUE...   (portable: no sed -i)
  local file=$1 pattern=$2 value tmp
  value=$(esc "$3")
  tmp=$(mktemp)
  sed "s|$pattern|$value|g" "$file" > "$tmp"
  cat "$tmp" > "$file"
  rm -f "$tmp"
}

for file in "${FILES[@]}"; do
  replace "$file" '<you>' "$GH_USER"
  replace "$file" '<vous>' "$GH_USER"
done
replace LICENSE 'The Pi Control authors' "$FULL_NAME"

git config user.name "$FULL_NAME"
git config user.email "$EMAIL"
if ! git diff --quiet; then
  git add -- "${FILES[@]}" LICENSE
  git commit -q -m "Set repository owner and license holder"
fi

if ! git rebase -r --root --exec "git commit --amend --no-edit --reset-author" >/dev/null 2>&1; then
  git rebase --abort >/dev/null 2>&1 || true
  die "could not rewrite the commit authors (nothing was lost: your files are intact)"
fi

printf '\nDone / Terminé. Every commit now carries: %s <%s>\n\n' "$FULL_NAME" "$EMAIL"
printf 'Next / Étape suivante :\n  git remote add origin https://github.com/%s/picontrol.git\n  git push -u origin main\n' "$GH_USER"
