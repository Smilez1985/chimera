#!/bin/sh
# Tests fuer lib/service.sh -- Dienstnutzer und systemd-Unit (Schritt 98).
#
# Geprueft wird die echte Bibliothek (Regel 9), in einer erfundenen Wurzel.
# `systemctl`, `useradd`, `userdel`, `runuser`, `getent`, `id` und `sleep`
# stehen als SHELL-FUNKTIONEN bereit (wie in test-module-state.sh): unter
# jeder Shell gleich, unabhaengig vom PATH des Runners, und ohne dass der
# Test einen echten Nutzer anlegt.
#
# CHIMERA_SERVICE_LIB ueberstimmt die geladene Bibliothek -- damit faehrt
# counter-check-service.sh denselben Test gegen verfaelschte Fassungen.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
LIB="${CHIMERA_SERVICE_LIB:-$HERE/lib/service.sh}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-dienst.XXXXXX" 2>/dev/null)" || W=""
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

printf '=== Dienst (lib/service.sh) ===\n'

# --- Spielfeld ------------------------------------------------------------
# $1 Name. Legt Wurzel, Repo-Attrappe und Zustandsdateien der Attrappen an.
feld() {
	F="$W/$1"
	R="$F/root"
	REPO="$F/repo"
	mkdir -p "$R/etc/systemd/system" "$R/var/lib/chimera" "$R/var/log/chimera" \
		"$REPO/src/chimera"
	printf 'print(1)\n' >"$REPO/src/chimera/__main__.py"
	printf 'pillow\n' >"$REPO/requirements.txt"
	: >"$F/nutzer"; : >"$F/spur"
	printf 'audio\ngpio\n' >"$F/gruppen"
	printf 'active\n' >"$F/aktiv"
	printf '0\n' >"$F/nrestarts"
	printf '0\n' >"$F/runuser-rc"
}

