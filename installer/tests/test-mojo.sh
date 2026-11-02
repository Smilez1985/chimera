#!/bin/sh
# Tests fuer lib/mojo.sh -- Meldeunit, Zeitgeber, Drop-ins (Schritt 27).
#
# Geprueft wird die echte Bibliothek, in einer erfundenen Wurzel. `systemctl`,
# `getent` und `id` stehen als SHELL-FUNKTIONEN bereit (wie in test-gateway.sh).
# Ob systemd die Drop-ins wirklich annimmt, prueft der Geraetetest, nicht dieser.
#
# CHIMERA_MOJO_LIB ueberstimmt die Bibliothek -- damit counter-check-mojo.sh
# denselben Test gegen verfaelschte Fassungen faehrt.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="${CHIMERA_MOJO_LIB:-$HERE/lib/mojo.sh}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-mojo.XXXXXX" 2>/dev/null)" || W=""
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
hat() {
	if grep -qF -- "$3" "$2" 2>/dev/null; then ok "$1"
	else bad "$1 -- '$3' fehlt"; fi
}
hat_nicht() {
	if grep -qF -- "$3" "$2" 2>/dev/null; then bad "$1 -- '$3' kam vor"
	else ok "$1"; fi
}

printf '=== Mojo (lib/mojo.sh) ===\n'

feld() {
	F="$W/$1"
	R="$F/root"
	mkdir -p "$R/etc/systemd/system" "$R/opt/chimera/state" "$R/opt/chimera/bin"
	: >"$F/spur"
	printf 'systemd-journal\n' >"$F/gruppen"
	printf 'wirkt\n' >"$F/onfailure"
	printf '#!/bin/sh\nexit 0\n' >"$R/opt/chimera/bin/chimera-tor"
	chmod 755 "$R/opt/chimera/bin/chimera-tor"
}

lauf() {
	(
		set +e
		CHIMERA_ROOT="$R"; export CHIMERA_ROOT
		CHIMERA_MANIFEST="$R/opt/chimera/state/manifest.tsv"
		CHIMERA_LOG_DIR="$R/logs"; CHIMERA_LOGFILE=""
		CHIMERA_MODE="${MODUS:-run}"; CHIMERA_STEP=27-mojo
		. "$HERE/lib/common.sh"
		. "$HERE/lib/manifest.sh"
		. "$HERE/lib/service.sh"
		. "$LIB"

		systemctl() {
			printf 'systemctl %s\n' "$*" >>"$F/spur"
			case "$1" in
				is-enabled) [ ! -e "$F/aus" ] ;;
				is-active)  [ ! -e "$F/aus" ] ;;
				cat)        [ ! -e "$F/ohne-${2:-}" ] ;;
				show)
					# systemctl show <unit> -p OnFailure --value. Eine Unit, die es nicht
					# gibt, hat keinen OnFailure-Eintrag (wie bei echtem systemd).
					if [ -e "$F/ohne-${2:-}" ]; then
						printf '\n'
					elif [ "$(cat "$F/onfailure")" = wirkt ]; then
						printf 'chimera-mojo@%s.service\n' "$2"
					else
						printf '\n'
					fi ;;
				*)          return 0 ;;
			esac
		}
		getent() { [ "$1" = group ] && grep -qx "$2" "$F/gruppen"; }
		id() { echo 0; }

		"$@" >"$F/aus-text" 2>&1
		echo $? >"$F/rc"
	)
}

U="etc/systemd/system"

# --- 1. Erstlauf ----------------------------------------------------------
feld erst
lauf mojo_einrichten
check "Erstlauf rc 0" "$(cat "$F/rc")" 0
for d in chimera.service chimera-tor.service chimera-hardware.service; do
	hat "Drop-in fuer $d: OnFailure auf die Meldeunit mit dem Namen des Dienstes (%N, nicht %n)" "$R/$U/$d.d/10-mojo.conf" "OnFailure=chimera-mojo@%N.service"
done
hat_nicht "Drop-ins: nie %n (haengt am Pi ein zweites .service an)" "$R/$U/chimera.service.d/10-mojo.conf" "@%n."
hat "Zeitgeber: nach dem Boot" "$R/$U/chimera-mojo.timer" "OnBootSec=3min"
hat "Zeitgeber: stuendlich" "$R/$U/chimera-mojo.timer" "OnUnitActiveSec=1h"
hat "Zeitgeber: startet den Lauf" "$R/$U/chimera-mojo.timer" "Unit=chimera-mojo.service"
hat "Zeitgeber: wird von timers.target gezogen" "$R/$U/chimera-mojo.timer" "WantedBy=timers.target"
hat "Zeitgeber eingeschaltet" "$F/spur" "systemctl enable --now chimera-mojo.timer"
hat "Zeitgeber im Manifest" "$R/opt/chimera/state/manifest.tsv" "dienst	chimera-mojo.timer	aktiviert"
hat "Datei im Manifest: Meldeunit" "$R/opt/chimera/state/manifest.tsv" "datei	$R/etc/systemd/system/chimera-mojo@.service"
hat "Datei im Manifest: Drop-in" "$R/opt/chimera/state/manifest.tsv" "datei	$R/etc/systemd/system/chimera.service.d/10-mojo.conf"
hat "daemon-reload nach neuen Units" "$F/spur" "systemctl daemon-reload"

