#!/bin/sh
# Chimera Uninstaller -- Modul 99-sohelper: Ausfuehrer zurueckbauen.
#
# DESIGN Regel 10l (Rueckbau-Gegenstueck). Entfernt, was Schritt 99-sohelper
# angelegt hat: Socket und Dienst, die Units, das Binary (steht im Manifest als
# Datei dieses Schritts), den Arbeitsordner (nur wenn leer) und den Nutzer
# chimera-sohelper (nur wenn der Installer ihn anlegte).
#
# Nicht angefasst: /opt/chimera/state/manifest.tsv (gehoert dem Rueckbau
# selbst) und der Elternordner /opt/chimera -- den nimmt der letzte Schritt.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/network.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/service.sh"
. "$_HERE/lib/sohelper.sh"

CHIMERA_STEP="99-sohelper"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "uninstall-sohelper" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Rueckbau: Ausfuehrer (chimera-sohelper)"
log ""

set +e
sohelper_rueckbau
rc=$?
set -e

log ""
case "$rc" in
	0) log "Ergebnis: rueckstandsfrei entfernt." ;;
	*) warn "Ergebnis: Befund -- siehe Meldungen oben." ;;
esac
log_close "$rc"
exit "$rc"
