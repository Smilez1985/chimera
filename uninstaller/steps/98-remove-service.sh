#!/bin/sh
# Gegenstueck zu installer/steps/98-service.sh (Architekturregel 10l).
#
# Was Schritt 98 hinterlaesst, steht im Manifest:
#   dienst  chimera.service (aktiviert)
#   datei   /etc/systemd/system/chimera.service, /var/lib/chimera/dienst-stand
#   nutzer  chimera (neu | vorher_da)
# Ein Nutzer mit `vorher_da` bleibt. Nutzerdaten bleiben immer.
# Die Logik steht in installer/lib/service.sh (service_rueckbau).
#
# Exitcode: 0 in Ordnung, 1 Befund.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/manifest.sh"
. "$_HERE/installer/lib/service.sh"

CHIMERA_STEP="98-remove-service"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-service" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Dienst (systemd-Unit und Dienstnutzer)"

set +e
service_rueckbau
rc=$?
set -e
log_close "$rc"
exit "$rc"
