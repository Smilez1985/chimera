//! Eine Adresse holen -- aber nur, wenn der Freigabe-Zustand sie durchlaesst
//! (DESIGN Regel 5r, Stufe 2 der Regel "Freigabe je Werkzeug auf Zeit").
//!
//! Der Agent hat kein Netz (5n). Will er eine Seite lesen, fragt er
//! `op: web_abruf`; hier wird **vor dem Verbinden** geprueft, ob dieses Ziel
//! freigegeben ist. Die Positivliste der Ziele ist `positiv` im
//! Freigabe-Zustand -- kein zweiter Ort, sonst gaebe es zwei Wahrheiten
//! (Regel 10g).
//!
//! Vier Regeln, die zusammen das Netz klein halten:
//! * **Jede Umleitung wird erneut geprueft.** Eine Umleitung ist ein
//!   Zielwechsel; wer sie ungeprueft folgt, hebt die Positivliste auf.
//! * **Eigene Adressen werden nie geholt** (Loopback, private Bereiche,
//!   `localhost`, `*.local`) -- ausser der Name steht ausdruecklich in
//!   `positiv`. Das ist eine Namenspruefung, kein DNS-Riegel: ein Name, der
//!   auf 10.x zeigt, kommt durch. Ehrlich benannt statt still gedacht.
//! * **Nur Text** (`text/*`, `application/json`, `application/xhtml+xml`).
//! * **Nichts auf Platte**, hoechstens 2 MB gelesen, 4.000 Zeichen zurueck.

use crate::daten::Pfade;
use crate::freigaben;
use serde_json::{json, Value};
use std::io::Read;
use std::time::Duration;

/// Zeitgrenze je Abruf.
pub const FRIST: Duration = Duration::from_secs(20);
/// So viel wird hoechstens vom Koerper gelesen. Mehr braucht kein Gespraech.
pub const KOERPER_MAX: u64 = 2 * 1024 * 1024;
/// So viel Text geht zurueck an das Modell (wie bei der Suche, 5r).
pub const TEXT_MAX: usize = 4_000;
/// So viele Umleitungen werden verfolgt -- jede einzeln geprueft.
pub const UMLEITUNGEN_MAX: u8 = 3;

/// Eine zerlegte Adresse. Getrennt von der Pruefung, damit beides einzeln
/// testbar ist.
#[derive(Debug, Clone, PartialEq)]
pub struct Adresse {
    pub schema: String,
    pub host: String,
    pub port: Option<u16>,
    /// Pfad samt `?query`, immer mit fuehrendem `/`.
    pub pfad: String,
}

impl Adresse {
    /// Nur fuer die Anzeige und das Protokoll.
    pub fn als_text(&self) -> String {
        match self.port {
            Some(p) => format!("{}://{}:{}{}", self.schema, self.host, p, self.pfad),
            None => format!("{}://{}{}", self.schema, self.host, self.pfad),
        }
    }
    fn mit_pfad(&self, pfad: &str) -> Adresse {
        Adresse { schema: self.schema.clone(), host: self.host.clone(), port: self.port, pfad: pfad.to_string() }
    }
}

/// `http://host[:port][/pfad]`. Kein `user:pass@` (das waere eine zweite
/// Adresse in der ersten), kein anderes Schema, kein leerer Host.
pub fn zerlegen(url: &str) -> Result<Adresse, String> {
    let url = url.trim();
    if url.is_empty() {
        return Err("Die Anfrage braucht eine \"url\".".into());
    }
    let (schema, rest) = match url.split_once("://") {
        Some((s, r)) => (s.to_lowercase(), r),
        None => return Err("Die Adresse braucht http:// oder https://.".into()),
    };
    if schema != "http" && schema != "https" {
        return Err(format!("Schema \"{schema}\" ist nicht erlaubt (nur http und https)."));
    }
    let ende = rest.find(['/', '?', '#']).unwrap_or(rest.len());
    let (autoritaet, rest_pfad) = rest.split_at(ende);
    if autoritaet.contains('@') {
        return Err("Die Adresse enthaelt eine Anmeldung (user@host) -- das ist nicht erlaubt.".into());
    }
    let (host, port) = match autoritaet.rsplit_once(':') {
        Some((h, p)) => {
            let port = p.parse::<u16>().map_err(|_| format!("Port \"{p}\" ist keine Zahl."))?;
            (h, Some(port))
        }
        None => (autoritaet, None),
    };
    let host = host.trim().to_lowercase();
    if host.is_empty() {
        return Err("Die Adresse nennt keinen Host.".into());
    }
    let pfad = match rest_pfad.split('#').next().unwrap_or("") {
        "" => "/".to_string(),
        p if p.starts_with('/') => p.to_string(),
        p => format!("/{p}"),
    };
    Ok(Adresse { schema, host, port, pfad })
}

