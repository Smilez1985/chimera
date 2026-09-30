#!/bin/sh
# Rundlauf: eintragen, zurueckbauen, pruefen was uebrig ist.
#
# Das ist der eigentliche Test des Manifests. Alle anderen Pruefungen sehen
# den Quelltext an; dieser laesst die Kette wirklich laufen -- gegen ein
# Wegwerf-Wurzelverzeichnis, ohne das System anzufassen.
#
# Gefragt wird, was nach dem Rueckbau uebrig ist:
#   - eine Zeile, die als `neu` eingetragen war, muss WEG sein
#   - eine Zeile, die als `vorher_da` eingetragen war, muss STEHEN
#
# Der zweite Punkt ist der wichtigere. Ein Rueckbau, der zu viel entfernt,
# faellt niemandem auf, bis etwas anderes nicht mehr startet.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
INST="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$INST/.." && pwd)"

OK=0
BAD=0
ok()  { OK=$((OK+1));  printf '  ok    %s\n' "$1"; }
bad() { BAD=$((BAD+1)); printf '  FEHL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"; else
		bad "$1"
		printf '        erwartet: %s\n        bekommen: %s\n' "$3" "$2"
	fi
}

TMPD="${TMPDIR:-/tmp}"
W="$TMPD/chimera-roundtrip.$$"
mkdir -p "$W/boot" "$W/var/lib/chimera" "$W/var/log/chimera" || {
	printf 'Kann Testverzeichnis nicht anlegen: %s\n' "$W"
	exit 2
}

