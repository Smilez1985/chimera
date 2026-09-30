#!/bin/sh
# Chimera installer -- gemeinsame Helfer.
#
# POSIX sh, keine bash-Abhaengigkeit: das Ding laeuft auf DietPi, aber auch
# in einer schlanken Testumgebung. Keine Arrays, kein [[ ]], kein local
# ausserhalb von Funktionen (dash kennt local, POSIX nicht -- wir bleiben
# bei dash-Kompatibilitaet, das ist DietPis /bin/sh).

# Locale festnageln. Nicht aus Ordnungsliebe: `sort` ordnet unter
# de_DE.UTF-8 anders als unter C, und `grep [a-z]` fasst dort auch Umlaute.
# Ein Installer, der je nach Umgebung anders sortiert, ist nicht
# reproduzierbar -- und auf dem Zielgeraet ist der Aufrufer ein
# systemd-Dienst mit leerem LANG, nicht die Shell des Entwicklers.
#
# LC_ALL sticht LANG und alle LC_*; darum genau diese Variable.
LC_ALL=C
export LC_ALL

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

# Mit `:=` statt `=`, damit ein von aussen gesetzter Wert erhalten bleibt
# (der Laeufer reicht das Protokoll an die Schritte durch) und die Variable
# auch dann definiert ist, wenn sie vorher `unset` war.
#
# Der Unterschied ist unter `set -u` kein Feinheit: Ein Skript, das
# common.sh laedt, CHIMERA_LOGFILE aber nicht setzt, starb beim ersten
# Protokollschreiben mit "parameter not set" -- und weil das auf stderr
# ging und der Aufrufer stderr wegwarf, sah es aus wie ein stiller
# Abbruch mitten in einer Funktion. Gekostet hat das eine Stunde Suche im
# falschen Bauteil.
: "${CHIMERA_LOGFILE:=}"

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
	_log_raw "=== chimera $_lo_name -- $(date '+%Y-%m-%d %H:%M:%S') ==="
	_log_raw "Version: $(cat "$(dirname "$0")/../VERSION" 2>/dev/null || echo '?')"
	return 0
}

# Nur in die Datei, nicht auf den Schirm.
#
# Der Zugriff nutzt ${...:-}, damit eine nicht gesetzte Variable unter
# `set -u` kein Abbruch ist. Protokollieren ist eine Nebensache; es darf
# den Lauf nicht beenden. Passiert ist genau das: Ein Aufrufer hatte
# CHIMERA_LOGFILE ge-unsett, und der Lauf starb beim ersten info().
_log_raw() {
	[ -n "${CHIMERA_LOGFILE:-}" ] || return 0
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

# Eine bewusste Bestaetigung einholen (Regel 10k).
#
# Fuer Faelle, in denen der Installer NICHT verbietet, aber auch nicht
# stillschweigend weitermacht: unbekanntes Board, ungetestete Kombination.
# Die Frage ist keine Formalie -- deshalb genuegt kein Eingabetaste-Druck,
# sondern es muss "ja" getippt werden.
#
# Nicht-interaktiv (Skript, CI, kein Terminal) gilt: ohne ausdruecklichen
# Schalter wird NICHT fortgesetzt. Ein Automatiklauf soll nicht
# versehentlich ueber eine Warnung hinweglaufen, die ein Mensch gelesen
# haette.
#
# Gilt die Antwort als Zustimmung? Eigene Funktion, damit sie geprueft
# werden kann, ohne ein Terminal vorzutaeuschen -- ein Test, der die
# Auswertung nachbaut, pruefte nur sich selbst (Regel 9).
#
# Eine leere Eingabe ist KEIN ja: Ein weggedruecktes Enter ist keine
# Entscheidung.
answer_is_yes() {
	case "${1:-}" in
		ja|JA|Ja|j|J) return 0 ;;
		*) return 1 ;;
	esac
}

