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

# --- Eigenes Spielfeld ----------------------------------------------------
#
# Der Laeufer darf nicht an derselben Klippe scheitern, die er prueft.
#
# In manchen Umgebungen zeigt TMPDIR auf ein Verzeichnis, das es hier gar
# nicht gibt (in der Android-App z. B. auf einen Pfad ausserhalb der
# Sandbox). mktemp liefert dann einen LEEREN Pfad, und ein Test, der dort
# einen Koeder anlegt, meldet "nicht anlegbar" -- obwohl der Installer in
# Ordnung ist. Der Lauf war dann rot wegen der Umgebung, nicht wegen des
# Codes.
#
# Deshalb: ein brauchbares Verzeichnis selbst einrichten und TMPDIR darauf
# setzen, BEVOR die erste Testdatei startet. Geprueft wird wie ueberall --
# mktemp kann auch hier einen leeren Pfad liefern, und das ist ein Abbruch,
# kein stiller Weiterlauf.
#
# CHIMERA_TEST_TMPDIR ueberstimmt die Wahl (fuer einen Lauf, der bewusst
# woanders arbeiten soll).
if [ -n "${CHIMERA_TEST_TMPDIR:-}" ]; then
	_tk_kandidaten="$CHIMERA_TEST_TMPDIR"
else
	_tk_kandidaten="${TMPDIR:-} /tmp /var/tmp $PWD"
fi

_tk_dir=""
for _tk_k in $_tk_kandidaten; do
	[ -n "$_tk_k" ] || continue
	[ -d "$_tk_k" ] && [ -w "$_tk_k" ] && { _tk_dir="$_tk_k"; break; }
done

if [ -z "$_tk_dir" ]; then
	printf 'FEHLER: kein beschreibbares Arbeitsverzeichnis gefunden.\n' >&2
	printf 'Geprueft: %s\n' "$_tk_kandidaten" >&2
	exit 2
fi

_TESTS_TMP="$(mktemp -d "$_tk_dir/.chimera-tests.XXXXXX" 2>/dev/null)" || _TESTS_TMP=""
if [ -z "$_TESTS_TMP" ] || [ ! -d "$_TESTS_TMP" ]; then
	printf 'FEHLER: mktemp lieferte kein Arbeitsverzeichnis in %s\n' "$_tk_dir" >&2
	exit 2
fi

TMPDIR="$_TESTS_TMP"
export TMPDIR
trap 'rm -rf "$_TESTS_TMP"' EXIT INT TERM

printf 'Arbeitsverzeichnis: %s\n\n' "$TMPDIR"

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
