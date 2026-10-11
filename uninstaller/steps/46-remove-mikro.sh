#!/bin/sh
# Gegenstueck zu installer/steps/46-mikro.sh (Architekturregel 10l).
#
# Was Schritt 46 hinterlaesst, steht im Manifest (Art datei, Modul 46-mikro):
#   state/mikro.json                         Messung (Angabe: Pruefsumme)
#   /etc/alsa/conf.d/50-chimera-mikro.conf   Aufnahmegeraet chimera_mikro
# Entfernt wird nur, was Schritt 46 SELBST eingetragen hat. Beide Dateien sind
# von Chimera angelegt -- es gibt kein "vorher_da".
#
# Exitcode: 0 in Ordnung, 1 Befund.
set -eu
_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/manifest.sh"
CHIMERA_STEP="46-remove-mikro"; export CHIMERA_STEP
[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-mikro" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."
log "Mikrofone (Messung und Aufnahmegeraet)"

_F="$(tmp_path chimera-rm-mikro)" || { log_close 1; exit 1; }
manifest_list_von datei 46-mikro | while IFS='	' read -r _pfad _angabe; do
	case "$_pfad" in
		*/mikro.json|*/50-chimera-mikro.conf) printf '%s\n' "$_pfad" >>"$_F" ;;
		*) continue ;;
	esac
done
if [ ! -s "$_F" ]; then
	rm -f "$_F"
	info "Nichts im Manifest -- kein Aufnahmegeraet von Chimera."
	log_close 0; exit 0
fi
if is_dry_run; then
	info "[wuerde entfernen]:"
	while IFS= read -r _z; do info "  $_z"; done <"$_F"
	rm -f "$_F"
	log_close 0; exit 0
fi
BEFUND=0
while IFS= read -r _z; do
	rm -f "$_z" || BEFUND=1
	# Am Ergebnis pruefen, nicht am Exitcode.
	if [ -e "$_z" ]; then
		warn "blieb stehen: $_z"
		BEFUND=1
	else
		info "entfernt: $_z"
	fi
done <"$_F"
rm -f "$_F"
log_close "$BEFUND"; exit "$BEFUND"
