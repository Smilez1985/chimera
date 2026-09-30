#!/bin/sh
# Chimera installer -- Modul 10: preflight.
#
# Aendert NICHTS. Es erfasst, meldet und urteilt. Das ist Absicht: Dieses
# Modul muss auf einem fremden Geraet gefahrlos laufen koennen, bevor
# irgendjemand ihm zutraut, in /boot zu schreiben.
#
# Exitcode:
#   0  Board und Betriebssystem erkannt, unterstuetzt, es kann weitergehen
#   1  kein passendes Profil -- es geht weiter, aber ohne Boardwissen:
#      erkannt-aber-noch-nicht-unterstuetzt (Radxa vor der Portierung)
#      oder gar nicht erkannt und vom Nutzer bestaetigt (Regel 10k)
#   2  der Nutzer hat abgelehnt, oder es war niemand da, der zustimmen
#      konnte (nicht-interaktiv ohne CHIMERA_ASSUME_YES)
#
# Es wird nicht abgebrochen, weil ein Board unbekannt ist -- unbekannt
# heisst ungetestet, nicht unvereinbar (Regel 10k). Abgebrochen wird nur,
# wenn die Entscheidung darueber niemand getroffen hat.

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/detect.sh"
. "$_HERE/lib/profiles.sh"

# --- Erfassen -------------------------------------------------------------

# Wenn direkt aufgerufen (nicht ueber chimera-install), eigenes Protokoll.
[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "preflight" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

BOARD="$(detect_board)"
OS="$(detect_os)"
BOOT="$(detect_boot)"
OVERLAY_DIR="$(detect_overlay_dir)"
KVER="$(read_file /proc/sys/kernel/osrelease 2>/dev/null | tr -d '\n' || uname -r)"

WHISPLAY_RAW="$(detect_whisplay)"
WHISPLAY_STATE="${WHISPLAY_RAW%%|*}"
_wr="${WHISPLAY_RAW#*|}"
WHISPLAY_PID="${_wr%%|*}"
WHISPLAY_VER="${_wr#*|}"

HEADERS_DIR="/lib/modules/$KVER/build"
HEADERS_OK=no
if have_dir "$HEADERS_DIR"; then HEADERS_OK=yes; fi

BOOTCONFIG=no
if have_file "/boot/config-$KVER"; then BOOTCONFIG=yes; fi

WM8960=absent
if have_cmd modinfo && [ -z "$CHIMERA_ROOT" ]; then
	if modinfo snd-soc-wm8960 >/dev/null 2>&1; then WM8960=present; fi
else
	# Im Test oder ohne modinfo: nach der Moduldatei suchen.
	if [ -d "$(rootpath "/lib/modules/$KVER")" ] && \
	   find "$(rootpath "/lib/modules/$KVER")" -name 'snd-soc-wm8960.ko*' 2>/dev/null | grep -q .; then
		WM8960=file_only
	fi
fi

MEM_MB=""
if _mi="$(read_file /proc/meminfo 2>/dev/null)"; then
	MEM_MB="$(printf '%s\n' "$_mi" | awk '/^MemTotal:/{printf "%d", $2/1024}')"
fi

# --- Berichten ------------------------------------------------------------

# Preflight aendert ohnehin nichts -- im Trockenlauf ist es also
# identisch. Das wird gesagt, statt die Option stillschweigend zu
# ignorieren: eine Option ohne Wirkung ist ein offenes Ende.
log "Chimera preflight"
is_dry_run && info "(preflight aendert nie etwas -- Betriebsart ohne Folgen)"
log ""
log "Board und System"
info "Board:          $BOARD ($(profile_get "$BOARD" name))"
info "Betriebssystem: $OS"
info "Bootmethode:    $BOOT"
info "Overlays:       ${OVERLAY_DIR:-nicht gefunden}"
info "Kernel:         $KVER"
[ -n "$MEM_MB" ] && info "Speicher:       ${MEM_MB} MB"
log ""

log "Whisplay HAT"
case "$WHISPLAY_STATE" in
	present) info "erkannt (product_id=${WHISPLAY_PID:-?} product_ver=${WHISPLAY_VER:-?})" ;;
	foreign) warn "Fremder HAT im EEPROM -- kein PiSugar-Board" ;;
	absent)  info "kein EEPROM lesbar (HAT nicht aufgesteckt oder ohne EEPROM)" ;;
