#!/bin/sh
# Tests fuer Schritt 50 -- Python-Umgebung.
#
# Das Modul wird als Ganzes geprueft, in einer Kopie des Repos (Regel 9:
# nicht die Logik nachbauen). Die Kopie traegt ein replacement der
# requirements.txt, das KEINE Netzabhaengigkeit hat: `pip` ist im
# frischen venv immer da, pip install pip ist online, pip install auf
# eine vorhandene Fassung meldet "already satisfied" ohne Netz. Damit
# ist der ECHTE Lauf messbar, auch im CI.
#
# Gegenprobe: eine Kopie mit GEBROCHENER Verdrahtung (requirements.txt
# leer oder .pth auf ein fehlendes Verzeichnis). Sie muss abbrechen,
# wo die echte durchlaeuft.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }

W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-python.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap '[ -n "${KEEP:-}" ] || rm -rf "$W"' EXIT INT TERM

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

printf '=== Python-Umgebung (Modul 50) ===\n'

# Baumkopie: lib und der Schritt, unter CHIMERA_ROOT als Wurzel.
# requirements.txt wird JEDER Kopie mitgegeben, je Fall anders. Der echte
# Lauf nimmt die ECHTE Anforderungen-Datei aus dem Repo (Pillow) -- der
# Nachweis `python -m chimera --pruefen` braucht sie, und der Test soll
# den echten Weg fahren, nicht einen behelfsmaessigen.
mkbaum() {
	# BAUM ist die Systemwurzel, BAUM/repo das Repo darin -- getrennt wie
	# auf dem Geraet. Lag das Repo frueher selbst an der Wurzel, landete
	# productive/ IM Repo, und der Inhaltshash des Repos aenderte sich
	# durch die eigene Kopie (Kopie "wich ab").
	WURZEL="$W/$1"
	BAUM="$WURZEL/repo"
	mkdir -p "$BAUM/installer/steps" "$WURZEL/etc"
	cp -r "$HERE/lib" "$BAUM/installer/lib"
	cp "$HERE/steps/50-python.sh" "$BAUM/installer/steps/50-python.sh"
	mkdir -p "$BAUM/src"
	cp -r "$HERE/../src/chimera" "$BAUM/src/chimera" 2>/dev/null || true
	cp "$HERE/../requirements.txt" "$BAUM/requirements.txt" 2>/dev/null || true
	# Auch die Konfigurationsvorlage gehoert zur Kopie (Schritt 50 legt
	# /etc/chimera/.env daraus ab).
	cp "$HERE/../.env.example" "$BAUM/.env.example" 2>/dev/null || true
	printf 'ID=debian\nVERSION_CODENAME=trixie\n' >"$WURZEL/etc/os-release" 2>/dev/null \
		|| true
	CHIMERA_ROOT="$WURZEL"; export CHIMERA_ROOT
	CHIMERA_MANIFEST="$WURZEL/opt/chimera/state/manifest.tsv"
	CHIMERA_LOG_DIR="$WURZEL/logs"; export CHIMERA_LOG_DIR
	mkdir -p "$(dirname "$CHIMERA_MANIFEST")" "$CHIMERA_LOG_DIR"
	MANIFEST="$CHIMERA_MANIFEST"
}

# Anforderungen einsetzen. Ohne Argument: die echte Datei aus dem Repo.
setze_anforderungen() {
	if [ -n "${1:-}" ]; then
		printf '%s\n' "$1" >"$BAUM/requirements.txt"
	else
		cp "$HERE/../requirements.txt" "$BAUM/requirements.txt"
	fi
}

# Den Schritt fahren. $1 Modus. Setzt RC und OUT.
fahr() {
	set +e
	OUT="$(env CHIMERA_ROOT="$WURZEL" CHIMERA_MANIFEST="$MANIFEST" \
	           CHIMERA_LOG_DIR="$CHIMERA_LOG_DIR" CHIMERA_MODE="$1" \
	           sh "$BAUM/installer/steps/50-python.sh" 2>&1)"
	RC=$?
	set -e
}

# --- Fall 1: requirements fehlt -------------------------------------------
mkbaum "anforderungen-fehlt"
setze_anforderungen ""
rm -f "$BAUM/requirements.txt"
fahr dry
check "requirements fehlt -> rc 2" "$RC" "2"
contains "Abbruch wird benannt" "$OUT" "requirements.txt fehlt"

# --- Fall 2: requirements leer --------------------------------------------
mkbaum "anforderungen-leer"
setze_anforderungen "# nur ein Kommentar"
fahr dry
check "nur Kommentare -> rc 2" "$RC" "2"
contains "leere Liste wird benannt" "$OUT" "nur Kommentare"

