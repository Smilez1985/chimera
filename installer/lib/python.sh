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

# --- uv (Vorgabe smilez 2.11./5.11.) -------------------------------------
#
# Warum ueberhaupt: uv loest Abhaengigkeiten als Ganzes auf und ist auf dem
# Pi deutlich schneller als pip. Die Anforderungen in requirements.txt gelten
# weiter, uv aendert die Auswahl nicht -- es nimmt nur dieselbe Arbeit
# schneller und mit einem pruefbaren Lock.
#
# Zwei Grundsaetze, die daran haengen:
#   * uv liegt in einem EIGENEN Werkzeug-venv und wird nur angelegt, wenn es
#     fehlt (idempotent, wie alles hier). Installiert wird es mit pip --
#     pip prueft die Pruefsummen der PyPI, uv selbst tut das beim Holen auch.
#   * uv ist eine BESCHLEUNIGUNG, keine Bedingung: fehlt es, laesst es sich
#     nicht anlegen oder scheitert es, laeuft derselbe Abruf ueber pip. Eine
#     eigene Fehlerquelle darf hier nicht entstehen.
#
# Gemessen (5.11.2026, uv 0.13.7 aarch64): `uv pip install --python <venv>`
# gibt es; `uv pip download` nicht.

: "${CHIMERA_UV:=an}"
: "${CHIMERA_UV_FRIST:=600}"     # harte Zeitgrenze je uv-Aufruf (Sekunden)

# Ist uv eingeschaltet? Einzige Stelle, an der der Schalter gelesen wird.
uv_an() {
	[ "${CHIMERA_UV:-an}" != aus ]
}

uv_verzeichnis() {
	printf '%s/tools/uv' "$(rootpath "${CHIMERA_OPT:-/opt/chimera}")"
}

# Pfad zum lauffaehigen uv, sonst rc 1. Ein Verzeichnis mit uv-Datei ist
# kein Beleg -- gefragt wird das Programm (Regel 10j).
uv_weg() {
	_uw_b="$(uv_verzeichnis)/bin/uv"
	[ -x "$_uw_b" ] || return 1
	"$_uw_b" --version >/dev/null 2>&1 || return 1
	printf '%s\n' "$_uw_b"
}

# uv herstellen, nur wenn es fehlt. rc 0 vorhanden, 1 nicht verfuegbar
# (dann pip), 2 abgeschaltet.
uv_bereitstellen() {
	uv_an || return 2
	uv_weg >/dev/null 2>&1 && return 0
	_ub_d="$(uv_verzeichnis)"
	info "uv: wird eingerichtet ($_ub_d) ..."
	mkdir -p "$(dirname "$_ub_d")" 2>/dev/null || return 1
	[ -x "$_ub_d/bin/python" ] || {
		python3 -m venv "$_ub_d" >/dev/null 2>&1 || {
			warn "uv: Werkzeug-venv nicht anlegbar -- es bleibt bei pip."
			return 1
		}
	}
	# pip in diesem venv holt uv samt Pruefsummenpruefung der PyPI.
	# --no-input/--disable-pip-version-check: keine Rueckfragen, kein Netz
	# fuer eine Versionsanzeige.
	_ub_rc=0
	"$_ub_d/bin/python" -m pip install --quiet --no-input \
		--disable-pip-version-check uv >/dev/null 2>&1 || _ub_rc=$?
	if [ "$_ub_rc" != 0 ] || ! uv_weg >/dev/null 2>&1; then
		warn "uv: liess sich nicht installieren (rc=$_ub_rc) -- es bleibt bei pip."
		return 1
	fi
	info "uv: bereit ($(uv_weg 2>/dev/null))"
	return 0
}

