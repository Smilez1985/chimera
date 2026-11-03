#!/bin/sh
# Gegenstueck zu installer/steps/27-mojo.sh (Regel "Jeder Installationsschritt hat sein Gegenstueck").
#
# Was Schritt 27 hinterlaesst, steht im Manifest:
#   dienst  chimera-mojo.timer (aktiviert)
#   dienst  chimera-mojo-fortsetzung.service (aktiviert, laeuft nur mit Marker)
#   datei   /etc/systemd/system/chimera-mojo{.service,.timer,@.service}
#   datei   /etc/systemd/system/chimera-mojo-fortsetzung.service
#   datei   /etc/systemd/system/<dienst>.service.d/10-mojo.conf
#
# Exitcode: 0 in Ordnung, 1 Befund.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/manifest.sh"
. "$_HERE/installer/lib/service.sh"
. "$_HERE/installer/lib/mojo.sh"

CHIMERA_STEP="27-remove-mojo"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-mojo" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Mojo (Meldeunit, Zeitgeber, Drop-ins)"

set +e
mojo_rueckbau
rc=$?
set -e
log_close "$rc"
exit "$rc"
