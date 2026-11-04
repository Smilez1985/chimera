#!/bin/sh
# Chimera installer -- Modul 55: Rust-Binary chimera-tor holen und ablegen.
#
# DESIGN Regel 14: Was dauernd laeuft und nicht auf das Modell wartet, ist
# Rust. Gebaut wird NIE auf dem Geraet, sondern in der CI; hier wird das
# Ergebnis geholt, geprueft und abgelegt.
#
# Welches Binary: genau das zum Commit der Quelle (state/quelle-commit, von
# Schritt 00 festgehalten) -- nie "das neueste". Binary und Quelle muessen
# zusammenpassen. Gibt es keinen Commit oder kein Prerelease dazu, ist das
# ein benannter Befund, kein Raten.
#
# Was dieser Schritt hinterlaesst:
#   /opt/chimera/bin/chimera-tor    root, 755 (Manifest: datei, Angabe = SHA-256)
#   /opt/chimera/bin                nur wenn er sie anlegte (Manifest: verzeich)
#   state/rust-stand                <commit> <hash des rust/-Baums> <version> --
#                                   damit ein unveraenderter Baum kein neues
#                                   Binary verlangt (kein Befund, kein CI-Build)
# Er startet NICHTS: Nutzer, Unit und Socket kommen mit dem Geruest (Phase 4d,
# Schritt 2).
#
# Exitcode:
#   0  Binary liegt da und hat die Version der Quelle (oder war schon da, oder
#      rust/ ist unveraendert und das vorhandene Binary ist geprueft)
#   1  Befund: kein Commit, kein Prerelease zum Commit, andere Architektur --
#      der Lauf geht weiter, das Gateway fehlt (der Dienst laeuft ohne)
#   2  abgebrochen: Pruefsumme stimmt nicht, Binary laeuft nicht, fremde Datei
#      am Zielort, kein Verwalter

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/network.sh"
. "$_HERE/lib/manifest.sh"

CHIMERA_STEP="55-rust"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "rust" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Rust-Binary (chimera-tor)"

: "${CHIMERA_RUST_URL:=https://github.com/Smilez1985/chimera/releases/download}"
BIN_DIR="$(rootpath "$CHIMERA_OPT/bin")"
BIN="$BIN_DIR/chimera-tor"
STATE_DIR="$(rootpath "$CHIMERA_STATE")"
QC="$STATE_DIR/quelle-commit"
ASSET="chimera-tor-aarch64"

# --- Voraussetzungen -----------------------------------------------------
if ! is_dry_run && [ -z "${CHIMERA_ROOT:-}" ] && [ "$(id -u)" != 0 ]; then
	err "$BIN_DIR gehoert root -- nur als Verwalter."
	log_close 2; exit 2
fi

# Architektur: die CI baut nur aarch64-musl. Ein anderes Geraet bekommt kein
# Binary, das nicht laeuft (Regel 14: armv7 kommt, wenn ein Board es braucht).
_arch="${CHIMERA_ARCH:-$(uname -m)}"
case "$_arch" in
	aarch64|arm64) : ;;
	*)
		warn "Architektur $_arch -- die CI baut nur aarch64. Kein Binary geladen."
		log_close 1; exit 1 ;;
esac

# --- Lokale Datei statt Prerelease -------------------------------------------
# CHIMERA_RUST_LOKAL=<Pfad>: ein selbst gebautes Binary (CI nicht erreichbar,
# Entwicklung am Geraet). Es ersetzt NUR das Laden: Die Versionsprobe und die
# Laufprobe unten gelten unveraendert, die Summe wird aus der Datei gebildet.
LOKAL="${CHIMERA_RUST_LOKAL:-}"
if [ -n "$LOKAL" ]; then
	[ -f "$LOKAL" ] && [ -s "$LOKAL" ] || { err "CHIMERA_RUST_LOKAL: '$LOKAL' fehlt oder ist leer."; log_close 2; exit 2; }
	COMMIT=lokal
	info "Quelle: lokale Datei $LOKAL"
else
	# --- Welcher Commit? -----------------------------------------------------
	COMMIT="$(tr -d ' \t\r\n' <"$QC" 2>/dev/null || true)"
	case "$COMMIT" in
		'')
			warn "Kein Commit der Quelle ($QC fehlt oder ist leer)."
			warn "  Zip, Paket oder geaenderter rust/-Baum haben keinen -- es wird nicht geraten."
			warn "  Das Binary muss zum Commit der Quelle passen; ohne Commit kein Binary."
			log_close 1; exit 1 ;;
		*[!0-9a-f]*)
			err "Commit in $QC ist kein Hex: '$COMMIT'"
			log_close 2; exit 2 ;;
	esac
	info "Quelle: Commit $COMMIT"
