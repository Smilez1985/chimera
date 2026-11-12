#!/bin/sh
# Chimera installer -- Ausfuehrer: Nutzer chimera-sohelper, Ordner, Units.
#
# DESIGN, Regel "Wer prueft, fuehrt aus". Der Ausfuehrer ist ein eigener
# Prozess ohne Netz; der Agent fragt ihn ueber einen Unix-Socket. Die Logik
# steht hier (pruefbar mit Attrappen, wie lib/service.sh), Schritt 99-sohelper
# ruft nur auf.
#
# Grundsaetze:
#   * Eigener Systemnutzer `chimera-sohelper`, ohne Home, ohne Anmeldung, in
#     KEINER Gruppe ausser der eigenen -- weniger Rechte als der Agent.
#   * Socket-Aktivierung wie beim Gateway: systemd haelt
#     /run/chimera/sohelper.sock (Eigentuemer chimera-sohelper, Gruppe
#     chimera = Agent, 0660) und startet den Ausfuehrer beim ersten Aufruf.
#     Deshalb braucht er kein Schreibrecht an /run/chimera.
#   * Arbeitsordner /opt/chimera/sohelper, Eigentum des Ausfuehrers, 700:
#     Das Elternverzeichnis gehoert root, der Agent kommt nicht hinein. Der
#     Kernel setzt die Trennung durch, nicht das Protokoll.
#   * `InaccessiblePaths=/opt/chimera/config`: Er sieht das venv (Interpreter,
#     Pakete), den Schluessel in config/.env sieht er nicht (smilez 11.11.).
#   * Kein `MemoryMax=`: Der Speicher-Controller ist auf dem Pi aus
#     (`cgroup_disable=memory`), die Zeile waere stiller Erfolg (DESIGN 10q).
#   * Nachweis am Ergebnis: ein echter `--ping` ueber den Socket, dann
#     is-active und NRestarts=0 -- nicht der Exitcode von systemctl.

: "${CHIMERA_SOHELPER_NUTZER:=chimera-sohelper}"
: "${CHIMERA_SOHELPER_SOCKETUNIT:=chimera-sohelper.socket}"
: "${CHIMERA_SOHELPER_DIENSTUNIT:=chimera-sohelper.service}"
: "${CHIMERA_SOHELPER_SOCKET:=/run/chimera/sohelper.sock}"
: "${CHIMERA_SOHELPER_ARBEIT:=/opt/chimera/sohelper}"
: "${CHIMERA_SOHELPER_WARTEN:=5}"

sohelper_programm() { printf '%s\n' "$CHIMERA_OPT/bin/chimera-sohelper"; }

sohelper_socket_text() {
	cat <<EOF
# Von chimera-install angelegt (Schritt 99-sohelper). Der Socket gehoert
# systemd: Er steht schon da, wenn der Ausfuehrer noch nicht laeuft, und der
# Agent wartet, statt "abgelehnt" zu bekommen (wie beim Gateway).
[Unit]
Description=Chimera -- Socket des Ausfuehrers (Regel "Wer prueft, fuehrt aus")

[Socket]
ListenStream=$CHIMERA_SOHELPER_SOCKET
Service=$CHIMERA_SOHELPER_DIENSTUNIT
# Der Ausfuehrer bedient, der Agent darf fragen -- sonst niemand.
SocketUser=$CHIMERA_SOHELPER_NUTZER
SocketGroup=$CHIMERA_DIENSTNUTZER
SocketMode=0660
DirectoryMode=0755
RemoveOnStop=yes
Backlog=16

[Install]
WantedBy=sockets.target
EOF
}

