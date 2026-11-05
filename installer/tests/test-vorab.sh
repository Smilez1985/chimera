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
if vorab_an; then bad "Vorgabe ist noch 'an' -- gemessen nutzlos, Vorgabe seit 5.11. aus"; \
	else ok "Vorgabe: Vorab-Laden ist aus (gemessen: kein Gewinn)"; fi
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
# Fehlt pip im Systempython, ist das ein BEFUND (pip ist eine Abhaengigkeit,
# die der Installer in Modul 20 selbst herstellt) -- also rc 1 und eine Marke
# mit Grund. Geprueft mit einer python3-Attrappe, damit der Fall unabhaengig
# davon pruefbar ist, ob im Sandbox ein pip liegt.
_stubpy="$W/pyohne"; mkdir -p "$_stubpy"
printf '#!/bin/sh\nexit 1\n' >"$_stubpy/python3"
chmod +x "$_stubpy/python3"
_rc=0
PATH="$_stubpy:$PATH" vorab_holen "pip-ohne" pip "Pillow" >/dev/null 2>&1 || _rc=$?
check "ohne pip ein Befund (rc 1)" "$_rc" "1"
if grep -q 'kein pip' "$(vorab_verzeichnis)/pip-ohne.fehler" 2>/dev/null; then
	ok "Fehlmarke nennt den fehlenden pip"
else
	bad "Fehlmarke ohne Hinweis auf pip"
fi
if vorab_fertig "pip-ohne"; then bad "ohne pip eine fertige Marke"; \
	else ok "ohne pip keine fertige Marke"; fi
rm -f "$(vorab_verzeichnis)/pip-ohne.fehler"

# Idempotenz: Was schon da ist, wird nicht erneut geholt. Geprueft am
# Bestand, nicht an der Marke -- eine Marke von gestern sagt nichts darueber,
# ob die Ware noch da ist, und eine neue Anforderung in der Liste muss auch
# dann geladen werden, wenn das Objekt schon eine .done hat.
_vd="$(vorab_verzeichnis)"
mkdir -p "$_vd/wheels"
: >"$_vd/wheels/pillow-10.0.0-py3-none-any.whl"
vorab_wheel_da "Pillow" && ok "Wheel erkannt (Pillow)" || bad "Wheel nicht erkannt"
vorab_wheel_da "pillow>=10" && ok "Anforderung mit Grenze erkannt" || bad "Anforderung mit Grenze nicht erkannt"
vorab_wheel_da "numpy" && bad "fremdes Wheel als Treffer gemeldet" || ok "fremdes Wheel kein Treffer"
_rc=0
vorab_holen "pip-daa" pip "Pillow" >/dev/null 2>&1 || _rc=$?
check "vollstaendig da: nichts zu holen (rc 3)" "$_rc" "3"
if vorab_fertig "pip-daa"; then ok "dabei entsteht eine fertige Marke"; else bad "Marke fehlt"; fi
rm -f "$_vd/wheels/pillow-10.0.0-py3-none-any.whl" "$_vd/pip-daa.done"
rmdir "$_vd/wheels" 2>/dev/null || true

if ! python3 -m pip --version >/dev/null 2>&1; then
	skip "pip-Weg mit Attrappen-Wheels (kein pip im Systempython)"
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
[ -d "$(vorab_verzeichnis)/wheels.teil" ] && bad "Zwischenverzeichnis blieb liegen" \
	|| ok "Zwischenverzeichnis ist aufgeraeumt"

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

# --- Start als eigene Unit -------------------------------------------------
# Warum das geprueft wird: Der Installer laeuft selbst als transiente Unit.
# Ein einfaches Kind haengt in deren Cgroup und wird bei ihrem Ende
# abgeraeumt (am Pi 5.11.: Vorab-Lader mitten im Download erschossen, keine
# Marke). Der Start muss deshalb ueber `systemd-run --unit=chimera-prefetch`
# gehen -- sichtbar geprueft mit einer Attrappe, nicht angenommen.
# Der Start wird geprueft, also den Schalter ausdruecklich einschalten --
# die Vorgabe ist seit 5.11. aus (gemessen: kein Gewinn).
CHIMERA_PREFETCH_RAD=1; export CHIMERA_PREFETCH_RAD
_stub="$W/stub"; mkdir -p "$_stub"
_fake="$W/fakeprefetch"; printf '#!/bin/sh\nexit 0\n' >"$_fake"
cat >"$_stub/systemd-run" <<'STUB'
#!/bin/sh
printf '%s\n' "$*" >>"$STUB_RUF"
[ -f "$STUB_SCHEITERT" ] && exit 1
exit 0
STUB
chmod +x "$_stub/systemd-run" "$_fake"

