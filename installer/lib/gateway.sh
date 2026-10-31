#!/bin/sh
# Chimera installer -- Gateway: Nutzer chimera-tor, Socket- und Dienst-Unit.
#
# DESIGN Regel 5n. Das Gateway ist der einzige Prozess mit Netzzugang, der
# Agent-Dienst (chimera.service) spricht nur ueber /run/chimera/tor.sock mit
# ihm. Die Logik steht hier (pruefbar mit Attrappen, wie lib/service.sh);
# der Schritt 99 ruft nur auf.
#
# Grundsaetze:
#   * Eigener Systemnutzer `chimera-tor`, ohne Home und ohne Anmeldung.
#   * Socket-Aktivierung: systemd haelt /run/chimera/tor.sock (Besitzer
#     chimera-tor, Gruppe chimera, Modus 660) und startet das Gateway beim
#     ersten Aufruf. Der Dienst haengt NICHT per Requires= am Gateway
#     (Regel 5n: ein abstuerzendes Gateway nimmt das Gesicht nicht mit).
#   * MemoryMax=10M (Regel 5n/10q), gemessen am Geraet, nicht angenommen.
#   * Exitcode 2 des Programms heisst "Konfiguration falsch" -- ein Neustart
#     hilft nicht (RestartPreventExitStatus=2, Regel 10p).
#   * Nachweis am Ergebnis: ein echter Aufruf des Sockets (`--ping`), dann
#     is-active UND NRestarts=0 -- nicht der Exitcode von systemctl.
#   * NICHT in diesem Schritt: IPAddressDeny=any fuer chimera.service. Der
#     Python-Dienst haelt bis Phase 4d Schritt 3 noch selbst die Anbieter;
#     die Sperre jetzt zoege ihm den Ollama-Server weg.

: "${CHIMERA_TOR_NUTZER:=chimera-tor}"
: "${CHIMERA_TOR_SOCKETUNIT:=chimera-tor.socket}"
: "${CHIMERA_TOR_DIENSTUNIT:=chimera-tor.service}"
: "${CHIMERA_TOR_SOCKET:=/run/chimera/tor.sock}"
: "${CHIMERA_SITZUNG_SOCKETUNIT:=chimera-sitzung.socket}"
: "${CHIMERA_SITZUNG_SOCKET:=/run/chimera/sitzung.sock}"
: "${CHIMERA_TOR_SPEICHER:=10M}"
: "${CHIMERA_TOR_WARTEN:=5}"

# Der Sitzungs-Socket (Regel 5s): der eine Weg in die Hauptsitzung. Er gehoert
# dem AGENT-Dienst (der bedient ihn), das Gateway ist Mitglied der Gruppe
# und der einzige Client. systemd haelt ihn und reicht ihn an chimera.service
# weiter (LISTEN_FDS), er ueberlebt also einen Neustart des Dienstes.
gateway_sitzung_socket_text() {
	cat <<EOF
# Von chimera-install angelegt (Schritt 99). Regel 5s.
[Unit]
Description=Chimera -- Sitzungs-Socket, der eine Weg in die Hauptsitzung (Regel 5s)

[Socket]
ListenStream=$CHIMERA_SITZUNG_SOCKET
Service=$CHIMERA_DIENST
SocketUser=$CHIMERA_DIENSTNUTZER
SocketGroup=$CHIMERA_TOR_NUTZER
SocketMode=0660
DirectoryMode=0755
RemoveOnStop=yes
Backlog=16

[Install]
WantedBy=sockets.target
EOF
}

gateway_programm() { printf '%s\n' "$CHIMERA_OPT/bin/chimera-tor"; }

gateway_socket_text() {
	cat <<EOF
# Von chimera-install angelegt (Schritt 99). Der Socket gehoert systemd:
# Er steht schon da, wenn das Gateway noch nicht (oder nicht mehr) laeuft,
# und der Aufrufer wartet, statt "abgelehnt" zu bekommen.
[Unit]
Description=Chimera -- Socket des Gateways (Regel 5n)

[Socket]
ListenStream=$CHIMERA_TOR_SOCKET
SocketUser=$CHIMERA_TOR_NUTZER
SocketGroup=$CHIMERA_DIENSTNUTZER
SocketMode=0660
DirectoryMode=0755
# Beim Stoppen verschwindet die Datei, sonst bliebe ein toter Socket liegen.
RemoveOnStop=yes
# Hoechstens so viele wartende Verbindungen; mehr bedient das Gateway nicht.
Backlog=16

[Install]
WantedBy=sockets.target
EOF
}

