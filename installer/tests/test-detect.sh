#!/bin/sh
# Tests fuer Erkennung und atomares Schreiben.
#
# Laeuft ohne Zielhardware: erfundene Gerätebaum-Dateien in einem temporaeren
# Wurzelverzeichnis, CHIMERA_ROOT zeigt darauf.
#
# Jeder Test, der eine Regression absichert, hat eine GEGENPROBE — sonst
# weiss man nicht, ob er ueberhaupt etwas messen kann (Architekturregel 9).

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0; FAIL=0

# Eigenes Spielfeld, unabhaengig von TMPDIR. Die Testumgebung darf nicht
# an derselben Klippe scheitern, die sie prueft — und ein kaputtes TMPDIR
# ist keine Theorie: in der Entwicklungsumgebung dieses Projekts zeigte es
# auf ein Verzeichnis, das nicht existierte, und mktemp lieferte einen
# leeren Pfad mit Exitcode 1.
: "${CHIMERA_TESTDIR:=/tmp}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
TMPDIR="$CHIMERA_TESTDIR"; export TMPDIR

ok()   { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"
	else bad "$1 — erwartet '$3', bekam '$2'"; fi
}

# Baut ein erfundenes Wurzelverzeichnis.
#   $1 model, $2 compatible (Leerzeichen -> Nullbytes), $3 os-marker
mkroot() {
	R="$(mktemp -d)"
	mkdir -p "$R/proc/device-tree" "$R/etc" "$R/boot"
	[ -n "${1:-}" ] && printf '%s\0' "$1" >"$R/proc/device-tree/model"
	if [ -n "${2:-}" ]; then
		: >"$R/proc/device-tree/compatible"
		for c in $2; do printf '%s\0' "$c" >>"$R/proc/device-tree/compatible"; done
	fi
	case "${3:-}" in
		dietpi)  printf 'x\n' >"$R/boot/dietpi.txt" ;;
		raspios) printf 'ID=debian\nPRETTY_NAME="Raspberry Pi OS"\n' >"$R/etc/os-release" ;;
		radxa)   mkdir -p "$R/usr/bin"; : >"$R/usr/bin/rsetup" ;;
		debian)  printf 'ID=debian\n' >"$R/etc/os-release" ;;
	esac
	echo "$R"
}

load() {
	CHIMERA_ROOT="$1"; export CHIMERA_ROOT
	# shellcheck source=/dev/null
	. "$HERE/lib/common.sh"; . "$HERE/lib/detect.sh"; . "$HERE/lib/profiles.sh"
}

echo "== Boarderkennung =="

R="$(mkroot "Raspberry Pi Zero 2 W Rev 1.0" "raspberrypi,model-zero-2-w brcm,bcm2837" dietpi)"
load "$R"; check "Pi Zero 2 W ueber compatible" "$(detect_board)" "rpi_zero2w"
check "DietPi erkannt" "$(detect_os)" "dietpi"
rm -rf "$R"

R="$(mkroot "Radxa ZERO 3W" "radxa,zero3w rockchip,rk3566" dietpi)"
load "$R"; check "Radxa Zero 3W ueber compatible" "$(detect_board)" "radxa_zero3w"
rm -rf "$R"

# Der Kern: ein FREMDES Radxa-Board darf nicht auf das Zero-3W-Profil
# fallen. Genau das tut der Hersteller-Installer mit model == *Radxa*.
R="$(mkroot "Radxa ROCK 5B" "radxa,rock-5b rockchip,rk3588" dietpi)"
load "$R"; check "fremdes Radxa -> unsupported, NICHT zero3w" "$(detect_board)" "unsupported_radxa"
rm -rf "$R"

R="$(mkroot "Raspberry Pi 4 Model B Rev 1.4" "raspberrypi,4-model-b brcm,bcm2711" raspios)"
load "$R"; check "fremder Pi -> unsupported" "$(detect_board)" "unsupported_rpi"
check "RasPi OS erkannt" "$(detect_os)" "raspios"
rm -rf "$R"

R="$(mkroot "" "" "")"
load "$R"; check "nichts erkennbar -> unknown" "$(detect_board)" "unknown"
rm -rf "$R"