esac
if [ "$WHISPLAY_STATE" = present ]; then
	warn "Revision V1 gegen V2 ist am EEPROM noch nicht unterscheidbar."
	warn "Auf V1 fuehrt die Button-Leitung 5 V -- ein Tastendruck kann das"
	warn "Board stromlos schalten. Vor dem ersten Tastendruck klaeren."
fi
if whisplay_soundcard_live; then
	info "Soundkarte ist im laufenden Geraetebaum aktiv"
fi
log ""

log "Datentraeger"
_root_dev="$(read_file /proc/cmdline 2>/dev/null | tr ' ' '\n' | grep '^root=' | head -1 || true)"
info "root: ${_root_dev:-unbekannt}"
case "$_root_dev" in
	*mmcblk*p*|*mmcblk*)
		if printf '%s' "$_root_dev" | grep -q 'mmcblk0'; then
			info "Hinweis: Systemtraeger pruefen (SD oder eMMC?) -- 'lsblk' zeigt es."
		fi ;;
esac
if have_dir /sys/block/mmcblk1 || have_dir /sys/block/sda; then
	info "Weiterer Datentraeger vorhanden -- moeglicher Rettungsweg."
else
	warn "Kein zweiter Datentraeger erkennbar. Laeuft das System vom eMMC,"
	warn "gibt es bei kaputter Bootkonfiguration nichts auszubauen -- die"
	warn "Rettung braucht dann Herstellerwerkzeug an einem PC."
fi
log ""

log "Bauvoraussetzungen"
info "Kernel-Headers:   $HEADERS_OK ($HEADERS_DIR)"
info "/boot/config-*:   $BOOTCONFIG"
info "snd-soc-wm8960:   $WM8960"
log ""

# --- Urteilen -------------------------------------------------------------

SUPPORTED="$(profile_get "$BOARD" supported)"

# Regel 10k: Unbekannt heisst ungetestet, nicht unvereinbar. Es wird
# gewarnt und gefragt, nicht verboten. Was NICHT passiert: ein geratenes
# Profil. Ohne Profil bleiben die bootnahen Schritte aus -- die Gefahr
# liegt im Eingriff, nicht in der Erkennung.
NO_PROFILE=0

case "$BOARD" in
unknown|unsupported_rpi|unsupported_radxa)
	NO_PROFILE=1
	warn "Board nicht erkannt oder ohne Profil: $BOARD"
	log ""
	log "Gefunden wurde:"
	info "model:      $(read_dt /proc/device-tree/model 2>/dev/null || echo '(nichts)')"
	info "compatible: $(read_dt_list /proc/device-tree/compatible 2>/dev/null | tr '\n' ' ' || echo '(nichts)')"
	log ""
	log "Profile gibt es fuer:"
	info "raspberrypi,model-zero-2-w   (Raspberry Pi Zero 2 W)"
	info "radxa,zero3w                 (Radxa ZERO 3W)"
	log ""
	warn "Das heisst nicht, dass es nicht laeuft -- es heisst, dass es"
	warn "niemand geprueft hat. Ungeprueft bleiben: Anzeige (SPI-Bus und"
	warn "-Takt), Audio (Codec, ALSA-Vorlage) und die Overlays."
	warn ""
	warn "Ohne Profil wird KEIN Overlay in die Bootkonfiguration"
	warn "geschrieben -- dieser eine Schritt kostet bei einem Geraet ohne"
	warn "Bildschirm sonst den Ausbau der SD-Karte. Die betroffenen Module"
	warn "melden sich ab, statt zu raten."
	warn ""
	warn "Laeuft es bei dir: bitte melden, dann wird daraus ein Profil."
	log ""
	if ! confirm_risk "Ungetestetes Board -- auf eigene Gefahr fortfahren?"; then
		err "Abgebrochen. Ein bekanntes Profil waehlt --force-board."
		log_close 2; exit 2
	fi
	warn "Fortgesetzt auf eigene Gefahr (Board ohne Profil)."
	;;
