#!/bin/sh
# Chimera installer -- Modul 25: Speicher (zram + Auslagerungsdatei).
#
# DESIGN Regel 5e. Nach den Paketen (20), vor allem, was Speicher braucht
# (Treiberbau 40, venv 50, Dienst 98). Logik in lib/speicher.sh, pruefbar
# ohne Hardware; Mechanik aus PiPortal uebernommen (zram-tools +
# dietpi-set_swapfile).
#
# Exitcode:
#   0  zram und Datei in Sollgroesse aktiv, zram vor der Datei
#   1  Befund (z. B. zu wenig Platz, kein DietPi) -- Lauf geht weiter
#   2  Abbruch (fremde zram-Verwaltung, Messung unmoeglich)

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/network.sh"
. "$_HERE/lib/speicher.sh"

CHIMERA_STEP="25-speicher"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "speicher" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Chimera Speicher (zram + Auslagerungsdatei)"
log ""

if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "Auslagerung einrichten geht nur als Verwalter."
	err "  sudo sh $0"
	log_close 2; exit 2
fi

set +e
speicher_einrichten
rc=$?
set -e

log ""
case "$rc" in
	0) log "Ergebnis: Auslagerung steht." ;;
	1) warn "Ergebnis: Auslagerung nicht vollstaendig -- siehe oben." ;;
	*) err "Ergebnis: abgebrochen." ;;
esac
log_close "$rc"
exit "$rc"
