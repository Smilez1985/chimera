#!/bin/sh
# Gegenprobe zu test-source.sh (Regel 9): je eine Zusage von lib/source.sh
# verfaelschen, der Test muss an der erwarteten Stelle rot werden.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HERE/lib/source.sh"
TEST="$HERE/tests/test-source.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-source-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Quelle ===\n'

if CHIMERA_SOURCE_LIB="$LIB" sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
fi

mutation() {
	_m="$G/$1.sh"
	sed "$2" "$LIB" >"$_m"
	if cmp -s "$LIB" "$_m"; then bad "$1: Mutation griff nicht"; return; fi
	if CHIMERA_SOURCE_LIB="$_m" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $3" "$G/$1.txt"; then
		ok "$1: rot bei '$3'"
	else
		bad "$1: rot, aber nicht bei '$3'"; grep 'FAIL' "$G/$1.txt" | head -3
	fi
}

# M1: Version vor Hash -- gleicher Inhalt, hoehere VERSION wuerde kopieren.
mutation version-vor-hash \
	's|^	\[ "$1" = "$2" \] \&\& { echo gleich; return; }$|	[ "$3" = "$4" ] \&\& [ "$1" = "$2" ] \&\& { echo gleich; return; }|' \
	"gleicher Hash, andere VERSION -> nichts"

# M2: Downgrade ohne Flag erlaubt.
mutation downgrade-frei \
	's|if \[ "$5" = true \]; then echo downgrade|if true; then echo downgrade|' \
	"aeltere VERSION -> abgelehnt"

# M3: sort -V ohne Umschreiben -- 0.1.0-pre galte als neuer als 0.1.0.
mutation pre-ungeordnet \
	"s|tr '-' '~'|cat|g" \
	"0.1.0-pre < 0.1.0"

# M4: .git zaehlt mit -- jeder Klon saehe anders aus als ein Zip.
mutation git-im-hash \
	"s|^_SRC_AUSSCHLUSS='.git |_SRC_AUSSCHLUSS='|" \
	"anderer Ort, .git, Bytecode -> gleicher Hash"

# M5: Zweigspitze statt Tags.
mutation zweigspitze \
	"s|grep -E '^v\[0-9\]+\\\\.\[0-9\]+\\\\.\[0-9\]+\$'|grep -E '.'|" \
	"online: source/ = hoechster Tag 0.10.0"

# M6: Kopie ungeprueft getauscht.
mutation kopie-ungeprueft \
	's|^	if \[ -z "$_sk_ist" \] \|\| \[ "$_sk_ist" != "$_sk_soll" \]; then$|	if false; then|' \
	"Kopie weicht ab: source/ unveraendert"

# M7: abgebrochener Tausch nicht geheilt.
mutation keine-heilung \
	's|^		mv "$1.alt" "$1"$|		:|' \
	"Tausch-Abbruch: alte Fassung wiederhergestellt"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
