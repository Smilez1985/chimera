#!/bin/sh
# Chimera installer -- Mojo: Meldeunit, Zeitgeber, Drop-ins (DESIGN, Regel "Mojo").
#
# Mojo laeuft als eigene Unit, nicht im Dienst des Agenten: Das Journal ist nur
# fuer die Gruppe systemd-journal lesbar (am Pi gemessen), und der Agent darf
# nichts davon aendern koennen (Regel "Agent ist ein eigener Nutzer").
#
# Gemessen am Pi (systemd 257): OnFailure= feuert bei JEDEM Fehlschlag, nicht
# erst nach der Startgrenze. Die Meldeunit trennt darum Zwischenfehler (der
# Dienst steht noch auf activating oder wird neu gestartet) von der Aufgabe
# (failed) und meldet nur die Aufgabe laut.
#
# Wird von steps/27-mojo.sh geladen; prueft sich in tests/test-mojo.sh ohne
# systemd (systemctl, id, getent stehen im Test als Funktionen bereit).

: "${CHIMERA_MOJO_MELDUNG:=chimera-mojo@.service}"
: "${CHIMERA_MOJO_LAUF:=chimera-mojo.service}"
: "${CHIMERA_MOJO_ZEIT:=chimera-mojo.timer}"
: "${CHIMERA_MOJO_GRUPPE:=systemd-journal}"
# Die Dienste, die bei Fehlschlag melden.
: "${CHIMERA_MOJO_DIENSTE:=chimera.service chimera-tor.service chimera-hardware.service}"

mojo_programm() { printf '%s\n' "$CHIMERA_OPT/bin/chimera-tor"; }

# Lauf: einmal pruefen und sanft reparieren. Laeuft als root (liest das Journal,
# startet Units), hat sonst keine Rechte (siehe Haertung).
mojo_lauf_text() {
	cat <<EOF
# Von chimera-install angelegt (Schritt 27). Aenderungen gehen beim
# naechsten Installerlauf verloren -- eigene Werte in ein Drop-in.
[Unit]
Description=Chimera -- Mojo: Dienste pruefen, Ursache nennen, sanft reparieren
After=local-fs.target
ConditionPathExists=$(mojo_programm)

[Service]
Type=oneshot
ExecStart=$(mojo_programm) --mojo --fix --datei $CHIMERA_STATE/mojo-letzter.json
# Laut: ein Befund ab Fehler laesst die Unit scheitern und erscheint damit in
# systemctl --failed und im Journal (Exitcode 2). Warnungen (1) gelten als Erfolg.
SuccessExitStatus=1
SupplementaryGroups=$CHIMERA_MOJO_GRUPPE
Environment=CHIMERA_STATE_DIR=$CHIMERA_STATE
# Wo das Protokoll auf der Karte landet: Mojo prueft, ob dort geschrieben werden kann.
Environment=CHIMERA_LOG_KARTE=$CHIMERA_LOGS_PRODUCTIVE
Environment=CHIMERA_REQUIREMENTS=$CHIMERA_SOURCE/requirements.txt
# Reicht fuer das Nachladen von Python-Paketen (Schritt 50: Netz, pip, bis zu 10 Minuten).
TimeoutStartSec=900
NoNewPrivileges=yes
PrivateTmp=yes
# Nicht yes: Mojo prueft, ob das Protokoll auf der Karte (unter /home) beschreibbar
# ist. Ist /home versteckt, sieht die Unit den Ordner gar nicht und meldete einen
# falschen Alarm (am Pi gemessen: "No such file or directory"). read-only plus
# ein einziger beschreibbarer Pfad genuegt.
ProtectHome=read-only
ProtectSystem=strict
# Das "-" vor dem Pfad: fehlt der Ordner, startet die Unit trotzdem (Mojo meldet es dann).
ReadWritePaths=$CHIMERA_STATE -$CHIMERA_LOGS_PRODUCTIVE
EOF
}

