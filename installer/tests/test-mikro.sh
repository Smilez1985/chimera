#!/bin/sh
# Tests fuer Modul 46 (Mikrofone messen, Aufnahmegeraet bauen) -- 11.10.2026.
#
# Zusagen:
#   1. Die Messung entscheidet, nicht der Code: rechts -> mono aus Kanal 1,
#      links -> mono aus Kanal 0, beide -> zwei Kanaele, keins -> kein Geraet
#      (rc 1, Dienst laeuft ohne Spracheingabe).
#   2. Eine gescheiterte Messung ist KEIN Befund: rc 1, nichts geschrieben,
#      eine alte Messung bleibt stehen.
#   3. Idempotent: zweiter Lauf misst nicht neu (gleiche Anzeige), schreibt
#      nichts; andere Anzeige oder CHIMERA_MIKRO_NEU=1 -> neu messen.
#   4. Eine fremde Datei am Zielort wird nie ueberschrieben.
#   5. Anzeige ohne Ton -> nichts zu tun (rc 0, keine Datei).
#   6. Manifest: Messung und Geraet stehen drin; der Rueckbau (46-remove)
#      entfernt beide und sonst nichts.
#   7. Auswertung (chimera.displays.mikro.auswerten) mit den am chimera-pi
#      gemessenen Werten: klirrendes L -> "rechts".
#
# Die Messung selbst (Lautsprecher, arecord) laeuft nur am Geraet; hier wird
# sie ueber CHIMERA_MIKRO_MESSUNG ersetzt (Befehl liefert das JSON).
# Gegenproben: tests/counter-check-mikro.sh

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
REPO="$(cd "$HERE/.." && pwd)"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-mikro.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap '[ -n "${KEEP:-}" ] || rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 -- erwartet '$3', bekam '$2'"; fi; }
hat()      { if printf '%s' "$2" | grep -q -- "$3"; then ok "$1"; else bad "$1 -- '$3' fehlt"; fi; }
hat_nicht() { if printf '%s' "$2" | grep -q -- "$3"; then bad "$1 -- '$3' kam doch vor"; else ok "$1"; fi; }

# Quellbaum: der ECHTE Schritt und die ECHTEN Bibliotheken.
SRC="${CHIMERA_SRC:-$REPO/src}"
STEP="${CHIMERA_STEP_46:-$HERE/steps/46-mikro.sh}"
RMSTEP="${CHIMERA_STEP_RM46:-$REPO/uninstaller/steps/46-remove-mikro.sh}"

printf '=== Mikrofone (Modul 46) ===\n'

mkroot() {
	R="$W/$1"
	mkdir -p "$R/opt/chimera/state" "$R/etc/alsa/conf.d" "$R/logs"
	MANIFEST="$R/opt/chimera/state/manifest.tsv"
	printf 'whisplay\n' >"$R/opt/chimera/state/anzeige"
	CONF="$R/etc/alsa/conf.d/50-chimera-mikro.conf"
	MESS="$R/opt/chimera/state/mikro.json"
}

# Messung als Datei, die der Ersatzbefehl ausgibt. $1 Entscheidung, $2 Kanal.
messung() {
	_k="null"; [ -n "${2:-}" ] && _k="$2"
	printf '{"entscheidung": "%s", "kanal": %s, "gruende": ["%s"], "warnungen": [], "werte": {}, "zeit": "2026-10-11T18:00:00+0200"}\n' \
		"$1" "$_k" "${3:-Test}" >"$W/messung.json"
	MESSBEFEHL="cat '$W/messung.json'; echo gemessen >>'$W/zaehler'"
}

