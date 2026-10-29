#!/bin/sh
# Tests fuer Modul 55 (Rust-Binary chimera-tor) und den Commit aus Modul 00.
#
# Zusagen:
#   1. Das Binary kommt zum Commit der Quelle (rust-<commit>), nie "das
#      neueste": liegt nur ein Prerelease zu einem anderen Commit bereit,
#      ist das ein Befund (rc 1) und nichts wird abgelegt.
#   2. Die Pruefsumme entscheidet: ein veraendertes Binary wird nicht abgelegt
#      (rc 2), ein vorhandenes bleibt unberuehrt.
#   3. Das Binary muss laufen und die Version der Quelle nennen -- sonst
#      nichts abgelegt (rc 2).
#   4. Ohne Commit (Zip, geaenderter rust/-Baum) wird nicht geraten (rc 1).
#   5. Andere Architektur als aarch64: kein Binary (rc 1).
#   6. Idempotent: zweiter Lauf laedt nicht neu, Manifest waechst nicht.
#   7. Eine fremde Datei am Zielort wird nie ueberschrieben (rc 2).
#   8. Rueckbau 55 entfernt nur, was im Manifest steht UND noch die
#      eingetragene Pruefsumme hat; eine ausgetauschte Datei bleibt (rc 1).
#   9. Schritt 00: source_commit_festhalten schreibt den Commit eines
#      sauberen Klons, nichts bei fehlendem .git oder geaendertem rust/, und
#      entfernt dann eine alte Datei.
#
# Das Netz wird durch einen HTTP-Spiegel auf localhost ersetzt (CHIMERA_RUST_URL); das
# "Binary" ist ein kleines Skript, das --version beantwortet.
# Gegenproben: tests/counter-check-rust.sh

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
REPO="$(cd "$HERE/.." && pwd)"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-rust.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap '[ -n "${KEEP:-}" ] || rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 -- erwartet '$3', bekam '$2'"; fi; }
hat()      { if printf '%s' "$2" | grep -q -- "$3"; then ok "$1"; else bad "$1 -- '$3' fehlt"; fi; }
hat_nicht() { if printf '%s' "$2" | grep -q -- "$3"; then bad "$1 -- '$3' kam doch vor"; else ok "$1"; fi; }

STEP="${CHIMERA_STEP_55:-$HERE/steps/55-rust.sh}"
RMSTEP="${CHIMERA_STEP_RM55:-$REPO/uninstaller/steps/55-remove-rust.sh}"
SRCLIB="${CHIMERA_SRCLIB:-$HERE/lib/source.sh}"
VERSION_SOLL="$(tr -d ' \t\r\n' <"$REPO/VERSION")"

printf '=== Rust-Binary (Modul 55) ===\n'

# Ein "Binary", das wie chimera-tor antwortet.
binary_bauen() { # $1 Datei, $2 Version
	printf '#!/bin/sh\n[ "${1:-}" = --version ] && { echo "chimera-tor %s"; exit 0; }\nexit 2\n' "$2" >"$1"
	chmod 755 "$1"
}

# Spiegel: $W/spiegel/rust-<commit>/{chimera-tor-aarch64,.sha256}
spiegel() { # $1 Commit, $2 Version im Binary
	_d="$W/spiegel/rust-$1"
	mkdir -p "$_d"
	binary_bauen "$_d/chimera-tor-aarch64" "$2"
	# Je Commit ein anderer Inhalt: sonst haetten zwei Staende dieselbe
	# Summe und "schon vorhanden" verdeckte jeden Unterschied.
	printf '# commit %s\n' "$1" >>"$_d/chimera-tor-aarch64"
	( cd "$_d" && sha256sum chimera-tor-aarch64 >chimera-tor-aarch64.sha256 )
}

mkroot() { # $1 Name, $2 Commit der Quelle (leer = keiner)
	R="$W/$1"
	mkdir -p "$R/opt/chimera/state" "$R/logs"
	MANIFEST="$R/opt/chimera/state/manifest.tsv"
	[ -z "${2:-}" ] || printf '%s\n' "$2" >"$R/opt/chimera/state/quelle-commit"
	BIN="$R/opt/chimera/bin/chimera-tor"
}

