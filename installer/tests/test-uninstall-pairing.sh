#!/bin/sh
# Setzt Architekturregel 10l durch: Jeder Installationsschritt hat sein
# Gegenstueck, und jede Aenderung landet im Manifest.
#
# Ohne diesen Test ist die Regel eine Absichtserklaerung. Mit ihm ist ein
# Schritt ohne Rueckbau ein roter Lauf -- also nicht mehr vergessbar.
#
# Der Test prueft das ERGEBNIS, nicht die Absicht: Er sucht die Dateien und
# liest ihren Inhalt. Ein Kommentar "Rueckbau folgt spaeter" zaehlt nicht.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
INST="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$INST/.." && pwd)"
UNINST="$REPO/uninstaller"

OK=0
BAD=0
ok()  { OK=$((OK+1));  printf '  ok    %s\n' "$1"; }
bad() { BAD=$((BAD+1)); printf '  FEHL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"; else
		bad "$1"
		printf '        erwartet: %s\n        bekommen: %s\n' "$3" "$2"
	fi
}

# Schritte, die nur pruefen und nichts aendern, brauchen kein Gegenstueck.
# Die Liste ist ausdruecklich -- wer einen Schritt hier eintraegt, sagt
# damit zu, dass er nichts veraendert. Das wird unten nachgeprueft.
nur_pruefend() {
	case "$1" in
		10-check-system) return 0 ;;
		*) return 1 ;;
	esac
}

printf '=== Installation und Rueckbau paarweise ===\n'

# --- 1. Gibt es den Uninstaller ueberhaupt? ------------------------------
if [ -d "$UNINST/steps" ]; then
	ok "uninstaller/steps/ vorhanden"
else
	bad "uninstaller/steps/ fehlt -- Regel 10l ist nicht umgesetzt"
	printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$OK" "$BAD"
	exit 1
fi

if [ -x "$UNINST/chimera-uninstall" ] || [ -f "$UNINST/chimera-uninstall" ]; then
	ok "chimera-uninstall vorhanden"
else
	bad "chimera-uninstall fehlt"
fi

# --- 2. Zu jedem aendernden Schritt ein Gegenstueck ----------------------
#
# Die Nummer verbindet die beiden: 20-install-packages <-> 20-remove-*.
# Auf den Namen hinter der Nummer wird NICHT bestanden -- "remove" und
# "restore" sind beides legitime Gegenstuecke, je nachdem ob etwas
# hinzugefuegt oder ersetzt wurde.
FEHLT=""
for f in "$INST"/steps/[0-9]*-*.sh; do
	[ -f "$f" ] || continue
	b="$(basename "$f" .sh)"
	nur_pruefend "$b" && continue
	nr="${b%%-*}"
	if ! ls "$UNINST"/steps/"$nr"-*.sh >/dev/null 2>&1; then
		FEHLT="$FEHLT $b"
	fi
done
check "jeder aendernde Schritt hat ein Gegenstueck" "${FEHLT:-keins}" "keins"

# --- 3. Umgekehrt: kein Gegenstueck ohne Vorlage -------------------------
#
# Ein Rueckbauschritt fuer etwas, das nie installiert wird, entfernt auf
# Verdacht. Das ist genauso ein Fehler, nur in der anderen Richtung.
WAISE=""
for f in "$UNINST"/steps/[0-9]*-*.sh; do
	[ -f "$f" ] || continue
	b="$(basename "$f" .sh)"
	nr="${b%%-*}"
	if ! ls "$INST"/steps/"$nr"-*.sh >/dev/null 2>&1; then
		WAISE="$WAISE $b"
	fi
done
check "kein Rueckbauschritt ohne Installationsschritt" "${WAISE:-keiner}" "keiner"

