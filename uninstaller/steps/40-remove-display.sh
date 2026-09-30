#!/bin/sh
# Gegenstueck zu installer/steps/40-install-display.sh
# (Architekturregel 10l).
#
# Nimmt zurueck, was Schritt 40 angelegt hat:
#   - Zeilen in der Bootkonfiguration (dtparam=...)
#   - die Gruppenmitgliedschaft (audio)
#
# Was NICHT zurueckgenommen wird, und warum:
#
#   Das Kernelmodul und das Overlay bleiben. Sie wurden vom
#   HERSTELLERINSTALLER angelegt, nicht von uns -- wir haben ihn nur
#   aufgerufen. Wer sie entfernt, entfernt fremde Arbeit auf Verdacht.
#   docs/UNINSTALL.md nennt den Weg fuer den, der es ausdruecklich will.
#
#   Die Sicherung der Bootkonfiguration bleibt liegen. Eine Deinstallation
#   ist der Moment, in dem am wenigsten klar ist, ob alles gutgeht --
#   genau dann wirft man die Sicherung nicht weg. Sie wird GENANNT, damit
#   niemand sie spaeter fuer Muell haelt.
#
# Exitcode: 0 in Ordnung, 1 Befund, 2 Abbruch.

set -eu

_HERE="$(cd "$(dirname "$0")/../.." && pwd)"
. "$_HERE/installer/lib/common.sh"
. "$_HERE/installer/lib/manifest.sh"

CHIMERA_STEP="40-remove-display"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "remove-display" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

BEFUND=0

log "Anzeige zurueckbauen"

# --- 1. Zeilen aus der Bootkonfiguration ---------------------------------
#
# Nur Zeilen, die als `neu:` eingetragen sind. Ein `vorher_da:` heisst:
# Die Zeile stand schon da, bevor Chimera kam -- sie gehoert dem Nutzer.
# Wer das nicht unterscheidet, schaltet ihm SPI ab, das er fuer etwas
# anderes braucht.
zeilen_zuruecknehmen() {
	_zz_n=0
	_zz_datei=""

	# manifest_list gibt "pfad<TAB>angabe" -- die Angabe ist
	# "neu:<zeile>" oder "vorher_da:<zeile>".
	manifest_list zeile | while IFS='	' read -r _zz_f _zz_a; do
		[ -n "$_zz_f" ] || continue

		case "$_zz_a" in
			neu:*)       _zz_zeile="${_zz_a#neu:}" ;;
			vorher_da:*) info "bleibt (war vorher da): ${_zz_a#vorher_da:}"
			             continue ;;
			*)           warn "Eintrag nicht deutbar: $_zz_a"
			             continue ;;
		esac

		if [ ! -f "$_zz_f" ]; then
			warn "Datei nicht mehr da: $_zz_f"
			continue
		fi

		if ! grep -qxF "$_zz_zeile" "$_zz_f" 2>/dev/null; then
			info "schon weg: $_zz_zeile"
			continue
		fi

		if is_dry_run; then
			info "[wuerde entfernen] $_zz_zeile  aus $_zz_f"
			continue
		fi

		# Vor dem Aendern sichern. Eine kaputte Bootkonfiguration kostet
		# den Ausbau der SD-Karte -- beim Rueckbau genauso wie beim
		# Aufbau.
		backup_file "$_zz_f" || {
			err "Sicherung fehlgeschlagen -- $_zz_f wird nicht angefasst."
			continue
		}

		# Ueber eine Nebendatei und atomares mv: Wird die Zieldatei
		# direkt geschrieben und der Vorgang bricht ab, ist die
		# Bootkonfiguration halb geschrieben. Und das Ergebnis wird
		# geprueft, nicht der Exitcode -- eine leere Ausgabe wuerde die
		# Datei leeren, und `mv` gelingt auch dann.
		_zz_tmp="${_zz_f}.chimera-neu.$$"
		if ! grep -vxF "$_zz_zeile" "$_zz_f" >"$_zz_tmp" 2>/dev/null; then
			# grep gibt 1 zurueck, wenn NICHTS uebrig bleibt. Das ist
			# hier kein Fehler, aber eine leere Bootkonfiguration schon.
			:
		fi
		if [ ! -s "$_zz_tmp" ]; then
			err "Ergebnis waere leer -- $_zz_f bleibt unveraendert."
			rm -f "$_zz_tmp"
			continue
		fi
		mv "$_zz_tmp" "$_zz_f" || {
			err "Konnte $_zz_f nicht ersetzen."
			rm -f "$_zz_tmp"
			continue
		}
		info "entfernt: $_zz_zeile"
		_zz_n=$((_zz_n + 1))
		_zz_datei="$_zz_f"
	done

	# Hinweis auf den Neustart nur, wenn wirklich etwas geaendert wurde.
	# Die Schleife lief in einer Pipe (Subshell) -- die Zaehler sind hier
	# draussen wieder leer. Deshalb wird am ZUSTAND geprueft, nicht am
	# Zaehler: Steht keine unserer Zeilen mehr drin, ist es getan.
	return 0
}

