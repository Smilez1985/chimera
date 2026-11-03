#!/bin/sh
# abgleich.sh -- Wurde der Stand, der im Repo liegt, auch WIRKLICH eingespielt?
#
# Anlass (4.11.2026): Die Aenderungen vom 3.11. lagen nur per `scp` in
# /opt/chimera/productive/code. `/opt/chimera/source` stand auf einem alten
# Commit. Beim naechsten Start kopierte der Hardware-Abgleich `source` ueber
# `productive` -- und rollte damit vier Commits zurueck, ohne dass es jemand
# merkte. Der Dienst lief, die Tests waren gruen, nur der Code war alt.
#
# Dieses Werkzeug vergleicht drei Dinge:
#   1. den Quellbaum (/opt/chimera/source) mit dem eingespielten Stand
#      (/opt/chimera/productive/code)
#   2. den festgehaltenen Commit (/opt/chimera/state/quelle-commit) mit dem
#      Commit, den der Quellbaum selbst nennt (er hat kein .git, also mit
#      dem, was der Aufrufer erwartet: --erwartet <commit>)
#   3. optional: den Arbeitsbaum des Repos gegen den Quellbaum
#
# Aufruf (auf dem Geraet, als root lesbar oder mit sudo):
#   sh abgleich.sh                          Quellbaum gegen produktiv
#   sh abgleich.sh --erwartet $(git rev-parse --short HEAD)
#   sh abgleich.sh --repo /pfad/zum/klon    Klon gegen Quellbaum
#
# Exitcode: 0 gleich, 1 Unterschied (mit Fundstelle), 2 Aufruffehler.

set -u

QUELLE=/opt/chimera/source
ZIEL=/opt/chimera/productive/code
STATE=/opt/chimera/state/quelle-commit
ERWARTET=""
REPO=""

while [ $# -gt 0 ]; do
	case "$1" in
	--erwartet) ERWARTET="${2:-}"; shift 2 ;;
	--repo)     REPO="${2:-}"; shift 2 ;;
	--quelle)   QUELLE="${2:-}"; shift 2 ;;
	--ziel)     ZIEL="${2:-}"; shift 2 ;;
	-h|--help)  sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
	*) echo "unbekannte Option: $1" >&2; exit 2 ;;
	esac
done

lesen() { [ -r "$1" ] && cat "$1" || { sudo -n cat "$1" 2>/dev/null; }; }

FEHLER=0
sag()   { printf '%s\n' "$*"; }
befund() { printf 'ABWEICHUNG: %s\n' "$*"; FEHLER=1; }

[ -d "$QUELLE" ] || { echo "FEHLER: Quellbaum $QUELLE fehlt" >&2; exit 2; }
[ -d "$ZIEL" ]   || { echo "FEHLER: eingespielter Stand $ZIEL fehlt" >&2; exit 2; }

# --- 1. Quellbaum gegen eingespielten Stand --------------------------------
# __pycache__ und .git zaehlen nicht: das eine entsteht beim Laufen, das
# andere hat der Installer bewusst nicht kopiert.
DIFF="$(diff -r -q \
	-x '__pycache__' -x '.git' -x '*.pyc' -x '.testtmp' \
	"$QUELLE" "$ZIEL" 2>&1)"
if [ -n "$DIFF" ]; then
	while IFS= read -r zeile; do befund "Quelle/Produktiv: $zeile"; done <<EOF
$DIFF
EOF
else
	sag "Quellbaum und eingespielter Stand sind gleich."
fi

# --- 2. Commit, der im Zustand steht --------------------------------------
IST="$(lesen "$STATE" 2>/dev/null | tr -d '[:space:]')"
if [ -n "$ERWARTET" ]; then
	if [ "$IST" = "$ERWARTET" ]; then
		sag "Commit im Zustand: $IST (wie erwartet)"
	else
		befund "Commit im Zustand ist '${IST:-?}', erwartet '$ERWARTET'"
	fi
else
	sag "Commit im Zustand: ${IST:-?} (kein --erwartet angegeben, nicht verglichen)"
fi

# --- 3. optional: Arbeitsbaum des Repos gegen den Quellbaum ---------------
if [ -n "$REPO" ]; then
	[ -d "$REPO" ] || { echo "FEHLER: Repo $REPO fehlt" >&2; exit 2; }
	D2="$(diff -r -q \
		-x '__pycache__' -x '.git' -x '*.pyc' -x '.testtmp' \
		"$REPO" "$QUELLE" 2>&1)"
	if [ -n "$D2" ]; then
		while IFS= read -r zeile; do befund "Repo/Quelle: $zeile"; done <<EOF
$D2
EOF
	else
		sag "Arbeitsbaum und Quellbaum sind gleich."
	fi
fi

if [ "$FEHLER" -eq 0 ]; then
	sag "Ergebnis: der eingespielte Stand entspricht der Quelle."
fi
exit "$FEHLER"
