#!/bin/sh
# Chimera installer -- Kernelmodule laden und pruefen.
#
# Worauf es ankommt: **Eine vorhandene .ko-Datei ist kein geladenes Modul.**
# Ein Modul kann ABI-inkompatibel sein, oder der Geraetebaum-Eintrag fehlt
# noch (das Overlay wirkt erst nach einem Neustart) -- dann liegt die Datei
# da und `modprobe` scheitert trotzdem. Wer nur die Datei prueft, meldet
# Erfolg fuer etwas, das nicht laeuft (Regel 10j).
#
# Der Hersteller-Installer macht diese Unterscheidung bereits, und sie ist
# der Grund, warum Regel I4 als Regel dasteht. Dieselbe Pruefung brauchen
# der Anzeigetreiber (Modul 40) und der Codec `snd-soc-wm8960`
# (`docs/INSTALLER.md`, Abschnitt 4) -- deshalb steht sie einmal hier und
# nicht zweimal dort. Ein zweiter Weg fuer dieselbe Sache driftet (Regel 10g).
#
# Der Modulpfad geht ueber `rootpath`, nicht direkt nach `/lib/modules`
# (Regel 10d): Dadurch ist auch das ohne Zielhardware pruefbar, mit einem
# erfundenen Wurzelverzeichnis.

# Pfad der ersten passenden Moduldatei -- oder nichts.
#
# Eigene Funktion, weil zwei Stellen dieselbe Frage stellen: das Urteil
# "laedt es?" (kernel_module_state) und die Erkennung "ist der Treiber da?"
# (lib/display.sh). Zwei eigene `find`-Aufrufe fuer dieselbe Sache waeren
# der Anfang davon, dass sie auseinanderlaufen (Regel 10g).
kernel_module_datei() {
	_kmd_kver="$(kernel_version)"
	[ -n "$_kmd_kver" ] || return 0
	find "$(rootpath "/lib/modules/$_kmd_kver")" -name "$1" 2>/dev/null | head -1
}

# Zustand eines Kernelmoduls.
#
#   $1  Dateimuster unter /lib/modules/<kver>/   (z. B. 'snd-soc-whisplay*')
#   $2  Modulname fuer modprobe
#
# Ausgabe auf stdout, genau einer von:
#   nicht_gebaut    es gibt keine .ko -- ein Fehlschlag
#   geladen         modprobe hat es geladen
#   nicht_geladen   die .ko liegt da, laedt aber nicht
#
# Rueckgabe 0, wenn eine Aussage moeglich war. Das Urteil faellt der
# Aufrufer -- hier wird nur festgestellt.
kernel_module_state() {
	_kms_muster="$1"
	_kms_name="$2"
	_kms_kver="$(kernel_version)"

	if [ -z "$_kms_kver" ]; then
		err "Kernelfassung nicht ermittelbar -- Modulzustand nicht feststellbar."
		return 1
	fi

	_kms_ko="$(kernel_module_datei "$_kms_muster")"

	if [ -z "$_kms_ko" ]; then
		printf '%s\n' "nicht_gebaut"
		return 0
	fi

	# depmod vor modprobe: Ohne aktualisierte Modulabhaengigkeiten
	# scheitert der Ladeversuch an fehlenden Abhaengigkeiten, obwohl das
	# Modul in Ordnung ist -- das waere ein falscher Befund.
	if have_cmd depmod; then
		depmod -a "$_kms_kver" 2>/dev/null || true
	fi

	if have_cmd modprobe && modprobe "$_kms_name" 2>/dev/null; then
		printf '%s\n' "geladen"
		return 0
	fi

	printf '%s\n' "nicht_geladen"
	return 0
}
