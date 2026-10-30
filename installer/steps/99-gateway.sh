#!/bin/sh
# Chimera installer -- Modul 99: Gateway (Nutzer chimera-tor, Socket, Unit).
#
# DESIGN Regel 5n. Braucht das Binary aus Schritt 55 und den Dienstnutzer
# aus Schritt 98 (der Socket gehoert dessen Gruppe). Die Logik steht in
# lib/gateway.sh (pruefbar ohne systemd), hier wird nur aufgerufen.
#
# Exitcode:
#   0  Das Gateway antwortet nachweislich am Socket
#   1  Befund: kein Binary (Schritt 55) oder antwortet nicht -- der Dienst
#      laeuft ohne Gateway weiter, solange er die Anbieter noch selbst haelt
#   2  abgebrochen -- Voraussetzung fehlt

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/service.sh"
. "$_HERE/lib/gateway.sh"

CHIMERA_STEP="99-gateway"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "gateway" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Chimera Gateway"
log ""

if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "Dieses Modul legt einen Systemnutzer und systemd-Units an --"
	err "das geht nur als Verwalter."
	err "  sudo sh $0"
	log_close 2; exit 2
fi

set +e
gateway_einrichten
rc=$?
set -e

log ""
case "$rc" in
	0) log "Ergebnis: Gateway antwortet nachweislich." ;;
	1) warn "Ergebnis: Gateway nicht nachweislich in Betrieb." ;;
	*) err "Ergebnis: abgebrochen." ;;
esac
log_close "$rc"
exit "$rc"
