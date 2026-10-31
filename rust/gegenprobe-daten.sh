#!/bin/sh
# Gegenprobe Datenschicht (DESIGN 5t): jede Mutation muss einen Test rot machen.
# Aufruf: sh gegenprobe-daten.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
F=crates/tor/src/daten.rs
cp "$F" /tmp/daten.rs.orig
gruen=0
mut() { # name, suchen, ersetzen
  cp /tmp/daten.rs.orig "$F"
  python3 - "$2" "$3" <<'EOF'
import sys
f="crates/tor/src/daten.rs"; s=open(f).read()
a,b=sys.argv[1],sys.argv[2]
assert s.count(a)>=1, "Muster fehlt: "+a
open(f,"w").write(s.replace(a,b,1))
EOF
  [ $? -eq 0 ] || { echo "MUSTER FEHLT: $1"; gruen=$((gruen+1)); return; }
  if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor daten:: >/tmp/gp-daten.log 2>&1; then
    echo "GRUEN (schlecht): $1"; gruen=$((gruen+1))
  else
    echo "rot (gut): $1"
  fi
}
mut id-ausbruch 'b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'"'"'-'"'" 'b != 0'
mut frist 'if jetzt.saturating_sub(seit) >= KATALOG_FRIST_S { continue; }' 'if false { continue; }'
mut fehlt-seit-erneuert 'let seit = e.get("fehlt_seit").and_then(Value::as_u64).unwrap_or(jetzt);' 'let seit = jetzt;'
mut modus 'fs::set_permissions(&tmp, fs::Permissions::from_mode(modus))' 'fs::set_permissions(&tmp, fs::Permissions::from_mode(0o644))'
mut sidecar-nicht-ersetzt 'let _ = fs::remove_file(&tmp);
    {' '{'
mut verweis-nicht-geprueft 'if !im_katalog {' 'if false {'
mut aus-ignoriert 'if a.get("an").and_then(Value::as_bool) == Some(false) {' 'if false {'
mut leere-kette 'if gut.is_empty() {
        msg.push' 'if false {
        msg.push'
mut schluessel-in-antwort 'v["schluessel"] = json!(schluessel_da(p, i));' 'v["schluessel"] = json!(schluessel_lesen(p, i));'
mut kaputt-geloescht 'Err(e) => { msg.push(meldung(&n, format!("kein gueltiges JSON: {e}"))); continue; }' 'Err(e) => { let _ = fs::remove_file(&pfad); msg.push(meldung(&n, format!("kein gueltiges JSON: {e}"))); continue; }'
cp /tmp/daten.rs.orig "$F"
echo "== $gruen gruen =="