# Anforderungen in ein venv bringen -- uv zuerst, pip als Rueckfall.
# $1 Python des venv, $2.. Anforderungen. rc 0 = ohne Fehler durchgelaufen
# (das Ergebnis prueft der Aufrufer nach, nicht dieser Exitcode).
pydep_holen() {
	_ph_py="$1"; shift
	_ph_uv="$(uv_weg 2>/dev/null)" || _ph_uv=""
	# Der Schalter gilt auch fuer die NUTZUNG, nicht nur fuers Anlegen --
	# sonst laesst sich ohne uv nicht messen (am Pi 5.11. aufgefallen: Lauf
	# mit CHIMERA_UV=aus benutzte trotzdem uv).
	uv_an || _ph_uv=""
	if [ -n "$_ph_uv" ]; then
		info "uv: hole $*"
		# Harte Zeitgrenze: ein haengender Abruf darf den Lauf nicht
		# festhalten. timeout gibt es in BusyBox und in Debian; fehlt es,
		# laeuft der Aufruf ohne Grenze (besser als gar kein uv).
		set +e
		if command -v timeout >/dev/null 2>&1; then
			timeout "${CHIMERA_UV_FRIST:-600}" "$_ph_uv" pip install \
				--python "$_ph_py" "$@"
		else
			"$_ph_uv" pip install --python "$_ph_py" "$@"
		fi
		_ph_rc=$?
		set -e
		[ "$_ph_rc" = 0 ] && return 0
		warn "uv: Exitcode $_ph_rc -- derselbe Abruf geht ueber pip."
	fi
	# pip, wie vor uv. Kein --upgrade: pip holt eine Fassung, die die
	# Anforderung erfuellt.
	set +e
	printf '%s\n' "$@" | grep -v '^$' | xargs "$_ph_py" -m pip install
	_ph_rc=$?
	set -e
	return "$_ph_rc"
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
	# Nur die betroffenen, nicht die ganze Liste -- und zwar ohne
	# `--upgrade`: pip holt eine Fassung, die die Anforderung erfuellt.
	# Mit `--upgrade` zieht pip auch dann die jeweils neueste, wenn die
	# vorhandene genuegt. (Der Fall "numpy 2.5.4 statt 1.26.4" kam nicht
	# daher, sondern von der Anforderung ohne Obergrenze; offener Punkt
	# in docs/ROADMAP.md.)
	#
	# Und der Abruf wird UMWARTET, nicht abgebrochen: Fehlt das Netz,
	# pausiert die Schleife, bis es zurueck ist (Vorgabe smilez: Downloads
	# und Abhaengigkeiten in derselben Warte-Schleife wie network_fetch,
	# Vorbild rag4ll bg-downloader). Erst wenn das Netz steht und pip
	# trotzdem scheitert, ist es ein Befund.
	# shellcheck disable=SC2086
	_pe_versuche="${CHIMERA_PIP_VERSUCHE:-3}"
	# uv einmal bereitstellen (nur anlegen, wenn es fehlt). Scheitert es,
	# laeuft alles ueber pip -- das ist der Rueckfall, kein Befund.
	uv_bereitstellen || true
	_pe_n=0
	_pe_ok=""
	while [ "$_pe_n" -lt "$_pe_versuche" ]; do
		_pe_n=$((_pe_n + 1))
		if command -v netz_warten_erreichbar >/dev/null 2>&1; then
			netz_warten_erreichbar || {
				err "Kein Netz -- pip-Abruf abgebrochen."
				return 1
			}
		fi
		[ "$_pe_n" -gt 1 ] && info "Versuch $_pe_n von $_pe_versuche"
		# uv zuerst, pip als Rueckfall (pydep_holen entscheidet und benennt
		# es).
		# shellcheck disable=SC2086
		_pe_rc=0
		pydep_holen "$_pe_py" $_pe_holt || _pe_rc=$?
		if [ "$_pe_rc" = 0 ]; then
			_pe_ok=1
			break
		fi
		warn "pip unterbrochen (Exitcode $_pe_rc)."
		[ "$_pe_n" -lt "$_pe_versuche" ] && sleep 2
	done
	[ -n "$_pe_ok" ] || warn "pip meldete einen Fehler -- entscheidend ist die Nachmessung."
	_pe_f="$(pydep_fehlend "$_pe_py" "$@")" && { info "Python-Abhaengigkeiten hergestellt."; return 0; }
	err "Nach pip weiterhin nicht erfuellt:"
	printf '%s\n' "$_pe_f" | sed 's/^/    /' >&2
	return 1
}
