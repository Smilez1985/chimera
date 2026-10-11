#!/bin/sh
# Tests fuer den Ton zur Laufzeit (Schritt 40, 11.10.2026).
#
# Zusagen:
#   1. Die Bootkonfiguration bleibt NEUTRAL: Was der Herstellerinstaller
#      fuer den Ton eintraegt (dtparam=i2s=on, dtoverlay=whisplay-soundcard),
#      nimmt boot_neutral() wieder heraus -- mit Sicherung, atomar, und nie
#      eine Zeile, die vor Chimera schon da war (Manifest: vorher_da).
#   2. Eine Bereinigung, die die Datei leeren wuerde, wird NICHT geschrieben
#      (Regel 8a: stiller Erfolg mit leerer Bootkonfiguration = totes Geraet).
#   3. `python3 -m chimera.displays ton <typ>`: Karte da -> nichts laden,
#      rc 0; Modul ohne Ton -> rc 2; ohne root -> benannter Fehler, rc 1.
#
# Gegenprobe am Ende: boot_neutral ohne die Leer-Pruefung schreibt die
# leere Datei -- der Test muss das rot sehen.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-ton.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 -- erwartet '$3', bekam '$2'"; fi; }

printf '=== Ton zur Laufzeit ===\n'

# boot_neutral aus Schritt 40 herausloesen: Der Schritt ist ein Skript, die
# Funktion steht zwischen zwei Markern. Geprueft wird die ECHTE Funktion,
# nicht eine Abschrift.
R="$W/root"
mkdir -p "$R/boot/firmware" "$R/opt/chimera/state"
BOOT="$R/boot/firmware/config.txt"
MANIFEST="$R/opt/chimera/state/manifest.tsv"

extrahiere() {  # $1 Quelle, $2 Ziel
	awk '/^boot_neutral\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$1" >"$2"
	grep -q '^boot_neutral() {' "$2"
}
extrahiere "$HERE/steps/40-install-display.sh" "$W/boot_neutral.sh" || {
	bad "boot_neutral() nicht aus Schritt 40 extrahierbar"; exit 1; }
ok "boot_neutral() aus Schritt 40 extrahiert ($(wc -l <"$W/boot_neutral.sh") Zeilen)"

# Aufrufer: Bibliotheken + Funktion, dann Lauf. $1 Funktionsdatei, $2 Modus.
cat >"$W/lauf.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
. "$HERE/lib/manifest.sh"
. "$1"
CHIMERA_MODE="$2"
BOOT_CFG="$BOOT"
TON_OVERLAYS="whisplay-soundcard"
ANZAHL_NEU=0
boot_neutral; rc=$?
printf 'rc=%s neu=%s\n' "$rc" "$ANZAHL_NEU"
EOF

lauf() {
	set +e
	OUT="$(env BOOT="$BOOT" CHIMERA_ROOT="$R" CHIMERA_MANIFEST="$MANIFEST" \
	           CHIMERA_STEP=40-install-display CHIMERA_LOG_DIR="$W/logs" \
	           sh "$W/lauf.sh" "$1" "$2" 2>&1)"
	RC=$?
	set -e
}

# --- 1. Herstellereintraege verschwinden, Nutzerzeilen bleiben ---------------
printf '# vom Nutzer\ndtparam=audio=off\ndtparam=spi=on\ndtparam=i2c_arm=on\ndtparam=i2s=on\ndtoverlay=whisplay-soundcard\ndtparam=watchdog=on\n' >"$BOOT"
lauf "$W/boot_neutral.sh" run
case "$OUT" in *"rc=0"*) ok "Bereinigung rc 0" ;; *) bad "Bereinigung: $OUT" ;; esac
if grep -qxF "dtparam=i2s=on" "$BOOT"; then bad "i2s=on steht noch drin"; else ok "i2s=on entfernt"; fi
if grep -qxF "dtoverlay=whisplay-soundcard" "$BOOT"; then bad "Overlay-Zeile steht noch drin"; else ok "dtoverlay=whisplay-soundcard entfernt"; fi
check "Nutzerzeilen und Busse bleiben" \
	"$(grep -c -E '^(# vom Nutzer|dtparam=audio=off|dtparam=spi=on|dtparam=i2c_arm=on|dtparam=watchdog=on)$' "$BOOT")" "5"
