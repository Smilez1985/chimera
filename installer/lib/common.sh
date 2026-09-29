#!/bin/sh
# Chimera installer — gemeinsame Helfer.
#
# POSIX sh, keine bash-Abhaengigkeit: das Ding laeuft auf DietPi, aber auch
# in einer schlanken Testumgebung. Keine Arrays, kein [[ ]], kein local
# ausserhalb von Funktionen (dash kennt local, POSIX nicht — wir bleiben
# bei dash-Kompatibilitaet, das ist DietPis /bin/sh).

# Wurzelverzeichnis fuer alle Systemabfragen. Im Betrieb "", in Tests ein
# temporaeres Verzeichnis mit erfundenen Dateien. Dadurch ist die gesamte
# Erkennung ohne Zielhardware pruefbar (Architekturregel 9).
: "${CHIMERA_ROOT:=}"

# --- Ausgabe ---------------------------------------------------------------

_c_use_color() { [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; }

log()  { printf '%s\n' "$*"; }
info() { printf '  %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
err()  { printf 'FEHLER: %s\n' "$*" >&2; }

die() { err "$*"; exit 1; }

# --- Lesen aus dem (ggf. erfundenen) Wurzelverzeichnis ---------------------

# Pfad im Zielsystem in einen echten Pfad uebersetzen.
rootpath() { printf '%s%s' "$CHIMERA_ROOT" "$1"; }

# Datei lesen, leer wenn nicht vorhanden. Kein Fehler — Abwesenheit ist
# hier eine gueltige Aussage, kein Ausnahmefall.
read_file() {
	_rf_p="$(rootpath "$1")"
	[ -r "$_rf_p" ] || return 1
	cat "$_rf_p" 2>/dev/null
}

# Gerätebaum-Strings sind nullterminiert. tr statt cat, sonst hängen
# Nullbytes in der Variablen und jeder Vergleich wird unzuverlässig.
read_dt() {
	_rd_p="$(rootpath "$1")"
	[ -r "$_rd_p" ] || return 1
	tr -d '\0' <"$_rd_p" 2>/dev/null
}

# compatible enthaelt mehrere nullgetrennte Kennungen — in Zeilen wandeln.
read_dt_list() {
	_rl_p="$(rootpath "$1")"
	[ -r "$_rl_p" ] || return 1
	tr '\0' '\n' <"$_rl_p" 2>/dev/null
}

have_dir()  { [ -d "$(rootpath "$1")" ]; }
have_file() { [ -e "$(rootpath "$1")" ]; }

# --- Werkzeuge -------------------------------------------------------------

# I4: Vorhandensein pruefen, bevor man sich darauf verlaesst. Ein Exitcode
# von 0 heisst nicht, dass das Programm existierte.
have_cmd() { command -v "$1" >/dev/null 2>&1; }

# --- Atomares Schreiben (I3) ----------------------------------------------

# Sidecar NEBEN dem Ziel anlegen, dann per mv umbenennen. Gleiches
# Dateisystem, deshalb ist mv atomar.
#
# Und der teuer bezahlte Teil: mktemp wird GEPRUEFT. Zeigt TMPDIR ins
# Leere oder ist das Dateisystem voll, liefert mktemp einen leeren Pfad.
# Ohne Pruefung bekaeme das nachfolgende Umbenennen eine leere Quelle und
# wuerde die Zieldatei leeren. Bei /boot-Dateien bootet das Geraet danach
# nicht mehr.
write_atomic() {
	_wa_target="$1"
	_wa_dir="$(dirname "$_wa_target")"

	[ -d "$_wa_dir" ] || { err "Zielverzeichnis fehlt: $_wa_dir"; return 1; }

	_wa_tmp="$(mktemp "$_wa_dir/.chimera.XXXXXX" 2>/dev/null)" || _wa_tmp=""
	if [ -z "$_wa_tmp" ] || [ ! -f "$_wa_tmp" ]; then
		err "mktemp lieferte keinen brauchbaren Pfad in $_wa_dir"
		err "Zieldatei bleibt unveraendert: $_wa_target"
		return 1
	fi

	if ! cat >"$_wa_tmp"; then
		rm -f "$_wa_tmp"
		err "Schreiben nach $_wa_tmp fehlgeschlagen; $_wa_target unveraendert"
		return 1
	fi

	# Leere Eingabe ist fast immer ein Fehler weiter oben in der Kette --
	# eine Pipe, deren Erzeuger gescheitert ist, liefert stillschweigend
	# nichts. Ohne diese Pruefung wuerde die leere Sidecar-Datei ueber das
	# Ziel gelegt und die Datei damit GELEERT, mit Exitcode 0. Genau diese
	# Fehlerklasse (stiller Datenverlust bei scheinbarem Erfolg) hat schon
	# einmal ein Geraet unbootbar gemacht.
	#
	# Wer wirklich eine leere Datei schreiben will, sagt das ausdruecklich:
	#   CHIMERA_ALLOW_EMPTY=1 write_atomic ...
	if [ ! -s "$_wa_tmp" ] && [ "${CHIMERA_ALLOW_EMPTY:-0}" != 1 ]; then
		rm -f "$_wa_tmp"
		err "Leere Eingabe fuer $_wa_target -- wird nicht geschrieben."
		err "Wenn das gewollt ist: CHIMERA_ALLOW_EMPTY=1 setzen."
		return 1
	fi

	# Rechte des Originals uebernehmen, falls es existiert.
	if [ -f "$_wa_target" ]; then
		chmod --reference="$_wa_target" "$_wa_tmp" 2>/dev/null || true
	else
		chmod 0644 "$_wa_tmp" 2>/dev/null || true
	fi

	if ! mv -f "$_wa_tmp" "$_wa_target"; then
		rm -f "$_wa_tmp"
		err "Umbenennen nach $_wa_target fehlgeschlagen"
		return 1
	fi
	return 0
}

# Sicherung mit Zeitstempel. Eine kaputte Bootkonfiguration auf einem
# Geraet ohne Bildschirm bedeutet SD-Karte ausbauen.
backup_file() {
	_bf_f="$1"
	[ -f "$_bf_f" ] || return 0
	_bf_b="${_bf_f}.chimera-$(date +%Y%m%d-%H%M%S).bak"
	cp -p "$_bf_f" "$_bf_b" || return 1
	info "Sicherung: $_bf_b"
}
