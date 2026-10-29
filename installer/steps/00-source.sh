#!/bin/sh
# Chimera installer -- Modul 00: Quelle (lokale SSOT-Kopie).
#
# Erster Schritt, vor allem anderen. Bringt den Stand nach
# /opt/chimera/source -- aus dem Startbaum (Klon, Zip, Paket) oder, wenn
# online ein hoeherer veroeffentlichter Stand (vX.Y.Z-Tag) liegt, von dort.
# Der Laeufer startet sich danach aus source/ neu (I8); ab dann sieht kein
# Schritt mehr den Startbaum. Begruendung: DESIGN Regel 10r.
#
# Exitcode:
#   0  source/ ist der gewollte Stand, nichts geaendert
#   4  weiter aus source/ -- source/ wurde erneuert, ODER der Startbaum
#      wurde abgelehnt (aelter) und source/ ist der gueltige Stand. Im
#      zweiten Fall steht CHIMERA_BEFUND_QUELLE in der Datei
#      $CHIMERA_LOG_DIR/.befund-quelle, damit der Befund den Neustart
#      ueberlebt und im Gesamt-Exitcode landet.
#   1  Befund ohne source/ (kann nicht weiter aus source/ arbeiten)
#   2  abgebrochen

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/network.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/source.sh"

CHIMERA_STEP="00-source"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "source" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

# Startbaum: das Repo, aus dem dieser Schritt laeuft. Ein Zip oder Paket
# hat dasselbe Layout (installer/, src/, VERSION).
START="$(cd "$_HERE/.." && pwd)"
ZIEL="$(rootpath "$CHIMERA_SOURCE")"
: "${CHIMERA_QUELLE_URL:=https://github.com/Smilez1985/chimera.git}"
: "${CHIMERA_DOWNGRADE:=false}"

log "Chimera Quelle"
info "Startbaum: $START"
info "Ziel:      $CHIMERA_SOURCE"

if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "source/ liegt unter $CHIMERA_OPT und gehoert root -- nur als Verwalter."
	err "  sudo sh $0"
	log_close 2; exit 2
fi

[ -f "$START/VERSION" ] || { err "VERSION fehlt im Startbaum ($START)."; log_close 2; exit 2; }

is_dry_run || source_reparieren "$ZIEL"

# Laeuft der Schritt schon AUS source/, ist der Startbaum source/ selbst.
# Dann gibt es lokal nichts zu vergleichen, nur online nachzusehen.
_aus_source=0
[ -d "$ZIEL" ] && [ "$(cd "$ZIEL" && pwd)" = "$START" ] && _aus_source=1

KAND="$START"
KAND_V="$(source_version "$START")"
_tmp=""
trap '[ -n "$_tmp" ] && rm -rf "$_tmp"' EXIT INT TERM

# --- Online: hoechster veroeffentlichter Stand ----------------------------
log ""
log "Veroeffentlichter Stand"
set +e
if [ "${CHIMERA_NEU_GESTARTET:-0}" = 1 ]; then
	# Schon im ersten Durchgang nachgesehen; source/ IST dessen Ergebnis.
	TAG=""; _nt_rc=3
else
	TAG="$(source_neuester_tag "$CHIMERA_QUELLE_URL")"
	_nt_rc=$?
fi
set -e
if [ "$_nt_rc" -eq 3 ]; then
	info "im ersten Durchgang nachgesehen -- nicht erneut."
elif [ "$_nt_rc" -ne 0 ]; then
	info "nicht nachsehbar (offline oder Quelle nicht erreichbar) -- es zaehlt der lokale Stand."
elif [ -z "$TAG" ]; then
	info "kein veroeffentlichter Stand (kein vX.Y.Z-Tag) -- es zaehlt der lokale Stand."
