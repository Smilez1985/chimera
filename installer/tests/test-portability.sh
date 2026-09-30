#!/bin/sh
# Pruefen, dass der Installer auf einem fremden System nicht bricht.
#
# Zwei Gefahren, beide schon beobachtet:
#
# 1. Nicht-ASCII in Shell-Dateien. Ohne gesetztes LANG -- und in einer
#    systemd-Unit ist es standardmaessig leer -- gibt die Konsole Umlaute
#    je nach Einstellung als Fragezeichen oder Kauderwelsch aus. Bei einer
#    Fehlermeldung ist das genau der Moment, in dem man sie lesen will.
#
# 2. Von der Locale abhaengige Sortierung und Zeichenklassen. `sort` und
#    `grep [a-z]` verhalten sich unter de_DE.UTF-8 anders als unter C.
#    Ein Installer, der je nach Umgebung anders sortiert, ist nicht
#    reproduzierbar.
#
# Der Test prueft das Ergebnis, nicht die Absicht: Er liest die Dateien und
# sucht die Bytes. Eine Zusage im Kommentar zaehlt nicht.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

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

# Alle Shell-Dateien des Installers -- Bibliotheken, Schritte, Laeufer,
# Tests und das Startprogramm ohne Endung.
#
# Ausgenommen sind die Pruefwerkzeuge selbst: Sie MUESSEN die verbotenen
# Muster im Quelltext enthalten, um nach ihnen suchen bzw. sie kuenstlich
# einbauen zu koennen. Ein Test, der sich selbst anklagt, ist nicht
# benutzbar.
#
# Die Ausnahme nennt eine ROLLE, nicht "diese Datei": Sonst faellt beim
# naechsten Pruefwerkzeug derselbe Fehler wieder an -- genau so passiert,
# als die Gegenprobe ins Repo kam und sofort sich selbst meldete.
# Die Liste wird beim Hinzufuegen eines Pruefwerkzeugs erweitert. Zweimal
# passiert: erst die Gegenprobe, dann test-uninstall-pairing.sh -- beide
# enthalten die verbotenen Muster, weil sie danach suchen.
#
# Bewusst eine ausdrueckliche Liste und keine Regel wie "jede Datei mit
# 'test' im Namen": Sonst waere jeder Test von der Pruefung befreit, und
# der ASCII-Riegel gaebe es fuer Tests nicht mehr.
is_meta_test() {
	case "$(basename "$1")" in
		test-portability.sh) return 0 ;;
		test-uninstall-pairing.sh) return 0 ;;
		counter-check-*.sh) return 0 ;;
		*) return 1 ;;
	esac
}

# Geprueft wird der Installer UND der Uninstaller. Beide laufen auf dem
# Zielgeraet, beide muessen portabel sein -- und der Uninstaller laeuft
# seltener, ein Fehler darin faellt also spaeter auf.
REPO_DIR="$(cd "$ROOT/.." && pwd)"

shell_files() {
	for _sf in $(find "$ROOT" "$REPO_DIR/uninstaller" -type f -name '*.sh' \
	             2>/dev/null | sort); do
		is_meta_test "$_sf" || echo "$_sf"
	done
	[ -f "$ROOT/chimera-install" ] && echo "$ROOT/chimera-install"
	[ -f "$REPO_DIR/uninstaller/chimera-uninstall" ] &&
		echo "$REPO_DIR/uninstaller/chimera-uninstall"
}

# Nur die Codezeilen einer Datei -- Kommentare und Leerzeilen weg.
#
# Grund: In common.sh und detect.sh steht "kein [[ ]]" bzw. ein
# Gegenbeispiel IM KOMMENTAR. Das ist kein Bashism, das ist eine Warnung
# davor. Wer nicht unterscheidet, meldet die Dokumentation als Fehler --
# und bringt damit den Autor dazu, die Warnung zu loeschen.
# Grenze, ehrlich benannt: Ein `#` innerhalb eines Strings wird hier
# faelschlich als Kommentarbeginn gelesen ("echo 'Farbe #ff0000'" wird
# abgeschnitten). Fuer die Bashism-Suche ist das harmlos -- abgeschnitten
# wird nur zu wenig gesucht, nie zu viel gemeldet. Fuer eine allgemeine
# Codeanalyse waere es zu grob.
code_only() {
	sed 's/[[:blank:]]*#.*$//' "$1" | grep -v '^[[:blank:]]*$'
}

printf '=== Portabilitaet ===\n'

# --- 1. Reines ASCII ------------------------------------------------------
#
# LC_ALL=C ist hier Pflicht: Ohne es wuerde grep die Bytes als UTF-8 deuten
# und ein Umlaut zaehlte als ein Zeichen innerhalb von [ -~] statt als zwei
# Bytes darueber. Der Test wuerde dann nichts finden -- und gruen sein,
# ohne zu pruefen.
FOUND=""
for f in $(shell_files); do
	if LC_ALL=C grep -q '[^ -~	]' "$f" 2>/dev/null; then
		FOUND="$FOUND $(basename "$f")"
	fi
