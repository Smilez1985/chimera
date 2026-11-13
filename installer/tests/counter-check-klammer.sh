#!/bin/sh
# Gegenprobe zu test-klammer-lauf.sh (Regel 9).
#
# Drei Zusagen, drei Verfaelschungen. Jede muss den Test an der ERWARTETEN
# Stelle rot machen -- ein Test, der aus einem anderen Grund rot wird, misst
# nicht, was er behauptet.
#
#   1. Der Lauf haelt die Dienste immer an (nicht nur bei neuem Stand).
#   2. Die Klammer zeigt dabei das Update-Gesicht.
#   3. Der Selbstneustart verliert die Klammer nicht (uebernommene Klammer
#      hat Vorrang vor einem zweiten Anhalten).

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
TEST="$HERE/tests/test-klammer-lauf.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-klammer-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Klammer im Lauf ===\n'

if sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
	tail -6 "$G/basis.txt"
fi

# Eine Kopie des Installers mit einer Verfaelschung in einer Datei.
# $1 Name, $2 Datei (relativ zum installer/), $3 sed-Ausdruck, $4 erwarteter
# Pruefpunkt (Text aus "FAIL  ...") je Fall.
kopie() {
	_k="$G/$1"
	rm -rf "$_k"
	mkdir -p "$_k"
	cp "$HERE/chimera-install" "$_k/chimera-install"
	cp -r "$HERE/lib" "$_k/lib"
	cp -r "$HERE/steps" "$_k/steps"
	printf '%s\n' "$_k"
}

mutation() {
	_name="$1"; _datei="$2"; _sed="$3"; shift 3
	_k="$(kopie "$_name")"
	sed "$_sed" "$_k/$_datei" >"$_k/$_datei.neu"
	if cmp -s "$_k/$_datei" "$_k/$_datei.neu"; then
		bad "$_name: Mutation griff nicht"; return
	fi
	mv "$_k/$_datei.neu" "$_k/$_datei"
	if CHIMERA_KLAMMER_BAUM="$_k" sh "$TEST" >"$G/$_name.txt" 2>&1; then
		bad "$_name: Test blieb gruen"
		return
	fi
	_alle=1
	for _erwartet in "$@"; do
		if grep -q "FAIL  $_erwartet" "$G/$_name.txt"; then
			ok "$_name: rot bei '$_erwartet'"
		else
			bad "$_name: nicht rot bei '$_erwartet'"; _alle=0
		fi
	done
	[ "$_alle" = 1 ] || grep 'FAIL' "$G/$_name.txt" | head -3
}

# M1: Die alte Bedingung zurueck -- Klammer nur, wenn sich etwas aendert.
# Gemessen wird das an einem Kriterium, das im Test immer wahr ist: der
# Quellstand wird als "gleich" behauptet, also bleibt klammer_noetig falsch.
mutation klammer-nur-bei-aenderung chimera-install \
	's|^	klammer_an \|\| { log_close 2; exit 2; }$|	if false; then klammer_an \|\| { log_close 2; exit 2; }; fi|' \
	"Zweitlauf: Dienste trotzdem angehalten" \
	"aus source/: Dienste angehalten"

# M2: Gesicht nicht mehr setzen -- die Dienste gehen trotzdem.
mutation ohne-gesicht lib/helfer.sh \
	's|^		if _ka_aus="$(python3 "$_ka_gesicht" "${CHIMERA_SITZUNG_SOCKET:-/run/chimera/sitzung.sock}" UPDATE 2>&1)"; then$|		if _ka_aus="Gesicht gesetzt"; then|' \
	"Erstlauf: Gesicht UPDATE geschickt" \
	"Zweitlauf: Gesicht UPDATE geschickt"

# M3: Uebernahme wieder hinter den Klammeraufruf -- der neue Prozess nach dem
# Neustart ruft klammer_an erneut auf, findet alles "inactive", leert die
# Merkerdatei und startet am Ende nichts.
mutation neustart-vergisst-klammer chimera-install \
	's|^if \[ "${CHIMERA_KLAMMER:-0}" = 1 \] \&\& \[ -f "$(_klammer_datei)" \]; then$|if false; then|' \
	"Erstlauf: Dienste wieder gestartet"

printf '\n=== Ergebnis: %s ok, %s FAIL ===\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ] || exit 1
exit 0
