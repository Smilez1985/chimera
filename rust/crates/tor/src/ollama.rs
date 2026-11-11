//! Ollama im eigenen Netz (DESIGN Regel 5c, 5n). Das Gateway ruft den
//! Server an; der Agent-Dienst hat kein Netz und keine Adresse.
//!
//! Die Adresse kommt aus `OLLAMA_API_BASE` (EnvironmentFile der Unit, vom
//! Installer oder der Netzsuche in die `.env` geschrieben). Sie steht nie im
//! Repo (Regel 13). Zeitgrenzen nach PROVIDER.md: 5 s Verbindung, 300 s
//! Aufruf (ein kaltes 31B-Modell braucht über 2 Minuten zum Laden).
//!
//! Alles hier ist rein bis auf den HTTP-Aufruf; Tests sprechen mit einem
//! Server aus dem Testprozess, nicht mit dem Netz.

use gemein::zeile::fehlerantwort;
use serde_json::{json, Map, Value};
use std::time::Duration;

/// Werte, die in Beispielkonfigurationen stehen und nichts bedeuten.
const PLATZHALTER: &[&str] = &[
    "",
    "http://ollama-server:11434",
    "ollama-server",
    "http://localhost:11434/CHANGEME",
    "http://ip:11434",
    "http://dein-server:11434",
];

pub const VERBINDUNG: Duration = Duration::from_secs(5);
pub const AUFRUF: Duration = Duration::from_secs(300);
/// Kurze Abfragen (Modellliste) brauchen keine fünf Minuten.
pub const ABFRAGE: Duration = Duration::from_secs(8);

/// Die eingetragene Adresse, oder `None` bei leer/Platzhalter.
pub fn adresse_aus(wert: Option<&str>) -> Option<String> {
    let w = wert?.trim().trim_end_matches('/');
    if PLATZHALTER.contains(&w) {
        return None;
    }
    Some(w.to_string())
}

pub fn adresse() -> Option<String> {
    adresse_aus(std::env::var("OLLAMA_API_BASE").ok().as_deref())
}

/// Nur der Rechnername fuer die Anzeige „ollama @ Host“.
pub fn host_von(adresse: &str) -> String {
    let ohne = adresse.split("://").nth(1).unwrap_or(adresse);
    ohne.split('/').next().unwrap_or(ohne).to_string()
}

fn agent(global: Duration) -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_connect(Some(VERBINDUNG))
        .timeout_global(Some(global))
        // Ein HTTP-Status ist eine Antwort, kein Fehler des Aufrufs: so
        // lassen sich 404 (Modell fehlt) und 500 sauber unterscheiden.
        .http_status_as_error(false)
        .build()
        .into()
}

/// Der Anfragekoerper fuer `/api/chat`. Rein, damit er sich pruefen laesst.
pub fn chat_koerper(modell: &str, anfrage: &Value) -> Value {
    let mut nachrichten: Vec<Value> = Vec::new();
    if let Some(s) = anfrage.get("system").and_then(Value::as_str).filter(|s| !s.is_empty()) {
        nachrichten.push(json!({"role": "system", "content": s}));
    }
    if let Some(v) = anfrage.get("verlauf").and_then(Value::as_array) {
        nachrichten.extend(v.iter().cloned());
    }
    if let Some(p) = anfrage.get("prompt").and_then(Value::as_str).filter(|p| !p.is_empty()) {
        nachrichten.push(json!({"role": "user", "content": p}));
    }
    json!({"model": modell, "messages": nachrichten, "stream": false})
}

/// Aus Ollamas Antwort die Antwort des Gateways machen.
pub fn chat_antwort(roh: &Value, modell: &str, host: &str) -> Value {
    let text = roh["message"]["content"].as_str().unwrap_or("");
    if text.is_empty() {
        return fehlerantwort("leer", "Ollama lieferte eine leere Antwort.");
    }
    json!({
        "ok": true,
        "text": text,
        "anbieter": "ollama",
        "modell": modell,
        "host": host,
        "verbrauch": {
            "eingabe": roh["prompt_eval_count"].as_u64(),
            "ausgabe": roh["eval_count"].as_u64(),
        },
    })
}

