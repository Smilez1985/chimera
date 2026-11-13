#!/bin/sh
# Ablage gebauter Binaries im Repo (DESIGN Regel 14, "Binary im Repo").
#
# Nimmt ein gebautes, statisches Programm (aarch64-musl) und legt es in seinen
# Ordner, zusammen mit Pruefsumme und Stand:
#
#   gateway/chimera-tor-aarch64           --art tor
#   sohelper/chimera-sohelper-aarch64     --art sohelper
#   <name>.sha256                         Pruefsumme (Format wie am Release)
#   <name>.stand                          "<commit> <hash des rust/-Baums> <version>"
#
# Geprueft wird VOR dem Ablegen: das Binary laeuft, nennt "<programm> <VERSION>"
# der Quelle, und seine Pruefsumme steht danach in der .sha256-Datei. Was nicht
# geprueft ist, wird nicht abgelegt -- es faellt sonst erst auf dem Geraet auf.
#
# **Ein Weg, zwei Programme.** Zwei getrennte Werkzeuge fuer dieselbe Handlung
# waeren der Anfang davon, dass sie auseinanderlaufen (Regel 10g); die Ordner
# und Namen stehen deshalb in Tabelle `ABLEGE_ARTEN`, nicht im Ablauf.
#
# Aufruf:
#   tools/binary-ablegen.sh <binary> --art <tor|sohelper> [--commit <kurz>] [--ohne-probe]
#
#   --commit <kurz>  Commit, aus dem das Binary gebaut wurde (Vorgabe: der
#                    Kopf des Repos, sonst "lokal")
#   --ohne-probe     das Binary NICHT starten (fremde Architektur). Dann bleibt
#                    die Version ungeprueft; das Werkzeug sagt es.
#
# Exitcode: 0 abgelegt, 1 Befund (nichts abgelegt), 2 abgebrochen.

set -eu

_HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$_HERE/.." && pwd)"
. "$REPO/installer/lib/common.sh"
. "$REPO/installer/lib/network.sh"
. "$REPO/installer/lib/source.sh"

# art | Ordner im Repo | Dateiname | Programmname in --version
ABLEGE_ARTEN="tor sohelper fdpass"

art_ordner() {
	case "$1" in
		tor)      printf '%s\n' gateway ;;
		sohelper) printf '%s\n' sohelper ;;
		fdpass)   printf '%s\n' sohelper ;;
		*) return 1 ;;
	esac
}

art_asset() {
	case "$1" in
		tor)      printf '%s\n' chimera-tor-aarch64 ;;
		sohelper) printf '%s\n' chimera-sohelper-aarch64 ;;
		fdpass)   printf '%s\n' chimera-fdpass-aarch64 ;;
		*) return 1 ;;
	esac
}

art_programm() {
	case "$1" in
		tor)      printf '%s\n' chimera-tor ;;
		sohelper) printf '%s\n' chimera-sohelper ;;
		fdpass)   printf '%s\n' chimera-fdpass ;;
		*) return 1 ;;
	esac
}

usage() {
	cat >&2 <<'EOF'
tools/binary-ablegen.sh <binary> --art <tor|sohelper> [--commit <kurz>] [--ohne-probe]

  Legt ein gebautes Binary in seinen Ordner (gateway/, sohelper/), mit
  Pruefsumme und Stand. Daneben: <name>.sha256, <name>.stand.
EOF
}

BIN=""
COMMIT=""
ART=""
PROBE=1
while [ $# -gt 0 ]; do
	case "$1" in
		--art)        ART="${2:?--art braucht einen Wert}"; shift 2 ;;
		--commit)     COMMIT="${2:?--commit braucht einen Wert}"; shift 2 ;;
		--ohne-probe) PROBE=0; shift ;;
		-h|--help)    usage; exit 0 ;;
		-*)           err "Unbekannte Option: $1"; usage; exit 2 ;;
		*)
			[ -z "$BIN" ] || { err "Nur ein Binary."; usage; exit 2; }
			BIN="$1"; shift ;;
	esac
done

