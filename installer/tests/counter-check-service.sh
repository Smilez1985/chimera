#!/bin/sh
# Gegenprobe zu test-service.sh (Regel 9).
#
# Je eine Zusage von lib/service.sh wird in einer Kopie verfaelscht; der
# Test laeuft gegen die Kopie (CHIMERA_SERVICE_LIB) und muss rot werden,
# und zwar mit dem erwarteten Pruefpunkt. Eine Mutation, die die Datei
# nicht veraendert (Muster nicht gefunden), ist selbst ein Fehler -- sonst
# "faengt" der Test eine Mutation, die nie stattfand.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HERE/lib/service.sh"
TEST="$HERE/tests/test-service.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-dienst-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Dienst ===\n'

# Unveraendert muss der Test gruen sein -- sonst beweist Rot unten nichts.
if CHIMERA_SERVICE_LIB="$LIB" sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
	tail -5 "$G/basis.txt"
fi

# $1 Name, $2 sed-Ausdruck, $3 erwarteter FAIL-Text im Testlauf
mutation() {
	_m="$G/$1.sh"
	sed "$2" "$LIB" >"$_m"
	if cmp -s "$LIB" "$_m"; then
		bad "$1: Mutation griff nicht (Muster fehlt in lib/service.sh)"
		return
	fi
	if CHIMERA_SERVICE_LIB="$_m" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $3" "$G/$1.txt"; then
		ok "$1: rot bei '$3'"
	else
		bad "$1: rot, aber nicht bei '$3'"
		grep 'FAIL' "$G/$1.txt" | head -3
	fi
}

# M1: Startlimit in [Service] statt [Unit] -- systemd ignoriert es dort.
mutation startlimit-service \
	'/^StartLimitIntervalSec=300$/d; /^StartLimitBurst=5$/d; s/^Type=simple$/Type=simple\
StartLimitIntervalSec=300\
StartLimitBurst=5/' \
	"StartLimitBurst steht in \[Unit\]"

# M2: Nachweis ohne NRestarts -- eine Schleife saehe gesund aus.
mutation ohne-nrestarts \
	's/^\t\t\*)$/\t\tnie-passt)/' \
	"Schleife: rc 1"

# M3: Codestand nicht verglichen -- git pull liefe nie an.
mutation ohne-codestand \
	's/\[ "\$_se_code" = "\$_se_alt" \]/true/' \
	"neuer Stand: Dienst neu gestartet"

# M4: Rueckbau loescht auch einen vorher vorhandenen Nutzer.
mutation vorher-da-blind \
	's/manifest_has_exact nutzer "\$CHIMERA_DIENSTNUTZER" neu/manifest_has nutzer "$CHIMERA_DIENSTNUTZER"/' \
	"vorher da: kein userdel"

# M5: Rueckbau prueft nicht, ob der Dienst wirklich steht.
mutation stop-ungeprueft \
	's/= active \]; then$/= nie ]; then/' \
	"Dienst laeuft weiter: Rueckbau rc 1"

# M6: Lesbarkeit fuer den Dienstnutzer nicht geprueft.
mutation ohne-lesbar \
	's/^\tservice_lesbar "\$_se_repo" || return 2$/\t:/' \
	"unlesbares Repo: rc 2"

# M7: Nachweis ohne Wartezeit -- eine Schleife faellt erst spaeter auf.
mutation ohne-warten \
	's/^\t\tsleep "\$CHIMERA_DIENST_WARTEN"$/\t\t:/' \
	"gewartet vor dem Nachweis"

# M8: Kurzdienst bekommt ein RuntimeDirectory -- loeschte beim Ende den
# RAM-Ordner des laufenden Hauptdienstes.
mutation timer-runtimedir \
	's/^ExecStart=\/bin\/sh \$SERVICE_ABGLEICH --ruhig$/RuntimeDirectory=chimera\/logs\/productive\
ExecStart=\/bin\/sh $SERVICE_ABGLEICH --ruhig/' \
	"Ruhezeit-Abgleich loescht den RAM-Ordner nicht"

# M9: Timer wird beim Rueckbau nicht abgeschaltet.
mutation timer-bleibt \
	's/^\tfor _sr_e in \$SERVICE_TIMER \$SERVICE_HARDWARE \$CHIMERA_DIENST; do$/\tfor _sr_e in $SERVICE_HARDWARE $CHIMERA_DIENST; do/' \
	"Rueckbau: Timer abgeschaltet"

# M10: Der Dienst wartet nicht mehr auf den Boot-Abgleich -- startet dann
# mit belegten Leitungen VOR der Erkennung.
mutation dienst-ohne-abgleich \
	's/^After=network-online.target \$SERVICE_HARDWARE$/After=network-online.target/' \
	"Dienst wartet auf den Boot-Abgleich (After=)"

# M12: Der Dienst liest die Anzeige nicht -- liefe blind, obwohl erkannt.
mutation dienst-ohne-anzeige \
	's|^EnvironmentFile=-\$CHIMERA_RUN_ANZEIGE$|# ohne|' \
	"Dienst liest die Anzeige aus dem RAM (EnvironmentFile=-)"

# M11: Boot-Abgleich ruft nicht --hardware, sondern den ganzen Installer
# (Schritt 00 geht beim Boot ins Netz, Schritt 98 startet den Dienst neu).
mutation abgleich-ganzer-installer \
	's|^ExecStart=/bin/sh \$SERVICE_INSTALLER --hardware$|ExecStart=/bin/sh $SERVICE_INSTALLER|' \
	"Boot-Abgleich ruft nur die Hardware-Module"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
