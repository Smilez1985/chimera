#!/bin/sh
# Chimera installer -- Installerhelfer und Klammer um den Lauf
# (DESIGN, Regel "Installerhelfer").
#
# 1. `helfer_starten`: Die Arbeit in einer eigenen, abgekoppelten Unit ausfuehren
#    (transient, Name chimera-installhelper). Faellt die SSH-Verbindung, laeuft
#    der Lauf weiter. Gemessen am Pi (2.11.): ein ueber SSH gestarteter Lauf
#    laeuft in /system.slice/ssh.service und stirbt mit der Sitzung.
# 2. `klammer_an` / `klammer_aus`: Vor dem Ersetzen von Dateien die Dienste
#    anhalten, danach in der richtigen Reihenfolge wieder starten. Gemessen:
#    Sockets muessen VOR den Diensten starten, sonst verweigert systemd
#    ("Socket service already active, refusing").
#
# Die Umgebung des Aufrufs geht ueber eine Datei (0600) an den Helfer, nicht
# ueber die Befehlszeile: Ein Passwort auf der Kommandozeile steht sonst in
# `systemctl show` und in der Prozessliste (Regel "Keine Secrets im Repo").
#
# Geprueft in tests/test-helfer.sh ohne systemd (systemctl und systemd-run
# stehen dort als Funktionen bereit).

: "${CHIMERA_HELFER_UNIT:=chimera-installhelper}"

# Was die Klammer anhaelt und wieder startet.
: "${KLAMMER_TIMER:=chimera-logabgleich.timer chimera-mojo.timer}"
: "${KLAMMER_SOCKETS:=chimera-tor.socket chimera-sitzung.socket}"
# Reihenfolge zaehlt: erst der Dienst des Agenten, dann das Gateway.
: "${KLAMMER_DIENSTE:=chimera.service}"
# Das Gateway ist socket-aktiviert: Es nimmt den Socket von systemd
# (LISTEN_FDS) und beendet sich mit Code 2, wenn es keinen bekommt. Ein
# direkter Start ist deshalb falsch; gestartet wird der Socket, geweckt wird
# das Gateway beim ersten Aufruf. Am Pi gemessen: nach einem direkten Start
# stand chimera-tor.service auf inactive.
: "${KLAMMER_SOCKETDIENSTE:=chimera-tor.service}"

# Umgebungsvariablen, die der Lauf von aussen bekommt und die der Helfer erben
# soll. Feste Liste: Was hier nicht steht, hat im Helfer seine Vorgabe.
HELFER_UMGEBUNG="CHIMERA_ROOT CHIMERA_LOG_DIR CHIMERA_LOG_KEEP CHIMERA_DOWNGRADE
CHIMERA_QUELLE_URL CHIMERA_RUST_URL CHIMERA_RUST_LOKAL CHIMERA_MIT
CHIMERA_WEB_PASSWORT CHIMERA_SWAP_RESERVE_MIB CHIMERA_ZRAM_PROZENT
CHIMERA_ZRAM_ALGO CHIMERA_ZRAM_PRIO CHIMERA_TOR_SPEICHER CHIMERA_TOR_WARTEN
CHIMERA_DIENST_WARTEN CHIMERA_NUTZER CHIMERA_DIENSTNUTZER CHIMERA_TOR_NUTZER
CHIMERA_UHR_MIN CHIMERA_ANZEIGE CHIMERA_LOG_KARTE CHIMERA_STATE_DIR"

# Laeuft dieser Prozess schon als Helfer?
helfer_laeuft() { [ "${CHIMERA_HELFER:-0}" = 1 ]; }

helfer_aktiv() {
	have_cmd systemctl || return 1
	systemctl is-active --quiet "$CHIMERA_HELFER_UNIT" 2>/dev/null
}

helfer_env_datei() { printf '/run/chimera-installhelfer.env'; }

# Die Umgebung des Aufrufs fuer den Helfer festhalten. rc 0 ok.
helfer_env_schreiben() {
	_hes_d="$(helfer_env_datei)"
	( umask 077; : >"$_hes_d" ) 2>/dev/null || {
		# Kein /run (etwa im Test): neben das Protokoll.
		_hes_d="${TMPDIR:-/tmp}/chimera-installhelfer.$$.env"
		( umask 077; : >"$_hes_d" ) || { err "Umgebungsdatei nicht schreibbar."; return 2; }
	}
	[ "$(stat -c %a "$_hes_d" 2>/dev/null)" = 600 ] || chmod 600 "$_hes_d" 2>/dev/null
	for _hes_v in $HELFER_UMGEBUNG; do
		eval "_hes_wert=\${$_hes_v:-}"
		[ -n "$_hes_wert" ] || continue
		# Eine Zeile je Variable, Wert unveraendert (auch mit Leerzeichen).
		printf '%s=%s\n' "$_hes_v" "$_hes_wert" >>"$_hes_d" || {
			err "Umgebungsdatei nicht beschreibbar: $_hes_d"; return 2; }
	done
	# Zurueckgelesen wird im Helfer mit `while IFS== read`.
	printf '%s\n' "$_hes_d"
}

