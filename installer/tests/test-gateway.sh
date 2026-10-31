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
if [ "\${1:-}" = --passwort-hash ]; then
	read -r pw; printf 'pw=%s\nargs=%s\n' "\$pw" "\$*" >>"$F/pw-spur"
	[ -f "$F/hash-leer" ] && exit 0
	printf 'pbkdf2-sha256\$1\$aabbccdd11223344\$%s\n' "0000000000000000000000000000000000000000000000000000000000000000"
	exit 0
fi
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
				is-enabled) [ ! -e "$F/aus-${3:-$2}" ] ;;
				is-active)
					case "${2:-}" in
						--quiet) [ ! -e "$F/aus-$3" ] && [ "$(cat "$F/aktiv")" = active ] ;;
						*) cat "$F/aktiv"; [ "$(cat "$F/aktiv")" = active ] ;;
					esac ;;
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

# --- 1b. Ablagen (Regel 5t) ------------------------------------------------
for _d in config/anbieter config/geheim config/wahl state/katalog; do
	[ -d "$R/opt/chimera/$_d" ] && ok "Ablage angelegt: $_d" || bad "Ablage fehlt: $_d"
	check "Ablage $_d: Modus 700" "$(stat -c %a "$R/opt/chimera/$_d")" 700
	hat "Ablage $_d im Manifest" "$R/opt/chimera/state/manifest.tsv" "verzeich	/opt/chimera/$_d"
done
check "config/ nur Durchgang fuer andere (751)" "$(stat -c %a "$R/opt/chimera/config")" 751
check "state/ nur fuer das Gateway durchgaengig (710), Agent bleibt draussen (10r)" "$(stat -c %a "$R/opt/chimera/state")" 710
_rw="$(grep '^ReadWritePaths=' "$R/$DIENST" || true)"
check "Dienst: genau eine ReadWritePaths-Zeile" "$(grep -c '^ReadWritePaths=' "$R/$DIENST")" 1
for _d in config/anbieter config/geheim config/wahl state/katalog; do
	case "$_rw" in *"-/opt/chimera/$_d"*) ok "Dienst darf schreiben: $_d" ;; *) bad "Dienst: $_d fehlt in ReadWritePaths" ;; esac
done
# Kein Pfad ohne Unterordner: weder config noch state als Ganzes.
case " $_rw " in
	*" -/opt/chimera/config "*|*"=-/opt/chimera/config "*|*" -/opt/chimera/state "*|*"=-/opt/chimera/state "*)
		bad "Dienst: config/ oder state/ als Ganzes schreibbar" ;;
	*) ok "Dienst: config/ und state/ nicht als Ganzes schreibbar" ;;
esac

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
hat "Dienst: kennt den Sitzungs-Socket (Telegram-Tuer, Regel 5s)" "$D" "Environment=CHIMERA_SITZUNG_SOCKET=/run/chimera/sitzung.sock"
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
hat_nicht "Zweitlauf schaltet nicht erneut ein" "$F/spur" "enable --now"
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

# --- 7. Web-Passwort (Regel 5m, 5j) ----------------------------------------
ENVD=etc/chimera/.env
webfeld() {
	feld "$1"
	mkdir -p "$R/opt/chimera/config"
	printf '# x\nCHIMERA_WEB_PASSWORT_HASH=%s\nCHIMERA_WEB_PORT=\n' "${2:-}" >"$R/opt/chimera/config/.env"
	chmod 640 "$R/opt/chimera/config/.env"
}
WENV=opt/chimera/config/.env

webfeld web-ohne
lauf gateway_einrichten
check "Web ohne Passwort: rc 0" "$(cat "$F/rc")" 0
hat_nicht "Web ohne Passwort: kein Hash eingetragen" "$R/$WENV" "pbkdf2"
hat "Web ohne Passwort: sagt, wie man einschaltet" "$F/aus" "Web-Oberflaeche bleibt zu"

webfeld web-mit
CHIMERA_WEB_PASSWORT='Geheimes-Pw-1' lauf gateway_einrichten
check "Web mit Passwort: rc 0" "$(cat "$F/rc")" 0
hat "Web mit Passwort: Hash steht in der .env" "$R/$WENV" "CHIMERA_WEB_PASSWORT_HASH=pbkdf2-sha256\$1\$aabbccdd11223344"
hat_nicht "Web mit Passwort: Klartext nicht in der .env" "$R/$WENV" "Geheimes-Pw-1"
hat_nicht "Web mit Passwort: Klartext nicht im Protokoll" "$F/aus" "Geheimes-Pw-1"
hat "Web mit Passwort: Binary bekam es ueber stdin" "$F/pw-spur" "pw=Geheimes-Pw-1"
hat_nicht "Web mit Passwort: nicht als Argument" "$F/pw-spur" "--passwort-hash Geheimes"
hat "Web mit Passwort: Aufruf nur mit --passwort-hash" "$F/pw-spur" "args=--passwort-hash"
check "Web mit Passwort: .env behaelt Modus 640" "$(stat -c %a "$R/$WENV")" 640
check "Web mit Passwort: Port-Zeile bleibt" "$(grep -c '^CHIMERA_WEB_PORT=' "$R/$WENV")" 1

