#!/bin/sh
# Tests fuer Architekturregel 10k -- unbekanntes Board warnt, verbietet nicht.
#
# Geprueft wird das Modul als Ganzes (nicht eine nachgebaute Logik, Regel 9):
# 10-check-system.sh laeuft gegen ein erfundenes Wurzelverzeichnis, und es wird
# sein echter Exitcode und seine echte Ausgabe bewertet.
#
# Jeder Test hat eine GEGENPROBE. Die wichtigste ist die gegen das alte
# Verhalten: Frueher brach das Modul bei einem unbekannten Board mit
# Exitcode 2 ab. Wuerde der Test das nicht bemerken, wuerde er nichts messen.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=/tmp}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
TMPDIR="$CHIMERA_TESTDIR"; export TMPDIR

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"
	else bad "$1 -- erwartet '$3', bekam '$2'"; fi
}
contains() {
	if printf '%s' "$2" | grep -qi -- "$3"; then ok "$1"
	else bad "$1 -- '$3' fehlt in der Ausgabe"; fi
}
lacks() {
	if printf '%s' "$2" | grep -qi -- "$3"; then bad "$1 -- '$3' kam doch vor"
	else ok "$1"; fi
}

# Erfundenes Wurzelverzeichnis. $1 model, $2 compatible (Leerzeichen-getrennt).
mkroot() {
	R="$(mktemp -d)"
	[ -n "$R" ] || { echo "mktemp lieferte nichts"; exit 1; }
	mkdir -p "$R/proc/device-tree" "$R/etc" "$R/boot" "$R/logs"
	[ -n "${1:-}" ] && printf '%s\0' "$1" >"$R/proc/device-tree/model"
	if [ -n "${2:-}" ]; then
		: >"$R/proc/device-tree/compatible"
		for c in $2; do printf '%s\0' "$c" >>"$R/proc/device-tree/compatible"; done
	fi
	printf 'ID=debian\nVERSION_CODENAME=trixie\n' >"$R/etc/os-release"
}

# Das Modul laufen lassen. $1 Wurzel, $2 stdin-Quelle, Rest: Umgebung.
# Setzt RC und OUT.
run_preflight() {
	_rp_root="$1"; _rp_in="$2"; shift 2
	set +e
	OUT="$(env CHIMERA_ROOT="$_rp_root" \
	           CHIMERA_LOG_DIR="$_rp_root/logs" \
	           CHIMERA_MODE=run \
	           "$@" \
	           sh "$HERE/steps/10-check-system.sh" <"$_rp_in" 2>&1)"
	RC=$?
	set -e
}

echo "== Unbekanntes Board (Regel 10k) =="

# Ein Pi 4: nicht getestet, aber kein Grund zu verbieten.
mkroot "Raspberry Pi 4 Model B Rev 1.4" "raspberrypi,4-model-b brcm,bcm2711"
printf 'ja\n' >"$R/antwort"

run_preflight "$R" "$R/antwort" CHIMERA_ASSUME_YES=1
check "Pi 4 bricht NICHT mit 2 ab" "$RC" "1"
contains "warnt ehrlich" "$OUT" "nicht erkannt"
contains "nennt das Risiko" "$OUT" "eigene Gefahr"
contains "sagt, was ungeprueft bleibt" "$OUT" "ungeprueft"
contains "verspricht kein Overlay" "$OUT" "KEIN Overlay"
lacks "schlaegt --force-board NICHT vor" "$OUT" "force-board"

# GEGENPROBE gegen das alte Verhalten: Exitcode 2 war Abbruch. Kaeme er
# hier heraus, waere die Regel nicht umgesetzt und dieser Test blind.
if [ "$RC" -eq 2 ]; then
	bad "GEGENPROBE: Modul bricht weiterhin ab (altes Verhalten)"
else
	ok "GEGENPROBE: der alte Abbruch mit 2 kommt nicht mehr"
fi
rm -rf "$R"

echo "== Die Entscheidung liegt beim Menschen =="

