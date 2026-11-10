#!/bin/sh
# Chimera installer -- Modul 55: Rust-Binary chimera-tor aus dem Startbaum ablegen.
#
# DESIGN Regel 14: Was dauernd laeuft und nicht auf das Modell wartet, ist
# Rust. Gebaut wird NIE auf dem Geraet. Das fertige Binary liegt mit im Repo
# (`gateway/`, smilez 10.11.2026) und kommt mit jedem Release neu; dieser
# Schritt holt nichts nach und braucht kein Netz.
#
# Quelle: <Startbaum>/gateway/chimera-tor-aarch64
#   daneben: chimera-tor-aarch64.sha256   Pruefsumme (CI)
#   daneben: chimera-tor-aarch64.stand    "<commit> <hash des rust/-Baums> <version>"
#
# Geprueft wird: vorhanden und nicht leer, Pruefsumme, Architektur, Laufprobe
# (--version nennt die VERSION der Quelle).
#
# Gemeldet, aber KEIN Abbruch und kein Befund im Exitcode: ist der rust/-Baum
# im Startbaum neuer als der, aus dem das Binary gebaut wurde. Zwischen zwei
# Fassungen ist das der Normalfall (smilez, 10.11.2026).
#
# Was dieser Schritt hinterlaesst:
#   /opt/chimera/bin/chimera-tor    root, 755 (Manifest: datei, Angabe = SHA-256)
#   /opt/chimera/bin                nur wenn er es anlegte (Manifest: verzeich)
#   state/rust-stand                <commit> <hash des rust/-Baums> <version>
#                                   (aus der .stand-Datei des Binaries)
# Er startet NICHTS: Nutzer, Unit und Socket kommen mit dem Geruest (Phase 4d).
#
# Exitcode:
#   0  Binary liegt da und hat die Version der Quelle (oder war schon da)
#   1  Befund: kein Binary im Startbaum, andere Architektur -- der Lauf geht
#      weiter, das Gateway fehlt (der Dienst laeuft ohne)
#   2  abgebrochen: Pruefsumme stimmt nicht, Binary laeuft nicht oder nennt
#      eine andere Version, fremde Datei am Zielort, keine Rechte

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/network.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/source.sh"

CHIMERA_STEP="55-rust"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "rust" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Rust-Binary (chimera-tor)"

BIN_DIR="$(rootpath "$CHIMERA_OPT/bin")"
BIN="$BIN_DIR/chimera-tor"
STATE_DIR="$(rootpath "$CHIMERA_STATE")"
RUST_STAND="$STATE_DIR/rust-stand"
# Der Startbaum ist der Baum, aus dem dieser Schritt laeuft (nach dem Neustart
# aus I8 ist das source/). Dort liegt gateway/ neben installer/.
REPO="$(cd "$_HERE/.." && pwd)"
QUELLE_DIR="$REPO/gateway"
ASSET="chimera-tor-aarch64"
RUST_BAUM="$REPO/rust"
[ -n "${CHIMERA_RUST_BAUM:-}" ] && RUST_BAUM="$CHIMERA_RUST_BAUM"
SOLL_V="$(tr -d ' \t\r\n' <"$REPO/VERSION" 2>/dev/null || true)"
[ -n "$SOLL_V" ] || { err "VERSION der Quelle fehlt."; log_close 2; exit 2; }

# --- Voraussetzungen -----------------------------------------------------
if ! is_dry_run && [ -z "${CHIMERA_ROOT:-}" ] && [ "$(id -u)" != 0 ]; then
	err "$BIN_DIR gehoert root -- nur als Verwalter."
	log_close 2; exit 2
fi

# Architektur: das Repo bringt nur aarch64 mit (Regel 14: armv7 kommt, wenn
# ein Board es braucht). Ein anderes Geraet bekommt kein Binary, das nicht
# laeuft -- das ist ein Befund, kein Abbruch.
_arch="${CHIMERA_ARCH:-$(uname -m)}"
case "$_arch" in
	aarch64|arm64) : ;;
	*)
		warn "Architektur $_arch -- das Repo bringt das Binary nur fuer aarch64 mit."
		log_close 1; exit 1 ;;
esac

