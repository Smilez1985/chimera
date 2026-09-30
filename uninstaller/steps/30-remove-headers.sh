#!/bin/sh
# Gegenstueck zu installer/steps/30-install-headers.sh
# (Architekturregel 10l).
#
# Die Kernel-Header sind ein einzelnes Paket (raspberrypi-kernel-headers
# bzw. linux-headers-*). Der Rueckbau ist derselbe Fall wie bei Schritt 20
# und folgt denselben Regeln: nur was `neu` ist, und nur auf ausdruecklichen
# Wunsch.
#
# Eigener Grund, hier besonders zurueckhaltend zu sein: Die Header werden
# gebraucht, sobald irgendein anderes Kernelmodul auf dem System gebaut
# werden soll -- DKMS-Pakete etwa. Sie zu entfernen, weil Chimera geht,
# nimmt dem System eine Faehigkeit, die nichts mit Chimera zu tun hat.
#
# Exitcode: 0 in Ordnung, 1 Befund.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/manifest.sh"

CHIMERA_STEP="30-remove-headers"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-headers" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Kernel-Header"

# Die Header stehen als Paket im Manifest, eingetragen von Schritt 30 ueber
# manifest_apt. Sie sind daran erkennbar, dass der Name "headers" enthaelt
# -- eine eigene Manifestart dafuer waere Uebergenauigkeit, die Liste ist
# klein und der Name eindeutig.
HEADER_NEU=""
_TD="${TMPDIR:-/tmp}"
_F="$_TD/.chimera-rm-hdr.$$"
: >"$_F"

manifest_list paket | while IFS='	' read -r _h_name _h_angabe; do
	case "$_h_name" in
		*headers*) : ;;
		*) continue ;;
	esac
	case "$_h_angabe" in
		neu) printf '%s ' "$_h_name" >>"$_F" ;;
		vorher_da) info "bleibt (war vorher da): $_h_name" ;;
	esac
done

HEADER_NEU="$(cat "$_F" 2>/dev/null || true)"
rm -f "$_F"

if [ -z "$HEADER_NEU" ]; then
	info "Keine von Chimera installierten Header im Manifest."
	log_close 0
	exit 0
fi

if [ "${KEEP_PACKAGES:-1}" = "1" ]; then
	info "Von Chimera installiert:$HEADER_NEU"
	info "Bleibt stehen. Andere Kernelmodule (DKMS) brauchen die Header"
	info "ebenfalls -- sie zu entfernen nimmt dem System eine Faehigkeit,"
	info "die nichts mit Chimera zu tun hat."
	info "Wer sie trotzdem weg will:"
	info "  chimera-uninstall --only 30 --remove-packages"
	log_close 0
	exit 0
fi

if is_dry_run; then
	info "[wuerde entfernen]$HEADER_NEU"
	log_close 0
	exit 0
fi

BEFUND=0
log "Wird entfernt:$HEADER_NEU"

if command -v apt-get >/dev/null 2>&1; then
	DEBIAN_FRONTEND=noninteractive apt-get remove -y $HEADER_NEU || BEFUND=1
elif command -v apk >/dev/null 2>&1; then
	apk del $HEADER_NEU || BEFUND=1
else
	warn "Keine bekannte Paketverwaltung -- von Hand:$HEADER_NEU"
	BEFUND=1
fi

# Am Ergebnis pruefen, nicht am Exitcode.
if [ "$BEFUND" -eq 0 ]; then
	for _p in $HEADER_NEU; do
		if manifest_package_present "$_p"; then
			warn "Trotz Erfolgsmeldung noch installiert: $_p"
			BEFUND=1
		fi
	done
fi

[ "$BEFUND" -eq 0 ] && info "entfernt:$HEADER_NEU"

log_close "$BEFUND"
exit "$BEFUND"