sohelper_dienst_text() {
	cat <<EOF
# Von chimera-install angelegt (Schritt 99-sohelper). Aenderungen gehen beim
# naechsten Installerlauf verloren -- eigene Werte in ein Drop-in:
#   systemctl edit $CHIMERA_SOHELPER_DIENSTUNIT
[Unit]
Description=Chimera -- Ausfuehrer: prueft und fuehrt aus (eigener Prozess)
Requires=$CHIMERA_SOHELPER_SOCKETUNIT
After=$CHIMERA_SOHELPER_SOCKETUNIT
# Regel 10p, Punkt 4: hoechstens 5 Starts in 300 s, dann bleibt er aus.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=$CHIMERA_SOHELPER_NUTZER
Group=$CHIMERA_SOHELPER_NUTZER
# Die Gruppe des Gateways, sonst kommt er nicht an dessen Socket (0660
# chimera-tor:chimera). Er fragt dort vor jeder Ausfuehrung die Freigabe --
# lesen darf er den Zustand trotzdem nicht (InaccessiblePaths unten).
SupplementaryGroups=$CHIMERA_DIENSTNUTZER
# Kein Netz -- die eigentliche Sperre (Regel 5n). Die Regeln im Programm
# lehnen Netzprogramme zusaetzlich ab; beides ist gewollt.
IPAddressDeny=any
# Er darf das venv benutzen (Interpreter, Pakete), den Schluessel nicht.
InaccessiblePaths=$CHIMERA_CONFIG
ExecStart=$(sohelper_programm) --arbeit $CHIMERA_SOHELPER_ARBEIT
Restart=on-failure
RestartSec=5
# Exitcode 2 heisst "Aufruf falsch" -- ein Neustart hilft nicht.
RestartPreventExitStatus=2
NoNewPrivileges=yes
RestrictSUIDSGID=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
# Schreiben nur im eigenen Arbeitsordner (ProtectSystem=strict sperrt alles
# andere). Befehle, die er ausfuehrt, laufen in diesem Ordner.
ReadWritePaths=$CHIMERA_SOHELPER_ARBEIT
EOF
}

# Systemnutzer sicherstellen. rc 0 ok, 2 nicht anlegbar.
sohelper_nutzer() {
	_so_u="$CHIMERA_SOHELPER_NUTZER"
	if id -u "$_so_u" >/dev/null 2>&1; then
		manifest_has nutzer "$_so_u" || manifest_record nutzer "$_so_u" vorher_da
		info "Ausfuehrer-Nutzer vorhanden: $_so_u"
		return 0
	fi
	if is_dry_run; then
		info "[wuerde anlegen] Systemnutzer $_so_u (ohne Home, ohne Anmeldung, ohne Gruppen)"
		return 0
	fi
	have_cmd useradd || { err "useradd fehlt -- $_so_u nicht anlegbar."; return 2; }
	_so_shell=/usr/sbin/nologin
	[ -x "$(rootpath "$_so_shell")" ] || _so_shell=/bin/false
	useradd --system --user-group --no-create-home --shell "$_so_shell" "$_so_u" \
		>/dev/null 2>&1 || true
	# Am Ergebnis pruefen, nicht am Exitcode.
	if ! id -u "$_so_u" >/dev/null 2>&1; then
		err "Nutzer $_so_u nicht angelegt (useradd)."
		return 2
	fi
	manifest_record nutzer "$_so_u" neu
	info "Nutzer angelegt: $_so_u"
	return 0
}

