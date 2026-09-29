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

# Protokoll. Jeder Lauf hinterlaesst eine Datei -- auch ein erfolgreicher.
# Ein Lauf, der nichts hinterlaesst, ist spaeter nicht nachvollziehbar, und
# genau dann braucht man ihn: wenn etwas schiefging und die Frage lautet,
# was vorher anders war.
: "${CHIMERA_LOG_DIR:=${CHIMERA_ROOT}/var/log/chimera}"
CHIMERA_LOGFILE=""

log_open() {
	_lo_name="${1:-chimera}"
	mkdir -p "$CHIMERA_LOG_DIR" 2>/dev/null || {
		# Kein Schreibrecht (z. B. Lauf ohne root): Protokoll ins
		# Arbeitsverzeichnis, aber NICHT stillschweigend weglassen.
		CHIMERA_LOG_DIR="./logs"
		mkdir -p "$CHIMERA_LOG_DIR" 2>/dev/null || return 1
	}
	CHIMERA_LOGFILE="$CHIMERA_LOG_DIR/${_lo_name}-$(date +%Y%m%d-%H%M%S).log"
	: >"$CHIMERA_LOGFILE" 2>/dev/null || { CHIMERA_LOGFILE=""; return 1; }
	_log_raw "=== chimera $_lo_name — $(date '+%Y-%m-%d %H:%M:%S') ==="
	_log_raw "Version: $(cat "$(dirname "$0")/../VERSION" 2>/dev/null || echo '?')"
	return 0
}

# Nur in die Datei, nicht auf den Schirm.
_log_raw() {
	[ -n "$CHIMERA_LOGFILE" ] || return 0
	printf '%s\n' "$*" >>"$CHIMERA_LOGFILE" 2>/dev/null || true
}

log()  { printf '%s\n' "$*";           _log_raw "$*"; }
info() { printf '  %s\n' "$*";         _log_raw "  $*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; _log_raw "WARN: $*"; }
err()  { printf 'FEHLER: %s\n' "$*" >&2; _log_raw "FEHLER: $*"; }

# Protokolle aufraeumen: die juengsten CHIMERA_LOG_KEEP behalten. Sonst
# laeuft auf einem Geraet, das monatelang durchlaeuft, die Karte voll --
# ausgerechnet wegen der Dateien, die beim Debuggen helfen sollen.
: "${CHIMERA_LOG_KEEP:=20}"
log_rotate() {
	[ -d "$CHIMERA_LOG_DIR" ] || return 0
	_lr_n=0
	# Neueste zuerst; alles ab Position KEEP+1 faellt weg.
	for _lr_f in $(ls -1t "$CHIMERA_LOG_DIR"/*.log 2>/dev/null); do
		_lr_n=$((_lr_n + 1))
		[ "$_lr_n" -le "$CHIMERA_LOG_KEEP" ] && continue
		rm -f "$_lr_f" 2>/dev/null || true
	done
}

# --- Betriebsart ----------------------------------------------------------
#
# Module fragen NICHT selbst die Variable ab, sondern benutzen diese
# Helfer. Sonst steht die Bedeutung von "dry" an zwanzig Stellen und
# driftet auseinander.
: "${CHIMERA_MODE:=run}"

mode_is()      { [ "$CHIMERA_MODE" = "$1" ]; }
is_dry_run()   { [ "$CHIMERA_MODE" = dry ] || [ "$CHIMERA_MODE" = check ]; }
is_check()     { [ "$CHIMERA_MODE" = check ]; }

# Eine aendernde Handlung ausfuehren -- oder im Trockenlauf nur ankuendigen.
# $1 Beschreibung, Rest: der Befehl.
do_change() {
	_dc_what="$1"; shift
	if is_dry_run; then
		info "[wuerde] $_dc_what"
		_log_raw "  [dry] $_dc_what"
		return 0
	fi
	info "$_dc_what"
	"$@"
}

# Bilanz am Ende -- auch bei Erfolg.
log_close() {
	_lc_rc="${1:-0}"
	if [ "$_lc_rc" -eq 0 ]; then _log_raw "=== Ergebnis: Erfolg (0) ==="
	else _log_raw "=== Ergebnis: Exitcode $_lc_rc ==="; fi
	[ -n "$CHIMERA_LOGFILE" ] && printf 'Protokoll: %s\n' "$CHIMERA_LOGFILE"
	log_rotate
	return 0
}

die() { err "$*"; log_close 1; exit 1; }

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

# Sicherung mit Zeitstempel.
#
# NOCH OHNE AUFRUFER: Wird von Modul 60 (Overlay/Bootkonfiguration)
# gebraucht, das es noch nicht gibt. Steht hier, weil die Regel dazu
# bereits feststeht und getestet ist -- nicht als Vorrat, sondern damit
# Modul 60 sie nicht neu erfindet.
#
# Eine kaputte Bootkonfiguration auf einem Geraet ohne Bildschirm bedeutet
# im besten Fall SD-Karte ausbauen. Laeuft das System vom eMMC, gibt es
# nichts auszubauen -- dann braucht die Rettung Herstellerwerkzeug an
# einem PC.
backup_file() {
	_bf_f="$1"
	[ -f "$_bf_f" ] || return 0
	_bf_b="${_bf_f}.chimera-$(date +%Y%m%d-%H%M%S).bak"
	cp -p "$_bf_f" "$_bf_b" || return 1
	info "Sicherung: $_bf_b"
}
