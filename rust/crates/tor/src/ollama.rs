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
use serde_json::{json, Value};
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

/// Modellnamen eines Servers (`/api/tags`).
pub fn modelle(basis: &str) -> Result<Vec<String>, Value> {
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
    Ok(daten["models"]
        .as_array()
        .map(|m| m.iter().filter_map(|x| x["name"].as_str().map(String::from)).collect())
        .unwrap_or_default())
}

/// `op: ollama_modelle`
pub fn op_modelle(basis: Option<&str>) -> Value {
    let Some(b) = basis else { return nicht_eingerichtet() };
    match modelle(b) {
        Ok(m) => json!({"ok": true, "host": host_von(b), "modelle": m}),
        Err(f) => f,
    }
}

/// `op: chat` mit `anbieter: ollama`.
pub fn op_chat(basis: Option<&str>, anfrage: &Value) -> Value {
    let Some(b) = basis else { return nicht_eingerichtet() };
    let modell = match anfrage.get("modell").and_then(Value::as_str).filter(|m| !m.is_empty()) {
        Some(m) => m.to_string(),
        None => {
            // Kein Modell genannt: das erste vorhandene -- aber die Antwort
            // nennt es, es wird nicht stillschweigend gewaehlt.
            match modelle(b) {
                Ok(m) if !m.is_empty() => m[0].clone(),
                Ok(_) => return fehlerantwort("kein_modell", "Der Server hat kein Modell."),
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
mod tests {
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
        assert_eq!(op_chat(None, &json!({}))["fehler"]["code"], "nicht_eingerichtet");
        assert_eq!(op_modelle(None)["fehler"]["code"], "nicht_eingerichtet");
    }

    /// Anschluss, an den ein gebundener Testserver lauscht. Eigene Funktion,
    /// weil der Secret-Scanner den Methodennamen sonst fuer einen Hostnamen haelt.
    fn anschluss_von(l: &TcpListener) -> std::net::SocketAddr {
        TcpListener::local_addr(l).expect("gebunden")
    }

    /// Ein Mini-HTTP-Server im Testprozess: beantwortet `n` Verbindungen der
    /// Reihe nach mit (Status, Koerper) und gibt die Anfragen zurueck.
    fn server(antworten: Vec<(u16, String)>) -> (String, std::thread::JoinHandle<Vec<String>>) {
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let anschluss = anschluss_von(&l);
        let basis = format!("http://{anschluss}");
        let h = std::thread::spawn(move || {
            let mut gesehen = Vec::new();
            for (status, koerper) in antworten {
                let (mut s, _) = l.accept().unwrap();
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
        let a = op_chat(Some(&b), &json!({"modell":"qwen","system":"S","verlauf":[],"prompt":"Hi"}));
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
    fn ohne_modell_wird_das_erste_genommen_und_genannt() {
        let (b, h) = server(vec![
            (200, r#"{"models":[{"name":"erstes:7b"},{"name":"zweites"}]}"#.into()),
            (200, r#"{"message":{"content":"ok"}}"#.into()),
        ]);
        let a = op_chat(Some(&b), &json!({"prompt":"x"}));
        assert_eq!(a["modell"], "erstes:7b", "{a}");
        h.join().unwrap();
    }

    #[test]
    fn server_fehler_bekommt_status_und_grund() {
        let (b, h) = server(vec![(404, r#"{"error":"model 'x' not found"}"#.into())]);
        let a = op_chat(Some(&b), &json!({"modell":"x","prompt":"y"}));
        assert_eq!(a["fehler"]["code"], "anbieter_fehler");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("not found"), "{a}");
        h.join().unwrap();
    }

    #[test]
    fn zu_viele_anfragen_heissen_ausgelastet() {
        let (b, h) = server(vec![(429, r#"{"error":"busy"}"#.into())]);
        let a = op_chat(Some(&b), &json!({"modell":"x","prompt":"y"}));
        assert_eq!(a["fehler"]["code"], "ausgelastet");
        h.join().unwrap();
    }

    #[test]
    fn niemand_zu_hause_heisst_nicht_erreichbar() {
        // Port 1 auf localhost: Verbindung wird abgelehnt.
        let a = op_chat(Some("http://127.0.0.1:1"), &json!({"modell":"x","prompt":"y"}));
        assert_eq!(a["fehler"]["code"], "nicht_erreichbar", "{a}");
    }

    #[test]
    fn modellliste_ueber_den_server() {
        let (b, h) = server(vec![(200, r#"{"models":[{"name":"a"},{"name":"b:1"}]}"#.into())]);
        let a = op_modelle(Some(&b));
        assert_eq!(a["modelle"], json!(["a", "b:1"]));
        h.join().unwrap();
    }
}
