#!/bin/sh
# Gegenstueck zu installer/steps/25-speicher.sh (Architekturregel 10l).
#
# Was Schritt 25 hinterlaesst, steht im Manifest:
#   swapdatei  <pfad>  vorher:<groesse>:<ort>   Ausgangszustand von DietPi
#   sicherung  /etc/default/zramswap.chimera-*  Original der zram-Konfig
#   paket      zram-tools (neu | vorher_da)      -> Rueckbau 20
# Zurueckgestellt wird mit demselben Werkzeug (dietpi-set_swapfile), damit
# fstab und dietpi.txt stimmen. Die Sicherung bleibt liegen.
#
# Exitcode: 0 in Ordnung, 1 Befund.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/manifest.sh"
. "$_HERE/installer/lib/speicher.sh"

CHIMERA_STEP="25-remove-speicher"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-speicher" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Speicher (zram-Konfiguration und Auslagerungsdatei)"

set +e
speicher_rueckbau 25-speicher
rc=$?
set -e
log_close "$rc"
exit "$rc"
