#!/bin/sh
# Chimera installer -- Quelle: lokale SSOT-Kopie (DESIGN Regel 10r).
#
# Egal woher der Code kommt (Git-Klon, Zip, spaeter apt/npm): Der Installer
# arbeitet aus /opt/chimera/source. Diese Bibliothek entscheidet, ob die
# Kopie erneuert wird, und tauscht sie.
#
# Entscheidung (smilez, 10.10.2026: "Hash wiegt schwerer als Version"):
#   gleicher Hash                    -> nichts zu tun, naechster Schritt
#   anderer Hash, VERSION >= vorhanden -> ersetzen
#   anderer Hash, VERSION <  vorhanden -> nur mit --downgrade=true
#
# Gleichheit ist eine Frage des INHALTS, nicht des Git-Commits: Zip und
# Paket haben keinen. Neuer/aelter ist eine Frage der VERSION -- eine
# Pruefsumme sagt nur "anders", nicht "neuer".

# Was nicht zum Stand gehoert: Versionsverwaltung, Testreste, Bytecode.
# Steht an EINER Stelle; Hash und Kopie benutzen dieselbe Liste, sonst
# meldete der Hash nach jeder Kopie "anders".
_SRC_AUSSCHLUSS='.git .testtmp __pycache__ logs'

# Inhaltspruefsumme eines Baums. Relative Pfade und Inhalte gehen ein,
# sortiert unter LC_ALL=C (common.sh) -- gleiche Baeume ergeben ueberall
# dieselbe Summe. Gibt nichts aus, wenn der Baum fehlt (Pruefung beim
# Aufrufer: leer ist ein Verdachtsfall).
source_hash() {
	[ -d "$1" ] || return 1
	( cd "$1" || exit 1
	  _sh_find=""
	  for _sh_x in $_SRC_AUSSCHLUSS; do
		_sh_find="$_sh_find -name $_sh_x -prune -o"
	  done
	  # shellcheck disable=SC2086
	  find . $_sh_find -type f ! -name '*.pyc' -print | sort |
	  while IFS= read -r _sh_f; do
		printf '%s  %s\n' "$(sha256sum <"$_sh_f" | cut -d' ' -f1)" "$_sh_f"
	  done | sha256sum | cut -d' ' -f1 )
}

source_version() { tr -d ' \t\r\n' <"$1/VERSION" 2>/dev/null; }

# Versionsvergleich. Ausgabe: lt | eq | gt (erste gegen zweite).
#
# `sort -V` ordnet "0.1.0-pre" HINTER "0.1.0" -- eine Vorabfassung galte
# als neuer als das Release (gemessen, GNU coreutils). Mit "~" statt "-"
# ordnet es richtig davor. Darum wird vor dem Vergleich umgeschrieben.
version_cmp() {
	[ "$1" = "$2" ] && { echo eq; return 0; }
	_vc_a="$(printf '%s' "$1" | tr '-' '~')"
	_vc_b="$(printf '%s' "$2" | tr '-' '~')"
	_vc_min="$(printf '%s\n%s\n' "$_vc_a" "$_vc_b" | sort -V | head -1)"
	if [ "$_vc_min" = "$_vc_a" ]; then echo lt; else echo gt; fi
}

# Hoechster veroeffentlichter Stand: vX.Y.Z-Tags der Quelle, nie eine
# Zweigspitze. Ausgabe: Tag oder nichts. rc 0 nachgesehen, 2 nicht
# nachsehbar (offline, Quelle nicht erreichbar, kein git).
#
# $1 Quelle (URL oder lokaler Pfad -- Tests benutzen ein lokales Repo).
source_neuester_tag() {
	have_cmd git || return 2
	case "$1" in
		http://*|https://*)
			_nt_host="$(printf '%s' "$1" | sed 's|^[a-z]*://||; s|/.*||')"
			network_reachable "$_nt_host" 443 5 >/dev/null 2>&1 || return 2 ;;
	esac
	_nt_l="$(git ls-remote --tags --refs "$1" 'v*' 2>/dev/null)" || return 2
	printf '%s\n' "$_nt_l" | sed 's|.*refs/tags/||' |
		grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' |
		sed 's/^v//' | sort -V | tail -1 | sed 's/^./v&/'
	return 0
}