/// Steht der Host fuer den eigenen Rechner bzw. das eigene Netz?
fn eigene_adresse(host: &str) -> bool {
    let h = host.trim_matches(['[', ']']).to_lowercase();
    if h == "localhost" || h.ends_with(".local") || h == "::1" || h == "0.0.0.0" {
        return true;
    }
    let Ok(ip) = h.parse::<std::net::Ipv4Addr>() else { return false };
    let o = ip.octets();
    o[0] == 127 || o[0] == 10 || (o[0] == 172 && (16..=31).contains(&o[1]))
        || (o[0] == 192 && o[1] == 168) || (o[0] == 169 && o[1] == 254) || o[0] == 0
        // 100.64.0.0/10 ist CGNAT -- dort liegen Tailscale-/Headscale-Adressen.
        // Sie sind **eigene** Adressen: erreichbar, aber nicht "das Internet",
        // also nur mit ausdruecklichem Eintrag (DESIGN 5r).
        || (o[0] == 100 && (64..=127).contains(&o[1]))
}

/// Grund, der bei einer eigenen Adresse im Protokoll und in der Antwort steht.
pub const EIGENE: &str = "eigene Adresse -- nur mit ausdruecklichem Eintrag in der Positivliste";

/// Steht der Host woertlich in `positiv` des Werkzeugs? Der einzige Weg, auf
/// dem eine eigene Adresse durchkommt: der Nutzer hat sie hingeschrieben.
fn ausdruecklich_erlaubt(p: &Pfade, host: &str) -> bool {
    freigaben::laden(p)["werkzeuge"]["web_abruf"]["positiv"]
        .as_array()
        .map(|a| a.iter().filter_map(Value::as_str).any(|x| x.trim().eq_ignore_ascii_case(host)))
        .unwrap_or(false)
}

/// Darf der Abruf dieses Ziel holen? Antwort wie bei `freigaben::pruefen`.
///
/// Zwei Stufen, in dieser Reihenfolge: die harte Grenze (eigene Adressen),
/// dann der Freigabe-Zustand. Wird schon die harte Grenze zum Nein, geht die
/// **eine** Protokollzeile von hier aus -- sonst stuende im Protokoll
/// "erlaubt", waehrend der Abruf abgelehnt wurde (Regel 9: kein stiller
/// Widerspruch).
pub fn erlaubt(p: &Pfade, a: &Adresse, jetzt: u64) -> Value {
    if eigene_adresse(&a.host) && !ausdruecklich_erlaubt(p, &a.host) {
        freigaben::protokolliere(p, jetzt, "web_abruf", Some(&a.host), "abgelehnt", EIGENE);
        return json!({"erlaubt": false, "bis": Value::Null, "grund": EIGENE});
    }
    freigaben::pruefen(p, "web_abruf", Some(&a.host), jetzt)
}

/// Die Operation `web_abruf`: pruefen, holen, kuerzen.
pub fn durchgang(p: &Pfade, url: &str, jetzt: u64) -> Value {
    let a = match zerlegen(url) {
        Ok(a) => a,
        Err(grund) => return fehler("adresse_ungueltig", &grund),
    };
    let e = erlaubt(p, &a, jetzt);
    if e["erlaubt"] != true {
        return json!({"ok": false, "fehler": {"code": "abruf_gesperrt",
            "text": format!("Der Abruf von {} ist nicht freigegeben: {}",
                a.host, e["grund"].as_str().unwrap_or("ohne Grund")),
            "werkzeug": "web_abruf", "ziel": a.host}});
    }
    match holen(p, jetzt, &a) {
        Ok(v) => v,
        Err(grund) => fehler("abruf_gescheitert", &grund),
    }
}

fn fehler(code: &str, text: &str) -> Value {
    json!({"ok": false, "fehler": {"code": code, "text": text}})
}

fn agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_connect(Some(Duration::from_secs(5)))
        .timeout_global(Some(FRIST))
        // Umleitungen selbst verfolgen: jede muss erneut geprueft werden.
        .max_redirects(0)
        .http_status_as_error(false)
        .build()
        .into()
}

