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
# Der Pfad des Gateway-Sockets steht sonst nur in lib/gateway.sh (Schritt 99).
# Die Klammer braucht ihn auch nach einem Neustart, wenn dieser Schritt nicht
# geladen ist -- sonst bricht sie unter `set -u` ab (am Pi 2.11.:
# "CHIMERA_TOR_SOCKET: parameter not set", Exitcode 2).
: "${CHIMERA_TOR_SOCKET:=/run/chimera/tor.sock}"

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

# --- Laufzettel ------------------------------------------------------------
#
# Warum nicht ueber systemd: Am Pi gemessen ist die transiente Unit nach dem
# Start nicht abfragbar ("could not be found", /run/systemd/transient/ leer),
# obwohl sie laeuft. Ein Laufzettel auf der Platte ist davon unabhaengig.

# Der Laufzettel liegt NICHT unter /run/chimera: Das ist RuntimeDirectory der
# Dienst-Unit, systemd loescht es beim Anhalten -- und die Klammer haelt den
# Dienst an. Am Pi gemessen: der Lauf war fertig, der Zettel verschwunden.
: "${CHIMERA_HELFER_STATUS:=/run/chimera-installhelper.status}"

helfer_zettel() {
	_hz_d="$(dirname "$CHIMERA_HELFER_STATUS")"
	if [ -d "$_hz_d" ] && [ -w "$_hz_d" ]; then
		printf '%s\n' "$CHIMERA_HELFER_STATUS"
		return 0
	fi
	# Kein /run (etwa im Test oder mit CHIMERA_ROOT): neben das Protokoll.
	printf '%s/installhelfer.status\n' "${TMPDIR:-/tmp}"
}

# $1 zustand (laufend|fertig), $2 pid, $3 rc (nur bei fertig), $4 startzeit
helfer_zettel_schreiben() {
	_zf="$(helfer_zettel)"
	printf 'zustand=%s\npid=%s\nrc=%s\nstart=%s\nende=%s\n' \
		"$1" "${2:-}" "${3:-}" "${4:-}" "$(date +%s)" >"$_zf" 2>/dev/null || true
}

helfer_zettel_wert() {
	_zf="$(helfer_zettel)"
	[ -f "$_zf" ] || return 1
	sed -n "s/^$1=//p" "$_zf" | head -n1
}

# Laeuft laut Laufzettel noch ein Lauf? rc 0 = ja.
helfer_zettel_laeuft() {
	[ "$(helfer_zettel_wert zustand)" = laufend ] || return 1
	_zp="$(helfer_zettel_wert pid)"
	[ -n "$_zp" ] || return 1
	kill -0 "$_zp" 2>/dev/null
}

