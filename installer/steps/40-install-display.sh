#!/bin/sh
# Chimera installer -- Modul 40: Anzeige erkennen, Busse, Ton.
#
# Das Panel (LCD, LED, Taste) spricht Chimera seit 11.10.2026 SELBST
# (src/chimera/displays/, DESIGN 5f-Ergaenzung) -- dafuer wird nichts
# installiert ausser den Python-Paketen aus display.json (Schritt 50).
# Dieser Schritt tut drei Dinge:
#
#   1. erkennen, welche Anzeige steckt (Treiberpaket, braucht freie
#      Leitungen -- deshalb vor dem Dienst), und es festhalten (state/anzeige)
#   2. die Busse in der Bootkonfiguration sicherstellen -- NUR die
#      neutralen (spi, i2c_arm). i2s=on kommt nicht in die config.txt:
#      Die SD-Karte wandert zwischen Boards, und mit i2s sind GPIO18-21
#      PCM -- GamePi13-Backlight (19) und E-Paper-Versorgung (18) waeren tot.
#   3. den TON der Anzeige, wenn sie einen hat: Herstellermodul bauen
#      (Kernelmodul + Overlay-Datei, Regel I4/5f: Commit und Pruefsumme
#      fest), ALSA-Konfiguration, und die Overlays ZUR LAUFZEIT laden
#      (`python3 -m chimera.displays ton <typ>`) -- idempotent, der Boot-
#      Abgleich tut dasselbe bei jedem Start.
#
# Was Chimera um den Herstellerinstaller legt, weil er es nicht tut:
#   * Bootkonfiguration vorher sichern (Regel 10i: nie ohne Rueckweg),
#     und was er hineinschreibt (i2s=on, dtoverlay=...) wieder herausnehmen
#   * festhalten, was sich geaendert hat (Regel 10e)
#   * nicht-interaktiv laufen, ohne die Rueckfrage zu verschlucken
#   * das ERGEBNIS pruefen, nicht den Exitcode (Regel 10j)
#   * Downloads pausieren statt abbrechen (lib/network.sh)
#
# Exitcode:
#   0  Anzeige festgehalten, Busse da, Ton (falls vorhanden) nachgewiesen
#   1  nichts erkannt / Anzeige bekannt, aber nicht unterstuetzt
#   2  abgebrochen -- Voraussetzung fehlt oder niemand hat zugestimmt
#   3  Neustart noetig (ein Bus kam neu in die Bootkonfiguration)

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/detect.sh"
. "$_HERE/lib/profiles.sh"
. "$_HERE/lib/network.sh"
. "$_HERE/lib/display.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/module.sh"

CHIMERA_STEP="40-install-display"; export CHIMERA_STEP
# Profil-Puffer von lib/display.sh (je Lauf) am Ende wegraeumen.
trap 'display_cache_leeren' EXIT

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "anzeige" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

BOARD="$(detect_board)"
BOOT_CFG="$(rootpath /boot/firmware/config.txt)"
[ -f "$BOOT_CFG" ] || BOOT_CFG="$(rootpath /boot/config.txt)"

# Wohin Fremdquelltext geholt wird. Nicht nach /tmp: Ein zweiter Lauf soll
# nicht erneut laden muessen (Idempotenz).
QUELLEN="${CHIMERA_QUELLEN:-$(rootpath "$CHIMERA_QUELLEN_PFAD")}"

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
	err "Kernelmodul -- das geht nur als Verwalter."
	err ""
	err "  sudo sh $0"
	err ""
	err "Was es tun WUERDE, zeigt ein Trockenlauf ohne Rechte:"
	err "  CHIMERA_MODE=dry sh $0"
	log_close 2; exit 2
fi

# --- Welche Anzeige? ------------------------------------------------------
#
# Die Erkennung lebt im Treiberpaket (DISPLAYS.md Abschnitt 4): ST7789-Kennung ueber
# SPI (Pflicht), Codec am I2C (eindeutig), Overlay/ALSA/Modul (nur
# "eingerichtet", waehlt nicht). Sie braucht freie Leitungen: Haelt sie der
# laufende Dienst, meldet sie "belegt" -- das ist ein Befund, kein "kein
# Panel". CHIMERA_ANZEIGE sticht (Regel 10g: der Mensch darf vorgeben,
# geraten wird nie).