# Ohne vorhandene Zeile wird angehaengt (anderer Zweig als oben).
webfeld web-anhaengen
sed -i '/^CHIMERA_WEB_PASSWORT_HASH=/d' "$R/$WENV"
CHIMERA_WEB_PASSWORT='Anhaengen-Pw-5' lauf gateway_einrichten
check "Web anhaengen: rc 0" "$(cat "$F/rc")" 0
hat "Web anhaengen: Hash steht in der .env" "$R/$WENV" "CHIMERA_WEB_PASSWORT_HASH=pbkdf2-sha256\$1\$aabbccdd11223344"
hat_nicht "Web anhaengen: Klartext nicht in der .env" "$R/$WENV" "Anhaengen-Pw-5"
check "Web anhaengen: genau eine Hash-Zeile" "$(grep -c '^CHIMERA_WEB_PASSWORT_HASH=' "$R/$WENV")" 1

webfeld web-da 'pbkdf2-sha256$1$aa$bb'
CHIMERA_WEB_PASSWORT='Anderes-Pw-22' lauf gateway_einrichten
hat "Web: vorhandener Hash bleibt" "$R/$WENV" "CHIMERA_WEB_PASSWORT_HASH=pbkdf2-sha256\$1\$aa\$bb"
check "Web: Binary wurde nicht gefragt" "$(cat "$F/pw-spur" 2>/dev/null | wc -l | tr -d ' ')" 0

webfeld web-leer
: >"$F/hash-leer"
CHIMERA_WEB_PASSWORT='Zu-Kurz' lauf gateway_einrichten
check "Web: leerer Hash -> Abbruch rc 2" "$(cat "$F/rc")" 2
hat_nicht "Web: leerer Hash wird nicht eingetragen" "$R/$WENV" "CHIMERA_WEB_PASSWORT_HASH=pb"
check "Web: keine Nebendatei liegt herum" "$(ls "$R/opt/chimera/config" | grep -c neu)" 0

webfeld web-trocken
MODUS=dry CHIMERA_WEB_PASSWORT='Trocken-Pw-3' lauf gateway_einrichten
hat_nicht "Web Trockenlauf: nichts eingetragen" "$R/$WENV" "pbkdf2"

webfeld web-neustart
lauf gateway_einrichten
: >"$F/spur"
CHIMERA_WEB_PASSWORT='Neustart-Pw-4' lauf gateway_einrichten
hat "Web: neuer Hash -> Gateway wird neu gestartet (stop)" "$F/spur" "systemctl stop chimera-tor.service"

# --- 8. Laeuft der Dienst schon, wird er fuer den Sitzungs-Socket kurz angehalten
feld dienst-laeuft
lauf gateway_einrichten
_z="$(grep -n 'systemctl stop chimera.service' "$F/spur" | head -1 | cut -d: -f1)"
_e="$(grep -n 'systemctl enable --now chimera-sitzung.socket' "$F/spur" | head -1 | cut -d: -f1)"
_s="$(grep -n 'systemctl start chimera.service' "$F/spur" | head -1 | cut -d: -f1)"
check "Dienst lief: rc 0" "$(cat "$F/rc")" 0
check "Dienst lief: erst stop, dann enable, dann start" \
	"$([ -n "$_z" ] && [ -n "$_e" ] && [ -n "$_s" ] && [ "$_z" -lt "$_e" ] && [ "$_e" -lt "$_s" ] && echo ja || echo nein)" ja

feld dienst-aus
printf 'inactive\n' >"$F/aktiv"
lauf gateway_einrichten
hat_nicht "Dienst aus: wird nicht angehalten" "$F/spur" "systemctl stop chimera.service"
hat_nicht "Dienst aus: wird nicht gestartet" "$F/spur" "systemctl start chimera.service"

# --- 9. Manifest sagt "aktiviert", der Socket ist aber aus (am Pi gefunden) --
feld tor-aus
lauf gateway_einrichten
: >"$F/spur"
: >"$F/aus-chimera-tor.socket"
lauf gateway_einrichten
hat "Socket aus trotz Manifest: wird neu eingeschaltet" "$F/spur" "systemctl enable --now chimera-tor.socket"
check "Socket aus trotz Manifest: Manifest nicht doppelt" \
	"$(grep -c 'dienst	chimera-tor.socket' "$R/opt/chimera/state/manifest.tsv")" 1
rm -f "$F/aus-chimera-tor.socket"
: >"$F/spur"
lauf gateway_einrichten
hat_nicht "Socket an: zweiter Lauf schaltet nichts neu ein" "$F/spur" "enable --now"

printf '\nErgebnis: %s ok, %s fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
