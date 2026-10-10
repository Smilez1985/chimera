#!/bin/sh
# Gegenprobe zu test-uninstall-aus-source.sh: Rueckbau 50 mit dem alten
# Filter (nur Art, nicht Modul). Der Test muss rot werden.

set -eu
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-rm-src-gp.XXXXXX" 2>/dev/null)" || G=""
[ -n "$G" ] && [ -d "$G" ] || { echo "mktemp lieferte kein Verzeichnis"; exit 2; }
trap 'rm -rf "$G"' EXIT INT TERM

printf '=== Gegenprobe Deinstallierer aus source/ ===\n'
sed 's/manifest_list_von verzeich 50-python/manifest_list verzeich/' \
	"$REPO/uninstaller/steps/50-remove-python.sh" >"$G/alt.sh"
if cmp -s "$G/alt.sh" "$REPO/uninstaller/steps/50-remove-python.sh"; then
	echo "  FAIL  Mutation griff nicht"; exit 1
fi
if CHIMERA_RM50="$G/alt.sh" sh "$HERE/tests/test-uninstall-aus-source.sh" >"$G/aus" 2>&1; then
	echo "  FAIL  alter Filter: Test blieb gruen"; exit 1
fi
if grep -q 'FAIL  ein Schritt fehlte mitten im Lauf' "$G/aus"; then
	echo "  ok    alter Filter: rot bei 'ein Schritt fehlte mitten im Lauf'"
else
	echo "  FAIL  alter Filter: rot, aber anders"; grep FAIL "$G/aus" | head -3; exit 1
fi
printf '\nErgebnis: 1 ok, 0 fehlgeschlagen\n'
