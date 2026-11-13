#!/bin/sh
# Gegenprobe des Guthabens je Anbieter (ROADMAP „Guthaben und Kosten je
# Anbieter", Auftrag smilez 13.11.). Jede Zusage verfaelschen,
# `cargo test quota::` muss rot werden.
# Aufruf: sh gegenprobe-quota.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
F=crates/tor/src/quota.rs
cp "$F" /tmp/gp-quota.orig
gruen=0
zurueck() { cp /tmp/gp-quota.orig "$F"; }
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
	if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor 'quota::' >/tmp/gp-quota-intern.log 2>&1; then
		echo "GRUEN (schlecht): $1"
		gruen=$((gruen + 1))
	else
		echo "rot (gut): $1"
	fi
}

# 1. Alle Waehrungen in einem Namen -- aus zwei Pools wuerde eine Zahl
#    ("currencies are never converted or summed").
mut waehrung-vereinheitlicht \
	'            "waehrung": waehrung,' \
	'            "waehrung": "XXX",'

# 2. Die Herkunft faellt weg -- eine Zahl ohne Quelle ist keine Auskunft.
mut herkunft-fehlt \
	'        "herkunft": herkunft(&typ, &basis),' \
	'        "herkunft": json!({}),'

# 3. Veraltet wird verschwiegen.
mut veraltet-verschwiegen \
	'        e["veraltet"] = json!(jetzt.saturating_sub(g) >= FRISCHE_S);' \
	'        e["veraltet"] = json!(false);'

# 4. Retry-After wird ignoriert -- der Knopf haemmerte auf den Anbieter.
mut retry-ignoriert \
	'    let durch_retry_gesperrt = jetzt < gesperrt_bis;' \
	'    let durch_retry_gesperrt = false;'

# 5. Ohne Schluessel wird trotzdem gefragt (der Abruf geht raus und
#    scheitert mit 401, statt vorher zu sagen, dass keiner da ist).
mut ohne-schluessel-gefragt \
	'            None => {
                e["zustand"] = json!("nicht_abrufbar");' \
	'            None => {
                e["zustand"] = json!("gut");'

# 6. Ein Anbieter ohne Adapter bekommt keine Auskunft -- die Karte bliebe
#    leer statt "es wird keine Zahl erfunden" zu sagen.
mut adapter-grund-fehlt \
	'            e["hinweis"] = json!(nicht_abrufbar_grund(&typ));' \
	'            e["hinweis"] = json!("");'

# 7. Der alte Stand wird bei gescheitertem Abruf weggeworfen.
mut alter-stand-weggeworfen \
	'                    if let Some(roh) = alt.get("roh").filter(|r| !r.is_null()) {
                        e["pools"] = Value::Array(pools_deepseek(roh));' \
	'                    if let Some(roh) = None::<&Value> {
                        e["pools"] = Value::Array(pools_deepseek(roh));'

# 8. Die Frist gilt nicht: jeder Aufruf fragt neu (Kosten beim Anbieter,
#    und die Anzeige zappelt).
mut frische-ignoriert \
	'    let faellig = neu || geholt.map(|g| jetzt.saturating_sub(g) >= FRISCHE_S).unwrap_or(true);' \
	'    let faellig = true;'

# 9. Ein abgeschalteter Anbieter wird doch gefragt.
mut ausgeschaltet-gefragt \
	'        if a.get("an").and_then(Value::as_bool) == Some(false) {
            continue;
        }' \
	'        if false {
            continue;
        }'

# 10. Die Kennung wird nicht geprueft -- "../x" waere ein Pfad.
mut id-ungeprueft \
	'        if !crate::daten::id_gueltig(id) {
            return fehlerantwort("id_ungueltig", "Die Anfrage braucht eine gueltige \"id\".");
        }' \
	'        if false {
            return fehlerantwort("id_ungueltig", "x");
        }'

zurueck
echo "---"
if [ "$gruen" -eq 0 ]; then
	echo "alle Mutationen rot -- die Zusagen werden gemessen"
else
	echo "$gruen Mutation(en) blieben gruen"
	exit 1
fi
