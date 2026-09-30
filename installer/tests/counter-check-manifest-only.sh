#!/bin/sh
# Gegenprobe zu Regel 10o (Was nicht im Manifest steht, gehoert nicht uns).
#
# Baut den frueheren, falschen Entwurf nach: Der Uninstaller entfernte ohne
# Manifest die Pfade, deren Name auf Chimera hindeutete. Der Test MUSS das
# finden -- sonst schuetzt er die Regel nicht, sondern nur den Zufall, dass
# gerade niemand loescht.
set -u
export TMPDIR=/tmp

SRC="$(cd "$(dirname "$0")/../.." && pwd)"
W="/tmp/gp-10o-$$"
mkdir -p "$W"
(cd "$SRC" && find installer uninstaller -type f 2>/dev/null |
	cpio -pdm "$W" 2>/dev/null)

T="$W/installer/tests/test-uninstall-roundtrip.sh"

run() { sh "$T" >"$W/out.txt" 2>&1; echo $?; }

result() {
	printf '%-56s ' "$1"
	if [ "$2" = "0" ]; then
		echo "GRUEN  <-- FEHLER, haette rot sein muessen"
		return 1
	fi
	echo "rot    (richtig)"
	return 0
}

FAIL=0

printf '%-56s ' "Ausgangslage unveraendert"
if [ "$(run)" = "0" ]; then echo "gruen  (richtig)"; else
	echo "ROT    <-- Ausgangslage ist schon kaputt"; cat "$W/out.txt"; FAIL=1
fi

# 1. DER FALSCHE ENTWURF: ohne Manifest die bekannten Pfade entfernen.
#    Genau so stand es in einer frueheren Fassung dieser Datei.
cp "$W/uninstaller/lib/discover.sh" "$W/disc.bak"
cat >>"$W/uninstaller/lib/discover.sh" <<'PATCH'

# Nachgebauter Fehler: loescht, was nur gefunden wurde.
discover_report() {
	log "Was jetzt am System ist"
	for _p in $(chimera_known_paths); do
		if [ -e "$_p" ]; then
			info "entferne: $_p"
			rm -rf "$_p"
		fi
	done
	return 0
}
PATCH
result "Uninstaller loescht Funde ohne Manifesteintrag" "$(run)" || FAIL=1
cp "$W/disc.bak" "$W/uninstaller/lib/discover.sh"

# 2. Die Umkehrung: Regel 10o durch WEGSEHEN erfuellen. Nichts loeschen,
#    aber auch nichts berichten. Das erfuellt den Buchstaben und verfehlt
#    den Zweck -- der Nutzer braucht die Fakten.
cp "$W/uninstaller/lib/discover.sh" "$W/disc2.bak"
cat >>"$W/uninstaller/lib/discover.sh" <<'PATCH'

# Nachgebauter Fehler: schweigt ueber die Funde.
discover_report() {
	log "Was jetzt am System ist"
	info "nichts zu melden."
	return 0
}
PATCH
result "Uninstaller schweigt ueber die Funde" "$(run)" || FAIL=1
cp "$W/disc2.bak" "$W/uninstaller/lib/discover.sh"

# 3. Berichten, aber ohne Begruendung. Ein Fund ohne Erklaerung sieht wie
#    ein Versehen aus -- der Nutzer weiss nicht, ob da noch was kommt.
cp "$W/uninstaller/lib/discover.sh" "$W/disc3.bak"
sed -i 's/Diese Funde bleiben unangetastet\./GEFUNDEN./' \
	"$W/uninstaller/lib/discover.sh"
sed -i '/nicht belegt, dass der Installer sie angelegt hat/d' \
	"$W/uninstaller/lib/discover.sh"
sed -i '/nicht im Manifest steht, fasst der Uninstaller nicht an/d' \
	"$W/uninstaller/lib/discover.sh"
sed -i '/Wer sie entfernen will, tut es von Hand/d' \
	"$W/uninstaller/lib/discover.sh"
result "Funde ohne Begruendung berichtet" "$(run)" || FAIL=1
cp "$W/disc3.bak" "$W/uninstaller/lib/discover.sh"

printf '%-56s ' "nach Zuruecksetzen wieder gruen"
if [ "$(run)" = "0" ]; then echo "gruen  (richtig)"; else
	echo "ROT    <-- Zuruecksetzen unvollstaendig"; cat "$W/out.txt"; FAIL=1
fi

rm -rf "$W" 2>/dev/null
echo
if [ "$FAIL" -eq 0 ]; then
	echo "Gegenprobe vollstaendig: Regel 10o ist durch Tests geschuetzt."
else
	echo "GEGENPROBE FEHLGESCHLAGEN -- der Test schuetzt die Regel nicht."
fi
exit "$FAIL"
