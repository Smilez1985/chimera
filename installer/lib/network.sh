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
		# Schema nach Port. Vorher stand hier immer https -- gegen
		# deb.debian.org:80 scheitert dann der TLS-Handshake (curl rc 35),
		# und der Installer wartete am chimera-pi (11.10.2026) 600 s auf ein
		# Netz, das die ganze Zeit da war.
		case "$_ne_port" in
			80|8080) _ne_url="http://$_ne_host:$_ne_port" ;;
			*)       _ne_url="https://$_ne_host:$_ne_port" ;;
		esac
		curl -s -o /dev/null --max-time "$_ne_frist" \
			--connect-timeout "$_ne_frist" \
			"$_ne_url" >/dev/null 2>&1 && return 0
		# Jede Antwort der Gegenstelle beweist Erreichbarkeit -- gefragt ist
		# nicht der Inhalt: HTTP-Fehler (22), leere Antwort (52), Abbruch
		# beim Empfang (56), und ebenso ein gescheiterter TLS-Handshake (35)
		# oder ein Zertifikatsfehler (60): Dafuer musste jemand antworten.
		# Nicht dabei: 6 (Name), 7 (Verbindung), 28 (Frist) -- das ist "weg".
		case "$?" in
			0|22|35|52|56|60) return 0 ;;
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
# Ist ueberhaupt Netz da? TCP, nicht ICMP: ICMP ist in der Sandbox gesperrt
# und auf manchen Netzen gefiltert. Ein offener TCP-Port ist die ehrlichere
# Aussage (Vorbild rag4ll bg-pull-models.py).
: "${CHIMERA_NETZ_PROBE:=8.8.8.8:53 1.1.1.1:443}"

network_erreichbar() {
	# Leere Probekliste heisst NICHT "Netz weg", sondern "ich kann es nicht
	# sehen" (Regel 10j). Das brauchen hermetische Testlaeufe: Sie setzen
	# CHIMERA_NETZ_PROBE leer, damit die Warteschleife nicht auf ein Netz
	# wartet, das sie absichtlich nicht benutzt.
	[ -n "${CHIMERA_NETZ_PROBE:-}" ] || return 2
	for _ne_ziel in $CHIMERA_NETZ_PROBE; do
		_ne_host="${_ne_ziel%%:*}"
		_ne_port="${_ne_ziel##*:}"
		# network_reachable statt network_wait: Die Probe soll leise sein und
		# nicht selbst minutenlang warten.
		network_reachable "$_ne_host" "$_ne_port" && return 0
	done
	return 1
}

# Warten, bis ueberhaupt Netz da ist.
#
# Die Pause-Schleife fuer Werkzeuge, die ihren Abruf selbst machen (pip):
# Fehlt das Netz, wird gewartet statt abgebrochen; kehrt es zurueck, geht es
# weiter. Dasselbe Muster wie network_fetch, nur ohne eigene Uebertragung --
# deshalb dieselbe Meldepolitik: erste Meldung sofort, dann in wachsenden
# Abstaenden, Grenze wie CHIMERA_NETWORK_LIMIT.
#
# $1 Grenze in Sekunden (0 = ohne Grenze)
netz_warten_erreichbar() {
	_nwe_grenze="${1:-${CHIMERA_NETWORK_LIMIT:-600}}"

	network_erreichbar || _nwe_rc=$?
	_nwe_rc="${_nwe_rc:-0}"
	case "$_nwe_rc" in
		0) return 0 ;;
		2) # Nicht pruefbar (keine Probe gesetzt): NICHT warten -- sonst
		   # haengt ein hermetischer Lauf an einem Netz, das er nicht braucht.
		   warn "Erreichbarkeit nicht pruefbar (CHIMERA_NETZ_PROBE leer) -- kein Warten."
		   return 0 ;;
	esac

	warn "Kein Netz (Probe: $CHIMERA_NETZ_PROBE)."
	warn "Es wird gewartet, nicht abgebrochen. Grenze: ${_nwe_grenze}s"

	_nwe_wartet=0
	_nwe_pause=2
	_nwe_meldung=15

	while :; do
		sleep "$_nwe_pause"
		_nwe_wartet=$((_nwe_wartet + _nwe_pause))

		if network_erreichbar; then
			log "Netz wieder da nach ${_nwe_wartet}s -- es geht weiter."
			return 0
		fi

		[ "$_nwe_pause" -lt 30 ] && _nwe_pause=$((_nwe_pause * 2))
		[ "$_nwe_pause" -gt 30 ] && _nwe_pause=30

		if [ "$_nwe_wartet" -ge "$_nwe_meldung" ]; then
			info "warte weiter ... ${_nwe_wartet}s ohne Netz"
			_nwe_meldung=$((_nwe_meldung * 2))
		fi

		if [ "$_nwe_grenze" != 0 ] && [ "$_nwe_wartet" -ge "$_nwe_grenze" ]; then
			err "Nach ${_nwe_wartet}s immer noch kein Netz. Aufgegeben."
			err "Der Lauf laesst sich wiederholen -- Fertiges bleibt fertig."
			return 1
		fi
	done
}

