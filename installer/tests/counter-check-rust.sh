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
	if ! python3 - "$_neu" "$3" "$4" <<'PY'
import sys
p, a, b = sys.argv[1:4]
s = open(p).read()
if a not in s:
    sys.exit(3)
open(p, "w").write(s.replace(a, b, 1))
PY
	then
		bad "$1: Mutation griff nicht (Muster fehlt)"
		return
	fi
	if cmp -s "$_neu.orig" "$_neu"; then
		bad "$1: Mutation griff nicht (Datei unveraendert)"
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
	'URL="$CHIMERA_RUST_URL/rust-$QUELLE_C"' 'URL="$CHIMERA_RUST_URL/rust-abc1234"' \
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
	"		'')
			warn \"Kein Commit der Quelle" "		'__nie__')
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

# M-L1: Die Versionsprobe entfaellt fuer die lokale Datei.
mutation lokal-ohne-version step \
	'if [ "$_ist" != "chimera-tor $SOLL_V" ]; then' 'if false; then' \
	"lokal falsche Version: rc 2"

# M8: Idempotenz fehlt -- immer neu laden.
mutation immer-laden step \
	'if [ -n "$_eigen_summe" ] && [ "$_eigen_summe" = "$SUMME" ] && \' 'if false && \' \
	"ohne Zustand, Binary passend: sagt es"

# M9: Alte Manifestzeile bleibt stehen (zwei Zeilen fuer dieselbe Datei).
mutation manifest-doppelt step \
	'if [ -n "$_eigen_summe" ] && [ -f "$CHIMERA_MANIFEST" ]; then' 'if false; then' \
	"neuer Commit: eine Manifestzeile fuer die Datei"

# M10: Trockenlauf legt doch ab.
mutation trockenlauf-schreibt step \
	'info "[wuerde ablegen] $BIN (root, 755)"
	log_close 0; exit 0
fi' 'info "[wuerde ablegen] $BIN (root, 755)"
fi' \
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

# M16: Der Kurzweg "rust/ unveraendert" faellt weg -- jeder Doku-Commit verlangt
# wieder ein Prerelease (genau der Befund, den die Zusage beseitigt).
mutation kurzweg-aus step \
	'if [ "$STILL" = 1 ] && [ -n "$_eigen_summe" ] && \' 'if false && \' \
	"baumgleich: ohne Prerelease rc 0 (kein Befund)"

# M17: Es zaehlt nur der Commit, nicht der Baum -- ein geaenderter rust/-Baum
# hielte dann still (veraltetes Binary bliebe liegen).
mutation baum-egal step \
	'[ "$BAUM_HASH" = "$_alt_h" ]' '[ -n "$_alt_h" ]' \
	"baum geaendert, kein Prerelease: rc 1"

# M18: Der Kurzweg prueft die Pruefsumme nicht -- ein ausgetauschtes Binary
# bliebe als "unveraendert" stehen.
mutation kurzweg-ohne-summe step \
	'[ "$(network_checksum "$BIN")" = "$_eigen_summe" ] && \' ': && \' \
	"baumgleich, Binary veraendert: wieder das Richtige"

# M19: Der Kurzweg prueft nicht, ob das Binary laeuft und die Version nennt.
mutation kurzweg-ohne-laufprobe step \
	'[ "$("$BIN" --version 2>/dev/null || true)" = "chimera-tor $SOLL_V" ]' ':' \
	"baumgleich, Binary laeuft nicht: kein Stillhalten"

# M20: Die VERSION zaehlt beim Stillhalten nicht mit (das Binary nennte die
# alte Version).
mutation version-egal step \
	'[ "$_alt_v" = "$SOLL_V" ]; then' 'true; then' \
	"andere Version im Zustand: kein Stillhalten (Befund ohne Netz)"

# M21: Der Zustand wird nie geschrieben -- dann gibt es kein Stillhalten und
# jeder Lauf braucht das Netz.
mutation zustand-fehlt step \
	"	printf '%s %s %s\\n' \"\$1\" \"\$2\" \"\$3\" >\"\$RUST_STAND.neu\"" \
	"	: >\"\$RUST_STAND.neu\"" \
	"baumgleich: Zustand nennt den Commit"

# M22: Fehlt das Binary, wird der neue Commit geladen statt der Stand des
# Zustands -- zu einem Doku-Commit gibt es aber kein Prerelease.
mutation neuer-commit-statt-stand step \
	'[ "$STILL" = 1 ] && QUELLE_C="$_alt_c"' ':' \
	"Binary fehlt, Baum gleich: rc 0"

# M23: Der Kurzweg schreibt im Trockenlauf doch -- er kuendigt nicht an, sondern
# tut, als waere er fertig.
mutation trockenlauf-kurzweg step \
	'info "[wuerde behalten] $BIN (rust/ unveraendert seit $_alt_c, Version $SOLL_V)"' 'info "Rust unveraendert seit $_alt_c"' \
	"Trockenlauf, Baum gleich: kuendigt Behalten an"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