[ -n "$BIN" ] || { usage; exit 2; }
[ -n "$ART" ] || { err "Ohne --art kein Ziel (tor|sohelper)."; usage; exit 2; }
case " $ABLEGE_ARTEN " in
	*" $ART "*) : ;;
	*) err "Unbekannte Art '$ART' (erlaubt: $ABLEGE_ARTEN)."; exit 2 ;;
esac
[ -f "$BIN" ] || { err "$BIN fehlt."; exit 2; }
[ -s "$BIN" ] || { err "$BIN ist leer."; exit 2; }

ASSET="$(art_asset "$ART")"
PROG="$(art_programm "$ART")"
ZIEL="$REPO/$(art_ordner "$ART")"

SOLL_V="$(tr -d ' \t\r\n' <"$REPO/VERSION" 2>/dev/null || true)"
[ -n "$SOLL_V" ] || { err "VERSION im Repo fehlt."; exit 2; }
[ -d "$REPO/rust" ] || { err "rust/ fehlt im Repo."; exit 2; }

# Herkunft: der Commit, aus dem gebaut wurde. Ohne Angabe der Kopf des Repos.
if [ -z "$COMMIT" ]; then
	if [ -d "$REPO/.git" ]; then
		COMMIT="$(git -C "$REPO" rev-parse --short=7 HEAD 2>/dev/null || true)"
	fi
	[ -n "$COMMIT" ] || COMMIT="lokal"
fi
case "$COMMIT" in
	*[!0-9a-zA-Z._-]*) err "Commit '$COMMIT' hat unerwartete Zeichen."; exit 2 ;;
esac

# Laufprobe: ein Binary, das nie gestartet wurde, ist eine Behauptung (Regel 14).
if [ "$PROBE" = 1 ]; then
	chmod 755 "$BIN" 2>/dev/null || true
	_ist="$("$BIN" --version 2>/dev/null || true)"
	if [ "$_ist" != "$PROG $SOLL_V" ]; then
		err "Binary meldet '${_ist:-nichts}' statt '$PROG $SOLL_V'."
		err "  Stimmt die VERSION im Repo und das Binary zusammen? Sonst nicht ablegen."
		exit 1
	fi
	info "Laufprobe: $PROG $SOLL_V"
else
	warn "Ohne Laufprobe: die Version des Binaries bleibt ungeprueft."
fi

mkdir -p "$ZIEL" || { err "$ZIEL nicht anlegbar."; exit 2; }
SUMME="$(network_checksum "$BIN")"
[ "${#SUMME}" = 64 ] || { err "Pruefsumme unbrauchbar: '$SUMME'"; exit 2; }
BAUM="$(rust_baum_hash "$REPO/rust" 2>/dev/null || true)"
[ -n "$BAUM" ] || { err "Der rust/-Baum liess sich nicht hashen."; exit 2; }

cp "$BIN" "$ZIEL/$ASSET.neu" || { rm -f "$ZIEL/$ASSET.neu"; err "Kopie nicht anlegbar."; exit 2; }
chmod 755 "$ZIEL/$ASSET.neu"
[ "$(network_checksum "$ZIEL/$ASSET.neu")" = "$SUMME" ] || {
	rm -f "$ZIEL/$ASSET.neu"; err "Kopie weicht von der Quelle ab."; exit 2; }
mv -f "$ZIEL/$ASSET.neu" "$ZIEL/$ASSET"

printf '%s  %s\n' "$SUMME" "$ASSET" >"$ZIEL/$ASSET.sha256"
printf '%s %s %s\n' "$COMMIT" "$BAUM" "$SOLL_V" >"$ZIEL/$ASSET.stand"

# Am Ergebnis pruefen, nicht am Exitcode.
[ "$(network_checksum "$ZIEL/$ASSET")" = "$SUMME" ] || {
	err "Die abgelegte Datei hat eine andere Pruefsumme."; exit 2; }
[ "$(awk '{ print $1; exit }' "$ZIEL/$ASSET.sha256")" = "$SUMME" ] || {
	err "Die Pruefsummendatei stimmt nicht."; exit 2; }

info "Abgelegt: $ZIEL/$ASSET"
info "  Pruefsumme: $(printf '%.12s' "$SUMME")...  (in $ASSET.sha256)"
info "  Stand:      $COMMIT, rust/-Baum $(printf '%.12s' "$BAUM")..., Version $SOLL_V"
log_close 0
