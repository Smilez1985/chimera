#!/bin/sh
# Tests fuer Regel I7 -- der Exitcode eines Moduls sagt, wie es weitergeht.
#
# Geprueft wird der LAEUFER als Ganzes, mit erfundenen Modulen in einem
# erfundenen Baum (Regel 9: nicht die Logik nachbauen, sondern das echte
# Skript laufen lassen und sein echtes Ergebnis bewerten).
#
# Warum das wichtig ist: Vorher behandelte der Laeufer alles ab 2 als
# Abbruch. Ein Anzeigemodul meldet nach dem Einrichten rc 3 ("Neustart
# noetig"), und damit endete der Lauf dort -- auf einer frischen
# Installation kam er nie ueber die Anzeige hinaus.
#
# Jeder Fall hat eine GEGENPROBE: dieselbe Lage mit einem mutierten Laeufer,
# der rc 3 wieder wie einen Abbruch behandelt. Bleibt die Gegenprobe gruen,
# misst der Test nichts.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }

W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-rc3.XXXXXX" 2>/dev/null)" || W=""
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

printf '=== Laeufer: Exitcodes der Module ===\n'

# --- Bauplan des Testbaums -------------------------------------------------
#
# $1 Name der Baumvariante, $2 "mutiert" fuer die Gegenprobe.
# Legt $BAUM an: Laeufer, lib, VERSION, steps/.
#
# Die Mutation stellt genau das ALTE Verhalten her: rc 3 wird wie rc 2
# behandelt und beendet den Lauf.
mkbaum() {
	BAUM="$W/$1"
	mkdir -p "$BAUM/steps"

	cp "$HERE/chimera-install" "$BAUM/chimera-install"
	cp -r "$HERE/lib" "$BAUM/lib"
	printf '0.1.0-test\n' >"$W/VERSION"

	if [ "${2:-}" = mutiert ]; then
		sed -i 's/elif \[ "\$rc" -eq 3 \]; then/elif false; then/' \
			"$BAUM/chimera-install"
		# Und rc 3 in den Abbruchzweig zurueckholen.
		sed -i 's/# Ab 2 hat das Modul den Lauf bewusst beendet.*/:/' \
			"$BAUM/chimera-install"
	fi

	# Modul 10: laeuft durch, markiert sich.
	cat >"$BAUM/steps/10-start.sh" <<'EOF'
#!/bin/sh
echo "start" >>"$CHIMERA_LOG_DIR/marken.txt"
exit 0
EOF

	# Modul 20: eingerichtet, aber Neustart noetig.
	cat >"$BAUM/steps/20-neustart.sh" <<'EOF'
#!/bin/sh
echo "neustart" >>"$CHIMERA_LOG_DIR/marken.txt"
exit 3
EOF

	# Modul 30: muss noch laufen -- genau das war vorher nicht so.
	cat >"$BAUM/steps/30-danach.sh" <<'EOF'
#!/bin/sh
echo "danach" >>"$CHIMERA_LOG_DIR/marken.txt"
exit 0
EOF

	mkdir -p "$BAUM/logs"
	MARKEN="$BAUM/logs/marken.txt"
}

# Zusaetzlich die beiden Module fuer den Abbruchfall. Getrennt, weil ein
# Baum mit allen fuenf Modulen im ersten Fall am Abbruch enden wuerde --
# dann pruefte er etwas anderes als gemeint.
mkabbruch() {
	# Modul 40: bricht ab.
	cat >"$BAUM/steps/40-abbruch.sh" <<'EOF'
#!/bin/sh
echo "abbruch" >>"$CHIMERA_LOG_DIR/marken.txt"
exit 2
EOF

	# Modul 50: darf nach einem Abbruch NICHT laufen.
	cat >"$BAUM/steps/50-nie.sh" <<'EOF'
#!/bin/sh
echo "nie" >>"$CHIMERA_LOG_DIR/marken.txt"
exit 0
EOF
}

# Den Laeufer fahren. Setzt RCL und OUTL.
fahr() {
	set +e
	OUTL="$(env CHIMERA_LOG_DIR="$(dirname "$MARKEN")" \
	             sh "$BAUM/chimera-install" "$@" 2>&1)"
	RCL=$?
	set -e
}

marke_hat() {
	grep -qx "$1" "$MARKEN" 2>/dev/null
}

# --- Fall 1: Neustartwunsch haelt den Lauf nicht auf -----------------------
mkbaum "neu" ""
fahr --only 10
fahr --only 20
fahr --only 30
# Alle drei zusammen, so wie der echte Lauf sie sieht.
rm -f "$MARKEN"
fahr
check "rc 3 mit Neustartwunsch" "$RCL" "3"
if marke_hat danach; then ok "Modul 30 lief trotz Neustartwunsch aus Modul 20"
else bad "Modul 30 lief NICHT -- der Lauf endete beim Neustartwunsch"; fi
if marke_hat neustart; then ok "Modul 20 lief"
else bad "Modul 20 lief nicht"; fi
contains "der Neustart wird gemeldet" "$OUTL" "reboot"

# --- Gegenprobe: alter Laeufer ---------------------------------------------
mkbaum "alt" mutiert
rm -f "$MARKEN"
fahr
check "Gegenprobe: rc bleibt 3" "$RCL" "3"
if marke_hat danach; then
	bad "Gegenprobe war unscharf -- Modul 30 lief auch mit dem alten Laeufer"
else
	ok "Gegenprobe: alter Laeufer endet beim Neustartwunsch (Test ist scharf)"
fi

# --- Fall 2: ein echter Abbruch endet weiterhin ----------------------------
mkbaum "abbruch" ""
mkabbruch
rm -f "$MARKEN"
fahr
check "rc 2 nach Abbruch" "$RCL" "2"
if marke_hat abbruch; then ok "Modul 40 lief"
else bad "Modul 40 lief nicht"; fi
if marke_hat nie; then
	bad "Modul 50 lief nach einem Abbruch -- der Lauf wurde nicht beendet"
else
	ok "Modul 50 lief nach dem Abbruch nicht"
fi

# --- Fall 3: ein Befund (rc 1) haelt den Lauf ebenfalls nicht auf ----------
mkbaum "befund" ""
cat >"$BAUM/steps/20-neustart.sh" <<'EOF'
#!/bin/sh
echo "neustart" >>"$CHIMERA_LOG_DIR/marken.txt"
exit 1
EOF
rm -f "$MARKEN"
fahr
check "rc 1 bei einem Befund" "$RCL" "1"
if marke_hat danach; then ok "Modul 30 lief trotz Befund"
else bad "Modul 30 lief nicht"; fi

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
