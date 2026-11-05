#!/bin/sh
# Vorab-Laden im Hintergrund (DESIGN, Regel "Warte-Schleife und Vorab-Laden").
#
# Der Installer kennt seine Downloads, BEVOR er sie braucht. Dieser Helfer
# holt sie in Modulreihenfolge, waehrend der Lauf arbeitet -- ein Objekt
# nach dem anderen, nicht alle gleichzeitig (ein Zero 2 W hat eine Leitung).
#
# Je Objekt eine Marke unter $CHIMERA_STATE/prefetch/:
#   <name>.done    fertig -- erst geschrieben, wenn die Ware wirklich da ist
#   <name>.fehler  Grund, warum es nicht ging (bleibt stehen, wird beim
#                  naechsten Lauf erneut versucht)
#   *.teil         Schreibzwischenstand der Marke (.done.teil/.fehler.teil),
#                  damit nie eine halbe Marke gelesen wird. Kein
#                  Fortsetzungspunkt eines Downloads -- halbe Downloads
#                  landen in wheels.teil und werden verworfen.
#
# Grundsatz: Eine Marke beschleunigt nur, sie ist NIE Bedingung. Jeder
# Verbraucher prueft seine Ware selbst (Pruefsumme, Version). Ein toter oder
# haengender Vorab-Lader darf keinen Installationsschritt blockieren.
#
# Zu `apt`: Es bleibt draussen. apt hat schon einen Eigentuemer
# (`apt_install` in lib/network.sh, mit DPkg::Lock::Timeout) -- ein zweiter
# Weg waere genau die Doppelimplementierung, die dieses Projekt schon dreimal
# bezahlt hat. Und er kann nicht ueberlappen: `apt-get install` holt unter
# derselben Sperre, die Modul 20 braucht; wer zuerst kommt, haelt den anderen
# auf (am Pi gemessen, 5.11.: 25 s fuer null Pakete). apt laedt also dort, wo
# es ohnehin laeuft -- in Modul 20. Was hier bleibt, ist pip: 22 MB, 16 s,
# und die fallen wirklich aus Modul 50 heraus.
#
# Schalter: CHIMERA_PREFETCH_RAD=0 laesst das Vorab-Laden aus (Vorgabe 1).
# Gebraucht wird er zum Messen (vorher/nachher) und als Notaus, wenn ein
# Geraet am Vorab-Laden haengt.

: "${CHIMERA_PREFETCH_RAD:=1}"

# Ist das Vorab-Laden eingeschaltet? Einzige Stelle, an der der Schalter
# gelesen wird -- Aufrufer fragen hier, nicht selbst.
vorab_an() {
	[ "${CHIMERA_PREFETCH_RAD:-1}" != 0 ]
}

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

