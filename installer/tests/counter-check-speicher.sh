#!/bin/sh
# Gegenprobe zu test-speicher.sh (Regel 9).
#
# Je eine Zusage von lib/speicher.sh wird in einer Kopie verfaelscht; der
# Test laeuft gegen die Kopie (CHIMERA_SPEICHER_LIB) und muss rot werden,
# und zwar am erwarteten Pruefpunkt. Eine Mutation, die die Datei nicht
# veraendert, ist selbst ein Fehler.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HERE/lib/speicher.sh"
TEST="$HERE/tests/test-speicher.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-speicher-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Speicher ===\n'

if CHIMERA_SPEICHER_LIB="$LIB" sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
	tail -5 "$G/basis.txt"
fi

# $1 Name, $2 sed-Ausdruck, $3 erwarteter FAIL-Text
mutation() {
	_m="$G/$1.sh"
	sed "$2" "$LIB" >"$_m"
	if cmp -s "$LIB" "$_m"; then
		bad "$1: Mutation griff nicht (Muster fehlt in lib/speicher.sh)"
		return
	fi
	if CHIMERA_SPEICHER_LIB="$_m" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $3" "$G/$1.txt"; then
		ok "$1: rot bei '$3'"
	else
		bad "$1: rot, aber nicht bei '$3'"
		grep 'FAIL' "$G/$1.txt" | head -3
	fi
}

# M1: Staffelgrenze verschoben (>= 64 -> > 64).
mutation staffel-grenze \
	's/if   \[ "\$_st_gb" -ge 64 \]/if   [ "$_st_gb" -gt 64 ]/' \
	"Staffel 64 GB -> 16 GiB"

# M2: zram nicht mehr am Zustand gemessen -- nach swapoff -a bliebe es aus.
mutation zram-ohne-zustand \
	's/\[ "\$_sz_neu" = 0 \] && \[ -n "\$_sz_aktiv" \]/[ "$_sz_neu" = 0 ]/' \
	"Kartenwechsel: zram neu gestartet"

# M3: Ausgangszustand bei jedem Umbau neu vermerkt -- Rueckbau stellte
# Chimeras Zwischenstand her.
mutation vorher-jedesmal \
	's/if \[ -z "\$(manifest_list_von swapdatei "\$CHIMERA_STEP")" \]; then/if true; then/' \
	"Kartenwechsel: nur EIN Ausgangszustand"

# M4: Platzmangel wird gekuerzt statt benannt (Pruefung ausgeschaltet).
mutation platz-ungeprueft \
	's/if \[ "\$_sd_soll" -gt "\$_sd_kann" \]; then/if false; then/' \
	"Platzmangel: rc 1"

# M5: Zweitlauf baut immer neu (Groessenvergleich weg).
mutation nicht-idempotent \
	's/if \[ "\$_sd_ist" -eq "\$_sd_soll" \] && \[ -n "\$(speicher_swap_eintrag "\$_sd_loc")" \]; then/if false; then/' \
	"Zweitlauf: Werkzeug nicht aufgerufen"

# M6: fremde zram-Verwaltung uebersehen.
mutation fremd-blind \
	's/^\tfor _sf_p in rpi-swap systemd-zram-generator dphys-swapfile; do$/\tfor _sf_p in nichts; do/' \
	"rpi-swap: rc 2"

# M7: Rueckbau holt die zram-Sicherung nicht zurueck.
mutation rueckbau-ohne-sicherung \
	's/^\tmanifest_list_von sicherung "\$_sr_schritt" >"\$_sr_f"$/\t: >"$_sr_f"/' \
	"Rueckbau: zram-Konfig weicht ab"

# M8: Trockenlauf schreibt die zram-Konfig trotzdem.
mutation trocken-schreibt \
	's/^\telif is_dry_run; then$/\telif false; then/' \
	"Trockenlauf: zram-Konfig geaendert"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
