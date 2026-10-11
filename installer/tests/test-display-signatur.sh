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
