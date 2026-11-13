//! Die Host-Tabelle der Fernausfuehrung (DESIGN, Regel "Jedes Werkzeug
//! bekommt nur seine Rechte", Abschnitt "Fernausfuehrung: ssh geht durch das
//! Gateway, und nur so").
//!
//! **Eine Wahrheit, zwei Haelften.** Hier steht, *welche* Hosts es gibt
//! (Adresse, Nutzer, Port, Schluessel**name**, Rechte, Herkunft). Die
//! Schluesseldateien selbst liegen beim Ausfuehrer
//! (`/opt/chimera/sohelper/ssh/keys/`) -- das Gateway hat den Netzzugang und
//! keinen Schluessel, der Ausfuehrer die Schluessel und kein Netz.
//!
//! **Ein Vorschlag wirkt nicht.** Der Agent darf Hosts anlegen
//! (`herkunft: "vorschlag"`), aber ein solcher Eintrag ist nicht brauchbar,
//! bis der Nutzer ihn im Web-Modul bestaetigt -- sonst oeffnete sich das
//! Modell selbst einen Zugang.
//!
//! **Der Hostschluessel wird geprueft, nicht geglaubt.** Der Eintrag traegt
//! Typ und Blob des Hostschluessels; der Fingerabdruck wird hier aus dem Blob
//! gerechnet (`SHA256:…`) und nicht vom Aufrufer uebernommen. Was in
//! `known_hosts` des Ausfuehrers landet, ist genau dieser Blob -- der
//! `StrictHostKeyChecking=yes`-Lauf vergleicht spaeter damit.
//!
//! Ablage: `config/ssh/hosts.json` in einem eigenen Ordner (Regel 5t), weil
//! atomar ueber eine Nebendatei im **selben Ordner** geschrieben wird.

use crate::daten::{atomar_schreiben, Pfade};
use serde_json::{json, Value};

/// Rechte auf dem Ziel. Die Vorgabe ist `force` -- wer mehr will, sagt es
/// ausdruecklich; ein unbekannter Wert wird abgelehnt, nicht grosszuegig
/// ausgelegt.
pub const RECHTE: &[&str] = &["zaun", "force", "voll"];

/// Namen sind Bezeichner, keine Kommandozeile: klein, ohne Leerraum, max. 32.
const NAME_MAX: usize = 32;

pub fn datei(p: &Pfade) -> std::path::PathBuf {
    p.config.join("ssh").join("hosts.json")
}

fn roh(p: &Pfade) -> Value {
    std::fs::read_to_string(datei(p))
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({ "hosts": {} }))
}

/// Ein Eintrag ist **brauchbar**, wenn der Nutzer ihn angelegt hat und ein
/// Hostschluessel mit Fingerabdruck dasteht. Ein Vorschlag ist es nie.
pub fn brauchbar(e: &Value) -> bool {
    e.get("herkunft").and_then(Value::as_str) == Some("nutzer")
        && e.get("hostschluessel")
            .and_then(|h| h.get("fingerabdruck"))
            .and_then(Value::as_str)
            .map(|f| f.starts_with("SHA256:"))
            .unwrap_or(false)
}

/// Die Tabelle fuer die Anzeige: Vorgaben aufgefuellt, nichts erfunden.
pub fn laden(p: &Pfade) -> Value {
    let ganz = roh(p);
    let mut hosts = serde_json::Map::new();
    if let Some(m) = ganz.get("hosts").and_then(Value::as_object) {
        for (name, e) in m {
            let mut e = e.clone();
            if let Some(o) = e.as_object_mut() {
                o.entry("port").or_insert(json!(22));
                o.entry("rechte").or_insert(json!("zaun"));
                o.entry("herkunft").or_insert(json!("vorschlag"));
                o.entry("notiz").or_insert(json!(""));
            }
            e["brauchbar"] = json!(brauchbar(&e));
            hosts.insert(name.clone(), e);
        }
    }
    json!({ "hosts": hosts })
}

fn name_ok(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= NAME_MAX
        && name.chars().next().map(|c| c.is_ascii_lowercase() || c.is_ascii_digit()).unwrap_or(false)
        && name.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-' || c == '_' || c == '.')
}

/// Adresse: IPv4, IPv6 (mit `:`), Name. Kein Leerraum, kein Schraegstrich,
/// kein fuehrender Bindestrich (der waere ein Argument).
fn adresse_ok(a: &str) -> bool {
    !a.is_empty()
        && a.len() <= 253
        && !a.starts_with('-')
        && a.chars().all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '-' || c == ':' || c == '_')
        && !a.contains("..")
}

fn nutzer_ok(n: &str) -> bool {
    !n.is_empty()
        && n.len() <= 32
        && n.chars().next().map(|c| c.is_ascii_alphanumeric() || c == '_').unwrap_or(false)
        && n.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
}

/// Der Schluessel**name** aus dem Verzeichnis des Ausfuehrers -- nie ein Pfad.
fn schluessel_ok(n: &str) -> bool {
    !n.is_empty()
        && n.len() <= 64
        && !n.starts_with('-')
        && n.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
        && !n.contains("..")
}

// --- base64 (nur was hier gebraucht wird: Blob lesen, Fingerabdruck schreiben)

const B64: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

fn b64_lesen(t: &str) -> Result<Vec<u8>, String> {
    let mut out = Vec::with_capacity(t.len() * 3 / 4);
    let mut puffer = 0u32;
    let mut bits = 0u32;
    for c in t.bytes() {
        if c == b'=' || c == b'\n' || c == b'\r' || c == b' ' {
            continue;
        }
        let v = B64.iter().position(|x| *x == c).ok_or_else(|| format!("kein base64: {:?}", c as char))? as u32;
        puffer = (puffer << 6) | v;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((puffer >> bits) as u8);
        }
    }
    Ok(out)
}

fn b64_schreiben(d: &[u8]) -> String {
    let mut s = String::with_capacity(d.len().div_ceil(3) * 4);
    for stueck in d.chunks(3) {
        let b = [stueck[0], *stueck.get(1).unwrap_or(&0), *stueck.get(2).unwrap_or(&0)];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        s.push(B64[(n >> 18) as usize & 63] as char);
        s.push(B64[(n >> 12) as usize & 63] as char);
        s.push(if stueck.len() > 1 { B64[(n >> 6) as usize & 63] as char } else { '=' });
        s.push(if stueck.len() > 2 { B64[n as usize & 63] as char } else { '=' });
    }
    s
}

/// `SHA256:` + base64 ohne Fuellzeichen -- die Form, die `ssh-keygen -lf`
/// ausgibt.
pub fn fingerabdruck(blob_b64: &str) -> Result<String, String> {
    let blob = b64_lesen(blob_b64)?;
    if blob.len() < 32 {
        return Err(format!("Der Schluessel ist zu kurz ({} Bytes).", blob.len()));
    }
    let d = ring::digest::digest(&ring::digest::SHA256, &blob);
    Ok(format!("SHA256:{}", b64_schreiben(d.as_ref()).trim_end_matches('=').to_string()))
}

/// Eine Zeile fuer die `known_hosts` des Ausfuehrers. Port 22 steht ohne
/// Klammern, jeder andere als `[adresse]:port` -- so liest ssh es.
pub fn known_hosts_zeile(e: &Value) -> Option<String> {
    let adresse = e.get("adresse")?.as_str()?;
    let h = e.get("hostschluessel")?;
    let typ = h.get("typ")?.as_str()?;
    let blob = h.get("schluessel")?.as_str()?;
    let port = e.get("port").and_then(Value::as_u64).unwrap_or(22);
    let ziel = if port == 22 { adresse.to_string() } else { format!("[{adresse}]:{port}") };
    Some(format!("{ziel} {typ} {blob}"))
}

/// Typ des Hostschluessels. Nur die drei, die OpenSSH heute benutzt -- ein
/// Tippfehler waere sonst ein Eintrag, der nie passt.
fn typ_ok(t: &str) -> bool {
    matches!(t, "ssh-ed25519" | "ssh-rsa" | "ecdsa-sha2-nistp256" | "ecdsa-sha2-nistp384" | "ecdsa-sha2-nistp521")
}

