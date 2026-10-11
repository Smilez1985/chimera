#!/bin/sh
# Chimera installer -- Anzeigen und ihre Treiber.
#
# Nicht "der Whisplay-Installer wird aufgerufen", sondern: **Jede Anzeige
# ist ein Eintrag mit demselben Satz Felder.** Der Whisplay-HAT ist der
# erste; E-Paper und ein nacktes ST7789-Panel sind die naechsten. Was sich
# je Anzeige unterscheidet, steht hier, nicht in einem Modul.
#
# Gleicher Gedanke wie bei den Boardprofilen (Regel 10c) und der
# Anbieter-Registry (Regel 5a), aus demselben Grund: Fallunterscheidungen,
# die ueber Module verteilt sind, driften auseinander.
#
# Felder je Anzeige:
#   name          Klartext
#   breite/hoehe  Bildpunkte
#   fps           Bildrate, 0 = nur auf Anstoss (Regel 7a)
#   busse         welche Busse die Bootkonfiguration braucht
#   quelle        git-Adresse des Herstellertreibers, leer = keiner noetig
#   installer     Pfad im geholten Baum, den wir aufrufen
#   alsa_karte    ALSA-Kartenname nach der Installation, leer = kein Ton
#   laufzeit      Verzeichnis im geholten Baum mit dem Python-Treiber,
#                 leer = keiner (Schritt 50 verdrahtet es per .pth)
#   py_modul      Modul, das sich danach im venv importieren lassen muss
#   pip           Python-Pakete fuer den Treiber (ins venv, Schritt 50)
#   apt           Systempakete, die diese pip-Pakete zum Bauen brauchen
#   erkennung     wie man prueft, ob die Anzeige da ist
#   pruefe        Befehl, der NACH der Installation treffen muss (Regel 10j)
#   hinweis       was ein Mensch dazu wissen muss

display_get() {
	_ag_typ="$1"
	_ag_feld="$2"

	case "$_ag_typ" in
	whisplay)
		case "$_ag_feld" in
		name)        echo "PiSugar Whisplay HAT" ;;
		breite)      echo "240" ;;
		hoehe)       echo "280" ;;
		fps)         echo "15" ;;
		# DREI Busse, nicht einer. SPI traegt das Bild, I2C die
		# Codec-Register und das HAT-EEPROM, I2S die Audiodaten.
		# Ohne I2S gibt es keinen Ton -- der erste Entwurf kannte nur
		# SPI und waere stumm geblieben.
		busse)       echo "spi i2c_arm i2s" ;;
		quelle)      echo "https://github.com/PiSugar/Whisplay.git" ;;
		installer)   echo "install_driver.sh" ;;
		# Fremdcode festgelegt (Regel I4, 5f): genau dieser Commit, und die
		# aufgerufene Datei muss GENAU diese Pruefsumme haben, bevor sie
		# ausgefuehrt wird. Gemessen 10.10.2026, Stand "main".
		commit)      echo "c73051e64dc62aced1853d16f33d4614fec5bee4" ;;
		sha256)      echo "0767aba3cbfe59cb1c63a003d49cd0eee6a0a2a8b30b07c2cf2717c637a24078" ;;
		# Der Hersteller liefert EINEN Treiber fuer WM8960 und ES8389;
		# beide melden sich als dieselbe Karte. Deshalb genuegt hier ein
		# Name statt einer Fallunterscheidung nach Codec.
		alsa_karte)  echo "whisplaysound" ;;
		# Python-Ansteuerung des Panels (LCD, LED, Taste). Der Hersteller
		# liefert kein pip-Paket: eingebunden wird `runtime/` aus dem
		# geholten Baum, so wie seine eigenen Beispiele es per sys.path
		# tun (WHISPLAY-HERSTELLER.md, Frage 3). Was whisplay.py
		# importiert, kommt per pip ins venv -- `spidev` baut dort aus
		# Quelltext und braucht die Python-Header (gemessen am chimera-pi
		# 11.10.2026: spidev 3.8 Quellbau, gpiod 2.5.0 als Wheel).
		laufzeit)    echo "runtime" ;;
		py_modul)    echo "whisplay" ;;
		# Auch diese Datei ist Fremdcode, der im Dienst laeuft (I4, 5f):
		# Pruefsumme von runtime/whisplay.py am festgelegten Commit.
		py_sha256)   echo "75d621ccf35eaf9610642e4d05bb9720e9fcc4778a021aa87e90d37a8dc496c2" ;;
		pip)         echo "spidev>=3.6 gpiod>=2.2" ;;
		apt)         echo "python3-dev" ;;
		erkennung)   echo "hat_eeprom:PiSugar" ;;
		pruefe)      echo "aplay -l 2>/dev/null | grep -qi whisplaysound" ;;
		hinweis)     echo "Braucht Kernel-Headers; der Treiber wird aus Quelltext gebaut." ;;
		*)           echo "" ;;
		esac
		;;

	st7789)
		# Ein nacktes SPI-Panel ohne Audio und ohne EEPROM. Kein
		# Herstellertreiber noetig -- Chimera spricht SPI selbst.
		case "$_ag_feld" in
		name)        echo "ST7789-SPI-Panel (ohne HAT)" ;;
		breite)      echo "240" ;;
		hoehe)       echo "240" ;;
		fps)         echo "15" ;;
		busse)       echo "spi" ;;
		quelle)      echo "" ;;
		installer)   echo "" ;;
		alsa_karte)  echo "" ;;
		erkennung)   echo "manuell" ;;
		pruefe)      echo "test -e /dev/spidev0.0" ;;
		hinweis)     echo "Kein Ton, keine Taste, keine LED. Nur Bild." ;;
		*)           echo "" ;;
		esac
		;;

	epaper)
		# Aus openclawgotchi. Noch nicht gebaut -- steht als ZUSTAND hier,
		# nicht als Platzhalter im Code (Regel 10c).
		case "$_ag_feld" in
		name)        echo "E-Paper (openclawgotchi-Erbe)" ;;
		breite)      echo "250" ;;
		hoehe)       echo "122" ;;
		# 0 heisst: nicht von selbst zeichnen. E-Ink braucht Sekunden je
		# Bild; eine Bildrate waere dort sinnlos (Regel 7a).
		fps)         echo "0" ;;
		busse)       echo "spi" ;;
		quelle)      echo "" ;;
		installer)   echo "" ;;
		alsa_karte)  echo "" ;;
		erkennung)   echo "manuell" ;;
		pruefe)      echo "test -e /dev/spidev0.0" ;;
		hinweis)     echo "Noch nicht umgesetzt. Lesbar ohne Strom, dafuer keine Animation." ;;
		*)           echo "" ;;
		esac
		;;

	keine)
		case "$_ag_feld" in
		name)        echo "keine Anzeige" ;;
		breite)      echo "240" ;;
		hoehe)       echo "280" ;;
		fps)         echo "0" ;;
		busse)       echo "" ;;
		quelle)      echo "" ;;
		installer)   echo "" ;;
		alsa_karte)  echo "" ;;
		erkennung)   echo "immer" ;;
		pruefe)      echo "true" ;;
		hinweis)     echo "Chimera laeuft blind -- Gesicht wird berechnet, aber nicht gezeigt." ;;
		*)           echo "" ;;
		esac
		;;

	*)
		echo ""
		return 1
		;;
	esac
}

