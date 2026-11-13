#!/bin/sh
# Gegenprobe der DeepSeek-Anbindung (ROADMAP „DeepSeek als Anbieter",
# Auftrag smilez 13.11.). Jede Zusage verfaelschen, `cargo test deepseek::`
# muss rot werden.
# Aufruf: sh gegenprobe-deepseek.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
F=crates/tor/src/deepseek.rs
cp "$F" /tmp/gp-deepseek.orig
gruen=0
zurueck() { cp /tmp/gp-deepseek.orig "$F"; }
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
	if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor 'deepseek::' >/tmp/gp-deepseek-intern.log 2>&1; then
		echo "GRUEN (schlecht): $1"
		gruen=$((gruen + 1))
	else
		echo "rot (gut): $1"
	fi
}

# 1. Der Schluessel geht nicht mit -- der Aufruf waere ein 401 und niemand
#    wuesste, warum.
mut ohne-bearer \
	'        .header("authorization", &format!("Bearer {schluessel}"))
        .header("content-type", "application/json")' \
	'        .header("content-type", "application/json")'

# 2. Kein Guthaben heisst wieder "Anbieter-Fehler" -- das Alarmsignal (402)
#    geht im Rauschen unter.
mut guthaben-als-unbekannt \
	'        402 => (
            "kein_guthaben",' \
	'        402 => (
            "anbieter_fehler",'

# 3. Die Usage im Strom wird nicht gesammelt -- jede Antwort haette
#    "unbekannt" statt Zahlen (Stufe 3 „Kosten" braucht sie).
mut usage-ignoriert \
	'        if v["usage"].is_object() {' \
	'        if false {'

# 4. Ohne `include_usage` fehlen die Zahlen im Strom ganz.
mut include-usage-weg \
	'        k["stream_options"] = json!({"include_usage": true});' \
	'        k["stream_options"] = json!({});'

# 5. Der Denktext aus dem Strom wird verworfen -- "nur gedacht" waere dann
#    "leer", also die falsche Auskunft.
mut denktext-ignoriert \
	'        if let Some(t) = d["reasoning_content"].as_str() {
            gedacht.push_str(t);
        }' \
	'        if false {
            gedacht.push_str("");
        }'

# 6. "Denken aus" wird nicht mehr geschickt -- der teure Denkmodus bliebe an,
#    obwohl der Aufrufer ihn abbestellt hat.
mut denken-aus-ignoriert \
	'    if denken_aus(anfrage) {
        k["thinking"] = json!({"type": "disabled"});' \
	'    if false {
        k["thinking"] = json!({"type": "disabled"});'

# 7. `tool_choice: required` geht im Denkmodus mit -- DeepSeek antwortet 400,
#    und der Aufrufer sieht nur "Anfrage abgelehnt".
mut required-durchgelassen \
	'    let wahl = anfrage.get("tool_choice")?;' \
	'    return None;
    #[allow(unreachable_code)]
    let wahl = anfrage.get("tool_choice")?;'

# 8. Ohne Usage wird 0 gebucht statt "unbekannt" -- ein Aufruf ohne Zahlen
#    saehe kostenlos aus.
mut usage-null-als-null-token \
	'        "eingabe": u["prompt_tokens"].as_u64(),' \
	'        "eingabe": Some(u["prompt_tokens"].as_u64().unwrap_or(0)),'

# 9. Die Argumente eines Aufrufs werden nicht gelesen -- das Werkzeug bekaeme
#    leere Argumente und liefe ins Leere.
mut argumente-verloren \
	'        let mut e = json!({
            "name": name,
            "argumente": Value::Object(crate::ollama::argumente_als_objekt(&c["function"]["arguments"])),
        });' \
	'        let mut e = json!({
            "name": name,
            "argumente": Value::Object(serde_json::Map::new()),
        });'

# 10. Die Reihenfolge des Nutzers wird nicht mehr beachtet -- es ginge immer
#     das erste Modell des Servers raus.
mut eigene-reihenfolge-ignoriert \
	'    for name in bevorzugt {
        if modelle.contains(name) {
            return Ok(name.clone());
        }
    }' \
	'    for name in bevorzugt.iter().take(0) {
        if modelle.contains(name) {
            return Ok(name.clone());
        }
    }'

zurueck
echo "---"
if [ "$gruen" -eq 0 ]; then
	echo "alle Mutationen rot -- die Zusagen werden gemessen"
else
	echo "$gruen Mutation(en) blieben gruen"
	exit 1
fi