TYP="${CHIMERA_ANZEIGE:-}"
DISPLAY_TYP=""; DISPLAY_QUELLE=""; DISPLAY_BEFUND=""

if [ -n "$TYP" ]; then
	info "Anzeige vorgegeben: $TYP"
else
	if ! display_detect_possible; then
		warn "I2C ist nicht aktiv -- der Codec der Whisplay kann sich nicht melden."
		warn "Das ist keine Aussage ueber die Hardware, sondern ueber die"
		warn "Sichtbarkeit: Ohne i2c_arm bleibt nur die Panel-Kennung."
	fi
	# Ohne Subshell, damit Grund und Belege hier ankommen.
	display_detect >/dev/null 2>&1 || true
	display_belege | while IFS= read -r _db_z; do info "  $_db_z"; done
	TYP="${DISPLAY_TYP:-}"
	if [ -n "$TYP" ]; then
		info "Erkannt: $TYP ($(display_quelle))"
	else
		warn "Keine Anzeige gewaehlt: ${DISPLAY_QUELLE:-Erkennung nicht moeglich}"
		warn "Es wird nicht geraten (Regel 10g). Mit CHIMERA_ANZEIGE=<typ>"
		warn "laesst sich eine Anzeige vorgeben. Bekannt: $(display_list)"
		log_close 1; exit 1
	fi
fi

display_profil_lesbar "$TYP" || {
	err "Unbekannter Anzeigetyp: $TYP"
	err "Bekannt sind: $(display_list)"
	log_close 2; exit 2
}
NAME="$(display_get "$TYP" name)"

BUSSE="$(display_get "$TYP" busse)"
QUELLE="$(display_get "$TYP" quelle)"
INSTALLER="$(display_get "$TYP" installer)"
QUELLE_COMMIT="$(display_get "$TYP" commit)"
QUELLE_SHA="$(display_get "$TYP" sha256)"
PRUEFE="$(display_get "$TYP" pruefe)"
HINWEIS="$(display_get "$TYP" hinweis)"
ALSA_KARTE="$(display_get "$TYP" alsa_karte)"
TON_APT="$(display_get "$TYP" ton_apt)"
TON_MODUL="$(display_get "$TYP" kernelmodul)"
TON_OVERLAYS="$(display_get "$TYP" ton_dtoverlay)"
ASOUND_CONF="$(display_get "$TYP" asound_conf)"

info "Anzeige:    $NAME"
info "Aufloesung: $(display_get "$TYP" breite)x$(display_get "$TYP" hoehe), \
$(display_get "$TYP" fps) Bilder/s"
info "Busse:      ${BUSSE:-keine}"
[ -n "$HINWEIS" ] && info "Hinweis:    $HINWEIS"
[ -n "$ALSA_KARTE" ] && info "Ton:        ALSA-Karte $ALSA_KARTE (Overlays zur Laufzeit: $TON_OVERLAYS)"
[ -n "$QUELLE_COMMIT" ] && info "Tonquelle:  festgelegt auf Commit $QUELLE_COMMIT"
log ""

# --- Entscheidung festhalten ----------------------------------------------
#
# Welche Anzeige es ist, entscheidet DIESER Schritt (Erkennung oder
# CHIMERA_ANZEIGE). Schritt 50 braucht die Antwort, um den Python-Treiber
# der Anzeige ins venv zu holen -- erraten soll er sie nicht ein zweites
# Mal (Regel 10g). Geschrieben wird vor jedem Ausstieg, auch vor dem
# "schon eingerichtet": Gerade dann fehlte bisher der Treiber im venv.
ANZEIGE_DATEI="$(rootpath "$CHIMERA_STATE")/anzeige"
if is_dry_run; then
	info "[wuerde merken] Anzeige $TYP in $CHIMERA_STATE/anzeige"
elif [ "$(cat "$ANZEIGE_DATEI" 2>/dev/null || true)" != "$TYP" ]; then
	manifest_init || true
	if printf '%s\n' "$TYP" | write_atomic "$ANZEIGE_DATEI"; then
		manifest_record datei "$ANZEIGE_DATEI" \
			"$(sha256sum "$ANZEIGE_DATEI" 2>/dev/null | cut -d' ' -f1)"
	else
		err "Anzeige nicht festhaltbar: $ANZEIGE_DATEI"
		log_close 2; exit 2
	fi
