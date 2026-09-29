#!/bin/sh
# Chimera installer — Modul 40: Anzeige und ihr Treiber.
#
# Der Herstellertreiber wird **aufgerufen, nicht nachgebaut**. Er
# uebersetzt ein Kernelmodul aus C-Quelltext, braucht Header, einen
# Geraetebaum-Uebersetzer und eine Reihe Pakete. Das nachzubauen brächte
# keinen Gewinn und schuefe eine zweite Quelle fuer dieselbe Sache -- genau
# die Doppelimplementierung, vor der Regel 10g warnt.
#
# Was Chimera drumherum legt, weil der Hersteller es nicht tut:
#
#   * Bootkonfiguration vorher sichern (Regel 10i: nie ohne Rueckweg)
#   * festhalten, was sich geaendert hat (Regel 10e)
#   * nicht-interaktiv laufen, ohne die Rueckfrage zu verschlucken
#   * das ERGEBNIS pruefen, nicht den Exitcode (Regel 10j)
#   * Downloads pausieren statt abbrechen (lib/netz.sh)
#
# Exitcode:
#   0  Anzeige eingerichtet und nachgewiesen
#   1  nichts zu tun, oder Anzeige bekannt aber nicht unterstuetzt
#   2  abgebrochen -- Voraussetzung fehlt oder niemand hat zugestimmt
#   3  Neustart noetig, damit der Nachweis moeglich wird

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/detect.sh"
. "$_HERE/lib/profiles.sh"
. "$_HERE/lib/netz.sh"
. "$_HERE/lib/anzeigen.sh"
. "$_HERE/lib/bestand.sh"

CHIMERA_MODUL="40-anzeige"; export CHIMERA_MODUL

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "anzeige" || \
	warn "Kein Protokoll moeglich — Lauf wird nicht festgehalten."

BOARD="$(detect_board)"
BOOT_CFG="$(rootpath /boot/firmware/config.txt)"
[ -f "$BOOT_CFG" ] || BOOT_CFG="$(rootpath /boot/config.txt)"

# Wohin Fremdquelltext geholt wird. Nicht nach /tmp: Ein zweiter Lauf soll
# nicht erneut laden muessen (Idempotenz).
QUELLEN="${CHIMERA_QUELLEN:-$(rootpath /opt/chimera/quellen)}"

log "Chimera Anzeige"
log ""

# --- Rechte, bevor irgendetwas anfaengt -----------------------------------
#
# In die Bootkonfiguration schreiben und ein Kernelmodul bauen geht nur
# als Verwalter. Das jetzt zu pruefen ist kein Formalismus: Ohne diese
# Pruefung scheitert der Lauf mitten in der Arbeit -- nach dem Herunter-
# laden, womoeglich nach der halben Paketinstallation. Ein Abbruch vor
# dem ersten Eingriff ist harmlos, einer mittendrin nicht.
if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "Dieses Modul aendert die Bootkonfiguration und baut ein"
	err "Kernelmodul — das geht nur als Verwalter."
	err ""
	err "  sudo sh $0"
	err ""
	err "Was es tun WUERDE, zeigt ein Trockenlauf ohne Rechte:"
	err "  CHIMERA_MODE=dry sh $0"
	log_close 2; exit 2
fi

# --- Welche Anzeige? ------------------------------------------------------

TYP="${CHIMERA_ANZEIGE:-}"

if [ -n "$TYP" ]; then
	info "Anzeige vorgegeben: $TYP"
else
	if ! anzeige_erkennung_moeglich; then
		warn "I2C ist nicht aktiv — ein HAT kann sich noch gar nicht melden."
		warn "Das ist keine Aussage ueber die Hardware, sondern ueber die"
		warn "Sichtbarkeit: Ohne i2c_arm liest die Firmware kein HAT-EEPROM."
	fi
	TYP="$(anzeige_erkennen || true)"
	case "$TYP" in
		whisplay)  info "Erkannt: $(anzeige_get whisplay name)" ;;
		unbekannt)
			warn "Ein HAT meldet sich, aber er ist uns unbekannt."
			warn "Es wird nicht geraten (Regel 10g). Mit CHIMERA_ANZEIGE=<typ>"
			warn "laesst sich eine Anzeige vorgeben. Bekannt: $(anzeigen_liste)"
			log_close 1; exit 1 ;;
		*)
			warn "Keine Anzeige erkannt, die sich selbst meldet."
			info "Chimera laeuft auch blind. Fuer ein Panel ohne EEPROM:"
			info "  CHIMERA_ANZEIGE=st7789 (oder epaper) setzen."
			log_close 1; exit 1 ;;
	esac