else
	info "hoechster Tag: $TAG (lokal: $KAND_V)"
	if [ "$(version_cmp "${TAG#v}" "$KAND_V")" = gt ]; then
		if is_dry_run; then
			info "[wuerde holen] $TAG"
		else
			_tmp="$(tmp_path .chimera-quelle)" && rm -f "$_tmp" || {
				err "Kein Zwischenverzeichnis fuer den Abruf."; log_close 2; exit 2; }
			if source_tag_holen "$CHIMERA_QUELLE_URL" "$TAG" "$_tmp"; then
				KAND="$_tmp"; KAND_V="$(source_version "$_tmp")"
				info "geholt: $TAG"
			else
				warn "$TAG nicht holbar -- es zaehlt der lokale Stand."
			fi
		fi
	fi
fi

# --- Entscheidung ---------------------------------------------------------
log ""
log "Vergleich"
# Laeuft der Schritt aus source/ und kam online nichts Neueres, ist
# source/ per Definition der Stand -- es gibt nichts zu vergleichen.
if [ "$_aus_source" = 1 ] && [ "$KAND" = "$START" ]; then
	log "Laeuft aus source/ ($KAND_V) -- nichts zu tun."
	log_close 0; exit 0
fi
# source_hash liefert rc 1, wenn ein Baum nicht eindeutig pruefbar ist --
# ohne `||` beendete set -e den Schritt hier still mit rc 1 ("Befund").
KAND_H="$(source_hash "$KAND")" || KAND_H=""
[ -n "$KAND_H" ] || { err "Pruefsumme des Startbaums leer -- Abbruch."; log_close 2; exit 2; }
IST_H=""; IST_V=""
if [ -d "$ZIEL" ]; then
	# Nicht pruefbar heisst: Inhalt unbekannt, also anders als der
	# Kandidat. Ueber das Ersetzen entscheidet dann wie sonst die VERSION.
	IST_H="$(source_hash "$ZIEL")" || {
		warn "source/ nicht eindeutig pruefbar -- gilt als abweichend."
		IST_H="nicht-pruefbar"; }
	IST_V="$(source_version "$ZIEL")"
fi
info "Kandidat: $KAND_V  ${KAND_H%"${KAND_H#????????????}"}"
info "source/:  ${IST_V:-fehlt}  ${IST_H:+${IST_H%"${IST_H#????????????}"}}"

ENTSCHEID="$(source_entscheiden "$KAND_H" "$IST_H" "$KAND_V" "$IST_V" "$CHIMERA_DOWNGRADE")"

# Commit der Quelle festhalten, solange .git noch da ist (Schritt 55 braucht
# ihn). Nicht im Trockenlauf; nicht, wenn source/ abgelehnt wird -- dann
# bleibt der bisherige Stand und mit ihm sein Commit.
quelle_commit() {
	is_dry_run && return 0
	_qc_f="$(rootpath "$CHIMERA_STATE")/quelle-commit"
	if _qc="$(source_commit_festhalten "$KAND" "$_qc_f")"; then
		if [ -n "$_qc" ]; then
			info "Commit der Quelle: $_qc"
			manifest_record datei "$_qc_f" ""
		else
			info "Quelle ohne Commit (kein .git oder rust/ geaendert) -- Schritt 55 kann kein Binary waehlen."
		fi
	else
		warn "Commit der Quelle nicht festgehalten ($_qc_f)."
	fi
}
case "$ENTSCHEID" in
	gleich)
		quelle_commit
		log "source/ ist bereits dieser Stand -- nichts zu tun."
		log_close 0; exit 0 ;;
	abgelehnt)
		warn "Startbaum $KAND_V ist aelter als source/ $IST_V -- kein Downgrade."
		warn "Es geht mit source/ ($IST_V) weiter. Bewusst zurueck: --downgrade=true"
		if is_dry_run; then log_close 1; exit 1; fi
		mkdir -p "$CHIMERA_LOG_DIR" 2>/dev/null && \
			printf 'abgelehnt %s < %s\n' "$KAND_V" "$IST_V" >"$CHIMERA_LOG_DIR/.befund-quelle"
		log_close 4; exit 4 ;;
	anlegen)                  info "source/ fehlt -- wird angelegt." ;;
	ersetzen)                 info "Aktualisierung $IST_V -> $KAND_V." ;;
	ersetzen_gleiche_version) warn "Gleiche VERSION ($KAND_V), anderer Inhalt -- source/ wird ersetzt." ;;
	downgrade)                warn "Downgrade $IST_V -> $KAND_V (--downgrade=true)." ;;
	*) err "unbekannte Entscheidung: $ENTSCHEID"; log_close 2; exit 2 ;;
esac

if is_dry_run; then
	info "[wuerde kopieren] $KAND -> $CHIMERA_SOURCE"
	log_close 0; exit 0
fi

if ! source_kopieren "$KAND" "$ZIEL" "$KAND_H"; then
	err "source/ nicht erneuert."
	log_close 2; exit 2
fi
manifest_has verzeich "$ZIEL" || manifest_record verzeich "$ZIEL" ""
quelle_commit
log "source/ = $KAND_V (${KAND_H%"${KAND_H#????????????}"})"
log_close 4; exit 4
