#!/bin/sh
# Gegenprobe zu test-uninstall-pairing.sh.
#
# Stellt die real aufgetretenen Fehler wieder her und verlangt, dass der
# Test rot wird. Ein Test, von dem niemand gezeigt hat, dass er rot werden
# KANN, ist eine Zusage ohne Beleg.
#
# Die zweite Probe ist die wichtigste: Sie baut den echten Fehler nach, den
# der Test finden soll -- Schritt 40 haengte per `printf >>` an config.txt
# an, ohne ins Manifest einzutragen. Waere der Test dafuer blind, wuerde er
# genau den Fall durchlassen, fuer den er geschrieben wurde.
set -u
export TMPDIR=/tmp

SRC="$(cd "$(dirname "$0")/../.." && pwd)"
W="/tmp/gp-pair-$$"
mkdir -p "$W"
(cd "$SRC" && find installer uninstaller -type f 2>/dev/null |
	cpio -pdm "$W" 2>/dev/null)

T="$W/installer/tests/test-uninstall-pairing.sh"

run() { sh "$T" >"$W/out.txt" 2>&1; echo $?; }

result() {
	printf '%-54s ' "$1"
	if [ "$2" = "0" ]; then
		echo "GRUEN  <-- FEHLER, haette rot sein muessen"
		return 1
	fi
	echo "rot    (richtig)"
	return 0
}

FAIL=0

printf '%-54s ' "Ausgangslage unveraendert"
if [ "$(run)" = "0" ]; then echo "gruen  (richtig)"; else
	echo "ROT    <-- Ausgangslage ist schon kaputt"; cat "$W/out.txt"; FAIL=1
fi

# 1. Gegenstueck loeschen.
mv "$W/uninstaller/steps/40-remove-display.sh" "$W/40.bak"
result "Gegenstueck zu Schritt 40 fehlt" "$(run)" || FAIL=1
mv "$W/40.bak" "$W/uninstaller/steps/40-remove-display.sh"

# 2. DER ECHTE FEHLER: an config.txt anhaengen, ohne einzutragen.
#    Nachgebaut wie er war -- `printf >>` statt manifest_line.
cp "$W/installer/steps/40-install-display.sh" "$W/40i.bak"
python3 - "$W/installer/steps/40-install-display.sh" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
# manifest_line-Aufruf durch das alte printf ersetzen, und alle anderen
# manifest_-Aufrufe entfernen, damit der Schritt wirklich nichts eintraegt.
s = s.replace('manifest_line "$BOOT_CFG" "$_bs_zeile" || {',
              'printf \'%s\\n\' "$_bs_zeile" >>"$BOOT_CFG" || {')
s = re.sub(r'^\s*manifest_(record|has|report|apt)\b.*$', '', s, flags=re.M)
open(p, "w", encoding="utf-8").write(s)
PY
result "Schritt 40 aendert config.txt ohne Manifesteintrag" "$(run)" || FAIL=1
cp "$W/40i.bak" "$W/installer/steps/40-install-display.sh"

# 3. Rueckbauschritt ignoriert vorher_da -- deinstalliert also auch
#    Pakete, die vor Chimera da waren.
cp "$W/uninstaller/steps/20-remove-packages.sh" "$W/20u.bak"
sed -i 's/vorher_da/egal_woher/g' "$W/uninstaller/steps/20-remove-packages.sh"
result "Rueckbau unterscheidet neu nicht von vorher_da" "$(run)" || FAIL=1
cp "$W/20u.bak" "$W/uninstaller/steps/20-remove-packages.sh"

# 4. Ein Rueckbauschritt ohne Vorlage -- entfernt auf Verdacht.
printf '#!/bin/sh\napt-get remove -y geist\n# vorher_da\n' \
	>"$W/uninstaller/steps/90-remove-ghost.sh"
result "Rueckbauschritt ohne Installationsschritt" "$(run)" || FAIL=1
rm -f "$W/uninstaller/steps/90-remove-ghost.sh"

# 5. Die Ausnahmeliste als Hintertuer missbrauchen: 10-check-system
#    installiert plotzlich Pakete, gilt aber weiter als "nur pruefend".
cp "$W/installer/steps/10-check-system.sh" "$W/10.bak"
printf 'apt-get install -y heimlich\n' >>"$W/installer/steps/10-check-system.sh"
result "als 'nur pruefend' gelisteter Schritt installiert doch" "$(run)" || FAIL=1
cp "$W/10.bak" "$W/installer/steps/10-check-system.sh"

printf '%-54s ' "nach Zuruecksetzen wieder gruen"
if [ "$(run)" = "0" ]; then echo "gruen  (richtig)"; else
	echo "ROT    <-- Zuruecksetzen unvollstaendig"; cat "$W/out.txt"; FAIL=1
fi

rm -rf "$W"
echo
if [ "$FAIL" -eq 0 ]; then
	echo "Gegenprobe vollstaendig: der Test wird bei jedem Rueckfall rot."
else
	echo "GEGENPROBE FEHLGESCHLAGEN -- der Test misst nicht, was er zusagt."
fi
exit "$FAIL"