fi

NAME="$(anzeige_get "$TYP" name)" || {
	err "Unbekannter Anzeigetyp: $TYP"
	err "Bekannt sind: $(anzeigen_liste)"
	log_close 2; exit 2
}

BUSSE="$(anzeige_get "$TYP" busse)"
QUELLE="$(anzeige_get "$TYP" quelle)"
INSTALLER="$(anzeige_get "$TYP" installer)"
PRUEFE="$(anzeige_get "$TYP" pruefe)"
HINWEIS="$(anzeige_get "$TYP" hinweis)"

info "Anzeige:    $NAME"
info "Aufloesung: $(anzeige_get "$TYP" breite)x$(anzeige_get "$TYP" hoehe), \
$(anzeige_get "$TYP" fps) Bilder/s"
info "Busse:      ${BUSSE:-keine}"
[ -n "$HINWEIS" ] && info "Hinweis:    $HINWEIS"
log ""

# --- Gruppen --------------------------------------------------------------
#
# Ein Nachweis, dessen Ergebnis von den Rechten des Aufrufers abhaengt,
# misst nicht das System. Auf dem Testgeraet meldete `aplay -l` als Nutzer
# `dietpi` "keine Soundkarten gefunden", waehrend /proc/asound/cards die
# Karte laengst fuehrte -- der Nutzer war schlicht nicht in der Gruppe
# `audio`. Wer das nicht einrichtet, sucht den Fehler beim Treiber.
gruppen_richten() {
	_gr_user="${SUDO_USER:-${CHIMERA_USER:-}}"
	[ -n "$_gr_user" ] || return 0
	[ "$_gr_user" = root ] && return 0

	for _gr_g in audio spi gpio i2c; do
		# Nur Gruppen anfassen, die es auf diesem System gibt.
		getent group "$_gr_g" >/dev/null 2>&1 || continue
		if id -nG "$_gr_user" 2>/dev/null | tr ' ' '\n' | grep -qx "$_gr_g"; then
			continue
		fi
		if is_dry_run; then
			info "[wuerde aufnehmen] $_gr_user in Gruppe $_gr_g"
			continue
		fi
		if usermod -aG "$_gr_g" "$_gr_user" 2>/dev/null; then
			info "$_gr_user in Gruppe $_gr_g aufgenommen"
			bestand_merke gruppe "$_gr_g" "$_gr_user"
		else
			warn "Konnte $_gr_user nicht in Gruppe $_gr_g aufnehmen."
		fi
	done

	# Die Gruppenzugehoerigkeit wirkt erst in einer neuen Anmeldung. Das
	# zu verschweigen wuerde den naechsten Nachweis fehlschlagen lassen,
	# obwohl alles richtig eingerichtet ist.
	if bestand_hat gruppe audio 2>/dev/null; then
		info "Hinweis: Gruppen wirken erst nach neuer Anmeldung."
		info "  Sofort pruefbar mit: sg audio -c 'aplay -l'"
	fi
}

# --- Ist schon alles fertig? ----------------------------------------------
#
# Idempotenz heisst nicht "tut nichts, wenn eine Marke existiert", sondern
# "prueft den Zustand". Eine Marke kann luegen, ein Nachweis nicht.
if [ -n "$PRUEFE" ] && sh -c "$PRUEFE" >/dev/null 2>&1; then
	log "Die Anzeige ist bereits eingerichtet und nachweisbar."
	info "Nachweis: $PRUEFE"
	# Auch hier: Die Anzeige kann laufen und die Gruppen trotzdem fehlen
	# -- etwa bei einem neu angelegten Nutzer. Idempotent heisst, den
	# Zustand herzustellen, nicht ihn beim ersten Treffer aufzugeben.
	gruppen_richten
	log_close 0; exit 0
fi

# --- Busse in der Bootkonfiguration ---------------------------------------

