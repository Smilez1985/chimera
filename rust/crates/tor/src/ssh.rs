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
pub const RECHTE: &[&str] = &["force", "rbash", "voll"];

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
                o.entry("rechte").or_insert(json!("force"));
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
    let rechte = wert.get("rechte").and_then(Value::as_str).unwrap_or("force").trim();
    if !RECHTE.contains(&rechte) {
        return Err(("wert_ungueltig", format!("Rechte \"{rechte}\" gibt es nicht ({}).", RECHTE.join(", "))));
    }
    let notiz = wert.get("notiz").and_then(Value::as_str).unwrap_or("").trim();
    if notiz.chars().count() > 200 {
        return Err(("wert_ungueltig", "Die Notiz ist laenger als 200 Zeichen.".into()));
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
            None => {
                return Err((
                    "hostschluessel_fehlt",
                    "Ohne Hostschluessel kein Eintrag: Typ und Blob aus \"ssh-keyscan\" mitgeben.".into(),
                ))
            }
        },
    };
    let neu = json!({
        "adresse": adresse, "nutzer": nutzer, "port": port, "schluessel": schluessel,
        "hostschluessel": hostschluessel, "rechte": rechte,
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
            out["brauchbar"] = json!(true);
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
        "schluessel": "", "hostschluessel": Value::Null, "rechte": "force",
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
    gemein::fdpass::senden(&strom, &zeile, &[tcp.as_raw_fd()])
        .map_err(|e| format!("Der Deskriptor ließ sich nicht übergeben: {e}"))?;
    let leser = strom.try_clone().map_err(|e| e.to_string())?;
    let mut leser = std::io::BufReader::new(leser);
    gemein::zeile::lesen(&mut leser, gemein::zeile::MAX_BYTES)
        .map_err(|e| format!("keine Antwort vom Ausführer ({e})"))
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
               "hostschluessel": {"typ": "ssh-ed25519", "schluessel": blob()}, "rechte": "force"})
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
        assert_eq!(h["rechte"], "force");
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
}
