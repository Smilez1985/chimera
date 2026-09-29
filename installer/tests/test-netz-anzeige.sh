#!/bin/sh
# Tests fuer lib/netz.sh und lib/anzeigen.sh.
#
# Der Schwerpunkt liegt auf der Eigenschaft, die am meisten wert ist und am
# schwersten zu pruefen: **Ein Netzausfall pausiert, er bricht nicht ab.**
# Und er wird gemeldet -- ein stiller Wiederholungsversuch sieht von aussen
# aus wie ein Haenger.
#
# Jeder Test hat eine Gegenprobe (Regel 9).

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=/tmp}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein Testverzeichnis"; exit 1; }
TMPDIR="$CHIMERA_TESTDIR"; export TMPDIR

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"
	else bad "$1 — erwartet '$3', bekam '$2'"; fi
}
enthaelt() {
	if printf '%s' "$2" | grep -q -- "$3"; then ok "$1"
	else bad "$1 — '$3' fehlt"; fi
}

CHIMERA_ROOT=""; export CHIMERA_ROOT
CHIMERA_LOGFILE=""; export CHIMERA_LOGFILE
CHIMERA_LOG_DIR="$CHIMERA_TESTDIR/logs"; export CHIMERA_LOG_DIR
mkdir -p "$CHIMERA_LOG_DIR"

. "$HERE/lib/common.sh"
. "$HERE/lib/netz.sh"
. "$HERE/lib/anzeigen.sh"

echo "== Erreichbarkeit =="

CHIMERA_MODE=run
if netz_erreichbar github.com 443 8; then
	ok "erreichbares Ziel wird erkannt"
else
	bad "github.com nicht erreichbar — haengt das Geraet am Netz?"
fi

# Gegenprobe: 192.0.2.0/24 ist per Norm fuer Doku reserviert und wird
# nirgends geroutet. Antwortet das, stimmt etwas mit der Pruefung nicht.
if netz_erreichbar 192.0.2.1 443 3; then
	bad "Gegenprobe: reservierte Adresse gilt als erreichbar"
else
	ok "Gegenprobe: unerreichbares Ziel wird erkannt"
fi

echo "== Ausfall pausiert, statt abzubrechen =="

# Der Kern der Anforderung. Geprueft wird mit einer Grenze von wenigen
# Sekunden, damit der Test nicht minutenlang laeuft -- die Logik ist
# dieselbe wie bei 600 Sekunden.
_t0="$(date +%s)"
if CHIMERA_NETZ_GRENZE=6 netz_warten 192.0.2.1 443 6 >"$CHIMERA_TESTDIR/warten.log" 2>&1; then
	bad "netz_warten meldete Erfolg fuer ein totes Ziel"
else
	ok "netz_warten gibt nach der Grenze auf"
fi
_dauer=$(( $(date +%s) - _t0 ))

# Es muss wirklich gewartet worden sein. Ein sofortiges Aufgeben waere
# genau das Verhalten, das die Anforderung verbietet.
#
# Die Untergrenze ist knapp gewaehlt, aber NICHT beliebig: Die erste
# Erreichbarkeitspruefung braucht selbst schon ihre Frist (3s), deshalb
# wuerde ein "groesser 0" auch bei sofortigem Aufgeben bestehen. Gemessen
# wird gegen die halbe Grenze -- wer pausiert, kommt dort hin, wer
# abbricht, nicht.
if [ "$_dauer" -ge 4 ]; then
	ok "es wurde gewartet (${_dauer}s), nicht sofort abgebrochen"
else
	bad "nur ${_dauer}s gewartet — das ist ein Abbruch, keine Pause"
fi

# Und der Beweis, dass ueberhaupt eine Warteschleife lief: Wer sofort
# aufgibt, meldet keine verstrichene Wartezeit. Die Zwischenmeldung
# ("warte weiter") kommt erst nach 15s und taugt bei dieser kurzen Grenze
# nicht als Beleg -- die Schlussmeldung dagegen schon.
_txt2="$(cat "$CHIMERA_TESTDIR/warten.log" 2>/dev/null || echo '')"
if printf '%s' "$_txt2" | grep -qE "Nach [0-9]+s immer noch kein Netz"; then
	ok "die verstrichene Wartezeit wird beziffert"
else
	bad "keine bezifferte Wartezeit — es lief keine Warteschleife"
fi

_txt="$(cat "$CHIMERA_TESTDIR/warten.log" 2>/dev/null || echo '')"
enthaelt "der Ausfall wird gemeldet" "$_txt" "Netz weg"
enthaelt "die Grenze wird genannt" "$_txt" "Grenze"
enthaelt "es wird gesagt, dass gewartet wird" "$_txt" "wartet"

# Gegenprobe: Bei erreichbarem Ziel darf es KEINE Wartemeldung geben --
# sonst waere die Meldung wertlos, weil sie immer kaeme.
_ok_txt="$(netz_warten github.com 443 10 2>&1 || true)"
if printf '%s' "$_ok_txt" | grep -q "Netz weg"; then
	bad "Gegenprobe: Wartemeldung auch bei erreichbarem Ziel"
else
	ok "Gegenprobe: kein Laerm, wenn das Netz da ist"
fi

echo "== Download =="

# Trockenlauf darf nichts anfassen.
CHIMERA_MODE=dry
_z="$CHIMERA_TESTDIR/dry.bin"
rm -f "$_z"
netz_laden "https://example.invalid/x" "$_z" >/dev/null 2>&1
[ -e "$_z" ] && bad "Trockenlauf hat geschrieben" || ok "Trockenlauf schreibt nichts"
CHIMERA_MODE=run

