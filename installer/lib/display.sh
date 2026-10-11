#!/bin/sh
# Chimera installer -- Anzeigen: Lesezugriff auf die Anzeigemodule.
#
# Die Wahrheit ueber eine Anzeige steht in GENAU EINER Datei:
# src/chimera/displays/<typ>/display.json. Dieselbe Datei liest der
# Python-Treiber (Profil), die Erkennung (Pruefliste) und dieser Installer
# (Deps, Busse, Ton). Bis 11.10.2026 stand hier eine zweite Fassung als
# case-Tabelle -- zwei Quellen fuer dieselbe Sache driften (Regel 10g),
# und sie taten es: "busse" nannte hier i2s, das Profil kannte es nicht.
#
# Gelesen wird ueber `python3 -m chimera.displays profil <typ>` -- Python
# steht ab Schritt 20 bereit, und ein JSON-Leser in Shell waere die
# naechste Doppelimplementierung. Ohne Python (vor Schritt 20, oder im
# Trockenlauf auf einer fremden Maschine) liefern die Funktionen nichts
# und sagen es (rc 1), statt zu raten.
#
# Felder je Anzeige (display_get <typ> <feld>):
#   name          Klartext
#   breite/hoehe  Bildpunkte
#   fps           Bildrate, 0 = nur auf Anstoss (Regel 7a)
#   busse         welche Busse die Bootkonfiguration braucht (spi i2c_arm)
#   pip           Python-Pakete des Moduls (zusaetzlich zu requirements.txt)
#   apt           Systempakete des Panels (Schritt 50)
#   alsa_karte    ALSA-Kartenname, leer = kein Ton
#   ton_apt       Systempakete des Tons (alsa-utils, raspi-utils-dt; Schritt 40)
#   ton_dtparam   dtparam-Zeilen, die der Ton zur LAUFZEIT braucht (i2s=on)
#   ton_dtoverlay Overlays, die der Ton zur LAUFZEIT laedt (whisplay-soundcard)
#   quelle        git-Adresse des Hersteller-Toninstallers, leer = keiner
#   commit        festgelegter Commit dieser Quelle (Regel 5f / I4)
#   installer     Pfad des Toninstallers im geholten Baum
#   sha256        Pruefsumme des Toninstallers an diesem Commit
#   kernelmodul   Kernelmodul, das der Toninstaller baut (Nachweis)
#   asound_conf   ALSA-Konfiguration im Herstellerbaum (Pfad relativ)
#   pruefe        Befehl, der NACH der Einrichtung treffen muss (Regel 10j)
#   hinweis       was ein Mensch dazu wissen muss

# Quellbaum, aus dem die Module gelesen werden: das Repo, aus dem dieser
# Installer laeuft (installer/.. = Repo, nach Schritt 00 ist das source/).
display_src() {
	# Die Schritte setzen _HERE = installer/; Tests und Bibliotheken ohne
	# Schritt nicht -- dann zaehlt der Ort dieser Datei (installer/lib/).
	# $0 taugt nicht: in einer gesourcten Bibliothek ist es "sh".
	for _ds_k in "${_HERE:-}" "${HERE:-}"; do
		[ -n "$_ds_k" ] && [ -d "$_ds_k/../src/chimera/displays" ] && {
			printf '%s\n' "$(cd "$_ds_k/.." && pwd)/src"; return 0; }
	done
	# Ohne Schritt und ohne Test: der installierte Stand (source/).
	printf '%s\n' "$(rootpath "$CHIMERA_SOURCE")/src"
}

# Python, das die Module lesen kann. Kein venv noetig: die Registry
# importiert nur die Standardbibliothek (base.py laedt numpy weich).
display_python() {
	[ -n "${CHIMERA_DISPLAY_PYTHON:-}" ] && { printf '%s\n' "$CHIMERA_DISPLAY_PYTHON"; return 0; }
	command -v python3 2>/dev/null
}