gateway_dienst_text() {
	cat <<EOF
# Von chimera-install angelegt (Schritt 99). Aenderungen gehen beim
# naechsten Installerlauf verloren -- eigene Werte in ein Drop-in:
#   systemctl edit $CHIMERA_TOR_DIENSTUNIT
[Unit]
Description=Chimera -- Gateway, der einzige Weg nach draussen (Regel 5n)
Requires=$CHIMERA_TOR_SOCKETUNIT
After=$CHIMERA_TOR_SOCKETUNIT network-online.target
Wants=network-online.target
# Regel 10p, Punkt 4: hoechstens 5 Starts in 300 s, dann bleibt es aus.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=$CHIMERA_TOR_NUTZER
Group=$CHIMERA_TOR_NUTZER
# Die .env liest systemd als root; der Prozess bekommt nur die Werte.
# So braucht chimera-tor kein Leserecht auf die Datei (Regel 5l).
EnvironmentFile=-$CHIMERA_CONFIG/.env
# Der eine Weg in die Hauptsitzung (Regel 5s). Die Telegram-Tuer im Gateway
# spricht ueber diesen Socket; er gehoert dem Agent-Dienst, die Gruppe des
# Sockets ist die des Gateways (SocketGroup in chimera-sitzung.socket).
Environment=CHIMERA_SITZUNG_SOCKET=$CHIMERA_SITZUNG_SOCKET
ExecStart=$(gateway_programm) --dienst
Restart=on-failure
RestartSec=5
RestartPreventExitStatus=2
# Regel 5n/10q: Obergrenze fuer den Prozess, vom Kernel durchgesetzt.
MemoryMax=$CHIMERA_TOR_SPEICHER
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
EOF
}

# Systemnutzer sicherstellen. rc 0 ok, 2 nicht anlegbar.
gateway_nutzer() {
	_gn_u="$CHIMERA_TOR_NUTZER"
	if id -u "$_gn_u" >/dev/null 2>&1; then
		manifest_has nutzer "$_gn_u" || manifest_record nutzer "$_gn_u" vorher_da
		info "Gateway-Nutzer vorhanden: $_gn_u"
		return 0
	fi
	if is_dry_run; then
		info "[wuerde anlegen] Systemnutzer $_gn_u (ohne Home, ohne Anmeldung)"
		return 0
	fi
	have_cmd useradd || { err "useradd fehlt -- $_gn_u nicht anlegbar."; return 2; }
	_gn_shell=/usr/sbin/nologin
	[ -x "$(rootpath "$_gn_shell")" ] || _gn_shell=/bin/false
	useradd --system --user-group --no-create-home --shell "$_gn_shell" "$_gn_u" \
		>/dev/null 2>&1 || true
	# Am Ergebnis pruefen, nicht am Exitcode.
	if ! id -u "$_gn_u" >/dev/null 2>&1; then
		err "Gateway-Nutzer $_gn_u nicht angelegt (useradd)."
		return 2
	fi
	manifest_record nutzer "$_gn_u" neu
	info "Gateway-Nutzer angelegt: $_gn_u"
	return 0
}

