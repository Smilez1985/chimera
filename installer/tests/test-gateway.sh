#!/bin/sh
# Tests fuer lib/gateway.sh -- Gateway-Nutzer, Socket- und Dienst-Unit (Schritt 99).
#
# Geprueft wird die echte Bibliothek (Regel 9), in einer erfundenen Wurzel.
# `systemctl`, `useradd`, `userdel`, `getent`, `id` und `sleep` stehen als
# SHELL-FUNKTIONEN bereit (wie in test-service.sh). Das Binary chimera-tor
# ist eine Attrappe, die ihre Argumente festhaelt und einen vorgegebenen
# Exitcode liefert -- ob das ECHTE Binary am Socket antwortet, prueft der
# Geraetetest und der Rust-Test (rust/crates/tor), nicht dieser.
#
# CHIMERA_GATEWAY_LIB ueberstimmt die Bibliothek -- damit faehrt
# counter-check-gateway.sh denselben Test gegen verfaelschte Fassungen.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
LIB="${CHIMERA_GATEWAY_LIB:-$HERE/lib/gateway.sh}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-gateway.XXXXXX" 2>/dev/null)" || W=""
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
hat() {   # $1 Name, $2 Datei, $3 Muster (fest)
	if grep -qF -- "$3" "$2" 2>/dev/null; then ok "$1"
	else bad "$1 -- '$3' fehlt"; fi
}
hat_nicht() {
	if grep -qF -- "$3" "$2" 2>/dev/null; then bad "$1 -- '$3' kam vor"
	else ok "$1"; fi
}

printf '=== Gateway (lib/gateway.sh) ===\n'

# --- Spielfeld ------------------------------------------------------------
feld() {
	F="$W/$1"
	R="$F/root"
	mkdir -p "$R/etc/systemd/system" "$R/opt/chimera/state" "$R/opt/chimera/bin"
	: >"$F/nutzer"; : >"$F/spur"
	printf 'chimera\n' >"$F/gruppen"
	printf 'chimera\n' >>"$F/nutzer"           # der Agent-Nutzer aus Schritt 98
	printf 'active\n' >"$F/aktiv"
	printf '0\n' >"$F/nrestarts"
	printf '0\n' >"$F/ping-rc"
	# Attrappe fuer das Binary: Argumente festhalten, Exitcode aus Datei.
	cat >"$R/opt/chimera/bin/chimera-tor" <<EOF
#!/bin/sh
printf '%s\n' "\$*" >>"$F/ping-spur"
exit "\$(cat "$F/ping-rc")"
EOF
	chmod 755 "$R/opt/chimera/bin/chimera-tor"
}

lauf() {
	(
		set +e
		CHIMERA_ROOT="$R"; export CHIMERA_ROOT
		CHIMERA_MANIFEST="$R/opt/chimera/state/manifest.tsv"
		CHIMERA_LOG_DIR="$R/logs"; CHIMERA_LOGFILE=""
		CHIMERA_MODE="${MODUS:-run}"; CHIMERA_STEP=99-gateway
		. "$HERE/lib/common.sh"
		. "$HERE/lib/manifest.sh"
		. "$HERE/lib/service.sh"
		. "$LIB"

		systemctl() {
			printf 'systemctl %s\n' "$*" >>"$F/spur"
			case "$1" in
				is-active) cat "$F/aktiv"; [ "$(cat "$F/aktiv")" = active ] ;;
				show)      cat "$F/nrestarts" ;;
				disable)   [ "${2:-}" = --now ] && [ ! -e "$F/haelt" ] && \
				               printf 'inactive\n' >"$F/aktiv"; return 0 ;;
				*)         return 0 ;;
			esac
		}
		useradd() {
			printf 'useradd %s\n' "$*" >>"$F/spur"
			eval "_u=\${$#}"; printf '%s\n' "$_u" >>"$F/nutzer"
		}
		userdel() {
			printf 'userdel %s\n' "$*" >>"$F/spur"
			grep -vx "$1" "$F/nutzer" >"$F/nutzer.neu" || true
			mv "$F/nutzer.neu" "$F/nutzer"
		}
		getent()  { [ "$1" = group ] && grep -qx "$2" "$F/gruppen"; }
		id() {
			if [ "$1" = -u ] && [ -n "${2:-}" ]; then grep -qx "$2" "$F/nutzer"
			else echo 0; fi
		}
		sleep() { printf 'sleep %s\n' "$*" >>"$F/spur"; }

		"$@" >"$F/aus" 2>&1
		echo $? >"$F/rc"
	)
}

SOCK=etc/systemd/system/chimera-tor.socket
DIENST=etc/systemd/system/chimera-tor.service

# --- 1. Erstlauf ----------------------------------------------------------
feld erst
lauf gateway_einrichten
check "Erstlauf rc 0" "$(cat "$F/rc")" 0
hat "Systemnutzer ohne Home angelegt" "$F/spur" "useradd --system --user-group --no-create-home"
hat "Nutzer im Manifest als neu" "$R/opt/chimera/state/manifest.tsv" "nutzer	chimera-tor	neu"
hat "Socket-Aktivierung eingeschaltet" "$F/spur" "systemctl enable --now chimera-tor.socket"
hat "Socket im Manifest" "$R/opt/chimera/state/manifest.tsv" "dienst	chimera-tor.socket	aktiviert"

