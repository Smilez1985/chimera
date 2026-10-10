#!/bin/sh
# Chimera installer -- Dienst: Dienstbenutzer und systemd-Unit.
#
# Die Logik steht hier, nicht im Schritt: So laesst sie sich in einem Test
# laden, in dem `systemctl`, `useradd` und Co. als Shell-Funktionen
# bereitstehen (wie bei lib/module.sh). Der Schritt 98 ruft nur auf.
#
# Grundsaetze (docs/INSTALLER.md 4c):
#   * Eigener Systemnutzer `chimera`, kein root. Der Agent hat ein
#     Werkzeug, das Programme startet -- das soll nicht als root laufen.
#   * Hardwaregruppen stehen in der Unit (SupplementaryGroups=), nicht per
#     usermod am Nutzer. Dann gibt es nichts zurueckzunehmen ausser der
#     Unit selbst.
#   * Nutzerdaten liegen in /var/lib/chimera/daten (StateDirectory=). Das
#     Manifest in /var/lib/chimera gehoert root und bleibt fuer den Dienst
#     unbeschreibbar -- sonst koennte ein Werkzeugaufruf des Agenten
#     festlegen, was der Deinstallierer loescht.
#   * StartLimit* steht in [Unit], nicht in [Service]: Dort ignoriert
#     systemd die Werte mit einer Warnung im Journal, und die Unit startet
#     scheinbar richtig (Regel 10p, Punkt 4).
#   * Exitcode 2 heisst "Konfiguration falsch" -- ein Neustart hilft dann
#     nicht (RestartPreventExitStatus=2).
#   * Nachweis: nach dem Start warten, dann `is-active` UND NRestarts=0.
#     `is-active` allein sieht eine Neustartschleife als gesund, wenn man
#     im richtigen Moment fragt.

: "${CHIMERA_DIENST:=chimera.service}"
: "${CHIMERA_DIENSTNUTZER:=chimera}"
: "${CHIMERA_DIENST_WARTEN:=10}"

SERVICE_GRUPPEN_KANDIDATEN="audio spi gpio i2c video"

service_unit_pfad()  { rootpath "/etc/systemd/system/$CHIMERA_DIENST"; }
service_stand_pfad() { rootpath /var/lib/chimera/dienst-stand; }

# Welche Hardwaregruppen gibt es auf diesem System? systemd verweigert den
# Start, wenn SupplementaryGroups= eine fehlende Gruppe nennt -- also nur
# die vorhandenen eintragen.
service_gruppen() {
	_sg_l=""
	for _sg_g in $SERVICE_GRUPPEN_KANDIDATEN; do
		getent group "$_sg_g" >/dev/null 2>&1 && _sg_l="$_sg_l $_sg_g"
	done
	printf '%s\n' "${_sg_l# }"
}

# Der Unit-Text. $1 Python des venv, $2 Gruppenliste (Leerzeichen).
# Pfade sind Zielpfade (ohne CHIMERA_ROOT), denn systemd liest sie am Ziel.
service_unit_text() {
	_su_py="$1"
	_su_gr="$2"
	cat <<EOF
# Von chimera-install angelegt (Schritt 98). Aenderungen gehen beim
# naechsten Installerlauf verloren -- eigene Werte in ein Drop-in:
#   systemctl edit $CHIMERA_DIENST
[Unit]
Description=Chimera -- ein Agent, der ein Gesicht macht
After=network-online.target
Wants=network-online.target
# Regel 10p, Punkt 4: hoechstens 5 Starts in 300 s, dann bleibt er aus.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=$CHIMERA_DIENSTNUTZER
Group=$CHIMERA_DIENSTNUTZER
EOF
	[ -n "$_su_gr" ] && printf 'SupplementaryGroups=%s\n' "$_su_gr"
	cat <<EOF
EnvironmentFile=/etc/chimera/.env
Environment=CHIMERA_HOME=/var/lib/chimera/daten
Environment=HOME=/var/lib/chimera/daten
Environment=LANG=C.UTF-8
Environment=PYTHONUNBUFFERED=1
StateDirectory=chimera/daten
StateDirectoryMode=0700
WorkingDirectory=/var/lib/chimera/daten
ExecStart=$_su_py -m chimera --dienst
Restart=on-failure
RestartSec=5
RestartPreventExitStatus=2
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
}

