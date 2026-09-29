#!/bin/sh
# Chimera installer — Modul 10: preflight.
#
# Aendert NICHTS. Es erfasst, meldet und urteilt. Das ist Absicht: Dieses
# Modul muss auf einem fremden Geraet gefahrlos laufen koennen, bevor
# irgendjemand ihm zutraut, in /boot zu schreiben.
#
# Exitcode:
#   0  Board und Betriebssystem erkannt, unterstuetzt, es kann weitergehen
#   1  erkannt, aber noch nicht unterstuetzt (z. B. Radxa vor der Portierung)
#   2  nicht erkannt — Abbruch mit Auskunft, kein Rateversuch
#
# Der Unterschied zwischen 1 und 2 ist wichtig: 1 heisst "wir wissen, was du
# hast, aber noch nicht wie", 2 heisst "wir wissen nicht, was du hast".

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/detect.sh"
. "$_HERE/lib/profiles.sh"

# --- Erfassen -------------------------------------------------------------

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

log "Chimera preflight"
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
	foreign) warn "Fremder HAT im EEPROM — kein PiSugar-Board" ;;
	absent)  info "kein EEPROM lesbar (HAT nicht aufgesteckt oder ohne EEPROM)" ;;
esac
if [ "$WHISPLAY_STATE" = present ]; then
	warn "Revision V1 gegen V2 ist am EEPROM noch nicht unterscheidbar."
	warn "Auf V1 fuehrt die Button-Leitung 5 V — ein Tastendruck kann das"
	warn "Board stromlos schalten. Vor dem ersten Tastendruck klaeren."
fi
if whisplay_soundcard_live; then
	info "Soundkarte ist im laufenden Geraetebaum aktiv"
fi
log ""

log "Bauvoraussetzungen"
info "Kernel-Headers:   $HEADERS_OK ($HEADERS_DIR)"
info "/boot/config-*:   $BOOTCONFIG"
info "snd-soc-wm8960:   $WM8960"
log ""

# --- Urteilen -------------------------------------------------------------

SUPPORTED="$(profile_get "$BOARD" supported)"

case "$BOARD" in
unknown)
	err "Board nicht erkannt."
	err ""
	err "Erwartet wird eine dieser Kennungen in /proc/device-tree/compatible:"
	err "  raspberrypi,model-zero-2-w   (Raspberry Pi Zero 2 W)"
	err "  radxa,zero3w                 (Radxa ZERO 3W)"
	err ""
	err "Gefunden wurde:"
	err "  model:      $(read_dt /proc/device-tree/model 2>/dev/null || echo '(nichts)')"
	err "  compatible: $(read_dt_list /proc/device-tree/compatible 2>/dev/null | tr '\n' ' ' || echo '(nichts)')"
	err ""
	err "Es wird nicht geraten: ein falsches Overlay in der Bootkonfiguration"
	err "kostet im schlimmsten Fall den Ausbau der SD-Karte."
	exit 2
	;;
unsupported_rpi)
	err "Raspberry Pi erkannt, aber nicht das Zero 2 W."
	err "Unterstuetzt wird derzeit nur der Pi Zero 2 W."
	exit 2
	;;
unsupported_radxa)
	err "Radxa-Board erkannt, aber nicht das ZERO 3W."
	err "Das Profil des ZERO 3W passt nicht auf andere Radxa-Boards."
	exit 2
	;;
esac

if [ "$OS" = unknown ]; then
	warn "Betriebssystem nicht erkannt. DietPi ist die getestete Grundlage."
fi
if [ "$OS" != dietpi ]; then
	info "Hinweis: DietPi ist das Betriebssystem der Wahl (headless, schlank)."
fi
if [ "$BOOT" = unknown ]; then
	warn "Bootmethode nicht erkannt — Modul 60 kann das Overlay nicht sicher"
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
	warn "voraus und ergaenzt ihn nur — Modul 40 muss ihn dann bauen."
fi

# Speicherlage: entscheidet, ob das Sprachmodell lokal laufen kann.
if [ -n "$MEM_MB" ] && [ "$MEM_MB" -lt 1024 ]; then
	info "Unter 1 GB Speicher: Sprache laeuft lokal, das Sprachmodell nicht."
	info "  Anbieter-Registry auf Ollama im eigenen Netz einstellen."
fi

log ""
if [ "$SUPPORTED" = yes ]; then
	log "Ergebnis: $BOARD wird unterstuetzt."
	exit 0
fi

log "Ergebnis: $BOARD ist erkannt, aber noch nicht unterstuetzt."
log "  $(profile_get "$BOARD" notes)"
exit 1