# Die Arbeit abgekoppelt starten und ihr Ergebnis abwarten.
# $1 das Programm (chimera-install), Rest: seine Argumente.
# Rueckgabe: Exitcode des Laufs; 2 wenn er nicht startbar ist.
helfer_starten() {
	_hs_prog="$1"; shift
	have_cmd systemd-run || { err "systemd-run fehlt -- der Lauf kann nicht abgekoppelt werden."; return 2; }
	if helfer_zettel_laeuft; then
		# Wieder aufrufbar: nach einem Abbruch der Verbindung findet der neue
		# Aufruf den laufenden Lauf und haengt sich an ihn.
		info "Ein Lauf ist bereits im Gange (PID $(helfer_zettel_wert pid)) -- haenge mich an, kein zweiter Start."
		helfer_abwarten
		return $?
	fi
	_hs_env="$(helfer_env_schreiben)" || return 2
	if is_dry_run; then
		info "[wuerde starten] systemd-run --unit=$CHIMERA_HELFER_UNIT ... /bin/sh $_hs_prog --helfer $*"
		rm -f "$_hs_env"
		return 0
	fi
	helfer_zettel_schreiben laufend "" "" "$(date +%s)"
	# Der Name kann von einem frueheren Lauf belegt sein ("Unit ... was already
	# loaded") -- etwa nach einem Abbruch. Einmal freigeben und erneut versuchen.
	_hs_fehl=""
	if ! _hs_fehl="$(systemd-run --unit="$CHIMERA_HELFER_UNIT" --collect --no-block --service-type=oneshot \
		--description="Chimera -- Installer (abgekoppelt)" \
		--setenv="CHIMERA_HELFER=1" --setenv="CHIMERA_HELFER_ENV=$_hs_env" \
		/bin/sh "$_hs_prog" --helfer "$@" 2>&1)"; then
		systemctl reset-failed "$CHIMERA_HELFER_UNIT" >/dev/null 2>&1 || true
		_hs_fehl=""
		if ! _hs_fehl="$(systemd-run --unit="$CHIMERA_HELFER_UNIT" --collect --no-block --service-type=oneshot \
			--description="Chimera -- Installer (abgekoppelt)" \
			--setenv="CHIMERA_HELFER=1" --setenv="CHIMERA_HELFER_ENV=$_hs_env" \
			/bin/sh "$_hs_prog" --helfer "$@" 2>&1)"; then
			helfer_zettel_schreiben fehler "" 2 "$(date +%s)"
			err "Der Helfer startete nicht (systemd-run): ${_hs_fehl:-ohne Meldung}"
			rm -f "$_hs_env"
			return 2
		fi
	fi
	# --no-block: ohne das wartet systemd-run, bis der oneshot fertig ist, und
	# meldet dessen Exitcode als eigenen Fehlschlag. Ein Lauf mit Befund (rc 1)
	# sah dadurch wie "Helfer startete nicht" aus, und abgekoppelt war er nie
	# (am Pi 2.11. gemessen: 20 s Blockade, dann "Job ... failed").
	# Ohne --quiet: systemd-run meldet bei einem Fehlschlag nur dann etwas
	# ("Job for ... failed"), sonst kaeme die Ursache leer an -- am Pi 2.11. so
	# gesehen: "startete nicht: ohne Meldung".
	info "Lauf laeuft abgekoppelt als $CHIMERA_HELFER_UNIT -- eine getrennte SSH-Sitzung beendet ihn nicht."
	helfer_abwarten
}

