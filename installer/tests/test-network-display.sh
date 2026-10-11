#!/bin/sh
# Tests fuer lib/network.sh und lib/display.sh.
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
	else bad "$1 -- erwartet '$3', bekam '$2'"; fi
}
contains() {
	if printf '%s' "$2" | grep -q -- "$3"; then ok "$1"
	else bad "$1 -- '$3' fehlt"; fi
}

CHIMERA_ROOT=""; export CHIMERA_ROOT
CHIMERA_LOGFILE=""; export CHIMERA_LOGFILE
CHIMERA_LOG_DIR="$CHIMERA_TESTDIR/logs"; export CHIMERA_LOG_DIR
mkdir -p "$CHIMERA_LOG_DIR"

. "$HERE/lib/common.sh"
. "$HERE/lib/network.sh"
. "$HERE/lib/module.sh"
. "$HERE/lib/display.sh"

echo "== Erreichbarkeit =="

CHIMERA_MODE=run
if network_reachable github.com 443 8; then
	ok "erreichbares Ziel wird erkannt"
else
	bad "github.com nicht erreichbar -- haengt das Geraet am Netz?"
fi

# Port 80 so, wie Schritt 50 ihn ruft (manifest_apt -> deb.debian.org:80).
# Die alte Fassung sprach dort immer https -- TLS gegen einen
# Klartext-Port scheitert, und der Installer wartete am chimera-pi
# 600 s auf ein vorhandenes Netz.
if network_reachable deb.debian.org 80 8; then
	ok "Port 80 (apt-Spiegel) wird als erreichbar erkannt"
else
	bad "deb.debian.org:80 nicht erreichbar -- Schema falsch oder kein Netz?"
fi
# Gegenprobe: die alte Fassung (immer https, rc 35 nicht als Antwort).
_alt="$CHIMERA_TESTDIR/network-alt.sh"
sed -e 's|^			80\|8080) _ne_url="http://\$_ne_host:\$_ne_port" ;;$|			nie) : ;;|' \
    -e 's/^			0|22|35|52|56|60) return 0 ;;$/			0|22|52|56) return 0 ;;/' \
	"$HERE/lib/network.sh" >"$_alt"
if cmp -s "$HERE/lib/network.sh" "$_alt"; then
	bad "Gegenprobe Port 80: Mutation griff nicht"
elif ( . "$_alt"; network_reachable deb.debian.org 80 8 ); then
	bad "Gegenprobe Port 80: alte Fassung haelt Port 80 fuer erreichbar"
else
	ok "Gegenprobe Port 80: alte Fassung meldet faelschlich 'weg'"
fi

# Gegenprobe: 192.0.2.0/24 ist per Norm fuer Doku reserviert und wird
# nirgends geroutet. Antwortet das, stimmt etwas mit der Pruefung nicht.
if network_reachable 192.0.2.1 443 3; then
	bad "Gegenprobe: reservierte Adresse gilt als erreichbar"
else
	ok "Gegenprobe: unerreichbares Ziel wird erkannt"
fi

echo "== Ausfall pausiert, statt abzubrechen =="

# Der Kern der Anforderung. Geprueft wird mit einer Grenze von wenigen
# Sekunden, damit der Test nicht minutenlang laeuft -- die Logik ist
# dieselbe wie bei 600 Sekunden.
_t0="$(date +%s)"
if CHIMERA_NETWORK_LIMIT=6 network_wait 192.0.2.1 443 6 >"$CHIMERA_TESTDIR/warten.log" 2>&1; then
	bad "network_wait meldete Erfolg fuer ein totes Ziel"
else
	ok "network_wait gibt nach der Grenze auf"
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
	bad "nur ${_dauer}s gewartet -- das ist ein Abbruch, keine Pause"
fi

# Und der Beweis, dass ueberhaupt eine Warteschleife lief: Wer sofort
# aufgibt, meldet keine verstrichene Wartezeit. Die Zwischenmeldung
# ("warte weiter") kommt erst nach 15s und taugt bei dieser kurzen Grenze
# nicht als Beleg -- die Schlussmeldung dagegen schon.
_txt2="$(cat "$CHIMERA_TESTDIR/warten.log" 2>/dev/null || echo '')"
if printf '%s' "$_txt2" | grep -qE "Nach [0-9]+s immer noch kein Netz"; then
	ok "die verstrichene Wartezeit wird beziffert"
else
	bad "keine bezifferte Wartezeit -- es lief keine Warteschleife"
fi

