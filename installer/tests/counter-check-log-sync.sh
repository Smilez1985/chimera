#!/bin/sh
# Gegenprobe zu test-log-sync.sh (Regel 9): je eine Zusage von common.sh
# verfaelschen, der Test muss an der erwarteten Stelle rot werden. Eine
# Mutation, die die Datei nicht aendert, ist selbst ein Fehler.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HERE/lib/common.sh"
TEST="$HERE/tests/test-log-sync.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-logsync-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Protokollweg ===\n'

if CHIMERA_COMMON_LIB="$LIB" sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
fi

mutation() {
	_m="$G/$1.sh"
	sed "$2" "$LIB" >"$_m"
	if cmp -s "$LIB" "$_m"; then
		bad "$1: Mutation griff nicht"; return
	fi
	if CHIMERA_COMMON_LIB="$_m" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $3" "$G/$1.txt"; then
		ok "$1: rot bei '$3'"
	else
		bad "$1: rot, aber nicht bei '$3'"; grep 'FAIL' "$G/$1.txt" | head -3
	fi
}

# M1: direkt auf die Karte schreiben (alter Zustand: ein Ort).
mutation direkt-auf-karte \
	's|CHIMERA_LOG_DIR="${CHIMERA_ROOT}${CHIMERA_RUNLOG}/installer"|CHIMERA_LOG_DIR="${CHIMERA_ROOT}${CHIMERA_LOGS_INSTALLER}"|' \
	"RAM-Ordner liegt unter /run"

# M2: log_close gleicht nicht ab.
mutation kein-abgleich \
	's|^		if log_sync; then$|		if true; then|' \
	"nach log_close genau ein Protokoll"

# M3: jeder Schritt gleicht ab, nicht nur der Oeffner.
mutation jeder-gleicht-ab \
	's|"${_CHIMERA_LOG_EIGEN:-0}" = 1|1 = 1|' \
	"Schritt mit geerbtem Protokoll"

# M4: ohne cmp -- alles wird jedes Mal neu geschrieben.
mutation ohne-cmp \
	's|^		cmp -s "$_ls_f" "$_ls_z" 2>/dev/null && continue$|		:|' \
	"unveraendertes Protokoll wird nicht neu geschrieben"

# M5: Fehler beim Kopieren verschluckt (stiller Erfolg).
mutation fehler-verschluckt \
	's|^			_ls_rc=1$|			:|' \
	"unbeschreibbares Ziel"

# M6: Ergebnis nicht am Ziel geprueft (nur Exitcode von mv).
mutation ohne-zielpruefung \
	's|mv -f "$_ls_t" "$_ls_z" 2>/dev/null \&\& \[ -f "$_ls_z" \] \&\&|mv -f "$_ls_t" "$_ls_z" 2>/dev/null \&\& true \&\&|; s|^		   cmp -s "$_ls_f" "$_ls_z"; then$|		   true; then|' \
	"unbeschreibbares Ziel"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
