#!/bin/sh
# Gegenprobe des Webabrufs (DESIGN Regel 5r, Stufe 2 der Freigaben): jede
# Zusage verfaelschen, `cargo test abruf::` muss rot werden.
# Aufruf: sh gegenprobe-abruf.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
F=crates/tor/src/abruf.rs
cp "$F" /tmp/gp-abruf.orig
gruen=0
zurueck() { cp /tmp/gp-abruf.orig "$F"; }
mut() { # name, suchen, ersetzen
	zurueck
	python3 - "$F" "$2" "$3" <<'EOF'
import sys
f, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(f).read()
assert s.count(a) >= 1, "Muster fehlt: " + a
open(f, "w").write(s.replace(a, b, 1))
EOF
	[ $? -eq 0 ] || { echo "MUSTER FEHLT: $1"; gruen=$((gruen + 1)); return; }
	if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor 'abruf::' >/tmp/gp-abruf-intern.log 2>&1; then
		echo "GRUEN (schlecht): $1"
		gruen=$((gruen + 1))
	else
		echo "rot (gut): $1"
	fi
}

# 1. Die Freigabe wird gar nicht gefragt (jedes Ziel geht durch).
mut freigabe-uebergangen \
	'    freigaben::pruefen(p, "web_abruf", Some(&a.host), jetzt)' \
	'    json!({"erlaubt": true, "grund": "immer"})'
# 2. Eigene Adressen sind nicht mehr gesperrt.
mut eigene-adresse-frei \
	'if eigene_adresse(&a.host) && !ausdruecklich_erlaubt(p, &a.host) {' \
	'if false {'
# 3. Eine Umleitung wird ungeprueft verfolgt.
mut umleitung-ungeprueft \
	'            let e = erlaubt(p, &naechste, jetzt);
            if e["erlaubt"] != true {' \
	'            let e = json!({"erlaubt": true});
            if false {'
# 4. Nicht-Text wird ausgeliefert (Bilder, PDFs in den Verlauf).
mut nicht-text-durch \
	'if !ist_text(&typ) {' \
	'if false {'
# 5. Die Textgrenze faellt (kein Kuerzen).
mut text-nicht-gekuerzt \
	'        let text: String = text.chars().take(TEXT_MAX).collect();' \
	'        let text: String = text;'
# 6. Jedes Schema ist erlaubt (file:, ftp:).
mut falsches-schema \
	'if schema != "http" && schema != "https" {' \
	'if false {'
# 7. Anmeldedaten in der Adresse bleiben stehen (zweite Adresse in der ersten).
mut anmeldung-erlaubt \
	"if autoritaet.contains('@') {" \
	'if false {'

zurueck
echo "== $gruen gruen =="
[ "$gruen" -eq 0 ]