# $1 die Frage. Rueckgabe 0 = fortfahren, 1 = nicht.
confirm_risk() {
	_cr_q="${1:-Fortfahren?}"

	if [ "${CHIMERA_ASSUME_YES:-0}" = 1 ]; then
		warn "$_cr_q -> ja (CHIMERA_ASSUME_YES=1, auf eigene Gefahr)"
		return 0
	fi

	if is_dry_run; then
		info "[wuerde fragen] $_cr_q"
		return 0
	fi

	if [ ! -t 0 ]; then
		err "$_cr_q"
		err "Keine Eingabe moeglich (kein Terminal). Wer das bewusst will,"
		err "setzt CHIMERA_ASSUME_YES=1 -- und traegt die Folgen."
		return 1
	fi

	printf '%s [ja/nein] ' "$_cr_q" >&2
	read -r _cr_a || _cr_a=""
	if answer_is_yes "$_cr_a"; then
		_log_raw "  Bestaetigt: $_cr_q -> $_cr_a"
		return 0
	fi
	_log_raw "  Abgelehnt: $_cr_q -> ${_cr_a:-(nichts)}"
	return 1
}

# Bilanz am Ende -- auch bei Erfolg.
log_close() {
	_lc_rc="${1:-0}"
	if [ "$_lc_rc" -eq 0 ]; then _log_raw "=== Ergebnis: Erfolg (0) ==="
	else _log_raw "=== Ergebnis: Exitcode $_lc_rc ==="; fi
	[ -n "${CHIMERA_LOGFILE:-}" ] && printf 'Protokoll: %s\n' "$CHIMERA_LOGFILE"
	log_rotate
	return 0
}

die() { err "$*"; log_close 1; exit 1; }

# --- Lesen aus dem (ggf. erfundenen) Wurzelverzeichnis ---------------------

# Pfad im Zielsystem in einen echten Pfad uebersetzen.
rootpath() { printf '%s%s' "$CHIMERA_ROOT" "$1"; }

# Datei lesen, leer wenn nicht vorhanden. Kein Fehler -- Abwesenheit ist
# hier eine gueltige Aussage, kein Ausnahmefall.
read_file() {
	_rf_p="$(rootpath "$1")"
	[ -r "$_rf_p" ] || return 1
	cat "$_rf_p" 2>/dev/null
}

# Geraetebaum-Strings sind nullterminiert. tr statt cat, sonst haengen
# Nullbytes in der Variablen und jeder Vergleich wird unzuverlaessig.
read_dt() {
	_rd_p="$(rootpath "$1")"
	[ -r "$_rd_p" ] || return 1
	tr -d '\0' <"$_rd_p" 2>/dev/null
}

# compatible contains mehrere nullgetrennte Kennungen -- in Zeilen wandeln.
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
# Eine Fremddatei sichern, bevor sie angefasst wird.
#
# Eine kaputte Bootkonfiguration auf einem Geraet ohne Bildschirm bedeutet
# im besten Fall SD-Karte ausbauen. Laeuft das System vom eMMC, gibt es
# nichts auszubauen -- dann braucht die Rettung Herstellerwerkzeug an
# einem PC.
#
# Aufrufer: steps/40-install-display.sh (bus_enable), vor dem Anhaengen an
# config.txt.
#
# Die Sicherung wird ins Manifest eingetragen, sonst weiss die
# Deinstallation nicht, welche Kopie zu welchem Original gehoert -- und
# eine Sicherung, die niemand zuordnen kann, ist nur noch Muell im
# Dateisystem (Architekturregel 10l).
backup_file() {
	_bf_f="$1"
	[ -f "$_bf_f" ] || return 0
	_bf_b="${_bf_f}.chimera-$(date +%Y%m%d-%H%M%S).bak"
	cp -p "$_bf_f" "$_bf_b" || return 1
	info "Sicherung: $_bf_b"

	# manifest.sh ist nicht ueberall geladen -- common.sh ist die
	# unterste Schicht und darf sie nicht voraussetzen. Darum pruefen,
	# statt zu hoffen: Fehlt die Funktion, wird das GESAGT, nicht
	# stillschweigend uebergangen (Architekturregel 8a).
	if command -v manifest_record >/dev/null 2>&1; then
		manifest_record sicherung "$_bf_b" "$_bf_f"
	else
		warn "Sicherung nicht im Manifest festgehalten (manifest.sh"
		warn "nicht geladen) -- die Deinstallation kann sie nicht"
		warn "zuordnen: $_bf_b"
	fi
}
