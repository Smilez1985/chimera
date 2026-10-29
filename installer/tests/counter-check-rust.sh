#!/bin/sh
# Gegenprobe zu test-rust.sh (Regel 9).
#
# Je eine Zusage von Modul 55, seinem Rueckbau oder des Commit-Lesens
# (lib/source.sh) wird in einer KOPIE verfaelscht; der Test laeuft gegen die
# Kopie (CHIMERA_STEP_55 / CHIMERA_STEP_RM55 / CHIMERA_SRCLIB) und muss rot
# werden -- am erwarteten Pruefpunkt. Eine Mutation, die die Datei nicht
# veraendert, ist selbst ein Fehler.
set -eu
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
STEP="$HERE/steps/55-rust.sh"
RMSTEP="$REPO/uninstaller/steps/55-remove-rust.sh"
SRCLIB="$HERE/lib/source.sh"
TEST="$HERE/tests/test-rust.sh"
PASS=0; FAIL=0
: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-rust-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM
ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Rust-Binary (Modul 55) ===\n'
if sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
	tail -5 "$G/basis.txt"
fi

# $1 Name, $2 Ziel (step|rm|lib), $3 python-Ersetzung "alt=>neu" als zwei
# Argumente $3 $4, $5 erwarteter FAIL-Text.
# Die Kopie liegt in einem Baum mit derselben Struktur wie das Repo: Die
# Schritte finden ihre Bibliotheken ueber dirname($0)/.. bzw. /../.. --
# ausserhalb davon wird der Test aus dem FALSCHEN Grund rot.
mutation() {
	_m="$G/$1"; mkdir -p "$_m"
	cp -r "$HERE" "$_m/installer"
	mkdir -p "$_m/uninstaller/steps"
	cp "$RMSTEP" "$_m/uninstaller/steps/"
	cp "$REPO/VERSION" "$_m/VERSION"
	case "$2" in
		step) _neu="$_m/installer/steps/55-rust.sh"; _env="CHIMERA_STEP_55=$_neu" ;;
		rm)   _neu="$_m/uninstaller/steps/55-remove-rust.sh"; _env="CHIMERA_STEP_RM55=$_neu" ;;
		lib)  _neu="$_m/installer/lib/source.sh"; _env="CHIMERA_SRCLIB=$_neu" ;;
	esac
	cp "$_neu" "$_neu.orig"
	python3 - "$_neu" "$3" "$4" <<'PY'
import sys
p, a, b = sys.argv[1:4]
s = open(p).read()
if a not in s:
    sys.exit(3)
open(p, "w").write(s.replace(a, b, 1))
PY
	if [ $? -ne 0 ] || cmp -s "$_neu.orig" "$_neu"; then
		bad "$1: Mutation griff nicht (Muster fehlt)"
		return
	fi
	if env "$_env" sh "$TEST" >"$_m/aus.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $5" "$_m/aus.txt"; then
		ok "$1: rot bei '$5'"
	else
		bad "$1: rot, aber nicht bei '$5'"
		grep 'FAIL' "$_m/aus.txt" | head -3
	fi
}

# M1: Rueckfall auf irgendein Binary -- der Commit wird nicht benutzt.
mutation commit-egal step \
	'URL="$CHIMERA_RUST_URL/rust-$COMMIT"' 'URL="$CHIMERA_RUST_URL/rust-abc1234"' \
	"anderer Commit: rc 1"

# M2: Pruefsumme wird beim Laden nicht geprueft (leere erwartete Summe). Die
# Nachkontrolle nach dem Ablegen faengt es noch auf (zweite Schicht), darum
# bricht der Punkt 'benannt' (die Meldung kommt von network_fetch) und
# 'altes Binary unberuehrt' -- nicht 'nichts abgelegt'.
mutation ohne-summenpruefung step \
	'network_fetch "$URL/$ASSET" "$_tmp/$ASSET" "$SUMME"' 'network_fetch "$URL/$ASSET" "$_tmp/$ASSET" ""' \
	"falsche Summe: benannt"

# M3: Version wird nicht verglichen.
mutation ohne-versionspruefung step \
	'if [ "$_ist" != "chimera-tor $SOLL_V" ]; then' 'if false; then' \
	"falsche Version: rc 2"

# M4: Ein Binary, das nie gestartet wurde, wird abgelegt (Lauf-Probe fehlt).
mutation ohne-laufprobe step \
	'_ist="$("$_tmp/$ASSET" --version 2>/dev/null || true)"' '_ist="chimera-tor $SOLL_V"' \
	"Binary laeuft nicht: rc 2"

# M5: Ohne Commit wird geraten statt gemeldet.
mutation commit-raten step \
	"	'')
		warn \"Kein Commit der Quelle" "	'__nie__')
		warn \"Kein Commit der Quelle" \
	"ohne Commit: benannt"

# M6: Architektur wird nicht geprueft.
mutation arch-egal step \
	'case "$_arch" in
	aarch64|arm64) : ;;' 'case "aarch64" in
	aarch64|arm64) : ;;' \
	"armv7l: rc 1"

# M7: Fremde Datei am Zielort wird ueberschrieben.
mutation fremde-datei step \
	'if [ -z "$_eigen_summe" ]; then
		err "$BIN existiert und steht nicht im Manifest' 'if false; then
		err "$BIN existiert und steht nicht im Manifest' \
	"fremde Datei: rc 2"

# M8: Idempotenz fehlt -- immer neu laden.
mutation immer-laden step \
	'if [ -n "$_eigen_summe" ] && [ "$_eigen_summe" = "$SUMME" ] && \' 'if false && \' \
	"zweiter Lauf: sagt es"

# M9: Alte Manifestzeile bleibt stehen (zwei Zeilen fuer dieselbe Datei).
mutation manifest-doppelt step \
	'if [ -n "$_eigen_summe" ] && [ -f "$CHIMERA_MANIFEST" ]; then' 'if false; then' \
	"neuer Commit: eine Manifestzeile fuer die Datei"

# M10: Trockenlauf legt doch ab.
mutation trockenlauf-schreibt step \
	'if is_dry_run; then
	info "[wuerde laden]' 'if false; then
	info "[wuerde laden]' \
	"Trockenlauf: rc 0"

# M11: Rueckbau loescht auch eine ausgetauschte Datei.
mutation rueckbau-ohne-summe rm \
	'if [ -n "$_soll" ] && [ "$(network_checksum "$_pfad")" != "$_soll" ]; then' 'if false; then' \
	"Rueckbau fremd: rc 1"

# M12: Rueckbau entfernt bin/ auch mit Fremdem darin (rm -rf statt rmdir).
mutation rueckbau-rmrf rm \
	'if rmdir "$_d" 2>/dev/null; then' 'if rm -rf "$_d" 2>/dev/null; then' \
	"Rueckbau: Binary weg, bin/ mit Fremdem bleibt"

# M13: Commit wird auch bei geaendertem rust/ gelesen.
mutation commit-schmutzig lib \
	'[ -z "$_sc_s" ] || return 0' ':' \
	"rust/ geaendert: kein Commit"

# M14: Eine alte quelle-commit bleibt stehen, wenn der neue Stand keinen hat.
mutation alter-commit-bleibt lib \
	'		rm -f "$2"
		return 0' '		return 0' \
	"rust/ geaendert: alte Datei entfernt"

# M15: Commit wird auch ohne .git "gefunden" (git rev-parse im Elternbaum).
mutation git-elternbaum lib \
	'[ -d "$1/.git" ] || return 0' ':' \
	"Baum im fremden Repo, ohne eigenes .git: kein Commit"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
