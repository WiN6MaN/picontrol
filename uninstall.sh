#!/usr/bin/env bash
# Pi Control uninstaller. / Désinstallateur de Pi Control.
#
# Usage: sudo ./uninstall.sh [--dry-run] [--purge]
# Removes the code, the launcher and the autostart block. Your configuration and log are kept
# unless you pass --purge. retroarch.cfg is left as it is (a backup, retroarch.cfg.picontrol-bak, exists).
# Supprime le code, le lanceur et le bloc d'autostart ; la configuration et le journal sont conservés sauf --purge.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
. "$SRC_DIR/scripts/common.sh"

PURGE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --purge) PURGE=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) parse_common_flag "$1" || die "unknown option: $1" ;;
  esac
  shift
done

need_root
say "Removing the autostart block"
remove_block "$AUTOSTART"
say "Removing $BIN_DIR/picontrol and $PREFIX"
run rm -f "$BIN_DIR/picontrol"
run rm -rf "$PREFIX"
if [ "$PURGE" = 1 ]; then
  say "Removing the configuration and the log"
  run rm -rf "$ETC_DIR"
  run rm -f "$LOG_FILE" "$LOG_FILE.1" "$LOG_FILE.2"
else
  say "Kept: $ETC_DIR and $LOG_FILE (use --purge to remove them)"
fi
say "Done. Reboot to stop the running service / Terminé : redémarrez pour arrêter le service."
