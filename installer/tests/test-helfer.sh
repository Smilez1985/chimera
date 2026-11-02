#!/bin/sh
# Tests fuer lib/helfer.sh -- abgekoppelter Installerhelfer und die Klammer um
# den Lauf (DESIGN, Regel "Installerhelfer").
#
# Geprueft wird die echte Bibliothek; `systemctl` und `systemd-run` stehen als
# SHELL-FUNKTIONEN bereit. Ob systemd die transiente Unit wirklich annimmt,
# prueft der Geraetetest am Pi, nicht dieser Test.
#
# CHIMERA_HELFER_LIB ueberstimmt die Bibliothek (counter-check-helfer.sh).

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="${CHIMERA_HELFER_LIB:-$HERE/lib/helfer.sh}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-helfer.XXXXXX" 2>/dev/null)" || W=""
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
	else bad "$1 -- '$3' fehlt in $2"; fi
}
hat_nicht() {
	if grep -qF -- "$3" "$2" 2>/dev/null; then bad "$1 -- '$3' kam vor"
	else ok "$1"; fi
}

printf '=== Installerhelfer und Klammer (lib/helfer.sh) ===\n'

feld() {
	F="$W/$1"
	mkdir -p "$F"
	: >"$F/spur"
	: >"$F/lauf"           # welche Einheiten laufen?
	: >"$F/startfehler"    # Einheiten, deren Start scheitert
	: >"$F/still"          # Einheiten, deren Start "gelingt", die aber nicht laufen
	printf '42\n' >"$F/rc"   # Exitcode, den die Unit meldet (0 bis 255)
}

lauf() {
	(
		set +e
		mkdir -p "$F/run"
		CHIMERA_MODE="${MODUS:-run}"; CHIMERA_STEP=27-mojo
		. "$HERE/lib/common.sh"
		. "$LIB"
		# nach common.sh: es setzt CHIMERA_RUNLOG auf seinen eigenen Vorgabewert
		CHIMERA_RUNLOG="$F/run"; CHIMERA_LOG_DIR="$F/run"
		CHIMERA_OPT="$F/opt"; CHIMERA_TOR_SOCKET="$F/tor.sock"
		CHIMERA_HELFER_STATUS="$F/zettel.status"

		systemd-run() {
			printf 'systemd-run %s\n' "$*" >>"$F/spur"
			# Wie der echte Helfer: Laufzettel schreiben (er sagt, wie es ausging).
			printf 'zustand=fertig\npid=\nrc=%s\nstart=0\nende=0\n' "$(cat "$F/rc")" \
				>"$CHIMERA_HELFER_STATUS"
			# Argumente der Unit festhalten, um sie im Test zu pruefen.
			printf '%s\n' "$*" >"$F/unit-args"
			return "${SR_RC:-0}"
		}
		systemctl() {
			printf 'systemctl %s\n' "$*" >>"$F/spur"
			case "$1 ${2:-}" in
				"is-active --quiet")
					# is-active --quiet UNIT. Mit "$F/ende-nach" endet der Lauf
					# nach so vielen Abfragen (sonst liefe das Anhaengen ewig).
					if [ -f "$F/ende-nach" ]; then
						_n=$(( $(cat "$F/ende-nach") - 1 ))
						if [ "$_n" -le 0 ]; then
							rm -f "$F/ende-nach"
							grep -vx "$3" "$F/lauf" >"$F/l2" || true
							mv "$F/l2" "$F/lauf"
						else
							printf '%s\n' "$_n" >"$F/ende-nach"
						fi
					fi
					grep -qx "$3" "$F/lauf"
					return $? ;;
				"is-active $2") grep -qx "$2" "$F/lauf" && echo active || echo inactive ;;
				"stop $2")
					grep -vx "$2" "$F/lauf" >"$F/l2" || true; mv "$F/l2" "$F/lauf" ;;
				"start $2"|"start --no-block")
					_u="${2#--no-block }"; [ "$2" = "--no-block" ] && _u="$3"
					grep -qx "$_u" "$F/startfehler" && return 1
					grep -qx "$_u" "$F/still" && return 0
					echo "$_u" >>"$F/lauf" ;;
				"is-active --quiet") : ;;
				"reset-failed $2") : ;;
				"show $2") cat "$F/rc" ;;
				*)
					# show ... -p ExecMainStatus --value
					case "$*" in *ExecMainStatus*) cat "$F/rc" ;; *) : ;; esac ;;
			esac
			return 0
		}
		# Im Test gelten systemctl und systemd-run als vorhanden (siehe oben).
		have_cmd() { :; }

		"$@" >"$F/aus" 2>&1
		echo $? >"$F/rc-aus"
	)
}