# mktemp-Falle: Bei kaputtem TMPDIR liefert es einen leeren Pfad, und
# `rm -rf ""` oder Schreiben nach "/..." trifft das echte System. Darum
# selbst pruefen, statt zu hoffen.
case "$W" in
	/tmp/*|/var/tmp/*) : ;;
	*) printf 'Unerwarteter Testpfad, Abbruch: %s\n' "$W"; exit 2 ;;
esac

CHIMERA_ROOT="$W"; export CHIMERA_ROOT
CHIMERA_MANIFEST="$W/var/lib/chimera/manifest.tsv"; export CHIMERA_MANIFEST
CHIMERA_LOG_DIR="$W/var/log/chimera"; export CHIMERA_LOG_DIR

. "$INST/lib/common.sh"
. "$INST/lib/manifest.sh"

CHIMERA_STEP="test-roundtrip"; export CHIMERA_STEP

printf '=== Rundlauf: eintragen und zurueckbauen ===\n'

# --- Ausgangslage: eine Bootkonfiguration mit fremdem Inhalt ------------
BOOT="$W/boot/config.txt"
cat >"$BOOT" <<'EOF'
# vom Nutzer, hat mit Chimera nichts zu tun
dtparam=watchdog=on
dtparam=i2c_arm=on
EOF

# --- 1. Eintragen wie der Installer es tut ------------------------------
#
# i2c_arm steht schon drin -> muss als `vorher_da` landen.
# spi steht nicht drin      -> muss als `neu` landen und angehaengt werden.
manifest_line "$BOOT" "dtparam=i2c_arm=on" >/dev/null 2>&1
manifest_line "$BOOT" "dtparam=spi=on"     >/dev/null 2>&1

grep -q '^dtparam=spi=on$' "$BOOT" && ok "neue Zeile wurde angehaengt" ||
	bad "neue Zeile fehlt in der Bootkonfiguration"

VORHER="$(manifest_list zeile | grep -c 'vorher_da' || true)"
NEUE="$(manifest_list zeile | grep -c 'neu:' || true)"
check "eine Zeile als vorher_da vermerkt" "${VORHER:-0}" "1"
check "eine Zeile als neu vermerkt"       "${NEUE:-0}" "1"

# --- 2. Zurueckbauen ----------------------------------------------------
#
# Der Rueckbauschritt wird mit demselben Wurzelverzeichnis aufgerufen.
# KEEP_PACKAGES=1, damit der Lauf keine Pakete anfasst -- hier geht es um
# die Bootkonfiguration.
KEEP_PACKAGES=1; export KEEP_PACKAGES
CHIMERA_MODE=run; export CHIMERA_MODE
unset CHIMERA_LOGFILE 2>/dev/null || true

sh "$REPO/uninstaller/steps/40-remove-display.sh" >"$W/rueckbau.log" 2>&1
RC=$?
check "Rueckbauschritt endet ohne Fehler" "$RC" "0"

# --- 3. Was ist uebrig? -------------------------------------------------
if grep -q '^dtparam=spi=on$' "$BOOT"; then
	bad "die als neu eingetragene Zeile steht noch da"
else
	ok "die als neu eingetragene Zeile ist entfernt"
fi

if grep -q '^dtparam=i2c_arm=on$' "$BOOT"; then
	ok "die vorher vorhandene Zeile steht noch da"
else
	bad "FREMDE Zeile entfernt -- der Rueckbau greift zu weit"
fi

if grep -q '^dtparam=watchdog=on$' "$BOOT"; then
	ok "nicht im Manifest gefuehrte Zeile unberuehrt"
else
	bad "eine Zeile entfernt, die nie im Manifest stand"
fi

# Die Datei darf nicht leer sein. Wird sie per Pipe geschrieben und der
# Erzeuger liefert nichts, gelingt das Umbenennen trotzdem -- mit leerer
# Zieldatei. Bei einer Bootkonfiguration kostet das den Ausbau der Karte.
[ -s "$BOOT" ] && ok "Bootkonfiguration ist nicht leer" ||
	bad "Bootkonfiguration ist LEER -- Datenverlust"

# --- 4. Der Rueckbau laeuft zweimal ohne Schaden ------------------------
#
# Idempotenz gilt fuer den Rueckbau genauso wie fuer die Installation.
sh "$REPO/uninstaller/steps/40-remove-display.sh" >"$W/rueckbau2.log" 2>&1
RC2=$?
check "zweiter Rueckbaulauf endet ohne Fehler" "$RC2" "0"
grep -q '^dtparam=i2c_arm=on$' "$BOOT" &&
	ok "zweiter Lauf laesst die fremde Zeile stehen" ||
	bad "zweiter Lauf hat die fremde Zeile entfernt"

# --- 5. Trockenlauf aendert nichts --------------------------------------
manifest_line "$BOOT" "dtparam=i2s=on" >/dev/null 2>&1
CHIMERA_MODE=dry; export CHIMERA_MODE
sh "$REPO/uninstaller/steps/40-remove-display.sh" >"$W/trocken.log" 2>&1
if grep -q '^dtparam=i2s=on$' "$BOOT"; then
	ok "Trockenlauf entfernt nichts"
else
	bad "Trockenlauf hat die Zeile entfernt -- er aendert das System"
fi

# Aufraeumen, aber der Exitcode des Aufraeumens darf das Testergebnis
# NICHT bestimmen. Genau das ist hier passiert: `rm -rf` scheiterte (in
# einer PRoot-Sandbox darf nicht jede Datei geloescht werden), gab 1
# zurueck, und weil es der letzte Befehl vor dem Ergebnis war, meldete der
# Test Exitcode 2 -- bei zehn gruenen Pruefungen und ohne eine einzige
# Fehlermeldung.
#
# Ein Test, der am Aufraeumen scheitert, meldet einen Fehler, den es nicht
# gibt. Das ist die Spiegelseite des stillen Erfolgs: stiller Fehlschlag.
rm -rf "$W" 2>/dev/null || warn_rest=1
if [ -d "$W" ]; then
	printf '  hinw  Testverzeichnis blieb liegen: %s\n' "$W"
fi

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$OK" "$BAD"
[ "$BAD" -eq 0 ]