fahr() { # $1 Modus; Variablen per env davor
	set +e
	OUT="$(env CHIMERA_ROOT="$R" CHIMERA_MANIFEST="$MANIFEST" CHIMERA_LOG_DIR="$R/logs" \
	           CHIMERA_MODE="$1" CHIMERA_RUST_URL="$URLBASIS" \
	           CHIMERA_ARCH="${ARCH:-aarch64}" CHIMERA_NETWORK_LIMIT=5 CHIMERA_DL_VERSUCHE=1 \
	           sh "${SCHRITT:-$STEP}" 2>&1)"
	RC=$?
	set -e
}
rueckbau() {
	set +e
	OUT="$(env CHIMERA_ROOT="$R" CHIMERA_MANIFEST="$MANIFEST" CHIMERA_LOG_DIR="$R/logs" \
	           CHIMERA_MODE=run sh "$RMSTEP" 2>&1)"
	RC=$?
	set -e
}
summe() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1 || true; }

# Spiegel als echter HTTP-Server auf localhost: network_fetch prueft vorher die
# Erreichbarkeit per TCP (file:// ginge daran vorbei und prueft den echten Weg
# nicht). Der Port wird vom System vergeben und aus der Ausgabe gelesen.
mkdir -p "$W/spiegel"
python3 - "$W/spiegel" "$W/port" >"$W/server.log" 2>&1 <<'PY' &
import http.server, os, socketserver, sys
os.chdir(sys.argv[1])
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
with socketserver.TCPServer(("127.0.0.1", 0), H) as s:
    open(sys.argv[2], "w").write(str(s.server_address[1]))
    s.serve_forever()
PY
SERVER=$!
trap '[ -n "${KEEP:-}" ] || rm -rf "$W"; kill "$SERVER" 2>/dev/null || true' EXIT INT TERM
_i=0; while [ ! -s "$W/port" ] && [ "$_i" -lt 50 ]; do sleep 0.1; _i=$((_i+1)); done
PORT="$(cat "$W/port" 2>/dev/null || true)"
[ -n "$PORT" ] || { echo "Spiegel nicht gestartet"; cat "$W/server.log"; exit 2; }
URLBASIS="http://127.0.0.1:$PORT"

# --- 1. Der Weg: Commit -> Prerelease -> abgelegt ----------------------------
spiegel abc1234 "$VERSION_SOLL"
mkroot gut abc1234
fahr run
check "gut: rc 0" "$RC" "0"
check "gut: Binary liegt da" "$([ -x "$BIN" ] && echo ja || echo nein)" "ja"
check "gut: Modus 755" "$(stat -c %a "$BIN" 2>/dev/null)" "755"
check "gut: Inhalt = Spiegel" "$(summe "$BIN")" "$(summe "$W/spiegel/rust-abc1234/chimera-tor-aarch64")"
check "gut: Binary laeuft" "$("$BIN" --version)" "chimera-tor $VERSION_SOLL"
hat "gut: Manifest Datei + Summe" "$(cat "$MANIFEST")" "$(summe "$BIN")"
hat "gut: Manifest Verzeichnis" "$(cat "$MANIFEST")" "verzeich"
hat "gut: Commit benannt" "$OUT" "Commit abc1234"
hat_nicht "gut: nichts Fremdes im Zielverzeichnis" "$(ls "$R/opt/chimera/bin")" "neu"

# --- 2. Anderer Commit: nie "das neueste" ---------------------------------------
spiegel def5678 "$VERSION_SOLL"
mkroot anderer 1111111
fahr run
check "anderer Commit: rc 1 (Befund)" "$RC" "1"
check "anderer Commit: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
hat "anderer Commit: benannt" "$OUT" "rust-1111111"
hat "anderer Commit: kein Rueckfall" "$OUT" "ANDERER Stand\|kein anderer Stand\|NICHT genommen"

# --- 3. Pruefsumme -----------------------------------------------------------
spiegel bad0001 "$VERSION_SOLL"
printf 'manipuliert\n' >>"$W/spiegel/rust-bad0001/chimera-tor-aarch64"
mkroot summe bad0001
fahr run
check "falsche Summe: rc 2" "$RC" "2"
check "falsche Summe: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
hat "falsche Summe: benannt" "$OUT" "Pruefsumme stimmt nicht"
# Ein vorhandenes, eigenes Binary bleibt bei falscher Summe unberuehrt.
mkroot summe2 abc1234; fahr run
_vor="$(summe "$BIN")"
printf 'bad0001\n' >"$R/opt/chimera/state/quelle-commit"
fahr run
check "falsche Summe: rc 2 auch mit altem Binary" "$RC" "2"
check "falsche Summe: altes Binary unberuehrt" "$(summe "$BIN")" "$_vor"

