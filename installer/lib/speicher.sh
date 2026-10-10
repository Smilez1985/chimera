#!/bin/sh
# Chimera installer -- Speicher: zram und Auslagerungsdatei (DESIGN Regel 5e).
#
# Mechanik uebernommen aus PiPortal (modules/05_swap.sh), dort auf derselben
# Hardware erprobt -- kein Nachbau:
#
#   zram          Paket zram-tools, Konfiguration /etc/default/zramswap
#                 (PERCENT/ALGO/PRIORITY), Dienst zramswap.service. Das
#                 Paketskript rechnet MemTotal * PERCENT / 100 und ruft
#                 `swapon -p PRIORITY /dev/zram0`.
#   Datei         DietPis eigenes Werkzeug dietpi-set_swapfile <MiB> <Pfad>.
#                 Es pflegt /etc/fstab und /boot/dietpi.txt selbst -- damit
#                 gibt es keine zweite Auslagerung neben DietPis, und der
#                 Firstboot dreht nichts zurueck.
#
# Groesse der Datei: Staffel nach Groesse des Systemdatentraegers (2/4/8/16
# GiB, PiPortal). Fuer einen Agenten-Harness ist viel Auslagerung OOM-Schutz,
# kein Luxus (Entscheidung smilez, 11.10.2026).
#
# Bekannte Grenze (DESIGN 5e): DietPis Werkzeug beginnt mit `swapoff -a` --
# das schaltet auch zram ab. Beim Ersetzen der Datei gibt es deshalb einen
# kurzen Moment ohne Auslagerung; danach wird zram sofort neu gestartet.
# Das passiert nur, wenn die Dateigroesse sich aendert.
#
# Logik hier, pruefbar ohne Hardware: alle Systemdateien ueber rootpath,
# Werkzeuge (systemctl, findmnt, lsblk, df) als Aufrufe, die ein Test als
# Funktion ersetzen kann.

: "${CHIMERA_ZRAM_PROZENT:=75}"
: "${CHIMERA_ZRAM_ALGO:=lz4}"
: "${CHIMERA_ZRAM_PRIO:=100}"
# Freier Platz, der nach dem Anlegen der Datei mindestens bleiben muss
# (PiPortal: 8 GiB). Ueberstimmbar fuer kleine Karten.
: "${CHIMERA_SWAP_RESERVE_MIB:=8192}"

SPEICHER_ZRAM_CONF=/etc/default/zramswap
SPEICHER_DIETPI_TOOL=/boot/dietpi/func/dietpi-set_swapfile
SPEICHER_DIETPI_TXT=/boot/dietpi.txt
SPEICHER_DATEI_VORGABE=/var/swap

# --- Messen ----------------------------------------------------------------

speicher_ram_kb() {
	awk '/^MemTotal:/ { print $2; exit }' "$(rootpath /proc/meminfo)" 2>/dev/null
}

# Groesse des Datentraegers, auf dem / liegt, in Byte. Leer = nicht messbar.
# Gemessen am Blockgeraet (sysfs, 512-Byte-Sektoren), nicht an df: df nennt
# die Partition, die Staffel richtet sich nach der Karte.
speicher_karte_bytes() {
	_kb_src="$(findmnt -no SOURCE / 2>/dev/null | head -n1)"
	[ -n "$_kb_src" ] || return 1
	_kb_pk="$(lsblk -no PKNAME "$_kb_src" 2>/dev/null | head -n1)"
	# Ohne Elterngeraet ist / selbst das ganze Geraet.
	[ -n "$_kb_pk" ] || _kb_pk="$(basename "$_kb_src")"
	_kb_s="$(cat "$(rootpath "/sys/class/block/$_kb_pk/size")" 2>/dev/null)"
	case "$_kb_s" in ""|*[!0-9]*) return 1 ;; esac
	printf '%s\n' "$((_kb_s * 512))"
}

# Staffel (PiPortal): dezimale GB wie auf der Karte aufgedruckt.
# $1 Byte, Ausgabe MiB.
speicher_staffel_mib() {
	_st_gb=$(( $1 / 1000000000 ))
	if   [ "$_st_gb" -ge 64 ]; then echo 16384
	elif [ "$_st_gb" -ge 32 ]; then echo 8192
	elif [ "$_st_gb" -ge 16 ]; then echo 4096
	else                            echo 2048
	fi
}

