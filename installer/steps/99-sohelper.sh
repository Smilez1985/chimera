#!/bin/sh
# Chimera installer -- Modul 99-sohelper: Ausfuehrer (Nutzer, Ordner, Units).
#
# DESIGN, Regel "Wer prueft, fuehrt aus". Braucht das Binary aus Schritt 55
# (und legt es ab, falls es fehlt) und die Gruppe des Agent-Dienstes aus
# Schritt 98 (der Agent ist der einzige, der fragen darf). Die Logik steht in
# lib/sohelper.sh (pruefbar ohne systemd), hier wird nur aufgerufen.
#
# Exitcode:
#   0  Der Ausfuehrer antwortet nachweislich am Socket
#   1  Befund: kein Binary oder antwortet nicht -- der Agent arbeitet wie
#      bisher mit seinen eigenen Werkzeugen weiter
#   2  abgebrochen -- Voraussetzung fehlt

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/network.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/source.sh"
. "$_HERE/lib/binary.sh"
. "$_HERE/lib/service.sh"
. "$_HERE/lib/sohelper.sh"

CHIMERA_STEP="99-sohelper"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "sohelper" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Chimera Ausfuehrer (chimera-sohelper)"
log ""

if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "Dieses Modul legt einen Systemnutzer und systemd-Units an --"
	err "das geht nur als Verwalter."
	err "  sudo sh $0"
	log_close 2; exit 2
fi

# Das Binary: derselbe Weg wie in Schritt 55 (lib/binary.sh), damit es keine
# zweite, leiser pruefende Fassung gibt (Regel 10g). Fehlt es, ist das ein
# Befund und kein Abbruch: der Agent arbeitet dann wie bisher.
BINARY_REPO="$(cd "$_HERE/.." && pwd)"
export BINARY_REPO
binary_aus_baum sohelper 99-sohelper
_ba=$?
case "$_ba" in
	2) log_close 2; exit 2 ;;
	1) warn "Ohne Binary wird der Ausfuehrer nicht eingerichtet." ;;
esac
log ""

set +e
sohelper_einrichten
rc=$?
set -e

log ""
case "$rc" in
	0) log "Ergebnis: Ausfuehrer antwortet nachweislich." ;;
	1) warn "Ergebnis: Ausfuehrer nicht nachweislich in Betrieb." ;;
	*) err "Ergebnis: abgebrochen." ;;
esac
log_close "$rc"
exit "$rc"
