#!/bin/sh
# Tests fuer Schritt 00 -- lokale SSOT-Kopie (DESIGN Regel 10r).
#
# Geprueft wird die echte Bibliothek und der echte Schritt (Regel 9), in
# einer erfundenen Wurzel. Der veroeffentlichte Stand kommt aus einem
# LOKALEN Testrepo mit Tags -- das echte Repo hat noch keinen, und ein
# Test darf nicht vom Netz abhaengen.
#
# `id -u` meldet im Schrittlauf 0 (Attrappe im PATH), damit der Test auch
# als normaler Nutzer laeuft.
#
# CHIMERA_SOURCE_LIB ueberstimmt die Bibliothek (Gegenprobe).

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
LIB="${CHIMERA_SOURCE_LIB:-$HERE/lib/source.sh}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-source.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap '[ -n "${KEEP:-}" ] || rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"
	else bad "$1 -- erwartet '$3', bekam '$2'"; fi
}

bib() {   # Bibliothek in einer Unterschale benutzen
	( set +e; CHIMERA_ROOT=""; . "$HERE/lib/common.sh"; . "$HERE/lib/network.sh"
	  . "$LIB"; "$@" )
}

printf '=== Quelle (Schritt 00) ===\n'

# --- 1. Entscheidung: Hash wiegt schwerer als Version ---------------------
check "fehlt -> anlegen"                 "$(bib source_entscheiden h1 '' 0.2.0 '' false)" anlegen
check "gleicher Hash -> nichts"          "$(bib source_entscheiden h1 h1 0.2.0 0.2.0 false)" gleich
check "gleicher Hash, andere VERSION -> nichts" "$(bib source_entscheiden h1 h1 0.3.0 0.2.0 false)" gleich
check "anderer Hash, hoehere VERSION -> ersetzen" "$(bib source_entscheiden h2 h1 0.3.0 0.2.0 false)" ersetzen
check "anderer Hash, gleiche VERSION -> ersetzen" "$(bib source_entscheiden h2 h1 0.2.0 0.2.0 false)" ersetzen_gleiche_version
check "aeltere VERSION -> abgelehnt"     "$(bib source_entscheiden h2 h1 0.1.0 0.2.0 false)" abgelehnt
check "aeltere VERSION + --downgrade=true" "$(bib source_entscheiden h2 h1 0.1.0 0.2.0 true)" downgrade

# --- 2. Versionsvergleich -------------------------------------------------
check "0.10.0 > 0.9.1"          "$(bib version_cmp 0.10.0 0.9.1)" gt
check "0.1.0-pre < 0.1.0"       "$(bib version_cmp 0.1.0-pre 0.1.0)" lt
check "0.1.0 > 0.1.0-pre"       "$(bib version_cmp 0.1.0 0.1.0-pre)" gt
check "gleich"                  "$(bib version_cmp 1.2.3 1.2.3)" eq

# --- 3. Hash: Inhalt, nicht Ort und nicht .git ----------------------------
baum() {   # $1 Pfad, $2 VERSION
	mkdir -p "$1/installer/steps" "$1/src/chimera"
	printf '%s\n' "$2" >"$1/VERSION"
	printf 'print(1)\n' >"$1/src/chimera/__main__.py"
	cp "$HERE/chimera-install" "$1/installer/chimera-install"
	cp -r "$HERE/lib" "$1/installer/lib"
	# Die Bibliothek unter Test (Gegenprobe) -- vor jeder Hashmessung.
	cp "$LIB" "$1/installer/lib/source.sh"
	cp "$HERE/steps/00-source.sh" "$1/installer/steps/00-source.sh"
	# Ein Ersatzschritt, damit der Neustart sichtbar wird.
	printf '#!/bin/sh\necho "ZWEITER SCHRITT AUS $(cd "$(dirname "$0")/../.." && pwd)" >>"$SPUR"\nexit 0\n' \
		>"$1/installer/steps/10-spur.sh"
}
baum "$W/a" 0.2.0
cp -r "$W/a" "$W/b"
mkdir -p "$W/b/.git"; printf 'x\n' >"$W/b/.git/HEAD"
mkdir -p "$W/b/src/chimera/__pycache__"; printf 'x' >"$W/b/src/chimera/__pycache__/m.pyc"
_ha="$(bib source_hash "$W/a")"; _hb="$(bib source_hash "$W/b")"
[ -n "$_ha" ] && ok "Hash nicht leer" || bad "Hash leer"
check "anderer Ort, .git, Bytecode -> gleicher Hash" "$_hb" "$_ha"
printf 'print(2)\n' >"$W/b/src/chimera/__main__.py"
_hb="$(bib source_hash "$W/b")"
[ "$_hb" != "$_ha" ] && ok "geaenderte Datei -> anderer Hash" || bad "geaenderte Datei, gleicher Hash"
mv "$W/b/src/chimera/__main__.py" "$W/b/src/chimera/haupt.py"
printf 'print(1)\n' >"$W/b/src/chimera/haupt.py"
_hb="$(bib source_hash "$W/b")"
[ "$_hb" != "$_ha" ] && ok "umbenannte Datei -> anderer Hash" || bad "umbenannte Datei, gleicher Hash"

