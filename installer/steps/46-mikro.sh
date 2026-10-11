#!/bin/sh
# Chimera installer -- Modul 46: Mikrofone messen und das Aufnahmegeraet bauen.
#
# Warum messen statt festlegen (smilez, 11.10.2026): Am chimera-pi klirrt das
# linke Mikro der Whisplay. Ein fest eingebautes "nur rechts" zwaenge diesen
# Defekt jedem auf, der das Repo zieht. Darum misst jede Installation selbst
# (python3 -m chimera.displays mikro): Testtoene ueber den eigenen Lautsprecher,
# beide Mikros nehmen auf, je Kanal Pegel und Klirren. Ergebnis:
# beide | links | rechts | keins.
#
# Was dieser Schritt hinterlaesst:
#   state/mikro.json                  Messwerte, Zeit, Entscheidung (root)
#   /etc/alsa/conf.d/50-chimera-mikro.conf
#                                     Aufnahmegeraet chimera_mikro: das gute
#                                     Mikro (mono) oder beide (stereo)
# Andere Programme behalten die Herstellergeraete (default/array) -- nur wer
# chimera_mikro oeffnet, bekommt die Auswahl.
#
# Wann gemessen wird: nur im vollen Lauf, NICHT beim Boot-Abgleich (--hardware)
# -- die Messung spielt drei Sekunden Testtoene, das soll nicht bei jedem
# Start piepen. Neu gemessen wird, wenn sich die Anzeige seit der letzten
# Messung geaendert hat (Kartentausch) oder CHIMERA_MIKRO_NEU=1 gesetzt ist.
#
# Exitcode:
#   0  Aufnahmegeraet eingerichtet, oder Anzeige ohne Ton (nichts zu tun)
#   1  Befund: kein brauchbares Mikro, oder Messung gescheitert -- der Lauf
#      geht weiter, der Dienst laeuft ohne Spracheingabe
#   2  abgebrochen -- Voraussetzung fehlt

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/display.sh"

CHIMERA_STEP="46-mikro"; export CHIMERA_STEP
trap 'display_cache_leeren' EXIT

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "mikro" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Mikrofone"

STATE_DIR="$(rootpath "$CHIMERA_STATE")"
ANZEIGE="$(cat "$STATE_DIR/anzeige" 2>/dev/null || true)"
MESSUNG="$STATE_DIR/mikro.json"
ALSA_CONF="$(rootpath "${CHIMERA_MIKRO_CONF:-/etc/alsa/conf.d/50-chimera-mikro.conf}")"

# --- Hat die Anzeige ueberhaupt Ton? ---------------------------------------
if [ -z "$ANZEIGE" ]; then
	info "Keine Anzeige festgehalten (Schritt 40) -- nichts zu messen."
	log_close 0; exit 0
fi
if ! display_profil_lesbar "$ANZEIGE"; then
	warn "Anzeige '$ANZEIGE' hat kein Modul -- Mikrofone nicht pruefbar."
	log_close 1; exit 1
fi
ALSA_KARTE="$(display_get "$ANZEIGE" alsa_karte)"
if [ -z "$ALSA_KARTE" ]; then
	info "Anzeige $ANZEIGE hat keinen Ton -- nichts zu messen."
	log_close 0; exit 0
fi

# --- Messen oder vorhandene Messung nehmen ----------------------------------
# Eine Messung gilt fuer die Anzeige, an der sie gemacht wurde. Steht in
# state/mikro.json eine andere Anzeige (Karte in anderem Geraet), wird neu
# gemessen.
_alte_anzeige=""
if [ -s "$MESSUNG" ]; then
	_alte_anzeige="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("anzeige",""))' \
		"$MESSUNG" 2>/dev/null)" || _alte_anzeige=""
fi

if [ "${CHIMERA_MIKRO_NEU:-0}" != 1 ] && [ -n "$_alte_anzeige" ] && [ "$_alte_anzeige" = "$ANZEIGE" ]; then
	info "Messung vorhanden ($MESSUNG, Anzeige $ANZEIGE) -- nicht neu gemessen."
	info "Neu messen: CHIMERA_MIKRO_NEU=1 chimera-install --only 46"