fi

# Und dieselbe Antwort fuer den Dienst, der state/ nicht lesen darf: eine
# Umgebungsdatei im RAM (CHIMERA_RUN_ANZEIGE), die seine Unit liest. Kein
# Manifest-Eintrag: tmpfs ist nach dem naechsten Boot leer.
RUN_ANZEIGE="$(rootpath "$CHIMERA_RUN_ANZEIGE")"
if is_dry_run; then
	info "[wuerde schreiben] $CHIMERA_RUN_ANZEIGE (CHIMERA_ANZEIGE=$TYP)"
elif [ "$(cat "$RUN_ANZEIGE" 2>/dev/null || true)" != "CHIMERA_ANZEIGE=$TYP" ]; then
	mkdir -p "$(dirname "$RUN_ANZEIGE")" 2>/dev/null || true
	if printf 'CHIMERA_ANZEIGE=%s\n' "$TYP" | write_atomic "$RUN_ANZEIGE"; then
		chmod 644 "$RUN_ANZEIGE" 2>/dev/null || true
	else
		warn "Laufzeit-Uebergabe nicht geschrieben: $CHIMERA_RUN_ANZEIGE -- der Dienst liest state/anzeige nicht und liefe blind."
	fi
fi

# --- Gruppen --------------------------------------------------------------
#
# Ein Nachweis, dessen Ergebnis von den Rechten des Aufrufers abhaengt,
# misst nicht das System. Auf dem Testgeraet meldete `aplay -l` als Nutzer
# `dietpi` "keine Soundkarten gefunden", waehrend /proc/asound/cards die
# Karte laengst fuehrte -- der Nutzer war schlicht nicht in der Gruppe
# `audio`. Wer das nicht einrichtet, sucht den Fehler beim Treiber.
group_ensure() {
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
			manifest_record gruppe "$_gr_g" "$_gr_user"
		else
			warn "Konnte $_gr_user nicht in Gruppe $_gr_g aufnehmen."
		fi
	done

	# Die Gruppenzugehoerigkeit wirkt erst in einer neuen Anmeldung. Das
	# zu verschweigen wuerde den naechsten Nachweis fehlschlagen lassen,
	# obwohl alles richtig eingerichtet ist.
	if manifest_has gruppe audio 2>/dev/null; then
		info "Hinweis: Gruppen wirken erst nach neuer Anmeldung."
		info "  Sofort pruefbar mit: sg audio -c 'aplay -l'"
	fi
}

# --- Ist schon alles fertig? ----------------------------------------------
#
# Idempotenz heisst nicht "tut nichts, wenn eine Marke existiert", sondern
# "prueft den Zustand". Eine Marke kann luegen, ein Nachweis nicht.
# Fuer das Panel: der Geraeteknoten (SPI an). Fuer den Ton: die ALSA-
# Karte -- die gibt es erst, wenn Modul, Overlay-Datei UND Laufzeitladen
# zusammenkommen; `ton_bereit` unten prueft genau das Ergebnis.
ton_bereit() {
	[ -n "$ALSA_KARTE" ] || return 0
	read_file /proc/asound/cards 2>/dev/null | grep -qi -- "$ALSA_KARTE"
}
if [ -n "$PRUEFE" ] && sh -c "$PRUEFE" >/dev/null 2>&1 && ton_bereit; then
	log "Die Anzeige ist bereits eingerichtet und nachweisbar."
	info "Nachweis: $PRUEFE${ALSA_KARTE:+ und ALSA-Karte $ALSA_KARTE}"
	# Auch hier: Die Anzeige kann laufen und die Gruppen trotzdem fehlen
	# -- etwa bei einem neu angelegten Nutzer. Idempotent heisst, den
	# Zustand herzustellen, nicht ihn beim ersten Treffer aufzugeben.
	group_ensure
	log_close 0; exit 0
fi

# --- Busse in der Bootkonfiguration ---------------------------------------