# Arbeitsordner: Eigentum des Ausfuehrers, 700. rc 0 ok, 2 nicht anlegbar.
sohelper_ordner() {
	_so_p="$(rootpath "$CHIMERA_SOHELPER_ARBEIT")"
	if is_dry_run; then
		info "[wuerde anlegen] $CHIMERA_SOHELPER_ARBEIT (700 $CHIMERA_SOHELPER_NUTZER)"
		return 0
	fi
	# Das Elternverzeichnis ($CHIMERA_OPT) gehoert root und bleibt so: Der
	# Agent kann den Ordner damit weder lesen noch ersetzen (Regel 10r).
	mkdir -p "$_so_p" || { err "nicht anlegbar: $CHIMERA_SOHELPER_ARBEIT"; return 2; }
	chown "$CHIMERA_SOHELPER_NUTZER:$CHIMERA_SOHELPER_NUTZER" "$_so_p" 2>/dev/null || true
	chmod 700 "$_so_p"
	# Am Ergebnis pruefen: Rechte sind hier die Schranke, nicht die Absicht.
	_so_recht="$(stat -c '%U %a' "$_so_p" 2>/dev/null || true)"
	if [ "$_so_recht" != "$CHIMERA_SOHELPER_NUTZER 700" ]; then
		err "$CHIMERA_SOHELPER_ARBEIT gehoert $_so_recht statt $CHIMERA_SOHELPER_NUTZER 700."
		return 2
	fi
	manifest_has verzeich "$CHIMERA_SOHELPER_ARBEIT" || \
		manifest_record verzeich "$CHIMERA_SOHELPER_ARBEIT" ""
	info "Arbeitsordner: $CHIMERA_SOHELPER_ARBEIT (700 $_so_u)"
	# Die Schluessel der Fernausfuehrung liegen beim Ausfuehrer, nicht beim
	# Gateway (DESIGN: das Gateway hat Netz und keinen Schluessel, der
	# Ausfuehrer Schluessel und kein Netz). 0700 -- der Agent kommt nicht
	# heran, der Nutzer legt Schluessel mit sudo hinein.
	_so_ssh="$_so_p/ssh"
	mkdir -p "$_so_ssh/keys" || { err "nicht anlegbar: $_so_ssh"; return 2; }
	chown -R "$CHIMERA_SOHELPER_NUTZER:$CHIMERA_SOHELPER_NUTZER" "$_so_ssh" 2>/dev/null || true
	chmod 700 "$_so_ssh" "$_so_ssh/keys"
	manifest_has verzeich "$CHIMERA_SOHELPER_ARBEIT/ssh" || \
		manifest_record verzeich "$CHIMERA_SOHELPER_ARBEIT/ssh" ""
	info "Schluesselordner: $CHIMERA_SOHELPER_ARBEIT/ssh/keys (700 $_so_u)"
	return 0
}

# Der ganze Ablauf. rc 0 Ausfuehrer antwortet nachweislich, 1 Befund, 2 Abbruch.
sohelper_einrichten() {
	_so_prog="$(rootpath "$(sohelper_programm)")"
	_so_dir="$(dirname "$(service_unit_pfad)")"

	have_cmd systemctl || { err "systemctl fehlt -- kein systemd, kein Ausfuehrer."; return 2; }
	if ! is_dry_run && ! getent group "$CHIMERA_DIENSTNUTZER" >/dev/null 2>&1; then
		err "Gruppe $CHIMERA_DIENSTNUTZER fehlt -- Schritt 98 zuerst."
		return 2
	fi

	log "Ausfuehrer-Nutzer"
	sohelper_nutzer || return 2
	log ""

	log "Arbeitsordner"
	sohelper_ordner || return 2
	log ""

	if ! is_dry_run && [ ! -x "$_so_prog" ]; then
		warn "$(sohelper_programm) fehlt -- Schritt 55 hat kein Binary abgelegt."
		warn "Der Ausfuehrer wird nicht eingerichtet; der Agent arbeitet wie bisher."
		return 1
	fi

	log "Units"
	_sd_neu=0
	service_datei "$_so_dir/$CHIMERA_SOHELPER_SOCKETUNIT" "$(sohelper_socket_text)" || return 2
	service_datei "$_so_dir/$CHIMERA_SOHELPER_DIENSTUNIT" "$(sohelper_dienst_text)" || return 2
	_so_neu=$_sd_neu

	if is_dry_run; then
		info "[wuerde] systemctl daemon-reload"
		info "[wuerde] systemctl enable --now $CHIMERA_SOHELPER_SOCKETUNIT"
		info "[wuerde] $CHIMERA_SOHELPER_SOCKET abfragen (--ping)"
		return 0
	fi
	[ "$_so_neu" = 1 ] && systemctl daemon-reload

	# Zustand zaehlt, nicht der Manifesteintrag (wie beim Gateway).
	if ! manifest_has dienst "$CHIMERA_SOHELPER_SOCKETUNIT" || \
	   ! systemctl is-enabled --quiet "$CHIMERA_SOHELPER_SOCKETUNIT" 2>/dev/null || \
	   ! systemctl is-active --quiet "$CHIMERA_SOHELPER_SOCKETUNIT" 2>/dev/null; then
		systemctl enable --now "$CHIMERA_SOHELPER_SOCKETUNIT" >/dev/null 2>&1 || {
			err "systemctl enable --now $CHIMERA_SOHELPER_SOCKETUNIT schlug fehl."
			return 2; }
		manifest_has dienst "$CHIMERA_SOHELPER_SOCKETUNIT" || \
			manifest_record dienst "$CHIMERA_SOHELPER_SOCKETUNIT" aktiviert
	elif [ "$_so_neu" = 1 ]; then
		# Neue Unit-Fassung: Socket neu laden, der Dienst startet beim
		# naechsten Aufruf mit dem neuen Text.
		systemctl restart "$CHIMERA_SOHELPER_SOCKETUNIT" >/dev/null 2>&1 || true
		systemctl stop "$CHIMERA_SOHELPER_DIENSTUNIT" >/dev/null 2>&1 || true
	fi
	log ""

	log "Nachweis"
	# Ein echter Aufruf: er startet den Ausfuehrer per Socket-Aktivierung.
	if ! "$_so_prog" --ping "$(rootpath "$CHIMERA_SOHELPER_SOCKET")" >/dev/null 2>&1; then
		err "Der Ausfuehrer antwortet nicht auf $CHIMERA_SOHELPER_SOCKET."
		err "  journalctl -u $CHIMERA_SOHELPER_DIENSTUNIT -n 30"
		return 1
	fi
	sleep "$CHIMERA_SOHELPER_WARTEN"
	_so_aktiv="$(systemctl is-active "$CHIMERA_SOHELPER_DIENSTUNIT" 2>/dev/null || true)"
	_so_nr="$(systemctl show -p NRestarts --value "$CHIMERA_SOHELPER_DIENSTUNIT" 2>/dev/null || true)"
	if [ "$_so_aktiv" != active ]; then
		err "Der Ausfuehrer ist nicht aktiv (Zustand: ${_so_aktiv:-unbekannt})."
		err "  journalctl -u $CHIMERA_SOHELPER_DIENSTUNIT -n 30"
		return 1
	fi
	case "$_so_nr" in
		0) : ;;
		""|*[!0-9]*)
			warn "NRestarts nicht lesbar -- eine Neustartschleife ist nicht"
			warn "ausgeschlossen, nur nicht messbar." ;;
		*)
			err "Ausfuehrer aktiv, aber schon $_so_nr Mal neu gestartet -- Schleife."
			return 1 ;;
	esac
	info "antwortet, aktiv, NRestarts=${_so_nr:-?}"
	return 0
}