elif is_dry_run; then
	info "[wuerde messen] Testtoene ueber den Lautsprecher, beide Mikros (rund 4 s)"
	log_close 0; exit 0
else
	if [ -z "${CHIMERA_ROOT:-}" ] && [ "$(id -u)" != 0 ]; then
		err "Messen und $ALSA_CONF schreiben geht nur als Verwalter."
		log_close 2; exit 2
	fi
	# CHIMERA_MIKRO_MESSUNG: Befehl, der statt der echten Messung das JSON
	# liefert (Tests ohne Lautsprecher). Ohne ihn wird wirklich gemessen.
	if [ -z "${CHIMERA_MIKRO_MESSUNG:-}" ]; then
		if ! have_cmd aplay || ! have_cmd arecord; then
			err "aplay/arecord fehlen (alsa-utils) -- Schritt 40 haette sie holen muessen."
			log_close 2; exit 2
		fi
		if ! read_file /proc/asound/cards 2>/dev/null | grep -qi -- "$ALSA_KARTE"; then
			warn "ALSA-Karte $ALSA_KARTE fehlt -- ohne Ton keine Messung."
			log_close 1; exit 1
		fi
	fi
	_src="${CHIMERA_DISPLAY_SRC:-$(display_src)}"
	_py="$(rootpath "$CHIMERA_VENV")/bin/python"
	[ -x "$_py" ] || _py="$(display_python)"
	_errf="$(tmp_path chimera-mikro)" || { log_close 2; exit 2; }
	info "Messe (Testtoene ueber den Lautsprecher) ..."
	set +e
	if [ -n "${CHIMERA_MIKRO_MESSUNG:-}" ]; then
		_json="$(sh -c "$CHIMERA_MIKRO_MESSUNG" 2>"$_errf")"
	else
		_json="$(PYTHONPATH="$_src" PYTHONDONTWRITEBYTECODE=1 "$_py" -m chimera.displays mikro --json 2>"$_errf")"
	fi
	_rc=$?
	set -e
	_fehler="$(cat "$_errf" 2>/dev/null || true)"
	rm -f "$_errf"
	if [ "$_rc" = 2 ] || [ -z "$_json" ]; then
		# Gescheiterte Messung ist KEIN Befund ueber die Mikros. Eine alte
		# Messung bleibt dann stehen, statt verworfen zu werden.
		warn "Messung gescheitert: ${_fehler:-keine Ausgabe}"
		log_close 1; exit 1
	fi
	# Anzeige dazuschreiben (fuer den Vergleich beim naechsten Lauf) und
	# das Ergebnis pruefen, nicht nur den Exitcode: leeres JSON waere sonst
	# eine leere Messdatei.
	_mit="$(printf '%s' "$_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); d["anzeige"]=sys.argv[1]; print(json.dumps(d, ensure_ascii=False, indent=2))' "$ANZEIGE" 2>/dev/null)" || _mit=""
	if [ -z "$_mit" ]; then
		warn "Messergebnis nicht lesbar -- nichts geschrieben."
		log_close 1; exit 1
	fi
	manifest_init || true
	printf '%s\n' "$_mit" | write_atomic "$MESSUNG" || {
		err "Messung nicht ablegbar: $MESSUNG"; log_close 2; exit 2; }
	chmod 600 "$MESSUNG" 2>/dev/null || true
	manifest_record datei "$MESSUNG" "$(sha256sum "$MESSUNG" 2>/dev/null | cut -d' ' -f1)"
fi

# --- Entscheidung lesen und das Geraet bauen --------------------------------
_feld() {
	python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); v=d.get(sys.argv[2]); print("; ".join(v) if isinstance(v, list) else ("" if v is None else v))' \
		"$MESSUNG" "$1" 2>/dev/null
}
# Kein stiller Abbruch unter set -e: Ein unlesbares Feld wird leer und dann
# unten benannt ("ohne gueltige Entscheidung").
ENTSCHEIDUNG="$(_feld entscheidung)" || ENTSCHEIDUNG=""
GRUENDE="$(_feld gruende)" || GRUENDE=""
WARNUNGEN="$(_feld warnungen)" || WARNUNGEN=""
case "$ENTSCHEIDUNG" in
	beide|links|rechts|keins) : ;;
	*) err "Messung ohne gueltige Entscheidung ($MESSUNG: '$ENTSCHEIDUNG')."
	   log_close 1; exit 1 ;;
