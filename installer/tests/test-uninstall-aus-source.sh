#!/bin/sh
# Der Deinstallierer laeuft AUS source/ -- und entfernt source/ selbst.
#
# Genau so wird er auf dem Geraet aufgerufen (/opt/chimera/source/
# uninstaller/chimera-uninstall). Gefunden 10.10.2026: Der Rueckbau von
# Schritt 50 filterte nur nach der Art `verzeich`, die auch Schritt 00
# benutzt, und loeschte source/ mitten im Lauf -- die folgenden Schritte
# meldeten "can't open". Ein Rueckbau entfernt nur, was sein eigener
# Schritt eingetragen hat (manifest_list_von).
#
# CHIMERA_RM50 ueberstimmt den Rueckbau 50 (Gegenprobe:
# counter-check-uninstall-aus-source.sh).

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-rm-src.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Deinstallierer aus source/ ===\n'

R="$W/root"
S="$R/opt/chimera/source"
V="$R/opt/chimera/productive/venv"
mkdir -p "$R/opt/chimera/state" "$S" "$V/bin"
( cd "$REPO" && tar -cf - --exclude=.git . ) | ( cd "$S" && tar -xf - )
[ -n "${CHIMERA_RM50:-}" ] && cp "$CHIMERA_RM50" "$S/uninstaller/steps/50-remove-python.sh"
printf '#\n' >"$V/bin/python"
M="$R/opt/chimera/state/manifest.tsv"
printf 'z\t00-source\tverzeich\t%s\t\n' "$S" >"$M"
printf 'z\t50-python\tverzeich\t%s\t\n' "$V" >>"$M"

set +e
CHIMERA_ROOT="$R" CHIMERA_LOG_DIR="$W/logs" CHIMERA_MANIFEST="$M" \
	sh "$S/uninstaller/chimera-uninstall" >"$W/aus" 2>&1
rc=$?
set -e

if [ "$rc" -eq 0 ]; then ok "Lauf rc 0"; else bad "Lauf rc $rc"; fi
if grep -q "can't open\|No such file" "$W/aus"; then
	bad "ein Schritt fehlte mitten im Lauf (source/ zu frueh weg)"
else ok "kein Schritt fehlte mitten im Lauf"; fi
[ -e "$V" ] && bad "venv blieb" || ok "venv (Schritt 50) entfernt"
[ -e "$S" ] && bad "source/ blieb" || ok "source/ (Schritt 00) zuletzt entfernt"
[ -d "$W/logs" ] && ok "Protokoll bleibt" || bad "Protokoll fehlt"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