# --- Rueckbau --------------------------------------------------------------
# Reihenfolge: Socket und Dienst anhalten, Units weg, daemon-reload, Ordner,
# Nutzer. Der Ordner wird nur entfernt, wenn er leer ist -- was der Agent dort
# hat arbeiten lassen, gehoert ihm, nicht dem Installer.
sohelper_rueckbau() {
	_so_befund=0
	for _so_e in "$CHIMERA_SOHELPER_SOCKETUNIT" "$CHIMERA_SOHELPER_DIENSTUNIT"; do
		manifest_has dienst "$CHIMERA_SOHELPER_SOCKETUNIT" || break
		if is_dry_run; then
			info "[wuerde] systemctl disable --now $_so_e"
		elif have_cmd systemctl; then
			systemctl disable --now "$_so_e" >/dev/null 2>&1 || true
			systemctl stop "$_so_e" >/dev/null 2>&1 || true
			if [ "$(systemctl is-active "$_so_e" 2>/dev/null)" = active ]; then
				warn "laeuft noch: $_so_e"; _so_befund=1
			else
				info "gestoppt und abgeschaltet: $_so_e"
			fi
		else
			warn "systemctl fehlt -- $_so_e nicht abschaltbar."; _so_befund=1
		fi
	done

	_so_f="${TMPDIR:-/tmp}/.chimera-rm-sohelper.$$"
	manifest_list_von datei 99-sohelper >"$_so_f"
	_so_weg=0
	# Das Manifest nennt Zielpfade; `rootpath` macht daraus den Pfad in der
	# Wurzel, die gerade bearbeitet wird -- auf dem Geraet ist das derselbe.
	# Entfernt wird nur, was noch unsere Pruefsumme hat (wie der Rueckbau von
	# Schritt 55): eine ausgetauschte Datei ist nicht mehr unsere.
	while IFS='	' read -r _so_p _so_soll; do
		[ -n "$_so_p" ] || continue
		# Auf dem Geraet ist CHIMERA_ROOT leer -- derselbe Pfad. In einem
		# erfundenen Wurzelverzeichnis (Tests) wird vorgesetzt, aber nur
		# einmal: ein Pfad, der die Wurzel schon traegt, bleibt wie er ist.
		case "$_so_p" in
			"$CHIMERA_ROOT"*) _so_ziel="$_so_p" ;;
			*)                _so_ziel="$(rootpath "$_so_p")" ;;
		esac
		if [ ! -e "$_so_ziel" ] && [ ! -L "$_so_ziel" ]; then
			info "schon weg: $_so_p"; continue
		fi
		if [ -n "$_so_soll" ] && [ "$(network_checksum "$_so_ziel")" != "$_so_soll" ]; then
			warn "nicht mehr unsere Datei (Pruefsumme weicht ab), bleibt liegen: $_so_p"
			_so_befund=1; continue
		fi
		if is_dry_run; then info "[wuerde entfernen] $_so_p"; continue; fi
		rm -f "$_so_ziel"
		if [ -e "$_so_ziel" ]; then warn "blieb stehen: $_so_p"; _so_befund=1
		else info "entfernt: $_so_p"; _so_weg=1; fi
	done <"$_so_f"
	rm -f "$_so_f"
	if [ "$_so_weg" = 1 ] && have_cmd systemctl; then
		systemctl daemon-reload >/dev/null 2>&1 || true
	fi

	# Arbeitsordner weg, wenn leer -- sonst bleibt er stehen und wird benannt.
	_so_arbeit="$(rootpath "$CHIMERA_SOHELPER_ARBEIT")"
	if [ -d "$_so_arbeit" ]; then
		if is_dry_run; then
			info "[wuerde entfernen] $CHIMERA_SOHELPER_ARBEIT (nur wenn leer)"
		# Die leeren Unterordner der Fernausfuehrung zuerst (ssh/keys legt
		# der Installer an). Liegt dort ein Schluessel, bleibt alles stehen:
		# ein Schluessel gehoert dem Nutzer, nicht dem Installer.
		elif rmdir "$_so_arbeit/ssh/keys" "$_so_arbeit/ssh" 2>/dev/null; then
			if rmdir "$_so_arbeit" 2>/dev/null; then
				info "entfernt: $CHIMERA_SOHELPER_ARBEIT"
			else
				warn "$CHIMERA_SOHELPER_ARBEIT ist nicht leer -- bleibt stehen."
				_so_befund=1
			fi
		elif rmdir "$_so_arbeit" 2>/dev/null; then
			info "entfernt: $CHIMERA_SOHELPER_ARBEIT"
		else
			warn "$CHIMERA_SOHELPER_ARBEIT ist nicht leer -- bleibt stehen."
			_so_befund=1
		fi
	fi

	if manifest_has_exact nutzer "$CHIMERA_SOHELPER_NUTZER" neu; then
		if is_dry_run; then
			info "[wuerde entfernen] Nutzer $CHIMERA_SOHELPER_NUTZER"
		elif ! id -u "$CHIMERA_SOHELPER_NUTZER" >/dev/null 2>&1; then
			info "schon weg: Nutzer $CHIMERA_SOHELPER_NUTZER"
		elif have_cmd userdel; then
			userdel "$CHIMERA_SOHELPER_NUTZER" >/dev/null 2>&1 || true
			if id -u "$CHIMERA_SOHELPER_NUTZER" >/dev/null 2>&1; then
				warn "Nutzer blieb: $CHIMERA_SOHELPER_NUTZER"; _so_befund=1
			else
				info "entfernt: Nutzer $CHIMERA_SOHELPER_NUTZER"
			fi
		else
			warn "userdel fehlt -- Nutzer $CHIMERA_SOHELPER_NUTZER bleibt."; _so_befund=1
		fi
	elif manifest_has nutzer "$CHIMERA_SOHELPER_NUTZER"; then
		info "Nutzer $CHIMERA_SOHELPER_NUTZER bleibt: er war vor Chimera da."
	fi
	return "$_so_befund"
}
