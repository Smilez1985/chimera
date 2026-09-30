#!/bin/sh
# Chimera installer -- Netzzugriffe, die eine Unterbrechung ueberleben.
#
# Ein Pi Zero 2 W haengt am WLAN, oft am Rand der Reichweite. Ein Download
# von mehreren Megabyte ueberlebt das nicht immer -- und ein Installer, der
# deswegen in der Mitte abbricht, hinterlaesst ein halb eingerichtetes
# System. Das ist der schlechteste Zustand: schlimmer als gar nicht
# angefangen, weil niemand weiss, was schon da ist.
#
# Deshalb gilt hier: **Eine Unterbrechung ist eine Pause, kein Ende.**
# Faellt das Netz aus, wartet der Installer und sagt, dass er wartet. Er
# bricht erst ab, wenn eine Grenze erreicht ist, die vorher genannt wurde.
#
# Und er schweigt nicht. Ein stiller Wiederholungsversuch sieht von aussen
# aus wie ein haengender Prozess; wer davorsitzt, weiss nicht, ob er warten
# oder eingreifen soll (Regel 8a, Regel 10e).

# --- Erreichbarkeit -------------------------------------------------------
#
# ICMP taugt dafuer nicht: Viele Netze verwerfen es, manche Sandkaesten
# koennen es gar nicht erzeugen. Geprueft wird deshalb mit einer echten
# TCP-Verbindung zum Ziel, das gleich gebraucht wird -- das misst, was
# zaehlt, statt etwas Aehnliches.
#
# $1 Rechnername, $2 Port (Vorgabe 443), $3 Frist in Sekunden (Vorgabe 5)
network_reachable() {
	_ne_host="$1"
	_ne_port="${2:-443}"
	_ne_frist="${3:-5}"

	# curl zuerst, nicht nc.
	#
	# Grund: `nc` gibt es in mindestens drei Bauarten (BusyBox,
	# netcat-openbsd, netcat-traditional), und sie behandeln `-z` und `-w`
	# unterschiedlich -- manche kennen `-z` gar nicht und warten dann auf
	# Eingabe, statt zu antworten. Das faellt nicht als Fehler auf: Die
	# Pruefung meldet "nicht erreichbar", die Warteschleife beginnt, und
	# von aussen sieht es aus wie ein Haenger.
	#
	# Genau das ist auf einem GitHub-Runner passiert, wo `sh` BusyBox war:
	# Lokal lief derselbe Test in 25 Sekunden, dort lief er in die Grenze.
	#
	# curl ist in dieser Hinsicht berechenbar und ueberall gleich.
	if have_cmd curl; then
		curl -s -o /dev/null --max-time "$_ne_frist" \
			--connect-timeout "$_ne_frist" \
			"https://$_ne_host:$_ne_port" >/dev/null 2>&1 && return 0
		# Auch ein HTTP-Fehler beweist, dass jemand geantwortet hat --
		# gefragt ist die Erreichbarkeit, nicht der Inhalt.
		case "$?" in
			0|22|52|56) return 0 ;;
		esac
		return 1
	fi
	if have_cmd nc; then
		nc -z -w "$_ne_frist" "$_ne_host" "$_ne_port" >/dev/null 2>&1
		return $?
	fi
	if have_cmd wget; then
		wget -q -O /dev/null --timeout="$_ne_frist" --tries=1 \
			"https://$_ne_host" >/dev/null 2>&1
		return $?
	fi

	# Kein Werkzeug da: Das ist KEIN "Netz ist weg", sondern "ich kann es
	# nicht sehen". Der Unterschied entscheidet, ob gewartet oder
	# weitergemacht wird (Regel 10j).
	warn "Kein nc, curl oder wget -- Erreichbarkeit nicht pruefbar."
	return 2
}