# Alle bekannten Anzeigen, in der Reihenfolge, in der erkannt wird.
display_list() {
	echo "whisplay st7789 epaper keine"
}

# --- Erkennung ------------------------------------------------------------
#
# Welche Anzeige steckt dran?
#
# Das HAT-EEPROM ist die beste Quelle -- es traegt den Herstellernamen und
# gehoert wirklich zur Platine. Aber es ist nicht die EINZIGE, und beim
# ausgelieferten Whisplay ist es nachweislich NICHT programmiert
# (docs/HARDWARE-BEFUNDE.md). Wer nur dort nachsieht, findet "keins" und
# bricht ab, obwohl die Anzeige angeschlossen ist.
#
# Deshalb mehrere Quellen, in dieser Reihenfolge:
#
#   1. HAT-EEPROM          -- meldet sich die Platine selbst?
#   2. weitere Kennungen   -- siehe display_signaturen()
#   3. nichts davon        -- "unbekannt" (EEPROM da) oder "keins"
#
# Welche Quelle angeschlagen hat, steht danach in DISPLAY_QUELLE. Ein
# Treffer wird also BENANNT und geht nicht als stiller Erfolg durch
# (Regel 10e). Widersprechen sich zwei Quellen, wird das gemeldet.

# Weitere Kennungen einer Anzeige, Form je Zeile `quelle:wert`.
#
# Whisplay: Alles hier ist am Herstellertreiber belegt, nicht geraten
# (audio/whisplay-soundcard/scripts/install.sh am Commit c73051e6, gegen
# geprueft mit docs/HARDWARE-BEFUNDE.md). Ohne EEPROM schreibt der
# Installer `dtoverlay=whisplay-soundcard` in die Bootkonfiguration,
# traegt die Module in /etc/modules ein und benennt die ALSA-Karte
# `whisplaysound`. Nach der Installation sieht das aus wie hier:
#
#   config.txt:  dtoverlay=whisplay-soundcard
#   /proc/asound/cards:  whisplaysound
#   /lib/modules/<kver>/...:  snd-soc-whisplay-soundcard.ko
#
display_signaturen() {
	case "$1" in
	whisplay)
		echo "overlay:dtoverlay=whisplay-soundcard"
		echo "alsa:whisplaysound"
		echo "modul:snd-soc-whisplay"
		;;
	*) : ;;
	esac
}