# Warten, bis die Unit fertig ist, und ihren Exitcode zurueckgeben.
helfer_abwarten() {
	# Warten, bis der Laufzettel "fertig" sagt oder der Prozess verschwunden ist.
	# Der Aufrufer hat den Zettel als "laufend" ohne PID hinterlegt; die PID
	# schreibt der Helfer selbst, kurz nachdem systemd-run mit --no-block
	# zurueckkehrt. Wer sofort liest, haelt den Lauf fuer abgestuerzt (am Pi
	# 2.11. gesehen). Deshalb: bis zu 15 s auf die erste Meldung warten.
	_hw_warte=0
	while :; do
		if helfer_zettel_laeuft; then
			_hw_warte=0
			sleep 2
			continue
		fi
		if [ "$(helfer_zettel_wert zustand)" = laufend ] && \
			[ -z "$(helfer_zettel_wert pid)" ] && [ "$_hw_warte" -lt 15 ]; then
			_hw_warte=$((_hw_warte+1))
			sleep 1
			continue
		fi
		break
	done
	case "$(helfer_zettel_wert zustand)" in
		fertig)
			_hw_rc="$(helfer_zettel_wert rc)"
			case "$_hw_rc" in
				''|*[!0-9]*) warn "Exitcode des Helfers nicht lesbar -- Ergebnis im Protokoll."; return 0 ;;
			esac
			info "Helfer beendet mit Exitcode $_hw_rc."
			return "$_hw_rc" ;;
		laufend)
			# Prozess weg, aber kein "fertig": abgestuerzt.
			err "Der Helfer endete ohne Ergebnis (Hartabbruch?) -- Protokoll pruefen."
			return 2 ;;
		*)
			warn "Kein Laufzettel -- Ergebnis im Protokoll."
			return 0 ;;
	esac
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
	# Die Klammer prueft jeden Schritt selbst und meldet ehrlich. Ein einzelner
	# fehlschlagender Befehl darf sie nicht mitten im Anhalten abbrechen --
	# am Pi 2.11. endete der Start so mit Exitcode 2, ohne dass der Merker
	# geschrieben oder der Dienst gestartet wurde.
	_ka_alt_e=0
	case $- in *e*) _ka_alt_e=1; set +e ;; esac
	if is_dry_run; then
		info "[wuerde anhalten] $KLAMMER_TIMER $KLAMMER_SOCKETS $KLAMMER_DIENSTE"
		return 0
	fi
	: >"$(_klammer_datei)" 2>/dev/null || {
		err "Klammer-Datei nicht schreibbar: $(_klammer_datei)"; return 2; }

	# 1. Zustand VOR dem Anhalten aufnehmen. Erst messen, dann anhalten.
	# Mit Requires=chimera-sitzung.socket nimmt ein Socket seinen Dienst beim
	# Stoppen mit. Wird zuerst gestoppt und dann gemessen, fehlt der Dienst in
	# der Liste und startet nach dem Lauf nie wieder -- am 2.11. am Pi so
	# passiert: "Dienste wieder gestartet" gemeldet, chimera blieb aus.
	info "Zustand vor dem Lauf:"
	for _ka_u in $KLAMMER_TIMER $KLAMMER_DIENSTE $KLAMMER_SOCKETDIENSTE $KLAMMER_SOCKETS; do
		_ka_aktiv="$(systemctl is-active "$_ka_u" 2>/dev/null || true)"
		_ka_ein="$(systemctl is-enabled "$_ka_u" 2>/dev/null || true)"
		info "  $_ka_u: aktiv=${_ka_aktiv:-unbekannt} eingeschaltet=${_ka_ein:-unbekannt}"
		if [ "$_ka_aktiv" = active ]; then
			printf '%s\n' "$_ka_u" >>"$(_klammer_datei)"
		fi
	done
	_ka_liste=" $(tr '\n' ' ' <"$(_klammer_datei)") "
	if [ -z "$(echo "$_ka_liste" | tr -d ' ')" ]; then
		info "Es lief nichts -- der Lauf fasst keine Dienste an."
		return 0
	fi

	# 2. Anhalten: Timer, Dienste, dann Sockets. Ein Socket nimmt ueber
	# Requires seinen Dienst mit; andersherum bliebe ein Dienst ohne Socket
	# zurueck, und genau das ist der Zustand, den es nicht geben darf.
	_ka_befund=0
	info "Anhalten:"
	for _ka_u in $KLAMMER_TIMER $KLAMMER_DIENSTE $KLAMMER_SOCKETDIENSTE $KLAMMER_SOCKETS; do
		case "$_ka_liste" in *" $_ka_u "*) ;; *) continue ;; esac
		_ka_rc=0
		systemctl stop "$_ka_u" >/dev/null 2>&1 || _ka_rc=$?
		if systemctl is-active --quiet "$_ka_u" 2>/dev/null; then
			err "  $_ka_u laeuft nach dem Anhalten weiter (rc=$_ka_rc)."
			_ka_befund=1
		else
			info "  $_ka_u angehalten (rc=$_ka_rc)"
		fi
	done
	if [ "$_ka_befund" != 0 ]; then
		# Lieber gar nicht installieren als Dateien unter einem laufenden Dienst
		# ersetzen.
		klammer_aus || true
		return 2
	fi
	info "Dienste angehalten, laufen nach dem Lauf wieder: $(tr '\n' ' ' <"$(_klammer_datei)")"
	[ "$_ka_alt_e" = 1 ] && set -e
	return 0
}

