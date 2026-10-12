#!/bin/sh
# Tests fuer source_hash (lib/source.sh): ein sha256sum-Aufruf fuer alle
# Dateien statt Prozesse je Datei -- bei GLEICHER Summe wie bis 0.1.0-pre.
#
# Warum die Summe gleich bleiben muss: Schritt 00 vergleicht den Startbaum
# mit source/, Schritt 50 source/ mit productive/code. Aenderte sich die
# Rechenart, waeren beide Seiten zwar wieder gleich -- aber nur, weil beide
# neu gerechnet werden. Ein Festwert haelt fest, was die alte Fassung fuer
# einen bekannten Baum lieferte. Er stammt aus der Fassung von c91917b,
# gemessen unter sh/dash/busybox sh mit GNU- und BusyBox-Werkzeugen.
#
# Gegen den Festwert laeuft der Baum zweimal: mit den Werkzeugen der
# Umgebung und mit BusyBox-Applets (wo BusyBox da ist). GNU sha256sum
# maskiert Namen mit Backslash oder Wagenruecklauf, BusyBox nicht -- die
# Summe darf davon nicht abhaengen.
#
# CHIMERA_SOURCE_LIB  ueberstimmt die Bibliothek (Gegenprobe)
# CHIMERA_SOURCE_STEP ueberstimmt Schritt 00 (Gegenprobe)
# CHIMERA_PYTHON_STEP ueberstimmt Schritt 50 (Gegenprobe)

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="${CHIMERA_SOURCE_LIB:-$HERE/lib/source.sh}"
STEP00="${CHIMERA_SOURCE_STEP:-$HERE/steps/00-source.sh}"
STEP50="${CHIMERA_PYTHON_STEP:-$HERE/steps/50-python.sh}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-hash.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap '[ -n "${KEEP:-}" ] || { chmod -R u+rwX "$W" 2>/dev/null; rm -rf "$W"; }' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"
	else bad "$1 -- erwartet '$3', bekam '$2'"; fi
}

bib() {   # Bibliothek in einer Unterschale; Ausgabe stdout, rc durchgereicht
	( set +e; CHIMERA_ROOT=""; . "$HERE/lib/common.sh"; . "$HERE/lib/network.sh"
	  . "$LIB"; "$@" )
}

CR="$(printf '\r')"
NL='
'

printf '=== Pruefsumme (source_hash) ===\n'

# --- 1. Festwert der alten Fassung ----------------------------------------
# Gewoehnlicher Name, Leerzeichen im Verzeichnis, Backslash in Datei und
# Verzeichnis, Wagenruecklauf.
FEST=531db39c03be5f9fe1f6d7905b9879421cc128a29be5dba7884f8fb11a8dbc7f
K="$W/fest"
mkdir -p "$K/sub dir" "$K/d\\ir"
printf '1' >"$K/a"
printf '2' >"$K/sub dir/b"
printf '3' >"$K/back\\slash"
printf '4' >"$K/cr${CR}name"
printf '5' >"$K/d\\ir/f"

check "Festwert (Werkzeuge der Umgebung)" "$(bib source_hash "$K")" "$FEST"

if command -v busybox >/dev/null 2>&1; then
	BB="$W/bb"; mkdir -p "$BB"
	for _c in sha256sum find sort wc grep cut; do
		printf '#!/bin/sh\nexec busybox %s "$@"\n' "$_c" >"$BB/$_c"
		chmod +x "$BB/$_c"
	done
	check "Festwert (BusyBox-Werkzeuge)" "$(PATH="$BB:$PATH" bib source_hash "$K")" "$FEST"
else
	printf '  --    BusyBox fehlt: Festwert nur mit den Werkzeugen der Umgebung\n'
fi

# --- 2. Ein Aufruf fuer alle Dateien --------------------------------------
# Eine Attrappe vor sha256sum zaehlt die Aufrufe. 40 gewoehnliche Dateien
# duerfen nicht 40 Aufrufe kosten. Grenze 3: find darf sehr lange Listen
# aufteilen, 40 kurze Namen passen aber in einen Aufruf.
#
# Unter BusyBox sh gehen Applets dem PATH vor -- dort sieht die Attrappe
# nichts. Ob sie greift, zeigt erst die Zaehlung selbst: Kommt kein Aufruf
# an, ist die Pruefung hier nicht moeglich und wird benannt, nicht gruen.
V="$W/viele"; mkdir -p "$V"
_i=0; while [ "$_i" -lt 40 ]; do printf '%s' "$_i" >"$V/f$_i"; _i=$((_i + 1)); done
ZB="$W/zaehl"; mkdir -p "$ZB"
_echt_sha="$(command -v sha256sum)"
printf '#!/bin/sh\necho x >>"%s/aufrufe"\nexec %s "$@"\n' "$W" "$_echt_sha" >"$ZB/sha256sum"
chmod +x "$ZB/sha256sum"
: >"$W/aufrufe"
_hv="$(PATH="$ZB:$PATH" bib source_hash "$V")"
_n="$(wc -l <"$W/aufrufe")"
if [ "$_n" -eq 0 ]; then
	printf '  --    Aufrufzaehlung nicht moeglich (Shell nimmt das eingebaute sha256sum)\n'
elif [ "$_n" -le 3 ]; then
	ok "40 Dateien: $((_n)) sha256sum-Aufrufe (hoechstens 3)"
else
	bad "40 Dateien: $((_n)) sha256sum-Aufrufe -- erwartet hoechstens 3"
