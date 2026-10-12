#!/bin/sh
# Gegenprobe zu test-source-hash.sh (Regel 9): je eine Zusage von
# source_hash bzw. der Schritte 00/50 verfaelschen -- der Test muss an der
# erwarteten Stelle rot werden.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HERE/lib/source.sh"
STEP00="$HERE/steps/00-source.sh"
STEP50="$HERE/steps/50-python.sh"
TEST="$HERE/tests/test-source-hash.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-hash-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Pruefsumme ===\n'

if sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
	grep 'FAIL' "$G/basis.txt" | head -3
fi

# $1 Name, $2 Datei (lib|00|50), $3 sed-Ausdruck, $4 erwartete FAIL-Zeile
mutation() {
	case "$2" in
		lib) _orig="$LIB";    _var=CHIMERA_SOURCE_LIB ;;
		00)  _orig="$STEP00"; _var=CHIMERA_SOURCE_STEP ;;
		50)  _orig="$STEP50"; _var=CHIMERA_PYTHON_STEP ;;
	esac
	_m="$G/$1.sh"
	sed "$3" "$_orig" >"$_m"
	if cmp -s "$_orig" "$_m"; then bad "$1: Mutation griff nicht"; return; fi
	if env "$_var=$_m" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $4" "$G/$1.txt"; then
		ok "$1: rot bei '$4'"
	else
		bad "$1: rot, aber nicht bei '$4'"; grep 'FAIL' "$G/$1.txt" | head -3
	fi
}

# M1: Summe ohne Pfade -- nur die Inhalte gehen ein (andere Summe).
mutation ohne-pfad lib \
	's/| sort -k 2 | sha256sum | cut/| cut -c1-64 | sort | sha256sum | cut/' \
	"Festwert (Werkzeuge der Umgebung)"

# M2: Backslash-Namen in den Sammelaufruf -- GNU maskiert, die Summe haengt
# dann am Werkzeug. Fangbar nur, wo sha256sum maskiert (GNU); mit BusyBox
# ist die Mutation harmlos -- dann benannt statt rot.
_mt="$G/maske"; mkdir -p "$_mt"; printf 'x' >"$_mt/a\\b"
case "$(cd "$_mt" && sha256sum 'a\b')" in
	\\*) mutation maskiert-gesammelt lib \
		"s/ ! -path '\*\\\\\\\\\*' ! -path \"\*\$_sh_cr\*\" \\\\/ \\\\/" \
		"Festwert (Werkzeuge der Umgebung)" ;;
	*) printf '  --    maskiert-gesammelt: sha256sum maskiert hier nicht -- nicht pruefbar\n' ;;
esac

# M3: wieder je Datei ein Aufruf (alte Rechenart: gleiche Summe, aber
# 40 Aufrufe) -- nur die Zaehlung kann das fangen. Nimmt die Shell das
# eingebaute sha256sum, zaehlt der Test nicht: dann benannt statt rot.
if grep -q 'Aufrufzaehlung nicht moeglich' "$G/basis.txt"; then
	printf '  --    je-datei: Aufrufzaehlung in dieser Shell nicht moeglich\n'
else
	mutation je-datei lib \
		's/-exec sha256sum {} +)" || exit 1/-exec sha256sum {} \\;)" || exit 1/' \
		"40 Dateien:"
fi

# M4: Zeilenumbruch nicht ausdruecklich abgelehnt. Das zweite Netz (Zeilen
# gegen Dateien) faengt den Namen trotzdem -- rc bleibt 1. Rot wird darum
# die Benennung: ohne sie hiesse der Befund "unvollstaendig", und niemand
# saehe den Dateinamen.
mutation umbruch-still lib \
	's/^	  if \[ -n "\$_sh_lf" \]; then$/	  if false; then/' \
	"Zeilenumbruch im Namen: nicht benannt"

# M5: Zeilenzahl nicht gegen die Dateizahl geprueft.
mutation keine-zaehlung lib \
	's/^	if \[ "\$_hz_z" -ne "\$2" \]; then$/	if false; then/' \
	"Zeilen: eine fehlt -> rc 1"

# M6: Format nicht geprueft -- eine maskierte Zeile ginge in die Summe.
mutation kein-format lib \
	"s/^	if \[ \"\$_hz_z\" -gt 0 \] \&\& printf/	if false \&\& printf/" \
	"Zeilen: maskierte Zeile -> rc 1"

# M7: Schritt 00 ohne Auffangen -- set -e beendet still mit rc 1.
mutation 00-still 00 \
	's/^KAND_H="\$(source_hash "\$KAND")" || KAND_H=""$/KAND_H="$(source_hash "$KAND")"/' \
	"Schritt 00, Startbaum nicht pruefbar: rc 2"

# M8: Schritt 50 ohne Auffangen -- set -e beendet still mit rc 1.
mutation 50-still 50 \
	's/^_soll="\$(source_hash "\$REPO")" || _soll=""$/_soll="$(source_hash "$REPO")"/' \
	"Schritt 50, Quelle nicht pruefbar: rc 2"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