# Warten, bis ein Ziel wieder antwortet.
#
# Das ist die Schleife, die einen Download pausieren laesst statt ihn
# abzubrechen. Sie meldet den Ausfall beim ersten Mal, dann in groesser
# werdenden Abstaenden -- eine Meldung je Sekunde waere eine Protokollflut,
# gar keine waere Schweigen.
#
# $1 Rechnername, $2 Port, $3 Grenze in Sekunden (0 = ohne Grenze)
network_wait() {
	_nw_host="$1"
	_nw_port="${2:-443}"
	_nw_grenze="${3:-${CHIMERA_NETWORK_LIMIT:-600}}"

	network_reachable "$_nw_host" "$_nw_port" && return 0

	warn "Netz weg: $_nw_host:$_nw_port antwortet nicht."
	warn "Es wird gewartet, nicht abgebrochen. Grenze: ${_nw_grenze}s"
	[ "$_nw_grenze" = 0 ] && warn "  (ohne Grenze -- mit Strg-C beenden)"

	_nw_wartet=0
	_nw_pause=2
	_nw_meldung=15

	while :; do
		sleep "$_nw_pause"
		_nw_wartet=$((_nw_wartet + _nw_pause))

		if network_reachable "$_nw_host" "$_nw_port"; then
			log "Netz wieder da nach ${_nw_wartet}s -- es geht weiter."
			return 0
		fi

		# Abstand langsam vergroessern, bis 30s. Haeufig pruefen ist am
		# Anfang richtig (kurze Stoerung), spaeter nutzlos.
		[ "$_nw_pause" -lt 30 ] && _nw_pause=$((_nw_pause * 2))
		[ "$_nw_pause" -gt 30 ] && _nw_pause=30

		if [ "$_nw_wartet" -ge "$_nw_meldung" ]; then
			info "warte weiter ... ${_nw_wartet}s ohne Netz"
			_nw_meldung=$((_nw_meldung * 2))
		fi

		if [ "$_nw_grenze" != 0 ] && [ "$_nw_wartet" -ge "$_nw_grenze" ]; then
			err "Nach ${_nw_wartet}s immer noch kein Netz. Aufgegeben."
			err "Der Lauf laesst sich wiederholen -- Fertiges bleibt fertig."
			return 1
		fi
	done
}

# --- Herunterladen --------------------------------------------------------
#
# $1 Adresse, $2 Zieldatei, $3 erwartete SHA256 (optional)
#
# Eigenschaften, die hier nicht verhandelbar sind:
#
#  * **Fortsetzen statt neu beginnen.** curl -C - und wget -c setzen an der
#    Abbruchstelle an. Auf einem Zero 2 W am WLAN-Rand ist das der
#    Unterschied zwischen "geht irgendwann durch" und "geht nie durch".
#  * **Pause statt Abbruch.** Zwischen den Versuchen wird auf das Netz
#    gewartet (network_wait), nicht blind wiederholt.
#  * **In eine Nebendatei schreiben, dann umbenennen.** Sonst liegt am Ziel
#    ein halbes Archiv, das beim naechsten Lauf fuer fertig gehalten wird.
#  * **Das Ergebnis pruefen, nicht den Exitcode.** Eine leere Datei mit
#    Exitcode 0 ist ein Fehlschlag (Regel 10j).
network_fetch() {
	_nl_url="$1"
	_nl_ziel="$2"
	_nl_summe="${3:-}"
	_nl_versuche="${CHIMERA_DL_VERSUCHE:-20}"

	_nl_host="$(printf '%s' "$_nl_url" | sed -e 's|^[a-z]*://||' -e 's|/.*||' -e 's|:.*||')"
	case "$_nl_url" in
		https://*) _nl_port=443 ;;
		http://*)  _nl_port=80 ;;
		*)         _nl_port=443 ;;
	esac

	if is_dry_run; then
		info "[wuerde laden] $_nl_url -> $_nl_ziel"
		return 0
	fi

	# Schon da und stimmig? Dann nichts tun -- der Installer ist
	# idempotent, ein zweiter Lauf laedt nicht erneut.
	if [ -s "$_nl_ziel" ] && [ -n "$_nl_summe" ]; then
		if network_checksum_ok "$_nl_ziel" "$_nl_summe"; then
			info "Schon vorhanden und geprueft: $(basename "$_nl_ziel")"
			return 0
		fi
		warn "Vorhandene Datei passt nicht zur Pruefsumme -- wird neu geladen."
		rm -f "$_nl_ziel"
	fi

	mkdir -p "$(dirname "$_nl_ziel")" || {
		err "Zielverzeichnis nicht anlegbar: $(dirname "$_nl_ziel")"
		return 1
	}

	_nl_teil="$_nl_ziel.teil"
	_nl_n=0

	while [ "$_nl_n" -lt "$_nl_versuche" ]; do
		_nl_n=$((_nl_n + 1))

		network_wait "$_nl_host" "$_nl_port" || {
			err "Kein Netz -- Download abgebrochen: $_nl_url"
			return 1
		}

		[ "$_nl_n" -gt 1 ] && info "Versuch $_nl_n von $_nl_versuche" \
			&& [ -s "$_nl_teil" ] \
			&& info "  setze bei $(wc -c <"$_nl_teil") Byte fort"

		if have_cmd curl; then
			curl -fL -C - --connect-timeout 20 --speed-time 60 --speed-limit 512 \
				-o "$_nl_teil" "$_nl_url" && _nl_rc=0 || _nl_rc=$?
		elif have_cmd wget; then
			wget -c -q --show-progress --timeout=60 --tries=1 \
				-O "$_nl_teil" "$_nl_url" && _nl_rc=0 || _nl_rc=$?
		else
			err "Weder curl noch wget vorhanden."
			return 1
		fi

		if [ "$_nl_rc" = 0 ] && [ -s "$_nl_teil" ]; then
			if [ -n "$_nl_summe" ] && ! network_checksum_ok "$_nl_teil" "$_nl_summe"; then
				err "Pruefsumme stimmt nicht: $(basename "$_nl_ziel")"
				err "  erwartet: $_nl_summe"
				err "  bekommen: $(network_checksum "$_nl_teil")"
				rm -f "$_nl_teil"
				return 1
			fi
			mv "$_nl_teil" "$_nl_ziel" || {
				err "Umbenennen fehlgeschlagen: $_nl_teil"
				return 1
			}
			info "Geladen: $(basename "$_nl_ziel") ($(wc -c <"$_nl_ziel") Byte)"
			return 0
		fi

		# Hier NICHT schweigen. Ein stiller Wiederholungsversuch sieht von
		# aussen aus wie ein Haenger.
		warn "Download unterbrochen (Exitcode $_nl_rc)."
		[ -s "$_nl_teil" ] && warn "  $(wc -c <"$_nl_teil") Byte sind da, es wird fortgesetzt."
		sleep 3
	done

	err "Nach $_nl_versuche Versuchen nicht vollstaendig: $_nl_url"
	[ -s "$_nl_teil" ] && err "  Angefangenes bleibt liegen: $_nl_teil"
	return 1
}

