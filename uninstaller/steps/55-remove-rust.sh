#!/bin/sh
# Gegenstueck zu installer/steps/55-rust.sh (Architekturregel 10l).
#
# Was Schritt 55 hinterlaesst, steht im Manifest (Modul 55-rust):
#   datei     /opt/chimera/bin/chimera-tor   Angabe: SHA-256 beim Ablegen
#   verzeich  /opt/chimera/bin               nur, wenn Schritt 55 es anlegte
# Entfernt wird die Datei nur, wenn sie noch die Pruefsumme hat, die
# Schritt 55 eintrug. Hat jemand sie ersetzt, ist es nicht mehr unsere --
# sie bleibt liegen und der Rueckbau meldet es. Das Verzeichnis geht nur weg,
# wenn es leer ist.
#
# Exitcode: 0 in Ordnung, 1 Befund.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/network.sh"
. "$_HERE/installer/lib/manifest.sh"

CHIMERA_STEP="55-remove-rust"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-rust" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Rust-Binary (chimera-tor)"

BEFUND=0

_F="$(tmp_path chimera-rm-rust)" || { log_close 1; exit 1; }
manifest_list_von datei 55-rust >"$_F"
_V="$(tmp_path chimera-rm-rust-v)" || { rm -f "$_F"; log_close 1; exit 1; }
manifest_list_von verzeich 55-rust >"$_V"
trap 'rm -f "$_F" "$_V"' EXIT INT TERM

if [ ! -s "$_F" ] && [ ! -s "$_V" ]; then
	info "Nichts im Manifest -- kein Binary von Chimera."
	log_close 0; exit 0
fi

while IFS='	' read -r _pfad _soll; do
	[ -n "$_pfad" ] || continue
	if [ ! -e "$_pfad" ] && [ ! -L "$_pfad" ]; then
		info "schon weg: $_pfad"; continue
	fi
	if [ -n "$_soll" ] && [ "$(network_checksum "$_pfad")" != "$_soll" ]; then
		warn "nicht mehr unsere Datei (Pruefsumme weicht ab), bleibt liegen: $_pfad"
		BEFUND=1; continue
	fi
	if is_dry_run; then info "[wuerde entfernen] $_pfad"; continue; fi
	rm -f "$_pfad"
	# Am Ergebnis pruefen, nicht am Exitcode.
	if [ -e "$_pfad" ]; then warn "blieb stehen: $_pfad"; BEFUND=1
	else info "entfernt: $_pfad"; fi
done <"$_F"

while IFS='	' read -r _d _rest; do
	[ -n "$_d" ] || continue
	[ -d "$_d" ] || continue
	if is_dry_run; then info "[wuerde entfernen, wenn leer] $_d"; continue; fi
	if rmdir "$_d" 2>/dev/null; then info "entfernt: $_d"
	else info "bleibt (nicht leer): $_d"; fi
done <"$_V"

log_close "$BEFUND"
exit "$BEFUND"