# Web-Passwort (Regel 5m, 5j): Der Installer fragt nicht, er liest
# CHIMERA_WEB_PASSWORT aus der Umgebung des Laufs, hasht es mit dem Binary
# (Eingabe nur ueber stdin, nie als Argument) und traegt NUR den Hash in die
# .env ein. Ein vorhandener Hash wird nie ueberschrieben. Ohne Passwort bleibt
# die Oberflaeche zu -- das ist gewollt, kein Fehler.
# rc 0 nichts zu tun oder eingetragen (CHIMERA_WEB_NEU=1 bei neu), 2 Abbruch.
gateway_web_passwort() {
	CHIMERA_WEB_NEU=0
	_wp_env="$(rootpath "$CHIMERA_CONFIG")/.env"
	_wp_prog="$(rootpath "$(gateway_programm)")"
	if is_dry_run; then
		[ -n "${CHIMERA_WEB_PASSWORT:-}" ] && info "[wuerde] Web-Passwort hashen und in die .env eintragen"
		return 0
	fi
	[ -f "$_wp_env" ] || { info "Web-Oberflaeche: keine .env -- uebersprungen."; return 0; }
	if grep -Eq '^CHIMERA_WEB_PASSWORT_HASH=.+' "$_wp_env"; then
		info "Web-Oberflaeche: Passwort-Hash vorhanden (bleibt unangetastet)."
		return 0
	fi
	if [ -z "${CHIMERA_WEB_PASSWORT:-}" ]; then
		info "Web-Oberflaeche bleibt zu (kein Passwort). Einschalten:"
		info "  echo 'MeinPasswort' | $(gateway_programm) --passwort-hash"
		info "  und den Hash als CHIMERA_WEB_PASSWORT_HASH in $CHIMERA_CONFIG/.env eintragen."
		return 0
	fi
	_wp_hash="$(printf '%s\n' "$CHIMERA_WEB_PASSWORT" | "$_wp_prog" --passwort-hash 2>/dev/null)" || _wp_hash=""
	# Ergebnis pruefen, nicht den Exitcode: leer oder falsche Form = Abbruch.
	case "$_wp_hash" in
		pbkdf2-sha256\$*\$*\$*) : ;;
		*) err "Web-Passwort: kein Hash erhalten (mindestens 8 Zeichen?)."; return 2 ;;
	esac
	_wp_tmp="$_wp_env.neu"
	if grep -q '^CHIMERA_WEB_PASSWORT_HASH=' "$_wp_env"; then
		HASH="$_wp_hash" awk '/^CHIMERA_WEB_PASSWORT_HASH=/ { print "CHIMERA_WEB_PASSWORT_HASH=" ENVIRON["HASH"]; next } { print }' "$_wp_env" >"$_wp_tmp" || { rm -f "$_wp_tmp"; return 2; }
	else
		{ cat "$_wp_env"; printf 'CHIMERA_WEB_PASSWORT_HASH=%s\n' "$_wp_hash"; } >"$_wp_tmp" || { rm -f "$_wp_tmp"; return 2; }
	fi
	chmod --reference="$_wp_env" "$_wp_tmp" 2>/dev/null || chmod 640 "$_wp_tmp"
	chown --reference="$_wp_env" "$_wp_tmp" 2>/dev/null || true
	if ! grep -qxF "CHIMERA_WEB_PASSWORT_HASH=$_wp_hash" "$_wp_tmp"; then
		rm -f "$_wp_tmp"; err "Web-Passwort: Eintrag nicht geschrieben."; return 2
	fi
	mv "$_wp_tmp" "$_wp_env" || { rm -f "$_wp_tmp"; return 2; }
	CHIMERA_WEB_NEU=1
	info "Web-Oberflaeche: Passwort-Hash eingetragen (Port ${CHIMERA_WEB_PORT:-8080})."
	return 0
}