busse_setzen() {
	[ -n "$BUSSE" ] || return 0
	[ -f "$BOOT_CFG" ] || {
		err "Keine Bootkonfiguration gefunden ($BOOT_CFG)."
		return 1
	}

	# Erst sichern, dann anfassen. Auf einem Geraet ohne Bildschirm kostet
	# eine kaputte Bootkonfiguration den Ausbau der SD-Karte.
	#
	# Im Trockenlauf wird NICHT gesichert: Es gibt nichts zu sichern, wenn
	# nichts geaendert wird. Eine Sicherung im Trockenlauf waere selbst
	# eine Aenderung.
	if ! is_dry_run; then
		backup_file "$BOOT_CFG" || {
			err "Sicherung fehlgeschlagen — es wird nichts geaendert."
			return 1
		}
	fi

	_bs_neu=0
	for _bs_b in $BUSSE; do
		case "$_bs_b" in
			spi) _bs_zeile="dtparam=spi=on" ;;
			*)   _bs_zeile="dtparam=${_bs_b}=on" ;;
		esac

		if grep -q "^${_bs_zeile}$" "$BOOT_CFG" 2>/dev/null; then
			info "schon gesetzt: $_bs_zeile"
			continue
		fi

		if is_dry_run; then
			info "[wuerde anhaengen] $_bs_zeile"
			continue
		fi

		printf '%s\n' "$_bs_zeile" >>"$BOOT_CFG"
		info "gesetzt: $_bs_zeile"
		_bs_neu=$((_bs_neu + 1))
	done

	# Der HAT braucht den Tonausgang des Boards nicht -- er bringt einen
	# eigenen Codec mit. DietPi setzt audio=off; das bleibt so, es stoert
	# nicht. Erwaehnt wird es, damit niemand spaeter danach sucht.
	grep -q "^dtparam=audio=off" "$BOOT_CFG" 2>/dev/null && \
		info "dtparam=audio=off bleibt — der HAT hat einen eigenen Codec."

	ANZAHL_NEU="$_bs_neu"
	return 0
}

ANZAHL_NEU=0
log "Busse"
busse_setzen || { log_close 2; exit 2; }
log ""

# --- Herstellertreiber ----------------------------------------------------

treiber_holen_und_bauen() {
	[ -n "$QUELLE" ] || {
		info "Kein Herstellertreiber noetig fuer diese Anzeige."
		return 0
	}

	_tb_dir="$QUELLEN/$TYP"

	log "Treiberquelle"
	netz_git "$QUELLE" "$_tb_dir" || return 1

	# Im Trockenlauf wurde nichts geholt -- dann auf die Datei zu pruefen
	# hiesse, das eigene Nichtstun als Fehler zu melden.
	if is_dry_run; then
		info "[wuerde ausfuehren] $INSTALLER (aus $_tb_dir)"
		info "[wuerde danach pruefen] $PRUEFE"
		return 0
	fi

	[ -f "$_tb_dir/$INSTALLER" ] || {
		err "Herstellerinstaller fehlt: $_tb_dir/$INSTALLER"
		err "Hat sich der Aufbau des Fremdrepos geaendert?"
		return 1
	}

	log ""
	log "Herstellerinstaller"
	info "Aufruf:  $INSTALLER"
	info "Quelle:  $_tb_dir"

	if is_dry_run; then
		info "[wuerde ausfuehren] bash $INSTALLER"
		return 0
	fi

	# Bauwerkzeug, bevor der Fremdinstaller anfaengt.
	#
	# Gelernt auf echter Hardware: Der Hersteller installiert `make` und
	# `gcc` nur in einem seiner beiden Pfade. Auf Raspberry Pi OS sind sie
	# vorinstalliert, auf DietPi nicht -- dort scheitert er bei Schritt 3
	# von 8 mit "make: Kommando nicht gefunden", nachdem er schon Pakete
	# nachgeladen hat. Ein fremder Installer ist eben fremder Code
	# (Regel 5f): Wir pruefen seine Voraussetzungen selbst, statt uns
	# darauf zu verlassen, dass er es tut.
	_tb_fehlt=""
	for _tb_c in make gcc dtc; do
		have_cmd "$_tb_c" || _tb_fehlt="$_tb_fehlt $_tb_c"
	done
	if [ -n "$_tb_fehlt" ]; then
		info "Bauwerkzeug fehlt:$_tb_fehlt — wird nachgeholt."
		netz_apt build-essential device-tree-compiler || {
			err "Bauwerkzeug nicht installierbar."
			return 1
		}
		for _tb_c in make gcc; do
			have_cmd "$_tb_c" || {
				err "$_tb_c fehlt weiterhin — der Treiberbau wuerde scheitern."
				return 1
			}
		done
	fi

	# Der Installer fragt "Proceed? [y/N]" und liest von der Standard-
	# eingabe. Ein 'y' hineinzureichen ist hier zulaessig, WEIL vorher
	# gefragt wurde und die Sicherung steht -- nicht, um die Frage zu
	# umgehen (Regel 10k: die Entscheidung trifft ein Mensch, aber nur
	# einmal).
	_tb_log="${CHIMERA_LOG_DIR:-./logs}/hersteller-$(date '+%Y%m%d-%H%M%S').log"
	mkdir -p "$(dirname "$_tb_log")" 2>/dev/null || _tb_log=/dev/null
	if printf 'y\n' | (cd "$_tb_dir" && bash "$INSTALLER") 2>&1 | tee "$_tb_log"; then
		_tb_rc=0
	else
		_tb_rc=$?
	fi

	info "Ausgabe des Herstellerlaufs: $_tb_log"

	# Der Exitcode allein ist nicht das Urteil -- der Hersteller meldet
	# Erfolg, auch wenn das Modul erst nach einem Neustart laedt. Aber er
	# darf auch nicht ignoriert werden: Beim ersten echten Lauf scheiterte
	# der Bau an fehlendem `make`, und dieses Modul meldete trotzdem
	# "eingerichtet, nur noch nicht nachweisbar". Das ist Beschoenigung,
	# und genau die Fehlerklasse aus Regel 8a.
	#
	# Deshalb wird jetzt am ERGEBNIS unterschieden: Gibt es das gebaute
	# Kernelmodul? Wenn nein, ist es ein Fehlschlag -- egal was der
	# Exitcode sagt und egal ob ein Neustart bevorsteht.
	if [ "$_tb_rc" != 0 ]; then
		warn "Herstellerinstaller endete mit Exitcode $_tb_rc."
	fi

	if ! find /lib/modules/"$(uname -r)" -name 'snd-soc-whisplay*' 2>/dev/null |
	     head -1 | grep -q .; then
		err "Das Kernelmodul wurde nicht gebaut."
		err "Grund steht in: $_tb_log"
		_tb_grund="$(grep -iE 'command not found|Kommando nicht gefunden|No such file|error:' \
			"$_tb_log" 2>/dev/null | head -3)"
		[ -n "$_tb_grund" ] && printf '%s\n' "$_tb_grund" | sed 's/^/    /' >&2
		return 1
	fi

	info "Kernelmodul gebaut."
	return 0
}

