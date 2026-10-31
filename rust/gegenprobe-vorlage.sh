#!/bin/sh
# Gegenprobe fuer modul_vorlage.rs (DESIGN Regel 5v): jede Mutation verfaelscht eine
# Messaussage; die Tests muessen dann ROT werden. Danach wird die Quelle
# zurueckgelegt und per cmp geprueft. Dauer einige Minuten: abgekoppelt starten.
set -u
cd "$(dirname "$0")" || exit 2
. "$HOME/.cargo/env"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/root/chimera-target}"
F=crates/tor/src/modul_vorlage.rs
SICH=$(mktemp) || exit 2
[ -n "$SICH" ] || exit 2
cp "$F" "$SICH" || exit 2
[ -s "$SICH" ] || { echo "Sicherung leer"; exit 2; }
trap 'cp "$SICH" "$F"' EXIT INT TERM

ROT=0; GRUEN=0
mutiere() {  # name, alt, neu
    cp "$SICH" "$F"
    python3 - "$F" "$2" "$3" <<'EOF'
import sys
p, alt, neu = sys.argv[1:4]
s = open(p).read()
if s.count(alt) != 1:
    print("MUSTER NICHT EINDEUTIG:", s.count(alt)); sys.exit(3)
open(p, "w").write(s.replace(alt, neu))
EOF
    [ $? -eq 0 ] || { echo "  FEHLER  $1: Mutation nicht anwendbar"; GRUEN=$((GRUEN+1)); return; }
    if cargo test --offline -p chimera-tor modul_vorlage >/tmp/gp-vorlage.log 2>&1; then
        echo "  GRUEN (schlecht)  $1 -- Test merkt es nicht"; GRUEN=$((GRUEN+1))
    else
        if rg -q 'test result: FAILED|panicked' /tmp/gp-vorlage.log; then
            echo "  rot (gut)  $1"; ROT=$((ROT+1))
        else
            echo "  BAUFEHLER  $1"; rg 'error' /tmp/gp-vorlage.log | head -3; GRUEN=$((GRUEN+1))
        fi
    fi
}

mutiere "Pruefsumme: Dateinamen zaehlen nicht" \
  '        ctx.update(rel.as_bytes());' '        ctx.update(b"");'
mutiere "Pruefsumme: Dateigrenzen verschiebbar" \
  '        ctx.update(&(inhalt.len() as u64).to_be_bytes());' '        ctx.update(b"");'
mutiere "Pruefsumme: Unterverzeichnisse uebersprungen" \
  '        if typ.is_dir() {
            sammeln(wurzel, &p, aus)?;' '        if typ.is_dir() {
            continue;'
mutiere "Verweise werden gefolgt" \
  '        if typ.is_symlink() {' '        if false {'
mutiere "Vorhandenes Verzeichnis wird ueberschrieben" \
  '    if dir.exists() {' '    if false {'
mutiere "Eingabepruefung aus" \
  '    if !text_ok(wert) {' '    if false {'
mutiere "Anfuehrungszeichen erlaubt" \
  "c == '\"' || c == '\\\\' ||" "false ||"
mutiere "Manifest wird nicht mit dem Gateway-Code geprueft" \
  '    web::manifest_lesen(&e.name, &manifest, false).map_err(|f| format!("Manifest ungueltig: {f}"))?;' '    let _ = &manifest;'
mutiere "Einstiegsdatei nicht geprueft" \
  '    if !dir.join(&m.einstieg).is_file() {' '    if false {'
mutiere "Klassenname ohne Grossbuchstaben" \
  "Some(f) => f.to_ascii_uppercase().to_string() + c.as_str()," "Some(f) => f.to_string() + c.as_str(),"

cp "$SICH" "$F"
if cmp -s "$SICH" "$F"; then echo "Quelle zurueckgelegt (cmp ok)"; else echo "QUELLE NICHT ZURUECK"; exit 2; fi
echo "rot: $ROT  gruen (schlecht): $GRUEN"
[ "$GRUEN" -eq 0 ] && [ "$ROT" -gt 0 ]