_txt="$(cat "$CHIMERA_TESTDIR/warten.log" 2>/dev/null || echo '')"
contains "der Ausfall wird gemeldet" "$_txt" "Netz weg"
contains "die Grenze wird genannt" "$_txt" "Grenze"
contains "es wird gesagt, dass gewartet wird" "$_txt" "wartet"

# Gegenprobe: Bei erreichbarem Ziel darf es KEINE Wartemeldung geben --
# sonst waere die Meldung wertlos, weil sie immer kaeme.
# Grenze klein halten: Sollte die Erreichbarkeitspruefung auf einem
# fremden System scheitern, darf der Test nicht minutenlang warten,
# sondern muss zuegig rot werden. Ein haengender Test meldet nichts.
_ok_txt="$(CHIMERA_NETWORK_LIMIT=8 network_wait github.com 443 8 2>&1 || true)"
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
network_fetch "https://example.invalid/x" "$_z" >/dev/null 2>&1
[ -e "$_z" ] && bad "Trockenlauf hat geschrieben" || ok "Trockenlauf schreibt nichts"
CHIMERA_MODE=run

# Echter Download, klein.
_z="$CHIMERA_TESTDIR/robots.txt"
rm -f "$_z" "$_z.teil"
if network_fetch "https://raw.githubusercontent.com/PiSugar/Whisplay/main/LICENSE" "$_z" \
     >"$CHIMERA_TESTDIR/dl.log" 2>&1; then
	[ -s "$_z" ] && ok "Datei geladen und nicht leer" \
		|| bad "Exitcode 0, aber die Datei ist leer"
else
	bad "Download fehlgeschlagen -- Netz?"
fi

# Die Nebendatei darf nicht liegenbleiben: Sonst haelt ein spaeterer Lauf
# ein halbes Archiv fuer fertig.
[ -e "$_z.teil" ] && bad "Nebendatei blieb liegen" || ok "Nebendatei aufgeraeumt"

# Zweiter Lauf mit Pruefsumme: darf NICHT erneut laden (Idempotenz).
if [ -s "$_z" ]; then
	_summe="$(network_checksum "$_z")"
	_zweit="$(network_fetch "https://example.invalid/nope" "$_z" "$_summe" 2>&1)"
	contains "vorhandene Datei wird nicht neu geladen" "$_zweit" "Schon vorhanden"
fi

# Gegenprobe: falsche Pruefsumme muss auffallen.
if [ -s "$_z" ]; then
	if network_checksum_ok "$_z" "0000000000000000000000000000000000000000000000000000000000000000"; then
		bad "Gegenprobe: falsche Pruefsumme galt als richtig"
	else
		ok "Gegenprobe: falsche Pruefsumme faellt auf"
	fi
fi

echo "== Anzeigen-Registry (display.json ist die Quelle) =="

# Seit 11.10.2026 liest lib/display.sh die Module unter src/chimera/displays/
# -- dieselbe Datei wie der Python-Treiber. Was hier steht, muss dort stehen.
check "Module aus den Ordnern" "$(display_list)" "keine whisplay"
check "Whisplay: Bootkonfiguration NEUTRAL (i2s zur Laufzeit)" "$(display_get whisplay busse)" "spi i2c_arm"
check "Whisplay: i2s kommt zur Laufzeit" "$(display_get whisplay ton_dtparam)" "i2s=on"
check "Whisplay: Overlay zur Laufzeit" "$(display_get whisplay ton_dtoverlay)" "whisplay-soundcard"
check "Whisplay meldet eine ALSA-Karte" "$(display_get whisplay alsa_karte)" "whisplaysound"
check "Whisplay hat 15 Bilder/s" "$(display_get whisplay fps)" "15"
check "Whisplay: Tonquelle an Commit gebunden" "$(display_get whisplay commit)" "c73051e64dc62aced1853d16f33d4614fec5bee4"
case "$(display_get whisplay pip)" in
	*numpy*) ok "Whisplay: numpy als Abhaengigkeit (RGB565)" ;;
	*) bad "Whisplay: numpy fehlt in deps.pip" ;;
esac
case "$(display_get whisplay pip)$(display_get whisplay apt)" in
	*spidev*|*gpiod*|*python3-dev*) bad "Whisplay: Herstellerabhaengigkeiten (spidev/gpiod/python3-dev) noch im Profil" ;;
	*) ok "Whisplay: kein spidev/gpiod/python3-dev mehr (eigener Treiber)" ;;
esac

# "keine" ist der Rueckfall: zeichnet nicht von selbst (Regel 7a), kein Ton.
check "keine: zeichnet nicht von selbst" "$(display_get keine fps)" "0"
check "keine: kein Ton" "$(display_get keine alsa_karte)" ""