# --- 1. Abkoppeln ---------------------------------------------------------
feld start
SR_RC=0 lauf helfer_starten /pfad/chimera-install --only 99
check "Helfer: Exitcode des Laufs kommt an (42)" "$(cat "$F/rc-aus")" "42"
check "Helfer: systemd-run benutzt" "$(grep -c '^systemd-run' "$F/spur")" 1
hat "Helfer: eigener Unit-Name" "$F/unit-args" "--unit=chimera-installhelper"
hat "Helfer: transient, wird nach dem Lauf entfernt" "$F/unit-args" "--collect"
hat "Helfer: als oneshot (Exitcode kommt an)" "$F/unit-args" "--service-type=oneshot"
hat "Helfer: Schalter fuer den Helfer selbst" "$F/unit-args" "CHIMERA_HELFER=1"
hat "Helfer: Umgebung ueber eine Datei, nicht ueber die Befehlszeile" "$F/unit-args" "CHIMERA_HELFER_ENV="
hat "Helfer: --helfer mit den Argumenten" "$F/unit-args" "--helfer --only 99"
hat_nicht "Helfer: kein Passwort auf der Befehlszeile" "$F/unit-args" "CHIMERA_WEB_PASSWORT="

# --- 2. Zweiter Aufruf haengt sich an, startet nichts Neues --------------
feld doppelt
printf '3\n' >"$F/rc"
mkdir -p "$F/run"
# Ein Lauf ist im Gange: Laufzettel "laufend" mit lebender PID; nach 2 s endet er.
printf 'zustand=laufend\npid=%s\nrc=\nstart=0\nende=0\n' "$$" >"$F/zettel.status"
( sleep 2; printf 'zustand=fertig\npid=\nrc=3\nstart=0\nende=1\n' >"$F/zettel.status" ) &
SR_RC=0 lauf helfer_starten /pfad/chimera-install
check "Wiederaufruf: Exitcode des laufenden Laufs" "$(cat "$F/rc-aus")" 3
check "Wiederaufruf: kein zweiter systemd-run" "$(grep -c '^systemd-run' "$F/spur" || true)" 0
hat "Wiederaufruf: benannt" "$F/aus" "haenge mich an"

# --- 3. systemd-run scheitert --------------------------------------------
feld fehlstart
SR_RC=1 lauf helfer_starten /pfad/chimera-install
check "Start scheitert: rc 2" "$(cat "$F/rc-aus")" 2
hat "Start scheitert: benannt" "$F/aus" "startete nicht"

# --- 4. Umgebung: nur gesetzte Variablen, Modus 600 ----------------------
feld umgebung
MODUS=run lauf helfer_env_schreiben
_envd="$(ls /run/chimera-installhelfer.env 2>/dev/null || true)"
if [ -n "$_envd" ]; then
	check "Umgebungsdatei: Modus 600" "$(stat -c %a "$_envd")" 600
	rm -f "$_envd"
else
	check "Umgebungsdatei: angelegt" "fehlt" "angelegt"
fi

# --- 5. Klammer: anhalten in der richtigen Reihenfolge -------------------
feld klammer
printf 'chimera.service\nchimera-tor.service\nchimera-tor.socket\nchimera-sitzung.socket\nchimera-mojo.timer\n' >"$F/lauf"
	# Das Gateway-Programm fuer das Wecken: eine Attrappe, die Erfolg meldet.
	mkdir -p "$F/opt/bin"; printf '#!/bin/sh\nexit 0\n' >"$F/opt/bin/chimera-tor"; chmod 755 "$F/opt/bin/chimera-tor"
lauf klammer_an
check "Klammer an: rc 0" "$(cat "$F/rc-aus")" 0
check "Klammer an: nichts laeuft mehr" "$(grep -c . "$F/lauf" || true)" 0
# Reihenfolge: Timer und Sockets zuerst, die Dienste zuletzt.
check "Klammer an: Reihenfolge (Timer, Sockets, Dienste, Gateway)" \
	"$(grep '^systemctl stop' "$F/spur" | awk '{print $3}' | tr '\n' ' ')" \
	"chimera-mojo.timer chimera-tor.socket chimera-sitzung.socket chimera.service chimera-tor.service "
check "Klammer an: nicht laufende Einheiten werden nicht angefasst" \
	"$(grep -c 'stop chimera-logabgleich.timer' "$F/spur" || true)" 0

