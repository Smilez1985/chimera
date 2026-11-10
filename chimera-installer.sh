#!/bin/sh
# Chimera -- Installer, Einstieg fuer den Nutzer.
#
# Die eine Datei, die man aufruft (DESIGN, Regel "Installerhelfer"): aus dem
# geklonten Repo oder aus einem entpackten Zip, auf dem Geraet.
#
#   sudo sh chimera-installer.sh              installieren oder aktualisieren
#   sudo sh chimera-installer.sh --dry-run    nur berichten, nichts aendern
#   sh chimera-installer.sh --help            alle Optionen
#
# Sie reicht nur weiter: Die Arbeit macht installer/chimera-install, mit
# denselben Optionen und demselben Exitcode. Hier steht deshalb keine Option
# und keine Pruefung ein zweites Mal -- zwei Stellen fuer dieselbe Logik
# laufen auseinander (DESIGN Regel 10g).
#
# Vorbild: setup.sh in rag4ll und install.sh in llmcf -- ein sichtbarer
# Einstieg in der Wurzel des Repos.

set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALLER="$HERE/installer/chimera-install"

if [ ! -f "$INSTALLER" ]; then
	printf 'FEHLER: %s fehlt.\n' "$INSTALLER" >&2
	printf '  chimera-installer.sh gehoert in die Wurzel des Chimera-Repos\n' >&2
	printf '  (Klon oder entpacktes Zip) und wird von dort aufgerufen.\n' >&2
	exit 2
fi

# Der Hinweis "mit sudo neu starten" soll diese Datei nennen, nicht die
# innere (installer/chimera-install liest CHIMERA_EINSTIEG).
CHIMERA_EINSTIEG="$HERE/chimera-installer.sh"
export CHIMERA_EINSTIEG

exec sh "$INSTALLER" "$@"