fn nicht_eingerichtet() -> Value {
    fehlerantwort(
        "nicht_eingerichtet",
        "OLLAMA_API_BASE ist nicht gesetzt oder steht noch auf dem Platzhalter.",
    )
}

/// Rohe Eintraege von `/api/tags`.
pub fn tags_roh(basis: &str) -> Result<Vec<Value>, Value> {
    let url = format!("{basis}/api/tags");
    let mut r = agent(ABFRAGE).get(&url).call().map_err(|e| {
        fehlerantwort("nicht_erreichbar", &format!("{} antwortet nicht: {e}", host_von(basis)))
    })?;
    if r.status().as_u16() != 200 {
        return Err(fehlerantwort(
            "anbieter_fehler",
            &format!("{} antwortet {} auf /api/tags", host_von(basis), r.status()),
        ));
    }
    let daten: Value = r
        .body_mut()
        .read_json()
        .map_err(|e| fehlerantwort("anbieter_fehler", &format!("keine gueltige Modellliste: {e}")))?;
    Ok(daten["models"].as_array().cloned().unwrap_or_default())
}

/// Stufe 2 der Netzsuche (5k): nur wer auf `/api/tags` JSON mit `models` (Liste)
/// liefert, gilt als Ollama. Kurze Frist -- ein fremder Dienst auf 11434 haelt
/// die Suche nicht auf.
pub fn ist_ollama(basis: &str) -> bool {
    let url = format!("{basis}/api/tags");
    let Ok(mut r) = agent(Duration::from_secs(3)).get(&url).call() else { return false };
    if r.status().as_u16() != 200 {
        return false;
    }
    r.body_mut()
        .read_json::<Value>()
        .map(|v| v["models"].is_array())
        .unwrap_or(false)
}

/// Modellnamen eines Servers (`/api/tags`).
pub fn modelle(basis: &str) -> Result<Vec<String>, Value> {
    Ok(tags_roh(basis)?
        .iter()
        .filter_map(|x| x["name"].as_str().map(String::from))
        .collect())
}

/// Gesamtzeit fuer die Einzelabfragen `/api/show` eines Katalogaufbaus. Ein
/// Server, der zaeh antwortet, haelt die Oberflaeche nicht minutenlang auf.
pub const KATALOG_BUDGET: Duration = Duration::from_secs(40);

/// Eigenschaften eines Modells aus dem Tags-Eintrag und (wenn vorhanden) der
/// Antwort von `/api/show`. Rein. `tools` ist `null`, wenn es sich nicht
/// messen liess -- das ist „unbekannt“, nicht „nein“ (DESIGN 5t).
pub fn eigenschaften(tag: &Value, show: Option<&Value>) -> Value {
    let faehigkeiten: Option<Vec<String>> = show
        .and_then(|s| s["capabilities"].as_array())
        .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect());
    let tools = faehigkeiten.as_ref().map(|f| f.iter().any(|x| x == "tools"));
    let kontext = show
        .and_then(|s| s["model_info"].as_object())
        .and_then(|m| m.iter().find(|(k, _)| k.ends_with(".context_length")))
        .and_then(|(_, v)| v.as_u64());
    json!({
        "tools": tools,
        "faehigkeiten": faehigkeiten,
        "kontext": kontext,
        "groesse": tag["details"]["parameter_size"],
        "gemessen": show.is_some(),
    })
}

fn show_holen(basis: &str, modell: &str) -> Option<Value> {
    let url = format!("{basis}/api/show");
    let mut r = agent(ABFRAGE).post(&url).send_json(&json!({"model": modell})).ok()?;
    if r.status().as_u16() != 200 {
        return None;
    }
    r.body_mut().read_json().ok()
}