STUB_RUF="$W/rufe.txt"; export STUB_RUF
STUB_SCHEITERT="$W/scheitert"; export STUB_SCHEITERT
: >"$STUB_RUF"

_rc=0
PATH="$_stub:$PATH" CHIMERA_PREFETCH_RAD=0 vorab_starten "$_fake" || _rc=$?
check "abgeschaltet startet nicht (rc 2)" "$_rc" "2"
_n="$(wc -l <"$STUB_RUF" | tr -d ' ')"
check "abgeschaltet ruft systemd-run nicht" "$_n" "0"

_rc=0
PATH="$_stub:$PATH" vorab_starten "$_fake" || _rc=$?
check "Start ueber systemd-run (rc 0)" "$_rc" "0"
grep -q -- '--unit=chimera-prefetch' "$STUB_RUF" && ok "eigene Unit chimera-prefetch" \
	|| bad "startet nicht in eigener Unit"
grep -qF -- "$_fake" "$STUB_RUF" && ok "startet das uebergebene Programm" \
	|| bad "Programm kam nicht an"
grep -q -- '--collect' "$STUB_RUF" && ok "Unit wird aufgeraeumt (--collect)" \
	|| bad "ohne --collect bleibt die Unit liegen"
grep -q -- '--service-type=oneshot' "$STUB_RUF" && ok "oneshot wie der Installer-Helfer" \
	|| bad "falscher Unit-Typ"

# Scheitert systemd-run zweimal (Name belegt), ist das ein Befund -- und
# zwar ein gemeldeter: rc 1, nicht stiller Erfolg.
: >"$STUB_RUF"
: >"$STUB_SCHEITERT"
_rc=0
PATH="$_stub:$PATH" vorab_starten "$_fake" || _rc=$?
check "nicht startbar wird gemeldet (rc 1)" "$_rc" "1"
_n="$(grep -c 'chimera-prefetch' "$STUB_RUF" | tr -d ' ')"
check "zweiter Versuch nach reset-failed" "$_n" "2"
rm -f "$STUB_SCHEITERT"

# --- Kein apt im Vorab-Laden ----------------------------------------------
# apt hat einen Eigentuemer (apt_install in lib/network.sh) und teilt sich mit
# Modul 20 dieselbe Sperre -- es kann nicht ueberlappen (am Pi gemessen,
# 5.11.: 25 s fuer null Pakete). Dieser Test haelt fest, dass der Weg nicht
# versehentlich zurueckkommt: eine Liste ohne apt-Objekt, und die Art "apt"
# wird nicht mehr bedient.
_n="$(vorab_liste | grep -c '	apt	' || true)"
check "keine apt-Zeile in der Vorab-Liste" "$_n" "0"
_rc=0
vorab_holen "apt-probe" apt ca-certificates >/dev/null 2>&1 || _rc=$?
check "Art 'apt' wird nicht bedient (rc 2)" "$_rc" "2"
if vorab_fertig "apt-probe"; then bad "apt-Probe hinterliess eine fertige Marke"; \
	else ok "apt-Probe hinterlaesst keine Marke"; fi

# --- Fehlerbericht: was gestern schiefging, steht heute im Protokoll ------
# Mojo liest den Lauf, nicht das Verzeichnis. Der Bericht ist die einzige
# Bruecke zwischen einer .fehler-Marke und dem, was gefunden werden kann.
_texte="$W/bericht.txt"
vorab_fehler_berichten >"$_texte" 2>&1
grep -q 'probes' "$_texte" && ok "Fehlmarke wird im Lauf gemeldet" \
	|| bad "Fehlmarke bleibt unerwaehnt"
grep -q 'Testgrund' "$_texte" && ok "Bericht nennt den Grund" \
	|| bad "Bericht ohne Grund"
grep -q 'erneut versucht' "$_texte" && ok "Bericht sagt, dass es erneut versucht wird" \
	|| bad "Bericht ohne Hinweis auf den neuen Versuch"
rm -f "$(vorab_verzeichnis)/probes.fehler"
vorab_fehler_berichten >"$_texte" 2>&1
grep -q 'probes' "$_texte" && bad "Bericht redet von einer geloeschten Marke" \
	|| ok "ohne Fehlmarke schweigt der Bericht"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