# Einen Tag in ein Verzeichnis holen. rc 0 ok.
#
# --no-local: Bei einer lokalen Quelle (Spiegel, Testrepo) klont git sonst
# per Hardlink -- auf manchen Dateisystemen scheitert das ("hardlink
# different from source"), und --depth wird ignoriert. Fuer eine URL
# aendert die Option nichts.
source_tag_holen() {
	rm -rf "$3"
	git -c advice.detachedHead=false clone -q --no-local --depth 1 --branch "$2" "$1" "$3" \
		>/dev/null 2>&1 || return 1
	[ -f "$3/VERSION" ] || return 1
}

# Baum nach Ziel kopieren -- ueber ein Nachbarverzeichnis, geprueft, dann
# getauscht. $1 Quelle, $2 Ziel (echter Pfad), $3 erwarteter Hash.
#
# Der Tausch sind zwei Umbenennungen. Dazwischen gibt es kein Ziel; bricht
# der Lauf genau dort ab, liegt die alte Fassung als <ziel>.alt neben dem
# Ziel, und source_reparieren stellt sie beim naechsten Lauf wieder her.
source_kopieren() {
	_sk_von="$1"; _sk_nach="$2"; _sk_soll="$3"
	_sk_neu="$_sk_nach.neu"; _sk_alt="$_sk_nach.alt"
	mkdir -p "$(dirname "$_sk_nach")" || return 1
	rm -rf "$_sk_neu"
	mkdir -p "$_sk_neu" || return 1
	_sk_ex=""
	for _sk_x in $_SRC_AUSSCHLUSS; do _sk_ex="$_sk_ex --exclude=$_sk_x"; done
	# shellcheck disable=SC2086
	( cd "$_sk_von" && tar -cf - $_sk_ex --exclude='*.pyc' . ) |
		( cd "$_sk_neu" && tar -xf - ) || { rm -rf "$_sk_neu"; return 1; }
	# Fuer den Dienstnutzer lesbar, fuer niemanden ausser root schreibbar --
	# egal mit welcher umask der Startbaum entstand.
	chmod -R u+rwX,go+rX,go-w "$_sk_neu" 2>/dev/null
	# Am Ergebnis pruefen: die Kopie muss den erwarteten Inhalt tragen.
	_sk_ist="$(source_hash "$_sk_neu")"
	if [ -z "$_sk_ist" ] || [ "$_sk_ist" != "$_sk_soll" ]; then
		err "Kopie weicht ab (soll $_sk_soll, ist ${_sk_ist:-leer}) -- nicht getauscht."
		rm -rf "$_sk_neu"; return 1
	fi
	rm -rf "$_sk_alt"
	if [ -d "$_sk_nach" ]; then mv "$_sk_nach" "$_sk_alt" || return 1; fi
	mv "$_sk_neu" "$_sk_nach" || { [ -d "$_sk_alt" ] && mv "$_sk_alt" "$_sk_nach"; return 1; }
	rm -rf "$_sk_alt"
	return 0
}

# Abgebrochenen Tausch heilen: Ziel fehlt, .alt liegt da -> zurueck.
source_reparieren() {
	if [ ! -d "$1" ] && [ -d "$1.alt" ]; then
		warn "Abgebrochener Tausch gefunden -- alte Fassung wird wiederhergestellt."
		mv "$1.alt" "$1"
	fi
	rm -rf "$1.neu" 2>/dev/null || true
}

# Die Entscheidung als reine Funktion (testbar ohne Dateisystem).
# $1 Hash Kandidat, $2 Hash vorhanden (leer = fehlt), $3 VERSION Kandidat,
# $4 VERSION vorhanden, $5 Downgrade erlaubt (true|false).
# Ausgabe: anlegen | gleich | ersetzen | ersetzen_gleiche_version |
#          downgrade | abgelehnt
source_entscheiden() {
	[ -n "$2" ] || { echo anlegen; return; }
	[ "$1" = "$2" ] && { echo gleich; return; }
	case "$(version_cmp "$3" "$4")" in
		gt) echo ersetzen ;;
		eq) echo ersetzen_gleiche_version ;;
		lt) if [ "$5" = true ]; then echo downgrade; else echo abgelehnt; fi ;;
	esac
}
