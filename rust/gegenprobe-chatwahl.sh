#!/bin/sh
# Gegenprobe der Chat-Wahl ueber alle Tueren (DESIGN "Modellwahl im Chat",
# Ergaenzung 14.11.: die Wahl liegt bei der Sitzung, alle Tueren setzen sie).
# Jede Zusage verfaelschen -- `cargo test` muss rot werden.
# Aufruf: sh gegenprobe-chatwahl.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
gruen=0
zurueck() {
	cp /tmp/gp-wahl-daten.orig crates/tor/src/daten.rs
	cp /tmp/gp-wahl-telegram.orig crates/tor/src/telegram.rs
	cp /tmp/gp-wahl-web.orig crates/tor/src/web.rs
	cp /tmp/gp-wahl-sitzung.orig crates/tor/src/sitzung.rs
}
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
	if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor "$5" >/tmp/gp-wahl-intern.log 2>&1; then
		echo "GRUEN (schlecht): $1"
		gruen=$((gruen + 1))
	else
		echo "rot (gut): $1"
	fi
}

cp crates/tor/src/daten.rs /tmp/gp-wahl-daten.orig
cp crates/tor/src/telegram.rs /tmp/gp-wahl-telegram.orig
cp crates/tor/src/web.rs /tmp/gp-wahl-web.orig
cp crates/tor/src/sitzung.rs /tmp/gp-wahl-sitzung.orig

# 1. Leerer Wert loescht nicht mehr -- dann bliebe "ohne Wahl" alte Werte stehen.
mut leer-loescht-nicht crates/tor/src/daten.rs \
	'    if wert.is_null() {
        obj.remove(feld);' \
	'    if false {
        obj.remove(feld);' 'daten::'

# 2. Unsinnige Denkstufe wird angenommen.
mut denkstufe-ungeprueft crates/tor/src/daten.rs \
	'"denken" if !DENKSTUFEN.contains(&text.to_lowercase().as_str()) => Err((' \
	'"denken" if false => Err((' 'daten::'

# 3. Die Denkstufe wird nicht klein geschrieben -- "MITTEL" kaeme beim
#    Anbieter anders an als gespeichert.
mut denkstufe-gross crates/tor/src/daten.rs \
	'Ok(json!(if feld == "denken" { text.to_lowercase() } else { text }))' \
	'Ok(json!(text))' 'daten::'

# 4. Unwaehlbares (Spezial/unbekannt) wird trotzdem gewaehlt.
mut nicht-waehlbar-cr crates/tor/src/telegram.rs \
	'    let Some(eintrag) = eintrag else {' \
	'    let Some(eintrag) = eintrag.or(Some(&json!({}))) else {' 'telegram::'

# 5. Die Denkstufe wird ungeprueft uebernommen.
mut falsche-stufe-ok crates/tor/src/telegram.rs \
	'    if !stufe.is_empty() && !stufen.iter().any(|s| *s == stufe) {' \
	'    if false {' 'telegram::'

# 6. Nummern zeigen auf die falsche Zeile (um eins verschoben).
mut nummern-verschoben crates/tor/src/telegram.rs \
	'ziele.push((ziele.len() + 1, id.to_string(), name.to_string()))' \
	'ziele.push((ziele.len() + 2, id.to_string(), name.to_string()))' 'telegram::'

# 7. Die Wahlzeile behauptet eine Wahl, wo keine ist.
mut ohne-wahl-erfunden crates/tor/src/telegram.rs \
	'        return "Gilt: keine Wahl — der Anbieter entscheidet.".to_string();' \
	'        return "Gilt: ollama/irgendwas.".to_string();' 'telegram::'

# 8. Der Web-Weg schickt die gespeicherte Wahl nicht mit.
mut web-ohne-gespeicherte-wahl crates/tor/src/web.rs \
	'        if let Some(x) = wert(koerper, feld).or_else(|| wert(gespeichert, feld)) {' \
	'        if let Some(x) = wert(koerper, feld) {' 'web::'

# 9. Der Telegram-Weg schickt die Wahl nicht mit.
mut telegram-ohne-wahl crates/tor/src/sitzung.rs \
	'        if let Some(w) = wahl.get(feld).and_then(Value::as_str).map(str::trim).filter(|s| !s.is_empty()) {' \
	'        if let Some(w) = None::<&str> {' 'sitzung::'

zurueck
echo "---"
if [ "$gruen" -eq 0 ]; then
	echo "alle Mutationen rot: die Zusagen sind gemessen."
else
	echo "$gruen Mutation(en) blieben gruen -- Test fehlt."
fi
exit "$gruen"