bus_enable() {
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
	# ... und nur dann, wenn wirklich etwas fehlt. Eine Sicherung bei
	# jedem Lauf fuellt /boot/firmware mit Kopien derselben Datei.
	_bs_fehlt=0
	for _bs_b in $BUSSE; do
		grep -q "^dtparam=${_bs_b}=on$" "$BOOT_CFG" 2>/dev/null || _bs_fehlt=1
	done
	if ! is_dry_run && [ "$_bs_fehlt" -eq 1 ]; then
		backup_file "$BOOT_CFG" || {
			err "Sicherung fehlgeschlagen -- es wird nichts geaendert."
			return 1
		}
	fi

	_bs_neu=0
	for _bs_b in $BUSSE; do
		case "$_bs_b" in
			spi) _bs_zeile="dtparam=spi=on" ;;
			*)   _bs_zeile="dtparam=${_bs_b}=on" ;;
		esac

		# Ueber manifest_line, nicht per `printf >>`. Die Funktion tut
		# dasselbe -- pruefen, anhaengen, Trockenlauf beachten -- und
		# traegt den Eintrag zusaetzlich ins Manifest, mitsamt der
		# Unterscheidung `vorher_da` gegen `neu`.
		#
		# Vorher stand hier ein eigenes `printf >>`: dieselbe Aufgabe,
		# zweiter Weg, und der benutzte war der, der nichts festhielt.
		# Damit war die Zeile in der Bootkonfiguration nicht
		# zurueckbaubar (Architekturregel 10l).
		_bs_vorher=0
		grep -q "^${_bs_zeile}$" "$BOOT_CFG" 2>/dev/null && _bs_vorher=1

		manifest_line "$BOOT_CFG" "$_bs_zeile" || {
			err "Konnte $_bs_zeile nicht setzen."
			return 1
		}
		[ "$_bs_vorher" -eq 0 ] && ! is_dry_run &&
			_bs_neu=$((_bs_neu + 1))
	done

	# Der HAT braucht den Tonausgang des Boards nicht -- er bringt einen
	# eigenen Codec mit. DietPi setzt audio=off; das bleibt so, es stoert
	# nicht. Erwaehnt wird es, damit niemand spaeter danach sucht.
	grep -q "^dtparam=audio=off" "$BOOT_CFG" 2>/dev/null && \
		info "dtparam=audio=off bleibt -- der HAT hat einen eigenen Codec."

	ANZAHL_NEU="$_bs_neu"
	return 0
}

# Die Bootkonfiguration bleibt NEUTRAL: Was der Herstellerinstaller dort
# fuer den Ton eintraegt (i2s=on, dtoverlay=whisplay-soundcard), nimmt
# dieser Schritt wieder heraus -- der Ton wird zur Laufzeit geladen, nach
# der Erkennung (DISPLAYS.md Abschnitt 4, Kartentausch zwischen Boards). Eine Zeile,
# die VOR Chimera schon drin stand, bleibt (Manifest kennt sie nicht).
boot_neutral() {
	[ -f "$BOOT_CFG" ] || return 0
	_bn_weg=""
	for _bn_z in "dtparam=i2s=on" $(for _o in $TON_OVERLAYS; do echo "dtoverlay=$_o"; done); do
		grep -qxF "$_bn_z" "$BOOT_CFG" 2>/dev/null || continue
		if manifest_has_exact zeile "$BOOT_CFG" "vorher_da:$_bn_z" 2>/dev/null; then
			info "$_bn_z stand vor Chimera in der Bootkonfiguration -- bleibt."
			continue
		fi
		_bn_weg="$_bn_weg $_bn_z"
	done
	[ -n "$_bn_weg" ] || return 0
	if is_dry_run; then
		info "[wuerde entfernen] aus $BOOT_CFG:$_bn_weg (Ton laedt zur Laufzeit)"
		return 0
	fi
	# Erst sichern (Regel 10i) -- diese Zeilen zu entfernen ist ein Eingriff
	# in die Bootkonfiguration wie jeder andere.
	backup_file "$BOOT_CFG" || { err "Sicherung fehlgeschlagen -- es wird nichts geaendert."; return 1; }
	_bn_tmp="$(tmp_path bootcfg)" || return 1
	cp "$BOOT_CFG" "$_bn_tmp" || return 1
	for _bn_z in $_bn_weg; do
		grep -vxF "$_bn_z" "$_bn_tmp" >"$_bn_tmp.neu" || true
		mv "$_bn_tmp.neu" "$_bn_tmp"
	done
	# write_atomic verweigert eine leere Eingabe (Regel I3/8a): Eine leere
	# Bootkonfiguration waere ein totes Geraet. Hier KEINE zweite Pruefung
	# -- sie stuende neben der einen Stelle, die das entscheidet.
	write_atomic "$BOOT_CFG" <"$_bn_tmp" || {
		err "Bereinigte Bootkonfiguration nicht geschrieben -- Original bleibt."
		rm -f "$_bn_tmp"; return 1; }
	rm -f "$_bn_tmp"
	info "Aus der Bootkonfiguration genommen (Ton laedt zur Laufzeit):$_bn_weg"
	ANZAHL_NEU=$((ANZAHL_NEU + 1))
	return 0
}

