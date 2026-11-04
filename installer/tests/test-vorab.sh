#!/bin/sh
# Tests fuer das Vorab-Laden (installer/lib/vorab.sh, installer/chimera-prefetch).
#
# Geprueft wird, was das ganze Verfahren zusammenhaelt:
#   * Marken werden atomar geschrieben (.teil -> .done), nie halb gelesen
#   * eine .teil-Datei gilt NICHT als fertig
#   * ein Fehlschlag hinterlaesst einen Grund (.fehler), keine .done
#   * der pip-Weg holt Wheels ohne Netz (Attrappen-Wheels, PIP_NO_INDEX)
#
# Der apt-Weg braucht root und apt; fehlt beides, wird er als uebersprungen
# gemeldet -- eine eigene Zeile, kein stiller Erfolg.
set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-vorab.XXXXXX")" || exit 2
trap '[ -n "${KEEP:-}" ] || rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
skip(){ printf '  uebersprungen  %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 -- erwartet '$3', bekam '$2'"; fi; }

printf '=== Vorab-Laden ===\n'

# Wurzel wie auf dem Geraet: /opt/chimera/state liegt unter CHIMERA_ROOT.
CHIMERA_ROOT="$W/wurzel"; export CHIMERA_ROOT
CHIMERA_STATE="/opt/chimera/state"; export CHIMERA_STATE
CHIMERA_LOG_DIR="$W/logs"; export CHIMERA_LOG_DIR
mkdir -p "$CHIMERA_ROOT/opt/chimera/state" "$CHIMERA_LOG_DIR"

. "$HERE/lib/common.sh"
. "$HERE/lib/vorab.sh"

check "Vorab-Verzeichnis liegt unter state" \
	"$(vorab_verzeichnis)" "$CHIMERA_ROOT/opt/chimera/state/prefetch"

# Schalter: an ist die Vorgabe, 0 schaltet ab. Er wird an EINER Stelle
# gelesen (vorab_an), damit Installer und Prefetch-Prozess nicht
# verschiedener Meinung sind -- ein Schalter, den nur eine Seite kennt,
# ist schlimmer als keiner.
vorab_an && ok "Vorgabe: Vorab-Laden ist an" || bad "Vorgabe ist nicht 'an'"
if CHIMERA_PREFETCH_RAD=0 vorab_an; then bad "CHIMERA_PREFETCH_RAD=0 schaltet nicht ab"; \
	else ok "CHIMERA_PREFETCH_RAD=0 schaltet ab"; fi
CHIMERA_PREFETCH_RAD=1 vorab_an && ok "CHIMERA_PREFETCH_RAD=1 schaltet an" \
	|| bad "CHIMERA_PREFETCH_RAD=1 schaltet nicht an"

# Und der Schalter wirkt: abgeschaltet wird nichts geholt und keine Marke
# gesetzt (sonst waere "ab" nur ein Wort).
_rc=0
CHIMERA_PREFETCH_RAD=0 vorab_alle >/dev/null 2>&1 || _rc=$?
check "vorab_alle meldet 'abgeschaltet' (rc 2)" "$_rc" "2"
_n="$(ls "$(vorab_verzeichnis)" 2>/dev/null | wc -l | tr -d ' ')"
check "abgeschaltet entstehen keine Marken" "$_n" "0"

vorab_anlegen && ok "Verzeichnis anlegbar" || bad "Verzeichnis nicht anlegbar"
[ -d "$(vorab_verzeichnis)" ] && ok "Verzeichnis existiert" || bad "Verzeichnis fehlt"

if vorab_fertig probe; then bad "ohne Marke gilt als fertig"; else ok "ohne Marke nicht fertig"; fi

# Eine .teil-Datei ist ein laufender Abruf, kein Ergebnis.
printf 'halb\n' >"$(vorab_verzeichnis)/probe.teil"
if vorab_fertig probe; then bad ".teil gilt als fertig (stiller Erfolg)"; else ok ".teil gilt nicht als fertig"; fi
rm -f "$(vorab_verzeichnis)/probe.teil"

vorab_marke_done probe
if vorab_fertig probe; then ok "Marke gesetzt: fertig"; else bad "Marke fehlt nach dem Setzen"; fi
[ -f "$(vorab_verzeichnis)/probe.done.teil" ] && bad "Zwischenmarke blieb liegen" \
	|| ok "Marke ist atomar umbenannt (kein .teil-Rest)"
grep -q 'objekt=probe' "$(vorab_verzeichnis)/probe.done" && ok "Marke nennt das Objekt" \
	|| bad "Marke ohne Objektangabe"

vorab_marke_fehler probes "Testgrund"
grep -q 'grund=Testgrund' "$(vorab_verzeichnis)/probes.fehler" && ok "Fehlermarke nennt den Grund" \
	|| bad "Fehlermarke ohne Grund"
if vorab_fertig probes; then bad "Fehlerfall gilt als fertig"; else ok "Fehlerfall ist nicht fertig"; fi

# --- pip-Weg: Wheels aus Attrappen, ohne Netz -----------------------------
# Ohne pip im System (Debian bringt es nicht mit, PEP 668) faellt dieser Weg
# im Betrieb auf den normalen Abruf in Modul 50 zurueck. Hier wird er dann
# als uebersprungen gemeldet, nicht als gruen.
if ! python3 -m pip --version >/dev/null 2>&1; then
	skip "pip-Weg (kein pip im Systempython)"
	_wh=""
else
_wh="$W/quelle"
python3 "$HERE/tests/fake-wheel.py" "$_wh" Pillow 10.0.0 >/dev/null
python3 "$HERE/tests/fake-wheel.py" "$_wh" numpy 1.26.4 >/dev/null

set +e
PIP_NO_INDEX=1 PIP_FIND_LINKS="$_wh" vorab_holen "pip-test" pip "Pillow" >/dev/null 2>&1
_rc=$?
set -e
check "pip-Objekt geholt (rc)" "$_rc" "0"
if vorab_fertig "pip-test"; then ok "pip-Objekt hat eine fertige Marke"; else bad "pip-Marke fehlt"; fi
_n="$(ls "$(vorab_verzeichnis)/wheels" 2>/dev/null | grep -c 'Pillow' || true)"
check "Wheel liegt im Vorab-Verzeichnis" "$_n" "1"

# Gegenprobe: unloesbare Anforderung -> Fehlermarke, keine fertige Marke.
set +e
PIP_NO_INDEX=1 PIP_FIND_LINKS="$_wh" vorab_holen "pip-kaputt" pip "gibtsnicht-paket>=1" >/dev/null 2>&1
_rc=$?
set -e
[ "$_rc" != 0 ] && ok "unloesbare Anforderung meldet Fehler" || bad "unloesbare Anforderung galt als Erfolg"
if vorab_fertig "pip-kaputt"; then bad "Fehlerfall hinterliess eine fertige Marke"; else ok "Fehlerfall hinterliess keine fertige Marke"; fi
grep -q 'pip download rc=' "$(vorab_verzeichnis)/pip-kaputt.fehler" && ok "Fehler nennt pip-Exitcode" \
	|| bad "Fehlermarke ohne pip-Exitcode"

fi

# --- apt-Weg --------------------------------------------------------------
if [ "$(id -u)" = 0 ] && command -v apt-get >/dev/null 2>&1 && \
   apt-get install --download-only --yes --print-uris ca-certificates >/dev/null 2>&1; then
	set +e
	vorab_holen "apt-test" apt ca-certificates >/dev/null 2>&1
	_rc=$?
	set -e
	check "apt-Objekt geholt (rc)" "$_rc" "0"
	if vorab_fertig "apt-test"; then ok "apt-Objekt hat eine fertige Marke"; else bad "apt-Marke fehlt"; fi
else
	skip "apt-Weg (kein root oder kein apt in dieser Umgebung)"
fi

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