# --- 2. Socket-Unit -------------------------------------------------------
S="$R/$SOCK"
hat "Socket: Pfad" "$S" "ListenStream=/run/chimera/tor.sock"
hat "Socket: Besitzer chimera-tor" "$S" "SocketUser=chimera-tor"
hat "Socket: Gruppe des Agent-Dienstes" "$S" "SocketGroup=chimera"
hat "Socket: Modus 0660 (nicht fuer alle)" "$S" "SocketMode=0660"
hat_nicht "Socket: kein offener Modus" "$S" "SocketMode=0666"
hat "Socket: Datei verschwindet beim Stoppen" "$S" "RemoveOnStop=yes"

# --- 3. Dienst-Unit -------------------------------------------------------
D="$R/$DIENST"
hat "Dienst: eigener Nutzer" "$D" "User=chimera-tor"
hat "Dienst: Programm mit --dienst" "$D" "ExecStart=/opt/chimera/bin/chimera-tor --dienst"
hat "Dienst: Umgebung aus der .env (Anbieteradressen)" "$D" "EnvironmentFile=-/opt/chimera/config/.env"
hat "Dienst: Speichergrenze (Regel 5n)" "$D" "MemoryMax=10M"
hat "Dienst: Fehlkonfiguration ohne Neustartschleife" "$D" "RestartPreventExitStatus=2"
_abschnitt="$(awk '/^\[/{s=$0} /^StartLimitBurst=/{print s}' "$D")"
check "StartLimitBurst steht in [Unit]" "$_abschnitt" "[Unit]"
hat "Dienst: haengt am Socket" "$D" "Requires=chimera-tor.socket"
hat "Dienst: Wurzel read-only" "$D" "ProtectSystem=strict"
# Regel 5n: der Agent-Dienst haengt NICHT per Requires= am Gateway -- und
# Schritt 99 fasst seine Unit gar nicht an. Die Unit liegt VOR dem Lauf da;
# danach muss sie byte-gleich sein.
feld agent
printf '[Unit]\nDescription=Agent (Attrappe)\n' >"$R/etc/systemd/system/chimera.service"
cp "$R/etc/systemd/system/chimera.service" "$F/agent.vorher"
lauf gateway_einrichten
if cmp -s "$F/agent.vorher" "$R/etc/systemd/system/chimera.service"; then
	ok "Agent-Dienst-Unit bleibt unberuehrt (kein Requires= aufs Gateway)"
else
	bad "Agent-Dienst-Unit bleibt unberuehrt -- wurde veraendert"
fi

# --- 3b. Sitzungs-Socket (Regel 5s) ---------------------------------------
SS="$R/etc/systemd/system/chimera-sitzung.socket"
feld erst-ss
lauf gateway_einrichten
SS="$R/etc/systemd/system/chimera-sitzung.socket"
hat "Sitzungs-Socket: Pfad" "$SS" "ListenStream=/run/chimera/sitzung.sock"
if grep -qxF "SocketUser=chimera" "$SS"; then ok "Sitzungs-Socket: gehoert dem Agent-Dienst"
else bad "Sitzungs-Socket: gehoert dem Agent-Dienst -- Zeile SocketUser=chimera fehlt"; fi
hat "Sitzungs-Socket: Gruppe des Gateways (einziger Client)" "$SS" "SocketGroup=chimera-tor"
hat "Sitzungs-Socket: Modus 0660" "$SS" "SocketMode=0660"
hat_nicht "Sitzungs-Socket: nicht offen" "$SS" "SocketMode=0666"
hat "Sitzungs-Socket: reicht an den Agent-Dienst weiter" "$SS" "Service=chimera.service"
hat "Sitzungs-Socket: Datei verschwindet beim Stoppen" "$SS" "RemoveOnStop=yes"
hat "Sitzungs-Socket: eingeschaltet" "$F/spur" "systemctl enable --now chimera-sitzung.socket"
hat "Sitzungs-Socket im Manifest" "$R/opt/chimera/state/manifest.tsv" "dienst	chimera-sitzung.socket	aktiviert"
hat_nicht "Erstlauf startet den Gateway-Socket nicht zusaetzlich neu" "$F/spur" "restart chimera-tor.socket"

# --- 4. Nachweis am Ergebnis ----------------------------------------------
hat "Nachweis: echter Aufruf des Sockets" "$F/ping-spur" "--ping $R/run/chimera/tor.sock"
feld stumm
printf '1\n' >"$F/ping-rc"
lauf gateway_einrichten
check "antwortet nicht -> rc 1 (Befund, kein Erfolg)" "$(cat "$F/rc")" 1
hat "Befund benannt" "$F/aus" "antwortet nicht"