# --- 4. Version ----------------------------------------------------------------
spiegel aaa0001 "9.9.9"
mkroot version aaa0001
fahr run
check "falsche Version: rc 2" "$RC" "2"
check "falsche Version: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
hat "falsche Version: benannt" "$OUT" "statt 'chimera-tor $VERSION_SOLL'"
# Ein Binary, das gar nicht laeuft.
spiegel bbb0001 "$VERSION_SOLL"
printf 'kein programm\n' >"$W/spiegel/rust-bbb0001/chimera-tor-aarch64"
( cd "$W/spiegel/rust-bbb0001" && sha256sum chimera-tor-aarch64 >chimera-tor-aarch64.sha256 )
mkroot nolauf bbb0001
fahr run
check "Binary laeuft nicht: rc 2" "$RC" "2"
check "Binary laeuft nicht: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"

# --- 5. Ohne Commit ---------------------------------------------------------------
mkroot ohne ""
fahr run
check "ohne Commit: rc 1" "$RC" "1"
check "ohne Commit: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
hat "ohne Commit: benannt" "$OUT" "Kein Commit der Quelle"
mkroot kaputt "xyz"
fahr run
check "Commit kein Hex: rc 2" "$RC" "2"

# --- 6. Architektur -----------------------------------------------------------------
mkroot arm abc1234
ARCH=armv7l fahr run
check "armv7l: rc 1" "$RC" "1"
check "armv7l: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
hat "armv7l: benannt" "$OUT" "nur aarch64"

# --- 7. Idempotenz -------------------------------------------------------------------
mkroot idem abc1234
fahr run
_sum="$(summe "$BIN")"; _z="$(wc -l <"$MANIFEST")"; _m="$(stat -c %Y "$BIN")"
sleep 1
fahr run
check "zweiter Lauf: rc 0" "$RC" "0"
hat "zweiter Lauf: sagt es" "$OUT" "Schon vorhanden und geprueft"
check "zweiter Lauf: Datei unveraendert" "$(summe "$BIN")" "$_sum"
check "zweiter Lauf: nicht neu geschrieben" "$(stat -c %Y "$BIN")" "$_m"
check "zweiter Lauf: Manifest nicht gewachsen" "$(wc -l <"$MANIFEST")" "$_z"

# Neuer Commit -> Binary wird ersetzt, Manifest hat EINE Zeile fuer die Datei.
spiegel 2220002 "$VERSION_SOLL"
printf 'neuer-inhalt\n' >>"$W/spiegel/rust-2220002/chimera-tor-aarch64"
printf '#!/bin/sh\n[ "${1:-}" = --version ] && { echo "chimera-tor %s"; exit 0; }\n# neu\nexit 2\n' "$VERSION_SOLL" >"$W/spiegel/rust-2220002/chimera-tor-aarch64"
chmod 755 "$W/spiegel/rust-2220002/chimera-tor-aarch64"
( cd "$W/spiegel/rust-2220002" && sha256sum chimera-tor-aarch64 >chimera-tor-aarch64.sha256 )
printf '2220002\n' >"$R/opt/chimera/state/quelle-commit"
fahr run
check "neuer Commit: rc 0" "$RC" "0"
check "neuer Commit: Binary ersetzt" "$(summe "$BIN")" "$(summe "$W/spiegel/rust-2220002/chimera-tor-aarch64")"
check "neuer Commit: eine Manifestzeile fuer die Datei" "$(grep -c "	datei	$BIN	" "$MANIFEST")" "1"
hat "neuer Commit: neue Summe im Manifest" "$(cat "$MANIFEST")" "$(summe "$BIN")"

# --- 8. Fremde Datei -------------------------------------------------------------------
mkroot fremd abc1234
mkdir -p "$(dirname "$BIN")"; printf 'gehoert jemand anders\n' >"$BIN"
fahr run
check "fremde Datei: rc 2" "$RC" "2"
check "fremde Datei: Inhalt unveraendert" "$(cat "$BIN")" "gehoert jemand anders"
hat "fremde Datei: benannt" "$OUT" "nicht im Manifest"

# --- 9. Trockenlauf ----------------------------------------------------------------------
mkroot trocken abc1234
fahr dry
check "Trockenlauf: rc 0" "$RC" "0"
hat "Trockenlauf: kuendigt an" "$OUT" "wuerde laden"
check "Trockenlauf: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
check "Trockenlauf: Manifest unberuehrt" "$([ -e "$MANIFEST" ] && echo da || echo weg)" "weg"

