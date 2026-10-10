#!/bin/sh
# Gegenstueck zu installer/steps/00-source.sh (Architekturregel 10l).
#
# Schritt 00 legt /opt/chimera/source an (Manifest: verzeich). Der Rueckbau
# entfernt es zuletzt -- der Deinstallierer laeuft rueckwaerts, und solange
# andere Schritte zurueckbauen, darf ihre Quelle noch da sein.
#
# Was bleibt (DESIGN Regel 10r): Protokolle, config/, die Daten im Home.
#
# Exitcode: 0 in Ordnung, 1 Befund.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/manifest.sh"

CHIMERA_STEP="00-remove-source"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-source" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Quelle (source/)"

ZIEL="$(rootpath "$CHIMERA_SOURCE")"
BEFUND=0

# Nur was im Manifest steht -- ein Verzeichnis gleichen Namens ohne
# Eintrag hat jemand anders angelegt (Regel 10o).
if ! manifest_list_von verzeich 00-source | cut -f1 | grep -qxF "$ZIEL"; then
	info "Nicht im Manifest -- nichts zu tun."
	log_close 0; exit 0
fi

for _p in "$ZIEL" "$ZIEL.neu" "$ZIEL.alt"; do
	[ -e "$_p" ] || continue
	if is_dry_run; then info "[wuerde entfernen] $_p"; continue; fi
	rm -rf "$_p"
	if [ -e "$_p" ]; then warn "blieb stehen: $_p"; BEFUND=1
	else info "entfernt: $_p"; fi
done

log_close "$BEFUND"
exit "$BEFUND"
