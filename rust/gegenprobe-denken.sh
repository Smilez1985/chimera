#!/bin/sh
# Gegenprobe zu „Denktext ist keine Antwort" (DESIGN, Regel „Aufrufe, nicht Text").
# Jede Zusage verfaelschen, `cargo test ollama::` muss rot werden.
# Aufruf: sh gegenprobe-denken.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
F=crates/tor/src/ollama.rs
cp "$F" /tmp/gp-denken.orig
gruen=0
zurueck() { cp /tmp/gp-denken.orig "$F"; }
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
	if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor 'ollama::' >/tmp/gp-denken-intern.log 2>&1; then
		echo "GRUEN (schlecht): $1"
		gruen=$((gruen + 1))
	else
		echo "rot (gut): $1"
	fi
}

# 1. Denktext wird ignoriert -- der alte Zustand: "leer", obwohl das Modell
#    etwas gesagt hat (nur eben nicht als Antwort).
mut denktext-ignoriert \
	'        if let Some(gedacht) = roh["message"]["thinking"].as_str().filter(|s| !s.trim().is_empty()) {' \
	'        if let Some(gedacht) = None::<&str> {'

# 2. Der Denkauszug wird nicht begrenzt -- ein 900-Zeichen-Gedanke ginge voll
#    in die Antwort (und in jedes Protokoll).
mut auszug-unbegrenzt \
	'gedacht.chars().take(400)' \
	'gedacht.chars().take(usize::MAX)'

# 3. Denktext wird als Antworttext ausgegeben -- der Agent wuerde das
#    Selbstgespraech des Modells als Ergebnis nehmen.
mut denktext-als-antwort \
	'    let text = roh["message"]["content"].as_str().unwrap_or("");' \
	'    let text = roh["message"]["content"].as_str().filter(|t| !t.is_empty())
        .or_else(|| roh["message"]["thinking"].as_str()).unwrap_or("");'

# 4. Ein Aufruf neben Denktext gilt als Fehler -- der Normalfall bei
#    Denkmodellen mit Werkzeugen wuerde damit unbrauchbar.
mut aufruf-mit-denktext-ist-fehler \
	'    if text.is_empty() && aufrufe.is_empty() {' \
	'    if text.is_empty() {'

# 5. Eine Zeitgrenze gilt wieder als "nicht erreichbar" -- der alte Zustand:
#    der Suchende schaut zum Netz, obwohl das Modell noch denkt.
mut zeitgrenze-als-nicht-erreichbar \
	'if matches!(e, ureq::Error::Timeout(_)) {' \
	'if false {'

zurueck
echo "== $gruen gruen =="
[ "$gruen" -eq 0 ]
