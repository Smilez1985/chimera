#!/bin/sh
# Chimera installer -- Modul 55: Rust-Binaries aus dem Startbaum ablegen.
#
# DESIGN Regel 14: Was dauernd laeuft und nicht auf das Modell wartet, ist
# Rust. Gebaut wird NIE auf dem Geraet. Die fertigen Binaries liegen mit im
# Repo (`gateway/`, smilez 10.11.2026; `sohelper/`, 11.11.2026) und kommen mit
# jedem Release neu; dieser Schritt holt nichts nach und braucht kein Netz.
#
# Quelle: <Startbaum>/gateway/chimera-tor-aarch64
#           daneben: chimera-tor-aarch64.sha256   Pruefsumme (CI)
#           daneben: chimera-tor-aarch64.stand    "<commit> <hash> <version>"
#         <Startbaum>/sohelper/chimera-sohelper-aarch64 (.sha256 daneben)
#
# Geprueft wird je Binary: vorhanden und nicht leer, Pruefsumme, Architektur,
# Laufprobe (--version nennt die VERSION der Quelle). Die Arbeit steht in
# `lib/binary.sh` -- Schritt 99 (Ausfuehrer) braucht dieselbe Pruefung und
# bekommt sie von dort, nicht als zweite Fassung (Regel 10g).
#
# Gemeldet, aber KEIN Abbruch und kein Befund im Exitcode: ist der rust/-Baum
# im Startbaum neuer als der, aus dem das Binary gebaut wurde. Zwischen zwei
# Fassungen ist das der Normalfall (smilez, 10.11.2026).
#
# Was dieser Schritt hinterlaesst:
#   /opt/chimera/bin/chimera-tor          root, 755 (Manifest: datei, Summe)
#   /opt/chimera/bin/chimera-sohelper     root, 755 (Manifest: datei, Summe)
#   /opt/chimera/bin                      nur wenn er es anlegte (verzeich)
#   state/rust-stand                      <commit> <hash> <version> (Gateway)
# Er startet NICHTS: Nutzer, Unit und Socket kommen mit 98/99.
#
# Exitcode:
#   0  beide Binaries liegen da und haben die Version der Quelle (oder waren da)
#   1  Befund: ein Binary fehlt im Startbaum oder hat eine andere Architektur --
#      der Lauf geht weiter, das Programm fehlt
#   2  abgebrochen: Pruefsumme stimmt nicht, Binary laeuft nicht oder nennt
#      eine andere Version, fremde Datei am Zielort, keine Rechte

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/network.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/source.sh"
. "$_HERE/lib/binary.sh"

CHIMERA_STEP="55-rust"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "rust" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

log "Rust-Binaries (chimera-tor, chimera-sohelper)"

# Der Startbaum: der Baum, aus dem dieser Schritt laeuft (nach dem Neustart
# aus I8 ist das source/). Dort liegt gateway/ neben installer/.
BINARY_REPO="$(cd "$_HERE/.." && pwd)"
export BINARY_REPO
RUST_BAUM="$BINARY_REPO/rust"
[ -n "${CHIMERA_RUST_BAUM:-}" ] && RUST_BAUM="$CHIMERA_RUST_BAUM"

RC=0
for art in tor sohelper; do
	binary_aus_baum "$art" 55-rust
	_a=$?
	case "$_a" in
		0) : ;;
		1) [ "$RC" -lt 1 ] && RC=1 ;;
		*) RC=2 ;;
	esac
	[ "$RC" = 2 ] && break
	log ""
done

case "$RC" in
	0) : ;;
	1) warn "Ergebnis: mindestens ein Binary fehlt -- das Programm dazu laeuft nicht." ;;
	*) err "Ergebnis: abgebrochen, nichts weiter abgelegt." ;;
esac

log_close "$RC"
exit "$RC"
