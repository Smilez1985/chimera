#!/bin/sh
# Chimera installer — Bestandsverzeichnis.
#
# **Wer etwas ablegt, schreibt auf, wo er es abgelegt hat.** Ohne das kann
# eine Deinstallation nur raten -- und Raten heisst hier, fremde Dateien zu
# loeschen oder eigene liegenzulassen.
#
# Das Verzeichnis ist die einzige Wahrheitsquelle darueber, was Chimera am
# System geaendert hat. Nicht eine Marke ("installiert: ja"), sondern eine
# Liste mit Herkunft: Welches Modul, welche Art, welcher Pfad, wann.
#
# Format: eine Zeile je Eintrag, Tabulator als Trenner.
#
#   zeitstempel  modul  art  pfad_oder_name  angabe
#
# Warum Tabulator: Pfade enthalten Leerzeichen, Paketnamen Bindestriche,
# und ein Trennzeichen darf nicht im Inhalt vorkommen. (Gelernt bei der
# Mustertabelle des Secrets-Pruefers, wo `|` die Regex-Alternativen
# zerschnitt.)
#
# Arten:
#   paket      per Paketverwaltung installiert     Angabe: vorher_da|neu
#   datei      von uns angelegt                    Angabe: Pruefsumme
#   zeile      an eine Fremddatei angehaengt       Angabe: die Zeile
#   sicherung  Kopie einer Fremddatei              Angabe: Originalpfad
#   verzeich   von uns angelegtes Verzeichnis      Angabe: leer
#   dienst     systemd-Einheit eingerichtet        Angabe: aktiviert|nur_da
#   gruppe     Nutzer einer Gruppe hinzugefuegt    Angabe: Nutzer
#   modul      Kernelmodul gebaut und installiert  Angabe: Version
#
# Die Unterscheidung `vorher_da` gegen `neu` ist der wichtigste Teil: Ein
# Paket, das es vor Chimera schon gab, darf eine Deinstallation NICHT
# entfernen. Wer das nicht mitschreibt, reisst beim Aufraeumen halbe
# Systeme mit.

: "${CHIMERA_BESTAND:=${CHIMERA_ROOT}/var/lib/chimera/bestand.tsv}"

bestand_init() {
	_bi_d="$(dirname "$CHIMERA_BESTAND")"
	mkdir -p "$_bi_d" 2>/dev/null || {
		warn "Bestandsverzeichnis nicht anlegbar: $_bi_d"
		warn "Es wird installiert, aber nicht festgehalten — eine spaetere"
		warn "Deinstallation muesste raten. Das ist ein Mangel, kein Detail."
		return 1
	}
	[ -f "$CHIMERA_BESTAND" ] && return 0

	{
		echo "# Chimera-Bestandsverzeichnis. Von hier liest die Deinstallation."
		echo "# Nicht von Hand bearbeiten -- ausser man weiss, was man tut."
		echo "# zeit	modul	art	pfad_oder_name	angabe"
	} >"$CHIMERA_BESTAND" 2>/dev/null || return 1
	info "Bestandsverzeichnis angelegt: $CHIMERA_BESTAND"
}

# Einen Eintrag festhalten.
# $1 Art, $2 Pfad oder Name, $3 Angabe (optional)
bestand_merke() {
	_bm_art="$1"
	_bm_was="$2"
	_bm_angabe="${3:-}"
	_bm_modul="${CHIMERA_MODUL:-unbekannt}"

	is_dry_run && { info "[wuerde merken] $_bm_art $_bm_was"; return 0; }

	bestand_init || return 1

	# Schon vermerkt? Dann nicht doppelt -- der Installer ist idempotent,
	# das Verzeichnis muss es auch sein.
	if bestand_hat "$_bm_art" "$_bm_was"; then
		return 0
	fi

	printf '%s\t%s\t%s\t%s\t%s\n' \
		"$(date '+%Y-%m-%dT%H:%M:%S')" "$_bm_modul" \
		"$_bm_art" "$_bm_was" "$_bm_angabe" \
		>>"$CHIMERA_BESTAND" 2>/dev/null || {
			warn "Eintrag nicht festgehalten: $_bm_art $_bm_was"
			return 1
		}
}

# Steht etwas schon im Verzeichnis?
bestand_hat() {
	[ -f "$CHIMERA_BESTAND" ] || return 1
	awk -F'\t' -v a="$1" -v w="$2" \
		'$1 !~ /^#/ && $3 == a && $4 == w { found=1 } END { exit !found }' \
		"$CHIMERA_BESTAND" 2>/dev/null
}

