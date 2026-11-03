#!/bin/sh
# Tests fuer den Shell-Rand der Anzeigenerkennung (lib/display.sh).
#
# Die Entscheidung selbst lebt seit 11.10.2026 im Treiberpaket
# (src/chimera/displays/erkennen.py) und wird dort geprueft
# (tests/test_displays.py mit Gegenprobe). Hier geht es um das, was die
# Shell daraus macht:
#
#   * DISPLAY_TYP / DISPLAY_QUELLE / Belege kommen ohne Subshell an
#   * Spuren einer frueheren Einrichtung (Overlay-Zeile, ALSA-Karte,
#     gebautes Kernelmodul) WAEHLEN NICHT -- sie belegen nur, dass die
#     Karte schon einmal in einer Whisplay steckte (smilez, 11.10.2026:
#     die Karte wandert zwischen Boards; wer nach Spuren waehlt, treibt
#     ein E-Paper mit dem Whisplay-Treiber an)
#   * ohne Python/ohne Quellbaum: kein Ergebnis, kein Raten (rc 1)
#
# Gegenprobe: die Erkennung so verfaelscht, dass "eingerichtet" waehlt --
# der Test muss rot werden.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }

W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-signatur.XXXXXX" 2>/dev/null)" || W=""
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
# Grund-Texte enthalten Umlaute (Python); Shell-Dateien bleiben ASCII.
# Verglichen wird deshalb "typ|anfang des grundes".
kopf() { printf '%s' "$1" | cut -c1-"$2"; }

printf '=== Anzeigenerkennung: Shell-Rand ===\n'

KVER="$(uname -r)"
R="$W/root"
mkdir -p "$R/boot/firmware" "$R/proc/sys/kernel" "$R/proc/asound" "$R/lib/modules" \
	"$R/sys/bus/i2c/devices/i2c-1" "$R/chimera-probe"
printf '%s\n' "$KVER" >"$R/proc/sys/kernel/osrelease"

# Aufrufer: laedt die Bibliotheken und gibt Typ und Grund aus. Ohne
# Subshell, damit der Grund die Funktion ueberlebt. $1 = Quellbaum.
cat >"$W/aufruf.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
. "$HERE/lib/module.sh"
. "$HERE/lib/display.sh"
CHIMERA_DISPLAY_SRC="$1"; export CHIMERA_DISPLAY_SRC
display_detect >/dev/null 2>&1 || true
printf '%s|%s\n' "${DISPLAY_TYP:-}" "${DISPLAY_QUELLE:-}"
EOF
chmod +x "$W/aufruf.sh"

lauf() {
	set +e
	OUT="$(CHIMERA_ROOT="$R" sh "$W/aufruf.sh" "$1" 2>&1)"
	RC=$?
	set -e
}

SRC="$HERE/../src"

# --- Ausgangslage: nichts messbar -> Rueckfall "keine", benannt -------------
printf '' >"$R/chimera-probe/st7789-dc27"
printf '0' >"$R/chimera-probe/i2c-1-1a"
printf '0' >"$R/chimera-probe/i2c-1-10"
lauf "$SRC"
check "nichts messbar -> Rueckfall keine" "$(kopf "$OUT" 21)" "keine|nichts erkannt "

# --- Spuren einer Einrichtung waehlen NICHT ----------------------------------
printf 'dtoverlay=whisplay-soundcard\n' >"$R/boot/firmware/config.txt"
printf ' 0 [whisplaysound  ]: Whisplay - Whisplay Sound\n' >"$R/proc/asound/cards"
mkdir -p "$R/lib/modules/$KVER/kernel/sound/soc/codecs"
: >"$R/lib/modules/$KVER/kernel/sound/soc/codecs/snd-soc-whisplay-soundcard.ko"
lauf "$SRC"
check "Overlay+ALSA+Modul ohne Kennung -> trotzdem keine" "$(kopf "$OUT" 21)" "keine|nichts erkannt "

