#!/bin/sh
# Gegenstueck zu installer/steps/20-install-packages.sh
# (Architekturregel 10l).
#
# Entfernt NUR Pakete, die im Manifest als `neu` stehen. Alles mit
# `vorher_da` bleibt -- und das ist der wichtigste Teil dieses Schritts,
# nicht eine Feinheit.
#
# Warum: Die Liste enthaelt git, python3, make, gcc, alsa-utils. Auf einem
# gewachsenen System war das meiste davon schon da. Ein Rueckbau, der nicht
# unterscheidet, deinstalliert dem Nutzer seine Werkzeugkette -- samt allem,
# was per Abhaengigkeit mitgeht. Das ist kein Aufraeumen, das ist Schaden.
#
# Standardmaessig werden Pakete darum NICHT entfernt: Der Gewinn (ein paar
# Megabyte) steht in keinem Verhaeltnis zum Risiko. Wer es will, sagt es
# ausdruecklich -- ohne --remove-packages werden die Kandidaten nur genannt.
#
# Exitcode: 0 in Ordnung, 1 Befund.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/manifest.sh"

CHIMERA_STEP="20-remove-packages"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-packages" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

BEFUND=0

log "Pakete"

# Zwei Listen trennen. Ueber Dateien, nicht ueber Variablen: Die Schleife
# laeuft in einer Pipe und damit in einer Subshell -- dort gesetzte
# Variablen sind draussen weg. Derselbe Fehler steckte einmal in Schritt 20
# und liess vorhandene Pakete als fehlend erscheinen.
_TD="${TMPDIR:-/tmp}"
_F_NEU="$_TD/.chimera-rm-neu.$$"
_F_ALT="$_TD/.chimera-rm-alt.$$"
: >"$_F_NEU"
: >"$_F_ALT"

manifest_list paket | while IFS='	' read -r _p_name _p_angabe; do
	[ -n "$_p_name" ] || continue
	case "$_p_angabe" in
		neu)       printf '%s ' "$_p_name" >>"$_F_NEU" ;;
		vorher_da) printf '%s ' "$_p_name" >>"$_F_ALT" ;;
		*)         warn "Paketeintrag nicht deutbar: $_p_name ($_p_angabe)" ;;
	esac
done

NEU="$(cat "$_F_NEU" 2>/dev/null || true)"
ALT="$(cat "$_F_ALT" 2>/dev/null || true)"
rm -f "$_F_NEU" "$_F_ALT"

if [ -n "$ALT" ]; then
	info "bleibt (war vor Chimera da):$ALT"
fi

if [ -z "$NEU" ]; then
	info "Kein Paket wurde von Chimera neu installiert -- nichts zu tun."
	log_close 0
	exit 0
fi

# KEEP_PACKAGES wird vom Laeufer gesetzt. Die Vorgabe ist "behalten": Der
# vorsichtige Weg ist der voreingestellte, nicht der, den man extra
# absichern muss.
if [ "${KEEP_PACKAGES:-1}" = "1" ]; then
	info "Von Chimera installiert:$NEU"
	info ""
	info "Diese Pakete bleiben stehen. Sie zu entfernen bringt wenige"
	info "Megabyte und kann per Abhaengigkeit mehr mitreissen als"
	info "erwartet -- deshalb ist Behalten die Vorgabe."
	info "Wer sie wirklich weg will:"
	info "  chimera-uninstall --only 20 --remove-packages"
	log_close 0
	exit 0
fi

log "Wird entfernt:$NEU"

if is_dry_run; then
	info "[wuerde entfernen]$NEU"
	log_close 0
	exit 0
fi

# `apt-get remove` statt `purge`: purge loescht auch Konfigurationsdateien
# anderer Herkunft. Und `--auto-remove` bleibt bewusst weg -- es entscheidet
# selbst, was noch gebraucht wird, und hat dabei schon Systeme entkernt.
if command -v apt-get >/dev/null 2>&1; then
	if DEBIAN_FRONTEND=noninteractive apt-get remove -y $NEU; then
		info "entfernt:$NEU"
	else
		warn "Entfernen fehlgeschlagen -- die Pakete bleiben."
		BEFUND=1
	fi
elif command -v apk >/dev/null 2>&1; then
	if apk del $NEU; then
		info "entfernt:$NEU"
	else
		warn "Entfernen fehlgeschlagen -- die Pakete bleiben."
		BEFUND=1
	fi
else
	warn "Keine bekannte Paketverwaltung gefunden."
	warn "Von Hand zu entfernen:$NEU"
	BEFUND=1
fi

# Ergebnis pruefen, nicht den Exitcode. `apt-get remove` meldet Erfolg auch
# fuer ein Paket, das es gar nicht angefasst hat.
if [ "$BEFUND" -eq 0 ]; then
	_REST=""
	for _p in $NEU; do
		manifest_package_present "$_p" && _REST="$_REST $_p"
	done
	if [ -n "$_REST" ]; then
		warn "Trotz Erfolgsmeldung noch installiert:$_REST"
		BEFUND=1
	fi
fi

log_close "$BEFUND"
exit "$BEFUND"
