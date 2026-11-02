#!/bin/sh
# Fortschrittsanzeige waehrend des Laufs (installer/lib/py/fortschritt.py).
#
# Warum getrennt vom Dienst: Der Installer haelt den Dienst an, bevor er
# Dateien tauscht. Genau dann will man den Fortschritt sehen -- der Dienst kann
# ihn also nicht zeichnen.
#
# Bezug: Jede Stufe zaehlt gleich viel. fertig/gesamt ergibt den Anteil
# (Vorgabe smilez, 2.11.: "alle Installer Stufen bis Abschluss = 100 %").

FORT_DIR="${CHIMERA_FORTSCHRITT_DIR:-/run/chimera-setup}"
FORT_DATEI="$FORT_DIR/stand"
FORT_MARKE="$FORT_DIR/stop"
FORT_PID="$FORT_DIR/pid"
_FORT_GESAMT=0

_fort_py() {
	for _fp_k in "${CHIMERA_PYTHON:-}" "${CHIMERA_VENV:-}/bin/python3" python3; do
		[ -n "$_fp_k" ] && [ -x "$_fp_k" ] && { printf '%s' "$_fp_k"; return 0; }
		[ "$_fp_k" = python3 ] && have_cmd python3 && { printf 'python3'; return 0; }
	done
	return 1
}

# $1 Gesamtzahl der Stufen, $2 bereits erledigt (nach einer Pause).
# Ohne Anzeige (--still) wird nichts gestartet.
fortschritt_start() {
	_FORT_GESAMT="${1:-0}"
	_FORT_SCHON="${2:-0}"
	[ "$_FORT_GESAMT" -gt 0 ] 2>/dev/null || return 0
	if [ "${CHIMERA_FORTSCHRITT_STILL:-0}" = 1 ]; then
		info "Anzeige: Fortschritt ohne Panel (--still)."
		return 0
	fi
	mkdir -p "$FORT_DIR" 2>/dev/null || {
		warn "Anzeige: $FORT_DIR nicht anlegbar -- kein Fortschrittsbalken."
		return 0; }
	rm -f "$FORT_MARKE" 2>/dev/null || true
	# Ein bereits erreichter Stand bleibt stehen: Nach dem Selbstneustart aus
	# source/ beginnt der Lauf neu, der Balken darf aber nicht zurueckspringen.
	if [ -f "$FORT_DATEI" ]; then
		_alt="$(awk 'NR == 1 { print $1 }' "$FORT_DATEI" 2>/dev/null)"
		case "$_alt" in
			''|*[!0-9]*) : ;;
			*) [ "$_alt" -gt "$_FORT_SCHON" ] && _FORT_SCHON="$_alt" ;;
		esac
	fi
	printf '%s %s\n' "$_FORT_SCHON" "$_FORT_GESAMT" >"$FORT_DATEI" || return 0

	_fs_py="$(_fort_py)" || {
		warn "Anzeige: kein Python gefunden -- kein Fortschrittsbalken."; return 0; }
	_fs_skript="${_HERE:-${HERE:-.}}/lib/py/fortschritt.py"
	[ -f "$_fs_skript" ] || { warn "Anzeige: $_fs_skript fehlt."; return 0; }
	_fs_src="${CHIMERA_DISPLAY_SRC:-${CHIMERA_SOURCE:-}/src}"
	_fs_moods="${CHIMERA_SOURCE:-}/data/moods-builtin.json"
	if command -v setsid >/dev/null 2>&1; then
		PYTHONPATH="$_fs_src" PYTHONDONTWRITEBYTECODE=1 \
			setsid "$_fs_py" "$_fs_skript" --datei "$FORT_DATEI" \
			--marke "$FORT_MARKE" --moods "$_fs_moods" --text "${CHIMERA_FORTSCHRITT_TEXT:-Updating...}" </dev/null >/dev/null 2>&1 &
	else
		PYTHONPATH="$_fs_src" PYTHONDONTWRITEBYTECODE=1 \
			"$_fs_py" "$_fs_skript" --datei "$FORT_DATEI" \
			--marke "$FORT_MARKE" --moods "$_fs_moods" --text "${CHIMERA_FORTSCHRITT_TEXT:-Updating...}" </dev/null >/dev/null 2>&1 &
	fi
	echo "$!" >"$FORT_PID" 2>/dev/null || true
	# Kurz warten und pruefen, ob der Zeichner ueberhaupt lebt.
	sleep 1
	_fs_pid="$(cat "$FORT_PID" 2>/dev/null || echo "")"
	if [ -n "$_fs_pid" ] && kill -0 "$_fs_pid" 2>/dev/null; then
		info "Anzeige: Fortschrittsbalken laeuft (PID $_fs_pid, $_FORT_SCHON/$_FORT_GESAMT)."
	else
		warn "Anzeige: Zeichner nicht gestartet -- es gibt keinen Balken."
	fi
	return 0
}

# $1 erledigte Stufen
fortschritt_setze() {
	[ "${_FORT_GESAMT:-0}" -gt 0 ] 2>/dev/null || return 0
	[ -d "$FORT_DIR" ] || return 0
	# Nie zurueck: Nach einem Neustart zaehlt der neue Lauf wieder ab 0, der
	# erreichte Stand bleibt aber stehen (sonst spraenge der Balken zurueck).
	_setz="${1:-0}"
	if [ -f "$FORT_DATEI" ]; then
		_alt="$(awk 'NR == 1 { print $1 }' "$FORT_DATEI" 2>/dev/null)"
		case "$_alt" in
			''|*[!0-9]*) : ;;
			*) [ "$_alt" -gt "$_setz" ] && _setz="$_alt" ;;
		esac
	fi
	printf '%s %s\n' "$_setz" "$_FORT_GESAMT" >"$FORT_DATEI" 2>/dev/null || true
	return 0
}

# Zeichner anhalten, aber Zaehlung behalten -- fuer Schritte, die das Panel
# selbst brauchen (Anzeige-Erkennung, Messung; am Pi 2.11. gemessen: mit
# laufendem Zeichner meldet die Erkennung "Leitungen belegt").
fortschritt_halt() {
	_fh_pid="$(cat "$FORT_PID" 2>/dev/null || echo "")"
	: >"$FORT_MARKE" 2>/dev/null || true
	_fh_i=0
	while [ -n "$_fh_pid" ] && kill -0 "$_fh_pid" 2>/dev/null && [ "$_fh_i" -lt 6 ]; do
		_fh_i=$((_fh_i + 1))
		sleep 0.5
	done
	[ -n "$_fh_pid" ] && kill "$_fh_pid" 2>/dev/null || true
	rm -f "$FORT_MARKE" "$FORT_PID" 2>/dev/null || true
	return 0
}

fortschritt_stop() {
	[ -d "$FORT_DIR" ] || return 0
	: >"$FORT_MARKE" 2>/dev/null || true
	_fst_pid="$(cat "$FORT_PID" 2>/dev/null || echo "")"
	_fst_i=0
	while [ -n "$_fst_pid" ] && kill -0 "$_fst_pid" 2>/dev/null && [ "$_fst_i" -lt 6 ]; do
		_fst_i=$((_fst_i + 1))
		sleep 0.5
	done
	if [ -n "$_fst_pid" ] && kill -0 "$_fst_pid" 2>/dev/null; then
		kill "$_fst_pid" 2>/dev/null || true
		warn "Anzeige: Zeichner reagierte nicht -- beendet."
	fi
	rm -f "$FORT_MARKE" "$FORT_PID" "$FORT_DATEI" 2>/dev/null || true
	return 0
}
