#!/bin/sh
# Nachsehen, was tatsaechlich am System ist.
#
# Das Manifest sagt, was Chimera GETAN hat. Diese Bibliothek sagt, was
# JETZT da ist. Beides ist noetig, und beides beantwortet eine andere
# Frage:
#
#   Manifest:  "ich habe python3-pil neu installiert"
#   Nachsehen: "python3-pil ist installiert"
#
# Fehlt das Manifest, wird nicht abgebrochen und nicht geraten -- es wird
# nachgesehen. Was dabei eindeutig Chimera gehoert (eigene Pfade, eigene
# Dienstnamen), wird entfernt. Was mehrdeutig ist, wird GENANNT und dem
# Nutzer zur Entscheidung gegeben.
#
# Die Grenze des Nachsehens, ehrlich benannt: Ob ein Paket VOR Chimera
# schon installiert war, steht nirgends im System. Das ist Historie, und
# die kennt nur das Manifest. `dpkg-query` sagt "installiert", nicht
# "von wem". Wer ohne Manifest Pakete entfernt, entfernt auf Verdacht --
# deshalb werden sie dort nur berichtet.

# --- Was gehoert eindeutig Chimera? --------------------------------------
#
# Eigene Pfade und eigene Namen. Hier ist kein Zweifel moeglich: Ein
# Verzeichnis /opt/chimera hat niemand anders angelegt.
chimera_own_paths() {
	cat <<EOF
${CHIMERA_ROOT}/opt/chimera
${CHIMERA_ROOT}/var/lib/chimera
${CHIMERA_ROOT}/etc/chimera
${CHIMERA_ROOT}/usr/local/bin/chimera
${CHIMERA_ROOT}/usr/local/bin/chimera-install
${CHIMERA_ROOT}/usr/local/bin/chimera-uninstall
EOF
}

chimera_own_services() {
	cat <<'EOF'
chimera.service
chimera-face.service
EOF
}

# --- Einzelne Feststellungen ---------------------------------------------
#
# Jede Funktion gibt drei Zustaende zurueck, nie zwei:
#   0 = ist da
#   1 = ist nicht da
#   2 = kann nicht nachsehen
#
# Der dritte ist der wichtige. "Ich kann nicht sehen" ist keine
# Abwesenheit, und wer beides gleich behandelt, meldet Aufgeraeumtheit,
# wo er blind ist (Architekturregel 10j).

discover_package() {
	if command -v dpkg-query >/dev/null 2>&1; then
		case "$(dpkg-query -W -f='${db:Status-Status}' "$1" 2>/dev/null)" in
			installed) return 0 ;;
			*) return 1 ;;
		esac
	elif command -v apk >/dev/null 2>&1; then
		apk info -e "$1" >/dev/null 2>&1 && return 0
		return 1
	fi
	return 2
}

discover_path() {
	[ -e "$1" ] && return 0
	return 1
}

discover_service() {
	command -v systemctl >/dev/null 2>&1 || return 2
	# `is-enabled` kennt mehr Zustaende als ja/nein: enabled, disabled,
	# static, masked, not-found. Nur "not-found" heisst wirklich "gibt es
	# nicht" -- alles andere ist eine vorhandene Einheit.
	_ds_out="$(systemctl is-enabled "$1" 2>&1)"
	case "$_ds_out" in
		*"not-found"*|*"No such file"*) return 1 ;;
		"") return 2 ;;
		*) return 0 ;;
	esac
}

discover_group_member() {
	# $1 Gruppe, $2 Nutzer
	command -v id >/dev/null 2>&1 || return 2
	id -nG "$2" 2>/dev/null | tr ' ' '\n' | grep -qx "$1" && return 0
	return 1
}

# Eine von uns stammende Zeile in einer Fremddatei erkennen.
#
# OHNE Manifest ist das nicht eindeutig entscheidbar: `dtparam=spi=on`
# kann von Chimera oder vom Nutzer sein. Darum gibt diese Funktion nur
# Auskunft ueber die ANWESENHEIT, nie ueber die Herkunft. Die Herkunft
# steht im Manifest oder nirgends.
discover_line() {
	[ -f "$1" ] || return 2
	grep -qxF "$2" "$1" && return 0
	return 1
}

# --- Bericht ueber den Istzustand ----------------------------------------
#
# Wird ohne Manifest gebraucht: Statt abzubrechen wird gesagt, was da ist.
# Der Nutzer bekommt damit die Fakten, die das Manifest gehabt haette --
# minus der Herkunft, und das wird auch so gesagt.
discover_report() {
	log "Was jetzt am System ist"

	_dr_gefunden=0

	for _dr_p in $(chimera_own_paths); do
		if discover_path "$_dr_p"; then
			info "vorhanden: $_dr_p"
			_dr_gefunden=$((_dr_gefunden + 1))
		fi
	done

	for _dr_s in $(chimera_own_services); do
		# Der Aufruf MUSS in einer Bedingung stehen. Steht er nackt da,
		# beendet `set -e` den Lauf, sobald die Funktion etwas anderes als
		# 0 zurueckgibt -- und 1 ("nicht da") wie 2 ("kann nicht sehen")
		# sind hier normale Auskuenfte, keine Fehler.
		#
		# Genau daran ist der erste Lauf gestorben: kein systemctl in der
		# Testumgebung, discover_service gab 2, der Lauf brach mit
		# Exitcode 2 ab -- ohne Meldung, weil `set -e` nichts sagt.
		_dr_rc=0
		discover_service "$_dr_s" || _dr_rc=$?
		case "$_dr_rc" in
			0) info "Dienst eingerichtet: $_dr_s"
			   _dr_gefunden=$((_dr_gefunden + 1)) ;;
			2) warn "Dienst $_dr_s: kann nicht nachsehen (kein systemctl)" ;;
		esac
	done

	if [ "$_dr_gefunden" -eq 0 ]; then
		info "Nichts gefunden, was eindeutig Chimera gehoert."
	fi

	# Die Zahl steht in DISCOVER_FOUND, nicht in einer Datei. Hier stand
	# vorher ein `printf > "${VAR:-/dev/null}"`, das unter `set -e` den
	# ganzen Lauf mit Exitcode 2 beendete -- ohne Meldung, weil die
	# Umleitung selbst scheiterte. Eine Nebensache, die den Hauptlauf
	# killt, ist immer ein Fehler.
	DISCOVER_FOUND="$_dr_gefunden"
	return 0
}
