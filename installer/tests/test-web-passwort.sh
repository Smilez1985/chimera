#!/bin/sh
# Tests fuer bin/web-passwort -- Web-Passwort neu setzen (Regel 5j/5m).
#
# Geprueft wird das echte Skript mit einer Attrappe fuer `--passwort-hash` und
# einer eigenen .env: kein root, kein systemd, keine echte Passwortdatei.
#
# CHIMERA_PASSWORT ueberstimmt das Skript (Gegenprobe am Ende per sed).

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
SKRIPT="${CHIMERA_PASSWORT:-$HERE/bin/web-passwort}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-passwort.XXXXXX" 2>/dev/null)" || W=""
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
hat() { # Name, Datei, Muster
	if grep -q "$3" "$2" 2>/dev/null; then ok "$1"; else bad "$1 -- '$3' fehlt"; fi
}

printf '=== Web-Passwort (bin/web-passwort) ===\n'

# Attrappe fuer das Gateway-Binary: gibt zu jeder Eingabe einen Hash aus.
cat >"$W/prog" <<'EOF'
#!/bin/sh
# --passwort-hash: Wert von stdin nehmen und einen erkennbaren Hash ausgeben
in="$(cat)"
printf 'pbkdf2-sha256$210000$salz$%s\n' "$(printf '%s' "$in" | cksum | tr ' ' '-')"
EOF
chmod 755 "$W/prog"

env_datei() { # $1 = Name; legt .env mit bekanntem Inhalt an
	E="$W/$1.env"
	printf 'CHIMERA_WEB_PORT=8080\nCHIMERA_WEB_PASSWORT_HASH=pbkdf2-sha256$1$alt$alt\nCHIMERA_WEB_BIND=0.0.0.0\n' >"$E"
	chmod 640 "$E"
}

lauf() { # Passwort auf stdin, Rest per Umgebung
	CHIMERA_WEB_ENV="$E" CHIMERA_WEB_PROG="$W/prog" CHIMERA_WEB_RESTART=0 \
		sh "$SKRIPT" >"$W/out" 2>"$W/err" || echo "rc=$?" >>"$W/out"
}

# 1. Gutes Passwort ersetzt den Hash und laesst die anderen Zeilen stehen.
env_datei gut
printf 'geheim-1234\ngeheim-1234\n' | lauf
hat "Hash ersetzt (nicht der alte)" "$E" '^CHIMERA_WEB_PASSWORT_HASH=pbkdf2-sha256\$2'
hat "andere Zeilen bleiben" "$E" '^CHIMERA_WEB_PORT=8080$'
hat "Bind bleibt" "$E" '^CHIMERA_WEB_BIND=0.0.0.0$'
hat "Erfolg wird gesagt" "$W/out" 'Passwort gesetzt'
check "Rechte bleiben 640" "$(ls -l "$E" | cut -c1-10)" "-rw-r-----"
check "keine NebenDatei liegen geblieben" "$(ls "$W"/*.neu 2>/dev/null | wc -l)" "0"
check "der Wert steht nicht in der Ausgabe" "$(grep -c 'geheim-1234' "$W/out" "$W/err" 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')" "0"

# 2. Zu kurz: abgelehnt, Datei unberuehrt.
env_datei kurz
cp "$E" "$W/vorher"
printf 'kurz\nkurz\n' | lauf
hat "zu kurz wird abgelehnt" "$W/err" 'mindestens 8 Zeichen'
check "Datei unberuehrt" "$(cat "$E")" "$(cat "$W/vorher")"

# 3. Zwei verschiedene Eingaben: abgelehnt.
env_datei ungleich
cp "$E" "$W/vorher2"
printf 'geheim-1234\ngeheim-9999\n' | lauf
hat "ungleiche Eingaben abgelehnt" "$W/err" 'nicht gleich'
check "Datei unberuehrt" "$(cat "$E")" "$(cat "$W/vorher2")"

# 4. Kein Hash vom Programm: abgelehnt, Datei unberuehrt.
env_datei kaputt
cp "$E" "$W/vorher3"
cat >"$W/prog2" <<'EOF'
#!/bin/sh
printf 'kein-hash\n'
EOF
chmod 755 "$W/prog2"
CHIMERA_WEB_ENV="$E" CHIMERA_WEB_PROG="$W/prog2" CHIMERA_WEB_RESTART=0 \
	printf 'geheim-1234\ngeheim-1234\n' | {
		CHIMERA_WEB_ENV="$E" CHIMERA_WEB_PROG="$W/prog2" CHIMERA_WEB_RESTART=0 \
			sh "$SKRIPT" >/dev/null 2>"$W/err4" || true
	}
hat "kein Hash: abgelehnt mit Grund" "$W/err4" 'Kein gueltiger Hash'
check "Datei unberuehrt" "$(cat "$E")" "$(cat "$W/vorher3")"

# 5. Fehlende .env: klare Auskunft statt Absturz.
CHIMERA_WEB_ENV="$W/gibtesnicht.env" CHIMERA_WEB_PROG="$W/prog" CHIMERA_WEB_RESTART=0 \
	sh "$SKRIPT" >/dev/null 2>"$W/err5" || true
hat "ohne .env kommt ein Satz" "$W/err5" 'ist Chimera installiert'

# 6. Gegenprobe: das Ersetzen ausgebaut -- der Test muss es merken.
printf '\n== Gegenprobe ==\n'
sed 's|^H="$H" awk .*|H="$H" true; cp "$ENV" "$T"|' "$SKRIPT" >"$W/mutant.sh"
if cmp -s "$SKRIPT" "$W/mutant.sh"; then
	bad "Gegenprobe: Muster nicht gefunden"
else
	env_datei gp
	printf 'geheim-1234\ngeheim-1234\n' | {
		CHIMERA_WEB_ENV="$E" CHIMERA_WEB_PROG="$W/prog" CHIMERA_WEB_RESTART=0 \
			sh "$W/mutant.sh" >/dev/null 2>&1 || true
	}
	if grep -q 'pbkdf2-sha256\$1\$alt' "$E"; then
		ok "Gegenprobe: ohne Ersetzen bleibt der alte Hash (Test ist scharf)"
	else
		bad "Gegenprobe: alter Hash verschwunden, obwohl nichts ersetzt wurde"
	fi
fi

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