done
check "alle Shell-Dateien sind reines ASCII" "${FOUND:-keine}" "keine"

# Gegenprobe: Der Test muss ein Nicht-ASCII-Zeichen auch finden. Ohne das
# beweist "keine Funde" nur, dass die Suche nichts tut.
TMPD="${TMPDIR:-/tmp}"
KOEDER="$TMPD/.chimera-koeder.$$.sh"

# Den Koeder mit awk erzeugen, nicht mit printf.
#
# Grund, in der CI gelernt: `printf '\xc3\xbc'` funktioniert in BusyBox,
# aber NICHT in dash -- POSIX kennt nur die Oktalform, nicht \x. Auf dash
# landete die Zeichenfolge literal in der Datei, der Koeder war reines
# ASCII, und die Gegenprobe meldete voellig zu Recht "Test ist blind".
#
# Ein Portabilitaetstest, dessen eigener Koeder nicht portabel ist, war
# eine schoene Ironie -- und ein echter Fund der Selbstpruefung. Ohne sie
# waere die ASCII-Pruefung auf dash stillschweigend blind gewesen.
#
# awk ist hier die verlaesslichere Wahl: sprintf mit Oktal ist in POSIX-awk
# festgelegt und verhaelt sich in mawk, busybox awk und gawk gleich.
awk 'BEGIN { printf "#!/bin/sh\necho \"Gr%cn\"\n", 252 }' >"$KOEDER" 2>/dev/null

# Und dann wird GEPRUEFT, ob der Koeder wirklich Nicht-ASCII enthaelt,
# statt es anzunehmen. Sonst prueft die Gegenprobe im Fehlerfall nur, dass
# ihr eigener Koeder kaputt ist -- und beschuldigt den Test.
if LC_ALL=C grep -q '[^ -~	]' "$KOEDER" 2>/dev/null; then
	ok "Gegenprobe: ein Umlaut wird gefunden"
elif [ ! -s "$KOEDER" ]; then
	bad "Gegenprobe unbrauchbar: Koeder konnte nicht erzeugt werden"
else
	# Der Koeder ist da, enthaelt aber kein Nicht-ASCII -- dann liegt es
	# am Erzeuger, nicht an der Suche. Das ist ein Mangel der Pruefung,
	# und er wird als solcher benannt (nicht als Mangel des Installers).
	bad "Gegenprobe unbrauchbar: Koeder enthaelt kein Nicht-ASCII (awk?)"
fi
rm -f "$KOEDER"

# --- 2. Locale wird festgelegt -------------------------------------------
#
# Der Installer muss LC_ALL selbst setzen. Sich auf die Umgebung zu
# verlassen heisst, dass Sortierung und Zeichenklassen vom Aufrufer
# abhaengen -- und der ist auf dem Zielgeraet ein systemd-Dienst mit
# leerem LANG.
if grep -q '^LC_ALL=C' "$ROOT/lib/common.sh" 2>/dev/null ||
   grep -q 'export LC_ALL=C' "$ROOT/lib/common.sh" 2>/dev/null; then
	ok "common.sh legt LC_ALL=C fest"
else
	bad "common.sh legt LC_ALL nicht fest -- Sortierung haengt am Aufrufer"
fi

# --- 3. Keine bashismen in /bin/sh-Skripten ------------------------------
#
# Auf DietPi ist /bin/sh dash, in der CI zusaetzlich BusyBox. Beide kennen
# weder Arrays noch [[ ]] noch ${x//y/z}. Der CI-Lauf hat das schon
# einmal gefunden, aber erst nach dem Push.
#
# Die Suche laeuft ueber code_only, damit ein Gegenbeispiel im Kommentar
# nicht als Fehler gilt. Und sie laeuft ueber DIESELBE Funktion wie die
# Gegenprobe weiter unten -- sonst bezeugt die Gegenprobe nur sich selbst.
# (Genau dieser Fehler steckte in der ersten Fassung des Secrets-Pruefers:
# Der Selbsttest rief sein eigenes grep, waehrend der echte Scan blind war.)
find_bashisms() {
	_fb_f="$1"
	_fb_hit=""
	_fb_code="$(code_only "$_fb_f")"
	# [[ ]] -- gibt es in dash/BusyBox nicht
	printf '%s\n' "$_fb_code" | grep -q '\[\[' &&
		_fb_hit="$_fb_hit [[]]"
	# ${var//muster/ersatz} -- Ersetzung gibt es nur in bash
	printf '%s\n' "$_fb_code" | grep -q '\${[A-Za-z_][A-Za-z_0-9]*//' &&
		_fb_hit="$_fb_hit \${//}"
	# arr=(...) -- Arrays gibt es nur in bash
	printf '%s\n' "$_fb_code" | grep -q '^[[:blank:]]*[A-Za-z_][A-Za-z_0-9]*=(' &&
		_fb_hit="$_fb_hit array"
	printf '%s' "$_fb_hit"
}