# Der Helfer liest seine Umgebung und raeumt sie weg.
helfer_env_lesen() {
	_hel_d="${CHIMERA_HELFER_ENV:-}"
	[ -n "$_hel_d" ] && [ -f "$_hel_d" ] || return 0
	while IFS='=' read -r _hel_k _hel_w; do
		[ -n "$_hel_k" ] || continue
		case "$_hel_k" in CHIMERA_*) : ;; *) continue ;; esac
		eval "export $_hel_k=\"\$_hel_w\""
	done <"$_hel_d"
	rm -f "$_hel_d"
}

# Die Arbeit abgekoppelt starten und ihr Ergebnis abwarten.
# $1 das Programm (chimera-install), Rest: seine Argumente.
# Rueckgabe: Exitcode des Laufs; 2 wenn er nicht startbar ist.
helfer_starten() {
	_hs_prog="$1"; shift
	have_cmd systemd-run || { err "systemd-run fehlt -- der Lauf kann nicht abgekoppelt werden."; return 2; }
	if helfer_aktiv; then
		# Wieder aufrufbar: Ein zweiter Aufruf startet nichts Neues, er haengt
		# sich an den laufenden Lauf (etwa nach einem Abbruch der Verbindung).
		info "Ein Lauf ist bereits im Gange ($CHIMERA_HELFER_UNIT) -- haenge mich an, kein zweiter Start."
		info "  Fortschritt: journalctl -u $CHIMERA_HELFER_UNIT -f"
		helfer_abwarten
		return $?
	fi
	_hs_env="$(helfer_env_schreiben)" || return 2
	if is_dry_run; then
		info "[wuerde starten] systemd-run --unit=$CHIMERA_HELFER_UNIT ... /bin/sh $_hs_prog --helfer $*"
		rm -f "$_hs_env"
		return 0
	fi
	if ! systemd-run --unit="$CHIMERA_HELFER_UNIT" --collect --quiet --service-type=oneshot \
		--description="Chimera -- Installer (abgekoppelt)" \
		--setenv="CHIMERA_HELFER=1" --setenv="CHIMERA_HELFER_ENV=$_hs_env" \
		/bin/sh "$_hs_prog" --helfer "$@"; then
		err "Der Helfer startete nicht (systemd-run)."
		rm -f "$_hs_env"
		return 2
	fi
	info "Lauf laeuft abgekoppelt als $CHIMERA_HELFER_UNIT -- eine getrennte SSH-Sitzung beendet ihn nicht."
	helfer_abwarten
}

# Warten, bis die Unit fertig ist, und ihren Exitcode zurueckgeben.
helfer_abwarten() {
	while systemctl is-active --quiet "$CHIMERA_HELFER_UNIT" 2>/dev/null; do
		sleep 2
	done
	_hw_rc="$(systemctl show "$CHIMERA_HELFER_UNIT" -p ExecMainStatus --value 2>/dev/null)"
	case "$_hw_rc" in
		'' | *[!0-9]*) warn "Exitcode des Helfers nicht lesbar -- Ergebnis im Protokoll."; return 0 ;;
	esac
	info "Helfer beendet mit Exitcode $_hw_rc."
	return "$_hw_rc"
}

# --- Klammer um den Lauf ---------------------------------------------------

# Wo der Merker liegt, welcher Dienst vorher lief. Genommen wird der erste
# Ordner, in den wirklich geschrieben werden kann; sonst TMPDIR.
_klammer_datei() {
	for _kd_d in "${CHIMERA_RUNLOG:-}" "${CHIMERA_LOG_DIR:-}" "${TMPDIR:-/tmp}"; do
		[ -n "$_kd_d" ] && [ -d "$_kd_d" ] && [ -w "$_kd_d" ] || continue
		printf '%s/klammer-lief' "$_kd_d"
		return 0
	done
	printf '/tmp/klammer-lief'
}

# Aendert dieser Lauf ueberhaupt etwas? Nur dann werden Dienste angehalten
# (Vorgabe smilez, 2.11.: "wenn es schon da ist und sich nichts aendert, lass
# die Finger weg"). Geprueft wird, was einen Neustart erzwingt:
#   * anderer Stand der Quelle (Code, Units, Installer selbst)
#   * fehlende oder zu alte Python-Pakete
# Alles andere schreibt seine Dateien ohnehin nur, wenn der Inhalt abweicht.
# rc 0 = ja, etwas aendert sich. rc 1 = nein, nichts anzufassen.
klammer_noetig() {
	# 1. Quellstand: der Kandidat gegen das, was in source/ liegt.
	_kn_neu="$(source_hash "$CHIMERA_STARTBAUM" 2>/dev/null || true)"
	_kn_alt="$(source_hash "$CHIMERA_SOURCE" 2>/dev/null || true)"
	if [ -n "$_kn_neu" ] && [ "$_kn_neu" != "$_kn_alt" ]; then
		info "neuer Quellstand ($_kn_alt -> $_kn_neu): Dienste werden angehalten"
		return 0
	fi
	# 2. Python-Pakete: fehlt eines oder ist eines zu alt, aendert sich etwas.
	if [ -x "$CHIMERA_VENV/bin/python" ] && [ -f "$CHIMERA_STARTBAUM/requirements.txt" ]; then
		# shellcheck disable=SC2046
		if ! pydep_fehlend "$CHIMERA_VENV/bin/python" $(pydep_liste "$CHIMERA_STARTBAUM/requirements.txt") >/dev/null 2>&1; then
			info "Python-Abhaengigkeiten nicht erfuellt: Dienste werden angehalten"
			return 0
		fi
	fi
	return 1
}

