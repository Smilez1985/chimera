#!/bin/sh
# Tests fuer lib/module.sh -- "liegt die .ko da" ist nicht "laedt sie".
#
# Geprueft wird die echte Funktion, in einem erfundenen Wurzelverzeichnis
# (Regel 9: nicht die Logik nachbauen, sondern das echte Skript laufen
# lassen). Die Werkzeuge `depmod` und `modprobe` stehen als SHELL-FUNKTIONEN
# in der Pruefumgebung bereit, nicht als Dateien im PATH:
#
#   * Der Test prueft die LOGIK von kernel_module_state -- ob depmod vor
#     dem Laden laeuft und ob der Ladefall/Nichtladefall richtig ausgelesen
#     wird. Das zu pruefen gehoert nicht zur Funktion, sondern zur
#     Umgebung: einen Weg zu suchen, der je Rechner anders aussieht
#     (Ubuntu hat echte modprobe/depmod in /usr/sbin), macht den Test
#     abhaengig von Dingen, die er nicht einrichtet. Genau das war der
#     erste CI-Lauf, der hier rot war, waehrend er lokal gruen war.
#   * Funktionen statt Dateien sind unter jeder Shell gleich und
#     unanfaellig gegen den PATH des CI-Runners.
#
# Gegenprobe: eine Kopie von module.sh, in der der Ladeversuch zu `true`
# verkuerzt ist. Sie muss "geladen" melden, wo die echte "nicht_geladen"
# sagt. Bliebe die Gegenprobe gruen, misst der Test nichts.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }

W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-modul.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"
	else bad "$1 -- erwartet '$3', bekam '$2'"; fi
}

printf '=== Kernelmodul: Zustand statt Datei ===\n'

KVER="9.9.9-test"
R="$W/root"
mkdir -p "$R/proc/sys/kernel" "$R/lib/modules"
printf '%s\n' "$KVER" >"$R/proc/sys/kernel/osrelease"

# --- Aufrufer --------------------------------------------------------------
#
# In einer eigenen Datei, damit die Attrappen als Funktionen zur Verfuegung
# stehen. Ausgang des (Attrappen-)modprobe liest er aus $W/modprobe-rc.
# $1 Fassung von module.sh, $2 Muster, $3 Name.
cat >"$W/aufruf.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"

# Attrappen als FUNKTIONEN: unter jeder Shell gleich, unanfaellig gegen
# den PATH des CI-Runners. Spurdateien zeigen, dass und was aufgerufen
# wurde.
#
# Die PFADE kommen als UMGEBUNG vom Test, nicht als `$W` an dieser Stelle:
# Der heredoc ist quoted und expandiert nicht, und eine Variable an dieser
# Stelle zu erwarten, waere ein stiller Leerlauf -- genau der Befund der
# ersten Fassung: Die Attrappen "wurden nicht aufgerufen", weil ihr Ziel
# nach / zeigte statt in das Testverzeichnis.
: "${SPUR_DEPMOD:?keine Spurdatei uebergeben}"
: "${SPUR_MODPROBE:?keine Spurdatei uebergeben}"
: "${MODPROBE_RC:?keine RC-Datei uebergeben}"

depmod() {
	printf '%s\n' "$*" >>"$SPUR_DEPMOD"
	return 0
}

modprobe() {
	printf '%s\n' "$*" >>"$SPUR_MODPROBE"
	return "$(cat "$MODPROBE_RC" 2>/dev/null || echo 0)"
}

# Die Attributpruefung kennt nur diese beiden Namen. Jede andere Antwort
# waere eine andere Umgebung als die, die der Test einrichtet.
have_cmd() {
	case "$1" in
		depmod|modprobe) return 0 ;;
		*) return 1 ;;
	esac
}

. "$1"
kernel_module_state "$2" "$3"
EOF
chmod +x "$W/aufruf.sh"

# lauf $1 = Fassung. Setzt OUT und RC.
lauf() {
	set +e
	OUT="$(CHIMERA_ROOT="$R" \
		SPUR_DEPMOD="$W/depmod-aufrufe.txt" \
		SPUR_MODPROBE="$W/modprobe-aufrufe.txt" \
		MODPROBE_RC="$W/modprobe-rc" \
		sh "$W/aufruf.sh" "$1" \
		'snd-soc-whisplay*' 'snd-soc-whisplay-soundcard' 2>&1)"
	RC=$?
	set -e
}

# --- Fall 1: keine .ko -----------------------------------------------------
printf 0 >"$W/modprobe-rc"
lauf "$HERE/lib/module.sh"
check "keine .ko -> nicht_gebaut" "$OUT" "nicht_gebaut"

# --- Fall 2: .ko da, laedt -------------------------------------------------
mkdir -p "$R/lib/modules/$KVER/kernel/sound/soc/codecs"
: >"$R/lib/modules/$KVER/kernel/sound/soc/codecs/snd-soc-whisplay-soundcard.ko"
printf 0 >"$W/modprobe-rc"
rm -f "$W/modprobe-aufrufe.txt" "$W/depmod-aufrufe.txt"
lauf "$HERE/lib/module.sh"
check ".ko da und ladbar -> geladen" "$OUT" "geladen"
if [ -s "$W/depmod-aufrufe.txt" ]; then ok "depmod laeuft vor dem Ladeversuch"
else bad "depmod wurde nicht aufgerufen -- Abhaengigkeiten bleiben alt"; fi
if grep -q 'snd-soc-whisplay-soundcard' "$W/modprobe-aufrufe.txt" 2>/dev/null; then
	ok "modprobe wurde mit dem Modulnamen aufgerufen"
else bad "modprobe wurde nicht aufgerufen"; fi

# --- Fall 3: .ko da, laedt NICHT -------------------------------------------
printf 1 >"$W/modprobe-rc"
lauf "$HERE/lib/module.sh"
check ".ko da, laedt nicht -> nicht_geladen" "$OUT" "nicht_geladen"

# --- Gegenprobe: die alte Fassung ------------------------------------------
# Der Ladeversuch wird zu `true` verkuerzt -- genau das alte Verhalten
# "Datei existiert, also fertig".
sed 's/modprobe "\$_kms_name" 2>\/dev\/null/true/' \
	"$HERE/lib/module.sh" >"$W/module-alt.sh"
if grep -q 'true; then' "$W/module-alt.sh"; then
	ok "Gegenprobe vorbereitet (Ladeversuch entfernt)"
else
	bad "Gegenprobe nicht vorbereitet -- Mutation griff nicht"
fi
lauf "$W/module-alt.sh"
check "Gegenprobe: alte Fassung meldet geladen" "$OUT" "geladen"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
