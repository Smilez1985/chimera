#!/bin/sh
# Gegenprobe Anbietermodul (DESIGN 5t, 5v): jede Mutation muss einen Test rot machen.
# Aufruf: sh gegenprobe-anbieter.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
gruen=0
mut() { # name, datei, suchen, ersetzen, testfilter
  f="crates/tor/src/$2"
  cp "$f" /tmp/gp-orig.rs
  python3 - "$f" "$3" "$4" <<'EOF'
import sys
f, a, b = sys.argv[1:4]
s = open(f).read()
if s.count(a) < 1:
    sys.exit(3)
open(f, "w").write(s.replace(a, b, 1))
EOF
  if [ $? -ne 0 ]; then
    echo "MUSTER FEHLT: $1"; gruen=$((gruen+1)); cp /tmp/gp-orig.rs "$f"; return
  fi
  if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor "$5" >/tmp/gp-anb.log 2>&1; then
    echo "GRUEN (schlecht): $1"; gruen=$((gruen+1))
  else
    echo "rot (gut): $1"
  fi
  cp /tmp/gp-orig.rs "$f"
}
# Recht: auch nachgelegte Module vergeben das Recht
mut nachgelegt-zaehlt web.rs 'x.eingebaut && x.rechte.iter().any(|r| r == recht))' 'x.rechte.iter().any(|r| r == recht))' web::
# Recht wird nicht geprueft
mut recht-ungeprueft web.rs 'if !schreibrecht_vergeben(m, recht) {' 'if false {' web::
# Methode wird nicht geprueft
mut methode-ungeprueft web.rs 'if nur_post != (a.methode == "POST") {' 'if false {' web::
# Katalog-Id nicht geprueft (Ausbruch)
mut katalog-id web.rs 'Some(id) if crate::daten::id_gueltig(id) => {
                json!({"ok": true, "id": id, "katalog"' 'Some(id) => {
                json!({"ok": true, "id": id, "katalog"' web::
# Adresse nicht geprueft
mut adresse-ungeprueft daten.rs 'Some(t) if t.starts_with("http://") || t.starts_with("https://") => {}' 'Some(_) => {}' daten::
# ausgeschalteter Anbieter wird bedient
mut aus-wird-bedient dienst.rs 'if a.get("an").and_then(Value::as_bool) == Some(false) {
            return Err' 'if false {
            return Err' dienst::
# Typ nicht geprueft
mut typ-ungeprueft dienst.rs 'if a["typ"] != "ollama" {' 'if false {' dienst::
# Katalog wird bei Fehler ueberschrieben statt in Ruhe gelassen
mut katalog-bei-fehler dienst.rs 'Err(f) => return f,
    };
    let jetzt' 'Err(_) => serde_json::Map::new(),
    };
    let jetzt' dienst::
# tools aus dem Namen geraten statt gemessen
mut tools-geraten ollama.rs 'let tools = faehigkeiten.as_ref().map(|f| f.iter().any(|x| x == "tools"));' 'let tools = Some(true);' ollama::
# unbekannt wird zu nein
mut unbekannt-ist-nein ollama.rs 'let tools = faehigkeiten.as_ref().map(|f| f.iter().any(|x| x == "tools"));' 'let tools = Some(faehigkeiten.as_ref().map(|f| f.iter().any(|x| x == "tools")).unwrap_or(false));' ollama::
# Budget ignoriert
mut budget-ignoriert ollama.rs 'if start.elapsed() < budget {' 'if true {' ollama::
echo "== $gruen gruen =="