# display.json eines Moduls als JSON -- je Typ EINMAL gelesen, dann aus
# einer Datei im Zwischenverzeichnis. Jeder Python-Start kostet auf dem
# Pi Zero 2 W rund 2 s; Schritt 40 fragt ein Dutzend Felder ab, und beim
# Boot-Abgleich (gemessen 11.10.2026) lagen zwischen "Erkannt" und
# "Busse" 32 s -- nur Lesen derselben Datei.
display_profil_json() {
	_dpj_typ="$1"
	_dpj_cache="${CHIMERA_DISPLAY_CACHE:-${TMPDIR:-/tmp}}/.chimera-profil-$$-$_dpj_typ.json"
	if [ -s "$_dpj_cache" ]; then
		cat "$_dpj_cache"; return 0
	fi
	_dpj_py="$(display_python)" || return 1
	[ -n "$_dpj_py" ] || return 1
	_dpj_src="${CHIMERA_DISPLAY_SRC:-$(display_src)}"
	[ -d "$_dpj_src/chimera/displays" ] || return 1
	_dpj_json="$(PYTHONPATH="$_dpj_src" PYTHONDONTWRITEBYTECODE=1 "$_dpj_py" -m chimera.displays profil "$_dpj_typ" 2>/dev/null)" || return 1
	[ -n "$_dpj_json" ] || return 1
	# Puffer ist Beschleunigung, keine Pflicht: Scheitert das Schreiben,
	# wird beim naechsten Mal eben wieder gelesen.
	printf '%s\n' "$_dpj_json" >"$_dpj_cache" 2>/dev/null || true
	printf '%s\n' "$_dpj_json"
}

# Puffer eines Laufs wegraeumen (die Schritte rufen es am Ende; ein
# Rest schadet nicht, weil die PID im Namen steht).
display_cache_leeren() {
	rm -f "${CHIMERA_DISPLAY_CACHE:-${TMPDIR:-/tmp}}"/.chimera-profil-$$-*.json 	      "${CHIMERA_DISPLAY_CACHE:-${TMPDIR:-/tmp}}"/.chimera-felder-$$-*.tsv 2>/dev/null || true
}

# Gibt es ein Modul dieses Namens? rc 0 ja.
display_profil_lesbar() {
	display_profil_json "$1" >/dev/null 2>&1
}

# Ein Feld lesen. Listen kommen als Leerzeichen-getrennte Woerter.
#
# Die Felder werden EINMAL je Typ flach abgelegt (feld<TAB>wert, eine
# Python-Ausfuehrung), danach liest `display_get` nur noch die Datei --
# kein Python-Start je Feld (rund 2 s auf dem Pi Zero 2 W).
display_felder_datei() {
	_df_typ="$1"
	_df_f="${CHIMERA_DISPLAY_CACHE:-${TMPDIR:-/tmp}}/.chimera-felder-$$-$_df_typ.tsv"
	if [ -s "$_df_f" ]; then printf '%s\n' "$_df_f"; return 0; fi
	_df_json="$(display_profil_json "$_df_typ")" || return 1
	_df_py="$(display_python)"
	printf '%s' "$_df_json" | "$_df_py" -c '
import json, sys
d = json.load(sys.stdin)
ton = d.get("ton") or {}; q = ton.get("quelle") or {}; deps = d.get("deps") or {}
def liste(x): return " ".join(str(i) for i in (x or []))
felder = {
    "name": d.get("name", ""), "breite": d.get("breite", ""), "hoehe": d.get("hoehe", ""),
    "fps": d.get("bildrate", ""), "busse": liste(d.get("busse")),
    "pip": liste(deps.get("pip")), "apt": liste(deps.get("apt")), "ton_apt": liste(ton.get("apt")),
    "alsa_karte": ton.get("alsa_karte", ""), "ton_dtparam": liste(ton.get("dtparam")),
    "ton_dtoverlay": liste(ton.get("dtoverlay")), "quelle": q.get("git", ""),
    "commit": q.get("commit", ""), "installer": q.get("installer", ""), "sha256": q.get("sha256", ""),
    "kernelmodul": ton.get("kernelmodul", ""), "asound_conf": ton.get("asound_conf", ""),
    "pruefe": d.get("pruefe", "true"), "hinweis": d.get("hinweis", ""),
}
for k, v in felder.items():
    print(k + "\t" + str(v).replace("\t", " ").replace("\n", " "))' >"$_df_f.neu" 2>/dev/null || { rm -f "$_df_f.neu"; return 1; }
	[ -s "$_df_f.neu" ] || { rm -f "$_df_f.neu"; return 1; }
	mv "$_df_f.neu" "$_df_f" 2>/dev/null || { cat "$_df_f.neu"; return 0; }
	printf '%s\n' "$_df_f"
}

