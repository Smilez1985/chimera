#!/bin/sh
# Gegenprobe zu test-mojo.sh (Regel 9): je eine Zusage von lib/mojo.sh
# verfaelschen, der Test muss an der erwarteten Stelle rot werden.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HERE/lib/mojo.sh"
TEST="$HERE/tests/test-mojo.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-mojo-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Mojo ===\n'

if CHIMERA_MOJO_LIB="$LIB" sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
fi

mutation() {
	_m="$G/$1.sh"
	sed "$2" "$LIB" >"$_m"
	if cmp -s "$LIB" "$_m"; then bad "$1: Mutation griff nicht"; return; fi
	if CHIMERA_MOJO_LIB="$_m" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $3" "$G/$1.txt"; then
		ok "$1: rot bei '$3'"
	else
		bad "$1: rot, aber nicht bei '$3'"; grep 'FAIL' "$G/$1.txt" | head -3
	fi
}


# M1: Das Drop-in haengt die Meldeunit ohne den Namen des Dienstes an (%N fehlt).
mutation dropin-ohne-name \
	's|OnFailure=chimera-mojo@%N.service|OnFailure=chimera-mojo.service|' \
	"Drop-in fuer chimera.service: OnFailure auf die Meldeunit mit dem Namen des Dienstes"

# M1b: Das Drop-in nimmt %n statt %N (haengt am Pi ein zweites .service an).
mutation dropin-n-statt-grosses-n \
	's|OnFailure=chimera-mojo@%N.service|OnFailure=chimera-mojo@%n.service|' \
	"Drop-ins: nie %n"

# M2: Die Meldeunit meldet jeden Zwischenfehler laut (Zustandspruefung weg).
mutation meldung-ohne-trennung \
	's|= failed|!= zzz|' \
	"Meldung: nur bei failed laut (Aufgabe)"

# M3: Die Meldeunit startet den Mojo-Lauf nie.
mutation meldung-ohne-lauf \
	's|exec systemctl start --no-block|exec echo|' \
	"Meldung: Aufgabe startet den Mojo-Lauf"

# M4: Mojo liest das Journal nicht (Gruppe fehlt im Lauf).
mutation lauf-ohne-gruppe \
	'/^mojo_lauf_text/,/^}/ s|^SupplementaryGroups=.*$||' \
	"Lauf: liest das Journal ueber die Gruppe"

# M5: Mojo laeuft als Agent-Nutzer (es koennte vom Agenten veraendert werden).
mutation lauf-als-agent \
	's|^TimeoutStartSec=900$|TimeoutStartSec=900\nUser=chimera|' \
	"Lauf: nicht als Agent-Nutzer"

# M6: Eine Warnung (Exitcode 1) laesst die Unit scheitern.
mutation warnung-scheitert \
	's|^SuccessExitStatus=1$||' \
	"Lauf: Warnung (Exitcode 1) ist kein Scheitern"

# M7: Der Bericht landet nicht auf der Karte.
mutation bericht-weg \
	's| --datei \$CHIMERA_STATE/mojo-letzter.json||' \
	"Lauf: legt den Bericht auf die Karte (state/)"

# M8: Der Zeitgeber laeuft nur einmal (kein Takt).
mutation zeit-ohne-takt \
	's|^OnUnitActiveSec=1h$||' \
	"Zeitgeber: stuendlich"

# M9: Der Zeitgeber wird nicht eingeschaltet.
mutation zeit-nicht-an \
	's|systemctl enable --now "\$CHIMERA_MOJO_ZEIT" >/dev/null 2>&1 \|\| {|true \|\| {|' \
	"Zeitgeber eingeschaltet"

# M10: Zweitlauf schaltet jedes Mal neu ein.
mutation nicht-idempotent \
	's|if ! manifest_has dienst "\$CHIMERA_MOJO_ZEIT" \|\| \\|if true \|\| \\|' \
	"Zweitlauf schaltet nicht erneut ein"