esac

if [ "$OS" = unknown ]; then
	warn "Betriebssystem nicht erkannt. DietPi ist die getestete Grundlage."
fi
if [ "$OS" != dietpi ]; then
	info "Hinweis: DietPi ist das Betriebssystem der Wahl (headless, schlank)."
fi
if [ "$BOOT" = unknown ]; then
	warn "Bootmethode nicht erkannt -- Modul 60 kann das Overlay nicht sicher"
	warn "einhaengen. Bitte melden, mit dem Inhalt von /boot."
fi

# Header-Strategie aus dem Profil, abgeglichen mit der Kombinationstabelle.
if [ "$HEADERS_OK" = no ]; then
	_stage="$(profile_get "$BOARD" header_stage)"
	_combo="$(combo_lookup "$BOARD" "$OS" "$KVER" || true)"
	if [ -n "$_combo" ]; then
		info "Headers fehlen. Bekannte Kombination: ${_combo%%|*}"
		info "  (${_combo#*|})"
	else
		warn "Headers fehlen, und die laufende Kernelversion steht in keiner"
		warn "bekannten Kombination. Bekannt sind:"
		known_combos | while IFS='|' read -r b o k pkg _; do
			[ "$b" = "$BOARD" ] || continue
			warn "  $o / $k  ->  $pkg"
		done
		warn "Modul 30 wird hier abbrechen, statt ein Paket zu erraten."
	fi
	[ "$_stage" = 2 ] && info "Header-Stufe 2: Paketquelle $(profile_get "$BOARD" header_pool)"
fi

if [ "$WM8960" = absent ] && [ "$(profile_get "$BOARD" wm8960_builtin)" != yes ]; then
	warn "snd-soc-wm8960 nicht gefunden. Der Whisplay-Treiber setzt den Codec"
	warn "voraus und ergaenzt ihn nur -- Modul 40 muss ihn dann bauen."
fi

# Das Sprachmodell liegt grundsaetzlich ausserhalb (Architekturregel 5):
# weder der BCM2837 noch der RK3566 koennen es tragen. Beim RK3566 hilft
# auch die NPU nicht -- Rockchips rknn-llm unterstuetzt sie gar nicht.
# Der Speicher entscheidet nur, ob STT und TTS gleichzeitig geladen
# bleiben koennen oder rotieren muessen.
info "Sprachmodell laeuft ausserhalb (Anthropic-Abo oder Ollama im Netz)."
if [ -n "$MEM_MB" ] && [ "$MEM_MB" -lt 1024 ]; then
	info "Unter 1 GB: STT und TTS muessen voraussichtlich rotieren,"
	info "  also nie gleichzeitig geladen sein."
fi

log ""
if [ "$NO_PROFILE" = 1 ]; then
	log "Ergebnis: kein Profil fuer dieses Board -- Lauf auf eigene Gefahr."
	log "  Boardabhaengige Module melden sich ab, statt zu raten (Regel 10k)."
	log_close 1; exit 1
fi

if [ "$SUPPORTED" = yes ]; then
	log "Ergebnis: $BOARD wird unterstuetzt."
	log_close 0; exit 0
fi

log "Ergebnis: $BOARD ist erkannt, aber noch nicht unterstuetzt."
log "  $(profile_get "$BOARD" notes)"
log_close 1; exit 1