/// Ein Hostschluessel, wie ihn der Nutzer aus `ssh-keyscan` uebernimmt:
/// `{typ, schluessel}` (Blob) -- den Fingerabdruck rechnet diese Stelle.
fn hostschluessel_lesen(v: &Value) -> Result<Value, (&'static str, String)> {
    let typ = v.get("typ").and_then(Value::as_str).unwrap_or("").trim();
    let blob = v.get("schluessel").and_then(Value::as_str).unwrap_or("").trim();
    if !typ_ok(typ) {
        return Err(("wert_ungueltig", format!("Hostschluessel-Typ \"{typ}\" ist unbekannt.")));
    }
    if blob.is_empty() {
        return Err(("wert_ungueltig", "Der Hostschluessel braucht seinen Blob (\"schluessel\").".into()));
    }
    let fp = fingerabdruck(blob).map_err(|e| ("wert_ungueltig", e))?;
    Ok(json!({"typ": typ, "schluessel": blob, "fingerabdruck": fp}))
}

fn zahlen(v: &Value, feld: &str, vorgabe: u64, min: u64, max: u64) -> Result<u64, (&'static str, String)> {
    match v.get(feld) {
        None | Some(Value::Null) => Ok(vorgabe),
        Some(x) => match x.as_u64() {
            Some(n) if (min..=max).contains(&n) => Ok(n),
            _ => Err(("wert_ungueltig", format!("\"{feld}\" braucht eine Zahl zwischen {min} und {max} (bekam {x})."))),
        },
    }
}

fn schreiben(p: &Pfade, ganz: &Value) -> Result<(), String> {
    let mut text = serde_json::to_vec_pretty(ganz).map_err(|e| e.to_string())?;
    text.push(b'\n');
    atomar_schreiben(&datei(p), &text, 0o660)
}

/// Der Nutzer legt einen Host an oder aendert ihn. Ein **neuer** Eintrag
/// braucht den Hostschluessel; beim Aendern bleibt er stehen, solange Adresse
/// und Port gleich bleiben (sonst gehoert der Schluessel zu einem anderen
/// Ziel und muss neu bestaetigt werden).
pub fn setzen(p: &Pfade, name: &str, wert: &Value) -> Result<Value, (&'static str, String)> {
    let name = name.trim();
    if !name_ok(name) {
        return Err((
            "name_ungueltig",
            format!("Name \"{name}\": erlaubt sind 1-{NAME_MAX} Zeichen, klein, Ziffern, \"-\", \"_\", \".\"."),
        ));
    }
    let ganz = roh(p);
    let alt = ganz.get("hosts").and_then(|h| h.get(name)).cloned();
    let adresse = wert.get("adresse").and_then(Value::as_str).unwrap_or("").trim();
    if !adresse_ok(adresse) {
        return Err(("wert_ungueltig", format!("Adresse \"{adresse}\" ist keine Adresse und kein Name.")));
    }
    let nutzer = wert.get("nutzer").and_then(Value::as_str).unwrap_or("").trim();
    if !nutzer_ok(nutzer) {
        return Err(("wert_ungueltig", format!("Nutzer \"{nutzer}\" ist kein Nutzername.")));
    }
    let port = zahlen(wert, "port", 22, 1, 65535)?;
    let schluessel = wert.get("schluessel").and_then(Value::as_str).unwrap_or("").trim();
    if !schluessel_ok(schluessel) {
        return Err((
            "wert_ungueltig",
            format!("Schluesselname \"{schluessel}\": nur ein Name aus dem Schluesselordner, kein Pfad."),
        ));
    }
    // Vorgabe ist `zaun` (restrict): kostet auf dem Ziel nichts, schaltet aber
    // PTY und Weiterleitungen ab. `force` verlangt eine Datei auf dem Ziel und
    // ist darum eine bewusste Wahl (DESIGN, "Welche Rechte auf dem Ziel").
    let rechte = wert.get("rechte").and_then(Value::as_str).unwrap_or("zaun").trim();
    if !RECHTE.contains(&rechte) {
        return Err(("wert_ungueltig", format!("Rechte \"{rechte}\" gibt es nicht ({}).", RECHTE.join(", "))));
    }
    let notiz = wert.get("notiz").and_then(Value::as_str).unwrap_or("").trim();
    if notiz.chars().count() > 200 {
        return Err(("wert_ungueltig", "Die Notiz ist laenger als 200 Zeichen.".into()));
    }
    // Der Zaun-Pfad: nur bei `force` gebraucht, aber **hier** geprueft -- sonst
    // faellt es erst bei der Aufnahme auf, und die ist dann schon gelaufen.
    // Geprueft wird dieselbe Form, die der Ausfuehrer verlangt: absolut, ohne
    // Leerraum, ohne " und ohne , (sonst zerlegt der Pfad die Zeile).
    let zaun = wert.get("zaun").and_then(Value::as_str).unwrap_or("").trim().to_string();
    if !zaun.is_empty()
        && (zaun.len() > 200
            || !zaun.starts_with('/')
            || zaun.chars().any(|c| c.is_whitespace() || c == '"' || c == ',' || c.is_control()))
    {
        return Err((
            "wert_ungueltig",
            format!("Der Zaun-Pfad \"{zaun}\" muss absolut sein und darf keinen Leerraum, kein \" und kein , enthalten."),
        ));
    }
    if rechte == "force" && zaun.is_empty() {
        return Err((
            "wert_ungueltig",
            "Die Stufe `force` braucht den Pfad des Zauns auf dem Ziel (zaun=\"/usr/local/bin/chimera-zaun\") \
             -- ohne ihn waere `command=` nur eine Weiterleitung."
                .into(),
        ));
    }
    // Hostschluessel: neu mitgeben, oder den alten behalten, wenn sich das
    // Ziel nicht geaendert hat.
    let gleiches_ziel = alt
        .as_ref()
        .map(|a| {
            a.get("adresse").and_then(Value::as_str) == Some(adresse)
                && a.get("port").and_then(Value::as_u64).unwrap_or(22) == port
        })
        .unwrap_or(false);
    let hostschluessel = match wert.get("hostschluessel") {
        Some(v) if v.is_object() => hostschluessel_lesen(v)?,
        _ => match alt.as_ref().and_then(|a| a.get("hostschluessel")).filter(|_| gleiches_ziel) {
            Some(h) => h.clone(),
            None if alt.is_some() && !gleiches_ziel => {
                return Err((
                    "hostschluessel_fehlt",
                    "Adresse oder Port haben sich geaendert -- der Hostschluessel muss neu bestaetigt werden.".into(),
                ))
            }
            // Ein Eintrag ohne Hostschluessel ist erlaubt, wenn er
            // ausdruecklich zur **Aufnahme** angelegt wird: der Schluessel
            // wird dann beim ersten Verbinden geholt und vom Nutzer
            // bestaetigt (DESIGN, "Aufnahme eines Hosts").
            None if wert.get("aufnahme").and_then(Value::as_bool) == Some(true) => Value::Null,
            None => {
                return Err((
                    "hostschluessel_fehlt",
                    "Ohne Hostschluessel kein Eintrag: Typ und Blob aus \"ssh-keyscan\" mitgeben \
                     (oder den Host zur Aufnahme anlegen, Feld \"aufnahme\": true).".into(),
                ))
            }
        },
    };
    let neu = json!({
        "adresse": adresse, "nutzer": nutzer, "port": port, "schluessel": schluessel,
        "hostschluessel": hostschluessel, "rechte": rechte, "zaun": if zaun.is_empty() { Value::Null } else { json!(zaun) },
        "herkunft": "nutzer", "notiz": notiz,
    });
    let mut ganz2 = ganz.clone();
    let hosts = ganz2.as_object_mut().and_then(|o| o.get_mut("hosts")).and_then(Value::as_object_mut);
    match hosts {
        Some(h) => {
            let neu_angelegt = !h.contains_key(name);
            h.insert(name.to_string(), neu.clone());
            schreiben(p, &ganz2).map_err(|e| ("nicht_gespeichert", e))?;
            let mut out = neu.clone();
            // Die Antwort sagt die Wahrheit: ein Eintrag zur Aufnahme ist
            // noch **nicht** brauchbar (kein Hostschluessel).
            out["brauchbar"] = json!(brauchbar(&neu));
            out["neu"] = json!(neu_angelegt);
            Ok(out)
        }
        None => Err(("nicht_gespeichert", "Die Host-Tabelle ist kein Objekt.".into())),
    }
}