BASHISM=""
for f in $(shell_files); do
	hit="$(find_bashisms "$f")"
	[ -n "$hit" ] && BASHISM="$BASHISM $(basename "$f"):$(echo $hit | tr ' ' ',')"
done
check "keine bashismen" "${BASHISM:-keine}" "keine"

# Gegenprobe, durch dieselbe Funktion.
KOEDER2="$TMPD/.chimera-koeder2.$$.sh"
printf '#!/bin/sh\nif [ -n "$x" ]; then :; fi\n' >"$KOEDER2"
printf 'test_x() { if [%s -n "$y" ]]; then :; fi; }\n' '[' >>"$KOEDER2"
if [ -n "$(find_bashisms "$KOEDER2")" ]; then
	ok "Gegenprobe: ein echter Bashism wird gefunden"
else
	bad "Gegenprobe: Bashism NICHT gefunden -- die Suche ist blind"
fi

# Und die Umkehrung: Ein Gegenbeispiel im Kommentar darf NICHT anschlagen.
# Ohne diese Probe wuerde eine zu strenge Suche unbemerkt die Warnhinweise
# aus der Dokumentation treiben.
KOEDER3="$TMPD/.chimera-koeder3.$$.sh"
printf '#!/bin/sh\n# Achtung: kein %s -n "$x" ]] verwenden!\necho ok\n' '[[' >"$KOEDER3"
if [ -z "$(find_bashisms "$KOEDER3")" ]; then
	ok "Gegenprobe: ein Hinweis im Kommentar zaehlt nicht als Fehler"
else
	bad "Gegenprobe: Kommentar wird als Bashism gemeldet -- zu streng"
fi
rm -f "$KOEDER2" "$KOEDER3"

# --- 4. Schrittdateien tragen eine Kennung -------------------------------
#
# Die Kennung landet als Spalte im Manifest und ist das, worueber der
# Uninstaller seinen Gegenpart findet. Fehlt sie, schreibt der Schritt
# unter "unbekannt" -- und ist spaeter nicht zurueckbaubar.
#
# 10-check-system ist ausgenommen: Es prueft nur und aendert nichts, hat
# also nichts einzutragen.
MISSING=""
for f in "$ROOT"/steps/*.sh; do
	[ -f "$f" ] || continue
	b="$(basename "$f" .sh)"
	case "$b" in 10-check-system) continue ;; esac
	if ! grep -q "CHIMERA_STEP=\"$b\"" "$f" 2>/dev/null; then
		MISSING="$MISSING $b"
	fi
done
check "jeder aendernde Schritt setzt CHIMERA_STEP passend zum Dateinamen" \
	"${MISSING:-keine}" "keine"

# --- 5. Der Laeufer findet die Schritte wirklich -------------------------
#
# Beim Umbenennen von modules/ nach steps/ blieb in chimera-install eine
# Suche in "$HERE/modules" stehen. Der Laeufer haette KEINEN Schritt mehr
# gefunden -- und waere mit Exit 0 durchgelaufen, weil eine leere Liste
# kein Fehler ist. Stiller Erfolg, die teuerste Fehlerart.
#
# Deshalb wird hier das Ergebnis geprueft, nicht der Exitcode: Es MUESSEN
# Schritte aufgezaehlt werden, und es muessen so viele sein, wie Dateien
# vorhanden sind.
# --- 5a. Die Pruefwerkzeuge selbst -------------------------------------
#
# Sie sind von der Bashism-Suche ausgenommen (sie muessen die Muster
# enthalten). Von der ASCII-Regel sind sie NICHT ausgenommen -- sonst
# entstuende durch die Ausnahme ein blinder Fleck, und genau dort wuerde
# der naechste Umlaut einziehen.
META_BAD=""
for f in $(find "$ROOT" -type f -name '*.sh' | sort); do
	is_meta_test "$f" || continue
	if LC_ALL=C grep -q '[^ -~	]' "$f" 2>/dev/null; then
		META_BAD="$META_BAD $(basename "$f")"
	fi
done
check "auch die Pruefwerkzeuge sind reines ASCII" \
	"${META_BAD:-keine}" "keine"

DA="$(find "$ROOT/steps" -name '[0-9]*-*.sh' 2>/dev/null | grep -c . || true)"
GENANNT="$(sh "$ROOT/chimera-install" --list 2>/dev/null |
	grep -c '^  [0-9]' || true)"
check "der Laeufer zaehlt alle Schritte auf" "${GENANNT:-0}" "${DA:-0}"

if [ "${DA:-0}" -gt 0 ]; then
	ok "es gibt ueberhaupt Schritte ($DA)"
else
	bad "keine Schrittdateien gefunden -- Pfad falsch?"
fi

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$OK" "$BAD"
[ "$BAD" -eq 0 ]