# Ein Lauf in einer Unterschale: Attrappen + Bibliothek laden, Befehl
# ausfuehren. $1 Befehl (service_einrichten / service_rueckbau), Ausgabe
# nach $F/aus, rc nach $F/rc.
lauf() {
	(
		set +e
		CHIMERA_ROOT="$R"; export CHIMERA_ROOT
		CHIMERA_MANIFEST="$R/var/lib/chimera/manifest.tsv"
		CHIMERA_LOG_DIR="$R/var/log/chimera"; CHIMERA_LOGFILE=""
		CHIMERA_MODE=run; CHIMERA_STEP=test
		. "$HERE/lib/common.sh"
		. "$HERE/lib/manifest.sh"
		. "$LIB"

		systemctl() {
			printf 'systemctl %s\n' "$*" >>"$F/spur"
			case "$1" in
				is-active) cat "$F/aktiv"; [ "$(cat "$F/aktiv")" = active ] ;;
				show)      cat "$F/nrestarts" ;;
				# Wie in echt: --now stoppt. Ein Dienst, der danach noch
				# laeuft, ist ein Befund (Test haelt ihn per Datei fest).
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
		runuser() { return "$(cat "$F/runuser-rc")"; }
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

PY=/opt/chimera/venv/bin/python
UNIT_REL=etc/systemd/system/chimera.service

# --- 1. Unit-Text ---------------------------------------------------------
feld text
lauf service_einrichten "$PY" "$REPO"
U="$R/$UNIT_REL"
check "Erstlauf rc 0" "$(cat "$F/rc")" 0
# StartLimit* muss in [Unit] stehen: dort, und nur dort, wirkt es.
_abschnitt="$(awk '/^\[/{s=$0} /^StartLimitBurst=/{print s}' "$U")"
check "StartLimitBurst steht in [Unit]" "$_abschnitt" "[Unit]"
_abschnitt="$(awk '/^\[/{s=$0} /^StartLimitIntervalSec=/{print s}' "$U")"
check "StartLimitIntervalSec steht in [Unit]" "$_abschnitt" "[Unit]"
hat "Konfigurationsfehler (2) startet nicht neu" "$U" "RestartPreventExitStatus=2"
hat "ExecStart im Dienstmodus" "$U" "ExecStart=$PY -m chimera --dienst"
hat "laeuft als eigener Nutzer" "$U" "User=chimera"
hat "nur vorhandene Gruppen" "$U" "SupplementaryGroups=audio gpio"
hat_nicht "keine fehlende Gruppe (spi)" "$U" "spi"
hat "liest die .env" "$U" "EnvironmentFile=/etc/chimera/.env"

# --- 2. Erstlauf: Nutzer, Manifest, Start, Nachweis -----------------------
M="$R/var/lib/chimera/manifest.tsv"
hat "Nutzer angelegt" "$F/nutzer" "chimera"
hat "Manifest: nutzer neu" "$M" "nutzer	chimera	neu"
hat "Manifest: dienst aktiviert" "$M" "dienst	chimera.service	aktiviert"
hat "Manifest: Unit als datei" "$M" "datei	$R/$UNIT_REL"
hat "daemon-reload" "$F/spur" "systemctl daemon-reload"
hat "enable" "$F/spur" "systemctl enable chimera.service"
hat "gestartet" "$F/spur" "systemctl restart chimera.service"
hat "gewartet vor dem Nachweis" "$F/spur" "sleep 10"
if [ -s "$R/var/lib/chimera/dienst-stand" ]; then ok "Stand festgehalten"
else bad "Stand nicht festgehalten"; fi

# --- 3. Zweitlauf aendert nichts -------------------------------------------
_m1="$(sha256sum "$M" | cut -d' ' -f1)"
: >"$F/spur"
lauf service_einrichten "$PY" "$REPO"
check "Zweitlauf rc 0" "$(cat "$F/rc")" 0
hat_nicht "Zweitlauf: kein Neustart" "$F/spur" "restart"
hat_nicht "Zweitlauf: kein daemon-reload" "$F/spur" "daemon-reload"
check "Zweitlauf: Manifest unveraendert" "$(sha256sum "$M" | cut -d' ' -f1)" "$_m1"

# --- 4. Neuer Code (git pull) -> Neustart ----------------------------------
printf 'print(2)\n' >"$REPO/src/chimera/__main__.py"
: >"$F/spur"
lauf service_einrichten "$PY" "$REPO"
check "neuer Stand rc 0" "$(cat "$F/rc")" 0
hat "neuer Stand: Dienst neu gestartet" "$F/spur" "systemctl restart chimera.service"

# --- 5. Neustartschleife wird erkannt --------------------------------------
feld schleife
printf '3\n' >"$F/nrestarts"
lauf service_einrichten "$PY" "$REPO"
check "Schleife: rc 1" "$(cat "$F/rc")" 1
hat "Schleife benannt" "$F/aus" "Schleife"
if [ -e "$R/var/lib/chimera/dienst-stand" ]; then
	bad "Schleife: Stand trotzdem festgehalten (naechster Lauf versucht nicht neu)"
else ok "Schleife: kein Stand festgehalten"; fi

# --- 6. Nicht aktiv --------------------------------------------------------
feld tot
printf 'failed\n' >"$F/aktiv"
lauf service_einrichten "$PY" "$REPO"
check "nicht aktiv: rc 1" "$(cat "$F/rc")" 1

# --- 7. Repo fuer den Dienstnutzer unlesbar --------------------------------
feld unlesbar
printf '1\n' >"$F/runuser-rc"
lauf service_einrichten "$PY" "$REPO"
check "unlesbares Repo: rc 2" "$(cat "$F/rc")" 2
if [ -e "$R/$UNIT_REL" ]; then bad "unlesbares Repo: Unit trotzdem geschrieben"
else ok "unlesbares Repo: keine Unit"; fi

# --- 8. Rueckbau -----------------------------------------------------------
feld rueckbau
lauf service_einrichten "$PY" "$REPO"
: >"$F/spur"
lauf service_rueckbau
check "Rueckbau rc 0" "$(cat "$F/rc")" 0
hat "Rueckbau: abgeschaltet" "$F/spur" "systemctl disable --now chimera.service"
if [ -e "$R/$UNIT_REL" ]; then bad "Rueckbau: Unit blieb"; else ok "Rueckbau: Unit weg"; fi
hat "Rueckbau: daemon-reload" "$F/spur" "systemctl daemon-reload"
hat "Rueckbau: Nutzer entfernt" "$F/spur" "userdel chimera"

# --- 8b. Dienst laesst sich nicht stoppen -> Befund, nicht Erfolg ----------
feld haelt
lauf service_einrichten "$PY" "$REPO"
: >"$F/haelt"
lauf service_rueckbau
check "Dienst laeuft weiter: Rueckbau rc 1" "$(cat "$F/rc")" 1
hat "Dienst laeuft weiter: benannt" "$F/aus" "Dienst laeuft noch"

# --- 9. Ein vorher vorhandener Nutzer bleibt -------------------------------
feld vorher
printf 'chimera\n' >"$F/nutzer"
lauf service_einrichten "$PY" "$REPO"
hat "vorher da: Manifest vorher_da" "$R/var/lib/chimera/manifest.tsv" "nutzer	chimera	vorher_da"
hat_nicht "vorher da: kein useradd" "$F/spur" "useradd"
: >"$F/spur"
lauf service_rueckbau
hat_nicht "vorher da: kein userdel" "$F/spur" "userdel"
hat "vorher da: Nutzer existiert noch" "$F/nutzer" "chimera"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
