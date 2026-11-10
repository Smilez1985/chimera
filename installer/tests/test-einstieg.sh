#!/bin/sh
# Tests fuer den Einstieg chimera-installer.sh in der Repo-Wurzel.
#
# Die Zusage (DESIGN, Regel "Installerhelfer"): Der Nutzer ruft EINE Datei
# auf, und sie reicht nur weiter -- dieselben Optionen, derselbe Exitcode
# wie installer/chimera-install. Geprueft wird deshalb der Vergleich mit dem
# inneren Installer, nicht ein nachgebauter Sollwert.
#
#   * vorhanden und ausfuehrbar
#   * --list und --help: gleiche Ausgabe wie der innere Installer, nicht leer
#   * der Exitcode kommt durch (unbekannte Option -> 2)
#   * Aufruf aus einem fremden Verzeichnis
#   * ohne den inneren Installer: benannter Abbruch, rc 2
#   * der Hinweis "mit sudo neu starten" nennt den Einstieg
#
# Sicherung: Ein Einstieg, der die Optionen verliert, wuerde als root einen
# ECHTEN Installerlauf starten -- genau diese Mutation faehrt die Gegenprobe.
# Davor steht eine systemd-run-Attrappe im Suchpfad: Ohne systemd-run koppelt
# der Installer keinen Lauf ab. Wirkt sie nicht, bricht der Test ab, statt es
# darauf ankommen zu lassen.
#
# Warum nicht ueber eine id-Attrappe: Die BusyBox der CI (Ubuntu
# busybox-static 1.36.1) nimmt ihre eingebauten Befehle VOR dem Suchpfad --
# `id -u` meldet dort 0, egal was im Suchpfad liegt (CI-Lauf 42914638466).
# systemd-run ist in keiner Shell eingebaut. Die id-Attrappe bleibt fuer die
# eine Pruefung, die einen gewoehnlichen Nutzer braucht; wo sie nicht wirkt
# und der Test als root laeuft, wird diese Pruefung als uebersprungen
# gemeldet, nicht als gruen.
#
# CHIMERA_EINSTIEG_BAUM ueberstimmt den geprueften Baum -- damit faehrt
# counter-check-einstieg.sh denselben Test gegen verfaelschte Fassungen.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
BAUM="${CHIMERA_EINSTIEG_BAUM:-$(cd "$HERE/.." && pwd)}"
E="$BAUM/chimera-installer.sh"
I="$BAUM/installer/chimera-install"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-einstieg.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 -- erwartet '$3', bekam '$2'"; fi; }
bilanz() {
	printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
	[ "$FAIL" -eq 0 ]
}

printf '=== Einstieg chimera-installer.sh ===\n'

# --- Attrappen ------------------------------------------------------------
# systemd-run und systemctl schreiben jeden Aufruf mit und scheitern. Kein
# Aufruf dieses Tests darf dort ankommen. id meldet einen gewoehnlichen
# Nutzer -- in Shells, die den Suchpfad vor ihren eingebauten Befehlen fragen.
S="$W/attrappen"; mkdir -p "$S" "$W/logs"
GESTARTET="$W/gestartet"; : >"$GESTARTET"
printf '#!/bin/sh\n[ "${1:-}" = -u ] && { echo 1000; exit 0; }\nexit 1\n' >"$S/id"
for _p in systemd-run systemctl; do
	printf '#!/bin/sh\necho "%s $*" >>"%s"\nexit 1\n' "$_p" "$GESTARTET" >"$S/$_p"
done
chmod 755 "$S/id" "$S/systemd-run" "$S/systemctl"

# Der Einstieg startet den Installer mit `sh` -- genau diese Shell muss die
# Attrappe sehen. Geprueft am Ergebnis: ein Probeaufruf muss mitgeschrieben
# sein.
PATH="$S:$PATH" sh -c 'systemd-run --probe' >/dev/null 2>&1 || true
if ! grep -q '^systemd-run --probe$' "$GESTARTET"; then
	bad "Schutz-Attrappe wirkt nicht (systemd-run nicht ersetzt) -- Test nicht ausfuehrbar"
	bilanz; exit 1
fi
: >"$GESTARTET"
ok "Schutz-Attrappe wirkt (systemd-run ist ersetzt)"

