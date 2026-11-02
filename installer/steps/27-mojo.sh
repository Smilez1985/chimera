#!/bin/sh
# Chimera installer -- Modul 27: Mojo (Meldeunit, Zeitgeber, Drop-ins).
#
# DESIGN, Regel "Mojo". Braucht das Binary aus Schritt 55. Die Logik steht in
# lib/mojo.sh (pruefbar ohne systemd), hier wird nur aufgerufen.
#
# Exitcode:
#   0  Meldeunit, Zeitgeber und Drop-ins sind da und wirken (von systemd bestaetigt)
#   1  Befund: kein Binary oder ein Drop-in wirkt nicht -- die Dienste laufen weiter
#   2  abgebrochen -- Voraussetzung fehlt

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/service.sh"
. "$_HERE/lib/mojo.sh"

CHIMERA_STEP="27-mojo"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "mojo" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Chimera Mojo"
log ""

if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "Dieses Modul legt systemd-Units an -- das geht nur als Verwalter."
	err "  sudo sh $0"
	log_close 2; exit 2
fi

set +e
mojo_einrichten
rc=$?
set -e

log ""
case "$rc" in
	0) log "Ergebnis: Mojo ist eingerichtet und wirkt." ;;
	1) warn "Ergebnis: Mojo nicht nachweislich in Betrieb." ;;
	*) err "Ergebnis: abgebrochen." ;;
esac
log_close "$rc"
exit "$rc"