# --- Pruefsummen ----------------------------------------------------------
network_checksum() {
	if have_cmd sha256sum; then sha256sum "$1" 2>/dev/null | awk '{print $1}'
	elif have_cmd shasum; then shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
	else echo ""; fi
}

network_checksum_ok() {
	_ns_ist="$(network_checksum "$1")"
	if [ -z "$_ns_ist" ]; then
		# Kein Werkzeug: nicht pruefbar ist nicht dasselbe wie falsch.
		# Aber es wird gesagt, statt es zu verschweigen (Regel 10j).
		warn "Keine Pruefsumme berechenbar (sha256sum fehlt) -- ungeprueft."
		return 0
	fi
	[ "$_ns_ist" = "$2" ]
}

# --- Git, mit denselben Eigenschaften -------------------------------------
#
# $1 Adresse, $2 Zielverzeichnis, $3 Zweig (optional)
network_git() {
	_ng_url="$1"
	_ng_ziel="$2"
	_ng_zweig="${3:-}"
	_ng_versuche="${CHIMERA_DL_VERSUCHE:-20}"

	_ng_host="$(printf '%s' "$_ng_url" | sed -e 's|^[a-z]*://||' -e 's|/.*||' -e 's|:.*||')"

	if is_dry_run; then
		info "[wuerde holen] $_ng_url -> $_ng_ziel"
		return 0
	fi

	have_cmd git || { err "git fehlt."; return 1; }

	_ng_n=0
	while [ "$_ng_n" -lt "$_ng_versuche" ]; do
		_ng_n=$((_ng_n + 1))

		network_wait "$_ng_host" 443 || {
			err "Kein Netz -- Abruf abgebrochen: $_ng_url"
			return 1
		}

		if [ -d "$_ng_ziel/.git" ]; then
			# Schon da: aktualisieren statt neu holen (idempotent).
			if (cd "$_ng_ziel" && git fetch -q --depth 1 origin && \
			    git reset -q --hard "origin/$(git rev-parse --abbrev-ref HEAD)"); then
				info "Aktualisiert: $_ng_ziel"
				return 0
			fi
		else
			if git clone -q --depth 1 ${_ng_zweig:+--branch "$_ng_zweig"} \
			      "$_ng_url" "$_ng_ziel"; then
				info "Geholt: $_ng_ziel"
				return 0
			fi
			# Halb geklont? Weg damit, sonst haelt der naechste Lauf es
			# fuer fertig.
			[ -d "$_ng_ziel" ] && [ ! -d "$_ng_ziel/.git" ] && rm -rf "$_ng_ziel"
		fi

		warn "Abruf unterbrochen (Versuch $_ng_n von $_ng_versuche)."
		sleep 3
	done

	err "Nach $_ng_versuche Versuchen nicht geholt: $_ng_url"
	return 1
}

# --- Pakete ---------------------------------------------------------------
#
# apt bricht bei Netzausfall ebenfalls ab. Gleiche Behandlung.
network_apt() {
	if is_dry_run; then
		info "[wuerde installieren] $*"
		return 0
	fi
	have_cmd apt-get || { err "apt-get fehlt."; return 1; }

	_na_n=0
	while [ "$_na_n" -lt "${CHIMERA_DL_VERSUCHE:-20}" ]; do
		_na_n=$((_na_n + 1))
		network_wait "deb.debian.org" 80 || {
			err "Kein Netz -- Paketinstallation abgebrochen."
			return 1
		}
		if DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@"; then
			info "Installiert: $*"
			return 0
		fi
		warn "Paketinstallation unterbrochen (Versuch $_na_n)."
		sleep 3
	done
	err "Pakete nicht installierbar: $*"
	return 1
}
