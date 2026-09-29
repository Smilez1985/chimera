#!/bin/sh
# Chimera installer — Modul 30: Kernel-Headers.
#
# Eigenes Modul, obwohl es nur ein Paket ist. Grund: Das richtige Paket
# haengt am Board UND an der Kernelfassung, und es gibt Faelle, in denen
# es keines gibt. Das in Modul 20 zu erledigen hiesse, eine Sonderlocke in
# die allgemeine Paketliste zu schreiben (Regel 10c).
#
# Header sind die Voraussetzung dafuer, dass Modul 40 ein Kernelmodul
# bauen kann. Fehlen sie, scheitert der Treiberbau -- und zwar mittendrin,
# nachdem der Fremdinstaller schon Pakete nachgeladen hat. Genau das ist
# beim ersten echten Lauf passiert.
#
# Exitcode:
#   0  Headers vorhanden und brauchbar
#   1  nicht vorhanden, aber das Board braucht sie vielleicht nicht
#   2  gebraucht und nicht zu bekommen

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/detect.sh"
. "$_HERE/lib/profiles.sh"
. "$_HERE/lib/netz.sh"
. "$_HERE/lib/bestand.sh"

CHIMERA_MODUL="30-headers"; export CHIMERA_MODUL

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "headers" || \
	warn "Kein Protokoll moeglich — Lauf wird nicht festgehalten."

BOARD="$(detect_board)"
OS="$(detect_os)"
KVER="$(read_file /proc/sys/kernel/osrelease 2>/dev/null | tr -d '\n' || uname -r)"

log "Chimera Kernel-Headers"
log ""
info "Board:   $BOARD"
info "Kernel:  $KVER"

# --- Sind sie schon da? ---------------------------------------------------
#
# Geprueft wird das Bauverzeichnis, nicht der Paketstatus: Ein Paket kann
# installiert sein und das Verzeichnis trotzdem fehlen oder ins Leere
# zeigen (Regel 10j). Und `Makefile` muss darin liegen, sonst ist es nur
# eine leere Huelle.
HDIR="$(rootpath "/lib/modules/$KVER/build")"

headers_brauchbar() {
	[ -d "$HDIR" ] || return 1
	[ -f "$HDIR/Makefile" ] || return 1
	return 0
}

if headers_brauchbar; then
	info "Headers: vorhanden ($HDIR)"
	log ""
	log "Ergebnis: nichts zu tun."
	log_close 0; exit 0
fi

info "Headers: fehlen ($HDIR)"
log ""

# --- Welches Paket? -------------------------------------------------------

STUFE="$(profile_get "$BOARD" header_stage)"
PKG="$(profile_get "$BOARD" header_pkg)"
POOL="$(profile_get "$BOARD" header_pool)"

if [ -z "$PKG" ]; then
	warn "Fuer dieses Board ist kein Header-Paket hinterlegt."
	warn "Es wird nicht geraten (Regel 10g). Ohne Headers kann Modul 40"
	warn "keinen Treiber bauen — eine Anzeige ohne Fremdtreiber geht"
	warn "trotzdem."
	log_close 1; exit 1
fi

info "Paket:   $PKG (Stufe $STUFE)"
[ -n "$POOL" ] && info "Quelle:  $POOL"

# Stufe 2 heisst: aus einer Fremdquelle. Das ist ein Eingriff in die
# Paketverwaltung des Systems und braucht eine bewusste Zustimmung
# (Regel 10k) -- ein zusaetzliches Repository aendert kuenftig auch
# Aktualisierungen, nicht nur diese Installation.
if [ "$STUFE" = 2 ]; then
	log ""
	warn "Die Headers kommen aus einer Fremdquelle: $POOL"
	warn "Das aendert die Paketverwaltung dauerhaft, nicht nur jetzt."
	if ! confirm_risk "Fremdquelle einbinden?"; then
		err "Abgelehnt. Ohne Headers kein Treiberbau."
		log_close 2; exit 2
	fi
fi

# --- Rechte ---------------------------------------------------------------
if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "Pakete installieren geht nur als Verwalter."
	err "  sudo sh $0"
	log_close 2; exit 2
fi

# --- Holen ----------------------------------------------------------------

log ""
log "Wird geholt: $PKG"

if ! bestand_apt "$PKG"; then
	err "Header-Paket liess sich nicht installieren: $PKG"
	err ""
	err "Bekannte Kombinationen fuer dieses Board:"
	known_combos 2>/dev/null | while IFS='|' read -r b o k pkg note; do
		[ "$b" = "$BOARD" ] || continue
		err "  $o / $k  ->  $pkg"
	done
	log_close 2; exit 2
fi

# --- Nachweis -------------------------------------------------------------
#
# apt meldet Erfolg auch dann, wenn das Bauverzeichnis hinterher nicht
# stimmt -- etwa weil das Paket zu einer anderen Kernelfassung gehoert.
# Deshalb wird das Ergebnis geprueft, nicht der Exitcode.

log ""
log "Nachweis"

if is_dry_run; then
	info "[wuerde pruefen] $HDIR/Makefile"
	log_close 0; exit 0
fi

if headers_brauchbar; then
	info "Bauverzeichnis: $HDIR"
	log ""
	log "Ergebnis: Headers stehen."
	log_close 0; exit 0
fi

err "Das Paket ist installiert, aber $HDIR taugt nicht."
err "Haeufigste Ursache: Das Paket gehoert zu einer anderen"
err "Kernelfassung als der laufenden ($KVER)."
err ""
err "Was jetzt hilft: Kernel aktualisieren und neu starten, dann erneut"
err "laufen lassen — dann passen Kernel und Headers wieder zusammen."
log_close 2
exit 2