fahr() {  # $1 Modus, weitere Variablen per env davor
	set +e
	OUT="$(env CHIMERA_ROOT="$R" CHIMERA_MANIFEST="$MANIFEST" CHIMERA_LOG_DIR="$R/logs" \
	           CHIMERA_MODE="$1" CHIMERA_DISPLAY_SRC="$SRC" CHIMERA_DISPLAY_PYTHON=python3 \
	           CHIMERA_MIKRO_MESSUNG="$MESSBEFEHL" CHIMERA_MIKRO_NEU="${NEU:-0}" \
	           sh "$STEP" 2>&1)"
	RC=$?
	set -e
}
gemessen() { [ -f "$W/zaehler" ] && grep -c . "$W/zaehler" || echo 0; }

# --- 1. Entscheidung -> Geraet ------------------------------------------------
mkroot rechts; rm -f "$W/zaehler"; messung rechts 1 "links: klirrt"
fahr run
check "rechts: rc 0" "$RC" "0"
hat "rechts: Ergebnis benannt" "$OUT" "Ergebnis: rechts"
hat "rechts: mono aus Kanal 1 (ttable.0.1)" "$(cat "$CONF" 2>/dev/null)" "ttable.0.1 1"
hat_nicht "rechts: nicht Kanal 0" "$(cat "$CONF" 2>/dev/null)" "ttable.0.0"
hat "rechts: Grund in der Datei" "$(cat "$CONF" 2>/dev/null)" "links: klirrt"
hat "Messung abgelegt" "$(cat "$MESS" 2>/dev/null)" '"entscheidung": "rechts"'
hat "Messung kennt ihre Anzeige" "$(cat "$MESS" 2>/dev/null)" '"anzeige": "whisplay"'
hat "Manifest: Geraet" "$(cat "$MANIFEST" 2>/dev/null)" "50-chimera-mikro.conf"
hat "Manifest: Messung" "$(cat "$MANIFEST" 2>/dev/null)" "mikro.json"

mkroot links; messung links 0 "rechts: hoert keinen Testton"
fahr run
check "links: rc 0" "$RC" "0"
hat "links: mono aus Kanal 0 (ttable.0.0)" "$(cat "$CONF" 2>/dev/null)" "ttable.0.0 1"

mkroot beide; messung beide "" "beide sauber"
fahr run
check "beide: rc 0" "$RC" "0"
# "channels 2" steht auch im Mono-Geraet (die Quelle hat zwei Kanaele) und
# trennt deshalb nichts. Trennend ist allein die fehlende Kanalauswahl.
hat "beide: Geraet chimera_mikro" "$(cat "$CONF" 2>/dev/null)" "pcm.chimera_mikro"
hat_nicht "beide: keine Kanalauswahl" "$(cat "$CONF" 2>/dev/null)" "ttable"

mkroot keins; messung keins "" "kein Testton gehoert"
fahr run
check "keins: rc 1 (Befund)" "$RC" "1"
check "keins: kein Geraet" "$([ -e "$CONF" ] && echo da || echo weg)" "weg"
hat "keins: benannt" "$OUT" "ohne Spracheingabe"

# --- 2. Gescheiterte Messung ---------------------------------------------------
mkroot gescheitert; messung rechts 1
fahr run   # erste, gute Messung
_vorher="$(cat "$MESS")"
MESSBEFEHL="echo 'arecord rc 1: kein Geraet' >&2; exit 2"
NEU=1 fahr run
check "gescheitert: rc 1" "$RC" "1"
hat "gescheitert: Grund benannt" "$OUT" "Messung gescheitert: arecord rc 1"
check "gescheitert: alte Messung bleibt" "$(cat "$MESS")" "$_vorher"
# rc 2 MIT Ausgabe: Die Messung scheiterte, hat aber etwas geschrieben (z. B.
# ein halbes JSON). Auch das ist kein Befund ueber die Mikros -- der rc zaehlt.
# ANDERER Inhalt als die alte Messung -- sonst saehe "bleibt" auch dann gleich
# aus, wenn sie ueberschrieben wurde.
printf '{"entscheidung": "beide", "kanal": null, "gruende": ["halb"], "warnungen": [], "werte": {}, "zeit": "x"}\n' >"$W/halb.json"
MESSBEFEHL="cat '$W/halb.json'; echo 'Aufnahme abgebrochen' >&2; exit 2"
NEU=1 fahr run
check "gescheitert mit Ausgabe: rc 1" "$RC" "1"
check "gescheitert mit Ausgabe: alte Messung bleibt" "$(cat "$MESS")" "$_vorher"
MESSBEFEHL="true"   # liefert nichts
NEU=1 fahr run
check "leere Ausgabe: rc 1" "$RC" "1"
check "leere Ausgabe: alte Messung bleibt" "$(cat "$MESS")" "$_vorher"
MESSBEFEHL="echo '{\"entscheidung\": \"vielleicht\"}'"
NEU=1 fahr run
check "ungueltige Entscheidung: rc 1" "$RC" "1"
hat "ungueltige Entscheidung: benannt" "$OUT" "ohne gueltige Entscheidung"