esac
info "Ergebnis: $ENTSCHEIDUNG -- $GRUENDE"
[ -n "$WARNUNGEN" ] && warn "$WARNUNGEN"

if [ "$ENTSCHEIDUNG" = keins ]; then
	# Kein Geraet bauen. Ein altes wird entfernt, wenn es von uns ist --
	# sonst hoerte der Dienst ueber ein Geraet, dessen Mikro als tot gilt.
	if [ -f "$ALSA_CONF" ] && manifest_has datei "$ALSA_CONF"; then
		if is_dry_run; then
			info "[wuerde entfernen] $ALSA_CONF"
		else
			rm -f "$ALSA_CONF" && info "entfernt: $ALSA_CONF"
		fi
	fi
	warn "Kein brauchbares Mikrofon -- der Dienst laeuft ohne Spracheingabe."
	log_close 1; exit 1
fi

_neu="$(PYTHONPATH="${CHIMERA_DISPLAY_SRC:-$(display_src)}" PYTHONDONTWRITEBYTECODE=1 python3 -c '
import json, sys
from chimera.displays.mikro import Befund, alsa_geraet
d = json.load(open(sys.argv[1]))
b = Befund(d["entscheidung"], d.get("kanal"), d.get("gruende", []), d.get("warnungen", []), {}, d.get("zeit", ""))
sys.stdout.write(alsa_geraet(b))' "$MESSUNG" 2>/dev/null)" || _neu=""
if [ -z "$_neu" ]; then
	err "Aufnahmegeraet nicht erzeugbar (Messung $MESSUNG)."
	log_close 1; exit 1
fi

if [ -f "$ALSA_CONF" ] && [ "$(cat "$ALSA_CONF")" = "$_neu" ]; then
	info "Aufnahmegeraet chimera_mikro aktuell ($ALSA_CONF)."
elif is_dry_run; then
	info "[wuerde schreiben] $ALSA_CONF (chimera_mikro: $ENTSCHEIDUNG)"
else
	if [ -f "$ALSA_CONF" ] && ! manifest_has datei "$ALSA_CONF"; then
		err "$ALSA_CONF existiert und ist nicht von Chimera -- bleibt unangetastet."
		log_close 1; exit 1
	fi
	mkdir -p "$(dirname "$ALSA_CONF")" || { err "$(dirname "$ALSA_CONF") nicht anlegbar."; log_close 2; exit 2; }
	printf '%s' "$_neu" | write_atomic "$ALSA_CONF" || {
		err "$ALSA_CONF nicht schreibbar."; log_close 2; exit 2; }
	chmod 644 "$ALSA_CONF" 2>/dev/null || true
	manifest_record datei "$ALSA_CONF" "$(sha256sum "$ALSA_CONF" 2>/dev/null | cut -d' ' -f1)"
	info "Aufnahmegeraet chimera_mikro eingerichtet: $ENTSCHEIDUNG ($ALSA_CONF)"
fi

# --- Nachweis: das Geraet laesst sich oeffnen --------------------------------
# Nicht "Datei geschrieben", sondern: ALSA kennt das Geraet (Regel 10j).
if ! is_dry_run && have_cmd arecord && [ -z "${CHIMERA_ROOT:-}" ]; then
	if arecord -q -D chimera_mikro -f S16_LE -r 48000 -d 1 /dev/null 2>/dev/null; then
		info "Nachweis: chimera_mikro nimmt auf."
	else
		err "Nachweis fehlgeschlagen: chimera_mikro laesst sich nicht oeffnen."
		log_close 1; exit 1
	fi
fi
log_close 0; exit 0