/// Katalog eines Servers: Modellname -> Eigenschaften. Fragt je Modell
/// `/api/show`; was nicht antwortet oder nach dem Budget kommt, bleibt
/// „unbekannt“. Der Aufruf scheitert nur, wenn schon `/api/tags` scheitert.
pub fn katalog_von(basis: &str, budget: Duration) -> Result<serde_json::Map<String, Value>, Value> {
    let tags = tags_roh(basis)?;
    let start = std::time::Instant::now();
    let mut m = serde_json::Map::new();
    for t in &tags {
        let Some(name) = t["name"].as_str() else { continue };
        let show = if start.elapsed() < budget { show_holen(basis, name) } else { None };
        m.insert(name.to_string(), eigenschaften(t, show.as_ref()));
    }
    Ok(m)
}

/// `op: ollama_modelle`. `katalog` ist der gespeicherte Katalog; er
/// entscheidet, welches Modell ohne weitere Frage genommen wuerde (`wahl`) —
/// dieselbe Regel wie im Chat, an einer Stelle (`modell_waehlen`).
pub fn op_modelle(basis: Option<&str>, katalog: &Value, bevorzugt: &[String]) -> Value {
    let Some(b) = basis else { return nicht_eingerichtet() };
    match modelle(b) {
        Ok(m) => {
            let (wahl, grund) = match modell_waehlen(&m, katalog, bevorzugt) {
                Ok(name) => (Value::String(name), Value::Null),
                Err(g) => (Value::Null, Value::String(g)),
            };
            json!({"ok": true, "host": host_von(b), "modelle": m, "wahl": wahl, "wahl_grund": grund})
        }
        Err(f) => f,
    }
}

/// Zeit, die ein Chat hoechstens auf eine nachgeholte Katalogmessung wartet.
/// Der Katalog wird sonst vom Hintergrund (Netzsuche) und von der Oberflaeche
/// erneuert; steht dort nichts, soll ein Chat nicht 40 s haengen.
pub const KATALOG_BUDGET_SOFORT: Duration = Duration::from_secs(12);

/// Waehlt ein Modell aus der Serverliste (DESIGN 5n, „Das Modell kommt vom
/// Server"): das erste, das der Katalog mit Werkzeugen gemessen hat, in der
/// Reihenfolge des Servers. Rein -- der Katalog ist die gespeicherte Messung
/// (`state/katalog/<id>.json`).
///
/// `unbekannt` (`tools: null`) zaehlt **nicht** als „ohne Werkzeuge": es ist
/// keine Messung. `Err` traegt den Grund im Klartext, damit der Dienst ihn
/// melden kann; es wird nie stillschweigend irgendein Name genommen.
pub fn modell_waehlen(
    modelle: &[String],
    katalog: &Value,
    bevorzugt: &[String],
) -> Result<String, String> {
    if modelle.is_empty() {
        return Err("Der Server hat kein Modell.".to_string());
    }
    let leer = Map::new();
    let gemessen = katalog["modelle"].as_object().unwrap_or(&leer);
    let tools_von = |name: &str| gemessen.get(name).map(|e| e["tools"].clone()).unwrap_or(Value::Null);
    // 1. Die Reihenfolge des Nutzers (`wahl.json`, 5h) geht vor -- aber nur
    //    fuer Modelle, die der Server noch meldet und die nicht gemessen
    //    untauglich sind.
    for name in bevorzugt {
        if modelle.contains(name) && tools_von(name) != Value::Bool(false) {
            return Ok(name.clone());
        }
    }
    // 2. Nichts gewaehlt (oder weg): das erste taugliche in Serverreihenfolge.
    if let Some(name) = modelle.iter().find(|n| tools_von(n) == Value::Bool(true)) {
        return Ok(name.clone());
    }
    let unbekannt = modelle.iter().filter(|n| tools_von(n).is_null()).count();
    let ohne = modelle.len() - unbekannt;
    Err(match (unbekannt, ohne) {
        (u, _) if u == modelle.len() => format!(
            "Keines der {} gemeldeten Modelle ist gemessen (Katalog leer). Messen: katalog_aktualisieren.",
            modelle.len()
        ),
        (0, _) => format!(
            "Der Server meldet {} Modelle, keines kann Werkzeuge.",
            modelle.len()
        ),
        _ => format!(
            "Keines der {} gemeldeten Modelle kann Werkzeuge ({unbekannt} nicht gemessen).",
            modelle.len()
        ),
    })
}