# --- 3. Idempotenz ---------------------------------------------------------------
mkroot idem; rm -f "$W/zaehler"; messung rechts 1
fahr run
_sum="$(sha256sum "$CONF" | cut -d' ' -f1)"; _z="$(wc -l <"$MANIFEST")"
fahr run
check "zweiter Lauf: rc 0" "$RC" "0"
check "zweiter Lauf: nicht neu gemessen" "$(gemessen)" "1"
hat "zweiter Lauf: sagt es" "$OUT" "nicht neu gemessen"
check "zweiter Lauf: Geraet unveraendert" "$(sha256sum "$CONF" | cut -d' ' -f1)" "$_sum"
check "zweiter Lauf: Manifest nicht gewachsen" "$(wc -l <"$MANIFEST")" "$_z"
# Anzeige ohne Ton (Modul "keine", ohne alsa_karte) -> nichts zu messen (Zusage 5)
printf 'keine\n' >"$R/opt/chimera/state/anzeige"
messung beide
fahr run
check "Anzeige ohne Ton: rc 0" "$RC" "0"
hat "Anzeige ohne Ton: benannt" "$OUT" "keinen Ton"
check "Anzeige ohne Ton: nicht gemessen" "$(gemessen)" "1"
# Unbekannte Anzeige -> Befund, nicht raten
printf 'gibtsnicht\n' >"$R/opt/chimera/state/anzeige"
fahr run
check "unbekannte Anzeige: rc 1" "$RC" "1"
hat "unbekannte Anzeige: benannt" "$OUT" "hat kein Modul"
printf 'whisplay\n' >"$R/opt/chimera/state/anzeige"
NEU=1 fahr run
check "CHIMERA_MIKRO_NEU=1: neu gemessen" "$(gemessen)" "2"
hat "neu gemessen: Geraet da" "$(cat "$CONF")" "pcm.chimera_mikro"
hat_nicht "neu gemessen: Kanalauswahl weg" "$(cat "$CONF")" "ttable"

# andere Anzeige in der alten Messung -> neu messen
python3 - "$MESS" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["anzeige"] = "andere"; json.dump(d, open(sys.argv[1], "w"))
PY
fahr run
check "Messung von anderer Anzeige: neu gemessen" "$(gemessen)" "3"

# --- 4. Fremde Datei ------------------------------------------------------------
mkroot fremd; messung rechts 1
printf '# von Hand\npcm.chimera_mikro { type hw card 0 }\n' >"$CONF"
fahr run
check "fremde Datei: rc 1" "$RC" "1"
hat "fremde Datei: benannt" "$OUT" "nicht von Chimera"
hat "fremde Datei: unangetastet" "$(cat "$CONF")" "von Hand"

