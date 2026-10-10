#!/bin/sh
# Chimera installer -- Modul 98: Dienst (Dienstnutzer + systemd-Unit).
#
# Letzter Schritt: Er braucht das venv aus Schritt 50 und die .env, und
# er startet das Ganze. Die Logik steht in lib/service.sh (pruefbar ohne
# systemd), hier wird nur aufgerufen. Begruendung: docs/INSTALLER.md 4c.
#
# Exitcode:
#   0  Dienst laeuft nachweislich (aktiv nach Wartezeit, keine Neustarts)
#   1  Befund: eingerichtet, aber nicht nachweislich laufend
#   2  abgebrochen -- Voraussetzung fehlt

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/service.sh"

CHIMERA_STEP="98-service"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "service" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

REPO="$(cd "$_HERE/.." && pwd)"
# Zielpfad (ohne CHIMERA_ROOT) -- systemd liest ihn am Ziel.
VENV_PY=/opt/chimera/venv/bin/python

log "Chimera Dienst"
log ""

if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "Dieses Modul legt einen Systemnutzer und eine systemd-Unit an --"
	err "das geht nur als Verwalter."
	err "  sudo sh $0"
	log_close 2; exit 2
fi

if ! is_dry_run && [ ! -x "$(rootpath "$VENV_PY")" ]; then
	err "venv fehlt ($VENV_PY) -- Schritt 50 zuerst."
	log_close 2; exit 2
fi

set +e
service_einrichten "$VENV_PY" "$REPO"
rc=$?
set -e

log ""
case "$rc" in
	0) log "Ergebnis: Dienst laeuft nachweislich." ;;
	1) warn "Ergebnis: Dienst eingerichtet, laeuft aber nicht nachweislich." ;;
	*) err "Ergebnis: abgebrochen." ;;
esac
log_close "$rc"
exit "$rc"
