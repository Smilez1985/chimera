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
#   9. Ein unveraenderter rust/-Baum verlangt kein neues Binary: das
#      vorhandene bleibt (rc 0, "Rust unveraendert seit <commit>"), ohne Netz
#      und ohne Befund. Gemessen wird der Baum, nicht der Commit; eine neue
#      VERSION hebt das Stillhalten auf.
#  10. Schritt 00: source_commit_festhalten schreibt den Commit eines
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

# Ein eigener rust/-Baum je Fall: er entscheidet, ob das Binary stillhaelt.
# Der echte Baum des Repos waere kein Pruefmittel -- er aendert sich mit jedem
# Rust-Commit und ist fuer alle Faelle derselbe.
baum_aendern() { printf '%s\n' "$1" >>"$R/rust/Baum.txt"; }

mkroot() { # $1 Name, $2 Commit der Quelle (leer = keiner)
	R="$W/$1"
	mkdir -p "$R/opt/chimera/state" "$R/logs" "$R/rust"
	printf 'a\n' >"$R/rust/Baum.txt"
	MANIFEST="$R/opt/chimera/state/manifest.tsv"
	[ -z "${2:-}" ] || printf '%s\n' "$2" >"$R/opt/chimera/state/quelle-commit"
	BIN="$R/opt/chimera/bin/chimera-tor"
}