display_get() {
	_dg_f="$(display_felder_datei "$1")" || { echo ""; return 1; }
	awk -F'\t' -v k="$2" '$1 == k { print substr($0, length(k) + 2); f = 1 } END { if (!f) print "" }' "$_dg_f"
}

# Alle bekannten Anzeigen (Ordner mit display.json), alphabetisch.
display_list() {
	_dl_py="$(display_python)" || { echo ""; return 1; }
	_dl_src="${CHIMERA_DISPLAY_SRC:-$(display_src)}"
	[ -d "$_dl_src/chimera/displays" ] || { echo ""; return 1; }
	PYTHONPATH="$_dl_src" PYTHONDONTWRITEBYTECODE=1 "$_dl_py" -c \
		'from chimera.displays import registry; print(" ".join(registry.typen()))' 2>/dev/null
}

# --- Erkennung ------------------------------------------------------------
#
# Die Erkennung lebt im Treiberpaket (src/chimera/displays/erkennen.py,
# DISPLAYS.md Abschnitt 4): Kennung des Panels ueber SPI (Pflicht), Codec am I2C
# (eindeutig), Overlay/ALSA/Kernelmodul (nur "eingerichtet", waehlt nicht).
# Sie braucht freie Leitungen -- laeuft also VOR dem Dienst, als root.
#
# Ausgabe hier: der gewaehlte Typ (oder nichts), rc 0 gewaehlt / 1 nicht.
# Danach stehen DISPLAY_TYP, DISPLAY_QUELLE (Grund) und DISPLAY_BEFUND
# (JSON) -- deshalb OHNE Subshell aufrufen.
display_detect() {
	DISPLAY_TYP=""; DISPLAY_QUELLE=""; DISPLAY_BEFUND=""
	_dd_py="$(display_python)" || return 1
	_dd_src="${CHIMERA_DISPLAY_SRC:-$(display_src)}"
	[ -d "$_dd_src/chimera/displays" ] || return 1
	DISPLAY_BEFUND="$(PYTHONPATH="$_dd_src" PYTHONDONTWRITEBYTECODE=1 \
		"$_dd_py" -m chimera.displays erkennen --json 2>/dev/null)" || true
	[ -n "$DISPLAY_BEFUND" ] || return 1
	DISPLAY_TYP="$(printf '%s' "$DISPLAY_BEFUND" | "$_dd_py" -c \
		'import json,sys; print(json.load(sys.stdin).get("gewaehlt") or "")')"
	DISPLAY_QUELLE="$(printf '%s' "$DISPLAY_BEFUND" | "$_dd_py" -c \
		'import json,sys; print(json.load(sys.stdin).get("grund") or "")')"
	[ -n "$DISPLAY_TYP" ] || return 1
	printf '%s\n' "$DISPLAY_TYP"
	return 0
}

# Woher die Erkennung ihr Ergebnis hat (leer, wenn nichts erkannt wurde).
display_quelle() { printf '%s\n' "${DISPLAY_QUELLE:-}"; }

# Die Belege der letzten Erkennung, eine Zeile je Pruefung (fuer das Protokoll).
display_belege() {
	[ -n "${DISPLAY_BEFUND:-}" ] || return 0
	_db_py="$(display_python)" || return 0
	printf '%s' "$DISPLAY_BEFUND" | "$_db_py" -c '
import json, sys
d = json.load(sys.stdin)
for b in d.get("belege", []):
    m = {True: "ja  ", False: "nein", None: "?   "}[b.get("treffer")]
    typ, klasse, text = b.get("typ", ""), b.get("klasse", ""), b.get("text", "")
    print("[" + m + "] " + typ.ljust(10) + " " + klasse.ljust(12) + " " + text)
for t in d.get("belegt", []):
    print(f"[belegt] {t}: Leitungen gehalten -- Dienst laeuft?")'
}

# Ist I2C ueberhaupt an? Ohne das ist die Codec-Pruefung blind, und dieser
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