# Trifft eine der Kennungen zu? Ausgabe die passende Zeile, sonst nichts.
display_signatur_treffer() {
	for _ds_z in $(display_signaturen "$1"); do
		_ds_q="${_ds_z%%:*}"
		_ds_w="${_ds_z#*:}"
		case "$_ds_q" in
		overlay)
			_ds_p=""
			for _ds_k in /boot/firmware/config.txt /boot/config.txt; do
				[ -f "$(rootpath "$_ds_k")" ] && { _ds_p="$_ds_k"; break; }
			done
			[ -n "$_ds_p" ] || continue
			grep -qxF "$_ds_w" "$(rootpath "$_ds_p")" 2>/dev/null || continue
			;;
		alsa)
			# /proc/asound/cards statt `aplay -l`: aplay haengt an der
			# Gruppe `audio`, und ein Nachweis, der von den Rechten des
			# Aufrufers abhaengt, misst nicht das System.
			read_file /proc/asound/cards 2>/dev/null | grep -qi -- "$_ds_w" || continue
			;;
		modul)
			[ -n "$(kernel_module_datei "${_ds_w}*")" ] || continue
			;;
		*)
			continue
			;;
		esac
		printf '%s\n' "$_ds_z"
		return 0
	done
	return 1
}

display_detect() {
	DISPLAY_QUELLE=""
	DISPLAY_TYP="keins"
	_ae_hat="$(rootpath /proc/device-tree/hat)"
	_ae_hat_da=0

	if [ -d "$_ae_hat" ]; then
		_ae_hat_da=1
		_ae_v="$(read_dt /proc/device-tree/hat/vendor 2>/dev/null || echo '')"
		_ae_p="$(read_dt /proc/device-tree/hat/product 2>/dev/null || echo '')"

		case "$_ae_v$_ae_p" in
			*PiSugar*|*Whisplay*|*whisplay*)
				DISPLAY_QUELLE="eeprom"
				DISPLAY_TYP="whisplay"
				echo "whisplay"; return 0 ;;
		esac
		# Ein EEPROM ist da, aber unbekannt. KEIN Abbruch an dieser
		# Stelle: erst die uebrigen Quellen pruefen, sonst bliebe ein
		# HAT mit unprogrammiertem EEPROM unerkannt.
		DISPLAY_TYP="unbekannt"
	fi

	for _ae_t in $(display_list); do
		_ae_treffer="$(display_signatur_treffer "$_ae_t" || true)"
		[ -n "$_ae_treffer" ] || continue
		DISPLAY_QUELLE="$_ae_treffer"
		DISPLAY_TYP="$_ae_t"
		echo "$_ae_t"; return 0
	done

	if [ "$_ae_hat_da" -eq 1 ]; then
		# Ein EEPROM ist da, aber wir kennen es nicht -- und keine
		# weitere Kennung passt. Das wird gesagt, nicht verschwiegen,
		# und es wird NICHT geraten (Regel 10g).
		echo "unbekannt"
		return 1
	fi

	DISPLAY_TYP="keins"
	echo "keins"
	return 1
}

# Woher die Erkennung ihr Ergebnis hat (leer, wenn nichts erkannt wurde).
display_quelle() { printf '%s\n' "${DISPLAY_QUELLE:-}"; }

# Ist I2C ueberhaupt an? Ohne das ist die Erkennung blind, und dieser
# Unterschied muss sichtbar bleiben.
#
# Gefragt wird der KERNEL (/sys/bus/i2c/devices/i2c-N = ein registrierter
# Bus), nicht der Geraeteknoten. /dev/i2c-N entsteht erst mit dem Modul
# i2c-dev, das nur fuer Zugriff aus dem Userspace noetig ist -- der
# Codec-Treiber braucht es nicht (HARDWARE-BEFUNDE, "Fallen bei der
# Erkennung"). Am chimera-pi (11.10.2026) lief I2C nachweislich (i2c-1,
# wm8960 an 1-001a), /dev/i2c-* fehlte, und Schritt 40 warnte trotzdem
# "I2C ist nicht aktiv".
display_detect_possible() {
	[ -n "$(find "$(rootpath /sys/bus/i2c/devices)" -maxdepth 1 -name 'i2c-*' \
		2>/dev/null | head -1)" ]
}