# Meldeunit (Vorlage): %i ist der gescheiterte Dienst. Zwischenfehler werden nur
# protokolliert, die Aufgabe laeuft in den Mojo-Lauf und wird laut.
mojo_meldung_text() {
	cat <<EOF
# Von chimera-install angelegt (Schritt 27).
[Unit]
Description=Chimera -- Meldung: %i ist gescheitert
# Eine Meldung ist keine Aufgabe, die selbst scheitern darf, ohne dass man es sieht.

[Service]
Type=oneshot
SupplementaryGroups=$CHIMERA_MOJO_GRUPPE
# Zwischenfehler (Neustart steht aus): nur protokollieren. Aufgabe (failed):
# Mojo laufen lassen -- Ursache nennen, sanft reparieren, nachpruefen, laut melden.
ExecStart=/bin/sh -c 'z=\$(systemctl show "%i" -p ActiveState --value); \\
  if [ "\$z" = failed ]; then \\
    echo "Mojo: %i ist aufgegeben (Ergebnis \$MONITOR_SERVICE_RESULT, Status \$MONITOR_EXIT_STATUS)" >&2; \\
    exec systemctl start --no-block $CHIMERA_MOJO_LAUF; \\
  else \\
    echo "Mojo: %i Zwischenfehler (Zustand \$z, Ergebnis \$MONITOR_SERVICE_RESULT, Status \$MONITOR_EXIT_STATUS), Neustart steht aus"; \\
  fi'
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
EOF
}

# Zeitgeber: nach dem Boot und stuendlich. Ein Dienst, der nie scheitert, aber
# still falsch laeuft (Socket aus), loest kein OnFailure= aus.
mojo_zeit_text() {
	cat <<EOF
# Von chimera-install angelegt (Schritt 27).
[Unit]
Description=Chimera -- Mojo: regelmaessig pruefen

[Timer]
OnBootSec=3min
OnUnitActiveSec=1h
RandomizedDelaySec=30
Unit=$CHIMERA_MOJO_LAUF

[Install]
WantedBy=timers.target
EOF
}

# Drop-in je Dienst: OnFailure= auf die Meldeunit, mit dem Namen des Dienstes.
# %N, nicht %n: am Pi gemessen haengt %n ein zweites ".service" an
# (der Dienstname mit doppelter Endung), den die Meldeunit nie als Dienst
# erkennt; %N liefert den Namen ohne Endung.
mojo_dropin_text() {
	cat <<EOF
# Von chimera-install angelegt (Schritt 27).
[Unit]
OnFailure=chimera-mojo@%N.service
EOF
}

mojo_dropin_pfad() { printf '%s/%s.d/10-mojo.conf\n' "$1" "$2"; }