# --- 5. Trockenlauf ---------------------------------------------------------------
mkroot trocken; rm -f "$W/zaehler"; messung rechts 1
fahr dry
check "Trockenlauf: rc 0" "$RC" "0"
check "Trockenlauf: nicht gemessen" "$(gemessen)" "0"
check "Trockenlauf: kein Geraet" "$([ -e "$CONF" ] && echo da || echo weg)" "weg"

# --- 6. Rueckbau -------------------------------------------------------------------
mkroot rueckbau; messung rechts 1
fahr run
printf 'x\n' >"$R/etc/alsa/conf.d/60-fremd.conf"
set +e
RMOUT="$(env CHIMERA_ROOT="$R" CHIMERA_MANIFEST="$MANIFEST" CHIMERA_LOG_DIR="$R/logs" \
             CHIMERA_MODE=run sh "$RMSTEP" 2>&1)"; RMRC=$?
set -e
check "Rueckbau: rc 0" "$RMRC" "0"
check "Rueckbau: Geraet weg" "$([ -e "$CONF" ] && echo da || echo weg)" "weg"
check "Rueckbau: Messung weg" "$([ -e "$MESS" ] && echo da || echo weg)" "weg"
check "Rueckbau: fremde Datei bleibt" "$([ -e "$R/etc/alsa/conf.d/60-fremd.conf" ] && echo da || echo weg)" "da"

# --- 7. Auswertung mit den Werten vom chimera-pi --------------------------------------
_aus="$(PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from chimera.displays.mikro import KanalWert, auswerten
L = [KanalWert(1000, -21.1, 2.5, -79.7), KanalWert(2000, -17.6, 3.7, -91.0), KanalWert(3000, -19.8, -7.8, -96.3)]
R = [KanalWert(1000, -7.2, -23.4, -85.7), KanalWert(2000, -1.7, -32.8, -90.1), KanalWert(3000, -2.3, -47.1, -89.5)]
b = auswerten(L, R); print(b.entscheidung, b.kanal, "|", "; ".join(b.gruende))
b = auswerten(R, R); print(b.entscheidung, b.kanal)
b = auswerten(R, L); print(b.entscheidung, b.kanal)
stumm = [KanalWert(f, -95.0, 0.0, -96.0) for f in (1000, 2000, 3000)]
b = auswerten(stumm, stumm); print(b.entscheidung, "|", "; ".join(b.gruende))
b = auswerten(stumm, R); print(b.entscheidung, b.kanal, "|", "; ".join(b.gruende))
leise = [KanalWert(w.ton_hz, w.grundton_db - 15, w.klirr_db, w.rauschen_db) for w in R]
b = auswerten(leise, R); print(b.entscheidung)
ein_klirr = [R[0], R[1], KanalWert(3000, -2.3, -5.0, -89.5)]
b = auswerten(ein_klirr, R); print(b.entscheidung, "|", "; ".join(b.warnungen))
PY
)"
_z1="$(printf '%s\n' "$_aus" | sed -n 1p)"
hat "chimera-pi-Werte: rechts" "$_z1" "^rechts 1"
hat "chimera-pi-Werte: Grund klirrt" "$_z1" "links: klirrt"
check "zwei saubere Kanaele: beide" "$(printf '%s\n' "$_aus" | sed -n 2p)" "beide None"
check "Seiten vertauscht: links" "$(printf '%s\n' "$_aus" | sed -n 3p)" "links 0"
hat "nichts gehoert: keins" "$(printf '%s\n' "$_aus" | sed -n 4p)" "^keins | kein Testton gehoert"
hat "ein Kanal stumm: der andere" "$(printf '%s\n' "$_aus" | sed -n 5p)" "^rechts 1 | links: hoert keinen Testton"
check "15 dB leiser, aber sauber: beide (leiser ist kein Defekt)" "$(printf '%s\n' "$_aus" | sed -n 6p)" "beide"
hat "ein einzelner Ton ueber der Grenze: beide mit Warnung" "$(printf '%s\n' "$_aus" | sed -n 7p)" "^beide | links: einzelner Ton"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
