#!/bin/sh
# Gegenprobe zu test-helfer.sh (Regel 9): je eine Zusage von lib/helfer.sh
# verfaelschen, der Test muss an der erwarteten Stelle rot werden.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HERE/lib/helfer.sh"
TEST="$HERE/tests/test-helfer.sh"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
G="$(mktemp -d "$CHIMERA_TESTDIR/chimera-helfer-gp.XXXXXX" 2>/dev/null)" || G=""
if [ -z "$G" ] || [ ! -d "$G" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$G"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

printf '=== Gegenprobe Installerhelfer ===\n'

if CHIMERA_HELFER_LIB="$LIB" sh "$TEST" >"$G/basis.txt" 2>&1; then
	ok "unveraendert gruen"
else
	bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"
fi

mutation() {
	_m="$G/$1.sh"
	sed "$2" "$LIB" >"$_m"
	if cmp -s "$LIB" "$_m"; then bad "$1: Mutation griff nicht"; return; fi
	if CHIMERA_HELFER_LIB="$_m" sh "$TEST" >"$G/$1.txt" 2>&1; then
		bad "$1: Test blieb gruen"
	elif grep -q "FAIL  $3" "$G/$1.txt"; then
		ok "$1: rot bei '$3'"
	else
		bad "$1: rot, aber nicht bei '$3'"; grep 'FAIL' "$G/$1.txt" | head -3
	fi
}



# M1: Die Arbeit laeuft in der Sitzung statt abgekoppelt.
mutation kein-systemd-run \
	's|systemd-run --unit="\$CHIMERA_HELFER_UNIT"|true; true|' \
	"Helfer: Exitcode des Laufs kommt an (42)"

# M2: Falscher Unit-Name (der Nutzer soll sie unter dem Namen finden).
mutation falscher-name \
	's|: "\${CHIMERA_HELFER_UNIT:=chimera-installhelper}"|: "${CHIMERA_HELFER_UNIT:=installer}"|' \
	"Helfer: eigener Unit-Name"

# M3: Kein --collect: die Unit bleibt nach dem Lauf liegen.
mutation ohne-collect \
	's| --collect||' \
	"Helfer: transient, wird nach dem Lauf entfernt"

# M4: Nicht oneshot: der Exitcode des Laufs kommt nicht an.
mutation ohne-oneshot \
	's| --service-type=oneshot||' \
	"Helfer: als oneshot (Exitcode kommt an)"

# M5: Der Helfer erkennt sich selbst nicht und koppelt endlos neu ab.
mutation ohne-helfer-schalter \
	's|--setenv="CHIMERA_HELFER=1" ||' \
	"Helfer: Schalter fuer den Helfer selbst"

# M6: Das Passwort steht auf der Befehlszeile.
mutation passwort-auf-kommandozeile \
	's|--setenv="CHIMERA_HELFER_ENV=\$_hs_env"|--setenv="CHIMERA_WEB_PASSWORT=geheim-123"|' \
	"Helfer: kein Passwort auf der Befehlszeile"

# M7: Die Umgebung geht nicht mit -> der Helfer laeuft mit Vorgaben.
mutation umgebung-vergessen \
	's|--setenv="CHIMERA_HELFER_ENV=\$_hs_env" ||' \
	"Helfer: Umgebung ueber eine Datei"

# M8: Zweiter Aufruf startet einen zweiten Lauf.
mutation zweiter-lauf \
	's|^\tif helfer_aktiv; then$|	if false; then|' \
	"Wiederaufruf: kein zweiter systemd-run"

# M9: Der Exitcode des Helfers wird ignoriert.
mutation exitcode-ignoriert \
	's|^\tinfo "Helfer beendet mit Exitcode \$_hw_rc."$|	info "Helfer beendet."|;s|^\treturn "\$_hw_rc"$|	return 0|' \
	"Helfer: Exitcode des Laufs kommt an (42)"

# M10: Start scheitert, wird aber als Erfolg gemeldet.
mutation startfehler-still \
	's|^\t\terr "Der Helfer startete nicht (systemd-run)."$|	:|' \
	"Start scheitert: benannt"

# M11: Die Umgebungsdatei ist fuer alle lesbar.
mutation envdatei-offen \
	's|( umask 077; : >"\$_hes_d" )|( umask 022; : >"$_hes_d" )|;s|^\t\[ "\$(stat -c %a "\$_hes_d" 2>/dev/null)" = 600 \] \|\| chmod 600 "\$_hes_d" 2>/dev/null$|\t:|' \
	"Umgebungsdatei: Modus 600"

# M12: Die Klammer haelt nichts an.
mutation klammer-ohne-stop \
	's|^\t\tsystemctl stop "\$_ka_u" >/dev/null 2>&1 \|\| {|\t\ttrue \&\& {|' \
	"Klammer an: nichts laeuft mehr"

# M13: Die Klammer startet in falscher Reihenfolge (Dienste vor Sockets).
mutation klammer-falsche-reihenfolge \
	's|^\tfor _ke_u in \$KLAMMER_SOCKETS \$KLAMMER_DIENSTE \$KLAMMER_TIMER; do$|	for _ke_u in $KLAMMER_DIENSTE $KLAMMER_SOCKETS $KLAMMER_TIMER; do|' \
	"Klammer aus: Reihenfolge (Sockets vor Diensten)"

# M14: Die Klammer startet auch, was vorher nicht lief.
mutation klammer-startet-alles \
	's|^\t\tcase "\$_ke_lief" in \*" \$_ke_u "\*) ;; \*) continue ;; esac$|		:|' \
	"Klammer aus: Reihenfolge (Sockets vor Diensten)"

# M15: Ein Dienst, der nach dem Lauf nicht laeuft, gilt als Erfolg.
mutation nachweis-fehlt \
	's|err "laeuft nach dem Lauf nicht: \$_ke_u"; _ke_befund=1;|: ;|' \
	"Klammer aus: stummer Start -> rc 1"

# M16: Fremde Variablen werden uebernommen.
mutation fremde-variablen \
	's|^\t\tcase "\$_hel_k" in CHIMERA_\*) : ;; \*) continue ;; esac$|		:|' \
	"Umgebung: fremde Variable wird nicht uebernommen"

# M17: Die Umgebungsdatei bleibt liegen (mit Passwort darin).
mutation envdatei-bleibt \
	's|^\trm -f "\$_hel_d"$|	:|' \
	"Umgebung: Datei wird danach geloescht"

# M19: Das Gateway wird direkt gestartet statt geweckt (am Pi gemessen: es beendet
# sich dann mit Code 2, weil es keinen Socket von systemd bekommt).
mutation gateway-direkt \
	's|KLAMMER_DIENSTE:=chimera.service}|KLAMMER_DIENSTE:=chimera.service chimera-tor.service}|' \
	"Klammer aus: Gateway nicht direkt gestartet"

printf '\nErgebnis: %s ok, %s fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