# M11: Ein wirkungsloses Drop-in wird nicht bemerkt (stiller Erfolg).
mutation nachweis-fehlt \
	's|\*) warn "OnFailure wirkt NICHT bei \$_mo_d (systemd meldet: .\${_mo_of:-leer}.)"; _mo_bad=1 ;;|*) : ;;|' \
	"Drop-in wirkt nicht: rc 1 (Befund, nicht stiller Erfolg)"

# M12: Fehlende Journal-Gruppe wird nicht bemerkt.
mutation gruppe-egal \
	's|^	if ! is_dry_run \&\& ! getent group "\$CHIMERA_MOJO_GRUPPE" >/dev/null 2>\&1; then$|	if false; then|' \
	"ohne Journal-Gruppe: rc 2 (Abbruch)"

# M13: Fehlendes Binary wird nicht bemerkt.
mutation binary-egal \
	's|^	if ! is_dry_run \&\& \[ ! -x "\$_mo_prog" \]; then$|	if false; then|' \
	"ohne Binary: rc 1 (Befund)"

# M14: Trockenlauf schreibt trotzdem.
mutation trockenlauf-schreibt \
	's|^	if is_dry_run; then$|	if false; then|' \
	"Trockenlauf rueckt systemctl nicht an"

# M15: Rueckbau laesst den Zeitgeber laufen.
mutation rueckbau-zeit \
	's|systemctl disable --now "\$CHIMERA_MOJO_ZEIT" >/dev/null 2>&1 \|\| true|true|' \
	"Rueckbau schaltet den Zeitgeber ab"

# M16: Rueckbau loescht ein Fremd-Drop-in mit (Verzeichnis samt Inhalt).
mutation rueckbau-fremd \
	's|rmdir "\$(dirname "\$_mr_p")" 2>/dev/null \|\| true|rm -rf "$(dirname "$_mr_p")"|' \
	"Rueckbau laesst ein fremdes Drop-in stehen"

# M17: Rueckbau entfernt das leere Drop-in-Verzeichnis nicht.
mutation rueckbau-verzeichnis \
	's|rmdir "\$(dirname "\$_mr_p")" 2>/dev/null \|\| true|true|' \
	"Rueckbau entfernt das leere Drop-in-Verzeichnis"

# M18: Hardware-Unit fehlt und wird als Fehler gemeldet.
mutation hw-fehlt-fehler \
	's|systemctl cat "\$_mo_d" >/dev/null 2>&1 \|\| continue|true|' \
	"ohne Hardware-Unit: rc 0 (wird uebersprungen, nicht gemeldet)"

# M19: Die Lauf-Unit versteckt /home (der Fehler vom 1.11. am Pi).
mutation lauf-ohne-home \
	'/^mojo_lauf_text/,/^}/ s|^ProtectHome=read-only$|ProtectHome=yes|' \
	"Lauf: nicht ProtectHome=yes"

# M20: Das Kartenprotokoll ist nicht beschreibbar.
mutation lauf-ohne-kartenpfad \
	's|^ReadWritePaths=\$CHIMERA_STATE -\$CHIMERA_LOGS_PRODUCTIVE$|ReadWritePaths=$CHIMERA_STATE|' \
	"Lauf: schreibt nur nach state/ und ins Kartenprotokoll"

# M21: Die Lauf-Unit bricht nach zwei Minuten ab (Nachladen von Paketen braucht laenger).
mutation lauf-zu-kurz \
	's|^TimeoutStartSec=900$|TimeoutStartSec=120|' \
	"Lauf: genug Zeit fuer das Nachladen von Python-Paketen"

# M22: Die Lauf-Unit kennt den Kartenpfad nicht (die Kartenpruefung bliebe blind).
mutation lauf-ohne-kartenpfad-umgebung \
	's|^Environment=CHIMERA_LOG_KARTE=.*$||' \
	"Lauf: kennt den Kartenpfad fuer die Pruefung"

# M23: Die Lauf-Unit kennt die requirements.txt nicht (das Nachladen bliebe ungeprueft).
mutation lauf-ohne-requirements \
	's|^Environment=CHIMERA_REQUIREMENTS=.*$||' \
	"Lauf: kennt die requirements.txt"

printf '\nErgebnis: %s ok, %s fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
