#!/bin/sh
# Tests fuer lib/sohelper.sh -- Ausfuehrer: Nutzer, Ordner, Units (Schritt 99).
#
# Geprueft wird die echte Bibliothek (Regel 9), in einer erfundenen Wurzel.
# `systemctl`, `useradd`, `userdel`, `getent`, `id` und `sleep` stehen als
# SHELL-FUNKTIONEN bereit (wie in test-service.sh/test-gateway.sh). Das Binary
# chimera-sohelper ist eine Attrappe; ob das ECHTE Binary ueber den Socket
# antwortet, prueft der Rust-Test (rust/crates/sohelper) und der Geraetetest.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
LIB="${CHIMERA_SOHELPER_LIB:-$HERE/lib/sohelper.sh}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-sohelper.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap "[ -n \"${KEEP:-}\" ] || rm -rf \"$W\"" EXIT INT TERM

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
# Eine Zeile muss genau so dastehen (nicht nur enthalten: "SocketGroup=chimera"
# steckt auch in "SocketGroup=chimera-sohelper").
zeile() { # $1 Name, $2 Datei, $3 Zeile
	if grep -qxF -- "$3" "$2" 2>/dev/null; then ok "$1"
	else bad "$1 -- Zeile '$3' fehlt"; fi
}
hat_nicht() {
	if grep -qF -- "$3" "$2" 2>/dev/null; then bad "$1 -- '$3' kam vor"
	else ok "$1"; fi
}

printf '=== Ausfuehrer (lib/sohelper.sh) ===\n'

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
	cat >"$R/opt/chimera/bin/chimera-sohelper" <<EOF
#!/bin/sh
printf '%s\n' "\$*" >>"$F/ping-spur"
[ "\${1:-}" = --ping ] && exit "\$(cat "$F/ping-rc")"
exit 0
EOF
	chmod 755 "$R/opt/chimera/bin/chimera-sohelper"
	# So, wie Schritt 99-sohelper es hinterlaesst: das Binary steht im Manifest
	# (dort legt binary_aus_baum es ab). Ohne den Eintrag gehoert es dem
	# Rueckbau nicht und bleibt zu Recht stehen.
	printf '%s\t99-sohelper\tdatei\t/opt/chimera/bin/chimera-sohelper\t%s\n' \
		"2026-11-11 21:00:00" "$(sha256sum "$R/opt/chimera/bin/chimera-sohelper" | cut -d' ' -f1)" \
		>>"$R/opt/chimera/state/manifest.tsv"
}

lauf() {
	(
		set +e
		CHIMERA_ROOT="$R"; export CHIMERA_ROOT
		CHIMERA_MANIFEST="$R/opt/chimera/state/manifest.tsv"
		CHIMERA_LOG_DIR="$R/logs"; CHIMERA_LOGFILE=""
		CHIMERA_MODE="${MODUS:-run}"; CHIMERA_STEP=99-sohelper
		. "$HERE/lib/common.sh"
		. "$HERE/lib/network.sh"
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
		# Eigentum ist im Test nicht herstellbar (in der Sandbox gibt es den
		# Nutzer nicht, und chown greift dort nicht). Geprueft wird deshalb,
		# dass der Installer das richtige Eigentum SETZT; die Wirkung zeigt
		# sich nur auf dem Geraet (dort ist es der Kernel, der prueft).
		chown() { printf 'chown %s\n' "$*" >>"$F/spur"; }
		stat() {
			case "${1:-}" in
				-c)
					if [ "${2:-}" = '%U %a' ]; then
						case "${3:-}" in
							*/opt/chimera/sohelper)
								printf 'chimera-sohelper %s\n' "$(command stat -c %a "${3:-}")" ;;
							*) command stat -c '%U %a' "${3:-}" ;;
						esac
					else
						command stat -c "${2:-}" "${3:-}"
					fi ;;
				*) command stat "$@" ;;
			esac
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

SOCK=etc/systemd/system/chimera-sohelper.socket
DIENST=etc/systemd/system/chimera-sohelper.service
ARBEIT=opt/chimera/sohelper