# Freier Platz auf / in MiB.
speicher_frei_mib() {
	_fr="$(df -Pk / 2>/dev/null | awk 'NR==2 { print $4 }')"
	case "$_fr" in ""|*[!0-9]*) return 1 ;; esac
	echo $((_fr / 1024))
}

# Eintrag aus /proc/swaps: "groesse_kb prioritaet" oder leer.
speicher_swap_eintrag() {
	awk -v n="$1" 'NR > 1 && $1 == n { print $3, $5; exit }' \
		"$(rootpath /proc/swaps)" 2>/dev/null
}

# Wert aus dietpi.txt (leer, wenn nicht da).
speicher_dietpi_wert() {
	sed -n "s/^[[:blank:]]*$1=//p" "$(rootpath "$SPEICHER_DIETPI_TXT")" 2>/dev/null | head -n1
}

speicher_zram_soll_bytes() {
	_zs_ram="$(speicher_ram_kb)"
	case "$_zs_ram" in ""|*[!0-9]*) return 1 ;; esac
	# Dieselbe Formel wie das zramswap-Skript von zram-tools.
	echo $((_zs_ram * 1024 * CHIMERA_ZRAM_PROZENT / 100))
}

speicher_zram_text() {
	cat <<EOF
# Von Chimera verwaltet (installer/steps/25-speicher.sh, DESIGN Regel 5e).
# Das Original liegt als Sicherung daneben und steht im Manifest.
ALGO=$CHIMERA_ZRAM_ALGO
PERCENT=$CHIMERA_ZRAM_PROZENT
PRIORITY=$CHIMERA_ZRAM_PRIO
EOF
}

# --- Fremde Einrichtungen --------------------------------------------------
#
# Zwei Verwalter fuer /dev/zram0 waeren zwei Systeme mit unklarem
# Verhalten. Der systemd-zram-generator (direkt oder ueber rpi-swap auf
# Raspberry Pi OS) belegt zram0 beim Booten -- dann wird nicht umgebaut,
# sondern abgebrochen und benannt. Ein Umstellen dieser Faelle ist ein
# offenes Ende (ROADMAP), kein stiller Weg.
speicher_fremd() {
	for _sf_p in rpi-swap systemd-zram-generator dphys-swapfile; do
		if manifest_package_present "$_sf_p"; then
			printf '%s\n' "$_sf_p"
			return 0
		fi
	done
	[ -e "$(rootpath /etc/systemd/zram-generator.conf)" ] && {
		echo "/etc/systemd/zram-generator.conf"; return 0; }
	return 1
}