# Nur Klartextname, kein compatible — Rueckfall muss greifen.
R="$(mkroot "Raspberry Pi Zero 2 W Rev 1.0" "" dietpi)"
load "$R"; check "Rueckfall ueber model" "$(detect_board)" "rpi_zero2w"
rm -rf "$R"

echo "== Betriebssystem =="
R="$(mkroot "Radxa ZERO 3W" "radxa,zero3w" radxa)"
load "$R"; check "Radxa-Abbild ueber rsetup" "$(detect_os)" "radxa_debian"
rm -rf "$R"

# DietPi setzt auf Debian auf — os-release allein wuerde es als Debian
# ausgeben. Der DietPi-Marker muss Vorrang haben.
R="$(mkroot "Radxa ZERO 3W" "radxa,zero3w" debian)"
printf 'x\n' >"$R/boot/dietpi.txt"
load "$R"; check "DietPi hat Vorrang vor ID=debian" "$(detect_os)" "dietpi"
rm -rf "$R"

echo "== Bootmethode =="
R="$(mkroot "Raspberry Pi Zero 2 W" "raspberrypi,model-zero-2-w" dietpi)"
mkdir -p "$R/boot/firmware"; : >"$R/boot/firmware/config.txt"
load "$R"; check "config.txt" "$(detect_boot)" "config_txt"
rm -rf "$R"

R="$(mkroot "Radxa ZERO 3W" "radxa,zero3w" radxa)"
mkdir -p "$R/boot/extlinux"; : >"$R/boot/extlinux/extlinux.conf"
load "$R"; check "extlinux" "$(detect_boot)" "extlinux"
rm -rf "$R"

R="$(mkroot "Radxa ZERO 3W" "radxa,zero3w" dietpi)"
: >"$R/boot/armbianEnv.txt"
load "$R"; check "u-boot-Skript" "$(detect_boot)" "uboot_script"
rm -rf "$R"

R="$(mkroot "Radxa ZERO 3W" "radxa,zero3w" dietpi)"
load "$R"; check "keine Bootdatei -> unknown" "$(detect_boot)" "unknown"
rm -rf "$R"

echo "== Whisplay-EEPROM =="
R="$(mkroot "Raspberry Pi Zero 2 W" "raspberrypi,model-zero-2-w" dietpi)"
mkdir -p "$R/proc/device-tree/hat"
printf 'PiSugar\0' >"$R/proc/device-tree/hat/vendor"
printf '0x0001\0'  >"$R/proc/device-tree/hat/product_id"
load "$R"; check "PiSugar-HAT erkannt" "$(detect_whisplay)" "present|0x0001|"
rm -rf "$R"

R="$(mkroot "Raspberry Pi Zero 2 W" "raspberrypi,model-zero-2-w" dietpi)"
load "$R"; check "kein HAT" "$(detect_whisplay)" "absent||"
rm -rf "$R"

echo "== Profile =="
load "$(mkroot "" "" "")"
check "Pi ist unterstuetzt"        "$(profile_get rpi_zero2w supported)"   "yes"
check "Radxa noch nicht"           "$(profile_get radxa_zero3w supported)" "not_yet"
check "Pi: Header-Stufe 1"         "$(profile_get rpi_zero2w header_stage)" "1"
check "Radxa: Header-Stufe 2"      "$(profile_get radxa_zero3w header_stage)" "2"
check "Radxa: SPI3"                "$(profile_get radxa_zero3w spi_bus)"   "3"
check "unbekanntes Board"          "$(profile_get foo supported)"          "no"

echo "== Kombinationstabelle =="
_c="$(combo_lookup radxa_zero3w dietpi "6.12.0-current-rockchip64" || true)"
check "rockchip64-Kernel gefunden" "${_c%%|*}" "linux-headers-current-rockchip64"
_c="$(combo_lookup radxa_zero3w dietpi "6.6.0-exotisch" || true)"
check "unbekannter Kernel -> leer" "${_c:-LEER}" "LEER"

echo "== Atomares Schreiben (I3) =="
R="$(mktemp -d)"; load "$R"
printf 'alt\n' >"$R/ziel.txt"
printf 'neu\n' | write_atomic "$R/ziel.txt" 2>/dev/null
check "Inhalt ersetzt" "$(cat "$R/ziel.txt")" "neu"