feld inaktiv
printf 'inactive\n' >"$F/aktiv"
lauf gateway_einrichten
check "antwortet, aber Dienst nicht aktiv -> rc 1" "$(cat "$F/rc")" 1

feld schleife
printf '3\n' >"$F/nrestarts"
lauf gateway_einrichten
check "Neustartschleife -> rc 1" "$(cat "$F/rc")" 1
hat "Schleife benannt" "$F/aus" "Schleife"

# --- 5. Voraussetzungen ---------------------------------------------------
feld ohne-binary
rm -f "$R/opt/chimera/bin/chimera-tor"
lauf gateway_einrichten
check "ohne Binary -> rc 1 (Befund)" "$(cat "$F/rc")" 1
hat_nicht "ohne Binary: kein Nutzer angelegt" "$F/spur" "useradd"
hat_nicht "ohne Binary: keine Unit" "$F/spur" "enable"

feld ohne-gruppe
: >"$F/gruppen"
lauf gateway_einrichten
check "ohne Agent-Gruppe -> rc 2 (Abbruch)" "$(cat "$F/rc")" 2

# --- 6. Wiederholung ------------------------------------------------------
feld zweimal
lauf gateway_einrichten
: >"$F/spur"
lauf gateway_einrichten
check "Zweitlauf rc 0" "$(cat "$F/rc")" 0
hat_nicht "Zweitlauf legt keinen Nutzer neu an" "$F/spur" "useradd"
hat_nicht "Zweitlauf schaltet nicht erneut ein" "$F/spur" "enable"
hat_nicht "Zweitlauf startet den Socket nicht neu" "$F/spur" "restart"
check "Manifest: Socket genau einmal" \
	"$(grep -c 'dienst	chimera-tor.socket' "$R/opt/chimera/state/manifest.tsv")" 1

# --- 7. Neue Unit-Fassung -------------------------------------------------
printf '# alte Fassung\n' >"$R/$SOCK"
: >"$F/spur"
lauf gateway_einrichten
check "geaenderte Unit: rc 0" "$(cat "$F/rc")" 0
hat "geaenderte Unit: Socket neu gestartet" "$F/spur" "systemctl restart chimera-tor.socket"
hat "geaenderte Unit: daemon-reload" "$F/spur" "systemctl daemon-reload"

# --- 8. Nutzer gab es schon -----------------------------------------------
feld vorhanden
printf 'chimera-tor\n' >>"$F/nutzer"
lauf gateway_einrichten
hat_nicht "vorhandener Nutzer wird nicht angelegt" "$F/spur" "useradd"
hat "vorhandener Nutzer als vorher_da" "$R/opt/chimera/state/manifest.tsv" "nutzer	chimera-tor	vorher_da"

# --- 9. Trockenlauf -------------------------------------------------------
feld trocken
MODUS=dry lauf gateway_einrichten
check "Trockenlauf rc 0" "$(cat "$F/rc")" 0
[ ! -e "$R/$SOCK" ] && ok "Trockenlauf schreibt keine Unit" || bad "Trockenlauf schrieb eine Unit"
hat_nicht "Trockenlauf legt keinen Nutzer an" "$F/spur" "useradd"

# --- 10. Rueckbau ---------------------------------------------------------
feld rueck
lauf gateway_einrichten
: >"$F/spur"
lauf gateway_rueckbau
check "Rueckbau rc 0" "$(cat "$F/rc")" 0
hat "Rueckbau: Socket abgeschaltet" "$F/spur" "systemctl disable --now chimera-tor.socket"
hat "Rueckbau: Sitzungs-Socket abgeschaltet" "$F/spur" "systemctl disable --now chimera-sitzung.socket"
[ ! -e "$R/etc/systemd/system/chimera-sitzung.socket" ] && ok "Rueckbau: Sitzungs-Socket-Unit weg" || bad "Rueckbau: Sitzungs-Socket-Unit blieb"
[ ! -e "$R/$SOCK" ] && ok "Rueckbau: Socket-Unit weg" || bad "Rueckbau: Socket-Unit blieb"
[ ! -e "$R/$DIENST" ] && ok "Rueckbau: Dienst-Unit weg" || bad "Rueckbau: Dienst-Unit blieb"
hat "Rueckbau: Nutzer entfernt" "$F/spur" "userdel chimera-tor"
check "Rueckbau: Nutzer nicht mehr da" "$(grep -cx chimera-tor "$F/nutzer" || true)" 0
check "Rueckbau: Agent-Nutzer bleibt" "$(grep -cx chimera "$F/nutzer" || true)" 1

feld rueck-vorher
printf 'chimera-tor\n' >>"$F/nutzer"
lauf gateway_einrichten
: >"$F/spur"
lauf gateway_rueckbau
hat_nicht "Rueckbau: fremder Nutzer bleibt" "$F/spur" "userdel"

feld rueck-haelt
lauf gateway_einrichten
: >"$F/haelt"
lauf gateway_rueckbau
check "Rueckbau: laeuft noch -> rc 1" "$(cat "$F/rc")" 1

printf '\nErgebnis: %s ok, %s fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