# --- 4. Wer aendert, traegt ins Manifest ein -----------------------------
#
# Geprueft wird am Quelltext: Ein Schritt, der eine der schreibenden
# Systemoperationen benutzt, muss auch eine manifest_-Funktion aufrufen.
#
# Die Liste der Operationen ist bewusst knapp und nennt nur, was wirklich
# am System schreibt. `printf >>` auf eine Fremddatei war der real
# aufgetretene Fall: Schritt 40 haengte an config.txt an, ohne einzutragen.
OHNE=""
for f in "$INST"/steps/[0-9]*-*.sh; do
	[ -f "$f" ] || continue
	b="$(basename "$f" .sh)"
	nur_pruefend "$b" && continue

	code="$(sed 's/[[:blank:]]*#.*$//' "$f")"
	schreibt=0
	printf '%s\n' "$code" | grep -q 'apt-get install\|apk add\|network_apt' && schreibt=1
	printf '%s\n' "$code" | grep -q 'usermod\|gpasswd' && schreibt=1
	printf '%s\n' "$code" | grep -q '>>[[:blank:]]*"\$BOOT_CFG"' && schreibt=1
	printf '%s\n' "$code" | grep -q 'install -D\|mkdir -p[[:blank:]]*"\$' && schreibt=1

	[ "$schreibt" -eq 1 ] || continue

	# Nur SCHREIBENDE Manifestfunktionen zaehlen. `manifest_has`,
	# `manifest_list` und `manifest_report` lesen -- sie halten nichts
	# fest.
	#
	# Erste Fassung fragte nur nach "manifest_" irgendwo in der Datei.
	# Die Gegenprobe hat das entlarvt: Im nachgebauten Fehlerfall blieb
	# ein `manifest_has` stehen, und der Test war gruen -- fuer genau den
	# Fall, fuer den er geschrieben wurde. Ein Test, der die Anwesenheit
	# eines Wortes prueft statt der Wirkung, prueft nichts.
	if ! printf '%s\n' "$code" | grep -q \
	   'manifest_record\|manifest_line\|manifest_apt'; then
		OHNE="$OHNE $b"
	fi
done
check "jeder aendernde Schritt ruft eine SCHREIBENDE manifest_-Funktion" \
	"${OHNE:-keiner}" "keiner"

# --- 5. Schritte, die als "nur pruefend" gelten, aendern wirklich nichts -
#
# Sonst waere die Ausnahmeliste eine Hintertuer: Wer einen Schritt dort
# eintraegt, koennte die Regel umgehen. Also wird die Zusage geprueft.
LUEGT=""
for f in "$INST"/steps/[0-9]*-*.sh; do
	[ -f "$f" ] || continue
	b="$(basename "$f" .sh)"
	nur_pruefend "$b" || continue
	code="$(sed 's/[[:blank:]]*#.*$//' "$f")"
	if printf '%s\n' "$code" | grep -q \
	   'apt-get install\|apk add\|usermod\|gpasswd\|network_apt'; then
		LUEGT="$LUEGT $b"
	fi
done
check "als 'nur pruefend' gelistete Schritte aendern nichts" \
	"${LUEGT:-keiner}" "keiner"

# --- 6. Der Rueckbau unterscheidet neu von vorher_da ---------------------
#
# Das ist der Kern des Manifests. Ein Rueckbauschritt, der Pakete anfasst,
# ohne `vorher_da` zu lesen, deinstalliert dem Nutzer seine Werkzeugkette.
BLIND=""
for f in "$UNINST"/steps/[0-9]*-*.sh; do
	[ -f "$f" ] || continue
	b="$(basename "$f" .sh)"
	code="$(sed 's/[[:blank:]]*#.*$//' "$f")"
	# Faesst dieser Schritt Pakete oder Zeilen an?
	printf '%s\n' "$code" | grep -q \
		'apt-get remove\|apk del\|grep -vxF' || continue
	if ! printf '%s\n' "$code" | grep -q 'vorher_da'; then
		BLIND="$BLIND $b"
	fi
done
check "jeder Rueckbauschritt liest vorher_da" "${BLIND:-keiner}" "keiner"

# --- 7. Gegenprobe: Der Test findet ein fehlendes Gegenstueck -----------
#
# Ohne diese Probe beweist "alles gepaart" nur, dass die Suche nichts tut.
TMPD="${TMPDIR:-/tmp}"
GP="$TMPD/.chimera-pairing-gp.$$"
mkdir -p "$GP/installer/steps" "$GP/uninstaller/steps"
printf '#!/bin/sh\nCHIMERA_STEP="90-install-ghost"\napt-get install -y x\nmanifest_apt x\n' \
	>"$GP/installer/steps/90-install-ghost.sh"
# absichtlich KEIN Gegenstueck anlegen
GP_FEHLT=""
for f in "$GP"/installer/steps/[0-9]*-*.sh; do
	b="$(basename "$f" .sh)"
	nr="${b%%-*}"
	ls "$GP"/uninstaller/steps/"$nr"-*.sh >/dev/null 2>&1 ||
		GP_FEHLT="$GP_FEHLT $b"
done
if [ -n "$GP_FEHLT" ]; then
	ok "Gegenprobe: ein fehlendes Gegenstueck wird gefunden"
else
	bad "Gegenprobe: fehlendes Gegenstueck NICHT gefunden -- Test ist blind"
fi
rm -rf "$GP"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$OK" "$BAD"
[ "$BAD" -eq 0 ]
