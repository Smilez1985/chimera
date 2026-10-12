#!/bin/sh
# Chimera installer -- Python-Abhaengigkeiten im venv, mit Versionspruefung.
#
# Regel (smilez, 11.10.2026): Alles, was der Code braucht, stellt der
# Installer her -- idempotent (fehlt es, kommt es) UND mit Versionspruefung
# (ist es zu alt, wird es erneuert). Ein `pip install -r` tut das zwar auch,
# aber es sagt nicht, WAS es getan hat, und es laeuft bei jedem Lauf gegen
# den Index -- offline schlug es am chimera-pi fehl, obwohl alles da war.
#
# Deshalb: erst messen (importlib.metadata im venv), dann nur das holen,
# was fehlt oder zu alt ist, dann nochmal messen. Das Ergebnis zaehlt, nicht
# der Exitcode von pip (Regel 10j).
#
# Anforderungen im Format von requirements.txt: `Name`, `Name>=1.2`,
# `Name==1.2`, `Name>=1.2,<3`; Kommentare und Leerzeilen werden ueberlesen.
# Verglichen wird mit packaging, wenn vorhanden, sonst mit einem einfachen
# Zahlenvergleich (reicht fuer >= und == auf X.Y.Z; Vorab-Fassungen gelten
# als kleiner).

# Die Messung selbst steht in lib/py/pydep.py (bis 12.10.2026 als Heredoc
# hier). Der Pfad kommt von der Bibliothek, nicht vom Aufrufer: Schritte
# sourcen sie aus <installer>/lib, und dort liegt py/ daneben. _HERE setzen
# alle Schritte vor dem Sourcen (installer/), HERE die Tests.
_PYDEP_PY="${_HERE:-${HERE:-.}}/lib/py/pydep.py"

# Welche Anforderungen sind im venv NICHT erfuellt? $1 Python des venv,
# $2.. Anforderungen (eine je Argument). Ausgabe: je Zeile
#   <anforderung>\t<ist-version oder "fehlt">
# rc 0 alles erfuellt, 1 etwas fehlt/zu alt, 2 nicht pruefbar (kein Python).
pydep_fehlend() {
	_pf_py="$1"; shift
	[ -x "$_pf_py" ] || return 2
	# Ohne die Messdatei ist nichts pruefbar -- benannt, nicht geraten.
	[ -f "$_PYDEP_PY" ] || { err "Versionspruefung fehlt: $_PYDEP_PY"; return 2; }
	"$_pf_py" "$_PYDEP_PY" "$@"
}

# Anforderungen aus einer requirements-Datei lesen (ohne Kommentare/Leerzeilen).
pydep_liste() {
	grep -vE '^[[:space:]]*(#|$)' "$1" 2>/dev/null | sed 's/[[:space:]]*#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//' | grep -v '^$'
}

# Herstellen: fehlende/zu alte Anforderungen holen, dann nachmessen.
# $1 Python des venv, $2.. Anforderungen. Benennt, was es tat.
# rc 0 alles erfuellt (vorher oder jetzt), 1 pip lief, Ergebnis stimmt
# trotzdem nicht, 2 nicht pruefbar.
pydep_ensure() {
	_pe_py="$1"; shift
	[ $# -gt 0 ] || return 0
	_pe_f="$(pydep_fehlend "$_pe_py" "$@")"; _pe_rc=$?
	[ "$_pe_rc" = 2 ] && { err "Python nicht ausfuehrbar: $_pe_py"; return 2; }
	if [ "$_pe_rc" = 0 ]; then
		info "Python-Abhaengigkeiten erfuellt: $*"
		return 0
	fi
	_pe_holt=""
	while IFS='	' read -r _pe_a _pe_ist; do
		[ -n "$_pe_a" ] || continue
		if [ "$_pe_ist" = fehlt ]; then
			info "fehlt: $_pe_a"
		else
			info "zu alt: $_pe_a (ist $_pe_ist)"
		fi
		_pe_holt="$_pe_holt
$_pe_a"
	done <<EOF
$_pe_f
EOF
	if is_dry_run; then
		info "[wuerde installieren]$(printf '%s' "$_pe_holt" | tr '\n' ' ')"
		return 0
	fi
	# Nur die betroffenen, nicht die ganze Liste -- und `--upgrade`, damit
	# "zu alt" auch wirklich erneuert wird (ohne haelt pip ein vorhandenes
	# Paket fuer erfuellt, selbst wenn die Anforderung hoeher liegt).
	# shellcheck disable=SC2086
	printf '%s\n' "$_pe_holt" | grep -v '^$' | xargs "$_pe_py" -m pip install --upgrade || \
		warn "pip meldete einen Fehler -- entscheidend ist die Nachmessung."
	_pe_f="$(pydep_fehlend "$_pe_py" "$@")" && { info "Python-Abhaengigkeiten hergestellt."; return 0; }
	err "Nach pip weiterhin nicht erfuellt:"
	printf '%s\n' "$_pe_f" | sed 's/^/    /' >&2
	return 1
}