# Mojo um eine Netz-Reparatur bitten: Es prueft und repariert, was es kennt
# (Dienste, Sockets, Karte, Speicher -- und seit 3.11. auch das Netz).
# Kein stilles Scheitern: Was Mojo nicht konnte, wird gemeldet.
# WLAN neu starten -- die Reihenfolge ist die der Wahrscheinlichkeit: erst
# sanft (Neuverbinden), dann der Dienst, dann die Schnittstelle.
# Ziel: nach dem Neustart ist das Netz wieder da, nicht nur "Befehl abgesetzt".
: "${CHIMERA_WLAN_IF:=wlan0}"
wlan_neu_starten() {
	_wl_if="${CHIMERA_WLAN_IF}"
	warn "WLAN neu starten ($_wl_if) ..."
	if have_cmd nmcli; then
		nmcli radio wifi off >/dev/null 2>&1 || true
		sleep 1
		nmcli radio wifi on >/dev/null 2>&1 || true
	elif have_cmd wpa_cli; then
		wpa_cli -i "$_wl_if" reconfigure >/dev/null 2>&1 || true
	fi
	for _wl_u in wpa_supplicant.service "wpa_supplicant@$_wl_if.service" \
	            "ifup@$_wl_if.service" networking.service; do
		systemctl is-active --quiet "$_wl_u" 2>/dev/null || continue
		systemctl restart "$_wl_u" >/dev/null 2>&1 || true
	done
	if have_cmd ip; then
		ip link set "$_wl_if" up >/dev/null 2>&1 || true
	fi
	if have_cmd ifup; then
		ifup "$_wl_if" >/dev/null 2>&1 || true
	fi
	# Nachsehen, nicht hoffen: bis zu 20 s auf das Netz warten.
	_wl_n=0
	while [ "$_wl_n" -lt 10 ]; do
		_wl_n=$((_wl_n + 1))
		sleep 2
		if network_erreichbar; then
			info "WLAN ist wieder da (nach $((_wl_n * 2)) s)."
			return 0
		fi
	done
	warn "WLAN nach 20 s noch nicht erreichbar."
	return 1
}

