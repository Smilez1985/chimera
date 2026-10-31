#!/bin/sh
# Gegenprobe zu test-tls-voraussetzungen.sh (Regel 9): je eine Zusage
# verfaelschen, der Test muss an der erwarteten Stelle rot werden.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
TEST="$HERE/tests/test-tls-voraussetzungen.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-tls-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe TLS-Voraussetzungen ===\n'

if sh "$TEST" >"$G/basis.txt" 2>&1; then ok "unveraendert gruen"
else bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"; fi

# $1 Name, $2 Quelle (detect|pakete), $3 sed-Ausdruck, $4 erwartete rote Stelle
mutation() {
	case "$2" in
		detect) _q="$HERE/lib/detect.sh"; _v=CHIMERA_TLS_DETECT ;;
		pakete) _q="$HERE/steps/20-install-packages.sh"; _v=CHIMERA_TLS_PAKETE ;;
	esac
	_m="$G/$1.sh"
	sed "$3" "$_q" >"$_m"
	if cmp -s "$_q" "$_m"; then bad "$1: Mutation griff nicht"; return; fi
	if env "$_v=$_m" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $4" "$G/$1.txt"; then
		ok "$1: rot bei '$4'"
	else
		bad "$1: rot, aber nicht bei '$4'"; grep 'FAIL' "$G/$1.txt" | head -3
	fi
}

# M1: ca-certificates wieder aus der Liste (alter Stand).
mutation ohne-cacerts pakete \
	'/^ca-certificates\t/d' \
	"ca-certificates fehlt bei den zwingenden Paketen"

# M2: Nachweis nur auf den Paketstand statt auf das Buendel.
mutation nachweis-paketstand pakete \
	's|test -s /etc/ssl/certs/ca-certificates.crt|dpkg -s ca-certificates|' \
	"Nachweis prueft das Buendel"

# M3: Nachweis akzeptiert ein leeres Buendel (-s -> -e).
mutation nachweis-leer-ok pakete \
	's|test -s /etc/ssl/certs/ca-certificates.crt|test -e /etc/ssl/certs/ca-certificates.crt|' \
	"leeres Buendel: Nachweis bestand"

# M4: Uhr: Untergrenze verschoben, 1970 gilt als plausibel.
mutation uhr-grenze-offen detect \
	's|CHIMERA_UHR_MIN:=1767225600|CHIMERA_UHR_MIN:=0|' \
	"Uhr 1970: unplausibel"

# M5: Uhr: genau an der Grenze faelschlich unplausibel (-lt -> -le).
mutation uhr-grenze-le detect \
	's|-lt "\$CHIMERA_UHR_MIN"|-le "$CHIMERA_UHR_MIN"|' \
	"Uhr genau an der Untergrenze"

# M6: Uhr: unlesbar wird als plausibel durchgewinkt.
mutation uhr-unlesbar-ok detect \
	's|Uhr nicht lesbar -- nicht pruefbar, ob TLS gelingt.";\n*||;/Uhr nicht lesbar/{n;s|return 1|return 0|}' \
	"Uhr nicht lesbar: Befund"

# M7: Modul 10 ruft die Uhrpruefung nicht auf (offenes Ende).
_m10="$G/m10.sh"
sed 's|^uhr_pruefen \|\| UHR_BEFUND=1$|:|' "$HERE/steps/10-check-system.sh" >"$_m10"
if cmp -s "$HERE/steps/10-check-system.sh" "$_m10"; then bad "m10-ohne-aufruf: Mutation griff nicht"
else
	# Der Test liest Modul 10 am festen Ort; fuer die Mutation eine Kopie des
	# Baums mit verfaelschtem Schritt.
	mkdir -p "$G/baum"
	cp -R "$HERE/lib" "$HERE/steps" "$HERE/tests" "$G/baum/"
	cp "$_m10" "$G/baum/steps/10-check-system.sh"
	if sh "$G/baum/tests/test-tls-voraussetzungen.sh" >"$G/m10.txt" 2>&1; then
		bad "m10-ohne-aufruf: Test blieb gruen"
	elif grep -q "FAIL  Modul 10 ruft die Uhrpruefung nicht auf" "$G/m10.txt"; then
		ok "m10-ohne-aufruf: rot bei 'Modul 10 ruft die Uhrpruefung nicht auf'"
	else
		bad "m10-ohne-aufruf: rot, aber nicht an der erwarteten Stelle"
	fi
fi

printf '\nErgebnis: %s ok, %s fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