# Alle Einträge einer Art ausgeben (Pfad/Name, eine Zeile je Eintrag).
bestand_liste() {
	[ -f "$CHIMERA_BESTAND" ] || return 0
	if [ -n "${1:-}" ]; then
		awk -F'\t' -v a="$1" '$1 !~ /^#/ && $3 == a { print $4 "\t" $5 }' \
			"$CHIMERA_BESTAND" 2>/dev/null
	else
		grep -v '^#' "$CHIMERA_BESTAND" 2>/dev/null
	fi
}

# --- Hilfen, die gleich mitschreiben --------------------------------------
#
# Damit das Festhalten nicht vergessen werden kann: Wer diese Funktionen
# benutzt, bekommt den Eintrag geschenkt. Ein Modul, das `netz_apt` direkt
# aufruft, muesste selbst daran denken -- und genau das wird vergessen.

# Pakete installieren UND festhalten, ob sie vorher schon da waren.
#
# Die Unterscheidung ist der Kern: `apt-get install` meldet Erfolg auch
# fuer ein Paket, das schon installiert war. Wer das nicht vorher prueft,
# kann spaeter nicht sagen, was er entfernen darf.
bestand_apt() {
	_ba_neu=""
	_ba_alt=""

	for _ba_p in "$@"; do
		if bestand_paket_da "$_ba_p"; then
			_ba_alt="$_ba_alt $_ba_p"
		else
			_ba_neu="$_ba_neu $_ba_p"
		fi
	done

	[ -n "$_ba_alt" ] && info "schon installiert:$_ba_alt"

	if [ -z "$_ba_neu" ]; then
		# Nichts zu tun. Die vorher vorhandenen trotzdem vermerken, damit
		# die Deinstallation weiss, dass sie sie NICHT anfassen darf.
		for _ba_p in $_ba_alt; do
			bestand_merke paket "$_ba_p" "vorher_da"
		done
		return 0
	fi

	info "wird installiert:$_ba_neu"
	netz_apt $_ba_neu || return 1

	for _ba_p in $_ba_neu; do
		# Erst nach dem Erfolg vermerken, und nur, was wirklich da ist.
		# Im Trockenlauf wurde nichts installiert -- dann waere die
		# Pruefung eine Beschwerde ueber das eigene Nichtstun.
		if is_dry_run; then
			info "[wuerde merken] paket $_ba_p (neu)"
		elif bestand_paket_da "$_ba_p"; then
			bestand_merke paket "$_ba_p" "neu"
		else
			warn "$_ba_p gilt als installiert, ist aber nicht da."
		fi
	done
	for _ba_p in $_ba_alt; do
		bestand_merke paket "$_ba_p" "vorher_da"
	done
}

bestand_paket_da() {
	if have_cmd dpkg-query; then
		[ "$(dpkg-query -W -f='${db:Status-Status}' "$1" 2>/dev/null)" = "installed" ]
	elif have_cmd apk; then
		apk info -e "$1" >/dev/null 2>&1
	else
		return 1
	fi
}

# Eine Zeile an eine Fremddatei anhaengen und festhalten, dass sie von uns
# ist. Ohne diesen Vermerk kann die Deinstallation nicht unterscheiden,
# welche Zeilen der Nutzer selbst eingetragen hat.
bestand_zeile() {
	_bz_datei="$1"
	_bz_zeile="$2"

	if grep -qxF "$_bz_zeile" "$_bz_datei" 2>/dev/null; then
		info "schon gesetzt: $_bz_zeile"
		# Trotzdem vermerken: Beim ersten Lauf war die Zeile vielleicht
		# schon da, weil der Nutzer sie selbst eingetragen hat. Dann
		# gehoert sie ihm -- also als `vorher_da` festhalten, damit die
		# Deinstallation sie stehen laesst.
		bestand_hat zeile "$_bz_datei" || \
			bestand_merke zeile "$_bz_datei" "vorher_da:$_bz_zeile"
		return 0
	fi

	if is_dry_run; then
		info "[wuerde anhaengen] $_bz_zeile"
		return 0
	fi

	printf '%s\n' "$_bz_zeile" >>"$_bz_datei" || {
		err "Konnte nicht schreiben: $_bz_datei"
		return 1
	}
	info "gesetzt: $_bz_zeile"
	bestand_merke zeile "$_bz_datei" "neu:$_bz_zeile"
}

# --- Bericht --------------------------------------------------------------
bestand_bericht() {
	[ -f "$CHIMERA_BESTAND" ] || {
		info "Noch nichts festgehalten."
		return 0
	}
	log "Was Chimera am System geaendert hat"
	for _bb_a in paket zeile datei verzeich dienst gruppe modul sicherung; do
		_bb_n="$(bestand_liste "$_bb_a" | grep -c . || true)"
		[ "${_bb_n:-0}" -gt 0 ] && info "$_bb_a: $_bb_n"
	done
	info "Verzeichnis: $CHIMERA_BESTAND"
}
