#!/bin/sh
# Vorab-Laden im Hintergrund (DESIGN, Regel "Warte-Schleife und Vorab-Laden").
#
# Der Installer kennt seine Downloads, BEVOR er sie braucht. Dieser Helfer
# holt sie in Modulreihenfolge, waehrend der Lauf arbeitet -- ein Objekt
# nach dem anderen, nicht alle gleichzeitig (ein Zero 2 W hat eine Leitung).
#
# Je Objekt eine Marke unter $CHIMERA_STATE/prefetch/:
#   <name>.teil    unterwegs (fortsetzbar, wird nie als fertig gelesen)
#   <name>.done    fertig -- erst nach Pruefung geschrieben, atomar
#   <name>.fehler  Grund, warum es nicht ging
#
# Grundsatz: Eine Marke beschleunigt nur, sie ist NIE Bedingung. Jeder
# Verbraucher prueft seine Ware selbst (Pruefsumme, Version). Ein toter oder
# haengender Vorab-Lader darf keinen Installationsschritt blockieren.
#
# Was NICHT hierher gehoert: `apt`. dpkg hat eine Sperre, und die Pakete
# werden von Modul 20 als erstes gebraucht -- ein paralleler apt-Lauf
# blockiert sich mit dem Installer selbst (gemessen: 4.11.).

: "${CHIMERA_PREFETCH_RAD:=1}"

vorab_verzeichnis() {
	printf '%s/prefetch' "$(rootpath "${CHIMERA_STATE:-/opt/chimera/state}")"
}

vorab_anlegen() {
	_vb_d="$(vorab_verzeichnis)"
	mkdir -p "$_vb_d" 2>/dev/null || return 1
	[ -w "$_vb_d" ] || return 1
}

# Ist das Objekt fertig vorgeladen? Prueft NUR die Marke; die Ware prueft
# der Verbraucher (siehe Kopf).
vorab_fertig() {
	[ -f "$(vorab_verzeichnis)/$1.done" ]
}

vorab_fehler_grund() {
	cat "$(vorab_verzeichnis)/$1.fehler" 2>/dev/null || true
}

# Marke setzen. Atomar: erst .teil, dann umbenennen -- nie eine halbe Marke.
vorab_marke_done() {
	_vb_d="$(vorab_verzeichnis)"
	_vb_t="$_vb_d/$1.done.teil"
	{
		printf 'objekt=%s\n' "$1"
		printf 'zeit=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
		printf 'gast=%s\n' "$(hostname 2>/dev/null || echo unbekannt)"
	} >"$_vb_t" && mv "$_vb_t" "$_vb_d/$1.done"
}

vorab_marke_fehler() {
	_vb_d="$(vorab_verzeichnis)"
	_vb_t="$_vb_d/$1.fehler.teil"
	{
		printf 'objekt=%s\n' "$1"
		printf 'zeit=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
		printf 'grund=%s\n' "$2"
	} >"$_vb_t" && mv "$_vb_t" "$_vb_d/$1.fehler"
}

# --- Die Objekte, in der Reihenfolge, in der die Module sie brauchen ------
#
# Je Zeile: Name <Tab> Art <Tab> Parameter
#   apt  <pakete>            -> .deb in den apt-Cache (Modul 20/30/40)
#   pip  <anforderungen>     -> Wheels nach <prefetch>/wheels (Modul 50)
#
# Die Liste ist bewusst kurz: Was wenige Sekunden kostet, wird nicht
# vorgeladen -- der Aufwand waere groesser als der Gewinn (gemessen 4.11.:
# Whisplay-Klon 3 s, rust-Binary 1 s, pip-Wheels 18 s, apt-Pakete 40-80 MB).
#
# `apt` steht vorn (Vorgabe smilez, 4.11.): apt holt und installiert je
# Paket nacheinander. Holt man die .deb VORHER alle zusammen, faellt der
# Netzanteil aus der Installation heraus -- `apt-get install` entpackt dann
# nur noch aus dem eigenen Cache.
vorab_liste() {
	cat <<'EOF'
apt-debs	apt	git gcc make device-tree-compiler alsa-utils ca-certificates python3-pil python3-numpy
pip-wheels	pip	Pillow numpy
EOF
}

