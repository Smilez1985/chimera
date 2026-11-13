#!/bin/sh
# Test fuer die Klammer im GANZEN LAUF (Vorgabe smilez, 13.11.).
#
# Die Zusage: Jeder echte Lauf haelt die Dienste an und zeigt dabei das
# Update-Gesicht -- auch wenn sich am Quellstand nichts geaendert hat.
#
# Warum das ein eigener Test ist: Der Fehler vom 13.11. war genau dieser Fall.
# Ich schob die Quelle nach /opt/chimera/source und startete den Installer von
# dort. Startbaum und Ziel waren damit gleich, `klammer_noetig` sagte "nichts
# zu tun", die Klammer blieb aus -- kein Gesicht, keine angehaltenen Dienste,
# und Schritt 55 ersetzte das Binary trotzdem unter dem laufenden Dienst.
# Ein Test auf die Bibliotheksfunktion allein haette das nicht gefunden; hier
# laeuft der echte chimera-install.
#
# Geprueft wird gegen Attrappen, die ihren Zustand fuehren (systemctl) und
# gegen einen Sitzungs-Socket, der mitprotokolliert, was ihm gesagt wird.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
# CHIMERA_KLAMMER_BAUM laesst die Gegenprobe eine veraenderte Kopie des
# Installers pruefen, ohne das Repo anzufassen (wie CHIMERA_SOURCE_LIB).
QUELLE="${CHIMERA_KLAMMER_BAUM:-$HERE}"

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-klammer.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap '[ -n "${KEEP:-}" ] || rm -rf "$W"' EXIT INT TERM

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
hat() {
	if grep -q -- "$3" "$2" 2>/dev/null; then ok "$1"; else bad "$1 -- nicht in $(basename "$2")"; fi
}
hatnicht() {
	if grep -q -- "$3" "$2" 2>/dev/null; then bad "$1 -- doch gefunden: $3"; else ok "$1"; fi
}

printf '=== Klammer im ganzen Lauf ===\n'

for _b in python3 sh; do
	command -v "$_b" >/dev/null 2>&1 || { printf '  ohne %s nicht pruefbar\n' "$_b"; exit 0; }
done

# --- Ein Baum, den chimera-install laufen kann -----------------------------
BAUM="$W/baum"
mkdir -p "$BAUM/installer/steps" "$BAUM/src/chimera"
printf '0.2.0\n' >"$BAUM/VERSION"
printf 'print(1)\n' >"$BAUM/src/chimera/__main__.py"
cp "$QUELLE/chimera-install" "$BAUM/installer/chimera-install"
cp -r "$QUELLE/lib" "$BAUM/installer/lib"
cp "$QUELLE/steps/00-source.sh" "$BAUM/installer/steps/00-source.sh"
# Ein Folgeschritt, der nur seine Spur schreibt -- kein Dienst, kein Netz.
printf '#!/bin/sh\necho "schritt gelaufen" >>"$SPUR"\nexit 0\n' \
	>"$BAUM/installer/steps/10-spur.sh"

R="$W/root"; mkdir -p "$R"
SPUR="$W/spur"; export SPUR
ZUSTAND="$W/zustand"; export ZUSTAND
GESICHTER="$W/gesichter"; export GESICHTER

# `id -u` meldet 0 -- der Schritt verlangt root, der Test laeuft auch als
# gewoehnlicher Nutzer (wie in test-source.sh).
mkdir -p "$W/bin"
_echt_id="$(command -v id)"
printf '#!/bin/sh\nif [ "${1:-}" = -u ] && [ $# -eq 1 ]; then echo 0; else exec %s "$@"; fi\n' \
	"$_echt_id" >"$W/bin/id"
chmod +x "$W/bin/id"

# systemctl-Attrappe MIT Zustand: is-active sagt nur "active", was in der
# Zustandsdatei steht. Ohne Zustand meldete die Attrappe in test-source.sh
# immer "inactive", und "Dienste angehalten" war damit nicht messbar.
cat >"$W/bin/systemctl" <<'ATTRAPPE'
#!/bin/sh
_u=""
for _a in "$@"; do _u="$_a"; done
case "$1" in
	is-active)
		if grep -qx "$_u" "$ZUSTAND" 2>/dev/null; then echo active; exit 0; fi
		echo inactive; exit 3 ;;
	is-enabled)
		echo enabled; exit 0 ;;
	reset-failed)	exit 0 ;;
	stop)
		grep -vx "$_u" "$ZUSTAND" >"$ZUSTAND.neu" 2>/dev/null || :
		mv "$ZUSTAND.neu" "$ZUSTAND"
		printf 'stop %s\n' "$_u" >>"$SPUR"; exit 0 ;;
	start)
		grep -qx "$_u" "$ZUSTAND" 2>/dev/null || printf '%s\n' "$_u" >>"$ZUSTAND"
		printf 'start %s\n' "$_u" >>"$SPUR"; exit 0 ;;
esac
exit 0
ATTRAPPE
chmod +x "$W/bin/systemctl"

# Sitzungs-Socket: Der Dienst, der das Gesicht zeichnet. Er protokolliert, was
# ihm geschickt wird, und antwortet wie der echte ({"ok":true}).
SOCK="$W/sitzung.sock"
cat >"$W/gesichtsdienst.py" <<'DIENST'
import json, os, socket, sys
pfad, spur = sys.argv[1], sys.argv[2]
if os.path.exists(pfad):
    os.unlink(pfad)
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(pfad)
s.listen(8)
while True:
    c, _ = s.accept()
    puffer = b""
    while b"\n" not in puffer:
        d = c.recv(4096)
        if not d:
            break
        puffer += d
    zeile = puffer.split(b"\n", 1)[0].decode("utf-8", "replace")
    with open(spur, "a", encoding="utf-8") as f:
        f.write(zeile + "\n")
    try:
        auftrag = json.loads(zeile)
        antwort = {"ok": True, "gesicht": auftrag.get("name", "?")}
    except ValueError:
        antwort = {"ok": False, "fehler": "kein JSON"}
    c.sendall((json.dumps(antwort) + "\n").encode())
    c.close()