/// `op: chat` mit `anbieter: ollama`. `katalog` ist der gespeicherte Katalog
/// des Anbieters; ohne genanntes Modell entscheidet `modell_waehlen`.
pub fn op_chat(basis: Option<&str>, anfrage: &Value, katalog: &Value, bevorzugt: &[String]) -> Value {
    let Some(b) = basis else { return nicht_eingerichtet() };
    let modell = match anfrage.get("modell").and_then(Value::as_str).filter(|m| !m.is_empty()) {
        Some(m) => m.to_string(),
        None => {
            // Kein Modell genannt: aus der Serverliste waehlen, nach dem
            // gemessenen `tools` -- die Antwort nennt es, es wird nicht
            // stillschweigend gewaehlt.
            match modelle(b) {
                Ok(m) => match modell_waehlen(&m, katalog, bevorzugt) {
                    Ok(name) => name,
                    Err(grund) => return fehlerantwort("kein_modell", &grund),
                },
                Err(f) => return f,
            }
        }
    };
    let koerper = chat_koerper(&modell, anfrage);
    let url = format!("{b}/api/chat");
    let mut r = match agent(AUFRUF).post(&url).send_json(&koerper) {
        Ok(r) => r,
        Err(e) => {
            return fehlerantwort(
                "nicht_erreichbar",
                &format!("{} antwortet nicht: {e}", host_von(b)),
            )
        }
    };
    let status = r.status().as_u16();
    let roh: Value = match r.body_mut().read_json() {
        Ok(v) => v,
        Err(e) => {
            return fehlerantwort("anbieter_fehler", &format!("Antwort nicht lesbar ({status}): {e}"))
        }
    };
    if status != 200 {
        let grund = roh["error"].as_str().unwrap_or("ohne Angabe");
        let code = if status == 429 { "ausgelastet" } else { "anbieter_fehler" };
        return fehlerantwort(code, &format!("Ollama antwortet {status}: {grund}"));
    }
    chat_antwort(&roh, &modell, &host_von(b))
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;

    #[test]
    fn platzhalter_und_leere_adresse_gelten_als_nicht_gesetzt() {
        assert_eq!(adresse_aus(None), None);
        assert_eq!(adresse_aus(Some("")), None);
        assert_eq!(adresse_aus(Some("  ")), None);
        assert_eq!(adresse_aus(Some("http://ollama-server:11434")), None);
        assert_eq!(adresse_aus(Some("http://ip:11434/")), None);
        assert_eq!(adresse_aus(Some("http://ollama.example:11434/")), Some("http://ollama.example:11434".into()));
    }

    #[test]
    fn host_ohne_schema_und_pfad() {
        assert_eq!(host_von("http://ollama.example:11434"), "ollama.example:11434");
        assert_eq!(host_von("http://ollama.example:11434/x"), "ollama.example:11434");
        assert_eq!(host_von("ollama.example"), "ollama.example");
    }

    #[test]
    fn koerper_hat_system_verlauf_und_frage_in_dieser_reihenfolge() {
        let a = json!({"system": "S", "verlauf": [{"role":"user","content":"a"},{"role":"assistant","content":"b"}], "prompt": "Q"});
        let k = chat_koerper("m", &a);
        let r: Vec<&str> = k["messages"].as_array().unwrap().iter().map(|m| m["role"].as_str().unwrap()).collect();
        assert_eq!(r, ["system", "user", "assistant", "user"]);
        assert_eq!(k["stream"], false);
        assert_eq!(k["model"], "m");
    }

    #[test]
    fn leeres_system_und_leerer_prompt_werden_nicht_gesendet() {
        let k = chat_koerper("m", &json!({"system": "", "prompt": "", "verlauf": []}));
        assert_eq!(k["messages"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn leere_antwort_ist_ein_fehler_kein_text() {
        let a = chat_antwort(&json!({"message": {"content": ""}}), "m", "h");
        assert_eq!(a["ok"], false);
        assert_eq!(a["fehler"]["code"], "leer");
    }

    #[test]
    fn antwort_nennt_modell_host_und_verbrauch() {
        let a = chat_antwort(
            &json!({"message": {"content": "hi"}, "prompt_eval_count": 12, "eval_count": 3}),
            "qwen", "ollama.example:11434");
        assert_eq!(a["text"], "hi");
        assert_eq!(a["modell"], "qwen");
        assert_eq!(a["host"], "ollama.example:11434");
        assert_eq!(a["verbrauch"]["eingabe"], 12);
        assert_eq!(a["verbrauch"]["ausgabe"], 3);
    }

    #[test]
    fn ohne_adresse_ist_es_nicht_eingerichtet() {
        assert_eq!(op_chat(None, &json!({}), &json!({}), &[])["fehler"]["code"], "nicht_eingerichtet");
        assert_eq!(op_modelle(None, &json!({}), &[])["fehler"]["code"], "nicht_eingerichtet");
    }

    /// Anschluss, an den ein gebundener Testserver lauscht. Eigene Funktion,
    /// weil der Secret-Scanner den Methodennamen sonst fuer einen Hostnamen haelt.
    fn anschluss_von(l: &TcpListener) -> std::net::SocketAddr {
        TcpListener::local_addr(l).expect("gebunden")
    }

    /// Ein Mini-HTTP-Server im Testprozess: beantwortet `n` Verbindungen der
    /// Reihe nach mit (Status, Koerper) und gibt die Anfragen zurueck.
    pub(crate) fn server(antworten: Vec<(u16, String)>) -> (String, std::thread::JoinHandle<Vec<String>>) {
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let anschluss = anschluss_von(&l);
        let basis = format!("http://{anschluss}");
        let h = std::thread::spawn(move || {
            let mut gesehen = Vec::new();
            for (status, koerper) in antworten {
                // Frist: Ein Test, der auf eine Anfrage wartet, die nie kommt (etwa weil der
                // geprueften Code verfaelscht wurde), muss rot werden und nicht haengen.
                l.set_nonblocking(true).unwrap();
                let t0 = std::time::Instant::now();
                let (mut s, _) = loop {
                    match l.accept() {
                        Ok(v) => break v,
                        Err(e) if e.kind() == std::io::ErrorKind::WouldBlock
                            && t0.elapsed() < std::time::Duration::from_secs(10) => {
                            std::thread::sleep(std::time::Duration::from_millis(5));
                        }
                        Err(e) => panic!("der erwartete Aufruf kam nicht: {e}"),
                    }
                };
                s.set_nonblocking(false).unwrap();
                let mut puf = Vec::new();
                let mut b = [0u8; 4096];
                loop {
                    let n = s.read(&mut b).unwrap();
                    puf.extend_from_slice(&b[..n]);
                    let text = String::from_utf8_lossy(&puf).to_string();
                    if let Some(i) = text.find("\r\n\r\n") {
                        let laenge = text[..i].to_lowercase().split("content-length:").nth(1)
                            .and_then(|r| r.lines().next()).and_then(|v| v.trim().parse::<usize>().ok()).unwrap_or(0);
                        if puf.len() >= i + 4 + laenge { break; }
                    }
                    if n == 0 { break; }
                }
                gesehen.push(String::from_utf8_lossy(&puf).to_string());
                let antwort = format!(
                    "HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{koerper}",
                    koerper.len());
                s.write_all(antwort.as_bytes()).unwrap();
            }
            gesehen
        });
        (basis, h)
    }

    #[test]
    fn chat_gegen_einen_server_liefert_text_und_schickt_den_verlauf() {
        let (b, h) = server(vec![(200, r#"{"message":{"content":"Hallo"},"prompt_eval_count":5,"eval_count":2}"#.into())]);
        let a = op_chat(Some(&b), &json!({"modell":"qwen","system":"S","verlauf":[],"prompt":"Hi"}), &json!({}), &[]);
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["text"], "Hallo");
        let anfragen = h.join().unwrap();
        assert!(anfragen[0].starts_with("POST /api/chat"), "{}", anfragen[0]);
        // Den Koerper als JSON lesen: auf die Schluesselreihenfolge kommt
        // es nicht an (serde_json sortiert, DESIGN 5q).
        let roh = &anfragen[0];
        let koerper: Value = serde_json::from_str(&roh[roh.find("\r\n\r\n").unwrap() + 4..]).unwrap();
        assert_eq!(koerper["model"], "qwen");
        assert_eq!(koerper["stream"], false);
        assert_eq!(koerper["messages"][0]["content"], "S");
        assert_eq!(koerper["messages"][1]["content"], "Hi");
    }

    #[test]
    fn ohne_modell_waehlt_das_erste_mit_gemessenen_werkzeugen_in_serverreihenfolge() {
        // Reihenfolge des Servers gilt, aber nur unter den tauglichen -- das
        // zweite Modell ist das erste mit `tools`, das dritte bleibt liegen.
        let katalog = json!({"stand": 1, "modelle": {
            "erstes:7b": {"tools": false},
            "zweites": {"tools": true},
            "drittes": {"tools": true},
        }});
        let (b, h) = server(vec![
            (200, r#"{"models":[{"name":"erstes:7b"},{"name":"zweites"},{"name":"drittes"}]}"#.into()),
            (200, r#"{"message":{"content":"ok"}}"#.into()),
        ]);
        let a = op_chat(Some(&b), &json!({"prompt":"x"}), &katalog, &[]);
        assert_eq!(a["modell"], "zweites", "{a}");
        let anfragen = h.join().unwrap();
        let roh = &anfragen[1];
        let koerper: Value = serde_json::from_str(&roh[roh.find("\r\n\r\n").unwrap() + 4..]).unwrap();
        assert_eq!(koerper["model"], "zweites", "der Server muss das gewaehlte Modell bekommen");
    }

    #[test]
    fn ohne_taugliches_modell_kein_modell_und_keine_anfrage() {
        // Ein Server mit zwei Modellen, keines gemessen: es wird NICHTS
        // geschickt -- der Testserver hat nur die Modellliste zu beantworten
        // und wuerde einen Chat-Versuch als fehlenden Aufruf melden.
        let katalog = json!({"stand": 1, "modelle": {"a": {"tools": null}, "b": {"tools": null}}});
        let (b, h) = server(vec![(200, r#"{"models":[{"name":"a"},{"name":"b"}]}"#.into())]);
        let a = op_chat(Some(&b), &json!({"prompt":"x"}), &katalog, &[]);
        assert_eq!(a["fehler"]["code"], "kein_modell", "{a}");
        let t = a["fehler"]["text"].as_str().unwrap();
        assert!(t.contains("gemessen"), "{t}");
        h.join().unwrap();
    }

    #[test]
    fn gemessen_ohne_werkzeuge_ist_ein_anderer_grund_als_unbekannt() {
        let katalog = json!({"stand": 1, "modelle": {"a": {"tools": false}, "b": {"tools": false}}});
        assert_eq!(
            modell_waehlen(&["a".into(), "b".into()], &katalog, &[]).unwrap_err(),
            "Der Server meldet 2 Modelle, keines kann Werkzeuge."
        );
        assert_eq!(
            modell_waehlen(&[], &katalog, &[]).unwrap_err(),
            "Der Server hat kein Modell."
        );
        assert_eq!(
            modell_waehlen(&["a".into()], &json!({}), &[]).unwrap_err(),
            "Keines der 1 gemeldeten Modelle ist gemessen (Katalog leer). Messen: katalog_aktualisieren."
        );
    }

    #[test]
    fn die_reihenfolge_des_nutzers_geht_vor_die_des_servers() {
        let katalog = json!({"modelle": {"a": {"tools": true}, "b": {"tools": true}}});
        let liste = vec!["a".to_string(), "b".to_string()];
        assert_eq!(modell_waehlen(&liste, &katalog, &[]).unwrap(), "a");
        assert_eq!(modell_waehlen(&liste, &katalog, &["b".to_string()]).unwrap(), "b");
        // Ein Modell, das der Server nicht mehr meldet, wird uebersprungen.
        assert_eq!(modell_waehlen(&liste, &katalog, &["weg".to_string(), "b".to_string()]).unwrap(), "b");
        // Gemessen untauglich ebenso -- die Wahl schickt nichts in ein Modell,
        // von dem die Messung sagt, dass es keine Werkzeuge kann.
        let k2 = json!({"modelle": {"a": {"tools": true}, "b": {"tools": false}}});
        assert_eq!(modell_waehlen(&liste, &k2, &["b".to_string()]).unwrap(), "a");
    }

    #[test]
    fn ein_genanntes_modell_wird_nicht_umgewaehlt() {
        // Wer ein Modell nennt, bekommt es -- auch ohne `tools` im Katalog.
        let katalog = json!({"modelle": {"b": {"tools": true}}});
        let (b, h) = server(vec![(200, r#"{"message":{"content":"ok"}}"#.into())]);
        let a = op_chat(Some(&b), &json!({"modell":"a","prompt":"x"}), &katalog, &[]);
        assert_eq!(a["modell"], "a", "{a}");
        h.join().unwrap();
    }

    #[test]
    fn server_fehler_bekommt_status_und_grund() {
        let (b, h) = server(vec![(404, r#"{"error":"model 'x' not found"}"#.into())]);
        let a = op_chat(Some(&b), &json!({"modell":"x","prompt":"y"}), &json!({}), &[]);
        assert_eq!(a["fehler"]["code"], "anbieter_fehler");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("not found"), "{a}");
        h.join().unwrap();
    }

    #[test]
    fn zu_viele_anfragen_heissen_ausgelastet() {
        let (b, h) = server(vec![(429, r#"{"error":"busy"}"#.into())]);
        let a = op_chat(Some(&b), &json!({"modell":"x","prompt":"y"}), &json!({}), &[]);
        assert_eq!(a["fehler"]["code"], "ausgelastet");
        h.join().unwrap();
    }

    #[test]
    fn niemand_zu_hause_heisst_nicht_erreichbar() {
        // Port 1 auf localhost: Verbindung wird abgelehnt.
        let a = op_chat(Some("http://127.0.0.1:1"), &json!({"modell":"x","prompt":"y"}), &json!({}), &[]);
        assert_eq!(a["fehler"]["code"], "nicht_erreichbar", "{a}");
    }

    #[test]
    fn modellliste_ueber_den_server() {
        let (b, h) = server(vec![(200, r#"{"models":[{"name":"a"},{"name":"b:1"}]}"#.into())]);
        let a = op_modelle(Some(&b), &json!({}), &[]);
        assert_eq!(a["modelle"], json!(["a", "b:1"]));
        assert_eq!(a["wahl"], Value::Null, "ohne Messung keine Wahl: {a}");
        assert!(a["wahl_grund"].as_str().unwrap().contains("gemessen"), "{a}");
        h.join().unwrap();
    }

    #[test]
    fn modellliste_nennt_die_wahl_die_ein_chat_treffen_wuerde() {
        let (b, h) = server(vec![(200, r#"{"models":[{"name":"a"},{"name":"b"}]}"#.into())]);
        let katalog = json!({"modelle": {"a": {"tools": false}, "b": {"tools": true}}});
        let a = op_modelle(Some(&b), &katalog, &[]);
        assert_eq!(a["wahl"], "b", "{a}");
        assert_eq!(a["wahl_grund"], Value::Null);
        h.join().unwrap();
    }

    #[test]
    fn eigenschaften_messen_tools_und_kontext() {
        let tag = json!({"name": "q", "details": {"parameter_size": "9.7B"}});
        let show = json!({"capabilities": ["completion", "tools"], "model_info": {"qwen35.context_length": 262144, "x.y": 1}});
        let e = eigenschaften(&tag, Some(&show));
        assert_eq!(e["tools"], true);
        assert_eq!(e["kontext"], 262144);
        assert_eq!(e["groesse"], "9.7B");
        assert_eq!(e["gemessen"], true);
        let emb = eigenschaften(&tag, Some(&json!({"capabilities": ["embedding"]})));
        assert_eq!(emb["tools"], false, "gemessen ohne tools ist nein");
    }

    #[test]
    fn nicht_messbar_ist_unbekannt_nicht_nein() {
        let tag = json!({"name": "q"});
        let e = eigenschaften(&tag, None);
        assert!(e["tools"].is_null(), "kein show: unbekannt");
        assert_eq!(e["gemessen"], false);
        // Alter Server: show antwortet, kennt aber keine capabilities.
        let alt = eigenschaften(&tag, Some(&json!({"model_info": {}})));
        assert!(alt["tools"].is_null(), "ohne capabilities: unbekannt");
        assert_eq!(alt["gemessen"], true);
    }

    #[test]
    fn katalog_fragt_tags_und_je_modell_show() {
        let (b, h) = server(vec![
            (200, r#"{"models":[{"name":"a","details":{"parameter_size":"1B"}},{"name":"b"}]}"#.into()),
            (200, r#"{"capabilities":["tools"],"model_info":{"l.context_length":4096}}"#.into()),
            (404, r#"{"error":"weg"}"#.into()),
        ]);
        let k = katalog_von(&b, Duration::from_secs(30)).unwrap();
        assert_eq!(k["a"]["tools"], true);
        assert_eq!(k["a"]["kontext"], 4096);
        assert!(k["b"]["tools"].is_null(), "show 404: unbekannt");
        let g = h.join().unwrap();
        assert!(g[0].starts_with("GET /api/tags"), "{}", g[0]);
        assert!(g[1].starts_with("POST /api/show") && g[1].contains("\"a\""), "{}", g[1]);
    }

    #[test]
    fn nach_dem_budget_wird_nicht_mehr_gefragt() {
        // Budget null: nur /api/tags geht raus, alle Modelle bleiben unbekannt.
        let (b, h) = server(vec![(200, r#"{"models":[{"name":"a"},{"name":"b"}]}"#.into())]);
        let k = katalog_von(&b, Duration::ZERO).unwrap();
        assert_eq!(k.len(), 2);
        assert!(k["a"]["tools"].is_null() && k["b"]["tools"].is_null());
        assert_eq!(h.join().unwrap().len(), 1, "kein /api/show");
    }

    #[test]
    fn das_budget_entscheidet_nicht_der_zufall_einer_verbindung() {
        // Ein Server, der show beantworten WUERDE. Bei Budget null darf sein
        // Wissen (tools: true) trotzdem nicht im Katalog stehen.
        let (b, _h) = server(vec![
            (200, r#"{"models":[{"name":"a"}]}"#.into()),
            (200, r#"{"capabilities":["tools"]}"#.into()),
        ]);
        let k = katalog_von(&b, Duration::ZERO).unwrap();
        assert!(k["a"]["tools"].is_null(), "show lief trotz abgelaufenem Budget: {k:?}");
        // Mit Budget gelangt dasselbe Wissen in den Katalog (Gegenstueck).
        let (b2, h2) = server(vec![
            (200, r#"{"models":[{"name":"a"}]}"#.into()),
            (200, r#"{"capabilities":["tools"]}"#.into()),
        ]);
        let k2 = katalog_von(&b2, Duration::from_secs(30)).unwrap();
        assert_eq!(k2["a"]["tools"], true);
        h2.join().unwrap();
    }

    #[test]
    fn katalog_scheitert_wenn_tags_scheitert() {
        let f = katalog_von("http://127.0.0.1:1", Duration::from_secs(1)).unwrap_err();
        assert_eq!(f["fehler"]["code"], "nicht_erreichbar");
    }
}