ANZAHL_NEU=0
log "Busse"
bus_enable || { log_close 2; exit 2; }
boot_neutral || { log_close 2; exit 2; }
log ""

# --- Ton: Herstellermodul bauen, Konfiguration, Laufzeit laden -----------
#
# Nur fuer Anzeigen mit ALSA-Karte (Whisplay). Der Hersteller liefert das
# Kernelmodul (snd-soc-whisplay-soundcard) als Quelltext und baut es mit
# seinem install.sh -- das wird AUFGERUFEN, nicht nachgebaut (Regel 10g),
# aber an Commit und Pruefsumme gebunden (I4, 5f). Seine Nebenwirkungen in
# der Bootkonfiguration nimmt boot_neutral() zurueck; geladen wird zur
# Laufzeit, so wie es der Boot-Abgleich bei jedem Start tut.

ton_quelle_dir="$QUELLEN/$TYP"

ton_modul_da() {
	[ -n "$TON_MODUL" ] || return 1
	[ -n "$(kernel_module_datei "${TON_MODUL}*")" ]
}
ton_overlay_da() {
	for _to_o in $TON_OVERLAYS; do
		[ -f "$(rootpath /boot/firmware/overlays/$_to_o.dtbo)" ] || \
		[ -f "$(rootpath /boot/overlays/$_to_o.dtbo)" ] || return 1
	done
	return 0
}