# --- Fall 2b: venv importierbar, ensurepip fehlt (Debian ohne python3-venv) -
# Am chimera-pi (11.10.2026) gemessen: `import venv` gelingt, `python3 -m
# venv` scheitert. Der Schritt muss das als FEHLEND erkennen. Nachgestellt
# mit einer python3-Huelle, die ensurepip sperrt (echtes Python dahinter).
mkbaum "ohne-ensurepip"
setze_anforderungen "pip"
mkdir -p "$W/bin-ohne-ensurepip"
_echt="$(command -v python3)"
cat >"$W/bin-ohne-ensurepip/python3" <<EOF
#!/bin/sh
exec "$_echt" -c 'import sys
class _Sperre:
    def find_spec(self, name, path=None, target=None):
        if name == "ensurepip" or name.startswith("ensurepip."):
            raise ModuleNotFoundError("No module named %r" % name)
        return None
sys.meta_path.insert(0, _Sperre())
import runpy
sys.argv = sys.argv[1:]
if sys.argv and sys.argv[0] == "-c":
    exec(sys.argv[1], {"__name__": "__main__"})
elif len(sys.argv) > 1 and sys.argv[0] == "-m":
    sys.argv = sys.argv[1:]
    runpy.run_module(sys.argv[0], run_name="__main__", alter_sys=True)
else:
    runpy.run_path(sys.argv[0], run_name="__main__")
' "\$@"
EOF
chmod +x "$W/bin-ohne-ensurepip/python3"
if "$W/bin-ohne-ensurepip/python3" -c 'import venv' 2>/dev/null &&
   ! "$W/bin-ohne-ensurepip/python3" -c 'import ensurepip' 2>/dev/null; then
	ok "Huelle: venv da, ensurepip gesperrt (Messaufbau stimmt)"
else
	bad "Huelle bildet den Geraetezustand nicht nach"
fi
_alt_path="$PATH"; PATH="$W/bin-ohne-ensurepip:$PATH"
fahr dry
PATH="$_alt_path"
lacks "ohne ensurepip: NICHT 'kein Paket noetig'" "$OUT" "kein Paket noetig"
contains "ohne ensurepip: python3-venv wird geholt" "$OUT" "wuerde holen"

# Gegenprobe: die alte Pruefung (`import venv`) haelt das Geraet fuer fertig.
sed "s/if python3 -c 'import venv, ensurepip' >\/dev\/null 2>&1; then/if python3 -c 'import venv' >\/dev\/null 2>\&1; then/" \
	"$BAUM/installer/steps/50-python.sh" >"$W/50-alt.sh"
if cmp -s "$BAUM/installer/steps/50-python.sh" "$W/50-alt.sh"; then
	bad "Gegenprobe ensurepip: Mutation griff nicht"
else
	cp "$W/50-alt.sh" "$BAUM/installer/steps/50-python.sh"
	PATH="$W/bin-ohne-ensurepip:$PATH"; fahr dry; PATH="$_alt_path"
	contains "Gegenprobe ensurepip: alte Pruefung sagt 'kein Paket noetig'" "$OUT" "kein Paket noetig"
fi

# --- Fall 2c: halbes venv ohne pip (Rest eines gescheiterten Laufs) --------
# Am chimera-pi (11.10.2026): venv mit Interpreter, aber ohne pip -- der
# naechste Lauf hielt es fuer fertig. Nachgestellt mit --without-pip.
mkbaum "halbes-venv"
setze_anforderungen "pip"
python3 -m venv --without-pip "$WURZEL/opt/chimera/productive/venv" >/dev/null 2>&1
fahr dry
contains "halbes venv: wird als nicht fertig erkannt" "$OUT" "[wuerde anlegen]"
# Gegenprobe: die alte venv_ready (ohne pip-Pruefung) haelt es fuer fertig.
sed 's/ \&\& "\$PY" -m pip --version >\/dev\/null 2>\&1$//' \
	"$BAUM/installer/steps/50-python.sh" >"$W/50-alt2.sh"
if cmp -s "$BAUM/installer/steps/50-python.sh" "$W/50-alt2.sh"; then
	bad "Gegenprobe halbes venv: Mutation griff nicht"
else
	cp "$W/50-alt2.sh" "$BAUM/installer/steps/50-python.sh"
	fahr dry
	contains "Gegenprobe halbes venv: alte Pruefung sagt 'vorhanden'" "$OUT" "venv vorhanden"
fi

# --- Fall 3: Trockenlauf aendert nichts -----------------------------------
mkbaum "trocken"
setze_anforderungen "pip"
fahr dry
check "Trockenlauf -> rc 0" "$RC" "0"
contains "announced" "$OUT" "[wuerde anlegen]"
if [ -d "$WURZEL/opt/chimera/productive/venv" ]; then
	bad "Trockenlauf hat ein venv angelegt"
else ok "Trockenlauf hat kein venv angelegt"; fi

# --- Fall 4: echter Lauf in der Kopie -------------------------------------
mkbaum "echt"
setze_anforderungen ""
fahr run
check "echter Lauf -> rc 0" "$RC" "0"
if [ -d "$WURZEL/opt/chimera/productive/venv" ]; then
	ok "venv wurde angelegt"
else bad "venv wurde NICHT angelegt"; fi
if [ -f "$CHIMERA_MANIFEST" ]; then
	ok "Manifest liegt in der Testwurzel"