# Der Ablauf. rc 0 ok, 1 Befund (z. B. Binary fehlt), 2 Abbruch.
mojo_einrichten() {
	_mo_prog="$(rootpath "$(mojo_programm)")"
	_mo_dir="$(dirname "$(service_unit_pfad)")"

	have_cmd systemctl || { err "systemctl fehlt -- kein systemd, kein Mojo."; return 2; }
	if ! is_dry_run && [ ! -x "$_mo_prog" ]; then
		warn "$(mojo_programm) fehlt -- Schritt 55 hat kein Binary abgelegt."
		warn "Mojo wird nicht eingerichtet; die Dienste laufen ohne."
		return 1
	fi
	if ! is_dry_run && ! getent group "$CHIMERA_MOJO_GRUPPE" >/dev/null 2>&1; then
		err "Gruppe $CHIMERA_MOJO_GRUPPE fehlt -- ohne sie kann Mojo das Journal nicht lesen."
		return 2
	fi

	log "Units"
	_sd_neu=0
	service_datei "$_mo_dir/$CHIMERA_MOJO_LAUF" "$(mojo_lauf_text)" || return 2
	service_datei "$_mo_dir/$CHIMERA_MOJO_MELDUNG" "$(mojo_meldung_text)" || return 2
	service_datei "$_mo_dir/$CHIMERA_MOJO_ZEIT" "$(mojo_zeit_text)" || return 2
	for _mo_d in $CHIMERA_MOJO_DIENSTE; do
		service_datei "$(mojo_dropin_pfad "$_mo_dir" "$_mo_d")" "$(mojo_dropin_text)" || return 2
	done
	_mo_neu=$_sd_neu

	if is_dry_run; then
		info "[wuerde] systemctl daemon-reload"
		info "[wuerde] systemctl enable --now $CHIMERA_MOJO_ZEIT"
		return 0
	fi
	[ "$_mo_neu" = 1 ] && systemctl daemon-reload

	# Zustand zaehlt, nicht das Manifest (wie beim Gateway): ein von Hand
	# abgeschalteter Zeitgeber wird wieder eingeschaltet.
	if ! manifest_has dienst "$CHIMERA_MOJO_ZEIT" || \
	   ! systemctl is-enabled --quiet "$CHIMERA_MOJO_ZEIT" 2>/dev/null || \
	   ! systemctl is-active --quiet "$CHIMERA_MOJO_ZEIT" 2>/dev/null; then
		systemctl enable --now "$CHIMERA_MOJO_ZEIT" >/dev/null 2>&1 || {
			err "systemctl enable --now $CHIMERA_MOJO_ZEIT schlug fehl."; return 2; }
		manifest_has dienst "$CHIMERA_MOJO_ZEIT" || manifest_record dienst "$CHIMERA_MOJO_ZEIT" aktiviert
	fi

	# Nachweis (Regel "Wer prueft, muss etwas sehen koennen"): Die Drop-ins muessen
	# wirken. systemd sagt es selbst, nicht nur die Datei auf der Platte.
	_mo_bad=0
	for _mo_d in $CHIMERA_MOJO_DIENSTE; do
		systemctl cat "$_mo_d" >/dev/null 2>&1 || continue   # Dienst gibt es nicht (z. B. ohne Hardware-Unit)
		_mo_of="$(systemctl show "$_mo_d" -p OnFailure --value 2>/dev/null)"
		case "$_mo_of" in
			*chimera-mojo@*) info "OnFailure wirkt: $_mo_d -> $_mo_of" ;;
			*) warn "OnFailure wirkt NICHT bei $_mo_d (systemd meldet: '${_mo_of:-leer}')"; _mo_bad=1 ;;
		esac
	done
	systemctl is-active --quiet "$CHIMERA_MOJO_ZEIT" 2>/dev/null || { warn "Zeitgeber $CHIMERA_MOJO_ZEIT ist nicht aktiv."; _mo_bad=1; }
	[ "$_mo_bad" = 0 ] || return 1
	return 0
}

mojo_rueckbau() {
	_mr_befund=0
	if manifest_has dienst "$CHIMERA_MOJO_ZEIT"; then
		if is_dry_run; then
			info "[wuerde] systemctl disable --now $CHIMERA_MOJO_ZEIT"
		elif have_cmd systemctl; then
			systemctl disable --now "$CHIMERA_MOJO_ZEIT" >/dev/null 2>&1 || true
			if [ "$(systemctl is-active "$CHIMERA_MOJO_ZEIT" 2>/dev/null)" = active ]; then
				warn "laeuft noch: $CHIMERA_MOJO_ZEIT"; _mr_befund=1
			else
				info "gestoppt und abgeschaltet: $CHIMERA_MOJO_ZEIT"
			fi
		else
			warn "systemctl fehlt -- $CHIMERA_MOJO_ZEIT nicht abschaltbar."; _mr_befund=1
		fi
	fi
	_mr_f="${TMPDIR:-/tmp}/.chimera-rm-mojo.$$"
	manifest_list_von datei 27-mojo | cut -f1 >"$_mr_f"
	_mr_weg=0
	while IFS= read -r _mr_p; do
		[ -n "$_mr_p" ] || continue
		if is_dry_run; then info "[wuerde entfernen] $_mr_p"; continue; fi
		rm -f "$_mr_p"
		if [ -e "$_mr_p" ]; then warn "blieb stehen: $_mr_p"; _mr_befund=1
		else info "entfernt: $_mr_p"; _mr_weg=1; fi
		# Ein leeres Drop-in-Verzeichnis gehoert uns dann auch nicht mehr.
		rmdir "$(dirname "$_mr_p")" 2>/dev/null || true
	done <"$_mr_f"
	rm -f "$_mr_f"
	if [ "$_mr_weg" = 1 ] && have_cmd systemctl; then
		systemctl daemon-reload >/dev/null 2>&1 || true
	fi
	return "$_mr_befund"
}