# --- Quelle: das Binary aus dem Startbaum --------------------------------
# CHIMERA_RUST_LOKAL=<Pfad>: ein selbst gebautes Binary statt des ausgelieferten
# (Entwicklung, Tests). Es ersetzt NUR die Quelle; Pruefsumme, Laufprobe und
# Versionsvergleich gelten unveraendert.
LOKAL="${CHIMERA_RUST_LOKAL:-}"
QUELLE=""
STAND=""
if [ -n "$LOKAL" ]; then
	[ -f "$LOKAL" ] && [ -s "$LOKAL" ] || {
		err "CHIMERA_RUST_LOKAL: '$LOKAL' fehlt oder ist leer."; log_close 2; exit 2; }
	QUELLE="$LOKAL"
	info "Quelle: lokale Datei $LOKAL"
else
	QUELLE="$QUELLE_DIR/$ASSET"
	if [ ! -f "$QUELLE" ]; then
		warn "Kein Binary im Startbaum: $QUELLE fehlt."
		warn "  Es gehoert ins Repo (gateway/, DESIGN Regel 14) und kommt mit dem Stand mit."
		warn "  Ohne Binary wird das Gateway nicht eingerichtet; der Dienst laeuft ohne."
		log_close 1; exit 1
	fi
	if [ ! -s "$QUELLE" ]; then
		err "Binary im Startbaum ist leer: $QUELLE"; log_close 2; exit 2
	fi
	[ -f "$QUELLE_DIR/$ASSET.stand" ] && STAND="$QUELLE_DIR/$ASSET.stand"
	info "Quelle: $QUELLE"
fi

# --- Pruefsumme ----------------------------------------------------------
# Erwartet wird die Summe aus der .sha256-Datei daneben (die CI schreibt sie).
# Fehlt sie, wird das benannt: eine Pruefsumme, die niemand kennt, prueft nichts.
_SUMME=""
if [ -n "$LOKAL" ]; then
	_SUMME="$(network_checksum "$QUELLE")"
else
	_ss="$QUELLE_DIR/$ASSET.sha256"
	if [ ! -f "$_ss" ]; then
		err "Pruefsumme fehlt: $_ss"
		err "  Zusammen mit dem Binary ablegen (tools/gateway-binary.sh schreibt sie)."
		log_close 2; exit 2
	fi
	_SUMME="$(awk '{ print $1; exit }' "$_ss")"
	case "$_SUMME" in
		*[!0-9a-f]*|'') err "Pruefsummendatei unbrauchbar: '$_SUMME'"; log_close 2; exit 2 ;;
	esac
	[ "${#_SUMME}" = 64 ] || {
		err "Pruefsumme hat ${#_SUMME} statt 64 Zeichen."; log_close 2; exit 2; }
	_ist_summe="$(network_checksum "$QUELLE")"
	if [ "$_ist_summe" != "$_SUMME" ]; then
		err "Binary im Startbaum stimmt nicht mit seiner Pruefsumme ueberein."
		err "  Datei: $QUELLE"
		err "  erwartet $_SUMME, gemessen $_ist_summe"
		log_close 2; exit 2
	fi
fi

# --- Stand: aus welchem rust/-Baum wurde es gebaut? ----------------------
# Kein Abbruch, wenn der Baum neuer ist -- nur eine Meldung (smilez, 10.11.).
if [ -n "$STAND" ]; then
	_alt_c=""; _alt_h=""; _alt_v=""
	read -r _alt_c _alt_h _alt_v <"$STAND" 2>/dev/null || true
	_jetzt_h="$(rust_baum_hash "$RUST_BAUM" 2>/dev/null || true)"
	if [ -n "$_jetzt_h" ] && [ -n "$_alt_h" ] && [ "$_jetzt_h" != "$_alt_h" ]; then
		info "Hinweis: rust/ ist neuer als das Binary (gebaut aus $_alt_c, Version ${_alt_v:-unbekannt})."
		info "  Zwischen zwei Fassungen ist das normal; das Binary aus dem Baum wird genommen."
	elif [ -n "$_alt_c" ]; then
		info "Binary gebaut aus $_alt_c (rust/ seitdem unveraendert)."
	fi
fi

# --- Eigen ist, was im Manifest steht UND dessen Pruefsumme noch stimmt ---
_eigen_summe=""
if [ -e "$BIN" ] || [ -L "$BIN" ]; then
	_eigen_summe="$(manifest_list_von datei 55-rust | awk -F'\t' -v p="$BIN" '$1 == p { print $2 }')"
	if [ -z "$_eigen_summe" ]; then
		err "$BIN existiert und steht nicht im Manifest -- wird nicht ueberschrieben."
		log_close 2; exit 2
	fi
fi