# Leere Eingabe darf das Ziel nicht leeren. Gefunden durch genau diesen
# Test: cat schreibt bei leerem stdin nichts, mv legt die leere Datei
# ueber das Ziel, Exitcode 0 -- stiller Datenverlust.
printf 'wichtig\n' >"$R/boot.txt"
if write_atomic "$R/boot.txt" </dev/null 2>/dev/null; then
	bad "leere Eingabe haette abgelehnt werden muessen"
else
	ok "leere Eingabe wird abgelehnt"
fi
check "Zieldatei NICHT geleert" "$(cat "$R/boot.txt")" "wichtig"

# Gegenprobe: ohne die Pruefung WIRD die Datei geleert. Belegt, dass der
# Test etwas messen kann und nicht nur zufaellig gruen ist.
printf 'wichtig\n' >"$R/naiv.txt"
_nt="$(mktemp "$R/.naiv.XXXXXX")"
cat >"$_nt" </dev/null; mv -f "$_nt" "$R/naiv.txt"
if [ -s "$R/naiv.txt" ]; then
	bad "Gegenprobe: naiver Weg haette leeren muessen"
else
	ok "Gegenprobe: ohne Pruefung wird die Datei tatsaechlich geleert"
fi

# Ausdruecklich leer schreiben muss moeglich bleiben.
printf 'x\n' >"$R/leer.txt"
CHIMERA_ALLOW_EMPTY=1 write_atomic "$R/leer.txt" </dev/null 2>/dev/null || true
if [ -s "$R/leer.txt" ]; then bad "ALLOW_EMPTY wirkte nicht"
else ok "ALLOW_EMPTY erlaubt bewusst leere Datei"; fi

# mktemp mit explizitem Template ignoriert TMPDIR -- genau deshalb ist die
# Sidecar-Variante richtig. Dieser Test haelt das Verhalten fest, damit ein
# spaeterer Umbau auf mktemp ohne Template auffaellt.
printf 'wichtig\n' >"$R/tmpdir.txt"
printf 'neu\n' >"$R/.quelle"
if TMPDIR="$R/gibt-es-nicht" write_atomic "$R/tmpdir.txt" <"$R/.quelle" 2>/dev/null; then
	ok "kaputtes TMPDIR stoert das Sidecar-Verfahren nicht"
else
	bad "Sidecar sollte von TMPDIR unabhaengig sein"
fi
check "Inhalt trotz kaputtem TMPDIR" "$(cat "$R/tmpdir.txt")" "neu"
rm -rf "$R"

echo "== Sicherung =="
R="$(mktemp -d)"; load "$R"
printf 'original\n' >"$R/boot.txt"
backup_file "$R/boot.txt" >/dev/null 2>&1
_bk="$(find "$R" -name 'boot.txt.chimera-*.bak' | head -1)"
if [ -n "$_bk" ]; then ok "Sicherung angelegt"
else bad "keine Sicherung angelegt"; fi
check "Sicherung hat den Originalinhalt" "$(cat "$_bk" 2>/dev/null)" "original"
backup_file "$R/gibtsnicht.txt" >/dev/null 2>&1 && ok "fehlende Datei ist kein Fehler" \
	|| bad "fehlende Datei haette durchgehen muessen"
rm -rf "$R"

echo "== Protokoll =="
R="$(mktemp -d)"; load "$R"
CHIMERA_LOG_DIR="$R/logs"; CHIMERA_LOGFILE=""
log_open "test" >/dev/null 2>&1
if [ -n "$CHIMERA_LOGFILE" ] && [ -f "$CHIMERA_LOGFILE" ]; then ok "Protokolldatei angelegt"
else bad "keine Protokolldatei"; fi
log "eine Zeile" >/dev/null
warn "eine Warnung" 2>/dev/null
log_close 0 >/dev/null
grep -q "eine Zeile" "$CHIMERA_LOGFILE" 2>/dev/null && ok "Ausgabe landet im Protokoll" || bad "Ausgabe fehlt im Protokoll"
grep -q "WARN: eine Warnung" "$CHIMERA_LOGFILE" 2>/dev/null && ok "Warnung landet im Protokoll" || bad "Warnung fehlt"
grep -q "Erfolg (0)" "$CHIMERA_LOGFILE" 2>/dev/null && ok "auch Erfolg wird festgehalten" || bad "Erfolg nicht vermerkt"
CHIMERA_LOGFILE=""
rm -rf "$R"

echo ""
printf 'Ergebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
