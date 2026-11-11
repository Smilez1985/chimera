#!/bin/sh
# Chimera installer -- ein Rust-Binary aus dem Startbaum ablegen.
#
# DESIGN Regel 14: Was dauernd laeuft und nicht auf das Modell wartet, ist
# Rust. Gebaut wird NIE auf dem Geraet. Die fertigen Binaries liegen mit im
# Repo (`gateway/chimera-tor-aarch64`, `sohelper/chimera-sohelper-aarch64`,
# smilez 10.11./11.11.2026) und kommen mit jedem Release neu; hier wird nichts
# nachgeladen, es braucht kein Netz.
#
# **Warum hier und nicht zweimal:** Gateway und Ausfuehrer stellen dieselbe
# Frage -- Pruefsumme, Architektur, Laufprobe, Manifest, fremde Datei am
# Zielort. Zwei Kopien waeren der Anfang davon, dass eine davon leiser prueft
# als die andere (Regel 10g).
#
# Aufruf:
#   binary_aus_baum <art> <modul>
#     art    tor | sohelper
#     modul  Name des Schritts fuers Manifest (55-rust, 99-sohelper)
#
# Exitcode:
#   0  Binary liegt da und hat die Version der Quelle (oder war schon da)
#   1  Befund: kein Binary im Startbaum, andere Architektur -- der Lauf geht
#      weiter, das Programm fehlt
#   2  abgebrochen: Pruefsumme stimmt nicht, Binary laeuft nicht oder nennt
#      eine andere Version, fremde Datei am Zielort, keine Rechte
#
# Voraussetzungen: common.sh, manifest.sh, network.sh, source.sh geladen.

binary_art_programm() {
	case "$1" in
		tor)      printf '%s\n' chimera-tor ;;
		sohelper) printf '%s\n' chimera-sohelper ;;
		*) return 1 ;;
	esac
}

binary_art_asset() {
	case "$1" in
		tor)      printf '%s\n' chimera-tor-aarch64 ;;
		sohelper) printf '%s\n' chimera-sohelper-aarch64 ;;
		*) return 1 ;;
	esac
}

binary_art_ordner() {
	case "$1" in
		tor)      printf '%s\n' gateway ;;
		sohelper) printf '%s\n' sohelper ;;
		*) return 1 ;;
	esac
}

# Wo der Stand des Binaries festgehalten wird (nur das Gateway braucht das:
# Modul 55 haelt daran still, solange sich rust/ nicht geaendert hat).
binary_art_standziel() {
	case "$1" in
		tor)      printf '%s\n' rust-stand ;;
		*)        printf '%s\n' "" ;;
	esac
}

# Der Schalter fuer ein selbst gebautes Binary (Entwicklung, Tests).
binary_art_lokal_var() {
	case "$1" in
		tor)      printf '%s\n' CHIMERA_RUST_LOKAL ;;
		sohelper) printf '%s\n' CHIMERA_SOHELPER_LOKAL ;;
		*) return 1 ;;
	esac
}