fi

SOLL_V="$(tr -d ' \t\r\n' <"$_HERE/../VERSION" 2>/dev/null || true)"
[ -n "$SOLL_V" ] || { err "VERSION der Quelle fehlt."; log_close 2; exit 2; }

# --- Haelt der rust/-Baum still? ---------------------------------------------
# Das Binary haengt allein am Inhalt von rust/. Ein Doku-Commit laesst ihn
# unveraendert -- dann ist kein neues Binary noetig, auch wenn es zum neuen
# Commit kein Prerelease gibt (jeder Doku-Commit sparte sonst einen CI-Build).
# Gemessen wird der BAUM, nicht der Commit: nur er sagt, ob sich das Binary
# aendern kann. Ein geaenderter Baum bei gleichem Commit (Entwicklung am
# Geraet) erkennt dieselbe Probe.
#
# state/rust-stand (eine Zeile):  <commit> <baumhash> <version>
# commit/version gehoeren zu dem Stand, aus dem das abgelegte Binary gebaut
# wurde -- daraus wird bei Bedarf nachgeladen (rust-<commit>).
RUST_BAUM="${CHIMERA_RUST_BAUM:-$_HERE/../rust}"
RUST_STAND="$STATE_DIR/rust-stand"

# Hash ueber alle Dateien des Baums (ohne target/: reiner Bauabfall).
# Pfade werden sortiert und samt Summe gehasht -- Umbenennen zaehlt mit,
# nur der Zeitstempel nicht.
rust_baum_hash() { # $1 Verzeichnis; Ausgabe: Hash oder nichts
	[ -d "$1" ] || return 0
	_rbh_l="$(mktemp "${TMPDIR:-/tmp}/chimera-baum.XXXXXX" 2>/dev/null)" || return 0
	(
		cd "$1" || exit 1
		find . -path ./target -prune -o -type f -print | LC_ALL=C sort | \
			while IFS= read -r _rb_f; do
				printf '%s  %s\n' "$(network_checksum "$_rb_f")" "$_rb_f"
			done
	) >"$_rbh_l" 2>/dev/null
	_rbh_h="$(network_checksum "$_rbh_l")"
	rm -f "$_rbh_l"
	[ -n "$_rbh_h" ] && printf '%s' "$_rbh_h"
	return 0
}

# Zustand schreiben (atomar: Nebendatei + mv). Ohne Hash wird nichts
# behauptet -- dann bleibt die Datei weg.
rust_stand_schreiben() { # $1 commit, $2 baumhash, $3 version
	[ -n "$2" ] || { rm -f "$RUST_STAND"; return 0; }
	mkdir -p "$(dirname "$RUST_STAND")" || return 1
	printf '%s %s %s\n' "$1" "$2" "$3" >"$RUST_STAND.neu" || { rm -f "$RUST_STAND.neu"; return 1; }
	mv "$RUST_STAND.neu" "$RUST_STAND" || { rm -f "$RUST_STAND.neu"; return 1; }
	[ "$(cat "$RUST_STAND" 2>/dev/null)" = "$1 $2 $3" ]
}

BAUM_HASH="$(rust_baum_hash "$RUST_BAUM" 2>/dev/null || true)"
if [ -z "$BAUM_HASH" ]; then
	info "Kein rust/-Baum unter $RUST_BAUM -- Stand wird nicht verglichen."
fi

_alt_c=""; _alt_h=""; _alt_v=""
if [ -f "$RUST_STAND" ]; then
	# shellcheck disable=SC2034
	read -r _alt_c _alt_h _alt_v <"$RUST_STAND" 2>/dev/null || true
fi

# Still heisst: gleicher Baum UND gleiche Version. Eine neue VERSION gehoert
# ins Binary (es nennt sie) -- dann wird gebaut, auch wenn rust/ gleich blieb.
STILL=0
if [ -n "$BAUM_HASH" ] && [ "$BAUM_HASH" = "$_alt_h" ] && [ -n "$_alt_c" ] && \
	[ "$_alt_v" = "$SOLL_V" ]; then
	STILL=1
fi

