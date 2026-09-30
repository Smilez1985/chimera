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
		# Der Hersteller liefert EINEN Treiber fuer WM8960 und ES8389;
		# beide melden sich als dieselbe Karte. Deshalb genuegt hier ein
		# Name statt einer Fallunterscheidung nach Codec.
		alsa_karte)  echo "whisplaysound" ;;
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
# Welche Anzeige steckt dran? Geprueft wird das HAT-EEPROM: Es traegt den
# Herstellernamen und ist die einzige Kennung, die wirklich zur Platine
# gehoert. Fehlt es, heisst das NICHT "keine Anzeige" -- es heisst "keine,
# die sich selbst meldet" (Regel 10j).
#
# Wichtig: Ohne aktives I2C liest die Firmware das EEPROM gar nicht erst.
# Ein fehlender HAT-Knoten vor dem ersten Einschalten von i2c_arm sagt
# deshalb nichts aus.
display_detect() {
	_ae_hat="$(rootpath /proc/device-tree/hat)"

	if [ -d "$_ae_hat" ]; then
		_ae_v="$(read_dt /proc/device-tree/hat/vendor 2>/dev/null || echo '')"
		_ae_p="$(read_dt /proc/device-tree/hat/product 2>/dev/null || echo '')"

		case "$_ae_v$_ae_p" in
			*PiSugar*|*Whisplay*|*whisplay*) echo "whisplay"; return 0 ;;
		esac

		# Ein EEPROM ist da, aber wir kennen es nicht. Das wird gesagt,
		# nicht verschwiegen -- und es wird NICHT geraten (Regel 10g).
		echo "unbekannt"
		return 1
	fi

	echo "keins"
	return 1
}

# Ist I2C ueberhaupt an? Ohne das ist die Erkennung blind, und dieser
# Unterschied muss sichtbar bleiben.
display_detect_possible() {
	[ -n "$(find "$(rootpath /dev)" -maxdepth 1 -name 'i2c-*' 2>/dev/null | head -1)" ]
}
