#!/bin/sh
# Chimera installer -- Boardprofile.
#
# ALLES Boardabhaengige steht hier, nicht verstreut in Fallunterscheidungen
# quer durch die Module. Ein neues Board ist ein Eintrag in dieser Datei.
#
# Gleicher Gedanke wie bei der Anbieter-Registry (DESIGN.md Regel 5a) und
# aus demselben Grund: verteilte Fallunterscheidungen driften auseinander.
# In ZTB lag dieselbe Logik dreimal vor, zweimal unterschiedlich, monatelang
# unbemerkt.
#
# Felder:
#   supported        yes | not_yet    -- kein Platzhalter im Code, ein Zustand
#   header_stage     1 | 2            -- woher die Kernel-Headers kommen
#   header_pkg       Distributionspaket fuer Stufe 1
#   header_pool      Paketquelle fuer Stufe 2
#   spi_bus/cs/speed LCD-Anbindung
#   busse            welche Busse die Bootkonfiguration braucht. DREI, nicht
#                    einer: SPI traegt das Bild, I2C die Codec-Register und
#                    das HAT-EEPROM, I2S die Audiodaten. Ohne I2S kein Ton.
#   overlay_src      Quelldatei im Whisplay-Treiberpaket
#   conflicts        Overlays, die abgeschaltet werden muessen
#   wm8960_builtin   bringt der Kernel den Codec mit?
#   notes            was bei diesem Board besonders ist

profile_get() {
	_pg_board="$1"
	_pg_field="$2"

	case "$_pg_board" in
	rpi_zero2w)
		case "$_pg_field" in
		name)           echo "Raspberry Pi Zero 2 W" ;;
		supported)      echo "yes" ;;
		soc)            echo "bcm2837" ;;
		ram_mb)         echo "512" ;;
		header_stage)   echo "1" ;;
		header_pkg)     echo "raspberrypi-kernel-headers" ;;
		header_pool)    echo "" ;;
		spi_bus)        echo "0" ;;
		spi_cs)         echo "0" ;;
		spi_speed)      echo "100000000" ;;
		busse)          echo "spi i2c_arm i2s" ;;
		overlay_src)    echo "dts/whisplay-soundcard.dts" ;;
		conflicts)      echo "" ;;
		wm8960_builtin) echo "yes" ;;
		llm_local)      echo "no" ;;
		notes)          echo "Entwicklungsziel. Headers kommen aus dem Distributionspaket." ;;
		*)              echo "" ;;
		esac
		;;

	radxa_zero3w)
		case "$_pg_field" in
		name)           echo "Radxa ZERO 3W" ;;
		supported)      echo "not_yet" ;;
		soc)            echo "rk3566" ;;
		ram_mb)         echo "1024-8192" ;;
		# DietPi baut fuer dieses Board keinen eigenen Kernel, sondern
		# nutzt Armbians rockchip64-Familie. Die Headers-Pakete existieren
		# im Armbian-Index -- deshalb Stufe 2 und nicht Stufe 3.
		header_stage)   echo "2" ;;
		header_pkg)     echo "linux-headers-current-rockchip64" ;;
		header_pool)    echo "https://apt.armbian.com" ;;
		spi_bus)        echo "3" ;;
		spi_cs)         echo "0" ;;
		spi_speed)      echo "48000000" ;;
		# Dieselben drei Busse, andere Schreibweise in der
		# Bootkonfiguration -- Armbian kennt kein dtparam. Modul 40
		# muss das beim Radxa ueber die Overlay-Datei loesen.
		busse)          echo "spi i2c i2s" ;;
		overlay_src)    echo "dts/whisplay-soundcard-radxa-zero3w.dts" ;;
		conflicts)      echo "rk3568-i2s3-m0.dtbo wm8960-radxa-zero3.dtbo" ;;
		wm8960_builtin) echo "unknown" ;;
		llm_local)      echo "no" ;;   # RK3566: A55-Kerne zu langsam, NPU nicht von rknn-llm unterstuetzt
		notes)          echo "Portierungsziel. Headers aus Armbians rockchip64-Pool; Version muss exakt zur laufenden passen." ;;
		*)              echo "" ;;
		esac
		;;

	*)
		case "$_pg_field" in
		name)      echo "unbekannt" ;;
		supported) echo "no" ;;
		*)         echo "" ;;
		esac
		;;
	esac
}

# Bekannte Kombinationen von Board, Betriebssystem und Kernelversion.
#
# Der Hersteller-Installer bindet hart auf EINE Kernelversion und bricht
# sonst ab. Das ist ehrlich, aber unbequem: ein Kernelupdate macht die
# Installation unbaubar. Hier steht stattdessen eine Tabelle -- und eine
# unbekannte Version fuehrt zu einem Abbruch MIT Auskunft, nicht zu einem
# Rateversuch.
#
# Format: board|os|kernel-glob|header-paket|anmerkung
known_combos() {
	cat <<'EOF'
rpi_zero2w|dietpi|*|raspberrypi-kernel-headers|Stufe 1, aus dem Distributionspaket
rpi_zero2w|raspios|*|raspberrypi-kernel-headers|Stufe 1, aus dem Distributionspaket
radxa_zero3w|dietpi|*-current-rockchip64|linux-headers-current-rockchip64|Stufe 2, Armbian-Pool
radxa_zero3w|dietpi|*-edge-rockchip64|linux-headers-edge-rockchip64|Stufe 2, Armbian-Pool
radxa_zero3w|radxa_debian|*|linux-headers-*|Ausweichpfad, cli-Abbild ohne Desktop
EOF
}

# Passt die laufende Kernelversion zu einem bekannten Eintrag?
combo_lookup() {
	_cl_board="$1"; _cl_os="$2"; _cl_kver="$3"
	known_combos | while IFS='|' read -r b o k pkg note; do
		[ "$b" = "$_cl_board" ] || continue
		[ "$o" = "$_cl_os" ] || continue
		# shellcheck disable=SC2254
		case "$_cl_kver" in
			$k) printf '%s|%s\n' "$pkg" "$note"; return 0 ;;
		esac
	done
}