binary_aus_baum() {
	_ba_art="$1"
	_ba_modul="$2"
	_ba_prog="$(binary_art_programm "$_ba_art")" || { err "Unbekannte Art: $_ba_art"; return 2; }
	_ba_asset="$(binary_art_asset "$_ba_art")"
	_ba_ordner="$(binary_art_ordner "$_ba_art")"
	_ba_standname="$(binary_art_standziel "$_ba_art")"
	_ba_lokalvar="$(binary_art_lokal_var "$_ba_art")"

	# Der Startbaum ist der Baum, aus dem der Schritt laeuft (nach dem Neustart
	# aus I8 ist das source/). Dort liegt gateway/ neben installer/. Der Aufrufer
	# setzt ihn als BINARY_REPO -- geraten wird hier nichts.
	_ba_repo="${BINARY_REPO:-}"
	[ -n "$_ba_repo" ] || { err "BINARY_REPO fehlt -- der Startbaum ist unbekannt."; return 2; }
	_ba_quelle_dir="$_ba_repo/$_ba_ordner"

	_ba_bin_dir="$(rootpath "$CHIMERA_OPT/bin")"
	_ba_bin="$_ba_bin_dir/$_ba_prog"
	# Das Manifest nennt Zielpfade (ohne Wurzelverzeichnis). In einem
	# erfundenen Wurzelverzeichnis (Tests) sind die beiden verschieden --
	# verglichen und eingetragen wird immer der Zielpfad.
	_ba_pfad="$CHIMERA_OPT/bin/$_ba_prog"
	_ba_stand=""
	[ -n "$_ba_standname" ] && _ba_stand="$(rootpath "$CHIMERA_STATE")/$_ba_standname"

	_ba_soll_v="$(tr -d ' \t\r\n' <"$_ba_repo/VERSION" 2>/dev/null || true)"
	[ -n "$_ba_soll_v" ] || { err "VERSION der Quelle fehlt."; return 2; }

	if ! is_dry_run && [ -z "${CHIMERA_ROOT:-}" ] && [ "$(id -u)" != 0 ]; then
		err "$_ba_bin_dir gehoert root -- nur als Verwalter."
		return 2
	fi

	# Architektur: das Repo bringt nur aarch64 mit (Regel 14: armv7 kommt, wenn
	# ein Board es braucht). Ein anderes Geraet bekommt kein Binary, das nicht
	# laeuft -- das ist ein Befund, kein Abbruch.
	_ba_arch="${CHIMERA_ARCH:-$(uname -m)}"
	case "$_ba_arch" in
		aarch64|arm64) : ;;
		*)
			warn "Architektur $_ba_arch -- das Repo bringt $_ba_prog nur fuer aarch64 mit."
			return 1 ;;
	esac

	# --- Quelle: das Binary aus dem Startbaum --------------------------------
	_ba_lokal=""
	eval "_ba_lokal=\${$_ba_lokalvar:-}"
	_ba_quelle=""
	_ba_standdatei=""
	if [ -n "$_ba_lokal" ]; then
		[ -f "$_ba_lokal" ] && [ -s "$_ba_lokal" ] || {
			err "$_ba_lokalvar: '$_ba_lokal' fehlt oder ist leer."; return 2; }
		_ba_quelle="$_ba_lokal"
		info "Quelle: lokale Datei $_ba_lokal"
	else
		_ba_quelle="$_ba_quelle_dir/$_ba_asset"
		if [ ! -f "$_ba_quelle" ]; then
			warn "Kein Binary im Startbaum: $_ba_quelle fehlt."
			warn "  Es gehoert ins Repo ($_ba_ordner/, DESIGN Regel 14) und kommt mit dem Stand mit."
			warn "  Ohne Binary wird $_ba_prog nicht eingerichtet."
			return 1
		fi
		if [ ! -s "$_ba_quelle" ]; then
			err "Binary im Startbaum ist leer: $_ba_quelle"; return 2
		fi
		[ -f "$_ba_quelle_dir/$_ba_asset.stand" ] && \
			_ba_standdatei="$_ba_quelle_dir/$_ba_asset.stand"
		info "Quelle: $_ba_quelle"
	fi

	# --- Pruefsumme ----------------------------------------------------------
	# Erwartet wird die Summe aus der .sha256-Datei daneben (die CI schreibt sie).
	# Fehlt sie, wird das benannt: eine Pruefsumme, die niemand kennt, prueft nichts.
	_ba_summe=""
	if [ -n "$_ba_lokal" ]; then
		_ba_summe="$(network_checksum "$_ba_quelle")"
	else
		_ba_ss="$_ba_quelle_dir/$_ba_asset.sha256"
		if [ ! -f "$_ba_ss" ]; then
			err "Pruefsumme fehlt: $_ba_ss"
			err "  Zusammen mit dem Binary ablegen (tools/binary-ablegen.sh schreibt sie)."
			return 2
		fi
		_ba_summe="$(awk '{ print $1; exit }' "$_ba_ss")"
		case "$_ba_summe" in
			*[!0-9a-f]*|'') err "Pruefsummendatei unbrauchbar: '$_ba_summe'"; return 2 ;;
		esac
		[ "${#_ba_summe}" = 64 ] || {
			err "Pruefsumme hat ${#_ba_summe} statt 64 Zeichen."; return 2; }
		_ba_ist="$(network_checksum "$_ba_quelle")"
		if [ "$_ba_ist" != "$_ba_summe" ]; then
			err "Binary im Startbaum stimmt nicht mit seiner Pruefsumme ueberein."
			err "  Datei: $_ba_quelle"
			err "  erwartet $_ba_summe, gemessen $_ba_ist"
			return 2
		fi
	fi

	# --- Stand: aus welchem rust/-Baum wurde es gebaut? ----------------------
	# Kein Abbruch, wenn der Baum neuer ist -- nur eine Meldung (smilez, 10.11.).
	if [ -n "$_ba_standdatei" ]; then
		_ba_alt_c=""; _ba_alt_h=""; _ba_alt_v=""
		read -r _ba_alt_c _ba_alt_h _ba_alt_v <"$_ba_standdatei" 2>/dev/null || true
		_ba_jetzt_h="$(rust_baum_hash "$_ba_repo/rust" 2>/dev/null || true)"
		if [ -n "$_ba_jetzt_h" ] && [ -n "$_ba_alt_h" ] && [ "$_ba_jetzt_h" != "$_ba_alt_h" ]; then
			info "Hinweis: rust/ ist neuer als das Binary (gebaut aus $_ba_alt_c, Version ${_ba_alt_v:-unbekannt})."
			info "  Zwischen zwei Fassungen ist das normal; das Binary aus dem Baum wird genommen."
		elif [ -n "$_ba_alt_c" ]; then
			info "Binary gebaut aus $_ba_alt_c (rust/ seitdem unveraendert)."
		fi
	fi

	# --- Eigen ist, was im Manifest steht UND dessen Pruefsumme noch stimmt ---
	_ba_eigen=""
	_ba_fremd_modul=""
	if [ -e "$_ba_bin" ] || [ -L "$_ba_bin" ]; then
		_ba_eigen="$(manifest_list_von datei "$_ba_modul" | awk -F'\t' -v p="$_ba_pfad" '$1 == p { print $2 }')"
		if [ -z "$_ba_eigen" ]; then
			# Dasselbe Programm kann von einem anderen Schritt abgelegt worden
			# sein: Schritt 55 legt beide Binaries ab, Schritt 99-sohelper
			# prueft danach denselben Pfad. Ein Eintrag eines anderen Moduls
			# ist kein Fremdkoerper -- aber nachsehen muss man es.
			_ba_eigen="$(manifest_list datei | awk -F'\t' -v p="$_ba_pfad" '$1 == p { print $2 }')"
			_ba_fremd_modul="$(manifest_list datei | awk -F'\t' -v p="$_ba_pfad" '$1 == p { print "ja" }')"
		fi
		if [ -z "$_ba_eigen" ]; then
			err "$_ba_bin existiert und steht nicht im Manifest -- wird nicht ueberschrieben."
			return 2
		fi
		if [ -n "$_ba_fremd_modul" ] && [ "$_ba_eigen" != "$_ba_summe" ]; then
			warn "$_ba_bin steht unter einem anderen Schritt im Manifest, aber mit anderer Pruefsumme."
			warn "  Sie wird ersetzt; der alte Eintrag bleibt stehen (Rueckbau sieht ihn)."
			_ba_fremd_modul=""
		fi
	fi

	# --- Schon da und stimmig? ----------------------------------------------
	if [ -n "$_ba_eigen" ] && [ "$_ba_eigen" = "$_ba_summe" ] && \
		[ "$(network_checksum "$_ba_bin")" = "$_ba_summe" ]; then
		info "Schon vorhanden und geprueft: $_ba_bin"
		if [ -n "$_ba_stand" ]; then
			rust_stand_schreiben "$_ba_standdatei" || \
				warn "state/rust-stand nicht schreibbar -- die naechste Meldung faellt aus."
		fi
		return 0
	fi

	# --- Trockenlauf ---------------------------------------------------------
	if is_dry_run; then
		info "[wuerde pruefen] $_ba_quelle (SHA-256 $(printf '%.12s' "$_ba_summe")...) und starten"
		info "[wuerde pruefen] Version = $_ba_prog $_ba_soll_v"
		info "[wuerde ablegen] $_ba_bin (root, 755)"
		return 0
	fi

	# --- Laufprobe: ein Binary, das nie gestartet wurde, ist eine Behauptung --
	_ba_tmp="$(tmp_path "chimera-$_ba_art")" && rm -f "$_ba_tmp" && mkdir -p "$_ba_tmp" || {
		err "Kein Zwischenverzeichnis."; return 2; }

	cp "$_ba_quelle" "$_ba_tmp/$_ba_asset" || {
		err "Kopie nicht anlegbar."; rm -rf "$_ba_tmp"; return 2; }
	chmod 755 "$_ba_tmp/$_ba_asset"
	if [ "$(network_checksum "$_ba_tmp/$_ba_asset")" != "$_ba_summe" ]; then
		err "Kopie weicht von der Quelle ab -- nichts abgelegt."; rm -rf "$_ba_tmp"; return 2
	fi
	_ba_ist="$("$_ba_tmp/$_ba_asset" --version 2>/dev/null || true)"
	if [ "$_ba_ist" != "$_ba_prog $_ba_soll_v" ]; then
		err "Binary meldet '${_ba_ist:-nichts}' statt '$_ba_prog $_ba_soll_v' -- nichts abgelegt."
		err "  Die VERSION der Quelle und das Binary im Startbaum passen nicht zusammen."
		rm -rf "$_ba_tmp"; return 2
	fi

	# --- Ablegen: Nebendatei neben dem Ziel, dann umbenennen ------------------
	_ba_bin_neu=0
	[ -d "$_ba_bin_dir" ] || _ba_bin_neu=1
	mkdir -p "$_ba_bin_dir" || { err "$_ba_bin_dir nicht anlegbar."; rm -rf "$_ba_tmp"; return 2; }
	chmod 755 "$_ba_bin_dir" 2>/dev/null || true
	cp "$_ba_tmp/$_ba_asset" "$_ba_bin.neu" || {
		rm -f "$_ba_bin.neu"; err "Kopie nach $_ba_bin.neu gescheitert."; rm -rf "$_ba_tmp"; return 2; }
	chmod 755 "$_ba_bin.neu"
	mv -f "$_ba_bin.neu" "$_ba_bin" || {
		rm -f "$_ba_bin.neu"; err "Umbenennen nach $_ba_bin gescheitert."; rm -rf "$_ba_tmp"; return 2; }
	rm -rf "$_ba_tmp"

	# Am Ergebnis pruefen, nicht am Exitcode.
	if [ "$(network_checksum "$_ba_bin")" != "$_ba_summe" ]; then
		# Eine Datei, die nicht stimmt, darf nicht stehen bleiben: der Dienst
		# wuerde sie starten.
		rm -f "$_ba_bin"
		err "$_ba_bin hat nach dem Ablegen eine andere Pruefsumme -- entfernt. Lauf wiederholen."
		return 2
	fi

	[ "$_ba_bin_neu" = 1 ] && { manifest_has verzeich "$_ba_bin_dir" || manifest_record verzeich "$_ba_bin_dir" ""; }
	# Eine alte Angabe (andere Summe) ersetzen: sonst bliebe sie stehen und der
	# Rueckbau hielte die Datei fuer fremd.
	if [ -n "$_ba_eigen" ] && [ -z "$_ba_fremd_modul" ] && [ -f "$CHIMERA_MANIFEST" ]; then
		_ba_mf_neu="$CHIMERA_MANIFEST.neu"
		awk -F'\t' -v p="$_ba_pfad" -v m="$_ba_modul" '!($1 !~ /^#/ && $2 == m && $3 == "datei" && $4 == p)' \
			"$CHIMERA_MANIFEST" >"$_ba_mf_neu" && [ -s "$_ba_mf_neu" ] && mv "$_ba_mf_neu" "$CHIMERA_MANIFEST" || {
			rm -f "$_ba_mf_neu"; err "Manifest nicht aktualisierbar."; return 2; }
	fi
	manifest_record datei "$_ba_pfad" "$_ba_summe"

	if [ -n "$_ba_stand" ]; then
		rust_stand_schreiben "$_ba_standdatei" || \
			warn "state/rust-stand nicht schreibbar -- die naechste Meldung faellt aus."
	fi

	info "Abgelegt: $_ba_bin (${_ba_lokal:+lokale Datei}${_ba_lokal:-$_ba_ordner/$_ba_asset}, $(printf '%.12s' "$_ba_summe"))"
	return 0
}