fi
[ -n "$_hv" ] && ok "40 Dateien: Summe nicht leer" || bad "40 Dateien: Summe leer"

# --- 3. Name mit Zeilenumbruch: benannt abgelehnt -------------------------
# Bis 0.1.0-pre zerfiel so ein Name still in zwei Zeilen; der Inhalt der
# Datei ging nicht in die Summe ein -- eine geaenderte Datei blieb unbemerkt.
Z="$W/umbruch"; mkdir -p "$Z"
printf 'x' >"$Z/normal"
printf 'y' >"$Z/zwei${NL}zeilen"
set +e
_hz="$(bib source_hash "$Z" 2>"$W/umbruch.err")"; _rc=$?
set -e
check "Zeilenumbruch im Namen: rc 1" "$_rc" 1
check "Zeilenumbruch im Namen: keine Summe" "$_hz" ""
if grep -q 'Zeilenumbruch' "$W/umbruch.err"; then ok "Zeilenumbruch im Namen: benannt"
else bad "Zeilenumbruch im Namen: nicht benannt ($(cat "$W/umbruch.err"))"; fi

# --- 4. Unlesbare Datei: keine Teilsumme ----------------------------------
# Als root ist jede Datei lesbar; dann ist der Fall nicht herstellbar.
U="$W/unlesbar"; mkdir -p "$U"
printf 'a' >"$U/a"; printf 'b' >"$U/b"; chmod 000 "$U/b"
if cat "$U/b" >/dev/null 2>&1; then
	printf '  --    unlesbare Datei nicht herstellbar (laeuft als root)\n'
else
	set +e
	_hu="$(bib source_hash "$U" 2>/dev/null)"; _rc=$?
	set -e
	check "unlesbare Datei: rc 1" "$_rc" 1
	check "unlesbare Datei: keine Summe" "$_hu" ""
fi
chmod 644 "$U/b"

# --- 5. Zeilenpruefung: Anzahl und Format ---------------------------------
_h1="$(printf '%064d' 0)"
_rc=0; bib source_hash_zeilen_ok "$_h1  ./a" 1 2>/dev/null || _rc=$?
check "Zeilen: passend -> rc 0" "$_rc" 0
_rc=0; bib source_hash_zeilen_ok "" 0 2>/dev/null || _rc=$?
check "Zeilen: leerer Baum -> rc 0" "$_rc" 0
_rc=0; bib source_hash_zeilen_ok "$_h1  ./a" 2 2>/dev/null || _rc=$?
check "Zeilen: eine fehlt -> rc 1" "$_rc" 1
_rc=0; bib source_hash_zeilen_ok "\\$_h1  ./a\\\\b" 1 2>/dev/null || _rc=$?
check "Zeilen: maskierte Zeile -> rc 1" "$_rc" 1

# --- 6. Schritte brechen benannt ab, nicht still --------------------------
# set -e haette bei rc 1 von source_hash den Schritt mitten in der
# Zuweisung beendet -- rc 1 = "Befund", ohne Meldung. Erwartet: rc 2 und
# die Meldung "Pruefsumme ... leer".
mkdir -p "$W/bin"
_echt_id="$(command -v id)"
printf '#!/bin/sh
if [ "${1:-}" = -u ] && [ $# -eq 1 ]; then echo 0; else exec %s "$@"; fi
' "$_echt_id" >"$W/bin/id"
chmod +x "$W/bin/id"

baum() {   # $1 Ziel: echtes Layout (installer/, src/, VERSION), nicht pruefbar
	mkdir -p "$1/installer/steps" "$1/src/chimera"
	printf '0.2.0\n' >"$1/VERSION"
	printf 'print(1)\n' >"$1/src/chimera/__main__.py"
	printf 'pillow\n' >"$1/requirements.txt"
	cp -r "$HERE/lib" "$1/installer/lib"
	cp "$LIB" "$1/installer/lib/source.sh"
	printf 'y' >"$1/src/chimera/zwei${NL}zeilen"
}

S0="$W/s0"; baum "$S0"; cp "$STEP00" "$S0/installer/steps/00-source.sh"
R0="$W/r0"; mkdir -p "$R0"
set +e
PATH="$W/bin:$PATH" CHIMERA_ROOT="$R0" CHIMERA_LOG_DIR="$W/logs0" \
CHIMERA_QUELLE_URL="$W/gibt-es-nicht" \
	sh "$S0/installer/steps/00-source.sh" >"$W/s0.aus" 2>&1
_rc=$?
set -e
check "Schritt 00, Startbaum nicht pruefbar: rc 2" "$_rc" 2
if grep -q 'Pruefsumme des Startbaums leer' "$W/s0.aus"; then ok "Schritt 00: benannt"
else bad "Schritt 00: nicht benannt ($(tail -2 "$W/s0.aus" | tr '\n' ' '))"; fi

S5="$W/s5"; baum "$S5"; cp "$STEP50" "$S5/installer/steps/50-python.sh"
R5="$W/r5"; mkdir -p "$R5"
set +e
PATH="$W/bin:$PATH" CHIMERA_ROOT="$R5" CHIMERA_LOG_DIR="$W/logs5" \
	sh "$S5/installer/steps/50-python.sh" >"$W/s5.aus" 2>&1
_rc=$?
set -e
check "Schritt 50, Quelle nicht pruefbar: rc 2" "$_rc" 2
if grep -q 'Pruefsumme von .* leer' "$W/s5.aus"; then ok "Schritt 50: benannt"
else bad "Schritt 50: nicht benannt ($(tail -2 "$W/s5.aus" | tr '\n' ' '))"; fi

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