# Stand des Programms, den der laufende Dienst geladen hat. Aendert er
# sich (git pull), muss der Dienst neu starten -- sonst laeuft nach
# "git pull + Installerlauf" weiter der alte Code (Regel 10).
service_code_stand() {
	_sc_repo="$1"
	( cd "$_sc_repo" 2>/dev/null || exit 1
	  find src requirements.txt -type f ! -name '*.pyc' 2>/dev/null | sort |
	  while IFS= read -r _sc_f; do sha256sum "$_sc_f"; done | sha256sum |
	  cut -d' ' -f1 )
}

# Dienstnutzer sicherstellen. rc 0 ok, 2 nicht anlegbar.
service_nutzer() {
	_sn_u="$CHIMERA_DIENSTNUTZER"
	if id -u "$_sn_u" >/dev/null 2>&1; then
		if ! manifest_has nutzer "$_sn_u"; then
			# Gab es vor Chimera -- darf ein Rueckbau nie loeschen.
			info "Nutzer $_sn_u gab es schon -- wird uebernommen, nicht angelegt."
			manifest_record nutzer "$_sn_u" vorher_da
		else
			info "Dienstnutzer vorhanden: $_sn_u"
		fi
		return 0
	fi
	if is_dry_run; then
		info "[wuerde anlegen] Systemnutzer $_sn_u (ohne Anmeldung)"
		return 0
	fi
	have_cmd useradd || { err "useradd fehlt -- Dienstnutzer nicht anlegbar."; return 2; }
	_sn_shell=/usr/sbin/nologin
	[ -x "$(rootpath "$_sn_shell")" ] || _sn_shell=/bin/false
	useradd --system --user-group --no-create-home \
		--home-dir /var/lib/chimera/daten --shell "$_sn_shell" "$_sn_u" \
		>/dev/null 2>&1 || true
	# Am Ergebnis pruefen, nicht am Exitcode.
	if ! id -u "$_sn_u" >/dev/null 2>&1; then
		err "Dienstnutzer $_sn_u nicht angelegt (useradd)."
		return 2
	fi
	manifest_record nutzer "$_sn_u" neu
	info "Dienstnutzer angelegt: $_sn_u"
	return 0
}

# Kann der Dienstnutzer das Programm lesen? Die .pth zeigt ins Repo; liegt
# das unter /root (700), startet der Dienst nie. Das vorher sagen, nicht
# erst im Journal finden lassen. rc 0 lesbar/unpruefbar, 2 nicht lesbar.
service_lesbar() {
	_sl_repo="$1"
	if ! have_cmd runuser; then
		warn "runuser fehlt -- nicht pruefbar, ob $CHIMERA_DIENSTNUTZER das Repo lesen kann."
		return 0
	fi
	is_dry_run && ! id -u "$CHIMERA_DIENSTNUTZER" >/dev/null 2>&1 && return 0
	if runuser -u "$CHIMERA_DIENSTNUTZER" -- \
		test -r "$_sl_repo/src/chimera/__main__.py" >/dev/null 2>&1; then
		return 0
	fi
	err "Der Dienstnutzer $CHIMERA_DIENSTNUTZER kann das Programm nicht lesen:"
	err "  $_sl_repo/src/chimera/__main__.py"
	err "Das Repo liegt vermutlich in einem geschlossenen Verzeichnis"
	err "(z. B. /root). Repo nach /opt/chimera/repo klonen oder die"
	err "Verzeichnisrechte oeffnen, dann den Lauf wiederholen."
	return 2
}