# Ein Objekt holen. Rueckgabe 0 = fertig (Marke gesetzt), 1 = Fehler (Marke
# gesetzt), 2 = uebersprungen (kein Grund, keine Marke).
vorab_holen() {
	_vh_name="$1"; _vh_art="$2"; shift 2
	_vh_d="$(vorab_verzeichnis)"

	case "$_vh_art" in
	apt)
		# --download-only holt die Pakete MIT Abhaengigkeiten in den
		# apt-Cache und installiert nichts. Der spaetere `apt-get install`
		# findet sie dort und braucht kein Netz mehr.
		#
		# Sperre: apt nimmt die dpkg-Sperre schon fuers Herunterladen. Laeuft
		# parallel ein anderer apt, wird hier gewartet (Lock::Timeout) --
		# nicht abgebrochen. Der Installer wartet seinerseits (Modul 20,
		# gleiche Option), damit keiner dem anderen in die Quere kommt.
		[ "$(id -u)" = 0 ] || { vorab_marke_fehler "$_vh_name" "nur als root"; return 1; }
		command -v apt-get >/dev/null 2>&1 || { vorab_marke_fehler "$_vh_name" "kein apt-get"; return 1; }
		_vh_rc=0
		apt-get install --download-only --yes \
			-o DPkg::Lock::Timeout="${CHIMERA_APT_LOCK_TIMEOUT:-300}" \
			"$@" >>"$_vh_d/$_vh_name.log" 2>&1 || _vh_rc=$?
		if [ "$_vh_rc" != 0 ]; then
			vorab_marke_fehler "$_vh_name" "apt-get rc=$_vh_rc (siehe ${CHIMERA_STATE:-/opt/chimera/state}/prefetch/$_vh_name.log)"
			return 1
		fi
		vorab_marke_done "$_vh_name"
		return 0 ;;
	pip)
		_vh_dir="$_vh_d/wheels"
		mkdir -p "$_vh_dir" || { vorab_marke_fehler "$_vh_name" "Verzeichnis nicht anlegbar"; return 1; }
		command -v python3 >/dev/null 2>&1 || {
			vorab_marke_fehler "$_vh_name" "kein python3"; return 1; }
		# --no-deps gibt es hier nicht: die Wheels sollen samt Abhaengigkeiten
		# im Verzeichnis liegen, damit Modul 50 sie ohne Netz findet.
		#
		# Kein pip? Debian ohne python3-pip ist kein Fehler des Vorab-Ladens --
		# Modul 50 richtet die Umgebung selbst ein und laedt dann normal.
		# `|| _vh_rc=$?` statt `set +e`: Das set -e des Aufrufers wird nicht
		# verstellt, und ein Fehlschlag ist trotzdem messbar.
		_vh_rc=0
		python3 -m pip download --no-cache-dir --dest "$_vh_dir" "$@" \
			>>"$_vh_d/$_vh_name.log" 2>&1 || _vh_rc=$?
		if [ "$_vh_rc" != 0 ]; then
			vorab_marke_fehler "$_vh_name" "pip download rc=$_vh_rc (siehe $CHIMERA_STATE/prefetch/$_vh_name.log)"
			return 1
		fi
		vorab_marke_done "$_vh_name"
		return 0 ;;
	esac
	return 2
}

# Alle Objekte der Liste abarbeiten. Bricht beim ersten Fehler NICHT ab:
# Jedes Objekt steht fuer sich, ein gescheitertes darf die uebrigen nicht
# aufhalten (und der Lauf merkt es ohnehin erst beim Verbraucher).
vorab_alle() {
	vorab_anlegen || {
		warn "Vorab-Laden: $(vorab_verzeichnis) nicht beschreibbar -- wird uebersprungen."
		return 1
	}
	vorab_liste | while IFS='	' read -r _va_name _va_art _va_rest; do
		[ -n "$_va_name" ] || continue
		if vorab_fertig "$_va_name"; then
			info "Vorab-Laden: $_va_name ist schon da."
			continue
		fi
		info "Vorab-Laden: $_va_name ($_va_art) ..."
		# shellcheck disable=SC2086
		if vorab_holen "$_va_name" "$_va_art" $_va_rest; then
			info "Vorab-Laden: $_va_name fertig."
		else
			warn "Vorab-Laden: $_va_name nicht geholt -- der Schritt laedt selbst."
		fi
	done
	return 0
}