ton_einrichten() {
	[ -n "$ALSA_KARTE" ] || { info "Diese Anzeige hat keinen Ton."; return 0; }

	log "Ton ($ALSA_KARTE)"

	# Systempakete des Tons (amixer/aplay, dtoverlay, speexrate) -- nur was fehlt.
	if [ -n "$TON_APT" ]; then
		_te_fehlt=""
		for _te_p in $TON_APT; do
			manifest_package_present "$_te_p" || _te_fehlt="$_te_fehlt $_te_p"
		done
		if [ -z "$_te_fehlt" ]; then
			info "Systempakete vorhanden: $TON_APT"
		elif is_dry_run; then
			info "[wuerde holen]$_te_fehlt"
		else
			manifest_apt $_te_fehlt || { err "Systempakete fuer den Ton nicht installierbar:$_te_fehlt"; return 1; }
		fi
	fi

	# Modul und Overlay-Datei: gebaut heisst, beide liegen da. Dann wird
	# der Herstellerinstaller NICHT erneut gerufen (er wuerde apt-get
	# update, make und config.txt anfassen -- jedes Mal).
	if ton_modul_da && ton_overlay_da; then
		info "Kernelmodul $TON_MODUL und Overlay $TON_OVERLAYS vorhanden."
	elif [ -z "$QUELLE" ]; then
		err "Ton braucht Kernelmodul $TON_MODUL, aber das Modul nennt keine Quelle."
		return 1
	else
		log "Tonquelle"
		network_git "$QUELLE" "$ton_quelle_dir" "" "$QUELLE_COMMIT" || return 1
		if is_dry_run; then
			info "[wuerde ausfuehren] $INSTALLER (aus $ton_quelle_dir)"
		else
			[ -f "$ton_quelle_dir/$INSTALLER" ] || {
				err "Herstellerinstaller fehlt: $ton_quelle_dir/$INSTALLER"
				err "Hat sich der Aufbau des Fremdrepos geaendert?"
				return 1
			}
			# Bevor fremder Code als root laeuft: stimmt er mit dem
			# festgelegten Stand ueberein? (I4, 5f)
			fremddatei_pruefen "$ton_quelle_dir/$INSTALLER" "$QUELLE_SHA" || return 1

			# Bauwerkzeug, bevor der Fremdinstaller anfaengt (gelernt auf
			# DietPi: make/gcc fehlen, der Hersteller setzt sie voraus).
			_te_bw=""
			for _te_c in make gcc dtc; do have_cmd "$_te_c" || _te_bw="$_te_bw $_te_c"; done
			if [ -n "$_te_bw" ]; then
				info "Bauwerkzeug fehlt:$_te_bw -- wird nachgeholt."
				network_apt build-essential device-tree-compiler || { err "Bauwerkzeug nicht installierbar."; return 1; }
				for _te_c in make gcc; do have_cmd "$_te_c" || { err "$_te_c fehlt weiterhin."; return 1; }; done
			fi

			log ""
			log "Herstellerinstaller (Ton)"
			info "Aufruf:  $INSTALLER"
			info "Quelle:  $ton_quelle_dir"
			# Der Installer fragt "Proceed? [y/N]". Ein 'y' ist zulaessig,
			# WEIL die Bootkonfiguration gesichert ist und boot_neutral
			# seine Eintraege gleich wieder herausnimmt (Regel 10k).
			_te_log="${CHIMERA_LOG_DIR:-./logs}/hersteller-ton-$(date '+%Y%m%d-%H%M%S').log"
			mkdir -p "$(dirname "$_te_log")" 2>/dev/null || _te_log=/dev/null
			if printf 'y\n' | (cd "$ton_quelle_dir" && bash "$INSTALLER") >"$_te_log" 2>&1; then
				_te_rc=0
			else
				_te_rc=$?
			fi
			info "Ausgabe des Herstellerlaufs: $_te_log"
			[ "$_te_rc" != 0 ] && warn "Herstellerinstaller endete mit Exitcode $_te_rc."

			# Am ERGEBNIS entscheiden (Regel 10j): Modul UND Overlay-Datei.
			if ! ton_modul_da; then
				err "Das Kernelmodul $TON_MODUL wurde nicht gebaut. Grund steht in: $_te_log"
				grep -iE 'command not found|Kommando nicht gefunden|No such file|error:' \
					"$_te_log" 2>/dev/null | head -3 | sed 's/^/    /' >&2
				return 1
			fi
			ton_overlay_da || { err "Overlay-Datei fehlt nach dem Herstellerlauf: $TON_OVERLAYS"; return 1; }
			manifest_has modul "$TON_MODUL" || manifest_record modul "$TON_MODUL" hersteller
			info "Kernelmodul gebaut, Overlay-Datei liegt."

			# Der Hersteller schreibt i2s=on und das Overlay in die
			# Bootkonfiguration und legt eine Warmup-Unit an, die Mixer
			# setzt. Beides uebernimmt Chimera selbst: Bootkonfiguration
			# neutral, Mixer beim Laden. Die Unit bleibt abgeschaltet
			# stehen (Herstellerbestand, nicht unserer).
			boot_neutral || return 1
		fi
	fi

	# Die Hersteller-Unit (whisplay-soundcard-warmup: wartet auf die Karte,
	# setzt Mixer 80/80) ist ueberfluessig -- Chimera setzt den Mixer beim
	# Laden selbst -- und sie liegt auch auf Karten, die der Hersteller-
	# installer frueher eingerichtet hat. Abschalten, nicht loeschen
	# (Herstellerbestand); am Ergebnis gemessen.
	if have_cmd systemctl && systemctl is-enabled whisplay-soundcard-warmup.service >/dev/null 2>&1; then
		if is_dry_run; then
			info "[wuerde abschalten] whisplay-soundcard-warmup.service (Chimera setzt den Mixer selbst)"
		else
			systemctl disable --now whisplay-soundcard-warmup.service >/dev/null 2>&1 || true
			if systemctl is-enabled whisplay-soundcard-warmup.service >/dev/null 2>&1; then
				warn "Hersteller-Unit whisplay-soundcard-warmup liess sich nicht abschalten."
			else
				info "Hersteller-Unit whisplay-soundcard-warmup abgeschaltet (Chimera setzt den Mixer selbst)."
			fi
		fi
	fi

	# ALSA-Konfiguration des Herstellers (dmix/dsnoop, default = Karte):
	# nur anlegen, wenn keine da ist -- eine fremde asound.conf gehoert
	# dem Nutzer.
	if [ -n "$ASOUND_CONF" ] && [ -f "$ton_quelle_dir/$ASOUND_CONF" ]; then
		_te_ac="$(rootpath /etc/asound.conf)"
		if [ -f "$_te_ac" ]; then
			info "/etc/asound.conf vorhanden -- bleibt."
		elif is_dry_run; then
			info "[wuerde anlegen] /etc/asound.conf aus $ASOUND_CONF"
		else
			write_atomic "$_te_ac" <"$ton_quelle_dir/$ASOUND_CONF" || { err "/etc/asound.conf nicht anlegbar."; return 1; }
			manifest_record datei "$_te_ac" "$(sha256sum "$_te_ac" 2>/dev/null | cut -d' ' -f1)"
			info "/etc/asound.conf angelegt (Herstellervorlage)."
		fi
	fi

	# Zur Laufzeit laden und nachweisen -- derselbe Weg wie beim Boot-Abgleich.
	if is_dry_run; then
		info "[wuerde laden] python3 -m chimera.displays ton $TYP"
		return 0
	fi
	_te_py="$(display_python)"
	if PYTHONPATH="$(display_src)" PYTHONDONTWRITEBYTECODE=1 "$_te_py" -m chimera.displays ton "$TYP" 2>&1 | sed 's/^/    /'; then
		info "Ton geladen und nachgewiesen: ALSA-Karte $ALSA_KARTE"
		return 0
	fi
	err "Ton nicht nachweisbar (ALSA-Karte $ALSA_KARTE fehlt nach dem Laden)."
	return 1
}

