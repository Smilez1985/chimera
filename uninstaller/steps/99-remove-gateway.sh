#!/bin/sh
# Gegenstueck zu installer/steps/99-gateway.sh (Architekturregel 10l).
#
# Was Schritt 99 hinterlaesst, steht im Manifest (Modul 99-gateway):
#   dienst  chimera-tor.socket (aktiviert)
#   datei   /etc/systemd/system/chimera-tor.{socket,service}
#   nutzer  chimera-tor (neu | vorher_da)
# Ein Nutzer mit `vorher_da` bleibt. Die Logik steht in
# installer/lib/gateway.sh (gateway_rueckbau).
#
# Exitcode: 0 in Ordnung, 1 Befund.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/manifest.sh"
. "$_HERE/installer/lib/service.sh"
. "$_HERE/installer/lib/gateway.sh"

CHIMERA_STEP="99-remove-gateway"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-gateway" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Gateway (systemd-Units und Nutzer)"

set +e
gateway_rueckbau
rc=$?
set -e
log_close "$rc"
exit "$rc"