# --- 1. Erstlauf ----------------------------------------------------------
feld erst
lauf sohelper_einrichten
check "Erstlauf rc 0" "$(cat "$F/rc")" 0
hat "Systemnutzer ohne Home angelegt" "$F/spur" "useradd --system --user-group --no-create-home"
hat "Nutzer im Manifest als neu" "$R/opt/chimera/state/manifest.tsv" "nutzer	chimera-sohelper	neu"
hat "Socket-Aktivierung eingeschaltet" "$F/spur" "systemctl enable --now chimera-sohelper.socket"
hat "Socket im Manifest" "$R/opt/chimera/state/manifest.tsv" "dienst	chimera-sohelper.socket	aktiviert"

# --- 1b. Arbeitsordner ----------------------------------------------------
check "Arbeitsordner existiert" "$([ -d "$R/$ARBEIT" ] && echo ja || echo nein)" "ja"
check "Arbeitsordner 700" "$(stat -c %a "$R/$ARBEIT")" "700"
hat "Arbeitsordner wird dem Ausfuehrer zugeschrieben" "$F/spur" "chown chimera-sohelper:chimera-sohelper "$R/$ARBEIT""
check "Arbeitsordner: kein Eigentum fuer den Agenten" \
	"$(grep -c 'chown chimera:chimera' "$F/spur" || true)" "0"
hat "Arbeitsordner im Manifest" "$R/opt/chimera/state/manifest.tsv" "verzeich	/opt/chimera/sohelper"

# --- 2. Socket-Unit -------------------------------------------------------
S="$R/$SOCK"
hat "Socket: Pfad" "$S" "ListenStream=/run/chimera/sohelper.sock"
hat "Socket: Besitzer chimera-sohelper" "$S" "SocketUser=chimera-sohelper"
zeile "Socket: Gruppe des Agent-Dienstes (nur er fragt)" "$S" "SocketGroup=chimera"
hat "Socket: Modus 0660 (nicht fuer alle)" "$S" "SocketMode=0660"
hat_nicht "Socket: kein offener Modus" "$S" "SocketMode=0666"
hat "Socket: Datei verschwindet beim Stoppen" "$S" "RemoveOnStop=yes"
hat "Socket: startet den Dienst" "$S" "Service=chimera-sohelper.service"

# --- 3. Dienst-Unit -------------------------------------------------------
D="$R/$DIENST"
zeile "Dienst: eigener Nutzer" "$D" "User=chimera-sohelper"
hat "Dienst: keine zusaetzlichen Gruppen" "$D" "Group=chimera-sohelper"
hat_nicht "Dienst: keine SupplementaryGroups (weniger Rechte als der Agent)" "$D" "SupplementaryGroups="
hat "Dienst: Programm mit Arbeitsordner" "$D" "ExecStart=/opt/chimera/bin/chimera-sohelper --arbeit /opt/chimera/sohelper"
hat "Dienst: haengt am Socket" "$D" "Requires=chimera-sohelper.socket"
hat "Dienst: kein Netz (Regel 5n)" "$D" "IPAddressDeny=any"
hat "Dienst: Schluessel unerreichbar" "$D" "InaccessiblePaths=/opt/chimera/config"
hat "Dienst: Wurzel read-only" "$D" "ProtectSystem=strict"
hat "Dienst: schreibt nur im Arbeitsordner" "$D" "ReadWritePaths=/opt/chimera/sohelper"
check "Dienst: genau eine ReadWritePaths-Zeile" "$(grep -c '^ReadWritePaths=' "$D")" 1
hat_nicht "Dienst: keine Speichergrenze, die auf dem Pi nicht wirkt (10q)" "$D" "MemoryMax="
hat "Dienst: Fehlkonfiguration ohne Neustartschleife" "$D" "RestartPreventExitStatus=2"
_abschnitt="$(awk '/^\[/{s=$0} /^StartLimitBurst=/{print s}' "$D")"
check "StartLimitBurst steht in [Unit]" "$_abschnitt" "[Unit]"
hat_nicht "Dienst: kein EnvironmentFile (er braucht keine Einstellungen)" "$D" "EnvironmentFile="

# --- 4. Nachweis ist ein echter Aufruf ------------------------------------
hat "Nachweis ueber den Socket (--ping)" "$F/ping-spur" "--ping $R/run/chimera/sohelper.sock"
hat "Nachher gefragt: laeuft er noch?" "$F/spur" "systemctl is-active chimera-sohelper.service"