# Gegenprobe: Ein unbekannter Typ liefert nichts und meldet das.
if display_get gibtesnicht name >/dev/null 2>&1; then
	bad "Gegenprobe: unbekannter Typ lieferte einen Namen"
else
	ok "Gegenprobe: unbekannter Typ wird abgelehnt"
fi

# Jede gelistete Anzeige muss vollstaendig beschrieben sein -- sonst
# faellt die Luecke erst auf dem Geraet auf.
for _a in $(display_list); do
	_fehlt=""
	for _f in name breite hoehe pruefe hinweis; do
		[ -n "$(display_get "$_a" "$_f")" ] || _fehlt="$_fehlt $_f"
	done
	[ -z "$_fehlt" ] && ok "$_a ist vollstaendig beschrieben" \
		|| bad "$_a fehlen Felder:$_fehlt"
done

# Shell und Python lesen dieselbe Datei: Breite/Hoehe/Bildrate muessen
# zeichengleich sein. (Sonst sind es wieder zwei Quellen.)
_py_sicht="$(PYTHONPATH="$(display_src)" PYTHONDONTWRITEBYTECODE=1 python3 -c '
from chimera.displays import registry
p = registry.profil("whisplay"); print(p.breite, p.hoehe, int(p.bildrate))')"
check "Shell-Sicht == Python-Sicht (whisplay)" \
	"$(display_get whisplay breite) $(display_get whisplay hoehe) $(display_get whisplay fps)" "$_py_sicht"

echo "== Erkennung =="

# Ohne I2C ist die Erkennung blind. Das muss unterscheidbar bleiben von
# "es steckt nichts dran" (Regel 10j).
_R="$(mktemp -d)"
mkdir -p "$_R/dev"
CHIMERA_ROOT="$_R"
if display_detect_possible; then
	bad "Erkennung gilt als moeglich, obwohl kein I2C da ist"
else
	ok "ohne I2C: Erkennung wird als unmoeglich gemeldet"
fi

# Die Falle aus HARDWARE-BEFUNDE: /dev/i2c-* allein (Userspace-Knoten
# ohne registrierten Bus im Kernel) ist KEIN Beleg fuer aktives I2C.
: >"$_R/dev/i2c-1"
if display_detect_possible; then
	bad "nur /dev/i2c-1 ohne Kernel-Bus gilt als aktives I2C"
else
	ok "nur /dev/i2c-1 ohne Kernel-Bus: nicht als aktiv gewertet"
fi
rm -f "$_R/dev/i2c-1"

# Gegenprobe: Bus im Kernel registriert, aber KEIN /dev/i2c-* (i2c-dev
# nicht geladen) -- genau der Zustand am chimera-pi. Muss moeglich sein.
mkdir -p "$_R/sys/bus/i2c/devices/i2c-1"
if display_detect_possible; then
	ok "Gegenprobe: Kernel-Bus i2c-1 ohne /dev-Knoten -> moeglich"
else
	bad "Gegenprobe: Kernel-Bus i2c-1 da, gilt aber als unmoeglich"
fi

# Erkennung laeuft im Treiberpaket; hier nur der Shell-Rand: Attrappen
# unter <root>/chimera-probe/ (wie tests/test_displays.py), Ergebnis kommt
# als Typ UND Grund zurueck (ohne Subshell).
mkdir -p "$_R/chimera-probe"
printf '8181b3' >"$_R/chimera-probe/st7789-dc27"
printf '1' >"$_R/chimera-probe/i2c-1-1a"
display_detect >/dev/null 2>&1 || true
check "Kennung + Codec -> whisplay" "${DISPLAY_TYP:-}" "whisplay"
check "Grund wird benannt" "$(display_quelle)" "eindeutiger Treffer"
case "$(display_belege)" in
	*"8181b3"*) ok "Belege nennen die Kennung" ;;
	*) bad "Belege nennen die Kennung nicht" ;;
esac

# Falsche Kennung: Rueckfall "keine", nicht geraten (Regel 10g).
printf '000000' >"$_R/chimera-probe/st7789-dc27"
display_detect >/dev/null 2>&1 || true
check "falsche Kennung -> Rueckfall keine" "${DISPLAY_TYP:-}" "keine"

# CHIMERA_ANZEIGE sticht -- auch ueber den Shell-Weg.
CHIMERA_ANZEIGE=whisplay display_detect >/dev/null 2>&1 || true
check "CHIMERA_ANZEIGE sticht" "${DISPLAY_TYP:-}" "whisplay"
unset CHIMERA_ANZEIGE

CHIMERA_ROOT=""
rm -rf "$_R"

echo ""
printf 'Ergebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
