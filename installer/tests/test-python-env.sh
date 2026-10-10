#!/bin/sh
# Tests fuer Schritt 50 -- Python-Umgebung.
#
# Das Modul wird als Ganzes geprueft, in einer Kopie des Repos (Regel 9:
# nicht die Logik nachbauen). Die Kopie traegt ein replacement der
# requirements.txt, das KEINE Netzabhaengigkeit hat: `pip` ist im
# frischen venv immer da, pip install pip ist online, pip install auf
# eine vorhandene Fassung meldet "already satisfied" ohne Netz. Damit
# ist der ECHTE Lauf messbar, auch im CI.
#
# Gegenprobe: eine Kopie mit GEBROCHENER Verdrahtung (requirements.txt
# leer oder .pth auf ein fehlendes Verzeichnis). Sie muss abbrechen,
# wo die echte durchlaeuft.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }

W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-python.XXXXXX" 2>/dev/null)" || W=""
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
lacks() {
	if printf '%s' "$2" | grep -qi -- "$3"; then bad "$1 -- '$3' kam doch vor"
	else ok "$1"; fi
}

printf '=== Python-Umgebung (Modul 50) ===\n'

# Baumkopie: lib und der Schritt, unter CHIMERA_ROOT als Wurzel.
# requirements.txt wird JEDER Kopie mitgegeben, je Fall anders. Der echte
# Lauf nimmt die ECHTE Anforderungen-Datei aus dem Repo (Pillow) -- der
# Nachweis `python -m chimera --pruefen` braucht sie, und der Test soll
# den echten Weg fahren, nicht einen behelfsmaessigen.
mkbaum() {
	BAUM="$W/$1"
	mkdir -p "$BAUM/etc"
	cp -r "$HERE/lib" "$BAUM/lib"
	mkdir -p "$BAUM/steps"
	cp "$HERE/steps/50-python.sh" "$BAUM/steps/50-python.sh"
	mkdir -p "$BAUM/src/chimera"
	cp -r "$HERE/../src/chimera" "$BAUM/src/chimera" 2>/dev/null || true
	printf 'ID=debian\nVERSION_CODENAME=trixie\n' >"$BAUM/etc/os-release" 2>/dev/null \
		|| true
	CHIMERA_ROOT="$BAUM"; export CHIMERA_ROOT
	CHIMERA_MANIFEST="$BAUM/var/lib/chimera/manifest.tsv"
	CHIMERA_LOG_DIR="$BAUM/var/log/chimera"; export CHIMERA_LOG_DIR
	mkdir -p "$(dirname "$CHIMERA_MANIFEST")" "$CHIMERA_LOG_DIR"
	MANIFEST="$CHIMERA_MANIFEST"
}

# Anforderungen einsetzen. Ohne Argument: die echte Datei aus dem Repo.
setze_anforderungen() {
	if [ -n "${1:-}" ]; then
		printf '%s\n' "$1" >"$BAUM/requirements.txt"
	else
		cp "$HERE/../requirements.txt" "$BAUM/requirements.txt"
	fi
}

# Den Schritt fahren. $1 Modus. Setzt RC und OUT.
fahr() {
	set +e
	OUT="$(env CHIMERA_ROOT="$BAUM" CHIMERA_MANIFEST="$MANIFEST" \
	           CHIMERA_LOG_DIR="$CHIMERA_LOG_DIR" CHIMERA_MODE="$1" \
	           sh "$BAUM/steps/50-python.sh" 2>&1)"
	RC=$?
	set -e
}

# --- Fall 1: requirements fehlt -------------------------------------------
mkbaum "anforderungen-fehlt"
setze_anforderungen ""
rm -f "$BAUM/requirements.txt"
fahr dry
check "requirements fehlt -> rc 2" "$RC" "2"
contains "Abbruch wird benannt" "$OUT" "requirements.txt fehlt"

# --- Fall 2: requirements leer --------------------------------------------
mkbaum "anforderungen-leer"
setze_anforderungen "# nur ein Kommentar"
fahr dry
check "nur Kommentare -> rc 2" "$RC" "2"
contains "leere Liste wird benannt" "$OUT" "nur Kommentare"

# --- Fall 3: Trockenlauf aendert nichts -----------------------------------
mkbaum "trocken"
setze_anforderungen "pip"
fahr dry
check "Trockenlauf -> rc 0" "$RC" "0"
contains "announced" "$OUT" "[wuerde anlegen]"
if [ -d "$BAUM/opt/chimera/venv" ]; then
	bad "Trockenlauf hat ein venv angelegt"
else ok "Trockenlauf hat kein venv angelegt"; fi

# --- Fall 4: echter Lauf in der Kopie -------------------------------------
mkbaum "echt"
setze_anforderungen ""
fahr run
check "echter Lauf -> rc 0" "$RC" "0"
if [ -d "$BAUM/opt/chimera/venv" ]; then
	ok "venv wurde angelegt"
else bad "venv wurde NICHT angelegt"; fi
if [ -d "$BAUM/var/lib/chimera" ]; then
	ok "Manifest liegt in der Testwurzel"
else bad "Manifest fehlt"; fi
contains "Nachweis nannt" "$OUT" "nachweisbar"

# Und die Verdrahtung stimmt: die .pth zeigt auf die Kopie.
_PTH="$(find "$BAUM/opt/chimera/venv" -name 'chimera.pth' 2>/dev/null | head -1)"
if [ -n "$_PTH" ] && [ -f "$_PTH" ]; then
	_ZIEL="$(cat "$_PTH")"
	if [ "$_ZIEL" = "$BAUM/src" ]; then
		ok ".pth verweist auf die Quellkopie"
	else
		bad ".pth verweist auf das Falsche: $_ZIEL (erwartet $BAUM/src)"
	fi
else bad ".pth wurde nicht angelegt"; fi

# --- Fall 5: idempotent ----------------------------------------------------
# Der zweite Lauf kommt in den Zustand "bereits nachweisbar" und aendert
# nichts Wesentliches. Messbar: die Zeitdauer der venv-Erstellung ist
# zweimal gleich, aber einfacher ist die Ausgabe.
mkbaum "zweiter"
setze_anforderungen ""
fahr run
_rc_erster="$RC"
_mk_erster="$BAUM"
_mk_erster_pth="$(find "$BAUM/opt/chimera/venv" -name 'chimera.pth' 2>/dev/null | wc -l)"
fahr run
check "zweiter Lauf -> rc 0" "$RC" "$_rc_erster"
_pth_jetzt="$(find "$BAUM/opt/chimera/venv" -name 'chimera.pth' 2>/dev/null | wc -l)"
check "nur eine .pth, nicht doppelt" "$_pth_jetzt" "1"

# --- Gegenprobe: ohne Verdrahtung ----------------------------------------
# Der Schritt wird geaendert: die .pth wird NICHT geschrieben. Dann muss
# der Lauf melden, dass das Modul nicht lauffaehig ist (rc 2).
mkbaum "gegenprobe"
setze_anforderungen ""
sed 's|write_atomic "\$_pth" |true |' "$BAUM/steps/50-python.sh" \
	>"$W/gegenprobe-step.sh"
set +e
OUT="$(env CHIMERA_ROOT="$BAUM" CHIMERA_MANIFEST="$MANIFEST" \
           CHIMERA_LOG_DIR="$CHIMERA_LOG_DIR" CHIMERA_MODE=run \
           sh "$W/gegenprobe-step.sh" 2>&1)"
RC=$?
set -e
check "Gegenprobe: ohne Verdrahtung -> rc 2" "$RC" "2"
contains "Fehlursache benannt" "$OUT" "pruefen"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