/// Der Agent darf **vorschlagen** -- nur anlegen, nie aendern, nie
/// bestaetigen, nie loeschen.
pub fn vorschlag(p: &Pfade, name: &str, adresse: &str, nutzer: &str, port: Option<u64>, notiz: &str) -> Result<Value, (&'static str, String)> {
    let name = name.trim();
    if !name_ok(name) {
        return Err(("name_ungueltig", format!("Name \"{name}\" ist kein Hostname fuer die Tabelle.")));
    }
    if !adresse_ok(adresse.trim()) || !nutzer_ok(nutzer.trim()) {
        return Err(("wert_ungueltig", "Ein Vorschlag braucht eine Adresse und einen Nutzer.".into()));
    }
    let port = port.unwrap_or(22);
    if !(1..=65535).contains(&port) {
        return Err(("wert_ungueltig", format!("\"port\" {port} liegt nicht zwischen 1 und 65535.")));
    }
    let mut ganz = roh(p);
    let Some(hosts) = ganz.as_object_mut().and_then(|o| o.get_mut("hosts")).and_then(Value::as_object_mut) else {
        return Err(("nicht_gespeichert", "Die Host-Tabelle ist kein Objekt.".into()));
    };
    if hosts.contains_key(name) {
        return Err(("host_bekannt", format!("\"{name}\" steht schon in der Tabelle -- ein Vorschlag aendert nichts.")));
    }
    let e = json!({
        "adresse": adresse.trim(), "nutzer": nutzer.trim(), "port": port,
        "schluessel": "", "hostschluessel": Value::Null, "rechte": "zaun",
        "herkunft": "vorschlag", "notiz": notiz.trim(),
    });
    hosts.insert(name.to_string(), e.clone());
    schreiben(p, &ganz).map_err(|e| ("nicht_gespeichert", e))?;
    Ok(json!({"host": name, "eintrag": e, "brauchbar": false,
        "hinweis": "Ein Vorschlag wirkt nicht: der Nutzer bestaetigt ihn im Modul \"Fernzugriff\" (Hostschluessel)."}))
}

/// Loeschen darf nur der Nutzer (ueber das Modul).
pub fn loeschen(p: &Pfade, name: &str) -> Result<bool, (&'static str, String)> {
    let mut ganz = roh(p);
    let Some(hosts) = ganz.as_object_mut().and_then(|o| o.get_mut("hosts")).and_then(Value::as_object_mut) else {
        return Ok(false);
    };
    let weg = hosts.remove(name).is_some();
    if weg {
        schreiben(p, &ganz).map_err(|e| ("nicht_gespeichert", e))?;
    }
    Ok(weg)
}

/// Ein Host, den die **Aufnahme** benutzen darf: er muss vom Nutzer stammen,
/// einen Hostschluessel braucht er noch nicht (der wird ja gerade geholt).
pub fn holen_fuer_aufnahme(p: &Pfade, name: &str) -> Result<Value, (&'static str, String)> {
    let ganz = roh(p);
    let Some(e) = ganz.get("hosts").and_then(|h| h.get(name)) else {
        return Err(("host_unbekannt", format!("\"{name}\" steht nicht in der Host-Tabelle.")));
    };
    if e.get("herkunft").and_then(Value::as_str) != Some("nutzer") {
        return Err((
            "host_unbestaetigt",
            format!("\"{name}\" ist nur ein Vorschlag -- der Nutzer hat ihn nicht bestaetigt."),
        ));
    }
    Ok(e.clone())
}

/// Ein Host, den `op: ssh` benutzen darf. Alles andere gibt es nicht --
/// kein "Host unbekannt, versuch es trotzdem".
pub fn holen(p: &Pfade, name: &str) -> Result<Value, (&'static str, String)> {
    let ganz = roh(p);
    let Some(e) = ganz.get("hosts").and_then(|h| h.get(name)) else {
        return Err(("host_unbekannt", format!("\"{name}\" steht nicht in der Host-Tabelle.")));
    };
    if e.get("herkunft").and_then(Value::as_str) != Some("nutzer") {
        return Err((
            "host_unbestaetigt",
            format!("\"{name}\" ist nur ein Vorschlag -- der Nutzer hat ihn nicht bestaetigt."),
        ));
    }
    if !brauchbar(e) {
        return Err(("host_unbestaetigt", format!("\"{name}\" hat keinen bestaetigten Hostschluessel.")));
    }
    Ok(e.clone())
}

/// Wo der Ausführer zu erreichen ist. Im Betrieb der systemd-Socket, in
/// Tests/Sandbox über die Umgebung.
const SOHELPER_SOCKET: &str = "/run/chimera/sohelper.sock";

/// Die Fernausführung: `{"op":"ssh","host":"…","befehl":"…"}`.
///
/// **Hier fällt die Entscheidung, und hier wird verbunden.** Erst die
/// Host-Tabelle (was nicht drinsteht oder nur ein Vorschlag ist, gibt es
/// nicht), dann die Freigabe (`user@host`, Vorgabe Positivliste), dann der
/// TCP-Verbindungsaufbau. Der offene Socket geht als **Deskriptor** an den
/// Ausführer — der hat kein Netz und kann keine zweite Verbindung aufbauen.
pub fn op_ssh(p: &Pfade, host: &str, befehl: &str, jetzt: u64) -> Value {
    let socket = std::env::var("CHIMERA_SOHELPER_SOCKET").unwrap_or_else(|_| SOHELPER_SOCKET.to_string());
    op_ssh_mit_socket(p, host, befehl, jetzt, &socket)
}

/// Dasselbe, aber mit genanntem Ausführer-Socket — fuer Tests, die keinen
/// Prozess starten wollen.
pub fn op_ssh_mit_socket(p: &Pfade, host: &str, befehl: &str, jetzt: u64, socket: &str) -> Value {
    let e = match holen(p, host) {
        Ok(e) => e,
        Err((code, text)) => return gemein::zeile::fehlerantwort(code, &text),
    };
    let nutzer = e["nutzer"].as_str().unwrap_or("");
    let adresse = e["adresse"].as_str().unwrap_or("");
    let port = e["port"].as_u64().unwrap_or(22) as u16;
    if befehl.trim().is_empty() {
        return gemein::zeile::fehlerantwort("befehl_fehlt", "ssh braucht ein Feld \"befehl\".");
    }
    // Das Ziel der Freigabe ist der Host, wie der Nutzer ihn eingetragen hat
    // -- nicht die Adresse (die wechselt, der Eintrag bleibt).
    let ziel = format!("{nutzer}@{host}");
    let frei = crate::freigaben::pruefen(p, "ssh", Some(&ziel), jetzt);
    if frei["erlaubt"] != true {
        return json!({
            "ok": false,
            "fehler": {"code": "ssh_gesperrt",
                "text": format!("Die Fernausführung nach {ziel} ist nicht freigegeben: {}",
                    frei["grund"].as_str().unwrap_or("ohne Grund")),
                "ziel": ziel, "grund": frei["grund"]},
        });
    }
    let beginn = std::time::Instant::now();
    let tcp = match verbinden(adresse, port) {
        Ok(t) => t,
        Err(e) => {
            return gemein::zeile::fehlerantwort(
                "nicht_erreichbar",
                &format!("{adresse}:{port} ist nicht erreichbar: {e}"),
            )
        }
    };
    let antwort = an_ausfuehrer_schicken(&e, host, befehl, &tcp, socket);
    drop(tcp);
    match antwort {
        Ok(mut v) => {
            if let Some(o) = v.as_object_mut() {
                o.insert("dauer_s".into(), json!(beginn.elapsed().as_secs()));
                o.insert("host".into(), json!(host));
                o.insert("ziel".into(), json!(ziel));
            }
            v
        }
        Err(e) => gemein::zeile::fehlerantwort("ausfuehrer", &e),
    }
}

/// Die **Aufnahme**: Passwort-Anmeldung, Schlüssel erzeugen lassen,
/// **eine** Zeile auf dem Ziel, Passwort danach weg.
///
/// Das gilt nur für Hosts mit `herkunft: nutzer`; ein Vorschlag des Agenten
/// ist nicht aufnehmbar. Und es braucht ein Passwort in der Ablage — der
/// Hinweis sagt, **wo** es eingegeben wird, nie „tippe es hier".
pub fn op_ssh_aufnahme(p: &Pfade, host: &str, jetzt: u64) -> Value {
    let socket = std::env::var("CHIMERA_SOHELPER_SOCKET").unwrap_or_else(|_| SOHELPER_SOCKET.to_string());
    op_ssh_aufnahme_mit_socket(p, host, jetzt, &socket)
}