fahr() { # $1 Modus; Variablen per env davor
	set +e
	OUT="$(env CHIMERA_ROOT="$R" CHIMERA_MANIFEST="$MANIFEST" CHIMERA_LOG_DIR="$R/logs" \
	           CHIMERA_MODE="$1" CHIMERA_RUST_URL="${RUST_URL:-$URLBASIS}" \
	           CHIMERA_RUST_BAUM="$R/rust" \
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
baum_aendern "rust geaendert"
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
hat "zweiter Lauf: sagt es" "$OUT" "Rust unveraendert seit"
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
baum_aendern "neuer rust-stand"
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

# --- 8b. Lokale Datei (CHIMERA_RUST_LOKAL) ----------------------------------------------
# Selbst gebautes Binary, ohne Netz und ohne Commit. Die Proben bleiben dieselben.
binary_bauen "$W/lokal-gut" "$VERSION_SOLL"
mkroot lokal ""
CHIMERA_RUST_LOKAL="$W/lokal-gut" fahr run
check "lokal: rc 0 auch ohne Commit" "$RC" "0"
check "lokal: Binary liegt da" "$([ -x "$BIN" ] && echo ja || echo nein)" "ja"
check "lokal: Inhalt = Datei" "$(summe "$BIN")" "$(summe "$W/lokal-gut")"
hat "lokal: Manifest Summe" "$(cat "$MANIFEST")" "$(summe "$BIN")"
hat "lokal: sagt, woher" "$OUT" "lokale Datei"
_z="$(wc -l <"$MANIFEST")"; _m="$(stat -c %Y "$BIN")"; sleep 1
CHIMERA_RUST_LOKAL="$W/lokal-gut" fahr run
check "lokal: zweiter Lauf rc 0" "$RC" "0"
hat "lokal: zweiter Lauf erkennt es" "$OUT" "Rust unveraendert seit lokal"
check "lokal: Manifest waechst nicht" "$(wc -l <"$MANIFEST")" "$_z"
check "lokal: nicht neu geschrieben" "$(stat -c %Y "$BIN")" "$_m"

binary_bauen "$W/lokal-alt" "9.9.9"
mkroot lokal-v ""
CHIMERA_RUST_LOKAL="$W/lokal-alt" fahr run
check "lokal falsche Version: rc 2" "$RC" "2"
check "lokal falsche Version: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
printf 'kein programm\n' >"$W/lokal-tot"; chmod 755 "$W/lokal-tot"
mkroot lokal-t ""
CHIMERA_RUST_LOKAL="$W/lokal-tot" fahr run
check "lokal laeuft nicht: rc 2" "$RC" "2"
check "lokal laeuft nicht: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
mkroot lokal-f ""
CHIMERA_RUST_LOKAL="$W/gibt-es-nicht" fahr run
check "lokal fehlt: rc 2" "$RC" "2"
: >"$W/lokal-leer"
CHIMERA_RUST_LOKAL="$W/lokal-leer" fahr run
check "lokal leer: rc 2" "$RC" "2"
mkroot lokal-a ""
ARCH=armv7l CHIMERA_RUST_LOKAL="$W/lokal-gut" fahr run
check "lokal auf armv7l: rc 1" "$RC" "1"

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

# --- 12. Unveraenderter rust/-Baum: kein neues Binary, kein Befund -------------
# Das Binary haengt am Inhalt von rust/. Ein Doku-Commit laesst ihn stehen --
# dann darf weder geladen noch gemeckert werden. Gemessen wird der Baum, nicht
# der Commit.
printf '\n=== Unveraenderter rust/-Baum ===\n'
spiegel 3330003 "$VERSION_SOLL"
mkroot baumgleich 3330003
fahr run
check "baumgleich: erster Lauf rc 0" "$RC" "0"
check "baumgleich: Zustand geschrieben" "$(cat "$R/opt/chimera/state/rust-stand" 2>/dev/null | wc -l)" "1"
hat "baumgleich: Zustand nennt den Commit" "$(cat "$R/opt/chimera/state/rust-stand")" "3330003"
_sum="$(summe "$BIN")"; _z="$(wc -l <"$MANIFEST")"
# Neuer Commit (Doku), gleicher Baum, KEIN Prerelease dazu -- und kein Netz.
printf '4440004\n' >"$R/opt/chimera/state/quelle-commit"
RUST_URL="http://127.0.0.1:1" fahr run
check "baumgleich: ohne Prerelease rc 0 (kein Befund)" "$RC" "0"
hat "baumgleich: sagt es" "$OUT" "Rust unveraendert seit 3330003"
check "baumgleich: Binary unberuehrt" "$(summe "$BIN")" "$_sum"
check "baumgleich: Manifest nicht gewachsen" "$(wc -l <"$MANIFEST")" "$_z"
check "baumgleich: Commit bleibt der des Binaries" "$(cut -d' ' -f1 "$R/opt/chimera/state/rust-stand")" "3330003"

# Ein ausgetauschtes Binary wird NICHT als "unveraendert" durchgewinkt: die
# Pruefsumme im Manifest entscheidet, danach wird nachgeladen.
printf '#!/bin/sh\necho "chimera-tor %s"\n' "$VERSION_SOLL" >"$BIN"
( cd "$R/opt/chimera/bin" && printf 'fremd\n' >>chimera-tor )
fahr run
check "baumgleich, Binary veraendert: rc 0 (nachgeladen)" "$RC" "0"
check "baumgleich, Binary veraendert: wieder das Richtige" "$(summe "$BIN")" "$_sum"

# Ein geaenderter Baum verlangt ein neues Binary -- gibt es keins zum neuen
# Commit, ist das ein Befund (das alte Binary bleibt liegen).
printf '5550005\n' >"$R/opt/chimera/state/quelle-commit"
baum_aendern "neue Zeile in rust/"
fahr run
check "baum geaendert, kein Prerelease: rc 1" "$RC" "1"
hat "baum geaendert: benannt" "$OUT" "rust-5550005"
check "baum geaendert: altes Binary bleibt" "$(summe "$BIN")" "$_sum"

# Eine neue VERSION im Zustand hebt das Stillhalten auf: die Version steht im
# Binary, ein Doku-Commit mit Versionssprung braucht also ein neues.
mkroot baumver 3330003
fahr run
_alt_hash="$(cut -d' ' -f2 "$R/opt/chimera/state/rust-stand")"
printf '3330003 %s 0.0.0-frueher\n' "$_alt_hash" >"$R/opt/chimera/state/rust-stand"
RUST_URL="http://127.0.0.1:1" fahr run
check "andere Version im Zustand: kein Stillhalten (Befund ohne Netz)" "$RC" "1"

# Fehlt das Binary, wird der Stand aus dem Zustand geholt -- nicht der neue
# Commit, zu dem es kein Prerelease gibt.
mkroot baumfehlt 3330003
fahr run
rm -f "$BIN"
printf '6660006\n' >"$R/opt/chimera/state/quelle-commit"
fahr run
check "Binary fehlt, Baum gleich: rc 0" "$RC" "0"
hat "Binary fehlt: laedt den Stand des Zustands" "$OUT" "rust-3330003"
check "Binary fehlt: wieder da" "$([ -x "$BIN" ] && echo ja || echo nein)" "ja"

# Ein Binary, das nicht mehr laeuft, gilt nicht als unveraendert -- auch wenn
# Manifest und Pruefsumme dazu passen (jemand hat beides nachgezogen).
mkroot baumtot 3330003
fahr run
printf 'kaputt\n' >"$BIN"
_sum_t="$(summe "$BIN")"
awk -F'\t' -v p="$BIN" -v s="$_sum_t" 'BEGIN{OFS="\t"} { if ($3 == "datei" && $4 == p) $5 = s; print }' \
	"$MANIFEST" >"$MANIFEST.neu" && mv "$MANIFEST.neu" "$MANIFEST"
RUST_URL="http://127.0.0.1:1" fahr run
check "baumgleich, Binary laeuft nicht: kein Stillhalten" "$RC" "1"

# Ohne Zustand wird nicht behauptet, der Baum sei gleich: der normale Weg
# prueft die Pruefsumme und findet das Binary passend ("schon vorhanden").
mkroot schon 3330003
fahr run
_sum_s="$(summe "$BIN")"; _z_s="$(wc -l <"$MANIFEST")"; _m_s="$(stat -c %Y "$BIN")"
rm -f "$R/opt/chimera/state/rust-stand"
sleep 1
fahr run
check "ohne Zustand, Binary passend: rc 0" "$RC" "0"
hat "ohne Zustand, Binary passend: sagt es" "$OUT" "Schon vorhanden und geprueft"
check "ohne Zustand, Binary passend: nicht neu geschrieben" "$(stat -c %Y "$BIN")" "$_m_s"
check "ohne Zustand, Binary passend: Manifest nicht gewachsen" "$(wc -l <"$MANIFEST")" "$_z_s"
check "ohne Zustand, Binary passend: Zustand wieder da" "$([ -s "$R/opt/chimera/state/rust-stand" ] && echo ja || echo nein)" "ja"

# Trockenlauf mit unveraendertem Baum: er kuendigt das Behalten an und legt
# nichts an (auch keinen Zustand).
mkroot trockenbaum 3330003
fahr run
_st_vor="$(summe "$R/opt/chimera/state/rust-stand")"
printf '7770007\n' >"$R/opt/chimera/state/quelle-commit"
RUST_URL="http://127.0.0.1:1" fahr dry
check "Trockenlauf, Baum gleich: rc 0" "$RC" "0"
hat "Trockenlauf, Baum gleich: kuendigt Behalten an" "$OUT" "wuerde behalten"
check "Trockenlauf, Baum gleich: Zustand unberuehrt" "$(summe "$R/opt/chimera/state/rust-stand")" "$_st_vor"

# Ohne Zustand wird nicht behauptet, der Baum sei gleich: normaler Weg.
mkroot baumleer 3330003
rm -f "$R/opt/chimera/state/rust-stand"
fahr run
check "ohne Zustand: rc 0" "$RC" "0"
hat "ohne Zustand: laedt (kein Kurzweg)" "$OUT" "Abgelegt:"
check "ohne Zustand: Zustand danach da" "$([ -s "$R/opt/chimera/state/rust-stand" ] && echo ja || echo nein)" "ja"

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
