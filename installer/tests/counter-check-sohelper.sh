#!/bin/sh
# Gegenprobe zu test-sohelper.sh (Regel 9): je eine Zusage von
# lib/sohelper.sh verfaelschen, der Test muss an der erwarteten Stelle rot
# werden. Bleibt er gruen, misst die Zusage nichts.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HERE/lib/sohelper.sh"
TEST="$HERE/tests/test-sohelper.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-sohelper-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Ausfuehrer ===\n'

if CHIMERA_SOHELPER_LIB="$LIB" sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
	grep 'FAIL' "$G/basis.txt" | head -3
fi

mutation() {
	_m="$G/$1.sh"
	sed "$2" "$LIB" >"$_m"
	if cmp -s "$LIB" "$_m"; then bad "$1: Mutation griff nicht"; return; fi
	if CHIMERA_SOHELPER_LIB="$_m" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $3" "$G/$1.txt"; then
		ok "$1: rot bei '$3'"
	else
		bad "$1: rot, aber nicht bei '$3'"; grep 'FAIL' "$G/$1.txt" | head -3
	fi
}

# M-S1: Der Socket ist fuer alle offen.
mutation socket-offen \
	's|SocketMode=0660|SocketMode=0666|' \
	"Socket: Modus 0660 (nicht fuer alle)"

# M-S2: Der Socket gehoert dem Ausfuehrer statt dem Agenten -- dann kann der
# Agent nicht fragen, und jeder andere auch nicht.
mutation socket-gruppe \
	's|^SocketGroup=\$CHIMERA_DIENSTNUTZER$|SocketGroup=$CHIMERA_SOHELPER_NUTZER|' \
	"Socket: Gruppe des Agent-Dienstes (nur er fragt)"

# M-S3: Die Netz-Sperre faellt weg.
mutation ohne-netzsperre \
	'/^IPAddressDeny=any$/d' \
	"Dienst: kein Netz (Regel 5n)"

# M-S4: Der Ausfuehrer sieht die Schluessel.
mutation ohne-schluesselsperre \
	's|^InaccessiblePaths=\$CHIMERA_CONFIG$|InaccessiblePaths=/tmp|' \
	"Dienst: Schluessel unerreichbar"

# M-S5: Der Arbeitsordner ist fuer alle lesbar -- dann kann der Agent hinein.
mutation ordner-offen \
	'/\tchmod 700 "\$_so_p"/ s|chmod 700|chmod 755|' \
	"Arbeitsordner 700"

# M-S6: Der Nachweis faellt aus (immer "antwortet").
mutation ohne-nachweis \
	'/if ! "\$_so_prog" --ping/ s|if ! "\$_so_prog" --ping|if ! true; then :; fi; if false \&\& "\$_so_prog" --ping|' \
	"stumm: rc 1 (Befund)"

# M-S7: Der Ausfuehrer bekommt zusaetzliche Rechte (Gruppen des Agenten).
mutation mit-gruppen \
	'/^Group=\$CHIMERA_SOHELPER_NUTZER$/ a SupplementaryGroups=chimera' \
	"Dienst: keine SupplementaryGroups (weniger Rechte als der Agent)"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
