#!/bin/sh
# Gegenprobe der Host-Tabelle (DESIGN, Regel "Jedes Werkzeug bekommt nur seine
# Rechte", Abschnitt "Fernausfuehrung"): jede Zusage verfaelschen,
# `cargo test ssh::` muss rot werden.
# Aufruf: sh gegenprobe-ssh.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
F=crates/tor/src/ssh.rs
cp "$F" /tmp/gp-ssh.orig
gruen=0
zurueck() { cp /tmp/gp-ssh.orig "$F"; }
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
	if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor 'ssh::' >/tmp/gp-ssh-intern.log 2>&1; then
		echo "GRUEN (schlecht): $1"
		gruen=$((gruen + 1))
	else
		echo "rot (gut): $1"
	fi
}

# 1. Ein Vorschlag gilt als brauchbar (der Agent oeffnet sich selbst einen Zugang).
mut vorschlag-wirkt \
	'e.get("herkunft").and_then(Value::as_str) == Some("nutzer")' \
	'true'
# 2. Ein Vorschlag darf einen bestehenden Host ueberschreiben.
mut vorschlag-aendert \
	'    if hosts.contains_key(name) {' \
	'    if false {'
# 3. Ohne Hostschluessel entsteht trotzdem ein Eintrag (kein Pin).
mut ohne-hostschluessel \
	'    let hostschluessel = match wert.get("hostschluessel") {' \
	'    let hostschluessel = json!({"typ":"ssh-ed25519","schluessel":"AAAA","fingerabdruck":"SHA256:x"});
    let _ungenutzt = match wert.get("hostschluessel") {'
# 4. Ein geaendertes Ziel nimmt den alten Schluessel mit.
mut ziel-ohne-neuen-schluessel \
	'.filter(|_| gleiches_ziel)' \
	'.filter(|_| true)'
# 5. Der Fingerabdruck wird uebernommen statt gerechnet.
mut fingerprint-geglaubt \
	'    let fp = fingerabdruck(blob).map_err(|e| ("wert_ungueltig", e))?;' \
	'    let fp = v.get("fingerabdruck").and_then(Value::as_str).unwrap_or("SHA256:?").to_string();'
# 6. Ein Pfad als Schluesselname wird durchgelassen.
mut schluessel-pfad \
	'        && !n.contains("..")' \
	'        && true'
# 7. Unbekannte Rechte werden stillschweigend durchgelassen.
mut rechte-freundlich \
	'    if !RECHTE.contains(&rechte) {' \
	'    if false {'
# 8. Ein unbestaetigter Host wird trotzdem herausgegeben -- **beide** Waechter
#    muessen fallen (Herkunft *und* Brauchbarkeit), sonst misst die Mutation
#    nur einen von beiden.
mut holen-ohne-pruefung \
'    if e.get("herkunft").and_then(Value::as_str) != Some("nutzer") {
        return Err((
            "host_unbestaetigt",
            format!("\"{name}\" ist nur ein Vorschlag -- der Nutzer hat ihn nicht bestaetigt."),
        ));
    }
    if !brauchbar(e) {
        return Err(("host_unbestaetigt", format!("\"{name}\" hat keinen bestaetigten Hostschluessel.")));
    }' \
'    let _ = (&e, name);'
# 9. Namen duerfen alles (Kommandozeile im Bezeichner).
mut name-frei \
	'        && name.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '"'"'-'"'"' || c == '"'"'_'"'"' || c == '"'"'.'"'"')' \
	'        && true'
# 10. known_hosts ohne Port (falsches Ziel bei Port != 22).
mut known-hosts-port \
	'    let ziel = if port == 22 { adresse.to_string() } else { format!("[{adresse}]:{port}") };' \
	'    let ziel = adresse.to_string();'

# 15. Die Freigabe wird beim ssh-Aufruf nicht gefragt (jedes Ziel geht durch).
mut ssh-ohne-freigabe \
	'    if frei["erlaubt"] != true {' \
	'    if false {'
# 16. Die Verbindung geht ohne Deskriptor an den Ausfuehrer.
mut ssh-ohne-deskriptor \
	'gemein::fdpass::senden(&strom, &zeile, &[tcp.as_raw_fd()])' \
	'gemein::fdpass::senden(&strom, &zeile, &[])'

# --- der Ausfuehrer: die feste Form des ssh-Aufrufs -----------------------
F2=crates/sohelper/src/ssh.rs
cp "$F2" /tmp/gp-ssh2.orig
zurueck2() { cp /tmp/gp-ssh2.orig "$F2"; }
mut2() { # name, suchen, ersetzen
	zurueck2
	python3 - "$F2" "$2" "$3" <<'EOF2'
import sys
f, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(f).read()
assert s.count(a) >= 1, "Muster fehlt: " + a
open(f, "w").write(s.replace(a, b, 1))
EOF2
	[ $? -eq 0 ] || { echo "MUSTER FEHLT: $1"; gruen=$((gruen + 1)); return; }
	if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-sohelper 'ssh::' >/tmp/gp-ssh2-intern.log 2>&1; then
		echo "GRUEN (schlecht): $1"
		gruen=$((gruen + 1))
	else
		echo "rot (gut): $1"
	fi
}

# 17. Der Hostschluessel wird nicht mehr gepinnt (accept-new statt yes).
mut2 hostschluessel-unkritisch \
	'"StrictHostKeyChecking=yes".into(),' \
	'"StrictHostKeyChecking=no".into(),'
# 18. Der Umweg ueber den Deskriptor faellt weg (ssh baut selbst auf).
mut2 proxy-umweg-weg \
	'"ProxyUseFdpass=yes".into(),' \
	'"ProxyUseFdpass=no".into(),'
# 19. Ein zweites Ziel wird einschmuggelbar.
mut2 zweiter-host \
	'a.adresse.clone(),
        "--".into(),' \
	'a.adresse.clone(),
        "zweiter.example".into(),
        "--".into(),'
# 20. Ein freies -o aus dem Auftrag ist erlaubt.
mut2 freie-option \
	'"-o".into(),
        "BatchMode=yes".into(),' \
	'"-o".into(),
        a.befehl.clone(),'

zurueck2

zurueck
echo "---"
echo "$gruen gruen (0 ist gut)"
[ "$gruen" = 0 ]
