#!/bin/sh
# Gegenprobe zu test-rust.sh (Regel 9).
#
# Je eine Zusage von Modul 55 oder seinem Rueckbau wird in einer KOPIE
# verfaelscht; der Test laeuft gegen die Kopie (CHIMERA_STEP_55 /
# CHIMERA_STEP_RM55 / CHIMERA_BINARY_LIB) und muss rot werden -- am
# erwarteten Pruefpunkt. Eine Mutation, die die Datei nicht veraendert, ist
# selbst ein Fehler.
#
# **Warum `lib` als Ziel (11.11.2026):** Ablegen und Pruefen des Binaries
# stehen seit `186a116`/`a8098b4` in `installer/lib/binary.sh`, nicht mehr in
# `steps/55-rust.sh`. Die Mutationen zeigten deshalb ins Leere ("Muster
# fehlt") -- elf von dreizehn -- und niemand merkte es, weil die CI die
# `counter-check-*.sh` nicht faehrt. Schritt 55 laedt die Bibliothek ueber
# `CHIMERA_BINARY_LIB`, damit die Gegenprobe wieder etwas misst.
set -eu
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
STEP="$HERE/steps/55-rust.sh"
LIB="$HERE/lib/binary.sh"
RMSTEP="$REPO/uninstaller/steps/55-remove-rust.sh"
TEST="$HERE/tests/test-rust.sh"
PASS=0; FAIL=0
: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-rust-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM
ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Rust-Binary (Modul 55) ===\n'
if sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
	tail -5 "$G/basis.txt"
fi

# $1 Name, $2 step|lib|rm, $3 alt, $4 neu, $5 erwarteter FAIL-Text
mutation() {
	_m="$G/$1"; mkdir -p "$_m"
	case "$2" in
		step) cp "$STEP" "$_m/55.sh"; _neu="$_m/55.sh"; _env="CHIMERA_STEP_55=$_neu" ;;
		lib)  cp "$LIB" "$_m/binary.sh"; _neu="$_m/binary.sh"; _env="CHIMERA_BINARY_LIB=$_neu" ;;
		rm)   cp "$RMSTEP" "$_m/55-remove.sh"; _neu="$_m/55-remove.sh"; _env="CHIMERA_STEP_RM55=$_neu" ;;
		*)    bad "$1: unbekanntes Ziel $2"; return ;;
	esac
	if ! python3 - "$_neu" "$3" "$4" <<'PY'
import sys
p, a, b = sys.argv[1:4]
s = open(p).read()
if a not in s:
    sys.exit(3)
open(p, "w").write(s.replace(a, b, 1))
PY
	then
		bad "$1: Mutation griff nicht (Muster fehlt)"
		return
	fi
	if env "$_env" sh "$TEST" >"$_m/aus.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $5" "$_m/aus.txt"; then
		ok "$1: rot bei '$5'"
	else
		bad "$1: rot, aber nicht bei '$5'"
		grep 'FAIL' "$_m/aus.txt" | head -3
	fi
}

# M1: Pruefsumme wird nicht verglichen -- eine manipulierte Datei kaeme durch.
mutation summe-egal lib \
	'if [ "$_ba_ist" != "$_ba_summe" ]; then' 'if false; then' \
	"falsche Summe: benannt"

# M2: Version wird nicht geprueft.
mutation version-egal lib \
	'if [ "$_ba_ist" != "$_ba_prog $_ba_soll_v" ]; then' 'if false; then' \
	"falsche Version: rc 2"

# M3: Laufprobe entfaellt -- ein Binary, das nie startet, wird abgelegt.
mutation ohne-laufprobe lib \
	'_ba_ist="$("$_ba_tmp/$_ba_asset" --version 2>/dev/null || true)"' '_ba_ist="$_ba_prog $_ba_soll_v"' \
	"Binary laeuft nicht: rc 2"

# M4: Architektur wird nicht geprueft.
mutation arch-egal lib \
	'	case "$_ba_arch" in
		aarch64|arm64) : ;;' '	case "aarch64" in
		aarch64|arm64) : ;;' \
	"armv7l: benannt"

# M5: Eine fremde Datei am Zielort wird ueberschrieben.
mutation fremde-datei lib \
	'		err "$_ba_bin existiert und steht nicht im Manifest -- wird nicht ueberschrieben."' \
	'		: # fremde Datei wird ueberschrieben' \
	"fremde Datei: benannt"

# M6: Idempotenz fehlt -- jeder Lauf schreibt neu.
mutation immer-schreiben lib \
	'if [ -n "$_ba_eigen" ] && [ "$_ba_eigen" = "$_ba_summe" ] && \' 'if false && \' \
	"zweiter Lauf: nicht neu geschrieben"

# M7: Alte Manifestzeile bleibt stehen (zwei Zeilen fuer dieselbe Datei).
mutation manifest-doppelt lib \
	'if [ -n "$_ba_eigen" ] && [ -z "$_ba_fremd_modul" ] && [ -f "$CHIMERA_MANIFEST" ]; then' 'if false; then' \
	"neue Fassung: eine Manifestzeile fuer die Datei"

# M8: Trockenlauf legt doch ab.
mutation trockenlauf-schreibt lib \
	'		info "[wuerde ablegen] $_ba_bin (root, 755)"
		return 0
	fi' '		info "[wuerde ablegen] $_ba_bin (root, 755)"
	fi' \
	"Trockenlauf: nichts abgelegt"

# M9: Der Hinweis auf einen neueren rust/-Baum faellt weg.
mutation ohne-hinweis lib \
	'	if [ -n "$_ba_jetzt_h" ] && [ -n "$_ba_alt_h" ] && [ "$_ba_jetzt_h" != "$_ba_alt_h" ]; then' '	if false; then' \
	"rust/ neuer: gemeldet"

# M10: Ein fehlendes Binary ist kein Befund (rc 0 statt 1).
mutation ohne-binary-kein-befund lib \
	'		if [ ! -f "$_ba_quelle" ]; then' '		if [ ! -f "$_ba_quelle" ]; then
			log_close 0; exit 0' \
	"kein Binary: rc 1"

# M11: Rueckbau loescht auch eine ausgetauschte Datei.
mutation rueckbau-ohne-summe rm \
	'if [ -n "$_soll" ] && [ "$(network_checksum "$_ziel")" != "$_soll" ]; then' 'if false; then' \
	"Rueckbau fremd: rc 1"

# M12: Rueckbau entfernt bin/ auch mit Fremdem darin (rm -rf statt rmdir).
mutation rueckbau-rmrf rm \
	'if rmdir "$_d" 2>/dev/null; then' 'if rm -rf "$_d" 2>/dev/null; then' \
	"Rueckbau: Binary weg, bin/ mit Fremdem bleibt"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
