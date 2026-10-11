#!/bin/sh
# Gegenprobe zu test-mikro.sh (Regel 9).
#
# Je eine Zusage von Modul 46, seinem Rueckbau oder der Auswertung
# (src/chimera/displays/mikro.py) wird in einer KOPIE verfaelscht; der Test
# laeuft gegen die Kopie (CHIMERA_STEP_46 / CHIMERA_STEP_RM46 / CHIMERA_SRC)
# und muss rot werden -- am erwarteten Pruefpunkt. Eine Mutation, die die
# Datei nicht veraendert, ist selbst ein Fehler.
#
# M1 ist der Zustand, gegen den das Modul gebaut ist: "nur rechts" fest
# eingebaut, egal was gemessen wurde.
set -eu
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
STEP="$HERE/steps/46-mikro.sh"
RMSTEP="$REPO/uninstaller/steps/46-remove-mikro.sh"
TEST="$HERE/tests/test-mikro.sh"
PASS=0; FAIL=0
: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-mikro-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM
ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Mikrofone (Modul 46) ===\n'
if sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
	tail -5 "$G/basis.txt"
fi

# $1 Name, $2 Ziel (step|rm|py), $3 sed-Ausdruck, $4 erwarteter FAIL-Text
mutation() {
	case "$2" in
		step) _orig="$STEP" ;;
		rm)   _orig="$RMSTEP" ;;
		py)   _orig="$REPO/src/chimera/displays/mikro.py" ;;
	esac
	_m="$G/$1"
	mkdir -p "$_m"
	# Die Kopie liegt in einem Baum mit derselben Struktur wie das Repo: Die
	# Schritte finden ihre Bibliotheken ueber dirname($0)/.. bzw. /../.. --
	# ausserhalb davon scheitern sie am fehlenden common.sh, und der Test
	# wird aus dem FALSCHEN Grund rot (10.10.2026 schon einmal passiert).
	if [ "$2" = py ]; then
		cp -r "$REPO/src" "$_m/src"
		sed "$3" "$_orig" >"$_m/src/chimera/displays/mikro.py"
		_neu="$_m/src/chimera/displays/mikro.py"
	elif [ "$2" = step ]; then
		cp -r "$HERE" "$_m/installer"
		_neu="$_m/installer/steps/46-mikro.sh"
		sed "$3" "$_orig" >"$_neu"
	else
		cp -r "$HERE" "$_m/installer"
		mkdir -p "$_m/uninstaller/steps"
		_neu="$_m/uninstaller/steps/46-remove-mikro.sh"
		sed "$3" "$_orig" >"$_neu"
	fi
	if cmp -s "$_orig" "$_neu"; then
		bad "$1: Mutation griff nicht (Muster fehlt)"
		return
	fi
	case "$2" in
		step) _env="CHIMERA_STEP_46=$_neu" ;;
		rm)   _env="CHIMERA_STEP_RM46=$_neu" ;;
		py)   _env="CHIMERA_SRC=$_m/src" ;;
	esac
	if env "$_env" sh "$TEST" >"$_m/aus.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $4" "$_m/aus.txt"; then
		ok "$1: rot bei '$4'"
	else
		bad "$1: rot, aber nicht bei '$4'"
		grep 'FAIL' "$_m/aus.txt" | head -3
	fi
}

# M1: der alte Gedanke -- immer "nur rechts", egal was gemessen wurde.
mutation immer-rechts py \
	's/    if befund.entscheidung == "beide":/    if False:/' \
	"beide: keine Kanalauswahl"

# M2: Kanal vertauscht (ttable nimmt den falschen Kanal).
mutation kanal-vertauscht py \
	's/ttable.0.{befund.kanal} 1/ttable.0.{1 - befund.kanal} 1/' \
	"rechts: mono aus Kanal 1 (ttable.0.1)"

# M3: gescheiterte Messung wird als Befund genommen (rc 2 nicht abgefangen).
mutation scheitern-ignoriert step \
	's/if \[ "\$_rc" = 2 \] || \[ -z "\$_json" \]; then/if [ -z "$_json" ]; then/' \
	"gescheitert mit Ausgabe: alte Messung bleibt"

# M4: keine Idempotenz -- misst bei jedem Lauf neu.
mutation immer-messen step \
	's/\[ -n "\$_alte_anzeige" \] \&\& \[ "\$_alte_anzeige" = "\$ANZEIGE" \]/false/' \
	"zweiter Lauf: nicht neu gemessen"

# M5: Kartentausch nicht erkannt (Anzeige der alten Messung wird nicht verglichen).
mutation anzeige-egal step \
	's/\[ "\$_alte_anzeige" = "\$ANZEIGE" \]/true/' \
	"Messung von anderer Anzeige: neu gemessen"

# M6: fremde Datei wird ueberschrieben.
mutation fremd-ueberschreiben step \
	's/if \[ -f "\$ALSA_CONF" \] \&\& ! manifest_has datei "\$ALSA_CONF"; then/if false; then/' \
	"fremde Datei: rc 1"

# M7: "keins" baut trotzdem ein Geraet (Abbruch fehlt).
mutation keins-baut step \
	's/^if \[ "\$ENTSCHEIDUNG" = keins \]; then/if false; then/' \
	"keins: benannt"
# (Rot wird hier die Meldung: Ein Geraet entsteht auch ohne diesen Zweig
# nicht, weil alsa_geraet() fuer "keins" nichts liefert -- zweites Netz.)

# M8: Rueckbau vergisst die Messung.
mutation rueckbau-ohne-messung rm \
	's|\*/mikro.json\|\*/50-chimera-mikro.conf)|*/50-chimera-mikro.conf)|' \
	"Rueckbau: Messung weg"

# M9: Auswertung prueft das Klirren nicht.
mutation ohne-klirrpruefung py \
	's/klirrt = \[w for w in eigen if w.gehoert and w.klirr_db > KLIRR_GRENZE_DB\]/klirrt = []/' \
	"chimera-pi-Werte: rechts"

# M10: Pegel allein sondert aus (leiser = Defekt) -- Grenze auf 10 dB.
mutation leise-ist-defekt py \
	's/^STUMM_ABSTAND_DB = 20.0/STUMM_ABSTAND_DB = 10.0/' \
	"15 dB leiser, aber sauber: beide (leiser ist kein Defekt)"

# M11: Trockenlauf misst trotzdem.
mutation trocken-misst step \
	's/^elif is_dry_run; then/elif false; then/' \
	"Trockenlauf: nicht gemessen"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