# Der ganze Ablauf. $1 venv-Python (Zielpfad), $2 Repo.
# rc 0 Dienst laeuft nachweislich, 1 Befund, 2 Abbruch.
service_einrichten() {
	_se_py="$1"
	_se_repo="$2"
	_se_unit="$(service_unit_pfad)"
	_se_stand="$(service_stand_pfad)"

	have_cmd systemctl || { err "systemctl fehlt -- kein systemd, kein Dienst."; return 2; }

	log "Dienstnutzer"
	service_nutzer || return 2
	service_lesbar "$_se_repo" || return 2
	log ""

	log "Unit"
	_se_text="$(service_unit_text "$_se_py" "$(service_gruppen)")"
	_se_neu=0
	if [ -f "$_se_unit" ] && [ "$(cat "$_se_unit")" = "$_se_text" ]; then
		info "Unit unveraendert: $_se_unit"
	elif is_dry_run; then
		info "[wuerde schreiben] $_se_unit"
		_se_neu=1
	else
		mkdir -p "$(dirname "$_se_unit")" || { err "Unit-Verzeichnis fehlt."; return 2; }
		printf '%s\n' "$_se_text" | write_atomic "$_se_unit" || return 2
		manifest_has datei "$_se_unit" || manifest_record datei "$_se_unit" ""
		info "Unit geschrieben: $_se_unit"
		_se_neu=1
	fi

	_se_code="$(service_code_stand "$_se_repo")"
	_se_alt="$(cat "$_se_stand" 2>/dev/null || true)"

	if is_dry_run; then
		[ "$_se_neu" = 1 ] && info "[wuerde] systemctl daemon-reload"
		info "[wuerde] systemctl enable --now $CHIMERA_DIENST (bzw. restart)"
		return 0
	fi

	[ "$_se_neu" = 1 ] && systemctl daemon-reload

	if ! manifest_has dienst "$CHIMERA_DIENST"; then
		systemctl enable "$CHIMERA_DIENST" >/dev/null 2>&1 || {
			err "systemctl enable $CHIMERA_DIENST schlug fehl."; return 2; }
		manifest_record dienst "$CHIMERA_DIENST" aktiviert
	fi

	_se_aktiv="$(systemctl is-active "$CHIMERA_DIENST" 2>/dev/null || true)"
	if [ "$_se_aktiv" = active ] && [ "$_se_neu" = 0 ] && [ "$_se_code" = "$_se_alt" ]; then
		info "Dienst laeuft mit diesem Stand -- kein Neustart."
		_se_gestartet=0
	else
		if [ "$_se_aktiv" = active ]; then
			info "Neuer Stand -- Dienst wird neu gestartet."
		fi
		# reset-failed: Eine fruehere Schleife hat sonst das Startlimit
		# schon verbraucht, und der Start wird abgelehnt.
		systemctl reset-failed "$CHIMERA_DIENST" >/dev/null 2>&1 || true
		systemctl restart "$CHIMERA_DIENST" || {
			err "systemctl restart $CHIMERA_DIENST schlug fehl."
			err "  journalctl -u $CHIMERA_DIENST -n 30"
			return 1; }
		_se_gestartet=1
	fi
	log ""

	log "Nachweis"
	if [ "$_se_gestartet" = 1 ]; then
		info "warte ${CHIMERA_DIENST_WARTEN} s ..."
		sleep "$CHIMERA_DIENST_WARTEN"
	fi
	_se_aktiv="$(systemctl is-active "$CHIMERA_DIENST" 2>/dev/null || true)"
	_se_nr="$(systemctl show -p NRestarts --value "$CHIMERA_DIENST" 2>/dev/null || true)"
	if [ "$_se_aktiv" != active ]; then
		err "Dienst ist nicht aktiv (Zustand: ${_se_aktiv:-unbekannt})."
		err "  journalctl -u $CHIMERA_DIENST -n 30"
		return 1
	fi
	case "$_se_nr" in
		0) : ;;
		""|*[!0-9]*)
			warn "NRestarts nicht lesbar -- eine Neustartschleife ist nicht"
			warn "ausgeschlossen, nur nicht messbar." ;;
		*)
			err "Dienst aktiv, aber schon $_se_nr Mal neu gestartet -- Schleife."
			err "  journalctl -u $CHIMERA_DIENST -n 30"
			return 1 ;;
	esac

	# Stand erst nach dem Nachweis festhalten: Ein gescheiterter Start
	# soll beim naechsten Lauf erneut versucht werden.
	if [ "$_se_code" != "$_se_alt" ]; then
		printf '%s\n' "$_se_code" | write_atomic "$_se_stand" || \
			warn "Stand nicht festgehalten -- naechster Lauf startet neu."
		manifest_has datei "$_se_stand" || manifest_record datei "$_se_stand" ""
	fi
	info "aktiv, NRestarts=${_se_nr:-?}"
	return 0
}