# Welcher Commit wird geladen? Bei unveraendertem Baum der Stand, aus dem das
# Binary gebaut wurde -- zu einem Doku-Commit gibt es kein Prerelease.
QUELLE_C="$COMMIT"
[ "$STILL" = 1 ] && QUELLE_C="$_alt_c"

URL="$CHIMERA_RUST_URL/rust-$QUELLE_C"

# --- Eine fremde Datei wird nie ueberschrieben -------------------------------
# Eigen ist, was im Manifest steht UND dessen Pruefsumme noch stimmt.
_eigen_summe=""
if [ -e "$BIN" ] || [ -L "$BIN" ]; then
	_eigen_summe="$(manifest_list_von datei 55-rust | awk -F'\t' -v p="$BIN" '$1 == p { print $2 }')"
	if [ -z "$_eigen_summe" ]; then
		err "$BIN existiert und steht nicht im Manifest -- wird nicht ueberschrieben."
		log_close 2; exit 2
	fi
fi

# --- Baum unveraendert: vorhandenes Binary bleibt ---------------------------
# Kein Netz, kein CI-Build: der Baum sagt, dass sich das Binary nicht
# aendern kann. Geprueft wird trotzdem -- Pruefsumme wie im Manifest,
# Lauf und Version. Was nicht geprueft ist, gilt nicht als unveraendert.
BEHALTEN=0
if [ "$STILL" = 1 ] && [ -n "$_eigen_summe" ] && \
	[ "$(network_checksum "$BIN")" = "$_eigen_summe" ] && \
	[ "$("$BIN" --version 2>/dev/null || true)" = "chimera-tor $SOLL_V" ]; then
	BEHALTEN=1
fi

if [ "$BEHALTEN" = 1 ]; then
	if is_dry_run; then
		info "[wuerde behalten] $BIN (rust/ unveraendert seit $_alt_c, Version $SOLL_V)"
		log_close 0; exit 0
	fi
	rust_stand_schreiben "$QUELLE_C" "$BAUM_HASH" "$SOLL_V" || \
		warn "state/rust-stand nicht schreibbar -- der naechste Lauf prueft wieder voll."
	info "Rust unveraendert seit $_alt_c -- Binary bleibt (Pruefsumme, Version und Lauf geprueft)."
	log_close 0; exit 0
fi

# --- Trockenlauf -----------------------------------------------------------
if is_dry_run; then
	if [ -n "$LOKAL" ]; then
		info "[wuerde kopieren] $LOKAL"
	else
		info "[wuerde laden] $URL/$ASSET"
	fi
	info "[wuerde pruefen] SHA-256, danach $BIN --version = chimera-tor $SOLL_V"
	info "[wuerde ablegen] $BIN (root, 755)"
	log_close 0; exit 0
fi

# --- Pruefsumme holen ---------------------------------------------------------
_tmp="$(tmp_path chimera-rust)" && rm -f "$_tmp" && mkdir -p "$_tmp" || {
	err "Kein Zwischenverzeichnis."; log_close 2; exit 2; }
trap 'rm -rf "$_tmp"' EXIT INT TERM

if [ -n "$LOKAL" ]; then
	SUMME="$(network_checksum "$LOKAL")"
else
	if ! network_fetch "$URL/$ASSET.sha256" "$_tmp/$ASSET.sha256"; then
		warn "Zum Commit $QUELLE_C gibt es kein Prerelease (rust-$QUELLE_C) oder es ist nicht erreichbar."
		warn "  Die CI veroeffentlicht es fuer Staende auf 'entwicklung' mit Rust-Aenderung;"
		warn "  ein anderer Stand wird NICHT genommen -- Binary und Quelle muessen passen."
		log_close 1; exit 1
	fi
	SUMME="$(awk '{ print $1; exit }' "$_tmp/$ASSET.sha256")"
	case "$SUMME" in
		*[!0-9a-f]*|'') err "Pruefsummendatei unbrauchbar: '$SUMME'"; log_close 2; exit 2 ;;
	esac
	[ "${#SUMME}" = 64 ] || { err "Pruefsumme hat ${#SUMME} statt 64 Zeichen."; log_close 2; exit 2; }
fi
case "$SUMME" in
	*[!0-9a-f]*|'') err "Pruefsumme unbrauchbar: '$SUMME'"; log_close 2; exit 2 ;;
esac
[ "${#SUMME}" = 64 ] || { err "Pruefsumme hat ${#SUMME} statt 64 Zeichen."; log_close 2; exit 2; }

