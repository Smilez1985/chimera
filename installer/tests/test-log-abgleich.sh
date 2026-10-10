#!/bin/sh
# Tests fuer bin/log-abgleich.sh -- Dienstprotokolle RAM -> Karte, sofort
# (ExecStopPost) und in Ruhezeiten (Timer, --ruhig). DESIGN Regel 10r.
#
# Geprueft wird das echte Skript; Zeit wird ueber mtime der Dateien
# gestellt (touch -d), nicht durch Warten.
#
# CHIMERA_ABGLEICH ueberstimmt das Skript (Gegenprobe am Ende per sed).

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
SKRIPT="${CHIMERA_ABGLEICH:-$HERE/bin/log-abgleich.sh}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-abgleich.XXXXXX" 2>/dev/null)" || W=""
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

printf '=== Protokollabgleich (bin/log-abgleich.sh) ===\n'

# $1 Name. RAM-Ordner mit einer Datei, leere Karte.
feld() {
	F="$W/$1"; RAM="$F/run"; KARTE="$F/karte"
	mkdir -p "$RAM"
	printf 'zeile 1\n' >"$RAM/dienst-1.log"
}
# Alter einer Datei setzen: $1 Datei, $2 Sekunden in der Vergangenheit.
alt() { touch -d "@$(( $(date +%s) - $2 ))" "$1"; }
lauf() {
	set +e
	CHIMERA_LOG_RAM="$RAM" CHIMERA_LOG_KARTE="$KARTE" sh "$SKRIPT" "$@" >"$F/aus" 2>&1
	RC=$?
	set -e
}
auf_karte() { [ -f "$KARTE/dienst-1.log" ] && cmp -s "$RAM/dienst-1.log" "$KARTE/dienst-1.log" && echo ja || echo nein; }

# 1. Sofort (ExecStopPost): gleicht ab, egal wie frisch.
feld sofort
lauf
check "sofort: rc 0" "$RC" 0
check "sofort: Datei auf der Karte" "$(auf_karte)" ja

# 2. --ruhig, Datei gerade geschrieben -> noch nicht.
feld frisch
lauf --ruhig
check "ruhig, frisch geschrieben: nicht abgeglichen" "$(auf_karte)" nein

# 3. --ruhig, seit 200 s still -> abgleichen.
feld still
alt "$RAM/dienst-1.log" 200
lauf --ruhig
check "ruhig, 200 s still: abgeglichen" "$(auf_karte)" ja

# 4. --ruhig, Karte aktuell -> nichts schreiben (mtime der Karte bleibt).
_m1="$(stat -c %Y "$KARTE/dienst-1.log")"
lauf --ruhig
check "ruhig, Karte aktuell: Karte unveraendert" "$(stat -c %Y "$KARTE/dienst-1.log")" "$_m1"

# 5. Dauerschreiber: RAM immer frisch, Karte eine Stunde alt -> doch abgleichen.
feld dauer
mkdir -p "$KARTE"; printf 'alt\n' >"$KARTE/dienst-1.log"
alt "$KARTE/dienst-1.log" 4000
lauf --ruhig
check "Dauerschreiber: nach spaetestens 1 h abgeglichen" "$(auf_karte)" ja

# 6. Dauerschreiber, Karte erst 10 min alt -> warten.
feld dauer2
mkdir -p "$KARTE"; printf 'alt\n' >"$KARTE/dienst-1.log"
alt "$KARTE/dienst-1.log" 600
lauf --ruhig
check "Dauerschreiber, Karte 10 min alt: wartet" "$(auf_karte)" nein

# 7. Dienst aus (kein RAM-Ordner) -> rc 0, nichts.
feld aus; rm -rf "$RAM"
lauf --ruhig
check "kein RAM-Ordner: rc 0" "$RC" 0

# 8. Ohne Umgebung -> Befund, nicht stiller Erfolg.
F="$W/leer"; mkdir -p "$F"
set +e; sh "$SKRIPT" >"$F/aus" 2>&1; RC=$?; set -e
check "ohne CHIMERA_LOG_RAM/KARTE: rc 1" "$RC" 1

# 9. Stuecke (dienst-X.1.log) gehen mit.
feld stuecke
printf 'teil\n' >"$RAM/dienst-1.1.log"
lauf
if [ -f "$KARTE/dienst-1.1.log" ]; then ok "Stueck dienst-X.1.log auf der Karte"
else bad "Stueck dienst-X.1.log fehlt auf der Karte"; fi

# --- Gegenprobe: ohne die Stunden-Grenze bleibt der Dauerschreiber liegen.
if [ -z "${CHIMERA_ABGLEICH:-}" ]; then
	sed 's/\[ \$((_jetzt - _karte)) -lt "\$CHIMERA_LOG_SPAETESTENS" \]/true/' \
		"$SKRIPT" >"$W/mutant.sh"
	if cmp -s "$SKRIPT" "$W/mutant.sh"; then
		bad "Gegenprobe: Mutation griff nicht"
	else
		# Mutant muss neben lib/ liegen, er laedt ../lib/common.sh.
		mkdir -p "$W/m/bin" && cp "$W/mutant.sh" "$W/m/bin/log-abgleich.sh" && \
			ln -s "$HERE/lib" "$W/m/lib"
		SKRIPT="$W/m/bin/log-abgleich.sh"
		feld gp
		mkdir -p "$KARTE"; printf 'alt\n' >"$KARTE/dienst-1.log"
		alt "$KARTE/dienst-1.log" 4000
		lauf --ruhig
		check "Gegenprobe: ohne Stunden-Grenze bleibt Dauerschreiber liegen" "$(auf_karte)" nein
	fi
fi

# --- Gegenprobe 2: ohne den Erstabgleich-Bezug gleicht der erste Lauf
# sofort ab (Karte leer = Epoche 0 = "seit Ewigkeiten nicht abgeglichen").
if [ -z "${CHIMERA_ABGLEICH:-}" ]; then
	sed 's/^\t\[ "\$_karte" -eq 0 \] && _karte="\$(aelteste "\$QUELLE")"$/\t:/' \
		"$HERE/bin/log-abgleich.sh" >"$W/mutant2.sh"
	if cmp -s "$HERE/bin/log-abgleich.sh" "$W/mutant2.sh"; then
		bad "Gegenprobe 2: Mutation griff nicht"
	else
		mkdir -p "$W/m2/bin" && cp "$W/mutant2.sh" "$W/m2/bin/log-abgleich.sh" && \
			ln -s "$HERE/lib" "$W/m2/lib"
		SKRIPT="$W/m2/bin/log-abgleich.sh"
		feld gp2
		lauf --ruhig
		check "Gegenprobe 2: ohne Bezug gleicht frische Datei sofort ab" "$(auf_karte)" ja
	fi
fi

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