# --- 2. Lauf-Unit ---------------------------------------------------------
L="$R/$U/chimera-mojo.service"
hat "Lauf: ruft mojo mit --fix" "$L" "ExecStart=/opt/chimera/bin/chimera-tor --mojo --fix"
hat "Lauf: legt den Bericht auf die Karte (state/)" "$L" "--datei /opt/chimera/state/mojo-letzter.json"
hat "Lauf: Warnung (Exitcode 1) ist kein Scheitern" "$L" "SuccessExitStatus=1"
hat "Lauf: Fehler (Exitcode 2) laesst die Unit scheitern" "$L" "Type=oneshot"
hat "Lauf: liest das Journal ueber die Gruppe" "$L" "SupplementaryGroups=systemd-journal"
hat "Lauf: Wurzel read-only" "$L" "ProtectSystem=strict"
# Der Kartenpfad kommt aus common.sh (CHIMERA_LOGS_PRODUCTIVE), nicht aus diesem Test.
KARTE="$(CHIMERA_ROOT="$W" sh -c '. "$1/lib/common.sh"; printf %s "$CHIMERA_LOGS_PRODUCTIVE"' _ "$HERE")"
[ -n "$KARTE" ] && ok "Kartenpfad aus common.sh gelesen" || bad "Kartenpfad aus common.sh gelesen -- leer"
hat "Lauf: schreibt nur nach state/ und ins Kartenprotokoll" "$L" "ReadWritePaths=/opt/chimera/state -$KARTE"
hat "Lauf: kennt den Kartenpfad fuer die Pruefung" "$L" "Environment=CHIMERA_LOG_KARTE=$KARTE"
hat "Lauf: kennt die requirements.txt" "$L" "Environment=CHIMERA_REQUIREMENTS=/opt/chimera/source/requirements.txt"
hat "Lauf: sieht /home (sonst falscher Alarm der Kartenpruefung)" "$L" "ProtectHome=read-only"
hat_nicht "Lauf: nicht ProtectHome=yes" "$L" "ProtectHome=yes"
hat_nicht "Lauf: nicht als Agent-Nutzer" "$L" "User=chimera"
hat "Lauf: kein Neustart der eigenen Rechte" "$L" "NoNewPrivileges=yes"
hat "Lauf: genug Zeit fuer das Nachladen von Python-Paketen" "$L" "TimeoutStartSec=900"

# --- 3. Meldeunit trennt Zwischenfehler von der Aufgabe -------------------
M="$R/$U/chimera-mojo@.service"
hat "Meldung: fragt den Zustand des Dienstes" "$M" "systemctl show \"%i\" -p ActiveState --value"
hat "Meldung: nur bei failed laut (Aufgabe)" "$M" "= failed"
hat "Meldung: Aufgabe startet den Mojo-Lauf" "$M" "systemctl start --no-block chimera-mojo.service"
hat "Meldung: Zwischenfehler wird nur protokolliert" "$M" "Zwischenfehler"
hat "Meldung: nennt Ergebnis und Status" "$M" "MONITOR_SERVICE_RESULT"
hat "Meldung: liest das Journal ueber die Gruppe" "$M" "SupplementaryGroups=systemd-journal"

# --- 4. Zweitlauf ---------------------------------------------------------
: >"$F/spur"
lauf mojo_einrichten
check "Zweitlauf rc 0" "$(cat "$F/rc")" 0
hat_nicht "Zweitlauf schaltet nicht erneut ein" "$F/spur" "enable --now"
check "Manifest: Zeitgeber genau einmal" "$(grep -c 'dienst	chimera-mojo.timer' "$R/opt/chimera/state/manifest.tsv")" 1
check "Manifest: Drop-in genau einmal" "$(grep -c 'chimera.service.d/10-mojo.conf' "$R/opt/chimera/state/manifest.tsv")" 1

# --- 5. Von Hand abgeschalteter Zeitgeber ---------------------------------
: >"$F/aus"
: >"$F/spur"
lauf mojo_einrichten
hat "Zeitgeber aus trotz Manifest: wird wieder eingeschaltet" "$F/spur" "enable --now chimera-mojo.timer"
rm -f "$F/aus"

