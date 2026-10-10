#!/bin/sh
# Tests fuer fremddatei_pruefen -- fremder Code wird nicht blind ausgefuehrt.
#
# Die Funktion prueft die Pruefsumme einer Datei gegen einen hinterlegten
# Sollwert. Bei Abweichung bricht sie BENANNT ab, bei fehlender
# Pruefmoeglichkeit ebenfalls -- beides ist hier gemessen.
#
# Gegenprobe: eine Kopie mit entferntem Vergleich. Sie muss Erfolg melden,
# wo die echte abbricht. Bliebe sie gruen, misst der Test nichts.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }

W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-fremd.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"
	else bad "$1 -- erwartet '$3', bekam '$2'"; fi
}
contains() {
	if printf '%s' "$2" | grep -qi -- "$3"; then ok "$1"
	else bad "$1 -- '$3' fehlt in der Ausgabe"; fi
}

printf '=== Fremdcode: Pruefsumme vor dem Ausfuehren ===\n'

# Datei zum Pruefen. Der Sollwert wird aus dem Inhalt gerechnet -- der Test
# prueft die FUNKTION, nicht den hinterlegten Herstellerwert (der steht in
# lib/display.sh und aendert sich beim Hersteller, nicht hier).
printf 'echo fremd\n' >"$W/installer.sh"
SOLL="$(sha256sum "$W/installer.sh" | awk '{print $1}')"

# Aufrufer: laedt common.sh und network.sh, ruft die Funktion.
cat >"$W/aufruf.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
. "$HERE/lib/network.sh"
fremddatei_pruefen "$1" "$2"
EOF
chmod +x "$W/aufruf.sh"

lauf() {
	set +e
	OUT="$(CHIMERA_LOG_DIR="$W/logs" sh "$W/aufruf.sh" "$1" "$2" 2>&1)"
	RC=$?
	set -e
}

mkdir -p "$W/logs"

# --- Fall 1: stimmt --------------------------------------------------------
lauf "$W/installer.sh" "$SOLL"
check "stimmt -> rc 0" "$RC" "0"
contains "Pruefsumme bestreitet Erfolg" "$OUT" "stimmt"

# --- Fall 2: stimmt nicht --------------------------------------------------
lauf "$W/installer.sh" "0000000000000000000000000000000000000000000000000000000000000000"
check "weicht ab -> rc 1" "$RC" "1"
contains "Abweichung wird benannt" "$OUT" "weicht ab"

# --- Fall 3: nicht pruefbar ------------------------------------------------
#
# `have_cmd` wird im Aufrufer durch eine Attrappe ersetzt, die sha256sum
# nicht kennt. So wird der Fall gemessen, ohne ein echtes Programm auf dem
# System zu bewegen -- ein Test, der /usr/bin anfasst, ist selbst ein
# Risiko.
cat >"$W/aufruf-ohne-sha.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
have_cmd() { [ "$1" != sha256sum ]; }
. "$HERE/lib/network.sh"
fremddatei_pruefen "$1" "$2"
EOF
chmod +x "$W/aufruf-ohne-sha.sh"

set +e
OUT="$(CHIMERA_LOG_DIR="$W/logs" sh "$W/aufruf-ohne-sha.sh" "$W/installer.sh" "$SOLL" 2>&1)"
RC=$?
set -e
check "Pruefwerkzeug fehlt -> rc 1" "$RC" "1"
contains "fehlendes Werkzeug wird benannt" "$OUT" "nicht pruefbar"

# --- Fall 4: ohne hinterlegten Sollwert ------------------------------------
lauf "$W/installer.sh" ""
check "kein Sollwert -> rc 0, mit Meldung" "$RC" "0"
contains "fehlender Sollwert wird gesagt" "$OUT" "Keine Pruefsumme"

# --- Gegenprobe ------------------------------------------------------------
# Der Vergleich wird entfernt -- die Kopie meldet Erfolg, wo die echte
# abbricht. Bliebe der Test gruen, pruefte er nur sich selbst.
sed 's/if \[ "\$_fp_ist" != "\$_fp_soll" \]; then/if false; then/' \
	"$HERE/lib/network.sh" >"$W/network-alt.sh"
if grep -q 'if false; then' "$W/network-alt.sh"; then
	ok "Gegenprobe vorbereitet"
else
	bad "Gegenprobe nicht vorbereitet -- Mutation griff nicht"
fi
cat >"$W/aufruf-alt.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
. "$1"
fremddatei_pruefen "$2" "$3"
EOF
chmod +x "$W/aufruf-alt.sh"
set +e
OUT="$(CHIMERA_LOG_DIR="$W/logs" sh "$W/aufruf-alt.sh" "$W/network-alt.sh" "$W/installer.sh" "0000000000000000000000000000000000000000000000000000000000000000" 2>&1)"
RC=$?
set -e
check "Gegenprobe: alte Fassung meldet Erfolg" "$RC" "0"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