# --- 4. Ganzer Lauf ueber den Laeufer --------------------------------------
# $1 Startbaum, weitere Argumente an chimera-install. Ausgabe/rc nach $W.
R="$W/root"; mkdir -p "$R"
# `id -u` meldet 0: Der Schritt verlangt root, der Test soll auch als
# normaler Nutzer laufen. Als Datei im PATH, weil die Schritte eigene
# Prozesse sind (Funktionen erben sie nicht). Andere Aufrufe gehen an das
# echte id.
mkdir -p "$W/bin"
_echt_id="$(command -v id)"
printf '#!/bin/sh
if [ "${1:-}" = -u ] && [ $# -eq 1 ]; then echo 0; else exec %s "$@"; fi
' \
	"$_echt_id" >"$W/bin/id"
chmod +x "$W/bin/id"
SPUR="$W/spur"; export SPUR
installer() {
	_st="$1"; shift
	: >"$SPUR"
	set +e
	PATH="$W/bin:$PATH" CHIMERA_ROOT="$R" CHIMERA_LOG_DIR="$W/logs" \
	CHIMERA_QUELLE_URL="$QUELLE" \
		sh "$_st/installer/chimera-install" "$@" >"$W/aus" 2>&1
	echo $? >"$W/rc"
	set -e
}

QUELLE="$W/gibt-es-nicht"     # offline: nicht nachsehbar
SRC="$R/opt/chimera/source"

installer "$W/a"
check "Erstlauf rc 0" "$(cat "$W/rc")" 0
[ -d "$SRC" ] && ok "source/ angelegt" || bad "source/ fehlt"
check "source/ = Startbaum (Hash)" "$(bib source_hash "$SRC")" "$_ha"
if grep -q 'nicht nachsehbar' "$W/aus"; then ok "offline benannt"; else bad "offline nicht benannt"; fi
if grep -q "ZWEITER SCHRITT AUS $SRC" "$SPUR"; then ok "Folgeschritt lief aus source/ (Neustart)"
else bad "Folgeschritt lief nicht aus source/: $(cat "$SPUR")"; fi
[ -d "$SRC/.git" ] && bad ".git mitkopiert" || ok ".git nicht mitkopiert"

# Zweiter Lauf, gleicher Stand: nichts zu tun, kein Neustart, source/ unberuehrt.
_m1="$(stat -c %Y "$SRC/VERSION")"
sleep 1
installer "$W/a"
check "Zweitlauf rc 0" "$(cat "$W/rc")" 0
if grep -q 'bereits dieser Stand' "$W/aus"; then ok "Zweitlauf: nichts zu tun"; else bad "Zweitlauf meldet keine Gleichheit"; fi
grep -q 'Neustart aus' "$W/aus" && bad "Zweitlauf startete neu" || ok "Zweitlauf: kein Neustart"
check "Zweitlauf: source/ nicht neu geschrieben" "$(stat -c %Y "$SRC/VERSION")" "$_m1"

# Aus einem anderen Startpfad, gleicher Inhalt: ebenfalls nichts zu tun.
cp -r "$W/a" "$W/a2"; mkdir -p "$W/a2/.git"
installer "$W/a2"
if grep -q 'bereits dieser Stand' "$W/aus"; then ok "anderer Startpfad, gleicher Inhalt: nichts zu tun"
else bad "anderer Startpfad loeste Kopie aus"; fi

# Aelterer Startbaum: abgelehnt, source/ bleibt.
baum "$W/alt" 0.1.0
printf 'alt\n' >"$W/alt/src/chimera/x.py"
installer "$W/alt"
if grep -q 'kein Downgrade' "$W/aus"; then ok "aelterer Stand abgelehnt"; else bad "aelterer Stand nicht abgelehnt"; fi
check "source/ bleibt 0.2.0" "$(cat "$SRC/VERSION")" 0.2.0
check "abgelehnt: Gesamtlauf meldet Befund (rc 1)" "$(cat "$W/rc")" 1
if grep -q "ZWEITER SCHRITT AUS $SRC" "$SPUR"; then ok "abgelehnt: Folgeschritte laufen aus source/"
else bad "abgelehnt: Folgeschritte liefen aus dem Startbaum: $(cat "$SPUR")"; fi
installer "$W/alt" --downgrade=true
check "--downgrade=true: source/ = 0.1.0" "$(cat "$SRC/VERSION")" 0.1.0

# Online: Testrepo mit Tags, hoechster Tag gewinnt; Zweigspitze zaehlt nie.
G="$W/repo"; baum "$G" 0.2.0
( cd "$G" && git init -q && git config user.email t@example.invalid && git config user.name t &&
  git add -A && git commit -qm a && git tag v0.2.0 &&
  printf '0.10.0\n' >VERSION && printf 'print(10)\n' >src/chimera/__main__.py &&
  git commit -qam b && git tag v0.10.0 &&
  printf '0.11.0\n' >VERSION && git commit -qam c && git tag nicht-semver &&
  printf '0.12.0\n' >VERSION && git commit -qam d && git tag v0.12.0-rc1 &&
  printf '9.9.9\n' >VERSION && git commit -qam spitze ) >/dev/null 2>&1
QUELLE="$G"
installer "$W/a" --downgrade=true
check "online: source/ = hoechster Tag 0.10.0" "$(cat "$SRC/VERSION")" 0.10.0

# Ohne Tags: kein veroeffentlichter Stand, lokaler gilt; Spitze nie.
G2="$W/repo2"; baum "$G2" 5.0.0
( cd "$G2" && git init -q && git config user.email t@example.invalid && git config user.name t &&
  git add -A && git commit -qm a ) >/dev/null 2>&1
QUELLE="$G2"
installer "$W/a"
if grep -q 'kein veroeffentlichter Stand' "$W/aus"; then ok "ohne Tag benannt"; else bad "ohne Tag nicht benannt"; fi
check "ohne Tag: Zweigspitze 5.0.0 nicht genommen" "$(cat "$SRC/VERSION")" 0.10.0

# --- 4b. Kopie mit falschem Inhalt wird nicht getauscht ------------------
# Erwarteter Hash passt nicht zur Quelle (simuliert eine Kopie, die
# unterwegs anders wurde). source/ muss unberuehrt bleiben.
_vor="$(bib source_hash "$SRC")"
_rc=0
bib source_kopieren "$W/a" "$SRC" "falscher-hash" >/dev/null 2>&1 || _rc=$?
check "Kopie weicht ab: abgelehnt (rc 1)" "$_rc" 1
check "Kopie weicht ab: source/ unveraendert" "$(bib source_hash "$SRC")" "$_vor"
[ -d "$SRC.neu" ] && bad "Kopie weicht ab: .neu liegen geblieben" || ok "Kopie weicht ab: kein .neu-Rest"

# --- 5. Abgebrochener Tausch wird geheilt ---------------------------------
mv "$SRC" "$SRC.alt"
bib source_reparieren "$SRC" >/dev/null 2>&1
[ -d "$SRC" ] && ok "Tausch-Abbruch: alte Fassung wiederhergestellt" || bad "Tausch-Abbruch: alte Fassung wiederhergestellt -- source/ weg"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