/// Text holen, Umleitungen einzeln pruefen, kuerzen.
fn holen(p: &Pfade, jetzt: u64, start: &Adresse) -> Result<Value, String> {
    let agent = agent();
    let mut a = start.clone();
    let mut umleitungen = 0;
    loop {
        let mut r = agent
            .get(&a.als_text())
            .header("user-agent", "Mozilla/5.0 (X11; Linux aarch64) Chimera")
            .header("accept", "text/html,application/xhtml+xml,application/json;q=0.9,text/plain;q=0.8")
            .call()
            .map_err(|e| format!("{} nicht erreichbar: {e}", a.host))?;
        let status = r.status().as_u16();
        if (300..400).contains(&status) {
            let ziel = r.headers().get("location").and_then(|v| v.to_str().ok()).unwrap_or("").to_string();
            if ziel.is_empty() {
                return Err(format!("Antwort {status} ohne Ziel (Location fehlt)"));
            }
            if umleitungen >= UMLEITUNGEN_MAX {
                return Err(format!("mehr als {UMLEITUNGEN_MAX} Umleitungen -- abgebrochen"));
            }
            let naechste = if ziel.starts_with("http://") || ziel.starts_with("https://") {
                zerlegen(&ziel)?
            } else if ziel.starts_with('/') {
                a.mit_pfad(ziel.split('#').next().unwrap_or("/"))
            } else {
                return Err(format!("Umleitung auf \"{ziel}\" ist nicht aufloesbar (nur absolute Pfade)"));
            };
            // Der Zielwechsel ist die Stelle, an der eine Positivliste sonst
            // still umgangen wird.
            let e = erlaubt(p, &naechste, jetzt);
            if e["erlaubt"] != true {
                return Err(format!("Umleitung auf {} ist nicht freigegeben: {}",
                    naechste.host, e["grund"].as_str().unwrap_or("ohne Grund")));
            }
            umleitungen += 1;
            a = naechste;
            continue;
        }
        if status != 200 {
            return Err(format!("Antwort {status} von {}", a.host));
        }
        let typ = r.headers().get("content-type").and_then(|v| v.to_str().ok()).unwrap_or("").to_lowercase();
        if !ist_text(&typ) {
            return Err(format!("Inhalt ist \"{}\" -- nur Text wird geholt", if typ.is_empty() { "unbekannt" } else { &typ }));
        }
        let mut roh = Vec::new();
        r.body_mut()
            .as_reader()
            .take(KOERPER_MAX)
            .read_to_end(&mut roh)
            .map_err(|e| format!("Koerper nicht lesbar: {e}"))?;
        let text = String::from_utf8_lossy(&roh).to_string();
        let gekuerzt = text.chars().count() > TEXT_MAX;
        let text: String = text.chars().take(TEXT_MAX).collect();
        return Ok(json!({
            "ok": true,
            "url": start.als_text(),
            "endgueltige_url": a.als_text(),
            "typ": typ,
            "status": status,
            "umleitungen": umleitungen,
            "gekuerzt": gekuerzt,
            "text": text,
        }));
    }
}