# --- 5. Kein Binary: Befund, nichts eingerichtet --------------------------
feld ohne_bin
rm -f "$R/opt/chimera/bin/chimera-sohelper"
lauf sohelper_einrichten
check "ohne Binary: rc 1 (Befund)" "$(cat "$F/rc")" 1
check "ohne Binary: keine Unit geschrieben" "$([ -e "$R/$DIENST" ] && echo da || echo weg)" "weg"
hat "ohne Binary: benannt" "$F/aus" "chimera-sohelper fehlt"

# --- 6. Gruppe des Agenten fehlt: Abbruch ---------------------------------
feld ohne_gruppe
: >"$F/gruppen"
lauf sohelper_einrichten
check "ohne Gruppe chimera: rc 2" "$(cat "$F/rc")" 2
hat "ohne Gruppe: Schritt 98 benannt" "$F/aus" "Schritt 98 zuerst"

# --- 7. Antwortet nicht: Befund -------------------------------------------
feld stumm
printf '1\n' >"$F/ping-rc"
lauf sohelper_einrichten
check "stumm: rc 1 (Befund)" "$(cat "$F/rc")" 1
hat "stumm: benannt" "$F/aus" "antwortet nicht auf /run/chimera/sohelper.sock"

# --- 8. Neustartschleife: Befund ------------------------------------------
feld schleife
printf '3\n' >"$F/nrestarts"
lauf sohelper_einrichten
check "Schleife: rc 1 (Befund)" "$(cat "$F/rc")" 1
hat "Schleife: benannt" "$F/aus" "neu gestartet"

# --- 9. Zweiter Lauf: nichts doppelt, Nutzer bleibt -----------------------
feld zweit
lauf sohelper_einrichten
_vor="$(cat "$F/spur")"
lauf sohelper_einrichten
check "zweiter Lauf: rc 0" "$(cat "$F/rc")" 0
check "zweiter Lauf: Nutzer nur einmal angelegt" \
	"$(grep -c 'useradd ' "$F/spur")" "$(printf '%s\n' "$_vor" | grep -c 'useradd ')"
check "zweiter Lauf: Socket nicht neu gestartet" \
	"$(grep -c 'systemctl restart chimera-sohelper.socket' "$F/spur")" "0"

# --- 10. Rueckbau ---------------------------------------------------------
feld rueck
lauf sohelper_einrichten
lauf sohelper_rueckbau
check "Rueckbau: rc 0" "$(cat "$F/rc")" 0
check "Rueckbau: Dienst-Unit weg" "$([ -e "$R/$DIENST" ] && echo da || echo weg)" "weg"
check "Rueckbau: Socket-Unit weg" "$([ -e "$R/$SOCK" ] && echo da || echo weg)" "weg"
check "Rueckbau: Binary weg" "$([ -e "$R/opt/chimera/bin/chimera-sohelper" ] && echo da || echo weg)" "weg"
check "Rueckbau: Arbeitsordner weg" "$([ -d "$R/$ARBEIT" ] && echo da || echo weg)" "weg"
check "Rueckbau: Nutzer weg" "$(grep -cx 'chimera-sohelper' "$F/nutzer" || true)" "0"
check "Rueckbau: Agent-Nutzer bleibt" "$(grep -cx 'chimera' "$F/nutzer" || true)" "1"

# ... und ein Ordner, in dem noch Arbeit liegt, bleibt stehen und wird benannt.
feld rueck_voll
lauf sohelper_einrichten
printf 'x\n' >"$R/$ARBEIT/notiz.txt"
lauf sohelper_rueckbau
check "Rueckbau mit Inhalt: rc 1 (Befund)" "$(cat "$F/rc")" 1
check "Rueckbau mit Inhalt: Ordner bleibt" "$([ -d "$R/$ARBEIT" ] && echo da || echo weg)" "da"
hat "Rueckbau mit Inhalt: benannt" "$F/aus" "ist nicht leer"

# --- 11. Trockenlauf aendert nichts ---------------------------------------
feld dry
MODUS=dry lauf sohelper_einrichten
check "Trockenlauf: rc 0" "$(cat "$F/rc")" 0
hat "Trockenlauf: kuendigt an" "$F/aus" "[wuerde anlegen]"
check "Trockenlauf: kein Nutzer angelegt" "$(grep -c 'chimera-sohelper' "$F/nutzer" || true)" "0"
check "Trockenlauf: keine Unit" "$([ -e "$R/$DIENST" ] && echo da || echo weg)" "weg"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