klammer_aus() {
	# Wie in klammer_an: jeder Schritt wird geprueft und gemeldet; ein einzelner
	# Fehlschlag bricht den Start nicht ab.
	_ke_alt_e=0
	case $- in *e*) _ke_alt_e=1; set +e ;; esac
	[ -f "$(_klammer_datei)" ] || { [ "$_ke_alt_e" = 1 ] && set -e; return 0; }
	if is_dry_run; then
		info "[wuerde starten] was vorher lief"
		rm -f "$(_klammer_datei)"
		return 0
	fi
	_ke_lief=" $(tr '\n' ' ' <"$(_klammer_datei)") "
	rm -f "$(_klammer_datei)"
	_ke_befund=0
	info "Start nach dem Lauf (vorher lief:$_ke_lief):"

	# Reihenfolge: Sockets zuerst, dann die Dienste, dann die Timer. Andersherum
	# verweigert systemd den Socket, weil sein Dienst schon laeuft ("Socket
	# service already active, refusing"; am 31.10. und 2.11. so passiert).
	for _ke_u in $KLAMMER_SOCKETS $KLAMMER_DIENSTE $KLAMMER_TIMER; do
		case "$_ke_lief" in *" $_ke_u "*) ;; *) continue ;; esac
		if systemctl is-active --quiet "$_ke_u" 2>/dev/null; then
			info "  $_ke_u: laeuft schon"
			continue
		fi
		systemctl reset-failed "$_ke_u" >/dev/null 2>&1 || true
		_ke_rc=0
		systemctl start "$_ke_u" >/dev/null 2>&1 || _ke_rc=$?
		_ke_st="$(systemctl is-active "$_ke_u" 2>/dev/null || true)"
		if [ "$_ke_st" = active ]; then
			info "  $_ke_u: gestartet (rc=$_ke_rc)"
		else
			err "  $_ke_u: Start fehlgeschlagen (rc=$_ke_rc, Zustand ${_ke_st:-unbekannt})"
			_ke_befund=1
		fi
	done

	# Das Gateway laeuft nicht von selbst: Es wird beim ersten Aufruf durch den
	# Socket gestartet. Ein direkter Start scheitert (es braucht LISTEN_FDS).
	for _ke_u in $KLAMMER_SOCKETDIENSTE; do
		case "$_ke_lief" in *" $_ke_u "*) ;; *) continue ;; esac
		_ke_prog="$CHIMERA_OPT/bin/chimera-tor"
		if [ -x "$_ke_prog" ]; then
			if "$_ke_prog" --ping "$CHIMERA_TOR_SOCKET" >/dev/null 2>&1; then
				info "  $_ke_u: ueber den Socket geweckt"
			else
				err "  $_ke_u: antwortet nach dem Lauf nicht (Socket $CHIMERA_TOR_SOCKET)."
				_ke_befund=1
			fi
		else
			warn "Gateway-Programm fehlt ($_ke_prog) -- Wecken uebersprungen."
		fi
	done

	# Sicherheitsnetz: Der Sitzungs-Socket muss lauschen, sobald der Dienst
	# laeuft -- unabhaengig davon, wie er vor dem Lauf stand. Nur, wenn er auch
	# eingeschaltet ist: Ein bewusst abgeschalteter bleibt aus.
	for _kn_s in $KLAMMER_SOCKETS; do
		systemctl is-active --quiet "$_kn_s" 2>/dev/null && continue
		[ "$(systemctl is-enabled "$_kn_s" 2>/dev/null)" = enabled ] || {
			info "  $_kn_s: aus und nicht eingeschaltet -- bleibt so."
			continue; }
		if systemctl is-active --quiet "$CHIMERA_DIENST" 2>/dev/null; then
			warn "$_kn_s laesst sich nicht starten, solange $CHIMERA_DIENST laeuft -- Dienst wird dafuer angehalten."
			systemctl stop "$CHIMERA_DIENST" >/dev/null 2>&1 || true
		fi
		if systemctl start "$_kn_s" >/dev/null 2>&1; then
			info "  $_kn_s: nachgezogen"
		else
			err "  $_kn_s: nicht startbar."
			_ke_befund=1
		fi
		systemctl is-active --quiet "$CHIMERA_DIENST" 2>/dev/null || \
			systemctl start "$CHIMERA_DIENST" >/dev/null 2>&1 || {
				err "  Dienst nach dem Socket-Start nicht startbar."; _ke_befund=1; }
	done

	# Nachweis als Tabelle: Ein Dienst, der gleich wieder stirbt, ist kein Erfolg.
	info "Zustand nach dem Lauf:"
	for _ke_u in $KLAMMER_TIMER $KLAMMER_SOCKETS $KLAMMER_DIENSTE; do
		_ke_st="$(systemctl is-active "$_ke_u" 2>/dev/null || true)"
		info "  $_ke_u: ${_ke_st:-unbekannt}"
		case "$_ke_lief" in *" $_ke_u "*) ;; *) continue ;; esac
		[ "$_ke_st" = active ] || {
			err "  laeuft nach dem Lauf nicht: $_ke_u"; _ke_befund=1; }
	done
	# Beim Gateway ist der Socket der Nachweis; der Dienst startet erst mit dem
	# ersten Aufruf und darf danach auch wieder enden (Socket-Aktivierung).
	if [ "$_ke_befund" = 0 ]; then
		info "Dienste wieder gestartet."
	else
		err "Nach dem Lauf laeuft nicht alles, was vorher lief."
	fi
	[ "$_ke_alt_e" = 1 ] && set -e
	return "$_ke_befund"
}