if ! ton_einrichten; then
	err "Ton konnte nicht eingerichtet werden."
	_sicherung="$(ls -1t "$BOOT_CFG".chimera-*.bak 2>/dev/null | head -1)"
	[ -n "$_sicherung" ] && err "Rueckweg Bootkonfiguration: $_sicherung"
	log_close 2; exit 2
fi
log ""

# --- Nachweis -------------------------------------------------------------

log "Nachweis"
if is_dry_run; then
	info "[wuerde pruefen] $PRUEFE${ALSA_KARTE:+ und ALSA-Karte $ALSA_KARTE}"
	log_close 0; exit 0
fi

if sh -c "$PRUEFE" >/dev/null 2>&1 && ton_bereit; then
	log "Ergebnis: $NAME eingerichtet und nachgewiesen."
	info "Nachweis: $PRUEFE${ALSA_KARTE:+ und ALSA-Karte $ALSA_KARTE}"
	group_ensure
	if [ "$ANZAHL_NEU" -gt 0 ]; then
		# Busse kamen neu in die Bootkonfiguration -- sie wirken erst nach
		# dem Start. Der Ton laeuft schon (Laufzeit), das Panel braucht SPI.
		warn "$ANZAHL_NEU Aenderung(en) an $BOOT_CFG wirken erst nach einem Neustart."
		log_close 3; exit 3
	fi
	log_close 0; exit 0
fi

group_ensure
if [ "$ANZAHL_NEU" -gt 0 ]; then
	log "Ergebnis: eingerichtet, aber noch nicht nachweisbar."
	warn "Busse in der Bootkonfiguration wirken erst nach einem Neustart."
	warn ""
	warn "  sudo reboot"
	warn ""
	warn "Danach pruefen:  $PRUEFE"
	log_close 3
	exit 3
fi
err "Nachweis fehlgeschlagen: $PRUEFE${ALSA_KARTE:+ / ALSA-Karte $ALSA_KARTE} -- ohne neue Bootzeilen."
err "Das ist kein Neustart-Fall, sondern ein Befund: Bus an, Geraet fehlt?"
log_close 1
exit 1