lauf klammer_aus
check "Klammer aus: rc 0" "$(cat "$F/rc-aus")" 0
check "Klammer aus: Reihenfolge (Sockets vor Diensten)" \
	"$(grep '^systemctl start' "$F/spur" | awk '{print $3}' | tr '\n' ' ')" \
	"chimera-tor.socket chimera-sitzung.socket chimera.service chimera-mojo.timer "
# Das Gateway wird NICHT direkt gestartet (socket-aktiviert), sondern geweckt.
hat_nicht "Klammer aus: Gateway nicht direkt gestartet" "$F/spur" "systemctl start chimera-tor.service"
check "Klammer aus: alles wieder aktiv" "$(sort "$F/lauf" | tr '\n' ' ')" \
	"chimera-mojo.timer chimera-sitzung.socket chimera-tor.socket chimera.service "

# --- 6. Klammer: Start scheitert -> Befund -------------------------------
feld klammerfehler
printf 'chimera.service\n' >"$F/lauf"
lauf klammer_an
printf 'chimera.service\n' >"$F/startfehler"
lauf klammer_aus
check "Klammer aus: Start scheitert -> rc 1" "$(cat "$F/rc-aus")" 1
hat "Klammer aus: benannt" "$F/aus" "laeuft nach dem Lauf nicht"

# --- 6b. Klammer: Start meldet Erfolg, Einheit laeuft nicht -> Nachweis faengt es
feld stumm
printf 'chimera.service\n' >"$F/lauf"
lauf klammer_an
printf 'chimera.service\n' >"$F/still"
lauf klammer_aus
check "Klammer aus: stummer Start -> rc 1" "$(cat "$F/rc-aus")" 1
hat "Klammer aus: Nachweis faengt stummen Start" "$F/aus" "laeuft nach dem Lauf nicht"

# --- 7b. Klammer nur, wenn sich etwas aendert (Idempotenz) ---------------
feld noetig
(
	set +e
	. "$HERE/lib/common.sh"
	. "$LIB"
	CHIMERA_STARTBAUM="$F/start"; CHIMERA_SOURCE="$F/source"
	CHIMERA_VENV="$F/venv"
	# Zwei Staende: der Kandidat (Pfad enthaelt "start") und source/.
	source_hash() {
		case "$1" in *start) cat "$F/hs" 2>/dev/null ;; *) cat "$F/hq" 2>/dev/null ;; esac
	}
	pydep_liste() { echo paket; }
	pydep_fehlend() { return "${PYDEP_RC:-0}"; }
	printf 'gleich\n' >"$F/hs"; printf 'gleich\n' >"$F/hq"
	klammer_noetig; echo "rc_nichts=$?" >>"$F/ergebnis"
	printf 'neu\n' >"$F/hs"
	klammer_noetig; echo "rc_neu=$?" >>"$F/ergebnis"
	PYDEP_RC=1 klammer_noetig; echo "rc_paket=$?" >>"$F/ergebnis"
) >/dev/null 2>&1
hat "Klammer noetig: nichts geaendert -> 1" "$F/ergebnis" "rc_nichts=1"
hat "Klammer noetig: neuer Quellstand -> 0" "$F/ergebnis" "rc_neu=0"
hat "Klammer noetig: fehlendes Paket -> 0" "$F/ergebnis" "rc_paket=0"

# --- 8. Umgebung wird im Helfer gelesen und entfernt ---------------------
feld lesen
printf 'CHIMERA_WEB_PASSWORT=geheim mit Leerzeichen\nCHIMERA_NUTZER=chimera\nFREMD=weg\n' >"$W/lesen.env"
chmod 600 "$W/lesen.env"
(
	set +e
	. "$HERE/lib/common.sh"
	. "$LIB"
	CHIMERA_HELFER_ENV="$W/lesen.env" helfer_env_lesen
	[ "${CHIMERA_WEB_PASSWORT:-}" = "geheim mit Leerzeichen" ] && echo ok >"$F/lese-ok" || echo nein >"$F/lese-ok"
	[ "${FREMD:-}" = "weg" ] && echo fremd-gesetzt >>"$F/lese-ok" || echo fremd-ignoriert >>"$F/lese-ok"
	[ -f "$W/lesen.env" ] && echo datei-bleibt >>"$F/lese-ok" || echo datei-weg >>"$F/lese-ok"
) >/dev/null 2>&1
hat "Umgebung: Wert mit Leerzeichen bleibt ganz" "$F/lese-ok" "ok"
hat "Umgebung: fremde Variable wird nicht uebernommen" "$F/lese-ok" "fremd-ignoriert"
hat "Umgebung: Datei wird danach geloescht" "$F/lese-ok" "datei-weg"

printf '\nErgebnis: %s ok, %s fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