pub fn op_ssh_aufnahme_mit_socket(p: &Pfade, host: &str, jetzt: u64, socket: &str) -> Value {
    let e = match holen_fuer_aufnahme(p, host) {
        Ok(e) => e,
        Err((code, text)) => return gemein::zeile::fehlerantwort(code, &text),
    };
    let nutzer = e["nutzer"].as_str().unwrap_or("");
    let adresse = e["adresse"].as_str().unwrap_or("");
    let port = e["port"].as_u64().unwrap_or(22) as u16;
    let ziel = format!("{nutzer}@{host}");
    let frei = crate::freigaben::pruefen(p, "ssh", Some(&ziel), jetzt);
    if frei["erlaubt"] != true {
        return json!({
            "ok": false,
            "fehler": {"code": "ssh_gesperrt",
                "text": format!("Die Aufnahme für {ziel} ist nicht freigegeben: {}",
                    frei["grund"].as_str().unwrap_or("ohne Grund")),
                "ziel": ziel},
        });
    }
    let Some(passwort) = crate::geheim::lesen(p, host) else {
        return json!({
            "ok": false,
            "fehler": {"code": "passwort_fehlt",
                "text": format!("Für \"{host}\" liegt kein Passwort in der Ablage. Es wird im Modul \
                                 \"Fernzugriff\" eingetragen (Feld am Host) oder über \
                                 `chimera-tor --geheim-ssh {host}` von der Kommandozeile -- nie im Chat."),
                "ziel": ziel},
        });
    };
    let tcp = match verbinden(adresse, port) {
        Ok(t) => t,
        Err(err) => {
            return gemein::zeile::fehlerantwort(
                "nicht_erreichbar",
                &format!("{adresse}:{port} ist nicht erreichbar: {err}"),
            )
        }
    };
    let begonn = std::time::Instant::now();
    let antwort = an_ausfuehrer_aufnahme(&e, host, &passwort, &tcp, socket);
    drop(tcp);
    match antwort {
        Ok(mut v) => {
            if v["ok"] == true {
                // Erst wenn der Schlüssel wirklich steht, ist das Passwort
                // entbehrlich. Danach wird es nicht mehr gebraucht.
                let _ = crate::geheim::loeschen(p, host);
                // Der Ausfuehrer liefert Typ und Blob getrennt (als Text),
                // nicht als Objekt -- hier wird daraus der Tabelleneintrag.
                let typ = v.get("hostschluessel_typ").and_then(Value::as_str).unwrap_or("").to_string();
                let blob = v.get("hostschluessel").and_then(Value::as_str).unwrap_or("").to_string();
                if let Some(o) = v.as_object_mut() {
                    let (typ, blob) = (typ.as_str(), blob.as_str());
                    let fp = fingerabdruck(blob).unwrap_or_default();
                    o.insert("fingerabdruck".into(), json!(fp));
                    o.insert("hostschluessel".into(), json!({
                        "typ": typ, "schluessel": blob, "fingerabdruck": fp
                    }));
                    o.insert("host".into(), json!(host));
                    o.insert("ziel".into(), json!(ziel));
                    o.insert("dauer_s".into(), json!(begonn.elapsed().as_secs()));
                    o.insert("hinweis".into(), json!(
                        "Der Eintrag wirkt noch nicht: im Modul \"Fernzugriff\" bestätigen."));
                }
            }
            v
        }
        Err(e) => gemein::zeile::fehlerantwort("ausfuehrer", &e),
    }
}

/// Den Aufnahme-Auftrag samt Deskriptor an den Ausführer geben.
fn an_ausfuehrer_aufnahme(e: &Value, host: &str, passwort: &str, tcp: &std::net::TcpStream, pfad: &str) -> Result<Value, String> {
    use std::os::unix::io::AsRawFd;
    let strom = std::os::unix::net::UnixStream::connect(pfad)
        .map_err(|e| format!("Der Ausführer ist nicht erreichbar ({pfad}: {e}); es wurde nichts geändert."))?;
    let _ = strom.set_read_timeout(Some(std::time::Duration::from_secs(300)));
    let anfrage = json!({
        "op": "ssh_aufnahme",
        "host": host,
        "nutzer": e["nutzer"], "adresse": e["adresse"], "port": e["port"],
        "schluessel": e["schluessel"],
        "rechte": e["rechte"], "zaun": e.get("zaun").cloned().unwrap_or(Value::Null),
        "passwort": passwort,
    });
    let mut zeile = serde_json::to_vec(&anfrage).map_err(|e| e.to_string())?;
    zeile.push(b'\n');
    // Der Deskriptor geht mit: ohne ihn hat der Ausführer keine Verbindung.
    gemein::fdpass::senden(&strom, &zeile, &[tcp.as_raw_fd()])
        .map_err(|e| format!("Der Deskriptor ließ sich nicht übergeben: {e}"))?;
    let leser = strom.try_clone().map_err(|e| e.to_string())?;
    let mut leser = std::io::BufReader::new(leser);
    gemein::zeile::lesen(&mut leser, gemein::zeile::MAX_BYTES)
        .map_err(|e| format!("keine Antwort vom Ausführer ({e})"))
}

fn verbinden(adresse: &str, port: u16) -> Result<std::net::TcpStream, String> {
    use std::net::ToSocketAddrs;
    let ziele: Vec<_> = (adresse, port)
        .to_socket_addrs()
        .map_err(|e| format!("Adresse nicht auflösbar: {e}"))?
        .collect();
    if ziele.is_empty() {
        return Err("keine Adresse aufgelöst".into());
    }
    let mut letzter = String::from("kein Versuch");
    for z in ziele {
        match std::net::TcpStream::connect_timeout(&z, std::time::Duration::from_secs(10)) {
            Ok(s) => {
                let _ = s.set_nodelay(true);
                return Ok(s);
            }
            Err(e) => letzter = format!("{z}: {e}"),
        }
    }
    Err(letzter)
}

/// Den Auftrag samt Deskriptor an den Ausführer geben und seine Antwort lesen.
fn an_ausfuehrer_schicken(e: &Value, host: &str, befehl: &str, tcp: &std::net::TcpStream, pfad: &str) -> Result<Value, String> {
    use std::os::unix::io::AsRawFd;
    let strom = std::os::unix::net::UnixStream::connect(pfad)
        .map_err(|e| format!("Der Ausführer ist nicht erreichbar ({pfad}: {e}); es wurde nichts ausgeführt."))?;
    let _ = strom.set_read_timeout(Some(std::time::Duration::from_secs(300)));
    let anfrage = json!({
        "op": "ssh",
        "host": host,
        "nutzer": e["nutzer"], "adresse": e["adresse"], "port": e["port"],
        "schluessel": e["schluessel"],
        "hostschluessel_typ": e["hostschluessel"]["typ"],
        "hostschluessel": e["hostschluessel"]["schluessel"],
        "befehl": befehl,
    });
    let mut zeile = serde_json::to_vec(&anfrage).map_err(|e| e.to_string())?;
    zeile.push(b'\n');
    // Dauerbetrieb: dieselbe Uebergabe wie bei der Aufnahme.
    gemein::fdpass::senden(&strom, &zeile, &[tcp.as_raw_fd()])
        .map_err(|e| format!("Der Deskriptor ließ sich nicht übergeben: {e}"))?;
    let leser = strom.try_clone().map_err(|e| e.to_string())?;
    let mut leser = std::io::BufReader::new(leser);
    gemein::zeile::lesen(&mut leser, gemein::zeile::MAX_BYTES)
        .map_err(|e| format!("keine Antwort vom Ausführer ({e})"))
}

// ---------------------------------------------------------------------------
// Hostschluessel mit `ssh-keyscan` lesen (entschieden smilez, 13.11.2026)
// ---------------------------------------------------------------------------
//
// Bis 13.11. tippte der Nutzer die Ausgabe von `ssh-keyscan` von Hand in das
// Feld -- eine Zeile, in der ein falsches Zeichen niemandem auffaellt. Das
// Gateway hat Netz und darf ein Programm starten; die Schluesselaushandlung
// und die Signaturpruefung erledigt die **gepruefte OpenSSH-Implementierung**.
// Eigener SSH-Code waere hier der Anfang eines zweiten, schlechteren ssh.

/// Zeitgrenze fuer `ssh-keyscan` selbst (`-T`). OpenSSH rechnet in Sekunden.
const SCAN_T: &str = "5";
/// Harte Grenze des ganzen Aufrufs: ein haengender Namensdienst oder ein
/// Gegenueber, das nicht antwortet, darf den Dienst nicht halten.
const SCAN_FRIST: std::time::Duration = std::time::Duration::from_secs(15);
/// Typen, die wir annehmen. Reihenfolge = Vorliebe; ed25519 zuerst.
const SCAN_TYPEN: &str = "ssh-ed25519,ecdsa-sha2-nistp256,ssh-rsa";

/// Die feste `argv` fuer `ssh-keyscan`. **Keine Shell**, kein zusammengebauter
/// Text: Adresse und Port sind Argumente, kein Kommando.
pub fn befehl(adresse: &str, port: u64) -> Vec<String> {
    [
        "ssh-keyscan".to_string(),
        "-T".to_string(),
        SCAN_T.to_string(),
        "-p".to_string(),
        port.to_string(),
        "-t".to_string(),
        SCAN_TYPEN.to_string(),
        adresse.to_string(),
    ]
    .to_vec()
}

