#!/bin/sh
# Tests fuer uv als Werkzeug von Modul 50 (installer/lib/python.sh).
#
# Geprueft wird, was die Regel ausmacht -- nicht, dass uv irgendwo steht:
#   * uv wird nur angelegt, wenn es fehlt (idempotent)
#   * es liegt in seinem eigenen Werkzeug-venv, nicht im Programm-venv
#   * uv scheitert -> derselbe Abruf geht ueber pip (Rueckfall, kein Befund)
#   * harte Zeitgrenze (CHIMERA_UV_FRIST): ein haengendes uv haelt den Lauf nicht
#   * Schalter CHIMERA_UV=aus laesst uv ganz weg
#   * kein --find-links mehr (Vorab-Laden am 5.11.2026 entfernt)
#
# Die Werkzeuge sind Attrappen: python3 (legt das Werkzeug-venv an) und uv
# (schreibt seine Aufrufe in ein Protokoll). Das echte uv wird hier NICHT
# geladen -- der Test laeuft ohne Netz und ohne uv im System.
set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-uv.XXXXXX")" || exit 2
trap '[ -n "${KEEP:-}" ] || rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 -- erwartet '$3', bekam '$2'"; fi; }

printf '=== uv (Werkzeug-venv, Rueckfall, Zeitgrenze) ===\n'

# --- Umgebung wie am Geraet, aber unter $W --------------------------------
CHIMERA_ROOT="$W/wurzel"; export CHIMERA_ROOT
CHIMERA_OPT="/opt/chimera"; export CHIMERA_OPT
CHIMERA_LOG_DIR="$W/logs"; export CHIMERA_LOG_DIR
mkdir -p "$CHIMERA_ROOT/opt/chimera" "$CHIMERA_LOG_DIR"

. "$HERE/lib/common.sh"
. "$HERE/lib/python.sh"

UV_LOG="$W/uv-aufrufe"; export UV_LOG
PY_LOG="$W/py-aufrufe"; export PY_LOG
: >"$UV_LOG"; : >"$PY_LOG"

# --- Attrappen ------------------------------------------------------------
# python3: legt bei `-m venv DIR` ein venv mit python+uv an; bei
# `-m pip install ... uv` setzt es uv lauffaehig. Alles andere wird protokolliert.
stub="$W/stub"; mkdir -p "$stub"
cat >"$stub/python3" <<'STUB'
#!/bin/sh
case "$1 $2" in
"-m venv")
	if [ "${PY_VENV_KAPUTT:-0}" = 1 ]; then exit 1; fi
	mkdir -p "$3/bin" || exit 1
	cp "$0" "$3/bin/python"
	chmod +x "$3/bin/python"
	exit 0 ;;
"-m pip")
	printf '%s\n' "$*" >>"$PY_LOG"
	# uv anlegen, wenn danach verlangt wird
	for a in "$@"; do
		[ "$a" = uv ] || continue
		_d="$(dirname "$0")"
		cat >"$_d/uv" <<'UV'
#!/bin/sh
if [ "$1" = "--version" ]; then echo "uv 0.0.0-attrappe"; exit 0; fi
printf '%s\n' "$*" >>"$UV_LOG"
[ "${UV_HAENGT:-0}" = 1 ] && sleep 30
exit "${UV_RC:-0}"
UV
		chmod +x "$_d/uv"
	done
	exit 0 ;;
esac
exit 0
STUB
chmod +x "$stub/python3"

UV_BIN="$(uv_verzeichnis)/bin/uv"

# --- 1. Schalter ----------------------------------------------------------
_rc=0; CHIMERA_UV=aus uv_bereitstellen || _rc=$?
check "CHIMERA_UV=aus: uv wird nicht angelegt (rc 2)" "$_rc" "2"
[ -e "$UV_BIN" ] && bad "trotz 'aus' wurde uv angelegt" || ok "trotz 'aus' nichts angelegt"

# --- 2. Anlegen, nur wenn es fehlt ---------------------------------------
_rc=0; PATH="$stub:$PATH" uv_bereitstellen || _rc=$?
check "uv wird eingerichtet (rc 0)" "$_rc" "0"
[ -x "$UV_BIN" ] && ok "uv liegt im Werkzeug-venv" || bad "uv fehlt nach dem Einrichten"
case "$(uv_verzeichnis)" in
"$CHIMERA_ROOT"*) ok "Werkzeug-venv liegt unter der Wurzel (CHIMERA_ROOT)" ;;
*) bad "Werkzeug-venv liegt ausserhalb der Wurzel: $(uv_verzeichnis)" ;;
esac

: >"$PY_LOG"; : >"$UV_LOG"
_rc=0; PATH="$stub:$PATH" uv_bereitstellen || _rc=$?
check "zweiter Aufruf: rc 0" "$_rc" "0"
check "zweiter Aufruf richtet nichts mehr ein" "$(grep -c . "$PY_LOG" || true)" "0"

# --- 3. Fehlschlag beim Anlegen -> pip, kein Absturz --------------------
rm -rf "$(uv_verzeichnis)"
_rc=0; PY_VENV_KAPUTT=1 PATH="$stub:$PATH" uv_bereitstellen || _rc=$?
check "venv nicht anlegbar: rc 1 (Rueckfall pip)" "$_rc" "1"
[ -e "$UV_BIN" ] && bad "uv trotz Fehlschlag vorhanden" || ok "kein halbes uv hinterlassen"

