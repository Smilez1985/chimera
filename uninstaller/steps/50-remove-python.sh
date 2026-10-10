#!/bin/sh
# Gegenstueck zu installer/steps/50-python.sh (Architekturregel 10l).
#
# Was Schritt 50 am System hinterlaesst, steht im Manifest:
#   verzeich  das venv (Angabe leer)
#   datei     die Verdrahtung chimera.pth (Angabe: Pruefsumme)
# Entfernt wird nur, was Schritt 50 SELBST eingetragen hat (Spalte Modul) --
# `verzeich` benutzt auch Schritt 00 (source/).
#
# Das venv und die .pth sind von Chimera angelegt, es gibt kein
# `vorher_da`: Wer sie entfernen laesst, hat sie von Chimera anlegen
# lassen. Anders als bei den Kernel-Headern (Schritt 30) nimmt der
# Rueckbau hier dem System keine Faehigkeit weg, die fremde Software
# bruchte.
#
# Exitcode: 0 in Ordnung, 1 Befund.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/manifest.sh"

CHIMERA_STEP="50-remove-python"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-python" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Python-Umgebung (venv und Verdrahtung)"

# Ziele einsammeln -- Manifest ist die Wahrheitsquelle, nicht die
# Verzeichnisstruktur. Ein venv, das nie im Manifest steht, wird hier
# NICHT angeraten, es bleibt fuer die Handarbeit.
_TD="${TMPDIR:-/tmp}"
_F="$_TD/.chimera-rm-py.$$"
: >"$_F"

manifest_list_von datei 50-python | while IFS='	' read -r _d_pfad _d_angabe; do
	case "$_d_pfad" in
		*/chimera.pth) printf '%s\n' "$_d_pfad" >>"$_F" ;;
		*) continue ;;
	esac
done

manifest_list_von verzeich 50-python | while IFS='	' read -r _v_pfad _v_angabe; do
	# Gurt: niemals eine Wurzel oder leere Zeichenkette fassen.
	case "$_v_pfad" in
		""|/|"${CHIMERA_ROOT:-/}") continue ;;
	esac
	printf '%s\n' "$_v_pfad" >>"$_F"
done

_ANZAHL="$(grep -c . "$_F" 2>/dev/null || true)"
if [ "$_ANZAHL" -eq 0 ]; then
	info "Nichts im Manifest -- keine Python-Umgebung von Chimera."
	log_close 0
	exit 0
fi

if is_dry_run; then
	info "[wuerde entfernen]:"
	while IFS= read -r _z; do info "  $_z"; done <"$_F"
	log_close 0
	exit 0
fi

BEFUND=0
while IFS= read -r _z; do
	case "$_z" in
		*/chimera.pth) rm -f "$_z" || BEFUND=1 ;;
		*)             rm -rf "$_z" || BEFUND=1 ;;
	esac
	# Am Ergebnis pruefen, nicht am Exitcode.
	if [ -e "$_z" ]; then
		warn "blieb stehen: $_z"
		BEFUND=1
	else
		info "entfernt: $_z"
	fi
done <"$_F"
rm -f "$_F"

log_close "$BEFUND"
exit "$BEFUND"
