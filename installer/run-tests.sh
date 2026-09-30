#!/bin/sh
# Alle hardwarefreien Installertests.
#
# Zwei Gruppen, beide Pflicht:
#
#   test-*.sh           pruefen den Installer
#   counter-check-*.sh  pruefen die Tests -- stellen den alten, kaputten
#                       Zustand wieder her und verlangen, dass der
#                       zugehoerige Test rot wird
#
# Die zweite Gruppe ist nicht Beiwerk. Ein Test, von dem niemand gezeigt
# hat, dass er rot werden KANN, ist eine Zusage ohne Beleg -- und genau so
# ist der erste Secrets-Pruefer monatelang blind gruen gewesen.
#
# Das Glob wird getrennt aufgezaehlt, weil `test-*.sh` die Gegenproben
# nicht erfasst. Ein Laeufer, der eine Datei nicht sieht, meldet nicht
# "uebersprungen", sondern schweigt -- schon passiert, deshalb steht es hier.
set -eu
cd "$(dirname "$0")"

GESAMT=0
SCHLECHT=0

lauf() {
	printf '=== %s ===\n' "$1"
	if sh "$1"; then
		GESAMT=$((GESAMT+1))
	else
		GESAMT=$((GESAMT+1))
		SCHLECHT=$((SCHLECHT+1))
		printf '!!! fehlgeschlagen: %s\n' "$1"
	fi
	printf '\n'
}

# set -e wuerde beim ersten roten Test abbrechen -- dann bleibt unbekannt,
# ob die uebrigen laufen. Hier wird alles ausgefuehrt und am Ende Bilanz
# gezogen.
set +e

for t in tests/test-*.sh; do
	[ -f "$t" ] || continue
	lauf "$t"
done

for t in tests/counter-check-*.sh; do
	[ -f "$t" ] || continue
	lauf "$t"
done

printf '========================================\n'
printf 'Testdateien: %d, davon fehlgeschlagen: %d\n' "$GESAMT" "$SCHLECHT"

if [ "$GESAMT" -eq 0 ]; then
	printf 'FEHLER: keine einzige Testdatei gefunden.\n'
	printf 'Ein Laeufer ohne Tests ist kein gruener Lauf, sondern ein Fund.\n'
	exit 2
fi

[ "$SCHLECHT" -eq 0 ]
