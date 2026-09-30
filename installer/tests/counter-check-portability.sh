#!/bin/sh
# Gegenprobe zum Portabilitaetstest.
#
# Ein Test, der gruen ist, beweist nichts, solange nicht gezeigt ist, dass
# er auch rot werden KANN. Hier wird der alte Zustand kuenstlich
# wiederhergestellt -- einmal ein Umlaut, einmal fehlendes LC_ALL, einmal
# ein echter Bashism, einmal eine falsche Schrittkennung. Jeder Fall muss
# den Test zum Fehlschlag bringen.
#
# Laeuft gegen eine Kopie, nie gegen das Repo.
set -u
export TMPDIR=/tmp

SRC="$(cd "$(dirname "$0")/../.." && pwd)"
W="/tmp/gp-$$"
mkdir -p "$W"
(cd "$SRC" && find installer -type f | cpio -pdm "$W" 2>/dev/null)

T="$W/installer/tests/test-portability.sh"

run() {
	sh "$T" >"$W/out.txt" 2>&1
	echo $?
}

result() {
	printf '%-52s ' "$1"
	if [ "$2" = "0" ]; then
		echo "GRUEN  <-- FEHLER, haette rot sein muessen"
		return 1
	else
		echo "rot    (richtig)"
		return 0
	fi
}

FAIL=0

# 0. Ausgangslage: muss gruen sein, sonst messen die Proben nichts.
printf '%-52s ' "Ausgangslage unveraendert"
if [ "$(run)" = "0" ]; then echo "gruen  (richtig)"; else
	echo "ROT    <-- FEHLER, Ausgangslage ist schon kaputt"
	cat "$W/out.txt"; FAIL=1
fi

# 1. Umlaut wieder einbauen.
cp "$W/installer/lib/common.sh" "$W/common.bak"
printf '# Zurueck zum alten Zustand: Gr\303\274ss dich\n' >>"$W/installer/lib/common.sh"
result "Umlaut in common.sh" "$(run)" || FAIL=1
cp "$W/common.bak" "$W/installer/lib/common.sh"

# 2. LC_ALL entfernen.
sed -i '/^LC_ALL=C$/d' "$W/installer/lib/common.sh"
result "LC_ALL entfernt" "$(run)" || FAIL=1
cp "$W/common.bak" "$W/installer/lib/common.sh"

# 3. Echter Bashism im Code (nicht im Kommentar).
cp "$W/installer/lib/detect.sh" "$W/detect.bak"
printf 'gp_test() { if %s -n "$x" ]]; then :; fi; }\n' '[[' \
	>>"$W/installer/lib/detect.sh"
result "Bashism [[ ]] im Code" "$(run)" || FAIL=1
cp "$W/detect.bak" "$W/installer/lib/detect.sh"

# 4. Schrittkennung passt nicht zum Dateinamen.
cp "$W/installer/steps/20-install-packages.sh" "$W/step.bak"
sed -i 's/CHIMERA_STEP="20-install-packages"/CHIMERA_STEP="20-pakete"/' \
	"$W/installer/steps/20-install-packages.sh"
result "Schrittkennung passt nicht zum Dateinamen" "$(run)" || FAIL=1
cp "$W/step.bak" "$W/installer/steps/20-install-packages.sh"

# 5. Der echte Fehler von vorhin: Laeufer sucht im alten Verzeichnis.
#    Er laeuft damit ohne Fehler durch, findet aber keinen Schritt.
cp "$W/installer/chimera-install" "$W/run.bak"
sed -i 's|find "$HERE/steps"|find "$HERE/modules"|' "$W/installer/chimera-install"
result "Laeufer sucht im falschen Verzeichnis" "$(run)" || FAIL=1
cp "$W/run.bak" "$W/installer/chimera-install"

# 6. Und wieder gruen, nachdem alles zurueckgesetzt ist.
printf '%-52s ' "nach Zuruecksetzen wieder gruen"
if [ "$(run)" = "0" ]; then echo "gruen  (richtig)"; else
	echo "ROT    <-- FEHLER, Zuruecksetzen unvollstaendig"
	cat "$W/out.txt"; FAIL=1
fi

rm -rf "$W"
echo
if [ "$FAIL" -eq 0 ]; then
	echo "Gegenprobe vollstaendig: der Test wird bei jedem Rueckfall rot."
else
	echo "GEGENPROBE FEHLGESCHLAGEN -- der Test misst nicht, was er zusagt."
fi
exit "$FAIL"