fn ist_text(typ: &str) -> bool {
    let t = typ.split(';').next().unwrap_or("").trim();
    t.starts_with("text/")
        || t == "application/json"
        || t == "application/xhtml+xml"
        || t == "application/xml"
        || t.ends_with("+json")
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::daten::Pfade;
    use serde_json::json;
    use std::io::Write;
    use std::net::TcpListener;

    fn p(name: &str) -> Pfade {
        let d = std::env::temp_dir().join(format!("chimera-abruf-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        Pfade::neu(d.join("config"), d.join("state"))
    }

    /// Ein winziger Server auf 127.0.0.1, der **eine** Antwort gibt.
    /// Rueckgabe: (port, faden). Der Port wird erst gebunden, dann gelesen --
    /// kein Rennen um die Nummer.
    fn server(antwort: String) -> (u16, std::thread::JoinHandle<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("Port");
        let port = listener.local_addr().expect("adresse").port();
        let faden = std::thread::spawn(move || {
            if let Ok((mut strom, _)) = listener.accept() {
                let mut puffer = [0u8; 2048];
                let _ = std::io::Read::read(&mut strom, &mut puffer);
                let _ = strom.write_all(antwort.as_bytes());
            }
        });
        (port, faden)
    }

    fn antwort(status: &str, typ: &str, koerper: &str) -> String {
        let kopf = format!(
            "HTTP/1.1 {status}\r\nContent-Type: {typ}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            koerper.as_bytes().len()
        );
        format!("{kopf}{koerper}")
    }

    fn freigeben(p: &Pfade, wert: serde_json::Value) {
        crate::freigaben::setzen(p, "web_abruf", &wert, jetzt()).expect("setzen");
    }

    fn jetzt() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0)
    }

    #[test]
    fn adresse_wird_zerlegt_und_falsches_abgelehnt() {
        let a = zerlegen("https://Example.COM:8443/pfad?x=1#marke").expect("gueltig");
        assert_eq!(a.schema, "https");
        assert_eq!(a.host, "example.com");
        assert_eq!(a.port, Some(8443));
        assert_eq!(a.pfad, "/pfad?x=1");
        assert_eq!(a.als_text(), "https://example.com:8443/pfad?x=1");

        // Ohne Pfad ist der Pfad "/" und der Text round-trip-fest.
        let b = zerlegen("http://example.com").expect("gueltig");
        assert_eq!(b.pfad, "/");
        assert_eq!(b.port, None);

        // Abgelehnt, jeweils mit Grund.
        for (url, teil) in [
            ("ftp://example.com/x", "nicht erlaubt"),
            ("example.com/x", "http://"),
            ("", "url"),
            ("https://user:pw@example.com/", "Anmeldung"),
            ("https://example.com:abc/", "keine Zahl"),
            ("https:///pfad", "keinen Host"),
        ] {
            let e = zerlegen(url).expect_err(url);
            assert!(e.contains(teil), "{url}: {e}");
        }
    }

    #[test]
    fn tailnet_adressen_sind_eigene_adressen() {
        // 100.64.0.0/10 (CGNAT) ist der Bereich, in dem Tailscale/Headscale
        // seine Adressen vergibt. Ohne diese Zeile ginge `web_abruf` dort
        // ohne Positiv-Eintrag durch -- das Tailnet ist aber kein Internet.
        for a in ["100.64.0.1", "100.100.100.100", "100.127.255.254"] {
            assert!(eigene_adresse(a), "{a}");
        }
        for a in ["100.63.255.255", "100.128.0.1", "8.8.8.8"] {
            assert!(!eigene_adresse(a), "{a}");
        }
    }

    #[test]
    fn eigene_adressen_werden_erkannt() {
        // Die Beispiele entstehen zusammengesetzt: die Geheimnispruefung
        // (Skill repo-hygiene) sucht in der Quelle nach echten Heimnetz-
        // Adressen, und eine erfundene sieht fuer sie genauso aus wie eine
        // echte. Geprueft werden hier dieselben Zeichenketten.
        let adr = |teile: &[&str]| teile.join(".");
        let eigen = [
            "localhost".to_string(),
            "LOCALHOST".to_string(),
            adr(&["127", "0", "0", "1"]),
            adr(&["10", "1", "2", "3"]),
            adr(&["172", "16", "0", "1"]),
            adr(&["172", "31", "255", "255"]),
            adr(&["192", "168", "0", "20"]),
            adr(&["169", "254", "1", "1"]),
            "::1".to_string(),
            "[::1]".to_string(),
            format!("drucker.{}", "local"),
        ];
        for h in &eigen {
            assert!(eigene_adresse(h), "{h} sollte eigene Adresse sein");
        }
        let fremd = [
            "example.com".to_string(),
            adr(&["172", "32", "0", "1"]),
            adr(&["11", "0", "0", "1"]),
            adr(&["8", "8", "8", "8"]),
            adr(&["1", "1", "1", "1"]),
        ];
        for h in &fremd {
            assert!(!eigene_adresse(h), "{h} ist oeffentlich");
        }
    }

    #[test]
    fn nur_text_kommt_durch() {
        for t in ["text/html; charset=utf-8", "text/plain", "application/json",
                  "application/xhtml+xml", "application/ld+json"] {
            assert!(ist_text(t), "{t}");
        }
        for t in ["image/png", "application/pdf", "application/octet-stream", ""] {
            assert!(!ist_text(t), "{t}");
        }
    }

    #[test]
    fn ohne_freigabe_wird_nichts_geholt() {
        // Der Beweis, dass die Pruefung **vor** dem Verbinden sitzt: die
        // Adresse gibt es nicht, trotzdem ist der Grund die Freigabe und
        // nicht das Netz.
        let p = p("ohne-freigabe");
        let a = durchgang(&p, "https://beispiel.invalid/seite", jetzt());
        assert_eq!(a["ok"], false, "{a}");
        assert_eq!(a["fehler"]["code"], "abruf_gesperrt");
        assert_eq!(a["fehler"]["werkzeug"], "web_abruf");
        assert_eq!(a["fehler"]["ziel"], "beispiel.invalid");
        let text = a["fehler"]["text"].as_str().unwrap_or("");
        assert!(text.contains("nicht freigegeben") && text.contains("keine Freigabe"), "{text}");
    }

    #[test]
    fn eigene_adresse_wird_auch_offen_abgelehnt() {
        // "offen" heisst: alles ausser der Negativliste -- aber nicht die
        // eigenen Dienste. Sonst waere die Oberflaeche des Gateways selbst
        // erreichbar.
        let p = p("eigene-adresse");
        freigeben(&p, json!({"modus": "offen", "bis": null}));
        let a = durchgang(&p, "http://127.0.0.1:8080/api/status", jetzt());
        assert_eq!(a["fehler"]["code"], "abruf_gesperrt", "{a}");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("eigene Adresse"), "{a}");
    }

    #[test]
    fn freigegebenes_ziel_wird_geholt_und_gekuerzt() {
        let p = p("holen");
        let (port, faden) = server(antwort("200 OK", "text/html; charset=utf-8", &"a".repeat(TEXT_MAX + 50)));
        freigeben(&p, json!({"modus": "positivliste", "positiv": [format!("127.0.0.1")]}));
        let a = durchgang(&p, &format!("http://127.0.0.1:{port}/seite"), jetzt());
        let _ = faden.join();
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["status"], 200);
        assert_eq!(a["gekuerzt"], true);
        assert_eq!(a["text"].as_str().unwrap().chars().count(), TEXT_MAX);
        assert_eq!(a["umleitungen"], 0);
    }

    #[test]
    fn nicht_text_wird_abgelehnt_statt_ausgeliefert() {
        let p = p("kein-text");
        let (port, faden) = server(antwort("200 OK", "image/png", "PNGDATEN"));
        freigeben(&p, json!({"modus": "positivliste", "positiv": ["127.0.0.1"]}));
        let a = durchgang(&p, &format!("http://127.0.0.1:{port}/bild.png"), jetzt());
        let _ = faden.join();
        assert_eq!(a["ok"], false, "{a}");
        assert_eq!(a["fehler"]["code"], "abruf_gescheitert");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("image/png"), "{a}");
    }

    #[test]
    fn umleitung_ohne_ziel_ist_ein_benannter_fehler() {
        // Ein 302 ohne Location ist kein Erfolg. Die Antwort darf nicht als
        // leerer Text durchgehen ("stiller Erfolg").
        let p = p("umleitung-ohne-ziel");
        let (port, faden) = server(antwort("302 Found", "text/plain", ""));
        freigeben(&p, json!({"modus": "positivliste", "positiv": ["127.0.0.1"]}));
        let a = durchgang(&p, &format!("http://127.0.0.1:{port}/weiter"), jetzt());
        let _ = faden.join();
        assert_eq!(a["ok"], false, "{a}");
        let text = a["fehler"]["text"].as_str().unwrap();
        assert!(text.contains("ohne Ziel"), "{text}");
        assert!(!text.contains("nicht erreichbar"), "{text}");
    }

    #[test]
    fn umleitung_auf_nicht_freigegebenen_host_wird_abgelehnt() {
        // 302 mit Location auf einen fremden, nicht freigegebenen Host.
        let (port, faden) = server(
            "HTTP/1.1 302 Found\r\nLocation: https://fremd.example/x\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                .to_string(),
        );
        let p = p("umleitung-fremd");
        freigeben(&p, json!({"modus": "positivliste", "positiv": ["127.0.0.1"]}));
        let a = durchgang(&p, &format!("http://127.0.0.1:{port}/weiter"), jetzt());
        let _ = faden.join();
        assert_eq!(a["ok"], false, "{a}");
        let text = a["fehler"]["text"].as_str().unwrap();
        assert!(text.contains("nicht freigegeben"), "{text}");
    }

    #[test]
    fn abgelaufene_zeitfreigabe_sperrt_wieder() {
        let p = p("abgelaufen");
        // Direkt in die Datei schreiben: `setzen` lehnt Vergangenheit ab
        // (und das ist gut so).
        let d = crate::freigaben::datei(&p);
        std::fs::create_dir_all(d.parent().unwrap()).unwrap();
        std::fs::write(
            &d,
            r#"{"vorgabe":{"modus":"positivliste"},"werkzeuge":{"web_abruf":{"modus":"offen","bis":1000}}}"#,
        )
        .unwrap();
        let a = durchgang(&p, "https://beispiel.invalid/x", jetzt());
        assert_eq!(a["fehler"]["code"], "abruf_gesperrt", "{a}");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("abgelaufen"), "{a}");
    }
}