# ... aber sie werden als Belege genannt (Regel 10e: benannt, nicht stumm).
cat >"$W/belege.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
. "$HERE/lib/module.sh"
. "$HERE/lib/display.sh"
CHIMERA_DISPLAY_SRC="$1"; export CHIMERA_DISPLAY_SRC
display_detect >/dev/null 2>&1 || true
display_belege
EOF
BELEGE="$(CHIMERA_ROOT="$R" sh "$W/belege.sh" "$SRC" 2>&1)"
case "$BELEGE" in
	*"[ja  ] whisplay   eingerichtet"*"whisplay-soundcard vorhanden"*) ok "Overlay-Spur wird als Beleg genannt" ;;
	*) bad "Overlay-Spur fehlt in den Belegen: $BELEGE" ;;
esac
case "$BELEGE" in
	*"ALSA-Karte whisplaysound vorhanden"*) ok "ALSA-Spur wird als Beleg genannt" ;;
	*) bad "ALSA-Spur fehlt in den Belegen" ;;
esac

# --- Kennung da, Codec da -> whisplay, Grund benannt ------------------------
printf '8181b3' >"$R/chimera-probe/st7789-dc27"
printf '1' >"$R/chimera-probe/i2c-1-1a"
lauf "$SRC"
check "Kennung + Codec -> whisplay" "$OUT" "whisplay|eindeutiger Treffer"

# --- Kennung da, kein Codec: einziger Kandidat, aber gesagt -----------------
printf '0' >"$R/chimera-probe/i2c-1-1a"
lauf "$SRC"
check "Kennung ohne Codec -> einziger Kandidat (benannt)" "$(kopf "$OUT" 26)" "whisplay|einziger Kandidat"

# --- Ohne Quellbaum: kein Ergebnis, kein Raten ------------------------------
lauf "$W/gibtsnicht"
check "ohne Quellbaum: kein Typ" "$OUT" "|"

# --- display_list / display_get ohne Python: leer und rc 1 -------------------
cat >"$W/ohnepy.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
. "$HERE/lib/display.sh"
CHIMERA_DISPLAY_PYTHON=/nonexistent/python3
if display_get whisplay name >/dev/null 2>&1; then echo "rc0"; else echo "rc1"; fi
EOF
check "display_get ohne Python: rc 1" "$(sh "$W/ohnepy.sh" 2>/dev/null)" "rc1"

# --- Leitungen belegt: Befund lesen (ohne Hardware pruefbar) ----------------
#
# Die Erkennung meldet "belegt", wenn der laufende Dienst die Pins haelt.
# Das ist eine Aussage ueber die Messung, nicht ueber das Panel -- Schritt 40
# wertet es deshalb nicht als Befund, sondern uebernimmt den festgehaltenen
# Typ (mit Nachweis, siehe unten).
cat >"$W/belegt.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
. "$HERE/lib/display.sh"
DISPLAY_BEFUND="$1"
if display_leitungen_belegt; then echo "belegt"; else echo "frei"; fi
EOF
check "Befund mit belegten Leitungen -> belegt" \
	"$(sh "$W/belegt.sh" '{"belegt":["whisplay"],"gewaehlt":null}' 2>/dev/null)" "belegt"
check "Befund ohne belegte Leitungen -> frei" \
	"$(sh "$W/belegt.sh" '{"belegt":[],"gewaehlt":"whisplay"}' 2>/dev/null)" "frei"
check "ohne Befund -> frei (keine Annahme)" "$(sh "$W/belegt.sh" '' 2>/dev/null)" "frei"

# --- Festgehaltener Typ gilt nur MIT Nachweis --------------------------------
#
# state/anzeige ist ein Merker, keine Messung. Uebernommen wird er nur, wenn
# der Nachweis aus display.json JETZT zutrifft -- sonst waere ein Panelwechsel
# unsichtbar (und ein Merker wuerde luegen).
SRC2="$W/src2"
cp -r "$SRC" "$SRC2"
mkdir -p "$SRC2/chimera/displays/immerda" "$SRC2/chimera/displays/nieda"
printf '%s\n' '{"typ":"immerda","name":"Attrappe immer da","breite":240,"hoehe":280,"farben":"rgb565","bildrate":0,"darstellung":"animiert","pins":{},"busse":[],"deps":{"pip":[],"apt":[]},"erkennung":[],"pruefe":"true"}' \
	>"$SRC2/chimera/displays/immerda/display.json"