# Der ganze Ablauf. rc 0 Gateway antwortet nachweislich, 1 Befund, 2 Abbruch.
gateway_einrichten() {
	_ge_prog="$(rootpath "$(gateway_programm)")"
	_ge_dir="$(dirname "$(service_unit_pfad)")"

	have_cmd systemctl || { err "systemctl fehlt -- kein systemd, kein Gateway."; return 2; }
	if ! is_dry_run && [ ! -x "$_ge_prog" ]; then
		warn "$(gateway_programm) fehlt -- Schritt 55 hat kein Binary abgelegt."
		warn "Das Gateway wird nicht eingerichtet; der Dienst laeuft ohne."
		return 1
	fi
	# Der Socket gehoert der Gruppe des Agent-Dienstes -- die muss es geben.
	if ! is_dry_run && ! getent group "$CHIMERA_DIENSTNUTZER" >/dev/null 2>&1; then
		err "Gruppe $CHIMERA_DIENSTNUTZER fehlt -- Schritt 98 zuerst."
		return 2
	fi

	log "Gateway-Nutzer"
	gateway_nutzer || return 2
	log ""

	log "Web-Oberflaeche"
	gateway_web_passwort || return 2
	log ""

	log "Units"
	_sd_neu=0
	service_datei "$_ge_dir/$CHIMERA_TOR_SOCKETUNIT" "$(gateway_socket_text)" || return 2
	service_datei "$_ge_dir/$CHIMERA_TOR_DIENSTUNIT" "$(gateway_dienst_text)" || return 2
	service_datei "$_ge_dir/$CHIMERA_SITZUNG_SOCKETUNIT" "$(gateway_sitzung_socket_text)" || return 2
	_ge_neu=$_sd_neu

	if is_dry_run; then
		info "[wuerde] systemctl daemon-reload"
		info "[wuerde] systemctl enable --now $CHIMERA_TOR_SOCKETUNIT"
		info "[wuerde] systemctl enable --now $CHIMERA_SITZUNG_SOCKETUNIT"
		return 0
	fi
	[ "$_ge_neu" = 1 ] && systemctl daemon-reload

	# Das Manifest sagt, was der Installer einmal tat, nicht was jetzt gilt:
	# Ein von Hand abgeschalteter Socket stuende dort weiter als "aktiviert".
	# Darum zaehlt der Zustand (is-enabled UND is-active), nicht der Eintrag.
	_ge_tor_neu=0
	if ! manifest_has dienst "$CHIMERA_TOR_SOCKETUNIT" || \
	   ! systemctl is-enabled --quiet "$CHIMERA_TOR_SOCKETUNIT" 2>/dev/null || \
	   ! systemctl is-active --quiet "$CHIMERA_TOR_SOCKETUNIT" 2>/dev/null; then
		systemctl enable --now "$CHIMERA_TOR_SOCKETUNIT" >/dev/null 2>&1 || {
			err "systemctl enable --now $CHIMERA_TOR_SOCKETUNIT schlug fehl."; return 2; }
		manifest_has dienst "$CHIMERA_TOR_SOCKETUNIT" || manifest_record dienst "$CHIMERA_TOR_SOCKETUNIT" aktiviert
		_ge_tor_neu=1
	fi
	# Der Sitzungs-Socket hat einen eigenen Manifesteintrag: Er kam spaeter
	# dazu, gilt also auch fuer Geraete, die das Gateway schon haben.
	if ! manifest_has dienst "$CHIMERA_SITZUNG_SOCKETUNIT"; then
		# systemd weigert sich, einen Socket zu starten, dessen Dienst schon
		# laeuft ("already active, refusing"; am Pi gefunden). Der Dienst muss
		# kurz aus und danach wieder an -- diesmal mit dem Socket von systemd.
		_ge_dienst_lief=0
		if systemctl is-active --quiet "$CHIMERA_DIENST" 2>/dev/null; then
			_ge_dienst_lief=1
			info "Dienst wird kurz angehalten, damit systemd den Sitzungs-Socket halten kann."
			systemctl stop "$CHIMERA_DIENST" >/dev/null 2>&1 || {
				err "systemctl stop $CHIMERA_DIENST schlug fehl."; return 2; }
		fi
		systemctl enable --now "$CHIMERA_SITZUNG_SOCKETUNIT" >/dev/null 2>&1 || {
			err "systemctl enable --now $CHIMERA_SITZUNG_SOCKETUNIT schlug fehl."
			[ "$_ge_dienst_lief" = 1 ] && systemctl start "$CHIMERA_DIENST" >/dev/null 2>&1
			return 2; }
		manifest_record dienst "$CHIMERA_SITZUNG_SOCKETUNIT" aktiviert
		if [ "$_ge_dienst_lief" = 1 ]; then
			systemctl start "$CHIMERA_DIENST" >/dev/null 2>&1 || {
				err "systemctl start $CHIMERA_DIENST schlug fehl."; return 2; }
		fi
	elif [ "$_ge_neu" = 1 ]; then
		systemctl restart "$CHIMERA_SITZUNG_SOCKETUNIT" >/dev/null 2>&1 || true
	fi
	if [ "$CHIMERA_WEB_NEU" = 1 ] && [ "$_ge_neu" = 0 ] && [ "$_ge_tor_neu" = 0 ]; then
		# Neuer Hash: das Gateway liest die .env nur beim Start.
		systemctl stop "$CHIMERA_TOR_DIENSTUNIT" >/dev/null 2>&1 || true
	fi
	if [ "$_ge_neu" = 1 ] && [ "$_ge_tor_neu" = 0 ]; then
		# Neue Unit-Fassung: Socket und Dienst neu laden. Der Socket-Neustart
		# schliesst Verbindungen -- das Gateway hat noch keine Sitzungen.
		systemctl reset-failed "$CHIMERA_TOR_DIENSTUNIT" >/dev/null 2>&1 || true
		systemctl restart "$CHIMERA_TOR_SOCKETUNIT" || {
			err "systemctl restart $CHIMERA_TOR_SOCKETUNIT schlug fehl."; return 1; }
		systemctl stop "$CHIMERA_TOR_DIENSTUNIT" >/dev/null 2>&1 || true
	fi
	log ""

	log "Nachweis"
	# Ein echter Aufruf: er startet das Gateway per Socket-Aktivierung.
	if ! "$_ge_prog" --ping "$(rootpath "$CHIMERA_TOR_SOCKET")" >/dev/null 2>&1; then
		err "Das Gateway antwortet nicht auf $CHIMERA_TOR_SOCKET."
		err "  journalctl -u $CHIMERA_TOR_DIENSTUNIT -n 30"
		return 1
	fi
	sleep "$CHIMERA_TOR_WARTEN"
	_ge_aktiv="$(systemctl is-active "$CHIMERA_TOR_DIENSTUNIT" 2>/dev/null || true)"
	_ge_nr="$(systemctl show -p NRestarts --value "$CHIMERA_TOR_DIENSTUNIT" 2>/dev/null || true)"
	if [ "$_ge_aktiv" != active ]; then
		err "Das Gateway ist nicht aktiv (Zustand: ${_ge_aktiv:-unbekannt})."
		err "  journalctl -u $CHIMERA_TOR_DIENSTUNIT -n 30"
		return 1
	fi
	case "$_ge_nr" in
		0) : ;;
		""|*[!0-9]*)
			warn "NRestarts nicht lesbar -- eine Neustartschleife ist nicht"
			warn "ausgeschlossen, nur nicht messbar." ;;
		*)
			err "Gateway aktiv, aber schon $_ge_nr Mal neu gestartet -- Schleife."
			return 1 ;;
	esac
	info "antwortet, aktiv, NRestarts=${_ge_nr:-?}"
	return 0
}

