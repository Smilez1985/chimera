#!/bin/sh
# Tests fuer Modul 55 (Rust-Binary aus dem Startbaum ablegen).
#
# Geprueft wird, was die Regel zusagt (DESIGN Regel 14): Das Binary liegt im
# Repo (`gateway/`), der Installer holt nichts nach und braucht kein Netz,
# prueft Pruefsumme, Architektur, Laufprobe und Version -- und meldet einen
# neueren rust/-Baum, ohne abzubrechen.
#
# Kein Netz, kein Git, kein Commit: Der Test baut einen Startbaum mit
# installer/, VERSION, rust/ und gateway/ und faehrt den Schritt daraus.
#
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
hat()      { if printf '%s' "$2" | grep -q -- "$3"; then ok "$1"; else bad "$1 -- '$3' fehlt in: $2"; fi; }
hat_nicht() { if printf '%s' "$2" | grep -q -- "$3"; then bad "$1 -- '$3' kam doch vor"; else ok "$1"; fi; }

STEP="${CHIMERA_STEP_55:-$HERE/steps/55-rust.sh}"
RMSTEP="${CHIMERA_STEP_RM55:-$REPO/uninstaller/steps/55-remove-rust.sh}"
VERSION_SOLL="$(tr -d ' \t\r\n' <"$REPO/VERSION")"

printf '=== Rust-Binary (Modul 55) ===\n'

# Ein "Binary", das wie chimera-tor antwortet.
binary_bauen() { # $1 Datei, $2 Version
	printf '#!/bin/sh\n[ "${1:-}" = --version ] && { echo "chimera-tor %s"; exit 0; }\nexit 2\n' "$2" >"$1"
	chmod 755 "$1"
}

# Ein "Binary", das wie chimera-sohelper antwortet.
soh_bauen() { # $1 Datei, $2 Version
	printf '#!/bin/sh\n[ "${1:-}" = --version ] && { echo "chimera-sohelper %s"; exit 0; }\nexit 2\n' "$2" >"$1"
	chmod 755 "$1"
}

# Ein "Binary", das wie chimera-fdpass antwortet (der Deskriptor-Helfer der
# Fernausfuehrung).
fd_bauen() { # $1 Datei, $2 Version
	printf '#!/bin/sh\n[ "${1:-}" = --version ] && { echo "chimera-fdpass %s"; exit 0; }\nexit 2\n' "$2" >"$1"
	chmod 755 "$1"
}

# Das ausgelieferte Ausfuehrer-Binary in den Startbaum legen. Der Schritt legt
# seit 11.11. beide Programme ab (seit 12.11. drei: chimera-fdpass reist mit
# dem Ausfuehrer); fehlt eines, ist das ein Befund (rc 1).
soh_ausliefern() { # $1 Version (leer = VERSION_SOLL)
	mkdir -p "$T/sohelper"
	soh_bauen "$T/sohelper/chimera-sohelper-aarch64" "${1:-$VERSION_SOLL}"
	fd_bauen "$T/sohelper/chimera-fdpass-aarch64" "${1:-$VERSION_SOLL}"
	( cd "$T/sohelper" && sha256sum chimera-sohelper-aarch64 >chimera-sohelper-aarch64.sha256 \
		&& sha256sum chimera-fdpass-aarch64 >chimera-fdpass-aarch64.sha256 )
}

# Startbaum: was der Schritt ausser der Wurzel braucht.
mkbaum() { # $1 Name
	T="$W/$1"
	mkdir -p "$T/installer/steps" "$T/rust" "$T/gateway" "$T/sohelper"
	cp "$STEP" "$T/installer/steps/55-rust.sh"
	cp -r "$HERE/lib" "$T/installer/lib"
	cp "$REPO/VERSION" "$T/VERSION"
	printf 'a\n' >"$T/rust/Baum.txt"
	soh_ausliefern
}

# Wurzel (was der Schritt anlegt) -- getrennt vom Startbaum.
mkroot() { # $1 Name
	R="$W/$1"
	mkdir -p "$R/opt/chimera/state" "$R/logs"
	MANIFEST="$R/opt/chimera/state/manifest.tsv"
	BIN="$R/opt/chimera/bin/chimera-tor"
}