else bad "Manifest fehlt"; fi
contains "Nachweis nannt" "$OUT" "nachweisbar"

# Und die Verdrahtung stimmt: die .pth zeigt auf die Kopie.
_PTH="$(find "$WURZEL/opt/chimera/productive/venv" -name 'chimera.pth' 2>/dev/null | head -1)"
if [ -n "$_PTH" ] && [ -f "$_PTH" ]; then
	_ZIEL="$(cat "$_PTH")"
	if [ "$_ZIEL" = "$WURZEL/opt/chimera/productive/code/src" ]; then
		ok ".pth verweist auf productive/code (nicht auf den Startbaum)"
	else
		bad ".pth verweist auf das Falsche: $_ZIEL (erwartet productive/code/src)"
	fi
else bad ".pth wurde nicht angelegt"; fi

# --- Fall 4a: Umgebungskonfiguration --------------------------------------
# Die Vorlage wird als /etc/chimera/.env abgelegt, mit Platzhaltern; die
# abgelegte Datei bleibt bei einem zweiten Lauf unangetastet (dort stehen
# spaeter echte Werte).
ENVF="$WURZEL/opt/chimera/config/.env"
if [ -f "$ENVF" ]; then
	ok "Umgebungskonfiguration abgelegt"
else bad "Umgebungskonfiguration fehlt: $ENVF"; fi
if grep -q 'OLLAMA_API_BASE=http://dein-server:11434' "$ENVF" 2>/dev/null; then
	ok "Vorlage enthaelt Platzhalter, keine echten Werte"
else bad "Vorlage ohne bekannten Platzhalter"; fi
if [ "$(stat -c %a "$ENVF" 2>/dev/null)" = "600" ]; then
	ok "Konfiguration ist 600"
else bad "Rechte der Konfiguration: $(stat -c %a "$ENVF" 2>/dev/null)"; fi
if [ ! -d "$W/trocken/opt/chimera/config" ]; then
	ok "Trockenlauf hat keine Konfiguration abgelegt"
else bad "Trockenlauf hat nach config/ geschrieben"; fi

# --- Fall 5: idempotent ----------------------------------------------------
# Der zweite Lauf kommt in den Zustand "bereits nachweisbar" und aendert
# nichts Wesentliches. Messbar: die Zeitdauer der venv-Erstellung ist
# zweimal gleich, aber einfacher ist die Ausgabe.
mkbaum "zweiter"
setze_anforderungen ""
fahr run
_rc_erster="$RC"
_mk_erster="$BAUM"
_mk_erster_pth="$(find "$WURZEL/opt/chimera/productive/venv" -name 'chimera.pth' 2>/dev/null | wc -l)"
fahr run
check "zweiter Lauf -> rc 0" "$RC" "$_rc_erster"
_pth_jetzt="$(find "$WURZEL/opt/chimera/productive/venv" -name 'chimera.pth' 2>/dev/null | wc -l)"
check "nur eine .pth, nicht doppelt" "$_pth_jetzt" "1"

# Die Konfiguration wird vom zweiten Lauf NICHT ueberschrieben -- dort
# stehen spaeter echte Werte. Also einen Wert eintragen und nachmessen.
ENVZ="$WURZEL/opt/chimera/config/.env"
printf '# vom Nutzer\nOLLAMA_API_BASE=http://ollama-server:11434\n' >>"$ENVZ"
fahr run
check "zweiter Lauf -> rc 0 (Feld 5)" "$RC" "$_rc_erster"
if grep -q 'vom Nutzer' "$ENVZ" && grep -q 'ollama-server' "$ENVZ"; then
	ok "Nutzerwerte blieben stehen (kein Ueberschreiben)"
else bad "zweiter Lauf hat die Konfiguration ueberschrieben"; fi

# --- Gegenprobe: ohne Verdrahtung ----------------------------------------
# Der Schritt wird geaendert: die .pth wird NICHT geschrieben. Dann muss
# der Lauf melden, dass das Modul nicht lauffaehig ist (rc 2).
# Der mutierte Schritt bleibt im Baum (unter steps/): der Schritt loest
# seine lib relativ zu $0 auf (dirname "$0"/..). Ausserhalb von $BAUM
# faende er sie nicht und braeche aus dem falschen Grund ab.
mkbaum "gegenprobe"
setze_anforderungen ""
sed 's|write_atomic "\$_pth" |true |' "$BAUM/installer/steps/50-python.sh" \
	>"$BAUM/installer/steps/50-python-gegenprobe.sh"
set +e
OUT="$(env CHIMERA_ROOT="$WURZEL" CHIMERA_MANIFEST="$MANIFEST" \
           CHIMERA_LOG_DIR="$CHIMERA_LOG_DIR" CHIMERA_MODE=run \
           sh "$BAUM/installer/steps/50-python-gegenprobe.sh" 2>&1)"
RC=$?
set -e
check "Gegenprobe: ohne Verdrahtung -> rc 2" "$RC" "2"
contains "Fehlursache benannt" "$OUT" "pruefen"

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