# Echter Download, klein.
_z="$CHIMERA_TESTDIR/robots.txt"
rm -f "$_z" "$_z.teil"
if netz_laden "https://raw.githubusercontent.com/PiSugar/Whisplay/main/LICENSE" "$_z" \
     >"$CHIMERA_TESTDIR/dl.log" 2>&1; then
	[ -s "$_z" ] && ok "Datei geladen und nicht leer" \
		|| bad "Exitcode 0, aber die Datei ist leer"
else
	bad "Download fehlgeschlagen — Netz?"
fi

# Die Nebendatei darf nicht liegenbleiben: Sonst haelt ein spaeterer Lauf
# ein halbes Archiv fuer fertig.
[ -e "$_z.teil" ] && bad "Nebendatei blieb liegen" || ok "Nebendatei aufgeraeumt"

# Zweiter Lauf mit Pruefsumme: darf NICHT erneut laden (Idempotenz).
if [ -s "$_z" ]; then
	_summe="$(netz_summe "$_z")"
	_zweit="$(netz_laden "https://example.invalid/nope" "$_z" "$_summe" 2>&1)"
	enthaelt "vorhandene Datei wird nicht neu geladen" "$_zweit" "Schon vorhanden"
fi

# Gegenprobe: falsche Pruefsumme muss auffallen.
if [ -s "$_z" ]; then
	if netz_summe_stimmt "$_z" "0000000000000000000000000000000000000000000000000000000000000000"; then
		bad "Gegenprobe: falsche Pruefsumme galt als richtig"
	else
		ok "Gegenprobe: falsche Pruefsumme faellt auf"
	fi
fi

echo "== Anzeigen-Registry =="

check "Whisplay braucht drei Busse" "$(anzeige_get whisplay busse)" "spi i2c_arm i2s"
check "Whisplay meldet eine ALSA-Karte" "$(anzeige_get whisplay alsa_karte)" "whisplaysound"
check "Whisplay hat 15 Bilder/s" "$(anzeige_get whisplay fps)" "15"

# E-Paper ist der Fall, fuer den Regel 7a gebaut wurde.
check "E-Paper zeichnet nicht von selbst" "$(anzeige_get epaper fps)" "0"
check "E-Paper braucht nur SPI" "$(anzeige_get epaper busse)" "spi"
check "E-Paper hat keinen Ton" "$(anzeige_get epaper alsa_karte)" ""

# Ein nacktes Panel braucht keinen Herstellertreiber.
check "ST7789 ohne Fremdtreiber" "$(anzeige_get st7789 quelle)" ""

# Gegenprobe: Ein unbekannter Typ liefert nichts und meldet das.
if anzeige_get gibtesnicht name >/dev/null 2>&1; then
	bad "Gegenprobe: unbekannter Typ lieferte einen Namen"
else
	ok "Gegenprobe: unbekannter Typ wird abgelehnt"
fi

# Jede gelistete Anzeige muss vollstaendig beschrieben sein -- sonst
# faellt die Luecke erst auf dem Geraet auf.
for _a in $(anzeigen_liste); do
	_fehlt=""
	for _f in name breite hoehe fps pruefe hinweis; do
		[ -n "$(anzeige_get "$_a" "$_f")" ] || _fehlt="$_fehlt $_f"
	done
	[ -z "$_fehlt" ] && ok "$_a ist vollstaendig beschrieben" \
		|| bad "$_a fehlen Felder:$_fehlt"
done

echo "== Erkennung =="

# Ohne I2C ist die Erkennung blind. Das muss unterscheidbar bleiben von
# "es steckt nichts dran" (Regel 10j).
_R="$(mktemp -d)"
mkdir -p "$_R/dev"
CHIMERA_ROOT="$_R"
if anzeige_erkennung_moeglich; then
	bad "Erkennung gilt als moeglich, obwohl kein I2C da ist"
else
	ok "ohne I2C: Erkennung wird als unmoeglich gemeldet"
fi

# Gegenprobe: mit I2C-Geraet ist sie moeglich.
: >"$_R/dev/i2c-1"
if anzeige_erkennung_moeglich; then
	ok "Gegenprobe: mit I2C ist die Erkennung moeglich"
else
	bad "Gegenprobe: I2C da, gilt aber als unmoeglich"
fi

# HAT-EEPROM mit PiSugar-Kennung -> whisplay
mkdir -p "$_R/proc/device-tree/hat"
printf 'PiSugar\0' >"$_R/proc/device-tree/hat/vendor"
printf 'Whisplay HAT\0' >"$_R/proc/device-tree/hat/product"
check "PiSugar-EEPROM wird erkannt" "$(anzeige_erkennen || true)" "whisplay"

# Fremdes EEPROM: nicht raten (Regel 10g).
printf 'Irgendwer\0' >"$_R/proc/device-tree/hat/vendor"
printf 'Unbekanntes Ding\0' >"$_R/proc/device-tree/hat/product"
check "fremdes EEPROM wird nicht geraten" "$(anzeige_erkennen || true)" "unbekannt"

# Kein EEPROM.
rm -rf "$_R/proc/device-tree/hat"
check "ohne EEPROM: keins" "$(anzeige_erkennen || true)" "keins"

CHIMERA_ROOT=""
rm -rf "$_R"

echo ""
printf 'Ergebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