# --- 4. Abruf: uv zuerst ------------------------------------------------
_rc=0; PATH="$stub:$PATH" uv_bereitstellen || _rc=$?
: >"$UV_LOG"; : >"$PY_LOG"
_rc=0; pydep_holen "$(uv_verzeichnis)/bin/python" Pillow numpy || _rc=$?
check "pydep_holen mit uv: rc 0" "$_rc" "0"
grep -q 'pip install --python' "$UV_LOG" && ok "uv bekommt 'pip install --python'" \
	|| bad "uv wurde nicht als Installationsweg benutzt"
grep -q 'Pillow numpy' "$UV_LOG" && ok "Anforderungen kommen bei uv an" || bad "Anforderungen fehlen"
check "pip wurde dabei nicht gerufen" "$(grep -c . "$PY_LOG" || true)" "0"

# --- 4b. Schalter gilt auch fuer die Nutzung ---------------------------
# Ohne diese Pruefung laesst sich "mit uv" und "ohne uv" nicht vergleichen
# (am Pi 5.11. aufgefallen: CHIMERA_UV=aus benutzte trotzdem uv).
: >"$UV_LOG"; : >"$PY_LOG"
_rc=0; CHIMERA_UV=aus pydep_holen "$(uv_verzeichnis)/bin/python" Pillow || _rc=$?
check "CHIMERA_UV=aus: Abruf laeuft durch (rc 0)" "$_rc" "0"
check "CHIMERA_UV=aus: uv wird nicht benutzt" "$(grep -c . "$UV_LOG" || true)" "0"
grep -q -- '-m pip install' "$PY_LOG" && ok "CHIMERA_UV=aus: pip uebernimmt" \
	|| bad "CHIMERA_UV=aus: pip lief nicht"

# --- 5. uv scheitert -> pip --------------------------------------------
# Der Rueckfall ist der Sinn der Sache: uv scheitert, pip uebernimmt, und das
# Ergebnis zaehlt. Erfolg ist hier also rc 0 -- gemessen wird, DASS pip lief.
: >"$UV_LOG"; : >"$PY_LOG"
_rc=0; UV_RC=1 pydep_holen "$(uv_verzeichnis)/bin/python" Pillow || _rc=$?
check "uv scheitert, pip liefert: rc 0" "$_rc" "0"
grep -q -- '-m pip install' "$PY_LOG" && ok "Rueckfall auf pip laeuft" || bad "kein Rueckfall auf pip"

# Und wenn auch pip scheitert, ist es ein Befund: rc != 0. Dafuer wird der
# Python des Werkzeug-venv kurz durch eine Attrappe ersetzt, die scheitert.
: >"$PY_LOG"
_rc=0
(
	mv "$(uv_verzeichnis)/bin/python" "$(uv_verzeichnis)/bin/python.echt"
	printf '#!/bin/sh\nexit 1\n' >"$(uv_verzeichnis)/bin/python"
	chmod +x "$(uv_verzeichnis)/bin/python"
	UV_RC=1 pydep_holen "$(uv_verzeichnis)/bin/python" Pillow
) || _rc=$?
[ "$_rc" != 0 ] && ok "uv und pip scheitern: Befund (rc $_rc)" || bad "doppelter Fehlschlag galt als Erfolg"
rm -f "$(uv_verzeichnis)/bin/python"
mv "$(uv_verzeichnis)/bin/python.echt" "$(uv_verzeichnis)/bin/python"

# --- 6. Harte Zeitgrenze ------------------------------------------------
if command -v timeout >/dev/null 2>&1; then
	: >"$UV_LOG"; : >"$PY_LOG"
	_t0="$(date +%s)"
	_rc=0; UV_HAENGT=1 CHIMERA_UV_FRIST=1 pydep_holen "$(uv_verzeichnis)/bin/python" Pillow || _rc=$?
	_d=$(( $(date +%s) - _t0 ))
	[ "$_d" -le 5 ] && ok "Zeitgrenze greift (${_d}s < 5s)" || bad "Zeitgrenze griff nicht (${_d}s)"
	grep -q -- '-m pip install' "$PY_LOG" && ok "nach Zeitgrenze: Rueckfall auf pip" \
		|| bad "nach Zeitgrenze kein Rueckfall"
else
	printf '  uebersprungen  Zeitgrenze (kein timeout)\n'
fi

# --- 7. Keine Vorab-Wheels mehr --------------------------------------
# Das Vorab-Laden ist am 5.11.2026 entfernt worden (Messreihe: 0 s Gewinn,
# siehe CHANGELOG). Ein wieder eingebautes --find-links waere eine zweite
# Quelle, die niemand pflegt -- dieser Test haelt fest, dass der Abruf
# nur den Index fragt, auch wenn ein prefetch-Verzeichnis herumliegt.
mkdir -p "$W/state/prefetch/wheels"
: >"$UV_LOG"; : >"$PY_LOG"
_rc=0; CHIMERA_STATE="$W/state" pydep_holen "$(uv_verzeichnis)/bin/python" Pillow || _rc=$?
grep -q -- '--find-links' "$UV_LOG" && bad "uv: --find-links trotz entferntem Vorab-Laden" \
	|| ok "uv: kein --find-links (Vorab-Laden ist entfernt)"
_rc=0; CHIMERA_UV=aus CHIMERA_STATE="$W/state" \
	pydep_holen "$(uv_verzeichnis)/bin/python" Pillow || _rc=$?
grep -q -- '--find-links' "$PY_LOG" && bad "pip: --find-links trotz entferntem Vorab-Laden" \
	|| ok "pip: kein --find-links (Vorab-Laden ist entfernt)"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
