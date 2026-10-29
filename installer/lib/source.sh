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
# dieselbe Summe. Gibt nichts aus und liefert rc 1, wenn der Baum fehlt
# oder nicht vollstaendig lesbar ist (Pruefung beim Aufrufer: leer ist ein
# Verdachtsfall).
#
# Je Datei eine Zeile "<sha256>  ./<pfad>", nach Pfad sortiert, darueber
# die Summe. Die Inhalte rechnet EIN sha256sum-Aufruf fuer alle Dateien
# (find -exec ... {} +). Vorher startete jede Datei eigene Prozesse --
# am chimera-pi 2,5 s fuer 160 Dateien, beim Boot zweimal (Schritt 50).
#
# Drei Arten Dateinamen:
# - gewoehnlich: sha256sum gibt genau diese Zeile aus, GNU wie BusyBox.
# - mit Backslash oder Wagenruecklauf: GNU sha256sum maskiert solche
#   Namen ("\<summe>  ./a\\b"), BusyBox nicht. Damit die Summe nicht vom
#   Werkzeug abhaengt, rechnen sie einzeln, der Name geht unveraendert ein.
# - mit Zeilenumbruch: keine eindeutige Zeile moeglich -> rc 1, benannt.
#   Bis 0.1.0-pre zerfiel so ein Name still in zwei Zeilen, und der Inhalt
#   der Datei fehlte in der Summe.
#
# Am Ergebnis geprueft, nicht nur am Exitcode: jede Zeile im erwarteten
# Format, und so viele Zeilen wie Dateien -- eine Summe ohne Abgleich
# gegen die Gesamtzahl waere eine Teilsumme.
source_hash() {
	[ -d "$1" ] || return 1
	( cd "$1" || exit 1
	  _sh_find=""
	  for _sh_x in $_SRC_AUSSCHLUSS; do
		_sh_find="$_sh_find -name $_sh_x -prune -o"
	  done
	  _sh_nl='
'
	  _sh_cr="$(printf '\r')"
	  # shellcheck disable=SC2086
	  _sh_lf="$(find . $_sh_find -type f ! -name '*.pyc' -path "*$_sh_nl*" -print)" || exit 1
	  if [ -n "$_sh_lf" ]; then
		printf 'Pruefsumme nicht eindeutig: Dateiname mit Zeilenumbruch: %s\n' "$_sh_lf" >&2
		exit 1
	  fi
	  # Gewoehnliche Namen: ein Aufruf (find teilt nur bei sehr langen
	  # Listen auf). Scheitert einer, meldet find rc != 0.
	  # shellcheck disable=SC2086
	  _sh_l="$(find . $_sh_find -type f ! -name '*.pyc' ! -path '*\\*' ! -path "*$_sh_cr*" \
		-exec sha256sum {} +)" || exit 1
	  # Backslash/Wagenruecklauf: einzeln, wie bis 0.1.0-pre.
	  # shellcheck disable=SC2086
	  _sh_s="$(find . $_sh_find -type f ! -name '*.pyc' \( -path '*\\*' -o -path "*$_sh_cr*" \) -print |
		while IFS= read -r _sh_f; do
			_sh_h="$(sha256sum <"$_sh_f")" || exit 1
			printf '%s  %s\n' "${_sh_h%% *}" "$_sh_f"
		done)" || exit 1
	  if [ -n "$_sh_l" ] && [ -n "$_sh_s" ]; then
		_sh_l="$_sh_l$_sh_nl$_sh_s"
	  elif [ -n "$_sh_s" ]; then
		_sh_l="$_sh_s"
	  fi
	  # shellcheck disable=SC2086
	  _sh_n="$(find . $_sh_find -type f ! -name '*.pyc' -print | wc -l)"
	  source_hash_zeilen_ok "$_sh_l" "$_sh_n" || exit 1
	  # Sortiert nach dem Pfad (Feld 2 bis Zeilenende). Alle Zeilen haben
	  # vorne gleich viele Zeichen -- die Reihenfolge ist die der Pfade.
	  { [ -z "$_sh_l" ] || printf '%s\n' "$_sh_l"; } | sort -k 2 | sha256sum | cut -d' ' -f1 )
}

# Die Zeilen fuer source_hash pruefen, bevor sie in die Summe gehen.
# $1 Zeilen, $2 Anzahl Dateien. rc 0 passt, 1 Befund (auf stderr benannt).
#   - so viele Zeilen wie Dateien (sonst waere die Summe eine Teilsumme)
#   - jede Zeile "<64 hex>  ./<pfad>" (eine maskierte Zeile von GNU
#     sha256sum beginnt mit "\" und faellt hier auf, statt still eine
#     andere Summe zu ergeben)
source_hash_zeilen_ok() {
	_hz_z=0
	[ -z "$1" ] || _hz_z="$(printf '%s\n' "$1" | wc -l)"
	if [ "$_hz_z" -ne "$2" ]; then
		printf 'Pruefsumme unvollstaendig: %s Zeilen fuer %s Dateien.\n' "$_hz_z" "$2" >&2
		return 1
	fi
	if [ "$_hz_z" -gt 0 ] && printf '%s\n' "$1" | grep -v '^[0-9a-f]\{64\}  \./' >/dev/null; then
		printf 'Pruefsumme: unerwartete Zeile von sha256sum.\n' >&2
		return 1
	fi
	return 0
}

