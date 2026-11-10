#!/bin/sh
# Gegenprobe zu test-einstieg.sh (Regel 9).
#
# Je eine Zusage des Einstiegs wird in einer Kopie des Baums verfaelscht; der
# Test laeuft gegen die Kopie (CHIMERA_EINSTIEG_BAUM) und muss rot werden,
# und zwar mit dem erwarteten Pruefpunkt. Eine Mutation, die die Datei nicht
# veraendert (Muster nicht gefunden), ist selbst ein Fehler -- sonst "faengt"
# der Test eine Mutation, die nie stattfand.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
TEST="$HERE/tests/test-einstieg.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-einstieg-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Einstieg ===\n'

# Ein Baum mit dem, was der Einstieg braucht: er selbst, der innere
# Installer mit Bibliotheken und Schritten, VERSION.
baum() {
	_b="$G/$1"
	mkdir -p "$_b/installer"
	cp "$REPO/chimera-installer.sh" "$_b/chimera-installer.sh"
	cp "$REPO/VERSION" "$_b/VERSION"
	cp "$HERE/chimera-install" "$_b/installer/chimera-install"
	cp -r "$HERE/lib" "$_b/installer/lib"
	cp -r "$HERE/steps" "$_b/installer/steps"
	printf '%s\n' "$_b"
}

# Unveraendert muss der Test gruen sein -- im Repo und in der Kopie. Sonst
# beweist Rot unten nichts (oder nur, dass der Kopie etwas fehlt).
if sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
	tail -5 "$G/basis.txt"
fi
# Braucht eine Pruefung einen gewoehnlichen Nutzer und meldet der Test sie
# als uebersprungen, laesst sich ihre Mutation hier nicht messen.
HINWEIS_PRUEFBAR=1
grep -q 'uebersprungen  ohne root' "$G/basis.txt" && HINWEIS_PRUEFBAR=0

_k="$(baum kopie)"
if CHIMERA_EINSTIEG_BAUM="$_k" sh "$TEST" >"$G/kopie.txt" 2>&1; then
	ok "Kopie des Baums gruen"
else
	bad "Kopie des Baums schon rot -- ihr fehlt etwas"
	tail -5 "$G/kopie.txt"
fi

# $1 Name, $2 Datei im Baum, $3 sed-Ausdruck, $4 erwarteter FAIL-Text
mutation() {
	_t="$(baum "$1")"
	_f="$_t/$2"
	sed "$3" "$_f" >"$_f.neu"
	if cmp -s "$_f" "$_f.neu"; then
		bad "$1: Mutation griff nicht (Muster fehlt in $2)"
		return
	fi
	mv "$_f.neu" "$_f"
	chmod 755 "$_f"
	if CHIMERA_EINSTIEG_BAUM="$_t" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $4" "$G/$1.txt"; then
		ok "$1: rot bei '$4'"
	else
		bad "$1: rot, aber nicht bei '$4'"
		grep 'FAIL' "$G/$1.txt" | head -3
	fi
}

# M1: Die Optionen gehen verloren -- aus --list wuerde ein echter Lauf.
mutation optionen-verloren chimera-installer.sh \
	's|^exec sh "\$INSTALLER" "\$@"$|exec sh "$INSTALLER"|' \
	"--list: gleiche Ausgabe wie installer/chimera-install"

# M2: Der Exitcode wird geschluckt -- ein gescheiterter Lauf saehe gut aus.
mutation exitcode-geschluckt chimera-installer.sh \
	's#^exec sh "\$INSTALLER" "\$@"$#sh "$INSTALLER" "$@" || true#' \
	"unbekannte Option: rc 2"

# M3: Keine Pruefung auf den inneren Installer -- die Shell meldet dann
# nur "can't open", ohne zu sagen, was zu tun ist. Erwartet wird der Punkt
# "benannt", nicht "rc 2": Den Exitcode liefert die Shell je nach Fassung
# selbst (BusyBox 2, andere 127), die Meldung liefert nur die Pruefung.
mutation ohne-pruefung chimera-installer.sh \
	'/^if \[ ! -f "\$INSTALLER" \]; then$/,/^fi$/d' \
	"ohne inneren Installer: benannt"

if [ "$HINWEIS_PRUEFBAR" = 1 ]; then
	# M4: Der Einstieg nennt sich nicht -- der Hinweis zeigt auf die innere Datei.
	mutation einstieg-nicht-genannt chimera-installer.sh \
		'/^export CHIMERA_EINSTIEG$/d' \
		"Hinweis nennt den Einstieg"

	# M5: Der innere Installer liest den Namen nicht (alter Stand).
	mutation hinweis-alt installer/chimera-install \
		's|\${CHIMERA_EINSTIEG:-\$0}|$0|' \
		"Hinweis nennt den Einstieg"
else
	printf '  uebersprungen  M4, M5 (Hinweis ohne root): hier nicht messbar, der Test ueberspringt die Pruefung\n'
fi

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
