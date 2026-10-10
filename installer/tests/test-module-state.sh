#!/bin/sh
# Tests fuer lib/module.sh -- "liegt die .ko da" ist nicht "laedt sie".
#
# Geprueft wird die echte Funktion, in einem erfundenen Wurzelverzeichnis
# und mit Attrappen fuer modprobe/depmod (Regel 9: nicht die Logik
# nachbauen, sondern das echte Skript laufen lassen).
#
# Warum das wichtig ist: Vorher pruefte Schritt 40 nur, ob eine Datei
# `snd-soc-whisplay*` unter /lib/modules liegt. Ein Modul, das nicht laedt
# -- ABI-inkompatibel, oder der Geraetebaum-Eintrag fehlt noch -- bekam
# damit ein "gebaut" und ging als Erfolg durch (Regel 10j).
#
# Gegenprobe: eine Kopie von module.sh, in der der Ladeversuch zu `true`
# verkuerzt ist. Sie muss "geladen" melden, wo die echte "nicht_geladen"
# sagt. Bliebe die Gegenprobe gruen, misst der Test nichts.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
HERE="$(cd "$HERE" && pwd)"
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
mkdir -p "$R/proc/sys/kernel" "$R/lib/modules" "$W/bin"
printf '%s\n' "$KVER" >"$R/proc/sys/kernel/osrelease"

# --- Attrappen -------------------------------------------------------------
# modprobe liest ihren Ausgang aus einer Datei: 0 = laedt, 1 = scheitert.
# depmod hinterlaesst eine Spur, damit pruefbar ist, dass sie VOR dem
# Laden laeuft.
cat >"$W/bin/modprobe" <<EOF
#!/bin/sh
echo "\$*" >>"$W/modprobe-aufrufe.txt"
exit "\$(cat "$W/modprobe-rc" 2>/dev/null || echo 0)"
EOF
cat >"$W/bin/depmod" <<EOF
#!/bin/sh
echo "\$*" >>"$W/depmod-aufrufe.txt"
exit 0
EOF
chmod +x "$W/bin/modprobe" "$W/bin/depmod"
PATH="$W/bin:$PATH"; export PATH

# --- Aufrufer --------------------------------------------------------------
# In einer eigenen Datei, damit die Quotes nicht dreifach verschachtelt
# werden. $1 Fassung von module.sh, $2 Muster, $3 Name.
cat >"$W/aufruf.sh" <<'EOF'
#!/bin/sh
. "$HERE/lib/common.sh"
. "$1"
kernel_module_state "$2" "$3"
EOF
chmod +x "$W/aufruf.sh"

# lauf $1 = Fassung. Setzt OUT und RC.
#
# Der PATH wird pro Aufruf gesetzt, nicht nur einmal im Skript: Einer
# Umgebung, die ihn zwischenzeitlich veraendert (oder Attrappen und echte
# Werkzeuge mischt), wird damit begegnet, statt auf die Reihenfolge zu
# hoffen. Das echten modprobe/depmod auf einem CI-Runner sind Faehnlinge
# dieser Art.
lauf() {
	set +e
	OUT="$(CHIMERA_ROOT="$R" PATH="$W/bin:$PATH" sh "$W/aufruf.sh" "$1" \
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
[ "$OUT" = "geladen" ] || {
	# Diagnose: welche Werkzeuge sieht der innere Aufruf wirklich?
	_diag="$(CHIMERA_ROOT="$R" PATH="$W/bin:$PATH" sh -c \
		'command -v depmod || echo "kein depmod";
		 command -v modprobe || echo "kein modprobe";
		 printf "PATH=%s\n" "$PATH"' 2>&1 | sed 's/^/        /')"
	printf '  DIAG  innerer Aufruf:\n%s\n' "$_diag"
}
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
