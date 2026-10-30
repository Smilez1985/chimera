#!/bin/sh
# Gegenprobe zu test-gateway.sh (Regel 9): je eine Zusage von lib/gateway.sh
# verfaelschen, der Test muss an der erwarteten Stelle rot werden.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HERE/lib/gateway.sh"
TEST="$HERE/tests/test-gateway.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-gateway-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Gateway ===\n'

if CHIMERA_GATEWAY_LIB="$LIB" sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
fi

mutation() {
	_m="$G/$1.sh"
	sed "$2" "$LIB" >"$_m"
	if cmp -s "$LIB" "$_m"; then bad "$1: Mutation griff nicht"; return; fi
	if CHIMERA_GATEWAY_LIB="$_m" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $3" "$G/$1.txt"; then
		ok "$1: rot bei '$3'"
	else
		bad "$1: rot, aber nicht bei '$3'"; grep 'FAIL' "$G/$1.txt" | head -3
	fi
}

# M1: Socket fuer alle offen.
mutation socket-offen \
	's|SocketMode=0660|SocketMode=0666|' \
	"Socket: Modus 0660"

# M1b: Socket-Datei bleibt nach dem Stoppen liegen (am Pi gefunden).
mutation socket-bleibt-liegen \
	's|^RemoveOnStop=yes$|RemoveOnStop=no|' \
	"Socket: Datei verschwindet beim Stoppen"

# M1c: Gateway bekommt die Anbieteradressen nicht.
mutation ohne-umgebung \
	's|^EnvironmentFile=-\$CHIMERA_CONFIG/.env$|# keine Umgebung|' \
	"Dienst: Umgebung aus der .env"

# M2: Speichergrenze weg.
mutation ohne-speichergrenze \
	's|^MemoryMax=\$CHIMERA_TOR_SPEICHER$|# MemoryMax entfallen|' \
	"Dienst: Speichergrenze"

# M3: Fehlkonfiguration startet in Schleife.
mutation neustartschleife-erlaubt \
	's|^RestartPreventExitStatus=2$|# nichts|' \
	"Dienst: Fehlkonfiguration"

# M4: Nachweis ueber den Exitcode von systemctl statt ueber einen Aufruf.
mutation nachweis-ohne-aufruf \
	's|if ! "\$_ge_prog" --ping "\$(rootpath "\$CHIMERA_TOR_SOCKET")" >/dev/null 2>\&1; then|if false; then|' \
	"antwortet nicht -> rc 1"

# M5: Schleife nicht erkannt.
mutation schleife-uebersehen \
	's|err "Gateway aktiv, aber schon \$_ge_nr Mal neu gestartet -- Schleife."|info "ok"|; s|^\t\t\treturn 1 ;;$|\t\t\t: ;;|' \
	"Neustartschleife -> rc 1"

# M6: Nutzer mit Home (Gateway braucht keins).
mutation nutzer-mit-home \
	's|--no-create-home|--create-home|' \
	"Systemnutzer ohne Home angelegt"

# M7: Fremder Nutzer wird beim Rueckbau geloescht.
mutation fremden-nutzer-loeschen \
	's|manifest_has_exact nutzer "\$CHIMERA_TOR_NUTZER" neu|manifest_has nutzer "$CHIMERA_TOR_NUTZER"|' \
	"Rueckbau: fremder Nutzer bleibt"

# M8: Zweitlauf schaltet den Socket erneut ein.
mutation nicht-idempotent \
	's|if ! manifest_has dienst "\$CHIMERA_TOR_SOCKETUNIT"; then|if true; then|' \
	"Zweitlauf schaltet nicht erneut ein"

# M9: Trockenlauf schreibt trotzdem.
mutation trockenlauf-schreibt \
	's|^	if is_dry_run; then$|	if false; then|' \
	"Trockenlauf"

# M10: Schritt 99 haengt den Agent-Dienst ans Gateway (Regel 5n verletzt).
mutation agent-haengt-am-gateway \
	's|^	log "Gateway-Nutzer"$|	echo "Requires=chimera-tor.socket" >>"$_ge_dir/chimera.service"; log "Gateway-Nutzer"|' \
	"Agent-Dienst-Unit bleibt unberuehrt"

printf '\nErgebnis: %s ok, %s fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