# --- Rueckbau --------------------------------------------------------------
#
# Reihenfolge: stoppen, abschalten, Unit weg, daemon-reload, Nutzer weg.
# Den Nutzer zuletzt -- ein laufender Prozess unter einem geloeschten
# Nutzer haelt die UID fest, und userdel verweigert.
# Nutzerdaten (/var/lib/chimera/daten) bleiben: nur auf ausdrueckliche
# Anforderung (INSTALLER.md 6).
service_rueckbau() {
	_sr_befund=0
	if manifest_has dienst "$CHIMERA_DIENST"; then
		if is_dry_run; then
			info "[wuerde] systemctl disable --now $CHIMERA_DIENST"
		elif have_cmd systemctl; then
			systemctl disable --now "$CHIMERA_DIENST" >/dev/null 2>&1 || true
			if [ "$(systemctl is-active "$CHIMERA_DIENST" 2>/dev/null)" = active ]; then
				warn "Dienst laeuft noch: $CHIMERA_DIENST"; _sr_befund=1
			else
				info "gestoppt und abgeschaltet: $CHIMERA_DIENST"
			fi
		else
			warn "systemctl fehlt -- Dienst nicht abschaltbar."; _sr_befund=1
		fi
	fi

	_sr_f="${TMPDIR:-/tmp}/.chimera-rm-dienst.$$"
	manifest_list datei | while IFS='	' read -r _sr_p _sr_a; do
		case "$_sr_p" in
			*/systemd/system/"$CHIMERA_DIENST"|*/var/lib/chimera/dienst-stand)
				printf '%s\n' "$_sr_p" ;;
		esac
	done >"$_sr_f"
	_sr_unit_weg=0
	while IFS= read -r _sr_p; do
		[ -n "$_sr_p" ] || continue
		if is_dry_run; then info "[wuerde entfernen] $_sr_p"; continue; fi
		rm -f "$_sr_p"
		if [ -e "$_sr_p" ]; then warn "blieb stehen: $_sr_p"; _sr_befund=1
		else info "entfernt: $_sr_p"; _sr_unit_weg=1; fi
	done <"$_sr_f"
	rm -f "$_sr_f"
	if [ "$_sr_unit_weg" = 1 ] && have_cmd systemctl; then
		systemctl daemon-reload >/dev/null 2>&1 || true
	fi

	if manifest_has_exact nutzer "$CHIMERA_DIENSTNUTZER" neu; then
		if is_dry_run; then
			info "[wuerde entfernen] Nutzer $CHIMERA_DIENSTNUTZER"
		elif ! id -u "$CHIMERA_DIENSTNUTZER" >/dev/null 2>&1; then
			info "schon weg: Nutzer $CHIMERA_DIENSTNUTZER"
		elif have_cmd userdel; then
			userdel "$CHIMERA_DIENSTNUTZER" >/dev/null 2>&1 || true
			if id -u "$CHIMERA_DIENSTNUTZER" >/dev/null 2>&1; then
				warn "Nutzer blieb: $CHIMERA_DIENSTNUTZER"; _sr_befund=1
			else
				info "entfernt: Nutzer $CHIMERA_DIENSTNUTZER"
			fi
		else
			warn "userdel fehlt -- Nutzer $CHIMERA_DIENSTNUTZER bleibt."; _sr_befund=1
		fi
	elif manifest_has nutzer "$CHIMERA_DIENSTNUTZER"; then
		info "Nutzer $CHIMERA_DIENSTNUTZER bleibt: er war vor Chimera da."
	fi

	_sr_daten="$(rootpath /var/lib/chimera/daten)"
	[ -d "$_sr_daten" ] && info "Nutzerdaten bleiben: $_sr_daten (nur auf Anforderung loeschen)"
	return "$_sr_befund"
}
