#!/bin/sh
# Gegenprobe Wahl (Modul `wahl`, DESIGN 5h/5r): jede Mutation muss einen Test
# rot machen. Aufruf: sh gegenprobe-wahl.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
D=crates/tor/src/daten.rs
W=crates/tor/src/web.rs
cp "$D" /tmp/wahl-daten.rs.orig
cp "$W" /tmp/wahl-web.rs.orig
gruen=0
zurueck() { cp /tmp/wahl-daten.rs.orig "$D"; cp /tmp/wahl-web.rs.orig "$W"; }
mut() { # name, datei, suchen, ersetzen, testfilter
	zurueck
	python3 - "$2" "$3" "$4" <<'EOF'
import sys
f, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(f).read()
assert s.count(a) >= 1, "Muster fehlt: " + a
open(f, "w").write(s.replace(a, b, 1))
EOF
	[ $? -eq 0 ] || { echo "MUSTER FEHLT: $1"; gruen=$((gruen + 1)); return; }
	if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor "$5" >/tmp/gp-wahl.log 2>&1; then
		echo "GRUEN (schlecht): $1"
		gruen=$((gruen + 1))
	else
		echo "rot (gut): $1"
	fi
}

# 1. Das Feld wird nicht geprueft: beliebiges Feld schreibbar.
mut feld-ungeprueft "$D" 'if !EINZELN_SETZBAR.contains(&feld) {' 'if false {' 'wahl'
# 2. Der Wert wird nicht geprueft: "an" als Zeichenkette gilt als wahr.
mut wert-ungeprueft "$D" '            let an = wert
                .as_bool()' '            let an = wert
                .as_bool()
                .or(Some(true))' 'wahl'
# 3. Der Rest der Datei wird verworfen: die Kette stirbt beim Stromschalter.
mut rest-verworfen "$D" 'let mut wahl = wahl_laden(p).map_err(|m| ("wahl_kaputt", format!("{}: {}", m.quelle, m.text)))?;' 'let mut wahl = json!({});' 'wahl'
# 5. Der Verweis wird nicht geprueft: beliebiger Text landet in der Kette.
mut verweis-ungeprueft "$D" 'if verweis_teilen(text).is_none() {' 'if false {' 'wahl'
# 6. Doppelte Eintraege werden durchgelassen.
mut doppelt-erlaubt "$D" 'if sauber.iter().any(|x| x == text) {' 'if false {' 'wahl'
# 7. Die Kette wird nicht geprueft (Typ/Laenge): rohe Liste in die Datei.
mut kette-roh "$D" 'let mut sauber: Vec<String> = Vec::with_capacity(liste.len());' 'let mut sauber: Vec<String> = liste.iter().filter_map(Value::as_str).map(str::to_string).collect(); if !sauber.is_empty() { return Ok(json!(sauber)); }' 'wahl'
# 4. Die Web-Tuer ohne Rechtspruefung.
mut tuer-ohne-recht "$W" '    if !schreibrecht_vergeben(m, recht) {
        return fehler(403, &format!("kein Modul hat das Recht '"'"'{recht}'"'"'"));
    }
    if nur_post != (a.methode == "POST") {
        return fehler(405, "Methode nicht erlaubt");
    }
    match was {' '    match was {' 'wahl'

zurueck
echo "== $gruen gruen =="