# --- Schon da und stimmig? -------------------------------------------------
if [ -n "$_eigen_summe" ] && [ "$_eigen_summe" = "$SUMME" ] && \
	[ "$(network_checksum "$BIN")" = "$SUMME" ]; then
	info "Schon vorhanden und geprueft: $BIN"
	rust_stand_schreiben "$QUELLE_C" "$BAUM_HASH" "$SOLL_V" || \
		warn "state/rust-stand nicht schreibbar -- der naechste Lauf prueft wieder voll."
	log_close 0; exit 0
fi

# --- Laden (network_fetch prueft die Summe und schreibt erst in eine Nebendatei)
if [ -n "$LOKAL" ]; then
	cp "$LOKAL" "$_tmp/$ASSET" && [ "$(network_checksum "$_tmp/$ASSET")" = "$SUMME" ] || {
		err "Lokale Datei nicht kopierbar oder veraendert -- nichts abgelegt."; log_close 2; exit 2; }
elif ! network_fetch "$URL/$ASSET" "$_tmp/$ASSET" "$SUMME"; then
	err "Binary nicht geladen oder Pruefsumme stimmt nicht -- nichts abgelegt."
	log_close 2; exit 2
fi
chmod 755 "$_tmp/$ASSET"

# Laeuft es, und ist es die Version der Quelle? Ein Binary, das nie gestartet
# wurde, ist eine Behauptung (Regel 14).
_ist="$("$_tmp/$ASSET" --version 2>/dev/null || true)"
if [ "$_ist" != "chimera-tor $SOLL_V" ]; then
	err "Binary meldet '${_ist:-nichts}' statt 'chimera-tor $SOLL_V' -- nichts abgelegt."
	log_close 2; exit 2
fi

# --- Ablegen: Nebendatei neben dem Ziel, dann umbenennen ---------------------
_bin_neu=0
[ -d "$BIN_DIR" ] || _bin_neu=1
mkdir -p "$BIN_DIR" || { err "$BIN_DIR nicht anlegbar."; log_close 2; exit 2; }
chmod 755 "$BIN_DIR" 2>/dev/null || true
cp "$_tmp/$ASSET" "$BIN.neu" || { rm -f "$BIN.neu"; err "Kopie nach $BIN.neu gescheitert."; log_close 2; exit 2; }
chmod 755 "$BIN.neu"
mv -f "$BIN.neu" "$BIN" || { rm -f "$BIN.neu"; err "Umbenennen nach $BIN gescheitert."; log_close 2; exit 2; }

# Am Ergebnis pruefen, nicht am Exitcode.
if [ "$(network_checksum "$BIN")" != "$SUMME" ]; then
	# Eine Datei, die nicht stimmt, darf nicht stehen bleiben: der Dienst
	# wuerde sie starten. War vorher keine da, wird sie wieder entfernt; ein
	# vorheriges eigenes Binary liegt dann nicht mehr da (der Tausch ist
	# geschehen) -- das wird benannt, nicht verschwiegen.
	rm -f "$BIN"
	err "$BIN hat nach dem Ablegen eine andere Pruefsumme -- entfernt. Lauf wiederholen."
	log_close 2; exit 2
fi

[ "$_bin_neu" = 1 ] && { manifest_has verzeich "$BIN_DIR" || manifest_record verzeich "$BIN_DIR" ""; }
# Eine alte Angabe (andere Summe) ersetzen: sonst bliebe sie stehen und der
# Rueckbau haelte die Datei fuer fremd.
if [ -n "$_eigen_summe" ] && [ -f "$CHIMERA_MANIFEST" ]; then
	_mf_neu="$CHIMERA_MANIFEST.neu"
	awk -F'\t' -v p="$BIN" -v m="55-rust" '!($1 !~ /^#/ && $2 == m && $3 == "datei" && $4 == p)' \
		"$CHIMERA_MANIFEST" >"$_mf_neu" && [ -s "$_mf_neu" ] && mv "$_mf_neu" "$CHIMERA_MANIFEST" || {
		rm -f "$_mf_neu"; err "Manifest nicht aktualisierbar."; log_close 2; exit 2; }
fi
manifest_record datei "$BIN" "$SUMME"

rust_stand_schreiben "$QUELLE_C" "$BAUM_HASH" "$SOLL_V" || \
	warn "state/rust-stand nicht schreibbar -- der naechste Lauf prueft wieder voll."

info "Abgelegt: $BIN (${LOKAL:+lokale Datei}${LOKAL:-rust-$QUELLE_C}, $(printf '%.12s' "$SUMME"))"
log_close 0; exit 0
