#!/bin/sh
# Gegenprobe Netzsuche (DESIGN 5k): jede Mutation muss einen Test rot machen.
# Aufruf: sh gegenprobe-netzsuche.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
gruen=0
mut() { # name, datei, suchen, ersetzen, testfilter
  f="crates/tor/src/$2"
  cp "$f" /tmp/gpn-orig.rs
  python3 - "$f" "$3" "$4" <<'EOF'
import sys
f, a, b = sys.argv[1:4]
s = open(f).read()
if s.count(a) < 1:
    sys.exit(3)
open(f, "w").write(s.replace(a, b, 1))
EOF
  if [ $? -ne 0 ]; then
    echo "MUSTER FEHLT: $1"; gruen=$((gruen+1)); cp /tmp/gpn-orig.rs "$f"; return
  fi
  if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor "$5" >/tmp/gpn.log 2>&1; then
    echo "GRUEN (schlecht): $1"; gruen=$((gruen+1))
  else
    echo "rot (gut): $1"
  fi
  cp /tmp/gpn-orig.rs "$f"
}
mut byte-reihenfolge netzsuche.rs 'map(u32::swap_bytes)' 'map(u32::from_le)' netzsuche::
mut netz-zu-gross netzsuche.rs 'if praefix < MIN_PRAEFIX {' 'if false {' netzsuche::
mut grenze-22 netzsuche.rs 'pub const MIN_PRAEFIX: u32 = 22;' 'pub const MIN_PRAEFIX: u32 = 20;' netzsuche::
mut sich-selbst netzsuche.rs '.filter(|a| *a != eigene)' '.filter(|_| true)' netzsuche::
mut broadcast netzsuche.rs '(netz + 1..bcast)' '(netz + 1..bcast + 1)' netzsuche::
mut enges-netz netzsuche.rs '.max_by_key(|(_, m)| m.count_ones())' '.min_by_key(|(_, m)| m.count_ones())' netzsuche::
mut standardroute netzsuche.rs '(gw == 0 && dest != 0 && maske != 0 && (l & maske) == dest)' '((l & maske) == dest)' netzsuche::
mut kein-ollama-pruefung ollama.rs '.map(|v| v["models"].is_array())' '.map(|_| true)' netzsuche::
mut doppelt-anlegen netzsuche.rs 'if vorhanden.iter().any(|(_, v)| v["adresse"].as_str().map(norm).as_deref() == Some(a.as_str())) {
            continue;
        }' '' netzsuche::
mut abgelehnt-ignoriert netzsuche.rs 'if weg.contains(&a) {
            continue;
        }' '' netzsuche::
mut marke-auto-fehlt netzsuche.rs '"auto": true,' '' netzsuche::
mut ablehnung-nicht-gemerkt daten.rs 'if v["auto"] == true {' 'if false {' daten::
mut ablehnung-bei-hand daten.rs 'if v["auto"] == true {' 'if true {' daten::
mut schreibweise netzsuche.rs 'a.trim().trim_end_matches('"'"'/'"'"').to_ascii_lowercase()' 'a.trim().to_ascii_lowercase()' netzsuche::
echo "== $gruen gruen =="