# --- 10. Rueckbau ---------------------------------------------------------------------------
mkroot rueck abc1234; fahr run
rueckbau
check "Rueckbau: rc 0" "$RC" "0"
check "Rueckbau: Binary weg" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
check "Rueckbau: leeres bin/ weg" "$([ -d "$R/opt/chimera/bin" ] && echo da || echo weg)" "weg"
# Eine ausgetauschte Datei bleibt liegen.
mkroot rueck2 abc1234; fahr run
printf 'ausgetauscht\n' >"$BIN"
rueckbau
check "Rueckbau fremd: rc 1 (Befund)" "$RC" "1"
check "Rueckbau fremd: Datei bleibt" "$(cat "$BIN")" "ausgetauscht"
hat "Rueckbau fremd: benannt" "$OUT" "nicht mehr unsere Datei"
# Ein bin/ mit Fremdem darin bleibt.
mkroot rueck3 abc1234; fahr run
printf 'anderer\n' >"$R/opt/chimera/bin/anderes"
rueckbau
check "Rueckbau: Binary weg, bin/ mit Fremdem bleibt" "$([ -e "$BIN" ] && echo da || echo weg)/$([ -e "$R/opt/chimera/bin/anderes" ] && echo da || echo weg)" "weg/da"
# Ohne Manifest wird nichts geraten.
mkroot rueck4 abc1234; mkdir -p "$R/opt/chimera/bin"; printf 'x\n' >"$BIN"
rueckbau
check "Rueckbau ohne Manifest: rc 0" "$RC" "0"
check "Rueckbau ohne Manifest: Datei bleibt" "$(cat "$BIN")" "x"

# --- 11. Commit aus Schritt 00 -----------------------------------------------------------------
printf '\n=== Commit der Quelle (Modul 00) ===\n'
. "$HERE/lib/common.sh" >/dev/null 2>&1
. "$SRCLIB"
G="$W/git"; mkdir -p "$G/rust"
( cd "$G" && git init -q . && git config user.email test@users.noreply.github.com && git config user.name t \
	&& printf '0.1.0-pre\n' >VERSION && printf 'x\n' >rust/a && git add -A && git commit -qm eins )
_HEAD="$(git -C "$G" rev-parse --short=7 HEAD)"
check "sauberer Klon: Commit gelesen" "$(source_commit_lesen "$G")" "$_HEAD"
QF="$W/state/quelle-commit"
check "festhalten: gibt den Commit aus" "$(source_commit_festhalten "$G" "$QF")" "$_HEAD"
check "festhalten: Datei hat ihn" "$(cat "$QF")" "$_HEAD"
check "festhalten: keine Nebendatei" "$([ -e "$QF.neu" ] && echo da || echo weg)" "weg"
printf 'y\n' >>"$G/rust/a"
check "rust/ geaendert: kein Commit" "$(source_commit_lesen "$G")" ""
source_commit_festhalten "$G" "$QF" >/dev/null
check "rust/ geaendert: alte Datei entfernt" "$([ -e "$QF" ] && echo da || echo weg)" "weg"
( cd "$G" && git checkout -q -- rust/a && printf 'z\n' >neben.txt )
check "Aenderung ausserhalb rust/ und VERSION: Commit bleibt" "$(source_commit_lesen "$G")" "$_HEAD"
printf '0.2.0\n' >"$G/VERSION"
check "VERSION geaendert: kein Commit" "$(source_commit_lesen "$G")" ""
( cd "$G" && git checkout -q -- VERSION )
mkdir -p "$W/zip/rust"; printf '0.1.0-pre\n' >"$W/zip/VERSION"
check "ohne .git (Zip): kein Commit" "$(source_commit_lesen "$W/zip")" ""
check "ohne .git: nichts geschrieben" "$(source_commit_festhalten "$W/zip" "$W/s2/quelle-commit")" ""
check "ohne .git: Datei nicht angelegt" "$([ -e "$W/s2/quelle-commit" ] && echo da || echo weg)" "weg"
# Ein Baum OHNE eigenes .git, der in einem fremden Repo liegt (Zip in einem
# Klon entpackt): git findet das Eltern-Repo und meldete dessen Commit --
# der gehoert nicht zu diesem Baum.
mkdir -p "$G/sub/rust"; printf '0.1.0-pre\n' >"$G/sub/VERSION"; printf 'q\n' >"$G/sub/rust/q"
( cd "$G" && git add -A && git commit -qm zwei )
check "Baum im fremden Repo, ohne eigenes .git: kein Commit" "$(source_commit_lesen "$G/sub")" ""

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
