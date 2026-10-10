#!/bin/sh
# Tests fuer die Anzeigenerkennung ueber mehrere Quellen.
#
# Warum: Vorher sah display_detect NUR in das HAT-EEPROM. Auf dem
# ausgelieferten Whisplay ist das EEPROM nachweislich NICHT programmiert
# (docs/HARDWARE-BEFUNDE.md) -- dort findet die Erkennung "keins" und
# Schritt 40 bricht ab, obwohl die Anzeige angeschlossen ist.
#
# Die weiteren Quellen sind am Herstellertreiber belegt, nicht geraten:
# dtoverlay-Eintrag, ALSA-Karte, gebautes Kernelmodul. Hier wird jede
# Quelle einzeln angeschaltet und einzeln als Treffer gefordert.
#
# Gegenprobe: display.sh ohne die Kennungen. Sie muss "keins" melden,
# wo die echte "whisplay" sagt.

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

printf '=== Anzeigenerkennung: mehrere Quellen ===\n'

KVER="$(uname -r)"
R="$W/root"
mkdir -p "$R/proc/device-tree" "$R/boot" "$R/boot/firmware" "$R/proc/sys/kernel" \
	"$R/proc/asound" "$R/lib/modules"
printf '%s\n' "$KVER" >"$R/proc/sys/kernel/osrelease"

# Aufrufer: laedt die beiden Bibliotheken und gibt Typ und Quelle aus.
# Ohne Subshell, damit die Quelle die Funktion ueberlebt.
cat >"$W/aufruf.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
. "$HERE/lib/module.sh"
. "$1"
display_detect >/dev/null 2>&1 || true
printf '%s|%s\n' "${DISPLAY_TYP:-?}" "${DISPLAY_QUELLE:-}"
EOF
chmod +x "$W/aufruf.sh"

lauf() {
	set +e
	OUT="$(CHIMERA_ROOT="$R" sh "$W/aufruf.sh" "$1" 2>&1)"
	RC=$?
	set -e
}

# --- Ausgangslage: nichts angeschlossen ------------------------------------
lauf "$HERE/lib/display.sh"
check "ohne alles -> keins" "$OUT" "keins|"

# --- Quelle 1: Overlay-Eintrag in der Bootkonfiguration --------------------
printf 'dtoverlay=whisplay-soundcard\n' >"$R/boot/config.txt"
lauf "$HERE/lib/display.sh"
check "Overlay-Eintrag -> whisplay" "$OUT" "whisplay|overlay:dtoverlay=whisplay-soundcard"

# Nur ueber /boot/config.txt reicht nicht: die zweite Ablage wird ebenfalls
# geprueft (andere Distributionen legen sie woanders ab).
rm -f "$R/boot/config.txt"
printf 'dtoverlay=whisplay-soundcard\n' >"$R/boot/firmware/config.txt"
lauf "$HERE/lib/display.sh"
check "Overlay in /boot/firmware reicht auch" "$OUT" "whisplay|overlay:dtoverlay=whisplay-soundcard"
rm -f "$R/boot/firmware/config.txt"

# --- Quelle 2: ALSA-Karte --------------------------------------------------
printf ' 0 [whisplaysound  ]: Whisplay - Whisplay Sound\n' >"$R/proc/asound/cards"
lauf "$HERE/lib/display.sh"
check "ALSA-Karte -> whisplay" "$OUT" "whisplay|alsa:whisplaysound"
rm -f "$R/proc/asound/cards"

# --- Quelle 3: gebautes Kernelmodul ----------------------------------------
mkdir -p "$R/lib/modules/$KVER/kernel/sound/soc/codecs"
: >"$R/lib/modules/$KVER/kernel/sound/soc/codecs/snd-soc-whisplay-soundcard.ko"
lauf "$HERE/lib/display.sh"
check "Kernelmodul -> whisplay" "$OUT" "whisplay|modul:snd-soc-whisplay"
rm -rf "$R/lib/modules/$KVER/kernel"

# --- Unbekanntes EEPROM bleibt unbekannt, wenn nichts weiter passt ----------
mkdir -p "$R/proc/device-tree/hat"
printf 'Fremdhersteller\0' >"$R/proc/device-tree/hat/vendor"
printf 'Fremdgeraet\0' >"$R/proc/device-tree/hat/product"
lauf "$HERE/lib/display.sh"
check "fremdes EEPROM ohne Kennung -> unbekannt" "$OUT" "unbekannt|"
rm -rf "$R/proc/device-tree/hat"

# --- EEPROM vorhanden, Kennung daneben: trotzdem whisplay -------------------
# Der wichtige Fall: unprogrammiertes EEPROM und eingerichteter Treiber.
# Der HAT-Knoten ist leer, die Erkennung darf NICHT aufgeben.
mkdir -p "$R/proc/device-tree/hat"
printf 'dtoverlay=whisplay-soundcard\n' >"$R/boot/config.txt"
lauf "$HERE/lib/display.sh"
check "leeres EEPROM + Overlay -> whisplay" "$OUT" "whisplay|overlay:dtoverlay=whisplay-soundcard"
rm -rf "$R/proc/device-tree/hat" "$R/boot/config.txt"

# --- Gegenprobe: ohne Kennungen --------------------------------------------
sed -e 's/^\(\t*\)echo "\(overlay:[^"]*\)"/\1echo ""/' \
	-e 's/^\(\t*\)echo "\(alsa:[^"]*\)"/\1echo ""/' \
	-e 's/^\(\t*\)echo "\(modul:[^"]*\)"/\1echo ""/' \
	"$HERE/lib/display.sh" >"$W/display-alt.sh"
if cmp -s "$W/display-alt.sh" "$HERE/lib/display.sh"; then
	bad "Gegenprobe nicht vorbereitet -- Mutation griff nicht"
else
	ok "Gegenprobe vorbereitet (Kennungen entfernt)"
fi
lauf "$W/display-alt.sh"
check "Gegenprobe: ohne Kennungen -> keins" "$OUT" "keins|"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