printf '%s\n' '{"typ":"nieda","name":"Attrappe nie da","breite":240,"hoehe":280,"farben":"rgb565","bildrate":0,"darstellung":"animiert","pins":{},"busse":[],"deps":{"pip":[],"apt":[]},"erkennung":[],"pruefe":"false"}' \
	>"$SRC2/chimera/displays/nieda/display.json"
cat >"$W/nachgew.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
. "$HERE/lib/module.sh"
. "$HERE/lib/display.sh"
CHIMERA_DISPLAY_SRC="$2"; export CHIMERA_DISPLAY_SRC
if t="$(display_typ_nachgewiesen "$1")"; then printf '%s\n' "$t"; else echo "KEIN"; fi
EOF
NA="$(mktemp -d "$CHIMERA_TESTDIR/anzeige.XXXXXX" 2>/dev/null || echo "$W/anzeigedir")"
mkdir -p "$NA"
nachgew() { CHIMERA_ROOT="$R" HERE="${3:-$HERE}" sh "$W/nachgew.sh" "$1" "${2:-$SRC2}" 2>/dev/null; }

printf 'immerda\n' >"$NA/anzeige"
check "Nachweis trifft -> Typ uebernommen" "$(nachgew "$NA/anzeige")" "immerda"
printf 'nieda\n' >"$NA/anzeige"
check "Nachweis trifft nicht -> kein Typ" "$(nachgew "$NA/anzeige")" "KEIN"
printf 'kenneichnicht\n' >"$NA/anzeige"
check "unbekannter Typ -> kein Typ" "$(nachgew "$NA/anzeige")" "KEIN"
printf 'immerda\n' >"$NA/anzeige"
check "fehlende Zustandsdatei -> kein Typ" "$(nachgew "$NA/gibtsnicht")" "KEIN"

# Gegenprobe: Nachweis entfernt -> der Merker gilt wieder blind, der Test
# oben muss rot werden. (Ein Regressionstest ohne Gegenprobe misst nichts.)
INST2="$W/inst2"
mkdir -p "$INST2/lib"
cp "$HERE/lib/common.sh" "$HERE/lib/module.sh" "$INST2/lib/" 2>/dev/null || true
cp "$HERE/lib/display.sh" "$INST2/lib/display.sh"
sed -i 's|sh -c "$_dtn_p" >/dev/null 2>&1 \|\| return 1|true|' "$INST2/lib/display.sh"
if cmp -s "$INST2/lib/display.sh" "$HERE/lib/display.sh"; then
	bad "Gegenprobe (Nachweis) nicht vorbereitet -- Mutation griff nicht"
else
	ok "Gegenprobe (Nachweis) vorbereitet"
fi
printf 'nieda\n' >"$NA/anzeige"
check "Gegenprobe: ohne Nachweis gilt der Merker blind" "$(nachgew "$NA/anzeige" "$SRC2" "$INST2")" "nieda"

# --- Gegenprobe: "eingerichtet" waehlt doch (die alte Haltung) --------------
MUT="$W/src"
cp -r "$SRC" "$MUT"
sed -i 's/elif klasse == "eindeutig" and treffer is True:/elif klasse in ("eindeutig", "eingerichtet") and treffer is True:/' \
	"$MUT/chimera/displays/erkennen.py"
if cmp -s "$MUT/chimera/displays/erkennen.py" "$SRC/chimera/displays/erkennen.py"; then
	bad "Gegenprobe nicht vorbereitet -- Mutation griff nicht"
else
	ok "Gegenprobe vorbereitet (eingerichtet waehlt)"
fi
printf '' >"$R/chimera-probe/st7789-dc27"
lauf "$MUT"
case "$OUT" in
	whisplay*) ok "Gegenprobe: verfaelschte Erkennung waehlt nach Spuren -- der Test oben faengt das" ;;
	*) bad "Gegenprobe: Mutation hatte keine Wirkung ($OUT)" ;;
esac

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
