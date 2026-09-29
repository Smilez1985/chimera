#!/bin/sh
# Chimera installer — Erkennung von Board, Betriebssystem und Bootmethode.
#
# Drei UNABHAENGIGE Achsen. Derselbe Chip unter DietPi und unter Radxas
# Abbild sind zwei Installationsfaelle, weil Overlay-Ablage und
# Bootkonfiguration sich unterscheiden. Wer das in einer Variablen
# zusammenfasst, baut sich die Fallunterscheidungen doppelt.
#
# Alle Abfragen laufen ueber CHIMERA_ROOT, damit die Erkennung ohne
# Zielhardware pruefbar ist.

# --- Board ----------------------------------------------------------------
#
# Reihenfolge: erst die konkreten Kennungen aus compatible, dann der
# Klartextname als Rueckfall.
#
# Bewusst NICHT so wie der Hersteller-Installer, der
#     [[ "$model" == *"Radxa"* ]] && echo radxa_zero3w
# macht und damit JEDES Radxa-Board auf ein Profil legt, das nur zum
# Zero 3W passt. Ein falsches Overlay in der Bootkonfiguration kostet den
# Ausbau der SD-Karte.
detect_board() {
	_db_model="$(read_dt /proc/device-tree/model || true)"
	_db_compat="$(read_dt_list /proc/device-tree/compatible || true)"

	# Radxa Zero 3W / 3E — rk3566
	if printf '%s\n' "$_db_compat" | grep -qi '^radxa,zero3'; then
		echo rpi_placeholder >/dev/null   # kein Treffer auf Pi-Zweig
		echo radxa_zero3w; return 0
	fi

	# Raspberry Pi Zero 2 W — bcm2837/bcm2710
	if printf '%s\n' "$_db_compat" | grep -qi '^raspberrypi,model-zero-2-w'; then
		echo rpi_zero2w; return 0
	fi

	# Rueckfall ueber den Klartextnamen, aber nur fuer die Modelle, die wir
	# wirklich unterstuetzen — kein Sammelmuster.
	case "$_db_model" in
		*"Raspberry Pi Zero 2 W"*) echo rpi_zero2w;    return 0 ;;
		*"Radxa ZERO 3W"*|*"Radxa Zero 3W"*) echo radxa_zero3w; return 0 ;;
	esac

	# Erkennbar verwandt, aber nicht unterstuetzt: ehrlich benennen, statt
	# das naechstbeste Profil zu nehmen.
	case "$_db_model" in
		*"Raspberry Pi"*) echo unsupported_rpi;   return 0 ;;
		*"Radxa"*)        echo unsupported_radxa; return 0 ;;
	esac

	echo unknown
}

# --- Betriebssystem -------------------------------------------------------
#
# DietPi ist die Zielplattform. Es setzt auf Debian auf, deshalb reicht
# os-release allein nicht — DietPi meldet sich dort als Debian.
detect_os() {
	if have_file /boot/dietpi.txt || have_file /boot/dietpi/.version \
	   || have_dir /boot/dietpi; then
		echo dietpi; return 0
	fi

	_do_rel="$(read_file /etc/os-release || true)"

	case "$_do_rel" in
		*"Raspbian"*|*"Raspberry Pi OS"*) echo raspios; return 0 ;;
	esac

	# Radxas eigenes Abbild bringt rsetup mit.
	if have_file /usr/bin/rsetup || have_file /etc/radxa-release; then
		echo radxa_debian; return 0
	fi

	if have_file /etc/armbian-release; then
		echo armbian; return 0
	fi

	case "$_do_rel" in
		*"ID=debian"*) echo debian; return 0 ;;
		*"ID=ubuntu"*) echo ubuntu; return 0 ;;
	esac

	echo unknown
}

# --- Bootmethode ----------------------------------------------------------
#
# Der eigentliche DietPi-Stolperstein: Der Hersteller-Installer ruft
# u-boot-update und erwartet /boot/extlinux/extlinux.conf. Das ist Radxas
# Struktur, nicht DietPis. Deshalb ermitteln statt voraussetzen.
detect_boot() {
	if have_file /boot/firmware/config.txt; then
		echo config_txt; return 0
	fi
	if have_file /boot/config.txt; then
		echo config_txt; return 0
	fi
	if have_file /boot/extlinux/extlinux.conf; then
		echo extlinux; return 0
	fi
	if have_file /boot/boot.scr || have_file /boot/boot.cmd \
	   || have_file /boot/armbianEnv.txt || have_file /boot/dietpiEnv.txt; then
		echo uboot_script; return 0
	fi
	echo unknown
}

# --- Wo liegen Overlays? --------------------------------------------------
detect_overlay_dir() {
	for d in /boot/overlays /boot/firmware/overlays /boot/dtbo \
	         /boot/dtb/rockchip/overlay /boot/dtb/overlay; do
		have_dir "$d" && { echo "$d"; return 0; }
	done
	echo ""
}

# --- Whisplay HAT ---------------------------------------------------------
#
# Der HAT hat ein EEPROM, das der Kernel in den Gerätebaum einhaengt. Damit
# ist die Platine erkennbar, ohne draufzuschauen.
#
# OFFEN: ob sich daraus V1 gegen V2 unterscheiden laesst. Bekannt ist nur
# product_id 0x0001. Solange das nicht geklaert ist, bleibt die Warnung
# stehen — auf V1 fuehrt die Button-Leitung 5 V und ein Tastendruck kann
# das Board stromlos schalten.
detect_whisplay() {
	_dw_vendor="$(read_dt /proc/device-tree/hat/vendor || true)"
	_dw_pid="$(read_dt /proc/device-tree/hat/product_id || true)"
	_dw_pver="$(read_dt /proc/device-tree/hat/product_ver || true)"

	if [ -z "$_dw_vendor" ]; then
		echo "absent||"
		return 0
	fi
	case "$_dw_vendor" in
		PiSugar*|pisugar*) echo "present|$_dw_pid|$_dw_pver" ;;
		*)                echo "foreign|$_dw_pid|$_dw_pver" ;;
	esac
}

# Ist die Whisplay-Soundkarte schon im laufenden Gerätebaum?
whisplay_soundcard_live() {
	_wl="$(read_dt /proc/device-tree/sound/compatible || true)"
	case "$_wl" in
		*"pisugar,whisplay-soundcard"*) return 0 ;;
	esac
	return 1
}