mojo_netz_reparieren() {
	_mo_bin="${CHIMERA_OPT:-/opt/chimera}/bin/chimera-tor"
	if [ ! -x "$_mo_bin" ]; then
		warn "Mojo nicht vorhanden ($_mo_bin) -- Netz wird nicht repariert."
		return 1
	fi
	warn "Mojo: Netzwerkstack neu starten und WLAN verbinden ..."
	if "$_mo_bin" --mojo --miracle --bereich netz >/dev/null 2>&1; then
		info "Mojo: Netz-Reparatur durchgelaufen."
		return 0
	fi
	# Der Bereich "netz" kann von aelteren Binaries noch unbekannt sein --
	# dann die ganze Pruefung, statt gar nichts zu tun.
	if "$_mo_bin" --mojo --miracle >/dev/null 2>&1 && network_erreichbar; then
		info "Mojo: Reparatur durchgelaufen (vollstaendige Pruefung)."
		return 0
	fi
	# Mojo hat (noch) keinen Netz-Bereich: Dann macht der Installer es selbst.
	# Sobald `--bereich netz` existiert, greift der Zweig oben und diese
	# Notloesung bleibt unbenutzt.
	warn "Mojo konnte das Netz nicht reparieren -- WLAN wird direkt neu gestartet."
	wlan_neu_starten
}

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
	# Ein Port in der Adresse (Spiegel, Test) gilt vor dem Schema: sonst
	# wuerde "http://127.0.0.1:8080/x" auf Port 80 geprueft und als "Netz
	# weg" gemeldet, obwohl die Gegenstelle antwortet.
	_nl_hostport="$(printf '%s' "$_nl_url" | sed -e 's|^[a-z]*://||' -e 's|/.*||')"
	case "$_nl_hostport" in
		*:[0-9]*) _nl_port="${_nl_hostport##*:}" ;;
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
	_nl_404=0

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

		# Eine Antwort ist keine Stoerung: 404/410/403 wiederholt niemand.
		# curl -f meldet HTTP-Fehler als Exitcode 22; welcher Code es war,
		# sagt eine einzelne Kopfabfrage.
		if [ "$_nl_rc" = 22 ] && have_cmd curl; then
			_nl_code="$(curl -sS -o /dev/null -w '%{http_code}' --head \
				--connect-timeout 10 --max-time 20 "$_nl_url" 2>/dev/null || true)"
			case "$_nl_code" in
				404|410)
					# Eine 404 kann auch luegen: Captive Portal, kaputter
					# Proxy, halb totes WLAN. Also nicht glauben, sondern
					# pruefen -- und wenn es klemmt, Mojo reparieren lassen.
					warn "Nicht vorhanden (HTTP $_nl_code) -- pruefe erst die Verbindung."
					if network_erreichbar; then
						warn "  Netz ist da -- ein Wiederholungsversuch."
					else
						warn "  Kein Netz -- Mojo wird eingeschaltet."
						mojo_netz_reparieren || true
					fi
					_nl_404=$((_nl_404 + 1))
					if [ "$_nl_404" -ge 3 ]; then
						err "Auch nach $_nl_404 Versuchen nicht vorhanden: $_nl_url"
						err "  Das ist jetzt ein Befund, kein Netzfehler."
						rm -f "$_nl_teil"
						return 1
					fi
					sleep 2
					continue ;;
				403)
					err "Zugriff verweigert (HTTP 403): $_nl_url"
					err "  Auch das wiederholt sich nicht von selbst."
					rm -f "$_nl_teil"
					return 1 ;;
			esac
			warn "HTTP-Fehler $_nl_code bei $_nl_url -- neuer Versuch."
		fi

		# Hier NICHT schweigen. Ein stiller Wiederholungsversuch sieht von
		# aussen aus wie ein Haenger.
		warn "Download unterbrochen (Exitcode $_nl_rc)."
		[ -s "$_nl_teil" ] && warn "  $(wc -c <"$_nl_teil") Byte sind da, es wird fortgesetzt."

		# Nach einem Timeout erst nachsehen, ob ueberhaupt Netz da ist --
		# sonst haemmert der Abruf gegen eine Wand und meldet nach 20
		# Versuchen dasselbe (Vorbild: _ping_ok vor dem Wiederholen).
		case "$_nl_rc" in
			6|7|28)
				_nl_warte=3
				while [ "$_nl_warte" -le 30 ] && ! network_erreichbar; do
					warn "  kein Netz (Probe: $CHIMERA_NETZ_PROBE) -- warte ${_nl_warte}s"
					sleep "$_nl_warte"
					_nl_warte=$((_nl_warte * 2))
				done
				;;
		esac
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
	# $4 Commit, falls der Inhalt auf einen Stand festgelegt ist (I4).
	# Setzt man ihn, wird genau dieser Stand geholt und der geholte Baum
	# per rev-parse dagegen geprueft. Auf einem Hauptzweig wuerde jedes
	# Commit des Herstellers den naechsten Installerlauf veraendern --
	# gefuehrt als root.
	_ng_commit="${4:-}"
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
			if [ -n "$_ng_commit" ]; then
				if (cd "$_ng_ziel" && git fetch -q --depth 1 origin "$_ng_commit" && \
				    git checkout -q FETCH_HEAD && \
				    [ "$(git rev-parse HEAD)" = "$_ng_commit" ]); then
					info "Auf festgelegten Stand gebracht: $_ng_commit"
					return 0
				fi
			elif (cd "$_ng_ziel" && git fetch -q --depth 1 origin && \
			      git reset -q --hard "origin/$(git rev-parse --abbrev-ref HEAD)"); then
				info "Aktualisiert: $_ng_ziel"
				return 0
			fi
		elif [ -n "$_ng_commit" ]; then
			# Ein einzelner Commit laesst sich nicht mit `clone --branch`
			# holen -- shallow-Klon und `fetch` auf die Kennung ist der
			# Weg, der auch bei GitHub traegt (gemessen).
			if git init -q "$_ng_ziel" && \
			   (cd "$_ng_ziel" && \
			    git remote add origin "$_ng_url" && \
			    git fetch -q --depth 1 origin "$_ng_commit" && \
			    git checkout -q FETCH_HEAD && \
			    [ "$(git rev-parse HEAD)" = "$_ng_commit" ]); then
				info "Geholt: $_ng_ziel ($_ng_commit)"
				return 0
			fi
			rm -rf "$_ng_ziel"
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