DIENST
# Ausgabe umleiten: Ein Hintergrundprozess, der stdout erbt, haelt die Leitung
# der aufrufenden Sitzung offen -- der Test haengt dann beim Warten auf das
# Ende der Ausgabe, nicht an seiner Arbeit.
python3 "$W/gesichtsdienst.py" "$SOCK" "$GESICHTER" >/dev/null 2>&1 &
_GDPID=$!
trap '[ -n "${KEEP:-}" ] || { kill $_GDPID 2>/dev/null; rm -rf "$W"; }' EXIT INT TERM
# Warten, bis der Socket da ist -- hoechstens 5 s, dann benannt abbrechen.
_i=0
while [ ! -S "$SOCK" ] && [ "$_i" -lt 50 ]; do
	_i=$((_i+1)); sleep 0.1
done
[ -S "$SOCK" ] || { bad "Sitzungs-Socket kam nicht hoch"; exit 1; }

ORIG="/opt/chimera/source-mit-abweichendem-inhalt"
installer() {
	: >"$SPUR"
	set +e
	PATH="$W/bin:$PATH" CHIMERA_ROOT="$R" CHIMERA_LOG_DIR="$W/logs" \
	CHIMERA_QUELLE_URL="$W/gibt-es-nicht" CHIMERA_HELFER=1 \
	CHIMERA_SITZUNG_SOCKET="$SOCK" \
		sh "$BAUM/installer/chimera-install" "$@" >"$W/aus" 2>&1
	echo $? >"$W/rc"
	set -e
}
SRC="$R/opt/chimera/source"

# --- 1. Erster Lauf: Dienste laufen, das Gesicht muss erscheinen ----------
printf 'chimera.service\nchimera-mojo.timer\nchimera-tor.socket\nchimera-sitzung.socket\nchimera-tor.service\n' \
	>"$ZUSTAND"
installer
hat "Erstlauf: Dienste angehalten (chimera-tor.service)" "$SPUR" "stop chimera-tor.service"
hat "Erstlauf: Dienste angehalten (chimera.service)" "$SPUR" "stop chimera.service"
hat "Erstlauf: Gesicht UPDATE geschickt" "$GESICHTER" '"name": "UPDATE"'
hat "Erstlauf: Gesicht gemeldet" "$W/aus" "Gesicht UPDATE gesetzt"
hat "Erstlauf: Dienste wieder gestartet" "$SPUR" "start chimera.service"
hat "Erstlauf: Schritt lief" "$SPUR" "schritt gelaufen"

# --- 2. Zweiter Lauf, GLEICHER Stand: die Zusage, um die es geht ---------
# Genau die Lage vom 13.11.: Quelle liegt schon in source/, es aendert sich
# nichts. Frueher endete das mit "Kein neuer Stand ... nichts wird angefasst".
: >"$GESICHTER"
printf 'chimera.service\nchimera-mojo.timer\nchimera-tor.socket\nchimera-sitzung.socket\nchimera-tor.service\n' \
	>"$ZUSTAND"
installer
hatnicht "Zweitlauf: keine Ausrede 'Kein neuer Stand'" "$W/aus" "Kein neuer Stand"
hat "Zweitlauf: Dienste trotzdem angehalten" "$SPUR" "stop chimera-tor.service"
hat "Zweitlauf: Gesicht UPDATE geschickt" "$GESICHTER" '"name": "UPDATE"'
hat "Zweitlauf: Gesicht gemeldet" "$W/aus" "Gesicht UPDATE gesetzt"
hat "Zweitlauf: Dienste wieder gestartet" "$SPUR" "start chimera.service"

# --- 3. Dieselbe Lage, aber direkt aus source/ gestartet -----------------
# Das ist der Weg, den ich am 13.11. genommen habe: Startbaum == source.
: >"$GESICHTER"
printf 'chimera.service\nchimera-tor.socket\nchimera-sitzung.socket\nchimera-tor.service\n' >"$ZUSTAND"
: >"$SPUR"
set +e
PATH="$W/bin:$PATH" CHIMERA_ROOT="$R" CHIMERA_LOG_DIR="$W/logs" \
CHIMERA_QUELLE_URL="$W/gibt-es-nicht" CHIMERA_HELFER=1 \
CHIMERA_SITZUNG_SOCKET="$SOCK" \
	sh "$SRC/installer/chimera-install" >"$W/aus" 2>&1
echo $? >"$W/rc"
set -e
hat "aus source/: Dienste angehalten" "$SPUR" "stop chimera.service"
hat "aus source/: Gesicht UPDATE geschickt" "$GESICHTER" '"name": "UPDATE"'

# --- 4. Gegenprobe der Attrappe selbst ------------------------------------
# Waere der Socket nicht benutzt worden, muesste 2 rot sein -- dann waere auch
# 1 nicht aussagekraeftig. Hier wird nur geprueft, dass die Spur wirklich leer
# sein KANN (sonst haekte der Test an einer Datei, die immer gefuellt ist).
: >"$GESICHTER"
hatnicht "leere Gesichtsspur bleibt leer" "$GESICHTER" "UPDATE"

printf '\n=== Ergebnis: %s ok, %s FAIL ===\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ] || exit 1
exit 0
