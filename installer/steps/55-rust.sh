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
# Er startet NICHTS: Nutzer, Unit und Socket kommen mit dem Geruest (Phase 4d,
# Schritt 2).
#
# Exitcode:
#   0  Binary liegt da und hat die Version der Quelle (oder war schon da)
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

URL="$CHIMERA_RUST_URL/rust-$COMMIT"

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
		warn "Zum Commit $COMMIT gibt es kein Prerelease (rust-$COMMIT) oder es ist nicht erreichbar."
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

info "Abgelegt: $BIN (${LOKAL:+lokale Datei}${LOKAL:-rust-$COMMIT}, $(printf '%.12s' "$SUMME"))"
log_close 0; exit 0