# Das ausgelieferte Binary in den Startbaum legen, mit Pruefsumme und Stand.
# $1 Version im Binary, $2 Inhalt-Zusatz (macht zwei Staende unterscheidbar),
# $3 Stand-Hash (leer = Hash des Testbaums)
ausliefern() {
	: >"$T/gateway/chimera-tor-aarch64"
	binary_bauen "$T/gateway/chimera-tor-aarch64" "${1:-$VERSION_SOLL}"
	printf '# %s\n' "${2:-stand}" >>"$T/gateway/chimera-tor-aarch64"
	( cd "$T/gateway" && sha256sum chimera-tor-aarch64 >chimera-tor-aarch64.sha256 )
	_h="${3:-$(sh -c ". '$T/installer/lib/common.sh'; . '$T/installer/lib/network.sh'; . '$T/installer/lib/source.sh'; rust_baum_hash '$T/rust'")}"
	printf 'abc1234 %s %s\n' "$_h" "${1:-$VERSION_SOLL}" >"$T/gateway/chimera-tor-aarch64.stand"
}

fahr() { # $1 Modus; Variablen per env davor
	set +e
	OUT="$(env CHIMERA_ROOT="$R" CHIMERA_MANIFEST="$MANIFEST" CHIMERA_LOG_DIR="$R/logs" \
	           CHIMERA_MODE="$1" CHIMERA_ARCH="${ARCH:-aarch64}" \
	           sh "$T/installer/steps/55-rust.sh" 2>&1)"
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

# --- 1. Der Weg: ausgeliefertes Binary -> abgelegt ------------------------
mkbaum gut; mkroot gut; ausliefern
fahr run
check "gut: rc 0" "$RC" "0"
check "gut: Binary liegt da" "$([ -x "$BIN" ] && echo ja || echo nein)" "ja"
check "gut: Modus 755" "$(stat -c %a "$BIN" 2>/dev/null)" "755"
check "gut: Inhalt = Startbaum" "$(summe "$BIN")" "$(summe "$T/gateway/chimera-tor-aarch64")"
check "gut: Binary laeuft" "$("$BIN" --version)" "chimera-tor $VERSION_SOLL"
hat "gut: Manifest Datei + Summe" "$(cat "$MANIFEST")" "$(summe "$BIN")"
hat "gut: Manifest Verzeichnis" "$(cat "$MANIFEST")" "verzeich"
hat "gut: nennt die Quelle" "$OUT" "gateway/chimera-tor-aarch64"
check "gut: Stand festgehalten" "$(wc -l <"$R/opt/chimera/state/rust-stand")" "1"
hat "gut: Stand nennt den Commit" "$(cat "$R/opt/chimera/state/rust-stand")" "abc1234"
# Seit 11.11. legt derselbe Schritt auch den Ausfuehrer ab (eigener Ordner
# sohelper/ im Repo). Beide Programme, ein Lauf, eine Pruefung.
SOH="$R/opt/chimera/bin/chimera-sohelper"
check "gut: Ausfuehrer liegt da" "$([ -x "$SOH" ] && echo ja || echo nein)" "ja"
check "gut: Ausfuehrer laeuft" "$("$SOH" --version)" "chimera-sohelper $VERSION_SOLL"
hat "gut: Ausfuehrer im Manifest" "$(cat "$MANIFEST")" "chimera-sohelper"
# Kein Netz: der Schritt darf keine Netzfunktion anfassen. Beleg: er laeuft
# mit einer Probekliste, die nirgends hinfuehrt, und braucht trotzdem nichts.
hat_nicht "gut: nichts Fremdes im Zielverzeichnis" "$(ls "$R/opt/chimera/bin")" "neu"

# --- 1b. Nur der Ausfuehrer fehlt: Befund, das Gateway kommt trotzdem ------
mkbaum ohne_soh; mkroot ohne_soh; ausliefern; rm -rf "$T/sohelper"
fahr run
check "Ausfuehrer fehlt: rc 1 (Befund)" "$RC" "1"
check "Ausfuehrer fehlt: Gateway trotzdem abgelegt" \
	"$([ -x "$R/opt/chimera/bin/chimera-tor" ] && echo ja || echo nein)" "ja"
check "Ausfuehrer fehlt: Ausfuehrer nicht abgelegt" \
	"$([ -e "$R/opt/chimera/bin/chimera-sohelper" ] && echo da || echo weg)" "weg"
hat "Ausfuehrer fehlt: benannt" "$OUT" "sohelper"

# --- 2. Kein Binary im Startbaum ------------------------------------------
mkbaum leer; mkroot leer
fahr run
check "kein Binary: rc 1 (Befund)" "$RC" "1"
check "kein Binary: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
hat "kein Binary: benannt" "$OUT" "Kein Binary im Startbaum"
hat "kein Binary: sagt, wohin es gehoert" "$OUT" "gehoert ins Repo"

# --- 3. Leeres Binary ------------------------------------------------------
mkbaum leerd; mkroot leerd
: >"$T/gateway/chimera-tor-aarch64"
fahr run
check "leeres Binary: rc 2" "$RC" "2"
hat "leeres Binary: benannt" "$OUT" "ist leer"

# --- 4. Pruefsumme fehlt / stimmt nicht ------------------------------------
mkbaum ohnestand; mkroot ohnestand; ausliefern
rm -f "$T/gateway/chimera-tor-aarch64.sha256"
fahr run
check "Pruefsumme fehlt: rc 2" "$RC" "2"
hat "Pruefsumme fehlt: benannt" "$OUT" "Pruefsumme fehlt"

mkbaum falschsumme; mkroot falschsumme; ausliefern
printf 'manipuliert\n' >>"$T/gateway/chimera-tor-aarch64"
fahr run
check "falsche Summe: rc 2" "$RC" "2"
check "falsche Summe: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
hat "falsche Summe: benannt" "$OUT" "stimmt nicht mit seiner Pruefsumme"

# --- 5. Version und Laufprobe ----------------------------------------------
mkbaum version; mkroot version; ausliefern "9.9.9" alt
# Pruefsumme passt (aus der Datei), aber die Version nicht.
fahr run
check "falsche Version: rc 2" "$RC" "2"
check "falsche Version: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
hat "falsche Version: benannt" "$OUT" "statt 'chimera-tor $VERSION_SOLL'"

mkbaum tot; mkroot tot
printf 'kein programm\n' >"$T/gateway/chimera-tor-aarch64"
( cd "$T/gateway" && sha256sum chimera-tor-aarch64 >chimera-tor-aarch64.sha256 )
fahr run
check "Binary laeuft nicht: rc 2" "$RC" "2"
check "Binary laeuft nicht: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"

# --- 6. Architektur --------------------------------------------------------
mkbaum arch; mkroot arch; ausliefern
ARCH=armv7l fahr run
check "armv7l: rc 1 (Befund)" "$RC" "1"
check "armv7l: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
hat "armv7l: benannt" "$OUT" "nur fuer aarch64"

# --- 7. Idempotenz und Ersetzen -------------------------------------------
mkbaum idem; mkroot idem; ausliefern
fahr run
_sum="$(summe "$BIN")"; _z="$(wc -l <"$MANIFEST")"; _m="$(stat -c %Y "$BIN")"
sleep 1
fahr run
check "zweiter Lauf: rc 0" "$RC" "0"
hat "zweiter Lauf: sagt es" "$OUT" "Schon vorhanden und geprueft"
check "zweiter Lauf: Datei unveraendert" "$(summe "$BIN")" "$_sum"
check "zweiter Lauf: nicht neu geschrieben" "$(stat -c %Y "$BIN")" "$_m"
check "zweiter Lauf: Manifest nicht gewachsen" "$(wc -l <"$MANIFEST")" "$_z"

# Neue Fassung im Startbaum -> wird ersetzt, EINE Manifestzeile fuer die Datei.
ausliefern "$VERSION_SOLL" "neu"
fahr run
check "neue Fassung: rc 0" "$RC" "0"
check "neue Fassung: Binary ersetzt" "$(summe "$BIN")" "$(summe "$T/gateway/chimera-tor-aarch64")"
check "neue Fassung: eine Manifestzeile fuer die Datei" \
	"$(grep -c "	datei	/opt/chimera/bin/chimera-tor	" "$MANIFEST")" "1"
hat "neue Fassung: neue Summe im Manifest" "$(cat "$MANIFEST")" "$(summe "$BIN")"

# --- 8. Fremde Datei am Zielort -------------------------------------------
mkbaum fremd; mkroot fremd; ausliefern
mkdir -p "$(dirname "$BIN")"; printf 'gehoert jemand anders\n' >"$BIN"
fahr run
check "fremde Datei: rc 2" "$RC" "2"
check "fremde Datei: Inhalt unveraendert" "$(cat "$BIN")" "gehoert jemand anders"
hat "fremde Datei: benannt" "$OUT" "nicht im Manifest"

# --- 9. Trockenlauf --------------------------------------------------------
mkbaum trocken; mkroot trocken; ausliefern
fahr dry
check "Trockenlauf: rc 0" "$RC" "0"
hat "Trockenlauf: kuendigt an" "$OUT" "wuerde ablegen"
check "Trockenlauf: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
check "Trockenlauf: Manifest unberuehrt" "$([ -e "$MANIFEST" ] && echo da || echo weg)" "weg"
check "Trockenlauf: kein Stand" "$([ -e "$R/opt/chimera/state/rust-stand" ] && echo da || echo weg)" "weg"

# --- 10. Hinweis: rust/ neuer als das Binary (kein Befund) ----------------
printf '\n=== Hinweis auf einen neueren rust/-Baum ===\n'
mkbaum hinweis; mkroot hinweis; ausliefern "$VERSION_SOLL" alt "0000000000000000000000000000000000000000000000000000000000000000"
fahr run
check "rust/ neuer: rc 0 (kein Befund)" "$RC" "0"
hat "rust/ neuer: gemeldet" "$OUT" "rust/ ist neuer als das Binary"
check "rust/ neuer: Binary trotzdem abgelegt" "$([ -x "$BIN" ] && echo ja || echo nein)" "ja"

mkbaum gleich; mkroot gleich; ausliefern
fahr run
check "rust/ gleich: rc 0" "$RC" "0"
hat "rust/ gleich: sagt es" "$OUT" "rust/ seitdem unveraendert"
hat_nicht "rust/ gleich: kein Hinweis" "$OUT" "ist neuer als das Binary"

# --- 11. Lokale Datei (CHIMERA_RUST_LOKAL) -------------------------------
printf '\n=== Lokale Datei (CHIMERA_RUST_LOKAL) ===\n'
binary_bauen "$W/lokal-gut" "$VERSION_SOLL"
mkbaum lokal; mkroot lokal
CHIMERA_RUST_LOKAL="$W/lokal-gut" fahr run
check "lokal: rc 0" "$RC" "0"
check "lokal: Binary liegt da" "$([ -x "$BIN" ] && echo ja || echo nein)" "ja"
check "lokal: Inhalt = Datei" "$(summe "$BIN")" "$(summe "$W/lokal-gut")"
hat "lokal: nennt die Herkunft" "$OUT" "lokale Datei"
check "lokal: kein Stand (keine .stand zu der Datei)" \
	"$([ -e "$R/opt/chimera/state/rust-stand" ] && echo da || echo weg)" "weg"

binary_bauen "$W/lokal-alt" "9.9.9"
mkbaum lokal-v; mkroot lokal-v
CHIMERA_RUST_LOKAL="$W/lokal-alt" fahr run
check "lokal falsche Version: rc 2" "$RC" "2"
check "lokal falsche Version: nichts abgelegt" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
mkbaum lokal-f; mkroot lokal-f
CHIMERA_RUST_LOKAL="$W/gibt-es-nicht" fahr run
check "lokal fehlt: rc 2" "$RC" "2"
ARCH=armv7l CHIMERA_RUST_LOKAL="$W/lokal-gut" fahr run
check "lokal auf armv7l: rc 1" "$RC" "1"

# --- 12. Rueckbau ---------------------------------------------------------
printf '\n=== Rueckbau ===\n'
mkbaum rueck; mkroot rueck; ausliefern; fahr run
rueckbau
check "Rueckbau: rc 0" "$RC" "0"
check "Rueckbau: Binary weg" "$([ -e "$BIN" ] && echo da || echo weg)" "weg"
check "Rueckbau: leeres bin/ weg" "$([ -d "$R/opt/chimera/bin" ] && echo da || echo weg)" "weg"
mkbaum rueck2; mkroot rueck2; ausliefern; fahr run
printf 'ausgetauscht\n' >"$BIN"
rueckbau
check "Rueckbau fremd: rc 1 (Befund)" "$RC" "1"
check "Rueckbau fremd: Datei bleibt" "$(cat "$BIN")" "ausgetauscht"
hat "Rueckbau fremd: benannt" "$OUT" "nicht mehr unsere Datei"
mkbaum rueck3; mkroot rueck3; ausliefern; fahr run
printf 'anderer\n' >"$R/opt/chimera/bin/anderes"
rueckbau
check "Rueckbau: Binary weg, bin/ mit Fremdem bleibt" \
	"$([ -e "$BIN" ] && echo da || echo weg)/$([ -e "$R/opt/chimera/bin/anderes" ] && echo da || echo weg)" "weg/da"
mkbaum rueck4; mkroot rueck4; mkdir -p "$R/opt/chimera/bin"; printf 'x\n' >"$BIN"
rueckbau
check "Rueckbau ohne Manifest: rc 0" "$RC" "0"
check "Rueckbau ohne Manifest: Datei bleibt" "$(cat "$BIN")" "x"

# --- 13. Der Ruf des Werkzeugs -------------------------------------------
# tools/gateway-binary.sh legt ab, was Schritt 55 erwartet: Binary,
# Pruefsumme und Stand -- und beides passt zusammen. Geprueft wird der
# Rundlauf, nicht ein nachgebauter Sollwert.
printf '\n=== Werkzeug: Binary ablegen ===\n'
WT="$W/werkzeug"; mkdir -p "$WT"
cp -r "$REPO/tools" "$WT/tools"
cp -r "$REPO/installer" "$WT/installer"
cp "$REPO/VERSION" "$WT/VERSION"
mkdir -p "$WT/rust"; printf 'a\n' >"$WT/rust/Baum.txt"
binary_bauen "$W/werkzeug-bin" "$VERSION_SOLL"
set +e
OUT="$(env CHIMERA_ROOT="" sh "$WT/tools/gateway-binary.sh" "$W/werkzeug-bin" --commit deadbee 2>&1)"
RC=$?
set -e
check "Werkzeug: rc 0" "$RC" "0"
check "Werkzeug: Binary liegt da" "$([ -x "$WT/gateway/chimera-tor-aarch64" ] && echo ja || echo nein)" "ja"
hat "Werkzeug: Pruefsumme geschrieben" "$(cat "$WT/gateway/chimera-tor-aarch64.sha256")" "$(summe "$WT/gateway/chimera-tor-aarch64")"
hat "Werkzeug: Stand nennt den Commit" "$(cat "$WT/gateway/chimera-tor-aarch64.stand")" "deadbee"

# Dasselbe Werkzeug, andere Art: der Ausfuehrer landet in sohelper/.
# Die Attrappe nennt den Programmnamen aus dem Namen, nicht fest "chimera-tor"
# (ein Binary, das sich falsch vorstellt, muss abgelehnt werden).
soh_bauen() { # $1 Datei, $2 Version
	printf '#!/bin/sh\n[ "${1:-}" = --version ] && { echo "chimera-sohelper %s"; exit 0; }\nexit 2\n' "$2" >"$1"
	chmod 755 "$1"
}
soh_bauen "$W/werkzeug-soh" "$VERSION_SOLL"
set +e
OUT="$(env CHIMERA_ROOT="" sh "$WT/tools/binary-ablegen.sh" "$W/werkzeug-soh" --art sohelper --commit deadbee 2>&1)"
RC=$?
set -e
check "Werkzeug --art sohelper: rc 0" "$RC" "0"
check "Werkzeug --art sohelper: Binary liegt da" \
	"$([ -x "$WT/sohelper/chimera-sohelper-aarch64" ] && echo ja || echo nein)" "ja"
hat "Werkzeug --art sohelper: Stand nennt den Commit" \
	"$(cat "$WT/sohelper/chimera-sohelper-aarch64.stand")" "deadbee"

# Gegenprobe: ein Gateway-Binary unter --art sohelper wird abgelehnt, und die
# abgelegte Datei bleibt unangetastet (sonst waere "abgelehnt" nur ein Wort).
SUMME_VOR="$(summe "$WT/sohelper/chimera-sohelper-aarch64")"
STAND_VOR="$(cat "$WT/sohelper/chimera-sohelper-aarch64.stand")"
set +e
OUT="$(env CHIMERA_ROOT="" sh "$WT/tools/binary-ablegen.sh" "$W/werkzeug-bin" --art sohelper --commit cafebee 2>&1)"
RC=$?
set -e
check "Gegenprobe: falsches Programm -> rc 1" "$RC" "1"
check "Gegenprobe: Datei unveraendert" "$(summe "$WT/sohelper/chimera-sohelper-aarch64")" "$SUMME_VOR"
check "Gegenprobe: Stand unveraendert" "$(cat "$WT/sohelper/chimera-sohelper-aarch64.stand")" "$STAND_VOR"

# Zweiter Aufruf unter einem ANDEREN Modul (so macht es 99-sohelper): das
# Binary ist da und steht im Manifest unter 55-rust. Es darf nicht als
# Fremdkoerper gelten -- sonst bricht der Lauf auf dem Geraet ab, obwohl
# Schritt 55 eben genau diese Datei abgelegt hat.
FR="$W/fremd"
mkdir -p "$FR/root/opt/chimera/state" "$FR/root/opt/chimera/bin"
cp "$WT/sohelper/chimera-sohelper-aarch64" "$FR/root/opt/chimera/bin/chimera-sohelper"
printf 'z\t55-rust\tdatei\t/opt/chimera/bin/chimera-sohelper\t%s\n' \
	"$(summe "$FR/root/opt/chimera/bin/chimera-sohelper")" >"$FR/root/opt/chimera/state/manifest.tsv"
_KOPIE_VOR="$(summe "$FR/root/opt/chimera/bin/chimera-sohelper")"
# `set +e`: ohne das bricht `set -e` bei einer Zuweisung ab, deren
# Befehlsersetzung einen Fehlercode liefert -- der Lauf endete dann mitten im
# Test ohne Meldung (in der CI passiert, lokal nicht).
set +e
_LOGV="$(env CHIMERA_ROOT="$FR/root" CHIMERA_MANIFEST="$FR/root/opt/chimera/state/manifest.tsv" \
	CHIMERA_LOG_DIR="$FR/logs" CHIMERA_ARCH=aarch64 sh -c '. "$0/installer/lib/common.sh"; . "$0/installer/lib/network.sh"; . "$0/installer/lib/manifest.sh"; . "$0/installer/lib/source.sh"; . "$0/installer/lib/binary.sh"; BINARY_REPO="$1"; binary_aus_baum sohelper 99-sohelper' "$WT" "$WT" 2>&1)"
_RC2=$?
set -e
check "fremdes Modul: rc 0 (kein Fremdkoerper)" "$_RC2" "0"
hat "fremdes Modul: sagt 'schon vorhanden'" "$_LOGV" "Schon vorhanden und geprueft"
check "fremdes Modul: Datei unveraendert" "$(summe "$FR/root/opt/chimera/bin/chimera-sohelper")" "$_KOPIE_VOR"
check "fremdes Modul: kein zweiter Eintrag" "$(wc -l <"$FR/root/opt/chimera/state/manifest.tsv")" "1"

# ... und Schritt 55 nimmt genau das, ohne dass etwas nachgeholt werden muss.
# Dazu gehoert der Deskriptor-Helfer: Schritt 55 legt drei Programme ab.
fd_bauen "$WT/sohelper/chimera-fdpass-aarch64" "$VERSION_SOLL"
( cd "$WT/sohelper" && sha256sum chimera-fdpass-aarch64 >chimera-fdpass-aarch64.sha256 )
mkroot werkzeug; T="$WT"
fahr run
check "Werkzeug -> Schritt 55: rc 0" "$RC" "0"
check "Werkzeug -> Schritt 55: abgelegt" "$(summe "$BIN")" "$(summe "$WT/gateway/chimera-tor-aarch64")"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