# Ablehnen heisst abbrechen.
mkroot "Raspberry Pi 4 Model B Rev 1.4" "raspberrypi,4-model-b"
printf 'nein\n' >"$R/antwort"
run_preflight "$R" "$R/antwort"
check "Ablehnung bricht ab" "$RC" "2"
contains "sagt, dass abgebrochen wurde" "$OUT" "Abgebrochen"
rm -rf "$R"

# Nicht-interaktiv ohne Schalter: kein stillschweigendes Durchlaufen.
mkroot "Raspberry Pi 4 Model B Rev 1.4" "raspberrypi,4-model-b"
run_preflight "$R" /dev/null
check "ohne Terminal und ohne Schalter: Abbruch" "$RC" "2"
contains "nennt den Schalter" "$OUT" "CHIMERA_ASSUME_YES"

# GEGENPROBE: derselbe Lauf MIT Schalter laeuft durch. Sonst koennte der
# Test oben auch aus einem ganz anderen Grund fehlschlagen.
run_preflight "$R" /dev/null CHIMERA_ASSUME_YES=1
check "GEGENPROBE: mit Schalter laeuft es durch" "$RC" "1"
rm -rf "$R"

echo "== Bekanntes Board bleibt unberuehrt =="

# Der Pi Zero 2 W hat ein Profil -- keine Warnung, keine Frage, Exitcode 0.
mkroot "Raspberry Pi Zero 2 W Rev 1.0" "raspberrypi,model-zero-2-w brcm,bcm2837"
run_preflight "$R" /dev/null
check "Zero 2 W wird unterstuetzt" "$RC" "0"
lacks "keine Risikofrage bei bekanntem Board" "$OUT" "eigene Gefahr"
rm -rf "$R"

echo "== confirm_risk selbst =="

R="$(mktemp -d)"; mkdir -p "$R/logs"
CHIMERA_LOG_DIR="$R/logs"; export CHIMERA_LOG_DIR
CHIMERA_LOGFILE=""; export CHIMERA_LOGFILE
CHIMERA_ROOT=""; export CHIMERA_ROOT
. "$HERE/lib/common.sh"

CHIMERA_MODE=run
CHIMERA_ASSUME_YES=1
confirm_risk "Test?" && ok "Schalter bejaht" || bad "Schalter wirkt nicht"

CHIMERA_ASSUME_YES=0
CHIMERA_MODE=dry
confirm_risk "Test?" && ok "Trockenlauf fragt nicht, blockiert aber auch nicht" \
	|| bad "Trockenlauf blockiert"

# Ohne Terminal steigt confirm_risk vor der Antwort aus -- das ist richtig
# so, macht aber jede Pruefung der Antwortauswertung durch confirm_risk
# hindurch blind. Deshalb wird answer_is_yes direkt aufgerufen: dieselbe
# Funktion, die confirm_risk benutzt, nicht eine nachgebaute (Regel 9).
CHIMERA_MODE=run
answer_is_yes "ja" && ok "'ja' bestaetigt" || bad "'ja' nicht erkannt"
answer_is_yes "j"  && ok "'j' bestaetigt"  || bad "'j' nicht erkannt"
answer_is_yes "JA" && ok "Grossschreibung zaehlt" || bad "'JA' nicht erkannt"

# Gegenproben: alles andere ist keine Zustimmung.
answer_is_yes "vielleicht" && bad "'vielleicht' galt als ja" \
	|| ok "Gegenprobe: 'vielleicht' ist kein ja"
answer_is_yes "" && bad "leere Eingabe galt als ja" \
	|| ok "Gegenprobe: Enter allein ist kein ja"
answer_is_yes "nein" && bad "'nein' galt als ja" \
	|| ok "Gegenprobe: 'nein' ist kein ja"
answer_is_yes "yes" && bad "'yes' galt als ja" \
	|| ok "Gegenprobe: englisches 'yes' zaehlt hier nicht"

# Und dass confirm_risk diese Funktion auch wirklich benutzt: mit
# Terminal-Ersatz laesst sich das hier nicht pruefen, wohl aber, dass ein
# fehlendes Terminal zur Ablehnung fuehrt statt zum Durchwinken.
confirm_risk "Test?" </dev/null && bad "ohne Terminal durchgewunken" \
	|| ok "ohne Terminal: keine Zustimmung"
rm -rf "$R"

echo ""
printf 'Ergebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