zeilen_zuruecknehmen || BEFUND=1

log ""

# --- 2. Gruppenmitgliedschaft --------------------------------------------
#
# `usermod -rG` gibt es nicht ueberall; der portable Weg ist `gpasswd -d`.
# Faellt beides weg, wird das GESAGT und nicht stillschweigend als Erfolg
# verbucht.
gruppe_zuruecknehmen() {
	_gz_n=0
	manifest_list gruppe | while IFS='	' read -r _gz_g _gz_user; do
		[ -n "$_gz_g" ] || continue
		[ -n "$_gz_user" ] || { warn "Gruppeneintrag ohne Nutzer: $_gz_g"; continue; }

		# Ist der Nutzer ueberhaupt (noch) drin?
		if ! id -nG "$_gz_user" 2>/dev/null | tr ' ' '\n' |
		     grep -qx "$_gz_g"; then
			info "schon draussen: $_gz_user aus $_gz_g"
			continue
		fi

		if is_dry_run; then
			info "[wuerde entfernen] $_gz_user aus Gruppe $_gz_g"
			continue
		fi

		if command -v gpasswd >/dev/null 2>&1; then
			if gpasswd -d "$_gz_user" "$_gz_g" >/dev/null 2>&1; then
				info "entfernt: $_gz_user aus $_gz_g"
			else
				warn "Konnte $_gz_user nicht aus $_gz_g entfernen."
			fi
		else
			warn "gpasswd fehlt -- $_gz_user bleibt in Gruppe $_gz_g."
			warn "Von Hand: gpasswd -d $_gz_user $_gz_g"
		fi
	done
	return 0
}

log "Gruppen"
gruppe_zuruecknehmen || BEFUND=1

log ""

# --- 3. Was absichtlich bleibt, wird benannt ------------------------------
#
# Schweigen ist hier nicht zulaessig (Architekturregel 8a): Wer nicht sagt,
# was stehen bleibt, laesst den Nutzer im Glauben, das System sei im
# Ausgangszustand.
log "Was absichtlich bleibt"

if manifest_has modul snd-soc-whisplay 2>/dev/null; then
	info "Das Kernelmodul bleibt -- es kam vom Herstellerinstaller."
else
	info "Kein von uns gebautes Kernelmodul im Manifest."
fi

_SICHERUNGEN="$(manifest_list sicherung | grep -c . || true)"
if [ "${_SICHERUNGEN:-0}" -gt 0 ]; then
	info "$_SICHERUNGEN Sicherung(en) bleiben liegen:"
	manifest_list sicherung | while IFS='	' read -r _s_kopie _s_orig; do
		[ -n "$_s_kopie" ] || continue
		info "  $_s_kopie  (Original: $_s_orig)"
	done
	info "Sie werden beim Rueckbau NICHT geloescht -- genau jetzt will man"
	info "sie haben. Wegraeumen von Hand, wenn das System wieder laeuft."
fi

info "Ein Neustart ist noetig, damit die Bootkonfiguration greift."

log_close "$BEFUND"
exit "$BEFUND"