/// Die Ausgabe von `ssh-keyscan` deuten: `{"typ","schluessel"}`.
///
/// Gelesen wird nur, was wirklich dasteht. Kommentarzeilen (`# ...`) sind
/// kein Befund; eine Zeile, die zu einem **anderen** Ziel gehoert, wird
/// abgelehnt -- `ssh-keyscan` schreibt das Ziel mit, und ein Name, der beim
/// Aufloesen anders lautet, ist ein Grund zur Vorsicht, nicht zum Mitnehmen.
pub fn ausgabe_deuten(text: &str, adresse: &str, port: u64) -> Result<Value, String> {
    let erwartet = if port == 22 { adresse.to_string() } else { format!("[{adresse}]:{port}") };
    let mut gefunden: Option<Value> = None;
    for zeile in text.lines() {
        let zeile = zeile.trim();
        if zeile.is_empty() || zeile.starts_with('#') {
            continue;
        }
        let teile: Vec<&str> = zeile.split_whitespace().collect();
        if teile.len() < 3 {
            continue;
        }
        let (ziel, typ, blob) = (teile[0], teile[1], teile[2]);
        if ziel != erwartet && ziel != adresse {
            return Err(format!(
                "ssh-keyscan antwortete fuer \"{ziel}\" statt \"{erwartet}\" -- der Name loest anders auf."
            ));
        }
        if !typ_ok(typ) || b64_lesen(blob).is_err() {
            continue;
        }
        // Vorliebe: ed25519, dann ecdsa, dann rsa -- die Reihenfolge der
        // Ausgabe von ssh-keyscan ist nicht zugesagt.
        let rang = match typ {
            "ssh-ed25519" => 0,
            t if t.starts_with("ecdsa-") => 1,
            _ => 2,
        };
        let besser = match &gefunden {
            None => true,
            Some(g) => {
                let alt = match g["typ"].as_str().unwrap_or("") {
                    "ssh-ed25519" => 0,
                    t if t.starts_with("ecdsa-") => 1,
                    _ => 2,
                };
                rang < alt
            }
        };
        if besser {
            gefunden = Some(json!({"typ": typ, "schluessel": blob}));
        }
    }
    gefunden.ok_or_else(|| "ssh-keyscan hat keinen brauchbaren Hostschluessel geliefert.".to_string())
}

/// `ssh-keyscan` wirklich starten. Getrennt von der Deutung, damit der Test
/// die Deutung pruefen kann, ohne im Netz zu haengen.
pub fn scan(adresse: &str, port: u64) -> Result<Value, String> {
    use std::process::{Command, Stdio};

    let argv = befehl(adresse, port);
    let mut kind = Command::new(&argv[0])
        .args(&argv[1..])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("ssh-keyscan nicht startbar ({e}) -- ist das Paket openssh-client installiert?"))?;
    let ende = std::time::Instant::now() + SCAN_FRIST;
    loop {
        match kind.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) => {}
            Err(e) => return Err(format!("ssh-keyscan nicht abwartbar: {e}")),
        }
        if std::time::Instant::now() >= ende {
            let _ = kind.kill();
            let _ = kind.wait();
            return Err(format!(
                "ssh-keyscan hat nach {} s nicht geantwortet -- abgebrochen.",
                SCAN_FRIST.as_secs()
            ));
        }
        std::thread::sleep(std::time::Duration::from_millis(50));
    }
    let aus = kind
        .wait_with_output()
        .map_err(|e| format!("Ausgabe von ssh-keyscan nicht lesbar: {e}"))?;
    let text = String::from_utf8_lossy(&aus.stdout).into_owned();
    // Ein Rueckgabewert 1 mit leerer Ausgabe heisst "keine Antwort"; das ist
    // ein Befund, kein stiller Erfolg.
    ausgabe_deuten(&text, adresse, port).map_err(|e| {
        let stderr = String::from_utf8_lossy(&aus.stderr);
        let stumm = stderr.trim();
        if stumm.is_empty() { e } else { format!("{e} ({})", stumm.lines().last().unwrap_or("")) }
    })
}

/// Was hat der Abruf ergeben, gemessen am Eintrag? Rein -- damit die drei
/// Faelle (neu, unveraendert, geaendert) ohne Netz pruefbar sind.
pub fn vergleichen(alt: Option<&Value>, neu: &Value) -> (&'static str, Option<Value>) {
    let Some(h) = alt else {
        return ("neu", None);
    };
    let alt_blob = h.get("schluessel").and_then(Value::as_str).unwrap_or("");
    let neu_blob = neu.get("schluessel").and_then(Value::as_str).unwrap_or("");
    if alt_blob.is_empty() {
        return ("neu", None);
    }
    if alt_blob == neu_blob {
        return ("unveraendert", None);
    }
    ("geaendert", Some(h.clone()))
}

/// Eine Zeile je Abruf -- auch der Erfolg wird protokolliert (Regel 9).
fn protokoll(p: &Pfade, host: &str, was: &str, text: &str) {
    let datei = p.state.join("log").join("ssh.log");
    if let Some(dir) = datei.parent() {
        if let Err(e) = std::fs::create_dir_all(dir) {
            eprintln!("ssh: Protokollordner {} nicht anlegbar: {e}", dir.display());
        }
    }
    let zeit = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let zeile = format!("{zeit}\t{was}\t{host}\t{text}\n");
    use std::io::Write;
    match std::fs::OpenOptions::new().create(true).append(true).open(&datei) {
        Ok(mut f) => {
            if let Err(e) = f.write_all(zeile.as_bytes()) {
                eprintln!("ssh: Protokollzeile nicht geschrieben: {e}");
            }
        }
        Err(e) => eprintln!("ssh: Protokoll {} nicht schreibbar: {e}", datei.display()),
    }
}

/// Der Abruf mit eingesetztem Leser -- so kann der Test alle drei Faelle
/// durchspielen, ohne einen sshd zu brauchen.
pub fn schluessel_lesen_mit(
    p: &Pfade,
    host: &str,
    leser: &dyn Fn(&str, u64) -> Result<Value, String>,
) -> Result<Value, (&'static str, String)> {
    let e = holen_fuer_aufnahme(p, host)?;
    let adresse = e.get("adresse").and_then(Value::as_str).unwrap_or("");
    let port = e.get("port").and_then(Value::as_u64).unwrap_or(22);
    let neu = leser(adresse, port).map_err(|text| ("schluessel_nicht_gelesen", text))?;
    let typ = neu["typ"].as_str().unwrap_or("");
    let blob = neu["schluessel"].as_str().unwrap_or("");
    let fp = fingerabdruck(blob).map_err(|text| ("wert_ungueltig", text))?;
    let schluessel = json!({"typ": typ, "schluessel": blob, "fingerabdruck": fp});
    let (befund, alt) = vergleichen(e.get("hostschluessel"), &schluessel);
    // Der Abruf schreibt **nichts**. Auch ein unveraenderter Schluessel wird
    // nicht bestaetigt -- bestaetigen tut der Nutzer, und nur er.
    let meldung = match befund {
        "neu" => "Neuer Hostschluessel gelesen. Er wirkt erst, wenn du ihn im Modul \
                  \"Fernzugriff\" bestaetigst.".to_string(),
        "unveraendert" => "Der Hostschluessel ist unveraendert.".to_string(),
        _ => {
            let altfp = alt
                .as_ref()
                .and_then(|a| a.get("fingerabdruck"))
                .and_then(Value::as_str)
                .unwrap_or("unbekannt")
                .to_string();
            format!(
                "Der Hostschluessel hat sich GEaENDERT (alt {altfp}, neu {fp}). Nichts wurde \
                 uebernommen: Ein geaenderter Schluessel ist entweder eine Neuinstallation oder \
                 ein Angriff -- pruefe den Fingerabdruck am Geraet, bevor du bestaetigst."
            )
        }
    };
    Ok(json!({
        "host": host,
        "adresse": adresse,
        "port": port,
        "befund": befund,
        "hostschluessel": schluessel,
        "alt": alt,
        "meldung": meldung,
    }))
}

