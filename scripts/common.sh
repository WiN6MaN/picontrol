#!/usr/bin/env bash
# Shared helpers for install.sh and uninstall.sh. / Fonctions communes à install.sh et uninstall.sh.
# shellcheck disable=SC2034  # variables are used by the scripts that source this file

# Every path can be overridden, which lets the test-suite run the installer in a sandbox.
# Chaque chemin peut être redéfini : les tests exécutent l'installateur dans un bac à sable.
PREFIX="${PICONTROL_PREFIX:-/opt/picontrol}"
ETC_DIR="${PICONTROL_ETC:-/etc/picontrol}"
BIN_DIR="${PICONTROL_BIN:-/usr/local/bin}"
AUTOSTART="${PICONTROL_AUTOSTART:-/opt/retropie/configs/all/autostart.sh}"
RETROARCH_CFG="${PICONTROL_RETROARCH_CFG:-/opt/retropie/configs/all/retroarch.cfg}"
LOG_FILE="${PICONTROL_LOGFILE:-/var/log/picontrol.log}"
RUN_USER="${PICONTROL_USER:-${SUDO_USER:-pi}}"
BEGIN_MARK="# >>> picontrol (managed block) >>>"
END_MARK="# <<< picontrol <<<"
DRY_RUN=0

say()  { printf '%s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# run CMD...: execute, or only print in --dry-run mode.
run() {
  if [ "$DRY_RUN" = 1 ]; then
    say "[dry-run] $*"
  else
    "$@"
  fi
}

need_root() {
  if [ "${PICONTROL_SANDBOX:-0}" != 1 ] && [ "$(id -u)" -ne 0 ]; then
    die "run this script with sudo / lancez ce script avec sudo"
  fi
}

# backup_once FILE: keep the very first original as FILE.picontrol-bak.
backup_once() {
  local file=$1
  if [ -f "$file" ] && [ ! -f "$file.picontrol-bak" ]; then
    run cp -p "$file" "$file.picontrol-bak"
  fi
}

# remove_block FILE: delete the managed block (if any) from FILE, in place.
remove_block() {
  local file=$1 tmp
  [ -f "$file" ] || return 0
  grep -qF "$BEGIN_MARK" "$file" || return 0
  if [ "$DRY_RUN" = 1 ]; then
    say "[dry-run] remove the picontrol block from $file"
    return 0
  fi
  tmp=$(mktemp)
  sed "/^${BEGIN_MARK//\//\\/}\$/,/^${END_MARK//\//\\/}\$/d" "$file" > "$tmp"
  cat "$tmp" > "$file"   # write in place: keeps owner and permissions
  rm -f "$tmp"
}

parse_common_flag() {
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    *) return 1 ;;
  esac
}