check "nichts anderes dazugekommen" "$(grep -c . "$BOOT")" "5"
if ls "$BOOT".chimera-*.bak >/dev/null 2>&1; then ok "Sicherung vor dem Eingriff angelegt"; else bad "keine Sicherung"; fi
case "$OUT" in *"neu=1"*) ok "Aenderung gezaehlt (Neustart-Hinweis)" ;; *) bad "Aenderung nicht gezaehlt: $OUT" ;; esac

# --- 2. Zweiter Lauf: nichts zu tun, keine neue Sicherung --------------------
_n_vorher="$(ls "$BOOT".chimera-*.bak 2>/dev/null | wc -l)"
lauf "$W/boot_neutral.sh" run
check "zweiter Lauf: nichts geaendert" "$OUT" "rc=0 neu=0"
check "zweiter Lauf: keine neue Sicherung" "$(ls "$BOOT".chimera-*.bak 2>/dev/null | wc -l)" "$_n_vorher"

# --- 3. Zeile war VOR Chimera da (Manifest vorher_da) -> bleibt -------------
printf 'dtparam=spi=on\ndtparam=i2s=on\n' >"$BOOT"
mkdir -p "$(dirname "$MANIFEST")"
printf '2026-10-11T00:00:00\t40-install-display\tzeile\t%s\tvorher_da:dtparam=i2s=on\n' "$BOOT" >"$MANIFEST"
lauf "$W/boot_neutral.sh" run
if grep -qxF "dtparam=i2s=on" "$BOOT"; then ok "vorher_da-Zeile bleibt stehen"; else bad "vorher_da-Zeile wurde entfernt"; fi
case "$OUT" in *"stand vor Chimera"*) ok "... und das wird gesagt" ;; *) bad "Grund fehlt: $OUT" ;; esac
rm -f "$MANIFEST"

# --- 4. Trockenlauf aendert nichts ------------------------------------------
printf 'dtparam=i2s=on\ndtoverlay=whisplay-soundcard\n' >"$BOOT"
_vorher="$(cat "$BOOT")"
lauf "$W/boot_neutral.sh" dry
check "Trockenlauf: Datei unveraendert" "$(cat "$BOOT")" "$_vorher"
case "$OUT" in *"[wuerde entfernen]"*) ok "Trockenlauf benennt, was es taete" ;; *) bad "Trockenlauf schweigt: $OUT" ;; esac

# --- 5. Bereinigung, die die Datei leeren wuerde, wird NICHT geschrieben -----
printf 'dtparam=i2s=on\ndtoverlay=whisplay-soundcard\n' >"$BOOT"
lauf "$W/boot_neutral.sh" run
case "$OUT" in *"rc=1"*) ok "leer werdende Datei: Abbruch (rc 1)" ;; *) bad "leer werdende Datei: $OUT" ;; esac
check "leer werdende Datei: Original unangetastet" "$(grep -c . "$BOOT")" "2"

# --- 6. python3 -m chimera.displays ton ------------------------------------
SRC="$HERE/../src"
TONR="$W/tonroot"
mkdir -p "$TONR/proc/asound" "$W/bin-amixer"
# amixer-Huelle: Mixer setzen gilt als gelungen, Aufrufe werden gezaehlt.
printf '#!/bin/sh\necho "$@" >>"%s/amixer-aufrufe.txt"\n' "$W" >"$W/bin-amixer/amixer"
chmod +x "$W/bin-amixer/amixer"
PATH="$W/bin-amixer:$PATH"; export PATH
printf ' 0 [whisplaysound  ]: whisplaysound - Whisplay Sound\n' >"$TONR/proc/asound/cards"
set +e
OUT="$(CHIMERA_ROOT="$TONR" PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 python3 -m chimera.displays ton whisplay 2>&1)"; RC=$?
set -e
check "Karte da -> rc 0, nichts geladen" "$RC" "0"
case "$OUT" in *"bereits vorhanden"*) ok "Karte da -> 'bereits vorhanden'" ;; *) bad "Karte da: $OUT" ;; esac
check "Mixer trotzdem gesetzt (speaker, mic)" "$(grep -c -E 'name=(speaker|mic)' "$W/amixer-aufrufe.txt" 2>/dev/null)" "2"
set +e
OUT="$(CHIMERA_ROOT="$TONR" PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 python3 -m chimera.displays ton keine 2>&1)"; RC=$?
set -e
check "Modul ohne Ton -> rc 2" "$RC" "2"
rm -f "$TONR/proc/asound/cards"
set +e
OUT="$(CHIMERA_ROOT="$TONR" PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 python3 -m chimera.displays ton whisplay --json 2>&1)"; RC=$?
set -e
check "Karte fehlt, CHIMERA_ROOT gesetzt -> nichts geladen, rc 1" "$RC" "1"
case "$OUT" in *'"da": false'*) ok "JSON-Befund: da=false" ;; *) bad "JSON-Befund fehlt: $OUT" ;; esac

