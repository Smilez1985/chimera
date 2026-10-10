#!/bin/sh
# Tests fuer den Protokollweg: erst Arbeitsspeicher, dann gesammelt auf den
# Datentraeger (DESIGN Regel 10r).
#
# Geprueft wird die echte common.sh (Regel 9). Die "Karte" ist ein
# Verzeichnis; dass waehrend des Laufs NICHT dorthin geschrieben wird, ist
# die eigentliche Zusage -- sie wird mitten im Lauf gemessen, nicht am Ende.
#
# Gegenprobe: CHIMERA_COMMON_LIB zeigt auf eine verfaelschte Fassung
# (counter-check-log-sync.sh).

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
LIB="${CHIMERA_COMMON_LIB:-$HERE/lib/common.sh}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-logsync.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"
	else bad "$1 -- erwartet '$3', bekam '$2'"; fi
}

printf '=== Protokoll: RAM, dann Datentraeger ===\n'

# Ein Lauf mit Vorgabepfaden (nur CHIMERA_ROOT gesetzt). Er schreibt drei
# Zeilen, misst dazwischen die Karte, schliesst ab.
R="$W/root"
mkdir -p "$R"
(
	CHIMERA_ROOT="$R"; export CHIMERA_ROOT
	unset CHIMERA_LOG_DIR CHIMERA_LOG_ZIEL CHIMERA_LOGFILE 2>/dev/null || true
	. "$LIB"
	log_open probe >/dev/null
	printf '%s\n' "$CHIMERA_LOG_DIR" >"$W/ram-dir"
	printf '%s\n' "$CHIMERA_LOG_ZIEL" >"$W/ziel-dir"
	log "eins" >/dev/null; info "zwei" >/dev/null
	ls "$CHIMERA_LOG_ZIEL" 2>/dev/null | wc -l | tr -d ' ' >"$W/karte-waehrend"
	log_close 0 >"$W/close-aus" 2>&1
)
RAM="$(cat "$W/ram-dir")"; ZIEL="$(cat "$W/ziel-dir")"

check "RAM-Ordner liegt unter /run" "${RAM#"$R"}" "/run/chimera/logs/installer"
check "Ziel liegt unter /opt/chimera/logs/installer" "${ZIEL#"$R"}" "/opt/chimera/logs/installer"
check "waehrend des Laufs nichts auf der Karte" "$(cat "$W/karte-waehrend")" "0"

_n="$(ls "$ZIEL"/probe-*.log 2>/dev/null | wc -l | tr -d ' ')"
check "nach log_close genau ein Protokoll auf der Karte" "$_n" "1"
_ram="$(ls "$RAM"/probe-*.log 2>/dev/null | head -1)"
_k="$(ls "$ZIEL"/probe-*.log 2>/dev/null | head -1)"
if [ -n "$_ram" ] && [ -n "$_k" ] && cmp -s "$_ram" "$_k"; then
	ok "Kopie gleich dem RAM-Protokoll (inkl. Bilanz)"
else bad "Kopie weicht vom RAM-Protokoll ab"; fi
if grep -q 'Ergebnis: Erfolg' "$_k" 2>/dev/null; then ok "Bilanzzeile auf der Karte"
else bad "Bilanzzeile fehlt auf der Karte"; fi
if grep -q "Protokoll: $ZIEL/" "$W/close-aus"; then ok "Meldung nennt den Kartenpfad"
else bad "Meldung nennt nicht den Kartenpfad: $(cat "$W/close-aus")"; fi
if ls "$ZIEL"/*.neu.* >/dev/null 2>&1; then bad "Sidecar-Datei liegen geblieben"
else ok "keine Sidecar-Reste"; fi

# Zweiter Abgleich ohne Aenderung schreibt nicht (mtime bleibt).
_m1="$(stat -c %Y "$_k")"
sleep 1
(
	CHIMERA_ROOT="$R"; export CHIMERA_ROOT
	CHIMERA_LOG_DIR="$RAM"; CHIMERA_LOG_ZIEL="$ZIEL"
	. "$LIB"
	log_sync
)
check "unveraendertes Protokoll wird nicht neu geschrieben" "$(stat -c %Y "$_k")" "$_m1"

# Ein Schritt unter dem Laeufer (CHIMERA_LOGFILE geerbt) gleicht NICHT ab.
R2="$W/root2"; mkdir -p "$R2/ram" "$R2/karte"
: >"$R2/ram/lauf-1.log"
(
	CHIMERA_ROOT="$R2"; CHIMERA_LOG_DIR="$R2/ram"; CHIMERA_LOG_ZIEL="$R2/karte"
	CHIMERA_LOGFILE="$R2/ram/lauf-1.log"
	. "$LIB"
	log "aus dem Schritt" >/dev/null
	log_close 0 >/dev/null 2>&1
)
check "Schritt mit geerbtem Protokoll schreibt nicht auf die Karte" \
	"$(ls "$R2/karte" | wc -l | tr -d ' ')" "0"

# Ziel nicht anlegbar -> Befund, nicht stiller Erfolg.
R3="$W/root3"; mkdir -p "$R3/ram"; : >"$R3/karte-ist-datei"
printf 'x\n' >"$R3/ram/a.log"
_rc=0
(
	CHIMERA_ROOT="$R3"; CHIMERA_LOG_DIR="$R3/ram"; CHIMERA_LOG_ZIEL="$R3/karte-ist-datei/sub"
	. "$LIB"
	log_sync
) || _rc=$?
check "Ziel nicht anlegbar: log_sync rc 1" "$_rc" "1"

# Kopie kommt nicht am Zielpfad an (dort steht ein Verzeichnis gleichen
# Namens; mv schiebt hinein und meldet Erfolg) -> Befund.
R4="$W/root4"; mkdir -p "$R4/ram" "$R4/karte/a.log"
printf 'x\n' >"$R4/ram/a.log"
_rc=0
(
	CHIMERA_ROOT="$R4"; CHIMERA_LOG_DIR="$R4/ram"; CHIMERA_LOG_ZIEL="$R4/karte"
	. "$LIB"
	log_sync
) || _rc=$?
check "unbeschreibbares Ziel: log_sync rc 1" "$_rc" "1"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