# --- Festgelegter Fremdcode (I4) ------------------------------------------
#
# Steht fest, WELCHE Datei ausgefuehrt wird? Ein Hersteller kann jederzeit
# etwas aendern; wird sein Repo auf einem Hauptzweig geholt, fuehrt der
# naechste Installerlauf stillschweigend anderen Code als root aus.
#
# Deshalb: ein hinterlegter Commit UND eine Pruefsumme der Datei, die
# aufgerufen wird. Beides wird geprueft, und eine fehlende Pruefmoeglichkeit
# ist kein Freibrief -- eine Zusicherung, die man nicht pruefen kann, ist
# keine (Regel 8a).
#
# $1 Datei, $2 erwartete Pruefsumme
# Rueckgabe 0 = stimmt, 1 = stimmt nicht oder nicht pruefbar.
fremddatei_pruefen() {
	_fp_datei="$1"
	_fp_soll="$2"

	[ -n "$_fp_soll" ] || {
		# Kein Sollwert hinterlegt. Das ist kein Fehler, aber es wird
		# GESAGT -- sonst haelt man es spaeter fuer geprueft.
		warn "Keine Pruefsumme hinterlegt fuer: $_fp_datei"
		warn "Der Inhalt kann sich beim Hersteller jederzeit aendern."
		return 0
	}

	if ! have_cmd sha256sum; then
		err "sha256sum fehlt -- die Pruefsumme ist damit nicht pruefbar."
		err "Ohne sie wird fremder Code nicht ausgefuehrt."
		return 1
	fi

	_fp_ist="$(sha256sum "$_fp_datei" 2>/dev/null | awk '{print $1}')"
	if [ "$_fp_ist" != "$_fp_soll" ]; then
		err "Der Fremdstand weicht ab: $_fp_datei"
		err "  erwartet: $_fp_soll"
		err "  gemessen: ${_fp_ist:-nichts -- nicht lesbar}"
		err ""
		err "Das heisst: der Fremdcode hat sich geaendert und niemand hat"
		err "ihn angesehen. Der Lauf fuehrt ihn nicht aus."
		return 1
	fi

	info "Pruefsumme stimmt: $(basename "$_fp_datei")"
	return 0
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
		if DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
			-o DPkg::Lock::Timeout="${CHIMERA_APT_LOCK_TIMEOUT:-300}" "$@"; then
			info "Installiert: $*"
			return 0
		fi
		warn "Paketinstallation unterbrochen (Versuch $_na_n)."
		sleep 3
	done
	err "Pakete nicht installierbar: $*"
	return 1
}
