#!/bin/sh
# Dienstprotokolle aus dem Arbeitsspeicher auf den Datentraeger bringen
# (DESIGN Regel 10r). Der EINE Weg dafuer: log_sync und log_rotate aus
# lib/common.sh -- kein zweiter Mechanismus.
#
# Aufrufer:
#   ExecStopPost= der Dienst-Unit   log-abgleich.sh           (sofort)
#   chimera-logabgleich.timer       log-abgleich.sh --ruhig   (Ruhezeit)
#
# --ruhig: nur abgleichen, wenn seit CHIMERA_LOG_RUHE Sekunden (120) keine
# Datei im RAM-Ordner geschrieben wurde -- ODER die Karte aelter ist als
# CHIMERA_LOG_SPAETESTENS (3600). Ohne die zweite Bedingung erreichte ein
# ununterbrochen schreibender Dienst die Karte nie, und ein Stromausfall
# naehme alles mit.
#
# Umgebung (von der Unit gesetzt):
#   CHIMERA_LOG_RAM    Quelle  (/run/chimera/logs/productive)
#   CHIMERA_LOG_KARTE  Ziel    (/home/<nutzer>/chimera/logs/productive)
#
# Exitcode: 0 abgeglichen oder nichts zu tun, 1 Befund (Kopie misslang).
# Der Aufrufer (ExecStopPost) wertet ihn nicht als Dienstfehler.

set -u

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"

: "${CHIMERA_LOG_RUHE:=120}"
: "${CHIMERA_LOG_SPAETESTENS:=3600}"

QUELLE="${CHIMERA_LOG_RAM:-}"
ZIEL="${CHIMERA_LOG_KARTE:-}"
if [ -z "$QUELLE" ] || [ -z "$ZIEL" ]; then
	echo "log-abgleich: CHIMERA_LOG_RAM und CHIMERA_LOG_KARTE noetig." >&2
	exit 1
fi
[ -d "$QUELLE" ] || exit 0

# Juengste bzw. aelteste Aenderung (Epoche) unter den *.log eines Ordners;
# 0 wenn keine.
juengste() {
	_j=0
	for _f in "$1"/*.log; do
		[ -f "$_f" ] || continue
		_m="$(stat -c %Y "$_f" 2>/dev/null || echo 0)"
		[ "$_m" -gt "$_j" ] && _j="$_m"
	done
	echo "$_j"
}
aelteste() {
	_a=0
	for _f in "$1"/*.log; do
		[ -f "$_f" ] || continue
		_m="$(stat -c %Y "$_f" 2>/dev/null || echo 0)"
		{ [ "$_a" -eq 0 ] || [ "$_m" -lt "$_a" ]; } && _a="$_m"
	done
	echo "$_a"
}

if [ "${1:-}" = "--ruhig" ]; then
	_jetzt="$(date +%s)"
	_ram="$(juengste "$QUELLE")"
	_karte="$(juengste "$ZIEL")"
	[ "$_ram" -eq 0 ] && exit 0
	# Karte schon auf diesem Stand? Dann nichts tun (log_sync vergleicht
	# zwar selbst per cmp, aber so faellt auch das Lesen weg).
	[ "$_karte" -ge "$_ram" ] && exit 0
	# Noch nie abgeglichen: Bezug ist der aelteste Stand im RAM (etwa der
	# Dienststart), nicht die Epoche 0 -- sonst galte "seit einer Stunde
	# nicht abgeglichen" schon in der ersten Sekunde.
	[ "$_karte" -eq 0 ] && _karte="$(aelteste "$QUELLE")"
	if [ $((_jetzt - _ram)) -lt "$CHIMERA_LOG_RUHE" ] &&
	   [ $((_jetzt - _karte)) -lt "$CHIMERA_LOG_SPAETESTENS" ]; then
		exit 0
	fi
fi

CHIMERA_LOG_DIR="$QUELLE"
CHIMERA_LOG_ZIEL="$ZIEL"
_rc=0
log_sync || _rc=1
log_rotate
exit "$_rc"