if ! treiber_holen_und_bauen; then
	err "Treiber konnte nicht eingerichtet werden."
	# Nur auf eine Sicherung verweisen, die es wirklich gibt. Ein Verweis
	# auf einen Rueckweg, den niemand angelegt hat, ist schlimmer als
	# keiner (Regel 8a).
	_sicherung="$(ls -1t "$BOOT_CFG".chimera-*.bak 2>/dev/null | head -1)"
	[ -n "$_sicherung" ] && err "Rueckweg: $_sicherung"
	log_close 2; exit 2
fi


# --- Nachweis -------------------------------------------------------------

log ""
log "Nachweis"

if [ -z "$PRUEFE" ]; then
	info "Fuer diese Anzeige gibt es keinen automatischen Nachweis."
	log_close 0; exit 0
fi

if is_dry_run; then
	info "[wuerde pruefen] $PRUEFE"
	log_close 0; exit 0
fi

if sh -c "$PRUEFE" >/dev/null 2>&1; then
	log "Ergebnis: $NAME eingerichtet und nachgewiesen."
	info "Nachweis: $PRUEFE"
	_alsa="$(anzeige_get "$TYP" alsa_karte)"
	[ -n "$_alsa" ] && info "ALSA-Karte: $_alsa"
	gruppen_richten
	log_close 0; exit 0
fi

# Nicht nachweisbar ist nicht dasselbe wie gescheitert: Overlay und
# Kernelmodul laden erst beim naechsten Start. Das wird gesagt, statt
# Erfolg zu behaupten oder Fehlschlag zu melden.
gruppen_richten
log "Ergebnis: eingerichtet, aber noch nicht nachweisbar."
warn "Das ist der Normalfall direkt nach der Installation: Overlay und"
warn "Kernelmodul werden beim Start geladen."
warn ""
warn "  sudo reboot"
warn ""
warn "Danach pruefen:"
warn "  $PRUEFE"
[ "$ANZAHL_NEU" -gt 0 ] && warn "  ($ANZAHL_NEU neue Zeile(n) in $BOOT_CFG)"
log_close 3
exit 3
