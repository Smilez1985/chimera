#!/bin/sh
# Tests fuer `chimera-install --hardware` (Boot-Abgleich, DESIGN 6e).
#
# Zusage: Mit --hardware laufen GENAU die Hardware-Module 40, 45 und 50 --
# kein 00 (Netzabgleich beim Boot), kein 10/20/25/30, kein 98 (der Dienst
# startet danach ohnehin ueber die Unit-Abhaengigkeit). Die Option
# ueberlebt den I8-Neustart aus source/ (ARGS_NEU).
#
# Gegenprobe: Laeufer ohne den --hardware-Filter -> alle Module laufen.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-hw.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 -- erwartet '$3', bekam '$2'"; fi; }

printf '=== Laeufer: --hardware ===\n'

mkbaum() {
	BAUM="$W/$1"
	mkdir -p "$BAUM/steps" "$BAUM/logs"
	cp "$HERE/chimera-install" "$BAUM/chimera-install"
	cp -r "$HERE/lib" "$BAUM/lib"
	printf '0.1.0-test\n' >"$W/VERSION"
	for n in 00-source 10-check 20-pakete 25-speicher 30-headers 40-install-display 45-ups 50-python 98-service; do
		printf '#!/bin/sh\necho "%s" >>"$CHIMERA_LOG_DIR/marken.txt"\nexit 0\n' "$n" >"$BAUM/steps/$n.sh"
	done
	if [ "${2:-}" = mutiert ]; then
		# Alte Welt: der Filter fehlt.
		sed -i 's/^\tif \[ "\$HARDWARE" = 1 \]; then$/\tif false; then/' "$BAUM/chimera-install"
	fi
	MARKEN="$BAUM/logs/marken.txt"
}

fahr() {
	set +e
	OUTL="$(env CHIMERA_LOG_DIR="$(dirname "$MARKEN")" sh "$BAUM/chimera-install" "$@" 2>&1)"
	RCL=$?
	set -e
}

gelaufen() { tr '\n' ' ' <"$MARKEN" 2>/dev/null | sed 's/ $//'; }

# --- 1. --hardware: genau 40, 45, 50, in dieser Reihenfolge -----------------
mkbaum hw
fahr --hardware
check "--hardware: rc 0" "$RCL" "0"
check "--hardware: genau die Hardware-Module" "$(gelaufen)" "40-install-display 45-ups 50-python"
case "$OUTL" in *"Boot-Abgleich: nur Hardware-Module"*) ok "--hardware wird im Protokoll benannt" ;; *) bad "--hardware nicht benannt" ;; esac

# --- 2. --hardware mit --only: Schnittmenge ---------------------------------
mkbaum hw-only
fahr --hardware --only 50
check "--hardware --only 50: nur 50" "$(gelaufen)" "50-python"

# --- 3. --hardware ueberlebt den I8-Neustart (ARGS_NEU) ---------------------
mkbaum hw-neustart
# Modul 00 meldet rc 4 (source/ erneuert) -> der Laeufer startet aus source/
# neu. Hier zeigt source/ auf denselben Baum; die Marken zeigen, was danach
# lief. Mit --hardware laeuft 00 gar nicht erst -- also KEIN Neustart und
# keine 00-Marke. Das ist die Zusage: beim Boot kein Netzabgleich.
printf '#!/bin/sh\necho "00-source" >>"$CHIMERA_LOG_DIR/marken.txt"\nexit 4\n' >"$BAUM/steps/00-source.sh"
fahr --hardware
check "--hardware: Schritt 00 laeuft nicht (kein Netz beim Boot)" "$(gelaufen)" "40-install-display 45-ups 50-python"
# ARGS_NEU traegt --hardware (fuer den Fall, dass ein Neustart doch stattfindet).
if grep -q 'ARGS_NEU="$ARGS_NEU --hardware"' "$BAUM/chimera-install"; then ok "--hardware steht in ARGS_NEU"; else bad "--hardware fehlt in ARGS_NEU"; fi

# --- 4. ohne --hardware: alles laeuft (Kontrolle) ---------------------------
mkbaum alles
fahr
check "ohne --hardware: alle Module" "$(gelaufen)" "00-source 10-check 20-pakete 25-speicher 30-headers 40-install-display 45-ups 50-python 98-service"

# --- Gegenprobe: Laeufer ohne Filter laesst mit --hardware alles laufen -----
mkbaum mut mutiert
if cmp -s "$BAUM/chimera-install" "$HERE/chimera-install"; then
	bad "Gegenprobe: Mutation griff nicht"
else
	fahr --hardware
	if [ "$(gelaufen)" = "40-install-display 45-ups 50-python" ]; then
		bad "Gegenprobe: Mutation hatte keine Wirkung"
	else
		ok "Gegenprobe: ohne Filter laufen auch 00/10/98 ($(gelaufen | wc -w) Module) -- Fall 1 faengt das"
	fi
fi

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