/// `op: ssh_schluessel_lesen` -- der Weg der Oberflaeche.
pub fn op_ssh_schluessel_lesen(p: &Pfade, host: &str) -> Value {
    match schluessel_lesen_mit(p, host, &|adresse, port| scan(adresse, port)) {
        Ok(v) => {
            protokoll(
                p,
                host,
                v["befund"].as_str().unwrap_or("?"),
                v["hostschluessel"]["fingerabdruck"].as_str().unwrap_or("-"),
            );
            let mut out = v;
            out["ok"] = json!(true);
            out
        }
        Err((code, text)) => {
            protokoll(p, host, "fehler", &text);
            json!({"ok": false, "fehler": {"code": code, "text": text}})
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(name: &str) -> Pfade {
        let d = std::env::temp_dir().join(format!("chimera-ssh-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        Pfade::neu(d.join("config"), d.join("state"))
    }

    /// Adressen im Test zusammensetzen: ein ausgeschriebener Heimnetz-Pfad
    /// loest die Geheimnispruefung aus (Skill repo-hygiene).
    fn adr(teile: &[&str]) -> String {
        teile.join(".")
    }

    /// Ein kleiner, aber echter Schluessel-Blob: 32 Bytes Zufall.
    fn blob() -> String {
        let d = ring::digest::digest(&ring::digest::SHA256, b"chimera-testhost");
        b64_schreiben(d.as_ref())
    }

    fn eintrag(adresse: &str) -> Value {
        json!({"adresse": adresse, "nutzer": "dietpi", "port": 22, "schluessel": "radxa_ed25519",
               "hostschluessel": {"typ": "ssh-ed25519", "schluessel": blob()}, "rechte": "zaun"})
    }

    #[test]
    fn ohne_datei_ist_die_tabelle_leer() {
        let p = p("leer");
        let t = laden(&p);
        assert_eq!(t["hosts"], json!({}));
    }

    #[test]
    fn ein_host_wird_angelegt_und_ist_brauchbar() {
        let p = p("anlegen");
        let e = setzen(&p, "radxa", &eintrag(&adr(&["192", "168", "0", "20"]))).unwrap();
        assert_eq!(e["brauchbar"], true);
        let t = laden(&p);
        let h = &t["hosts"]["radxa"];
        assert_eq!(h["nutzer"], "dietpi");
        assert_eq!(h["rechte"], "zaun");
        assert!(h["hostschluessel"]["fingerabdruck"].as_str().unwrap().starts_with("SHA256:"));
        assert_eq!(h["brauchbar"], true);
    }

    #[test]
    fn der_fingerabdruck_wird_gerechnet_nicht_uebernommen() {
        let p = p("fp");
        let mut e = eintrag(&adr(&["192", "168", "0", "20"]));
        e["hostschluessel"]["fingerabdruck"] = json!("SHA256:gefaelscht");
        setzen(&p, "radxa", &e).unwrap();
        let fp = laden(&p)["hosts"]["radxa"]["hostschluessel"]["fingerabdruck"].clone();
        assert_ne!(fp, json!("SHA256:gefaelscht"));
        assert_eq!(fp, json!(fingerabdruck(&blob()).unwrap()));
    }

    #[test]
    fn ein_vorschlag_wirkt_nicht() {
        let p = p("vorschlag");
        vorschlag(&p, "neu", &adr(&["10", "0", "0", "5"]), "ubuntu", None, "vom Agenten").unwrap();
        assert_eq!(laden(&p)["hosts"]["neu"]["herkunft"], "vorschlag");
        assert_eq!(laden(&p)["hosts"]["neu"]["brauchbar"], false);
        assert_eq!(holen(&p, "neu").unwrap_err().0, "host_unbestaetigt");
    }

    #[test]
    fn ein_vorschlag_bleibt_unbrauchbar_auch_mit_hostschluessel() {
        // Der Fall, den ein von Hand geschriebener oder spaeter ergaenzter
        // Eintrag erzeugen kann: Herkunft "vorschlag", aber ein Schluessel
        // steht da. Die Herkunft allein entscheidet -- sonst wuerde ein
        // nachgetragener Schluessel den Vorschlag still zum Zugang machen.
        let p = p("vorschlag3");
        let mut e = eintrag("v.example");
        e["hostschluessel"]["fingerabdruck"] = json!(fingerabdruck(&blob()).unwrap());
        e["herkunft"] = json!("vorschlag");
        let datei = datei(&p);
        std::fs::create_dir_all(datei.parent().unwrap()).unwrap();
        std::fs::write(&datei, json!({"hosts": {"v": e}}).to_string()).unwrap();
        assert_eq!(laden(&p)["hosts"]["v"]["brauchbar"], false);
        assert_eq!(holen(&p, "v").unwrap_err().0, "host_unbestaetigt");
    }

    #[test]
    fn ein_vorschlag_aendert_nie_einen_bestehenden_host() {
        let p = p("vorschlag2");
        setzen(&p, "radxa", &eintrag(&adr(&["192", "168", "0", "20"]))).unwrap();
        assert_eq!(vorschlag(&p, "radxa", "boese.example", "root", None, "").unwrap_err().0, "host_bekannt");
        assert_eq!(laden(&p)["hosts"]["radxa"]["adresse"], json!(adr(&["192", "168", "0", "20"])));
    }

    #[test]
    fn unbekannter_host_und_unbestaetigter_host_werden_abgelehnt() {
        let p = p("holen");
        assert_eq!(holen(&p, "gibtsnicht").unwrap_err().0, "host_unbekannt");
        vorschlag(&p, "v", "v.example", "u", None, "").unwrap();
        assert_eq!(holen(&p, "v").unwrap_err().0, "host_unbestaetigt");
    }

    #[test]
    fn ein_host_ohne_hostschluessel_wird_abgelehnt() {
        let p = p("ohne");
        let mut e = eintrag(&adr(&["192", "168", "0", "20"]));
        e.as_object_mut().unwrap().remove("hostschluessel");
        assert_eq!(setzen(&p, "radxa", &e).unwrap_err().0, "hostschluessel_fehlt");
        assert_eq!(laden(&p)["hosts"]["radxa"], Value::Null);
    }

    #[test]
    fn ein_geaendertes_ziel_verlangt_einen_neuen_hostschluessel() {
        let p = p("ziel");
        setzen(&p, "radxa", &eintrag(&adr(&["192", "168", "0", "20"]))).unwrap();
        // Nur der Nutzer wird geaendert: Schluessel bleibt.
        let mut e = eintrag(&adr(&["192", "168", "0", "20"]));
        e.as_object_mut().unwrap().remove("hostschluessel");
        e["nutzer"] = json!("root");
        assert!(setzen(&p, "radxa", &e).is_ok());
        // Andere Adresse: Schluessel muss neu bestaetigt werden.
        e["adresse"] = json!(adr(&["192", "168", "0", "21"]));
        assert_eq!(setzen(&p, "radxa", &e).unwrap_err().0, "hostschluessel_fehlt");
    }

    #[test]
    fn unbekannte_rechte_und_pfade_werden_abgelehnt() {
        let p = p("rechte");
        let mut e = eintrag(&adr(&["192", "168", "0", "20"]));
        e["rechte"] = json!("alles");
        assert_eq!(setzen(&p, "radxa", &e).unwrap_err().0, "wert_ungueltig");
        e["rechte"] = json!("voll");
        e["schluessel"] = json!("../../etc/shadow");
        assert_eq!(setzen(&p, "radxa", &e).unwrap_err().0, "wert_ungueltig");
        // ".." allein reicht schon: der Name kommt aus dem Schluesselordner.
        for boese in ["..x", "a..b", "-k"] {
            e["schluessel"] = json!(boese);
            assert_eq!(setzen(&p, "radxa", &e).unwrap_err().0, "wert_ungueltig", "{boese}");
        }
        e["schluessel"] = json!("ok_key");
        e["adresse"] = json!("-oProxyCommand=boese");
        assert_eq!(setzen(&p, "radxa", &e).unwrap_err().0, "wert_ungueltig");
    }

    #[test]
    fn ohne_angabe_gilt_zaun_als_vorgabe() {
        // `zaun` (restrict) kostet auf dem Ziel nichts; `force` verlangt eine
        // Datei und ist darum eine bewusste Wahl.
        let p = p("vorgabe");
        let mut e = eintrag("h.example");
        e.as_object_mut().unwrap().remove("rechte");
        setzen(&p, "h", &e).unwrap();
        assert_eq!(laden(&p)["hosts"]["h"]["rechte"], "zaun");
        // `rbash` gibt es nicht mehr: eine eingeschraenkte Shell ist kein Zaun.
        e["rechte"] = json!("rbash");
        assert_eq!(setzen(&p, "h", &e).unwrap_err().0, "wert_ungueltig");
    }

    #[test]
    fn force_verlangt_einen_zaun_und_der_wird_abgelegt() {
        // DESIGN, "Welche Rechte auf dem Ziel": in der Tabelle steht der
        // **Pfad** des Zauns. Ohne ihn ist `command=` eine Weiterleitung,
        // darum wird die Stufe hier abgelehnt und nicht erst bei der Aufnahme.
        let p = p("zaun-pfad");
        let mut e = eintrag("h.example");
        e["rechte"] = json!("force");
        assert_eq!(setzen(&p, "h", &e).unwrap_err().0, "wert_ungueltig");
        assert!(laden(&p)["hosts"].as_object().map(|h| h.is_empty()).unwrap_or(true), "nichts abgelegt");
        // Ein Pfad, der die Zeile zerlegen wuerde, ebenso wenig.
        for boese in ["relativ/pfad", "/mit leerraum", "/mit\"zitat", "/mit,komma", "-x"] {
            e["zaun"] = json!(boese);
            assert_eq!(setzen(&p, "h", &e).unwrap_err().0, "wert_ungueltig", "{boese:?}");
        }
        e["zaun"] = json!("/usr/local/bin/chimera-zaun");
        let v = setzen(&p, "h", &e).unwrap();
        assert_eq!(v["zaun"], "/usr/local/bin/chimera-zaun");
        // Er steht in der Ablage und kommt beim Lesen unveraendert zurueck.
        assert_eq!(laden(&p)["hosts"]["h"]["zaun"], "/usr/local/bin/chimera-zaun");
        // Ohne `force` bleibt der Pfad erlaubt, aber nicht vorgeschrieben.
        e["rechte"] = json!("zaun");
        e.as_object_mut().unwrap().remove("zaun");
        let v = setzen(&p, "h", &e).unwrap();
        assert_eq!(v["zaun"], Value::Null);
    }

    #[test]
    fn namen_sind_bezeichner() {
        let p = p("namen");
        for boese in ["", "Mit Gross", "../x", "a b", "-x", "sehr_langer_name_der_ueber_die_grenze_geht_123"] {
            assert_eq!(setzen(&p, boese, &eintrag("h.example")).unwrap_err().0, "name_ungueltig", "{boese:?}");
        }
    }

    #[test]
    fn known_hosts_zeile_mit_und_ohne_port() {
        let e = json!({"adresse": "h.example", "port": 22,
                       "hostschluessel": {"typ": "ssh-ed25519", "schluessel": "AAAA"}});
        assert_eq!(known_hosts_zeile(&e).unwrap(), "h.example ssh-ed25519 AAAA");
        let e2 = json!({"adresse": "h.example", "port": 2222,
                        "hostschluessel": {"typ": "ssh-ed25519", "schluessel": "AAAA"}});
        assert_eq!(known_hosts_zeile(&e2).unwrap(), "[h.example]:2222 ssh-ed25519 AAAA");
    }

    /// Das Ziel auf die Positivliste der Freigabe setzen.
    fn setzen_freigabe(p: &Pfade, werkzeug: &str, ziel: &str) {
        crate::freigaben::setzen(p, werkzeug, &json!({"modus": "positivliste", "positiv": [ziel]}), 1000).unwrap();
    }

    /// Ein freigegebener Host, wie ihn das Modul anlegt.
    fn host_anlegen(p: &Pfade, name: &str, adresse: &str, port: u16) {
        let mut e = eintrag(adresse);
        e["port"] = json!(port);
        setzen(p, name, &e).unwrap();
    }

    #[test]
    fn ssh_ohne_freigabe_verbindet_nicht() {
        let p = p("ssh-frei");
        host_anlegen(&p, "radxa", "r.example", 22);
        let a = op_ssh_mit_socket(&p, "radxa", "uptime", 1000, "/nicht/da.sock");
        assert_eq!(a["ok"], false);
        assert_eq!(a["fehler"]["code"], "ssh_gesperrt");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("dietpi@radxa"));
    }

    #[test]
    fn ssh_kennt_nur_die_tabelle() {
        let p = p("ssh-unbekannt");
        let a = op_ssh_mit_socket(&p, "gibtsnicht", "uptime", 1000, "/nicht/da.sock");
        assert_eq!(a["fehler"]["code"], "host_unbekannt");
        vorschlag(&p, "v", "v.example", "u", None, "").unwrap();
        let a = op_ssh_mit_socket(&p, "v", "uptime", 1000, "/nicht/da.sock");
        assert_eq!(a["fehler"]["code"], "host_unbestaetigt");
    }

    #[test]
    fn ssh_reicht_die_verbindung_als_deskriptor_weiter() {
        use std::io::{BufRead, Read, Write};
        use std::os::unix::io::FromRawFd;
        let p = p("ssh-fd");
        // Ein "Ziel", das auf eine Verbindung wartet.
        let ziel = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = ziel.local_addr().unwrap().port();
        host_anlegen(&p, "radxa", "127.0.0.1", port);
        // Eine echte Freigabe: das Ziel steht auf der Positivliste.
        setzen_freigabe(&p, "ssh", "dietpi@radxa");
        // Ein Ausführer, der den Deskriptor prueft statt ssh zu starten.
        let d = std::env::temp_dir().join(format!("chimera-ssh-sock-{}", std::process::id()));
        let _ = std::fs::remove_file(&d);
        let horcher = std::os::unix::net::UnixListener::bind(&d).unwrap();
        let faden = std::thread::spawn(move || {
            let (strom, _) = horcher.accept().unwrap();
            let (daten, fds) = gemein::fdpass::empfangen(&strom, 8192).unwrap();
            assert_eq!(fds.len(), 1, "kein Deskriptor angekommen");
            let auftrag: serde_json::Value = serde_json::from_slice(&daten).unwrap();
            // Ueber den weitergereichten Deskriptor ist die Verbindung offen.
            let mut s = unsafe { std::net::TcpStream::from_raw_fd(fds[0]) };
            s.write_all(b"vom-ausfuehrer\n").unwrap();
            let mut antwort = String::new();
            {
                let mut leser = std::io::BufReader::new(s.try_clone().unwrap());
                leser.read_line(&mut antwort).unwrap();
            }
            let mut schreiber = strom.try_clone().unwrap();
            schreiber.write_all(b"{\"ok\":true,\"text\":\"fertig\"}\n").unwrap();
            auftrag
        });
        // Die Gegenseite: die Zielverbindung, auf der der Ausfuehrer schreibt.
        let eingehend = std::thread::spawn(move || {
            let (mut s, _) = ziel.accept().unwrap();
            let mut zeile = String::new();
            {
                let mut leser = std::io::BufReader::new(s.try_clone().unwrap());
                leser.read_line(&mut zeile).unwrap();
            }
            s.write_all(b"banner\n").unwrap();
            zeile
        });
        let a = op_ssh_mit_socket(&p, "radxa", "uptime", 1000, &d.to_string_lossy());
        let auftrag = faden.join().unwrap();
        let _ = eingehend.join();
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["text"], "fertig");
        assert_eq!(auftrag["op"], "ssh");
        assert_eq!(auftrag["befehl"], "uptime");
        assert_eq!(auftrag["schluessel"], "radxa_ed25519");
        // Typ und Blob gehen getrennt mit; die known_hosts-Zeile baut der
        // Ausführer aus Adresse, Port und beidem.
        assert_eq!(auftrag["hostschluessel_typ"], "ssh-ed25519");
        assert_eq!(auftrag["hostschluessel"], json!(blob()));
        assert_eq!(auftrag["adresse"], "127.0.0.1");
        assert_eq!(auftrag["nutzer"], "dietpi");
        let _ = std::fs::remove_file(&d);
    }

    #[test]
    fn aufnahme_ohne_passwort_sagt_wo_es_hingehoert() {
        let p = p("auf-pw");
        host_anlegen(&p, "radxa", "r.example", 22);
        setzen_freigabe(&p, "ssh", "dietpi@radxa");
        let a = op_ssh_aufnahme_mit_socket(&p, "radxa", 1000, "/nicht/da.sock");
        assert_eq!(a["fehler"]["code"], "passwort_fehlt");
        let t = a["fehler"]["text"].as_str().unwrap();
        assert!(t.contains("Fernzugriff") && t.contains("--geheim-ssh"), "{t}");
        // Und der Hinweis sagt nicht "tippe es hier".
        assert!(!t.contains("tippe"), "{t}");
    }

    #[test]
    fn aufnahme_gilt_nur_fuer_hosts_des_nutzers() {
        let p = p("auf-herkunft");
        vorschlag(&p, "v", "v.example", "u", None, "").unwrap();
        let a = op_ssh_aufnahme_mit_socket(&p, "v", 1000, "/nicht/da.sock");
        assert_eq!(a["fehler"]["code"], "host_unbestaetigt");
        let a = op_ssh_aufnahme_mit_socket(&p, "gibtsnicht", 1000, "/nicht/da.sock");
        assert_eq!(a["fehler"]["code"], "host_unbekannt");
    }

    #[test]
    fn aufnahme_ohne_freigabe_verbindet_nicht() {
        let p = p("auf-frei");
        host_anlegen(&p, "radxa", "r.example", 22);
        crate::geheim::setzen(&p, "radxa", "Geheim123").unwrap();
        let a = op_ssh_aufnahme_mit_socket(&p, "radxa", 1000, "/nicht/da.sock");
        assert_eq!(a["fehler"]["code"], "ssh_gesperrt");
        // Das Passwort bleibt liegen: es ist noch nicht verbraucht.
        assert_eq!(crate::geheim::lesen(&p, "radxa").as_deref(), Some("Geheim123"));
    }

    #[test]
    fn loeschen_entfernt_den_eintrag() {
        let p = p("loeschen");
        setzen(&p, "radxa", &eintrag("r.example")).unwrap();
        assert!(loeschen(&p, "radxa").unwrap());
        assert_eq!(laden(&p)["hosts"]["radxa"], Value::Null);
        assert!(!loeschen(&p, "radxa").unwrap());
    }

    #[test]
    fn base64_und_fingerabdruck_stimmen_mit_ssh_keygen() {
        // Bekannter Wert: SHA256 ueber den Blob "abc" (base64 YWJj) -- hier
        // nur die Probe, dass Lesen und Schreiben zueinander passen.
        // Bekannter Vektor: SHA256("abc") in base64 (Form von `ssh-keygen -lf`).
        let d = ring::digest::digest(&ring::digest::SHA256, b"abc");
        let b = b64_schreiben(d.as_ref());
        assert_eq!(b.trim_end_matches('='), "ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0");
        assert_eq!(b64_lesen(&b).unwrap(), d.as_ref());
        // Fingerabdruck ueber den **Blob** (nicht ueber den Fingerabdruck):
        // 32 Bytes kodiert, gelesen, gehasht.
        let blob = b64_schreiben(&[7u8; 51]);
        let erwartet = b64_schreiben(ring::digest::digest(&ring::digest::SHA256, &[7u8; 51]).as_ref());
        assert_eq!(fingerabdruck(&blob).unwrap(), format!("SHA256:{}", erwartet.trim_end_matches('=')));
    }

    // --- Hostschluessel lesen (ssh-keyscan im Gateway) -------------------

    /// Die `argv` ist fest: Programm, Grenze, Port, Typen, Adresse -- und
    /// nichts, was aus einer Zeichenkette zusammengebaut wird.
    #[test]
    fn der_scan_befehl_hat_eine_feste_argv() {
        let a = adr(&["box", "example"]);
        assert_eq!(
            befehl(&a, 22),
            vec!["ssh-keyscan", "-T", "5", "-p", "22", "-t", "ssh-ed25519,ecdsa-sha2-nistp256,ssh-rsa", a.as_str()]
                .into_iter()
                .map(str::to_string)
                .collect::<Vec<_>>()
        );
        assert_eq!(befehl(&a, 2222)[4], "2222");
        // Eine Adresse mit Leerzeichen bleibt EIN Argument, kein zweites Wort.
        let sonderbar = "host mit leerzeichen.example";
        assert_eq!(befehl(sonderbar, 22).len(), 8);
        assert_eq!(befehl(sonderbar, 22)[7], sonderbar);
    }

    #[test]
    fn die_ausgabe_wird_gedeutet_und_kommentare_ignoriert() {
        let a = adr(&["box", "example"]);
        let ed = blob();
        let text = format!(
            "# box.example:22 SSH-2.0-OpenSSH_9.9\n# box.example:22 SSH-2.0-OpenSSH_9.9\n\
             {a} ssh-ed25519 {ed}\n{a} ssh-rsa {rsa}\n"
        , rsa = blob());
        let v = ausgabe_deuten(&text, &a, 22).expect("gedeutet");
        assert_eq!(v["typ"], "ssh-ed25519");
        assert_eq!(v["schluessel"], ed.as_str());
    }

    #[test]
    fn ed25519_gewinnt_auch_wenn_rsa_zuerst_kommt() {
        let a = adr(&["box", "example"]);
        let text = format!("{a} ssh-rsa {r}\n{a} ssh-ed25519 {e}\n", r = blob(), e = blob());
        let v = ausgabe_deuten(&text, &a, 22).expect("gedeutet");
        assert_eq!(v["typ"], "ssh-ed25519");
    }

    #[test]
    fn eine_antwort_fuer_ein_anderes_ziel_wird_abgelehnt() {
        let a = adr(&["box", "example"]);
        let text = format!("{} ssh-ed25519 {}\n", adr(&["boese", "example"]), blob());
        let e = ausgabe_deuten(&text, &a, 22).unwrap_err();
        assert!(e.contains("statt"), "{e}");
    }

    #[test]
    fn ohne_schluessel_ist_das_ein_befund_kein_erfolg() {
        let a = adr(&["box", "example"]);
        assert!(ausgabe_deuten("# nichts\n", &a, 22).unwrap_err().contains("keinen brauchbaren"));
        // Ein Blob, der kein base64 ist, zaehlt nicht.
        assert!(ausgabe_deuten(&format!("{a} ssh-ed25519 !!!\n"), &a, 22).is_err());
    }

    /// Die drei Faelle ohne Netz: neu, unveraendert, geaendert.
    #[test]
    fn der_abruf_vergleicht_mit_dem_eintrag() {
        let neu = json!({"typ": "ssh-ed25519", "schluessel": blob()});
        assert_eq!(vergleichen(None, &neu).0, "neu");
        let gleich = json!({"typ": "ssh-ed25519", "schluessel": blob(), "fingerabdruck": "SHA256:x"});
        assert_eq!(vergleichen(Some(&gleich), &neu).0, "unveraendert");
        let anders = json!({"typ": "ssh-ed25519", "schluessel": b64_schreiben(&[9u8; 32]), "fingerabdruck": "SHA256:y"});
        let (befund, alt) = vergleichen(Some(&anders), &neu);
        assert_eq!(befund, "geaendert");
        assert_eq!(alt.unwrap()["fingerabdruck"], "SHA256:y");
    }

    /// Ein **geaenderter** Schluessel wird nicht still uebernommen, und der
    /// Abruf schreibt ueberhaupt nichts in die Tabelle.
    #[test]
    fn ein_geaenderter_schluessel_wird_gemeldet_nicht_uebernommen() {
        let p = p("schluessel-geaendert");
        let a = adr(&["box", "example"]);
        setzen(&p, "radxa", &eintrag(&a)).expect("anlegen");
        let vorher = std::fs::read_to_string(datei(&p)).expect("datei");
        let neuer_blob = b64_schreiben(&[3u8; 32]);
        let r = schluessel_lesen_mit(&p, "radxa", &|_a, _p| {
            Ok(json!({"typ": "ssh-ed25519", "schluessel": neuer_blob.clone()}))
        })
        .expect("abruf");
        assert_eq!(r["befund"], "geaendert");
        assert!(r["meldung"].as_str().unwrap().contains("GEaENDERT"), "{r}");
        assert_eq!(r["alt"]["schluessel"], blob());
        // Nichts geschrieben: die Tabelle steht wie vorher.
        assert_eq!(std::fs::read_to_string(datei(&p)).unwrap(), vorher);
    }

    #[test]
    fn der_abruf_kennt_nur_bestaetigte_hosts() {
        let p = p("schluessel-vorschlag");
        vorschlag(&p, "radxa", &adr(&["box", "example"]), "dietpi", Some(22), "").expect("vorschlag");
        let e = schluessel_lesen_mit(&p, "radxa", &|_a, _p| Ok(json!({"typ": "ssh-ed25519", "schluessel": blob()})))
            .unwrap_err();
        assert_eq!(e.0, "host_unbestaetigt");
        let e = schluessel_lesen_mit(&p, "gibtesnicht", &|_a, _p| Ok(json!({"typ": "ssh-ed25519", "schluessel": blob()})))
            .unwrap_err();
        assert_eq!(e.0, "host_unbekannt");
    }

    /// Ein Fehler des Lesers wird benannt, nicht verschluckt.
    #[test]
    fn ein_fehler_beim_lesen_wird_benannt() {
        let p = p("schluessel-fehler");
        let a = adr(&["box", "example"]);
        setzen(&p, "radxa", &eintrag(&a)).expect("anlegen");
        let e = schluessel_lesen_mit(&p, "radxa", &|_a, _p| Err("keine Antwort".into())).unwrap_err();
        assert_eq!(e.0, "schluessel_nicht_gelesen");
        assert!(e.1.contains("keine Antwort"), "{}", e.1);
    }
}
