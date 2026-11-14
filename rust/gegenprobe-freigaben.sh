#!/bin/sh
# Gegenprobe der Freigaben je Werkzeug (DESIGN, Regel "Freigabe je Werkzeug
# auf Zeit"): jede Zusage verfaelschen, `cargo test` muss rot werden.
# Aufruf: sh gegenprobe-freigaben.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
F=crates/tor/src/freigaben.rs
T=crates/tor/src/telegram.rs
cp "$F" /tmp/gp-freigaben.orig
cp "$T" /tmp/gp-telegram.orig
gruen=0
zurueck() { cp /tmp/gp-freigaben.orig "$F"; cp /tmp/gp-telegram.orig "$T"; }
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
	if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor "$5" >/tmp/gp-frei.log 2>&1; then
		echo "GRUEN (schlecht): $1"
		gruen=$((gruen + 1))
	else
		echo "rot (gut): $1"
	fi
}

# 1. Negativliste wird im offenen Modus uebersehen.
mut negativ-uebersehen "$F" '    if !z.is_empty() && e.negativ.iter().any(|n| n.to_lowercase() == z) {' '    if false {' 'freigaben::'
# 2. Ablauf zaehlt nicht: eine Freigabe gilt fuer immer.
mut ablauf-ignoriert "$F" '        self.ist_modus("offen") && self.bis.map(|b| b > jetzt).unwrap_or(true)' '        self.ist_modus("offen")' 'freigaben::'
# 3. Unbekanntes Werkzeug wird durchgelassen.
mut werkzeug-offen "$F" '    if !WERKZEUGE.contains(&werkzeug) {
        return antwort(false,' '    if false {
        return antwort(false,' 'freigaben::'
# 4. Ein Teil-Auftrag leert die Listen (Zeitknopf loescht Ziele).
mut teilauftrag-leert "$F" '    let positiv = if wert.get("positiv").is_some() { liste("positiv")? } else { alt.positiv.clone() };' '    let positiv = liste("positiv")?;' 'freigaben::'
# 5. `seit` wird beim Oeffnen nicht gesetzt (die Erinnerung haette keinen Anfang).
mut seit-fehlt "$F" '&& seit.is_none() { Some(jetzt) } else { seit }' '&& seit.is_none() { None } else { seit }' 'freigaben::'
# 6. Eine mitgeschickte Frist wird gespeichert (Luege in der Datei).
mut frist-gespeichert "$F" '"bis": Value::Null, "seit": seit,' '"bis": wert.get("bis").cloned().unwrap_or(Value::Null), "seit": seit,' 'freigaben::'
# 7. Zu kurzer Erinnerungsabstand wird angenommen.
mut erinnern-zu-kurz "$F" '            Some(s) if s >= ERINNERN_MIN => Some(s),' '            Some(s) => Some(s),' 'freigaben::'
# 8. "aus" setzt nicht zurueck, sondern laesst alles offen.
mut aus-schaltet-nicht "$T" '"aus" | "zu" | "positivliste" | "schliessen" | "schließen" => return Ok(Auftrag::Aus),' '"aus" | "zu" | "positivliste" | "schliessen" | "schließen" => return Ok(Auftrag::Immer),' 'telegram::'
# 9. Eine Dauer wird still angenommen (der Nutzer glaubt an eine Frist, die es nicht gibt).
mut dauer-angenommen "$T" '        if ["m", "h", "d"].contains(&einheit.as_str()) && ohne_einheit.parse::<u64>().is_ok() {' '        if false {' 'telegram::'

# 10. Der dritte Modus gilt als "offen" (die gefaehrlichste Verwechslung).
mut dritter-modus-offen "$F" '        self.ist_modus("offen") && self.bis.map(|b| b > jetzt).unwrap_or(true)' '        !self.ist_modus("positivliste") && self.bis.map(|b| b > jetzt).unwrap_or(true)' 'freigaben::'
# 11. Ein Vorschlag wirkt sofort (er traegt sich selbst in die Positivliste).
mut vorschlag-wirkt "$F" '        e.vorschlaege.push(Vorschlag { ziel: z.clone(), herkunft: "agent".into(), seit: jetzt, notiz: n.to_string() });' '        e.positiv.push(z.clone());
        e.vorschlaege.push(Vorschlag { ziel: z.clone(), herkunft: "agent".into(), seit: jetzt, notiz: n.to_string() });' 'freigaben::'
# 12. Vorschlaege sind in jedem Modus erlaubt (sie koennten nie etwas werden).
mut vorschlag-immer "$F" '        if !e.ist_modus("offen_nach_vorschlag") {' '        if false {' 'freigaben::'
# 13. Die Annahme uebersieht die Negativliste.
mut annahme-ohne-negativ "$F" '    if vor.negativ.iter().any(|x| x.eq_ignore_ascii_case(&z)) {' '    if false {' 'freigaben::'
# 14. Verwerfen raeumt den Vorschlag nicht weg.
mut verwerfen-bleibt "$F" '        e.vorschlaege.remove(i);
        Ok(format!("\"{z}\" verworfen"))' '        Ok(format!("\"{z}\" verworfen"))' 'freigaben::'
# 15. Ein Zeitknopf wirft die offenen Vorschlaege weg.
mut teilauftrag-vorschlaege "$F" '        "positiv": e.positiv, "negativ": e.negativ,
        "vorschlaege": e.vorschlaege.iter().map(Vorschlag::als_json).collect::<Vec<_>>(),' '        "positiv": e.positiv, "negativ": e.negativ,
        "vorschlaege": Vec::<Value>::new(),' 'freigaben::'
# 16. Die Grenze fuer Vorschlaege fehlt (eine Schleife schreibt die Datei voll).
mut vorschlag-grenze "$F" '        if e.vorschlaege.len() >= VORSCHLAEGE_MAX {' '        if false {' 'freigaben::'

zurueck
echo "== $gruen gruen =="