# --- Schon da und stimmig? ----------------------------------------------
if [ -n "$_eigen_summe" ] && [ "$_eigen_summe" = "$_SUMME" ] && \
	[ "$(network_checksum "$BIN")" = "$_SUMME" ]; then
	info "Schon vorhanden und geprueft: $BIN"
	rust_stand_schreiben "$STAND" || \
		warn "state/rust-stand nicht schreibbar -- die naechste Meldung faellt aus."
	log_close 0; exit 0
fi

# --- Trockenlauf ---------------------------------------------------------
if is_dry_run; then
	info "[wuerde pruefen] $QUELLE (SHA-256 $(printf '%.12s' "$_SUMME")...) und starten"
	info "[wuerde pruefen] Version = chimera-tor $SOLL_V"
	info "[wuerde ablegen] $BIN (root, 755)"
	log_close 0; exit 0
fi

# --- Laufprobe: ein Binary, das nie gestartet wurde, ist eine Behauptung --
_tmp="$(tmp_path chimera-rust)" && rm -f "$_tmp" && mkdir -p "$_tmp" || {
	err "Kein Zwischenverzeichnis."; log_close 2; exit 2; }
trap 'rm -rf "$_tmp"' EXIT INT TERM

cp "$QUELLE" "$_tmp/$ASSET" || { err "Kopie nicht anlegbar."; log_close 2; exit 2; }
chmod 755 "$_tmp/$ASSET"
if [ "$(network_checksum "$_tmp/$ASSET")" != "$_SUMME" ]; then
	err "Kopie weicht von der Quelle ab -- nichts abgelegt."; log_close 2; exit 2
fi
_ist="$("$_tmp/$ASSET" --version 2>/dev/null || true)"
if [ "$_ist" != "chimera-tor $SOLL_V" ]; then
	err "Binary meldet '${_ist:-nichts}' statt 'chimera-tor $SOLL_V' -- nichts abgelegt."
	err "  Die VERSION der Quelle und das Binary im Startbaum passen nicht zusammen."
	log_close 2; exit 2
fi

# --- Ablegen: Nebendatei neben dem Ziel, dann umbenennen ------------------
_bin_neu=0
[ -d "$BIN_DIR" ] || _bin_neu=1
mkdir -p "$BIN_DIR" || { err "$BIN_DIR nicht anlegbar."; log_close 2; exit 2; }
chmod 755 "$BIN_DIR" 2>/dev/null || true
cp "$_tmp/$ASSET" "$BIN.neu" || { rm -f "$BIN.neu"; err "Kopie nach $BIN.neu gescheitert."; log_close 2; exit 2; }
chmod 755 "$BIN.neu"
mv -f "$BIN.neu" "$BIN" || { rm -f "$BIN.neu"; err "Umbenennen nach $BIN gescheitert."; log_close 2; exit 2; }

# Am Ergebnis pruefen, nicht am Exitcode.
if [ "$(network_checksum "$BIN")" != "$_SUMME" ]; then
	# Eine Datei, die nicht stimmt, darf nicht stehen bleiben: der Dienst
	# wuerde sie starten.
	rm -f "$BIN"
	err "$BIN hat nach dem Ablegen eine andere Pruefsumme -- entfernt. Lauf wiederholen."
	log_close 2; exit 2
fi

[ "$_bin_neu" = 1 ] && { manifest_has verzeich "$BIN_DIR" || manifest_record verzeich "$BIN_DIR" ""; }
# Eine alte Angabe (andere Summe) ersetzen: sonst bliebe sie stehen und der
# Rueckbau hielte die Datei fuer fremd.
if [ -n "$_eigen_summe" ] && [ -f "$CHIMERA_MANIFEST" ]; then
	_mf_neu="$CHIMERA_MANIFEST.neu"
	awk -F'\t' -v p="$BIN" -v m="55-rust" '!($1 !~ /^#/ && $2 == m && $3 == "datei" && $4 == p)' \
		"$CHIMERA_MANIFEST" >"$_mf_neu" && [ -s "$_mf_neu" ] && mv "$_mf_neu" "$CHIMERA_MANIFEST" || {
		rm -f "$_mf_neu"; err "Manifest nicht aktualisierbar."; log_close 2; exit 2; }
fi
manifest_record datei "$BIN" "$_SUMME"

rust_stand_schreiben "$STAND" || \
	warn "state/rust-stand nicht schreibbar -- die naechste Meldung faellt aus."

info "Abgelegt: $BIN (${LOKAL:+lokale Datei}${LOKAL:-gateway/$ASSET}, $(printf '%.12s' "$_SUMME"))"
log_close 0; exit 0