# --- 7. Schritt 40 uebergibt die Anzeige an den Dienst (RAM) -----------------
# Ganzer Schritt im Trockenlauf gegen eine erfundene Wurzel: Attrappen fuer
# Kennung + Codec, keine Hardware. Im Trockenlauf wird NICHT geschrieben,
# aber benannt; im echten Lauf (ohne root nicht fahrbar) prueft das der
# Echtlauf am Geraet (WHISPLAY-ABNAHME). Hier: der Dry-Run-Pfad und der
# Dateiname aus common.sh.
R7="$W/root7"
mkdir -p "$R7/boot/firmware" "$R7/sys/bus/i2c/devices/i2c-1" "$R7/chimera-probe" "$R7/opt/chimera/state" "$R7/var/lib/chimera"
printf 'dtparam=spi=on\ndtparam=i2c_arm=on\n' >"$R7/boot/firmware/config.txt"
printf '8181b3' >"$R7/chimera-probe/st7789-dc27"; printf '1' >"$R7/chimera-probe/i2c-1-1a"
set +e
OUT="$(env CHIMERA_ROOT="$R7" CHIMERA_MODE=dry CHIMERA_LOG_DIR="$W/logs" CHIMERA_MANIFEST="$R7/var/lib/chimera/manifest.tsv" \
	sh "$HERE/steps/40-install-display.sh" 2>&1)"; RC=$?
set -e
check "Schritt 40 Trockenlauf rc 0" "$RC" "0"
case "$OUT" in *"[wuerde schreiben] /run/chimera/anzeige.env (CHIMERA_ANZEIGE=whisplay)"*) ok "Trockenlauf benennt die Laufzeit-Uebergabe" ;; *) bad "Laufzeit-Uebergabe nicht benannt: $(printf '%s' "$OUT" | grep -i anzeige.env)" ;; esac
if [ -e "$R7/run/chimera/anzeige.env" ]; then bad "Trockenlauf hat anzeige.env geschrieben"; else ok "Trockenlauf schreibt anzeige.env nicht"; fi
check "Dateiname aus common.sh" "$(CHIMERA_ROOT= sh -c '. "$HERE/lib/common.sh"; printf %s "$CHIMERA_RUN_ANZEIGE"')" "/run/chimera/anzeige.env"

# --- Gegenprobe: Leer-Pruefung ausgeschaltet -> die leere Datei wird geschrieben
# Die Pruefung sitzt in write_atomic (eine Stelle). Mit CHIMERA_ALLOW_EMPTY=1
# ist sie aus -- dann muss Fall 5 kippen: Datei leer, rc 0.
printf 'dtparam=i2s=on\ndtoverlay=whisplay-soundcard\n' >"$BOOT"
set +e
OUT="$(env BOOT="$BOOT" CHIMERA_ROOT="$R" CHIMERA_MANIFEST="$MANIFEST" CHIMERA_ALLOW_EMPTY=1 \
           CHIMERA_STEP=40-install-display CHIMERA_LOG_DIR="$W/logs" \
           sh "$W/lauf.sh" "$W/boot_neutral.sh" run 2>&1)"
set -e
if [ "$(grep -c . "$BOOT")" = 0 ]; then
	ok "Gegenprobe: ohne Leer-Pruefung ist die Bootkonfiguration leer -- Fall 5 faengt das"
else
	bad "Gegenprobe: Leer-Pruefung liess sich nicht ausschalten ($(grep -c . "$BOOT") Zeilen, $OUT)"
fi

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