# --- Rueckbau --------------------------------------------------------------
# Reihenfolge: Socket und Dienst anhalten, Units weg, daemon-reload, Nutzer.
gateway_rueckbau() {
	_gr_befund=0
	for _gr_e in "$CHIMERA_SITZUNG_SOCKETUNIT" "$CHIMERA_TOR_SOCKETUNIT" "$CHIMERA_TOR_DIENSTUNIT"; do
		# Den Dienst gibt es nie im Manifest (er startet per Socket); beide
		# immer anhalten, wenn der Socket unser ist.
		manifest_has dienst "$CHIMERA_TOR_SOCKETUNIT" || continue
		if is_dry_run; then
			info "[wuerde] systemctl disable --now $_gr_e"
		elif have_cmd systemctl; then
			systemctl disable --now "$_gr_e" >/dev/null 2>&1 || true
			systemctl stop "$_gr_e" >/dev/null 2>&1 || true
			if [ "$(systemctl is-active "$_gr_e" 2>/dev/null)" = active ]; then
				warn "laeuft noch: $_gr_e"; _gr_befund=1
			else
				info "gestoppt und abgeschaltet: $_gr_e"
			fi
		else
			warn "systemctl fehlt -- $_gr_e nicht abschaltbar."; _gr_befund=1
		fi
	done

	_gr_f="${TMPDIR:-/tmp}/.chimera-rm-tor.$$"
	manifest_list_von datei 99-gateway | cut -f1 >"$_gr_f"
	_gr_weg=0
	while IFS= read -r _gr_p; do
		[ -n "$_gr_p" ] || continue
		if is_dry_run; then info "[wuerde entfernen] $_gr_p"; continue; fi
		rm -f "$_gr_p"
		if [ -e "$_gr_p" ]; then warn "blieb stehen: $_gr_p"; _gr_befund=1
		else info "entfernt: $_gr_p"; _gr_weg=1; fi
	done <"$_gr_f"
	rm -f "$_gr_f"
	if [ "$_gr_weg" = 1 ] && have_cmd systemctl; then
		systemctl daemon-reload >/dev/null 2>&1 || true
	fi

	# Der Gateway-Nutzer hat keine Daten; nur entfernen, was wir anlegten.
	if manifest_has_exact nutzer "$CHIMERA_TOR_NUTZER" neu; then
		if is_dry_run; then
			info "[wuerde entfernen] Nutzer $CHIMERA_TOR_NUTZER"
		elif ! id -u "$CHIMERA_TOR_NUTZER" >/dev/null 2>&1; then
			info "schon weg: Nutzer $CHIMERA_TOR_NUTZER"
		elif have_cmd userdel; then
			userdel "$CHIMERA_TOR_NUTZER" >/dev/null 2>&1 || true
			if id -u "$CHIMERA_TOR_NUTZER" >/dev/null 2>&1; then
				warn "Nutzer blieb: $CHIMERA_TOR_NUTZER"; _gr_befund=1
			else
				info "entfernt: Nutzer $CHIMERA_TOR_NUTZER"
			fi
		else
			warn "userdel fehlt -- Nutzer $CHIMERA_TOR_NUTZER bleibt."; _gr_befund=1
		fi
	elif manifest_has nutzer "$CHIMERA_TOR_NUTZER"; then
		info "Nutzer $CHIMERA_TOR_NUTZER bleibt: er war vor Chimera da."
	fi
	return "$_gr_befund"
}
