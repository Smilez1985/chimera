#!/bin/sh
# Chimera installer — Modul 20: Abhaengigkeiten.
#
# **Laeuft vor allem anderen.** Jedes spaetere Modul setzt voraus, dass
# sein Werkzeug da ist; wer das erst merkt, wenn er es braucht, scheitert
# mitten in der Arbeit. Beim ersten echten Lauf auf dem Pi passierte genau
# das: Modul 40 hatte Pakete nachgeladen, den Fremdinstaller gestartet, und
# der brach bei Schritt 3 von 8 ab -- `make` fehlte.
#
# Was hier installiert wird, wird **festgehalten** (lib/bestand.sh): mit
# der Unterscheidung, ob es vorher schon da war. Ein Paket, das es vor
# Chimera gab, darf eine Deinstallation nicht entfernen.
#
# Exitcode:
#   0  alles da
#   1  etwas Nicht-Zwingendes fehlt (wird benannt)
#   2  etwas Zwingendes fehlt und liess sich nicht holen

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/detect.sh"
. "$_HERE/lib/profiles.sh"
. "$_HERE/lib/netz.sh"
. "$_HERE/lib/bestand.sh"

CHIMERA_MODUL="20-pakete"; export CHIMERA_MODUL

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "pakete" || \
	warn "Kein Protokoll moeglich — Lauf wird nicht festgehalten."

BOARD="$(detect_board)"

log "Chimera Abhaengigkeiten"
log ""

# --- Was gebraucht wird ---------------------------------------------------
#
# Getrennt nach zwingend und nuetzlich. Ohne das Zwingende geht es nicht
# weiter; ohne das Nuetzliche laeuft Chimera, kann aber weniger -- und das
# wird gesagt, nicht verschwiegen.
#
# Je Zeile: Paket <Tab> Befehl-zum-Pruefen <Tab> wofuer
# Der Befehl ist der Nachweis: Ein Paket kann installiert sein und das
# Werkzeug trotzdem fehlen (Regel 10j).

zwingend() {
	cat <<'EOF'
git	command -v git	Quelltext holen
python3	command -v python3	Chimera selbst
make	command -v make	Treiberbau
gcc	command -v gcc	Treiberbau
device-tree-compiler	command -v dtc	Overlays uebersetzen
alsa-utils	command -v aplay	Audio pruefen und abspielen
EOF
}

nuetzlich() {
	cat <<'EOF'
python3-pil	python3 -c "import PIL"	Bilder zeichnen (Renderer)
python3-numpy	python3 -c "import numpy"	Umrechnung nach RGB565
i2c-tools	command -v i2cdetect	Busse von Hand pruefen
curl	command -v curl	Downloads mit Fortsetzen
sox	command -v sox	Toene pruefen
EOF
}

# --- Pruefen und holen ----------------------------------------------------

FEHLT_ZWINGEND=""
FEHLT_NUETZLICH=""

pruefen() {
	_pr_pkg="$1"; _pr_test="$2"; _pr_wofuer="$3"
	if sh -c "$_pr_test" >/dev/null 2>&1; then
		info "da:     $_pr_pkg  ($_pr_wofuer)"
		return 0
	fi
	info "fehlt:  $_pr_pkg  ($_pr_wofuer)"
	return 1
}

# Die Schleife laeuft in einer Subshell (Pipe) -- dort gesetzte Variablen
# sind draussen weg. Deshalb ueber eine Datei, die danach gelesen wird.
_FZ="${TMPDIR:-/tmp}/.chimera-fz.$$"
: >"$_FZ"
log "Zwingend"
zwingend | while IFS='	' read -r pkg test wofuer; do
	[ -n "$pkg" ] || continue
	pruefen "$pkg" "$test" "$wofuer" || printf '%s ' "$pkg" >>"$_FZ"
done
FEHLT_ZWINGEND="$(cat "$_FZ" 2>/dev/null || true)"
rm -f "$_FZ"

log ""
_FN="${TMPDIR:-/tmp}/.chimera-fn.$$"
: >"$_FN"
log "Nuetzlich"
nuetzlich | while IFS='	' read -r pkg test wofuer; do
	[ -n "$pkg" ] || continue
	pruefen "$pkg" "$test" "$wofuer" || printf '%s ' "$pkg" >>"$_FN"
done
FEHLT_NUETZLICH="$(cat "$_FN" 2>/dev/null || true)"
rm -f "$_FN"

log ""

if [ -z "$FEHLT_ZWINGEND" ] && [ -z "$FEHLT_NUETZLICH" ]; then
	log "Ergebnis: alles vorhanden, nichts zu tun."
	bestand_bericht
	log_close 0; exit 0
fi

# --- Rechte --------------------------------------------------------------
if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "Pakete installieren geht nur als Verwalter."
	err "  sudo sh $0"
	err ""
	err "Es fehlen:${FEHLT_ZWINGEND}${FEHLT_NUETZLICH}"
	log_close 2; exit 2
fi

# --- Installieren ---------------------------------------------------------

if [ -n "$FEHLT_ZWINGEND" ]; then
	log "Wird geholt (zwingend):$FEHLT_ZWINGEND"
	if ! bestand_apt $FEHLT_ZWINGEND; then
		err "Zwingende Pakete liessen sich nicht installieren."
		err "Ohne sie scheitern die folgenden Module — daher Abbruch hier,"
		err "vor dem ersten Eingriff, nicht mittendrin."
		log_close 2; exit 2
	fi
	log ""
fi

if [ -n "$FEHLT_NUETZLICH" ]; then
	log "Wird geholt (nuetzlich):$FEHLT_NUETZLICH"
	bestand_apt $FEHLT_NUETZLICH || \
		warn "Nicht alles Nuetzliche liess sich holen — siehe oben."
	log ""
fi

# --- Nachweis -------------------------------------------------------------
#
# Das Ergebnis pruefen, nicht den Exitcode von apt (Regel 10j). apt meldet
# Erfolg auch dann, wenn das Werkzeug hinterher nicht aufrufbar ist.

log "Nachweis"
_FR="${TMPDIR:-/tmp}/.chimera-fr.$$"
: >"$_FR"
zwingend | while IFS='	' read -r pkg test wofuer; do
	[ -n "$pkg" ] || continue
	sh -c "$test" >/dev/null 2>&1 || printf '%s ' "$pkg" >>"$_FR"
done
NOCH_FEHLT="$(cat "$_FR" 2>/dev/null || true)"
rm -f "$_FR"

if [ -n "$NOCH_FEHLT" ] && ! is_dry_run; then
	err "Nach der Installation fehlt weiterhin:$NOCH_FEHLT"
	err "Das Paket gilt als installiert, das Werkzeug ist aber nicht"
	err "aufrufbar. Pfad? Anderer Paketname auf diesem System?"
	log_close 2; exit 2
fi

info "Alles Zwingende ist aufrufbar."
log ""
bestand_bericht
log ""
log "Ergebnis: Abhaengigkeiten stehen."
log_close 0
exit 0