source_version() { tr -d ' \t\r\n' <"$1/VERSION" 2>/dev/null; }

# Versionsvergleich. Ausgabe: lt | eq | gt (erste gegen zweite).
#
# `sort -V` ordnet "0.1.0-pre" HINTER "0.1.0" -- eine Vorabfassung galte
# als neuer als das Release (gemessen, GNU coreutils). Der fruehere Ausweg
# "~" statt "-" hilft nur bei GNU: BusyBox `sort -V` ordnet "0.1.0~pre"
# ebenfalls hinter "0.1.0" (gemessen, BusyBox 1.37, CI-Lauf 38830059482).
# Darum wird die Vorabkennung abgetrennt und selbst verglichen; `sort -V`
# sieht nur noch reine Zahlenfolgen, die beide Fassungen gleich ordnen.
_version_min() { printf '%s\n%s\n' "$1" "$2" | sort -V | head -1; }
version_cmp() {
	[ "$1" = "$2" ] && { echo eq; return 0; }
	_vc_a="${1%%-*}"; _vc_b="${2%%-*}"
	_vc_pa=""; _vc_pb=""
	[ "$_vc_a" = "$1" ] || _vc_pa="${1#*-}"
	[ "$_vc_b" = "$2" ] || _vc_pb="${2#*-}"
	if [ "$_vc_a" != "$_vc_b" ]; then
		if [ "$(_version_min "$_vc_a" "$_vc_b")" = "$_vc_a" ]; then echo lt; else echo gt; fi
		return 0
	fi
	# Gleicher Kern: ohne Vorabkennung ist neuer als mit (SemVer 11.3).
	if [ -z "$_vc_pa" ]; then echo gt; return 0; fi
	if [ -z "$_vc_pb" ]; then echo lt; return 0; fi
	if [ "$_vc_pa" = "$_vc_pb" ]; then echo eq; return 0; fi
	if [ "$(_version_min "$_vc_pa" "$_vc_pb")" = "$_vc_pa" ]; then echo lt; else echo gt; fi
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
	# Kein `tar --exclude`: BusyBox ohne FEATURE_TAR_LONG_OPTIONS kennt es
	# nicht (Ubuntu busybox-static 1.36.1, CI-Lauf 38830059482: "tar:
	# unrecognized option '--exclude=.git'"). Dieselbe Auswahl wie
	# source_hash (find mit -prune), die Namen gehen als Argumente an cp --
	# kein Zerlegen an Leerzeichen oder Zeilenenden.
	_sk_find=""
	for _sk_x in $_SRC_AUSSCHLUSS; do _sk_find="$_sk_find -name $_sk_x -prune -o"; done
	# shellcheck disable=SC2086
	( cd "$_sk_von" && find . $_sk_find ! -type d ! -name '*.pyc' -exec sh -c '
		ziel="$1"; shift
		for f; do
			mkdir -p "$ziel/${f%/*}" && cp -Pp "$f" "$ziel/$f" || exit 1
		done' sh "$_sk_neu" {} + ) || { rm -rf "$_sk_neu"; return 1; }
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

# --- Commit der Quelle festhalten (DESIGN Regel 14, Binary zum Commit) -----
#
# Das Rust-Binary (Schritt 55) wird zum Commit der Quelle geladen, nie "das
# neueste". Darum merkt sich Schritt 00 den Commit, solange .git noch da ist
# (source/ hat keins). Ausgabe auf stdout: die 7 Zeichen, oder nichts.
#
# Leer ist ein benannter Befund, kein Fehler: Zip und Paket haben keinen
# Commit. Leer ist es auch, wenn rust/ oder VERSION gegenueber dem Commit
# geaendert sind -- das Binary zum Commit passte dann nicht zum Inhalt, und
# ein passendes zu raten waere genau das, was Regel "Nie raten" verbietet.
# $1 Baum
source_commit_lesen() {
	[ -d "$1/.git" ] || return 0
	have_cmd git || return 0
	_sc_c="$(git -C "$1" rev-parse --short=7 HEAD 2>/dev/null)" || return 0
	case "$_sc_c" in ''|*[!0-9a-f]*) return 0 ;; esac
	# status schweigt bei einem Fehler genauso wie bei "sauber": den
	# Exitcode pruefen, nicht nur die Ausgabe.
	_sc_s="$(git -C "$1" status --porcelain -- rust VERSION 2>/dev/null)" || return 0
	[ -z "$_sc_s" ] || return 0
	printf '%s' "$_sc_c"
}

# Festhalten: schreibt state/quelle-commit (atomar, Sidecar + mv) oder
# entfernt eine alte Datei, wenn der neue Stand keinen Commit hat -- ein
# veralteter Commit waere schlimmer als keiner.
# $1 Baum, $2 Datei. Ausgabe: der Commit oder nichts. rc 1 bei Schreibfehler.
source_commit_festhalten() {
	_sf_c="$(source_commit_lesen "$1")"
	if [ -z "$_sf_c" ]; then
		rm -f "$2"
		return 0
	fi
	mkdir -p "$(dirname "$2")" || return 1
	printf '%s\n' "$_sf_c" >"$2.neu" || { rm -f "$2.neu"; return 1; }
	mv "$2.neu" "$2" || { rm -f "$2.neu"; return 1; }
	[ "$(cat "$2" 2>/dev/null)" = "$_sf_c" ] || return 1
	printf '%s' "$_sf_c"
}