# --- 6. Trockenlauf -------------------------------------------------------
feld trocken
MODUS=dry lauf mojo_einrichten
check "Trockenlauf rc 0" "$(cat "$F/rc")" 0
check "Trockenlauf schreibt keine Unit" "$(ls "$R/$U" | wc -l | tr -d ' ')" 0
check "Trockenlauf schreibt kein Drop-in" "$(find "$R/$U" -name '*.d' | wc -l | tr -d ' ')" 0
# Ohne Manifest-Datei gilt "nichts eingetragen"; mit Datei darf keine Zeile von Mojo drinstehen.
if [ -f "$R/opt/chimera/state/manifest.tsv" ]; then
	check "Trockenlauf schreibt nichts ins Manifest" "$(grep -c mojo "$R/opt/chimera/state/manifest.tsv" || true)" 0
else
	ok "Trockenlauf legt kein Manifest an"
fi
check "Trockenlauf rueckt systemctl nicht an" "$(wc -l <"$F/spur" | tr -d ' ')" 0
unset MODUS

# --- 7. Voraussetzungen ---------------------------------------------------
feld ohne-binary
rm -f "$R/opt/chimera/bin/chimera-tor"
lauf mojo_einrichten
check "ohne Binary: rc 1 (Befund)" "$(cat "$F/rc")" 1
check "ohne Binary: nichts geschrieben" "$(ls "$R/$U" | wc -l | tr -d ' ')" 0
feld ohne-gruppe
: >"$F/gruppen"
lauf mojo_einrichten
check "ohne Journal-Gruppe: rc 2 (Abbruch)" "$(cat "$F/rc")" 2
hat "ohne Journal-Gruppe: sagt warum" "$F/aus-text" "Journal"

# --- 8. Nachweis: Drop-in wirkt nicht -------------------------------------
feld wirkt-nicht
printf 'nein\n' >"$F/onfailure"
lauf mojo_einrichten
check "Drop-in wirkt nicht: rc 1 (Befund, nicht stiller Erfolg)" "$(cat "$F/rc")" 1
hat "Drop-in wirkt nicht: benennt den Dienst" "$F/aus-text" "wirkt NICHT"

# --- 9. Fehlende Dienst-Unit (z. B. ohne Hardware-Dienst) -----------------
feld ohne-hw
: >"$F/ohne-chimera-hardware.service"
lauf mojo_einrichten
check "ohne Hardware-Unit: rc 0 (wird uebersprungen, nicht gemeldet)" "$(cat "$F/rc")" 0
hat_nicht "ohne Hardware-Unit: keine Warnung ueber sie" "$F/aus-text" "chimera-hardware.service (systemd meldet"
# Gegenstueck: eine vorhandene Unit ohne wirksames Drop-in ist ein Befund.
feld hw-ohne-wirkung
printf 'nein\n' >"$F/onfailure"
lauf mojo_einrichten
check "mit Hardware-Unit, Drop-in wirkungslos: rc 1" "$(cat "$F/rc")" 1

# --- 10. Rueckbau ---------------------------------------------------------
feld rueck
lauf mojo_einrichten
: >"$F/spur"
lauf mojo_rueckbau
check "Rueckbau rc 0" "$(cat "$F/rc")" 0
hat "Rueckbau schaltet den Zeitgeber ab" "$F/spur" "disable --now chimera-mojo.timer"
for d in chimera-mojo.service chimera-mojo@.service chimera-mojo.timer; do
	[ ! -e "$R/$U/$d" ] && ok "Rueckbau entfernt $d" || bad "Rueckbau entfernt $d -- blieb stehen"
done
[ ! -e "$R/$U/chimera.service.d/10-mojo.conf" ] && ok "Rueckbau entfernt das Drop-in" || bad "Rueckbau entfernt das Drop-in -- blieb stehen"
[ ! -d "$R/$U/chimera.service.d" ] && ok "Rueckbau entfernt das leere Drop-in-Verzeichnis" || bad "Rueckbau entfernt das leere Drop-in-Verzeichnis -- blieb stehen"
# Fremdes Drop-in im selben Verzeichnis bleibt (Regel "Was nicht im Manifest steht, gehoert nicht uns").
feld fremd
lauf mojo_einrichten
printf '[Service]\nNice=5\n' >"$R/$U/chimera.service.d/50-eigenes.conf"
lauf mojo_rueckbau
[ -f "$R/$U/chimera.service.d/50-eigenes.conf" ] && ok "Rueckbau laesst ein fremdes Drop-in stehen" || bad "Rueckbau laesst ein fremdes Drop-in stehen -- wurde geloescht"

printf '\nErgebnis: %s ok, %s fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