# Alte Fehlmarken in das Protokoll des Laufs holen.
#
# Warum das hierher gehoert: Der Vorab-Lader laeuft abgekoppelt und schreibt
# sein eigenes Protokoll; ein Fehlschlag von gestern steht sonst nur in
# state/prefetch und in keiner Zeile, die der Lauf kennt. Mojo liest den Lauf,
# nicht das Verzeichnis -- was nicht im Protokoll steht, findet es nicht.
# Beheben muss niemand etwas: der naechste Start versucht jedes Objekt ohne
# .done erneut (eine .fehler-Marke blockiert nicht). Die Meldung ist trotzdem
# wichtig, weil sie den Grund nennt, bevor er sich wiederholt.
vorab_fehler_berichten() {
	_vf_d="$(vorab_verzeichnis)"
	[ -d "$_vf_d" ] || return 0
	_vf_n=0
	for _vf_f in "$_vf_d"/*.fehler; do
		[ -f "$_vf_f" ] || continue
		_vf_n=$((_vf_n + 1))
		warn "Vorab-Laden: $(basename "$_vf_f" .fehler) scheiterte zuletzt -- $(sed -n 's/^grund=//p' "$_vf_f" 2>/dev/null | head -1)"
	done
	[ "$_vf_n" -eq 0 ] || \
		info "Vorab-Laden: $_vf_n Objekt(e) werden in diesem Lauf erneut versucht."
	return 0
}

# --- Die Objekte, in der Reihenfolge, in der die Module sie brauchen ------
#
# Je Zeile: Name <Tab> Art <Tab> Parameter
#   pip  <anforderungen>     -> Wheels nach <prefetch>/wheels (Modul 50)
#
# Die Liste ist bewusst kurz: Was wenige Sekunden kostet, wird nicht
# vorgeladen -- der Aufwand einer Marke waere groesser als der Gewinn
# (gemessen 4.11.: Whisplay-Klon 3 s, rust-Binary 1 s).
#
# Beim Nachdenken ueber ein neues Objekt zuerst fragen: Hat der Schritt, der
# es braucht, schon einen eigenen Weg (dann gehoert es dorthin), und kann der
# Abruf ueberhaupt nebenher laufen? Zwei Nein heisst: nicht vorladen.
vorab_liste() {
	cat <<'EOF'
pip-wheels	pip	Pillow numpy
EOF
}

# Ist fuer diese Anforderung schon ein Wheel da? (idempotent: installieren
# nur, was fehlt). Verglichen wird der Paketname aus der Anforderung
# (`numpy>=1.26` -> `numpy`, `python-dateutil` -> `python_dateutil`) mit dem
# Dateinamen im Vorab-Verzeichnis.
vorab_wheel_da() {
	_vwd="$1"
	_vwd="$(printf '%s' "$_vwd" | sed 's/[<>=!~[].*$//' | tr 'A-Z' 'a-z' | tr '-' '_')"
	[ -n "$_vwd" ] || return 1
	# Trennzeichen zwischen Name und Fassung ist im Wheel-Dateinamen '-'
	# (im Paketnamen selbst '_'): `pillow-13.0.0-...whl`, `python_dateutil-2.9-...`.
	ls "$(vorab_verzeichnis)/wheels" 2>/dev/null | tr 'A-Z' 'a-z' |
		grep -q "^${_vwd}[-_]"
}

# Ein Objekt holen. Rueckgabe 0 = fertig (Marke gesetzt), 1 = Fehler (Marke
# gesetzt), 2 = uebersprungen (keine Marke), 3 = nichts zu tun (alles da).
vorab_holen() {
	_vh_name="$1"; _vh_art="$2"; shift 2
	_vh_d="$(vorab_verzeichnis)"

	case "$_vh_art" in
	pip)
		_vh_dir="$_vh_d/wheels"
		# Direkt nach wheels/, KEIN Zwischenverzeichnis mehr. Grund (am Pi
		# gemessen, 5.11.2026): pip legt ein Wheel erst dann im Zielordner ab,
		# wenn es vollstaendig ist -- 40 Abtastungen waehrend eines 15-MB-
		# Downloads sahen nie eine halbe Datei, sie erschien einmal mit voller
		# Groesse. Ein Zwischenverzeichnis mit Umhaengen am ENDE kostete
		# dagegen genau den Vorteil: Modul 50 startet nach ~20 s, der Abruf
		# braucht ~20 s -- mit Zwischenverzeichnis war wheels/ zu diesem
		# Zeitpunkt noch leer und der Vorab-Lauf nutzlos (drei Messlaeufe,
		# Vorab-Laden brachte 0 s).
		# Was schon da ist, wird nicht erneut geholt (pip meldet "already
		# downloaded" und Erfolg) -- das bleibt idempotent und fortsetzbar.
		command -v python3 >/dev/null 2>&1 || {
			vorab_marke_fehler "$_vh_name" "kein python3"; return 1; }
		# Zuerst nachsehen, was wirklich fehlt -- nicht blind laden. Was schon
		# im Vorab-Verzeichnis liegt, wird nicht angefasst.
		_vh_fehl=""
		for _vh_a in "$@"; do
			vorab_wheel_da "$_vh_a" || _vh_fehl="$_vh_fehl $_vh_a"
		done
		if [ -z "$_vh_fehl" ]; then
			vorab_marke_done "$_vh_name"
			return 3
		fi
		mkdir -p "$_vh_dir" || {
			vorab_marke_fehler "$_vh_name" "Zielverzeichnis nicht anlegbar"; return 1; }
		# Fehlt pip im Systempython, wird es geholt -- nicht gemeldet und nicht
		# uebersprungen. pip ist eine Abhaengigkeit, die der Installer selbst
		# herstellt (`python3-pip`, Pflichtpaket in Modul 20); apt zu fragen ist
		# derselbe Weg wie dort, nicht ein zweiter: network_apt in
		# lib/network.sh haelt die Sperre (DPkg::Lock::Timeout), wartet aufs
		# Netz und installiert nur, was fehlt.
		if ! python3 -m pip --version >/dev/null 2>&1; then
			info "Vorab-Laden: kein pip im Systempython -- wird ueber apt geholt."
			if command -v network_apt >/dev/null 2>&1; then
				network_apt python3-pip || \
					warn "Vorab-Laden: apt konnte python3-pip nicht holen."
			fi
			if ! python3 -m pip --version >/dev/null 2>&1; then
				vorab_marke_fehler "$_vh_name" "kein pip im Systempython, auch nach apt (python3-pip)"
				return 1
			fi
		fi
		# DIESELBE Warte-Schleife wie in Modul 50 (pydep_ensure) und in
		# network_fetch: Fehlt das Netz, wird pausiert und weiter versucht --
		# ein Netzaussetzer ist kein Befund. Erst wenn das Netz steht und pip
		# trotzdem scheitert, gibt es eine .fehler-Marke.
		#
		# `|| _vh_rc=$?` statt `set +e`: Das set -e des Aufrufers bleibt
		# unangetastet, und ein Fehlschlag ist trotzdem messbar.
		_vh_versuche="${CHIMERA_PIP_VERSUCHE:-3}"
		_vh_n=0
		_vh_rc=1
		while [ "$_vh_n" -lt "$_vh_versuche" ]; do
			_vh_n=$((_vh_n + 1))
			if command -v netz_warten_erreichbar >/dev/null 2>&1; then
				netz_warten_erreichbar || {
					warn "Vorab-Laden: kein Netz -- $_vh_name bleibt offen, der Schritt laedt selbst."
					_vh_rc=1
					break
				}
			fi
			[ "$_vh_n" -gt 1 ] && \
				info "Vorab-Laden: $_vh_name, Versuch $_vh_n von $_vh_versuche"
			# Kein --no-deps: die Wheels sollen samt Abhaengigkeiten
			# im Verzeichnis liegen, damit Modul 50 sie ohne Netz findet.
			# Geladen wird nur, was fehlt ($_vh_fehl, Wortliste).
			_vh_rc=0
			# shellcheck disable=SC2086
			python3 -m pip download --no-cache-dir --dest "$_vh_dir" $_vh_fehl \
				>>"$_vh_d/$_vh_name.log" 2>&1 || _vh_rc=$?
			[ "$_vh_rc" = 0 ] && break
			warn "Vorab-Laden: $_vh_name unterbrochen (Exitcode $_vh_rc, Versuch $_vh_n von $_vh_versuche)."
			[ "$_vh_n" -lt "$_vh_versuche" ] && sleep 2
		done
		if [ "$_vh_rc" != 0 ]; then
			# Zwischenverzeichnis bleibt liegen: der naechste Lauf macht dort
			# weiter, wo dieser aufgehoert hat.
			vorab_marke_fehler "$_vh_name" "pip download rc=$_vh_rc nach $_vh_n Versuch(en) (siehe ${CHIMERA_STATE:-/opt/chimera/state}/prefetch/$_vh_name.log)"
			return 1
		fi
		vorab_marke_done "$_vh_name"
		return 0 ;;
	esac
	return 2
}

# Den Vorab-Lader abgekoppelt starten.
#
# $1 = Programm (installer/chimera-prefetch)
# Rueckgabe: 0 gestartet, 1 nicht startbar, 2 abgeschaltet (CHIMERA_PREFETCH_RAD=0).
#
# WARUM EINE EIGENE transient Unit und nicht `nohup ... &` (am Pi gemessen,
# 5.11.): Der Installer laeuft selbst als transiente Unit
# (`chimera-installhelper.service`, `--collect`). Ein einfaches Kind haengt in
# DESSEN Cgroup -- und systemd raeumt eine beendete Unit mit
# `KillMode=control-group` komplett ab. Der Vorab-Lader wurde damit beim Ende
# des Laufs erschossen, mitten im Download, ohne .done und ohne .fehler
# (erster Lauf: Pillow halb geholt, wheels/ leer). Eine eigene Unit gehoert
# niemandem ausser sich selbst und laeuft zu Ende.
vorab_starten() {
	_vs_prog="$1"
	vorab_an || return 2
	_vs_log="${CHIMERA_LOG_DIR:-/var/log/chimera}/prefetch.log"
	# setsid als Rueckfall: ohne systemd (Sandbox, Test) wenigstens eine
	# eigene Sitzung, damit ein SIGHUP des Aufrufers nicht durchschlaegt.
	if command -v systemd-run >/dev/null 2>&1; then
		if systemd-run --unit=chimera-prefetch --collect --no-block \
			--service-type=oneshot \
			--description="Chimera -- Vorab-Laden (abgekoppelt)" \
			/bin/sh "$_vs_prog" >>"$_vs_log" 2>&1; then
			return 0
		fi
		# Der Name kann von einem frueheren Lauf belegt sein.
		systemctl reset-failed chimera-prefetch >/dev/null 2>&1 || true
		systemd-run --unit=chimera-prefetch --collect --no-block \
			--service-type=oneshot \
			--description="Chimera -- Vorab-Laden (abgekoppelt)" \
			/bin/sh "$_vs_prog" >>"$_vs_log" 2>&1 && return 0
		return 1
	fi
	if command -v setsid >/dev/null 2>&1; then
		setsid nohup sh "$_vs_prog" >>"$_vs_log" 2>&1 </dev/null &
	else
		nohup sh "$_vs_prog" >>"$_vs_log" 2>&1 </dev/null &
	fi
	return 0
}
# Alle Objekte der Liste abarbeiten. Bricht beim ersten Fehler NICHT ab:
# Jedes Objekt steht fuer sich, ein gescheitertes darf die uebrigen nicht
# aufhalten (und der Lauf merkt es ohnehin erst beim Verbraucher).
vorab_alle() {
	vorab_an || { info "Vorab-Laden ist abgeschaltet (CHIMERA_PREFETCH_RAD=0)."; return 2; }
	vorab_anlegen || {
		warn "Vorab-Laden: $(vorab_verzeichnis) nicht beschreibbar -- wird uebersprungen."
		return 1
	}
	vorab_liste | while IFS='	' read -r _va_name _va_art _va_rest; do
		[ -n "$_va_name" ] || continue
		# Kein Sprung auf die .done-Marke: Was wirklich gebraucht wird,
		# entscheidet der Bestand (idempotent -- installieren, nur was fehlt).
		# Die Marke ist der Beleg, dass der Abruf durchlief, nicht das Tor.
		info "Vorab-Laden: $_va_name ($_va_art) ..."
		_va_rc=0
		# shellcheck disable=SC2086
		vorab_holen "$_va_name" "$_va_art" $_va_rest || _va_rc=$?
		case "$_va_rc" in
			0) info "Vorab-Laden: $_va_name fertig." ;;
			3) info "Vorab-Laden: $_va_name ist vollstaendig da -- nichts zu holen." ;;
			2) info "Vorab-Laden: $_va_name nicht vorgesehen (uebersprungen)." ;;
			*) warn "Vorab-Laden: $_va_name nicht geholt -- der Schritt laedt selbst." ;;
		esac
	done
	return 0
}