# Sieht der Installer hier einen gewoehnlichen Nutzer? Entweder ist der
# Aufrufer einer, oder die id-Attrappe wirkt.
_wer="$(PATH="$S:$PATH" sh -c 'id -u' 2>/dev/null || true)"
case "$_wer" in
	''|0) OHNE_ROOT=0 ;;
	*)    OHNE_ROOT=1 ;;
esac

# $1 Programm, Rest: seine Argumente. Setzt OUT und RC.
fahr() {
	_fp="$1"; shift
	set +e
	OUT="$(env PATH="$S:$PATH" CHIMERA_LOG_DIR="$W/logs" \
	           CHIMERA_HELFER_STATUS="$W/helfer.status" \
	           sh "$_fp" "$@" 2>&1)"
	RC=$?
	set -e
}

# --- 1. Vorhanden und ausfuehrbar -----------------------------------------
if [ ! -f "$E" ]; then
	bad "chimera-installer.sh liegt in der Repo-Wurzel"
	bilanz; exit 1
fi
ok "chimera-installer.sh liegt in der Repo-Wurzel"
if [ -x "$E" ]; then ok "ausfuehrbar markiert"; else bad "ausfuehrbar markiert"; fi

# --- 2. --list: wie der innere Installer, und nicht leer -------------------
fahr "$I" --list; INNEN="$OUT"; INNEN_RC="$RC"
check "innerer Installer: --list rc 0 (Messaufbau stimmt)" "$INNEN_RC" 0
fahr "$E" --list
check "--list: rc 0" "$RC" 0
check "--list: gleiche Ausgabe wie installer/chimera-install" "$OUT" "$INNEN"
_n="$(printf '%s\n' "$OUT" | grep -c '^  [0-9]' || true)"
if [ "$_n" -ge 1 ]; then ok "--list nennt Module ($_n)"; else bad "--list nennt kein Modul"; fi

# --- 3. --help: wie der innere Installer -----------------------------------
fahr "$I" --help; INNEN="$OUT"
fahr "$E" --help
check "--help: rc 0" "$RC" 0
check "--help: gleiche Ausgabe wie installer/chimera-install" "$OUT" "$INNEN"

# --- 4. Der Exitcode kommt durch -------------------------------------------
fahr "$E" --gibt-es-nicht
check "unbekannte Option: rc 2" "$RC" 2

# --- 5. Aufruf aus einem fremden Verzeichnis -------------------------------
fahr "$I" --list; INNEN="$OUT"
_alt="$(pwd)"; cd /
fahr "$E" --list
cd "$_alt"
check "aus fremdem Verzeichnis: gleiche Modulliste" "$OUT" "$INNEN"

# --- 6. Ohne den inneren Installer -----------------------------------------
mkdir -p "$W/allein"
cp "$E" "$W/allein/chimera-installer.sh"
fahr "$W/allein/chimera-installer.sh" --list
check "ohne inneren Installer: rc 2" "$RC" 2
if printf '%s' "$OUT" | grep -qF 'installer/chimera-install fehlt'; then
	ok "ohne inneren Installer: benannt"
else
	bad "ohne inneren Installer: benannt -- Ausgabe: $OUT"
fi

# --- 7. Der Hinweis ohne root nennt den Einstieg ---------------------------
# Ein echter Lauf (keine Option) als gewoehnlicher Nutzer: abgelehnt, mit dem
# Befehl, der stattdessen gilt. Der soll die Datei nennen, die der Nutzer
# aufgerufen hat.
if [ "$OHNE_ROOT" = 1 ]; then
	fahr "$E"
	check "ohne root: abgelehnt (rc 2)" "$RC" 2
	if printf '%s' "$OUT" | grep -qF "sudo sh $E"; then
		ok "Hinweis nennt den Einstieg"
	else
		bad "Hinweis nennt den Einstieg -- Ausgabe: $OUT"
	fi
else
	printf '  uebersprungen  ohne root: Hinweis nennt den Einstieg (Lauf als root, und diese Shell nimmt ihr eingebautes id)\n'
fi

# --- 8. Kein Aufruf hat einen Lauf gestartet --------------------------------
if [ -s "$GESTARTET" ]; then
	bad "kein Lauf gestartet -- aufgerufen: $(tr '\n' ';' <"$GESTARTET")"
else
	ok "kein Lauf gestartet"
fi

bilanz