klammer_an() {
	if is_dry_run; then
		info "[wuerde anhalten] $KLAMMER_TIMER $KLAMMER_SOCKETS $KLAMMER_DIENSTE"
		return 0
	fi
	: >"$(_klammer_datei)" 2>/dev/null || {
		err "Klammer-Datei nicht schreibbar: $(_klammer_datei)"; return 2; }
	_ka_befund=0
	# Zuerst weg, was nach dem Lauf neu startet. Das Gateway steht in
	# KLAMMER_SOCKETDIENSTE, es wird angehalten wie ein Dienst.
	for _ka_u in $KLAMMER_TIMER $KLAMMER_SOCKETS $KLAMMER_DIENSTE $KLAMMER_SOCKETDIENSTE; do
		systemctl is-active --quiet "$_ka_u" 2>/dev/null || continue
		echo "$_ka_u" >>"$(_klammer_datei)"
		systemctl stop "$_ka_u" >/dev/null 2>&1 || {
			err "systemctl stop $_ka_u schlug fehl -- es wird nichts geschrieben."; _ka_befund=1; }
		if systemctl is-active --quiet "$_ka_u" 2>/dev/null; then
			err "laeuft noch: $_ka_u -- es wird nichts geschrieben."
			_ka_befund=1
		fi
	done
	if [ "$_ka_befund" != 0 ]; then
		# Lieber gar nicht installieren als Dateien unter einem laufenden Dienst
		# ersetzen.
		klammer_aus || true
		return 2
	fi
	info "Dienste angehalten, laufen nach dem Lauf wieder: $(tr '\n' ' ' <"$(_klammer_datei)")"
	return 0
}

klammer_aus() {
	[ -f "$(_klammer_datei)" ] || return 0
	if is_dry_run; then
		info "[wuerde starten] was vorher lief"
		rm -f "$(_klammer_datei)"
		return 0
	fi
	_ke_lief=" $(tr '\n' ' ' <"$(_klammer_datei)") "
	rm -f "$(_klammer_datei)"
	_ke_befund=0
	# Sockets zuerst (sie halten den Anschluss), dann der Agent, dann das
	# Gateway. Andersherum verweigert systemd den Socket, weil sein Dienst schon
	# laeuft (am 31.10. so passiert).
	for _ke_u in $KLAMMER_SOCKETS $KLAMMER_DIENSTE $KLAMMER_TIMER; do
		case "$_ke_lief" in *" $_ke_u "*) ;; *) continue ;; esac
		if systemctl is-active --quiet "$_ke_u" 2>/dev/null; then
			info "laeuft schon: $_ke_u"
			continue
		fi
		systemctl reset-failed "$_ke_u" >/dev/null 2>&1 || true
		systemctl start "$_ke_u" >/dev/null 2>&1 || {
			err "systemctl start $_ke_u schlug fehl."; _ke_befund=1; }
	done

	# Das Gateway laeuft nicht von selbst: Es wird beim ersten Aufruf durch den
	# Socket gestartet. Ein direkter Start scheitert (es braucht LISTEN_FDS).
	for _ke_u in $KLAMMER_SOCKETDIENSTE; do
		case "$_ke_lief" in *" $_ke_u "*) ;; *) continue ;; esac
		_ke_prog="$CHIMERA_OPT/bin/chimera-tor"
		if [ -x "$_ke_prog" ]; then
			if "$_ke_prog" --ping "$CHIMERA_TOR_SOCKET" >/dev/null 2>&1; then
				info "Gateway ueber den Socket geweckt: $_ke_u"
			else
				err "Gateway antwortet nach dem Lauf nicht ($_ke_u, Socket $CHIMERA_TOR_SOCKET)."
				_ke_befund=1
			fi
		else
			warn "Gateway-Programm fehlt ($_ke_prog) -- Wecken uebersprungen."
		fi
	done
	# Nachweis: Ein Dienst, der gleich wieder stirbt, ist kein Erfolg.
	for _ke_u in $KLAMMER_SOCKETS $KLAMMER_DIENSTE; do
		case "$_ke_lief" in *" $_ke_u "*) ;; *) continue ;; esac
		systemctl is-active --quiet "$_ke_u" 2>/dev/null || {
			err "laeuft nach dem Lauf nicht: $_ke_u"; _ke_befund=1; }
	done
	# Beim Gateway ist der Socket der Nachweis; der Dienst startet erst mit dem
	# ersten Aufruf und darf danach auch wieder enden (Socket-Aktivierung).
	[ "$_ke_befund" = 0 ] && info "Dienste wieder gestartet."
	return "$_ke_befund"
}