# --- Auslagerungsdatei -----------------------------------------------------
#
# rc 0 Soll erreicht (oder war schon da), 1 Befund (nichts geaendert),
# 2 Abbruch.
speicher_datei() {
	_sd_tool="$(rootpath "$SPEICHER_DIETPI_TOOL")"
	if [ ! -x "$_sd_tool" ]; then
		warn "Kein DietPi ($SPEICHER_DIETPI_TOOL fehlt) -- Auslagerungsdatei"
		warn "nicht eingerichtet. Andere Systeme sind ein offenes Ende (ROADMAP)."
		return 1
	fi

	_sd_bytes="$(speicher_karte_bytes)" || {
		err "Groesse des Systemdatentraegers nicht messbar (findmnt/lsblk/sysfs)."
		return 2; }
	_sd_soll="$(speicher_staffel_mib "$_sd_bytes")"

	_sd_loc="$(speicher_dietpi_wert AUTO_SETUP_SWAPFILE_LOCATION)"
	case "$_sd_loc" in
		/dev/zram*|zram*|"") _sd_loc="$SPEICHER_DATEI_VORGABE" ;;
		/*) : ;;
		*) _sd_loc="$SPEICHER_DATEI_VORGABE" ;;
	esac
	info "Datentraeger: $((_sd_bytes / 1000000000)) GB -> Soll $_sd_soll MiB in $_sd_loc"

	_sd_f="$(rootpath "$_sd_loc")"
	_sd_ist=0
	[ -f "$_sd_f" ] && _sd_ist=$(( $(stat -c %s "$_sd_f") / 1048576 ))
	if [ "$_sd_ist" -eq "$_sd_soll" ] && [ -n "$(speicher_swap_eintrag "$_sd_loc")" ]; then
		info "Auslagerungsdatei hat schon $_sd_soll MiB und ist aktiv -- unveraendert."
		return 0
	fi
	info "ist: $_sd_ist MiB$( [ -n "$(speicher_swap_eintrag "$_sd_loc")" ] || printf ' (nicht aktiv)')"

	# Platz: Beim Ersetzen wird die alte Datei frei.
	_sd_frei="$(speicher_frei_mib)" || { err "Freier Platz nicht messbar (df)."; return 2; }
	_sd_kann=$((_sd_frei + _sd_ist - CHIMERA_SWAP_RESERVE_MIB))
	if [ "$_sd_soll" -gt "$_sd_kann" ]; then
		warn "Zu wenig Platz: Soll $_sd_soll MiB, frei $_sd_frei MiB,"
		warn "Reserve $CHIMERA_SWAP_RESERVE_MIB MiB. Nicht gekuerzt (Regel 5e) --"
		warn "die bisherige Auslagerung bleibt, wie sie ist."
		return 1
	fi

	# Ausgangszustand EINMAL festhalten -- der erste, nicht der vorige.
	# Ein zweiter Umbau (Karte gewechselt) darf das Original nicht
	# ueberschreiben, sonst stellt der Rueckbau Chimeras Zwischenstand her.
	if [ -z "$(manifest_list_von swapdatei "$CHIMERA_STEP")" ]; then
		_sd_vs="$(speicher_dietpi_wert AUTO_SETUP_SWAPFILE_SIZE)"
		_sd_vl="$(speicher_dietpi_wert AUTO_SETUP_SWAPFILE_LOCATION)"
		manifest_record swapdatei "$_sd_loc" "vorher:${_sd_vs:-1}:${_sd_vl:-$SPEICHER_DATEI_VORGABE}"
	fi

	if is_dry_run; then
		info "[wuerde] $SPEICHER_DIETPI_TOOL $_sd_soll $_sd_loc"
		return 0
	fi
	info "$SPEICHER_DIETPI_TOOL $_sd_soll $_sd_loc"
	"$_sd_tool" "$_sd_soll" "$_sd_loc" >/dev/null 2>&1 || \
		warn "dietpi-set_swapfile meldete einen Fehler -- Nachweis folgt."

	# Nachweis am Ergebnis, nicht am Exitcode.
	_sd_ist=0
	[ -f "$_sd_f" ] && _sd_ist=$(( $(stat -c %s "$_sd_f") / 1048576 ))
	if [ "$_sd_ist" -ne "$_sd_soll" ] || [ -z "$(speicher_swap_eintrag "$_sd_loc")" ]; then
		err "Auslagerungsdatei nach dem Umbau: $_sd_ist MiB, aktiv: $( [ -n "$(speicher_swap_eintrag "$_sd_loc")" ] && echo ja || echo nein)."
		return 1
	fi
	info "Auslagerungsdatei: $_sd_soll MiB, aktiv."
	return 0
}

# --- zram ------------------------------------------------------------------
#
# Nach Zustand: Hat dietpi-set_swapfile mit `swapoff -a` auch zram
# abgeschaltet, fehlt /dev/zram0 in /proc/swaps -- dann wird neu gestartet.
# rc 0 Soll erreicht, 1 Befund, 2 Abbruch.
speicher_zram() {
	_sz_soll="$(speicher_zram_soll_bytes)" || { err "MemTotal nicht lesbar."; return 2; }

	if ! manifest_package_present zram-tools; then
		manifest_apt zram-tools || { err "zram-tools nicht installierbar."; return 2; }
	else
		manifest_has paket zram-tools || manifest_record paket zram-tools vorher_da
	fi

	_sz_conf="$(rootpath "$SPEICHER_ZRAM_CONF")"
	_sz_text="$(speicher_zram_text)"
	_sz_neu=0
	if [ -f "$_sz_conf" ] && [ "$(cat "$_sz_conf")" = "$_sz_text" ]; then
		info "zram-Konfiguration unveraendert."
	elif is_dry_run; then
		info "[wuerde schreiben] $SPEICHER_ZRAM_CONF (PERCENT=$CHIMERA_ZRAM_PROZENT)"
		_sz_neu=1
	else
		# Original einmal sichern (Regel 5e: Rueckbau stellt es her).
		if [ -f "$_sz_conf" ] && ! manifest_list_von sicherung "$CHIMERA_STEP" | \
		     awk -F'\t' -v o="$_sz_conf" '$2 == o { f=1 } END { exit !f }'; then
			backup_file "$_sz_conf" || { err "Sicherung von $SPEICHER_ZRAM_CONF fehlgeschlagen."; return 2; }
		fi
		printf '%s\n' "$_sz_text" | write_atomic "$_sz_conf" || return 2
		info "geschrieben: $SPEICHER_ZRAM_CONF (PERCENT=$CHIMERA_ZRAM_PROZENT)"
		_sz_neu=1
	fi

	_sz_ds="$(cat "$(rootpath /sys/block/zram0/disksize)" 2>/dev/null || echo 0)"
	_sz_diff=$((_sz_ds - _sz_soll)); [ "$_sz_diff" -lt 0 ] && _sz_diff=$((-_sz_diff))
	_sz_aktiv="$(speicher_swap_eintrag /dev/zram0)"

	if [ "$_sz_neu" = 0 ] && [ -n "$_sz_aktiv" ] && [ "$_sz_diff" -le 4096 ]; then
		info "zram aktiv mit Sollgroesse -- unveraendert."
		return 0
	fi

	if is_dry_run; then
		info "[wuerde] systemctl enable zramswap; systemctl restart zramswap"
		return 0
	fi
	if [ "$(systemctl is-enabled zramswap 2>/dev/null)" != enabled ]; then
		systemctl enable zramswap >/dev/null 2>&1 || warn "systemctl enable zramswap schlug fehl."
	fi
	systemctl restart zramswap || { err "systemctl restart zramswap schlug fehl."; return 1; }

	# Nachweis: Groesse und Prioritaet ueber der Datei.
	_sz_ds="$(cat "$(rootpath /sys/block/zram0/disksize)" 2>/dev/null || echo 0)"
	_sz_diff=$((_sz_ds - _sz_soll)); [ "$_sz_diff" -lt 0 ] && _sz_diff=$((-_sz_diff))
	_sz_aktiv="$(speicher_swap_eintrag /dev/zram0)"
	if [ -z "$_sz_aktiv" ]; then
		err "zram nach dem Neustart nicht in /proc/swaps."; return 1; fi
	if [ "$_sz_diff" -gt 4096 ]; then
		err "zram hat $_sz_ds Byte, Soll $_sz_soll."; return 1; fi
	info "zram: $((_sz_ds / 1048576)) MiB, Prioritaet ${_sz_aktiv#* }."
	return 0
}

# --- Ablauf ----------------------------------------------------------------
speicher_einrichten() {
	if _se_f="$(speicher_fremd)"; then
		err "Fremde zram-Verwaltung gefunden: $_se_f"
		err "Zwei Verwalter fuer /dev/zram0 waeren zwei Systeme. Nicht"
		err "umgebaut -- Umstellen dieses Falls ist ein offenes Ende (ROADMAP)."
		return 2
	fi

	log "Auslagerungsdatei"
	speicher_datei; _se_d=$?
	[ "$_se_d" -ge 2 ] && return 2
	log ""
	log "zram"
	speicher_zram; _se_z=$?
	[ "$_se_z" -ge 2 ] && return 2
	log ""

	is_dry_run && return 0

	# Gesamtnachweis (Regel 5e): zram vor der Datei.
	log "Nachweis"
	_se_zp="$(speicher_swap_eintrag /dev/zram0 | cut -d' ' -f2)"
	_se_loc="$(manifest_list_von swapdatei "$CHIMERA_STEP" | cut -f1 | head -n1)"
	[ -n "$_se_loc" ] || _se_loc="$SPEICHER_DATEI_VORGABE"
	_se_dp="$(speicher_swap_eintrag "$_se_loc" | cut -d' ' -f2)"
	if [ -n "$_se_zp" ] && [ -n "$_se_dp" ] && [ "$_se_zp" -le "$_se_dp" ]; then
		err "zram (Prioritaet $_se_zp) liegt nicht vor der Datei ($_se_dp)."
		return 1
	fi
	info "/proc/swaps:"
	while IFS= read -r _se_z2; do info "  $_se_z2"; done <"$(rootpath /proc/swaps)"

	[ "$_se_d" -eq 0 ] && [ "$_se_z" -eq 0 ] && return 0
	return 1
}

# --- Rueckbau --------------------------------------------------------------
#
# Stellt den Ausgangszustand her: Dateigroesse und -ort mit demselben
# Werkzeug (DietPi pflegt fstab und dietpi.txt), zram-Konfiguration aus der
# Sicherung. Das Paket zram-tools nimmt Rueckbau 20 (nur `neu`, nur auf
# Wunsch). Die Sicherung bleibt liegen und wird genannt (wie Rueckbau 40).
speicher_rueckbau() {
	_sr_befund=0
	_sr_schritt="${1:-25-speicher}"

	_sr_z="$(manifest_list_von swapdatei "$_sr_schritt" | head -n1)"
	if [ -n "$_sr_z" ]; then
		_sr_vorher="${_sr_z#*	}"
		_sr_rest="${_sr_vorher#vorher:}"
		_sr_size="${_sr_rest%%:*}"
		_sr_loc="${_sr_rest#*:}"
		_sr_tool="$(rootpath "$SPEICHER_DIETPI_TOOL")"
		if is_dry_run; then
			info "[wuerde] $SPEICHER_DIETPI_TOOL $_sr_size $_sr_loc"
		elif [ -x "$_sr_tool" ]; then
			"$_sr_tool" "$_sr_size" "$_sr_loc" >/dev/null 2>&1 || true
			if [ "$(speicher_dietpi_wert AUTO_SETUP_SWAPFILE_SIZE)" = "$_sr_size" ]; then
				info "Auslagerung zurueck auf: $_sr_size $_sr_loc"
			else
				warn "Auslagerung nicht zurueckgestellt (Soll $_sr_size $_sr_loc)."
				_sr_befund=1
			fi
		else
			warn "$SPEICHER_DIETPI_TOOL fehlt -- Auslagerung nicht zurueckstellbar."
			_sr_befund=1
		fi
	fi

	_sr_f="$(tmp_path .chimera-rm-speicher)" || return 1
	manifest_list_von sicherung "$_sr_schritt" >"$_sr_f"
	_sr_zram=0
	while IFS='	' read -r _sr_kopie _sr_orig; do
		[ -n "$_sr_kopie" ] || continue
		if is_dry_run; then info "[wuerde zurueckholen] $_sr_orig aus $_sr_kopie"; continue; fi
		if [ ! -f "$_sr_kopie" ]; then
			warn "Sicherung fehlt: $_sr_kopie"; _sr_befund=1; continue; fi
		if write_atomic "$_sr_orig" <"$_sr_kopie" && cmp -s "$_sr_kopie" "$_sr_orig"; then
			info "zurueckgeholt: $_sr_orig (Sicherung bleibt: $_sr_kopie)"
			_sr_zram=1
		else
			warn "nicht zurueckgeholt: $_sr_orig"; _sr_befund=1
		fi
	done <"$_sr_f"
	rm -f "$_sr_f"

	# Das Werkzeug hat zram mit swapoff -a abgeschaltet, und die
	# Konfiguration ist wieder die alte: zram neu starten.
	if ! is_dry_run && { [ "$_sr_zram" = 1 ] || [ -n "$_sr_z" ]; } && \
	   [ "$(systemctl is-enabled zramswap 2>/dev/null)" = enabled ]; then
		systemctl restart zramswap >/dev/null 2>&1 || {
			warn "zramswap nicht neu startbar."; _sr_befund=1; }
	fi
	return "$_sr_befund"
}
