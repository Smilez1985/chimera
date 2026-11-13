//! DeepSeek in der Cloud (ROADMAP „DeepSeek als Anbieter", Auftrag smilez
//! 13.11.). Ein eigenes Modul neben `ollama.rs`, weil die Form eine andere ist:
//! OpenAI-kompatibel, aber mit eigenen Feldern (`thinking`,
//! `reasoning_content`) und einem **anderen Stromformat** (SSE statt NDJSON).
//!
//! Der Schlüssel gehört dem Gateway. Er kommt aus der Umgebung
//! (`DEEPSEEK_API_KEY`, nur das Gateway liest die `.env`, DESIGN 5l) oder aus
//! der Schlüsselablage der Anbietertabelle (`state/keys/`), die die Oberfläche
//! füllt. Er steht in keiner Antwort und in keiner Fehlermeldung.
//!
//! Die Fakten stehen in `docs/RECHERCHE-deepseek.md` (Abruf 13.11.), die
//! Abweichungen zur OpenAI-Form sind dort belegt und hier eingebaut:
//! Denktext neben `content`, kein eigener Usage-Chunk im Strom,
//! `tool_choice: "required"` ist im Thinking-Modus verboten (400).

use gemein::zeile::fehlerantwort;
use serde_json::{json, Value};
use std::time::Duration;

/// Die Adresse, wenn der Anbieter keine eigene nennt (Doku, 13.11.).
pub const BASIS: &str = "https://api.deepseek.com";
pub const VERBINDUNG: Duration = Duration::from_secs(10);
/// So lange darf ein Chat dauern. Der Agent wartet 310 s (`WARTEN_CHAT`) --
/// hier eine Sekunde weniger, damit **diese** Seite die Zeitgrenze meldet und
/// nicht der Aufrufer mit einem stummen Abbruch.
pub const AUFRUF: Duration = Duration::from_secs(300);
pub const ABFRAGE: Duration = Duration::from_secs(10);

/// Die Adresse des Anbieters: eigener Eintrag, sonst die feste Basis.
/// Leer heisst „nicht gesetzt" und nimmt die Vorgabe -- ein Anbieter ohne
/// Adresse ist DeepSeek selbst, kein Fehler.
pub fn basis_aus(wert: Option<&str>) -> String {
    match wert.map(str::trim).filter(|w| !w.is_empty()) {
        Some(a) => a.trim_end_matches('/').to_string(),
        None => BASIS.to_string(),
    }
}

/// Nur der Rechnername fuer die Anzeige („deepseek @ api.deepseek.com").
pub fn host_von(basis: &str) -> String {
    let ohne = basis.split("://").nth(1).unwrap_or(basis);
    ohne.split('/').next().unwrap_or(ohne).to_string()
}

fn agent(global: Duration) -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_connect(Some(VERBINDUNG))
        .timeout_global(Some(global))
        // Ein HTTP-Status ist eine Antwort, kein Fehler des Aufrufs: 402
        // (kein Guthaben) muss sich von „nicht erreichbar" unterscheiden.
        .http_status_as_error(false)
        .build()
        .into()
}

/// Der Schlüssel aus der Umgebung, ohne ihn je auszugeben.
pub fn schluessel_aus_umgebung() -> Option<String> {
    std::env::var("DEEPSEEK_API_KEY")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

// ------------------------------------------------------------- Denken

/// Ist das Denken ausdrücklich **aus**? Vorgabe ist bei DeepSeek **an**
/// (Doku, 13.11.) -- nur wer es abschaltet, bekommt das Feld.
pub fn denken_aus(anfrage: &Value) -> bool {
    match anfrage.get("denken") {
        Some(Value::Bool(false)) => true,
        Some(Value::String(s)) => matches!(s.trim().to_lowercase().as_str(), "off" | "aus" | "none"),
        _ => false,
    }
}

/// DeepSeeks Denkstufen: `low` / `high` / `max`. Was es nicht kennt, wird
/// nicht erfunden -- `medium`/`xhigh` entsprechen laut Doku `high`.
fn denkstufe(wert: &Value) -> Option<&'static str> {
    let s = match wert {
        Value::Bool(true) => return Some("high"),
        Value::String(s) => s.trim().to_lowercase(),
        _ => return None,
    };
    Some(match s.as_str() {
        "low" | "niedrig" | "minimal" => "low",
        "medium" | "mittel" | "high" | "hoch" | "xhigh" => "high",
        "max" => "max",
        "none" | "off" | "aus" => return None,
        _ => return None,
    })
}

/// `tool_choice: "required"` fällt im Thinking-Modus mit 400 durch (Doku
/// 13.11.). Das Gateway schickt es dann nicht mit und **sagt** es -- ein
/// stillschweigend weggelassenes Feld wäre die Falle, die der Aufrufer nicht
/// sieht. `Some(Text)` heisst: dieser Hinweis gehört in die Antwort.
fn werkzeug_wahl_verworfen(anfrage: &Value) -> Option<String> {
    let wahl = anfrage.get("tool_choice")?;
    if wahl.as_str() != Some("required") || denken_aus(anfrage) {
        return None;
    }
    Some(
        "tool_choice: \"required\" ist im Thinking-Modus verboten (HTTP 400) -- \
         nicht mitgeschickt, DeepSeek wählt selbst."
            .to_string(),
    )
}

// ------------------------------------------------------------- Koerper

/// Der Anfragekoerper fuer `/chat/completions`. Rein, damit er sich pruefen
/// laesst: OpenAI-Form, aber ohne die Felder, die DeepSeek ignoriert
/// (`frequency_penalty`, `presence_penalty` werden nicht erst geschickt).
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
    let strom = anfrage["stream"].as_bool().unwrap_or(false);
    let mut k = json!({
        "model": modell,
        "messages": nachrichten,
        "stream": strom,
    });
    // Ohne `include_usage` fehlen die Zahlen im Strom ganz -- die Doku sagt,
    // sie hängen am letzten Inhalts-Chunk (RECHERCHE 13.11., Abschnitt 2).
    if strom {
        k["stream_options"] = json!({"include_usage": true});
    }
    // Denken: nur nennen, wenn der Auftrag es sagt. Der Server denkt sonst
    // von selbst -- und das Gateway behauptet dann keine Einstellung.
    if denken_aus(anfrage) {
        k["thinking"] = json!({"type": "disabled"});
    } else if let Some(stufe) = anfrage.get("denken").and_then(denkstufe) {
        k["thinking"] = json!({"type": "enabled"});
        k["reasoning_effort"] = json!(stufe);
    }
    // Die Werkzeuge sind schon in der OpenAI-Form, die DeepSeek erwartet --
    // dieselbe Uebersetzung wie bei Ollama (eine Stelle, 10g).
    if let Some(w) = anfrage.get("werkzeuge").filter(|w| !w.is_null()) {
        let liste = crate::ollama::werkzeuge_nach_ollama(w);
        if liste.as_array().is_some_and(|a| !a.is_empty()) {
            k["tools"] = liste;
        }
    }
    if let Some(wahl) = anfrage.get("tool_choice") {
        if werkzeug_wahl_verworfen(anfrage).is_none() {
            k["tool_choice"] = wahl.clone();
        }
    }
    if let Some(t) = anfrage.get("temperature").filter(|t| t.is_number()) {
        k["temperature"] = t.clone();
    }
    k
}

// ------------------------------------------------------------- Strom

/// Eine SSE-Zeile zerlegen: `None` heisst „keine Nutzdaten" (Leerzeile,
/// `: keep-alive`-Kommentar, kaputtes JSON). Der Kommentar ist im Strom
/// normal -- ihn als JSON zu lesen war der Fehler, den die Doku nennt.
fn sse_daten(zeile: &str) -> Option<Value> {
    let z = zeile.trim();
    if z.is_empty() || z.starts_with(':') {
        return None;
    }
    let rest = z.strip_prefix("data:")?.trim();
    if rest.is_empty() || rest == "[DONE]" {
        return None;
    }
    serde_json::from_str::<Value>(rest).ok()
}

/// Die Zahlen aus `usage` (auch die Cache-Felder, RECHERCHE Abschnitt 2).
/// Fehlt `usage`, bleiben alle Werte `null` -- nicht 0: „ohne Usage" ist
/// etwas anderes als „null Token" (ROADMAP „Kosten aus Token × Preis").
fn verbrauch_aus(u: &Value) -> Value {
    json!({
        "eingabe": u["prompt_tokens"].as_u64(),
        "ausgabe": u["completion_tokens"].as_u64(),
        "cache_treffer": u["prompt_cache_hit_tokens"].as_u64(),
        "cache_neu": u["prompt_cache_miss_tokens"].as_u64(),
        "denken": u["completion_tokens_details"]["reasoning_tokens"].as_u64(),
    })
}

/// Die Werkzeugaufrufe einer Antwort, **neutral** (`[{"name", "argumente",
/// "id"?}]`) -- so steht es im Vertrag des Agenten (`provider/base.py`,
/// `Reply.werkzeuge`). DeepSeek schickt `arguments` als JSON-**Text**.
pub fn aufrufe_neutral(liste: &Value) -> Vec<Value> {
    let mut raus = Vec::new();
    let Some(l) = liste.as_array() else { return raus };
    for c in l.iter() {
        let name = c["function"]["name"].as_str().unwrap_or("").trim().to_string();
        if name.is_empty() {
            continue;
        }
        let mut e = json!({
            "name": name,
            "argumente": Value::Object(crate::ollama::argumente_als_objekt(&c["function"]["arguments"])),
        });
        if let Some(id) = c["id"].as_str().filter(|i| !i.is_empty()) {
            e["id"] = json!(id);
        }
        raus.push(e);
    }
    raus
}

/// Einen Strom sammeln: Teilstuecke zusammensetzen, Werkzeugaufrufe nach
/// `index` fuehren, `usage` vom letzten Chunk nehmen. Ergebnis hat dieselbe
/// Form wie eine Antwort ohne Strom (`{"text", "denken", "aufrufe",
/// "verbrauch"}`), damit der Rest des Wegs nur eine Form kennt.
pub fn strom_sammeln(zeilen: impl Iterator<Item = String>) -> Value {
    let mut text = String::new();
    let mut gedacht = String::new();
    // index, id, name, arguments (Text, wird am Ende gelesen)
    let mut calls: Vec<(i64, String, String, String)> = Vec::new();
    let mut usage = Value::Null;
    let mut fehler: Option<String> = None;
    for zeile in zeilen {
        if zeile.trim() == "data: [DONE]" || zeile.trim() == "[DONE]" {
            break;
        }
        let Some(v) = sse_daten(&zeile) else { continue };
        if let Some(e) = v["error"]["message"].as_str().or(v["error"].as_str()) {
            if !e.is_empty() {
                fehler = Some(e.to_string());
                continue;
            }
        }
        let d = &v["choices"][0]["delta"];
        if let Some(t) = d["content"].as_str() {
            text.push_str(t);
        }
        if let Some(t) = d["reasoning_content"].as_str() {
            gedacht.push_str(t);
        }
        if let Some(liste) = d["tool_calls"].as_array() {
            for (pos, c) in liste.iter().enumerate() {
                let idx = c["index"].as_i64().unwrap_or(pos as i64);
                let stelle = match calls.iter().position(|(i, _, _, _)| *i == idx) {
                    Some(s) => s,
                    None => {
                        calls.push((idx, String::new(), String::new(), String::new()));
                        calls.len() - 1
                    }
                };
                if let Some(id) = c["id"].as_str().filter(|i| !i.is_empty()) {
                    calls[stelle].1 = id.to_string();
                }
                if let Some(n) = c["function"]["name"].as_str() {
                    calls[stelle].2.push_str(n);
                }
                match &c["function"]["arguments"] {
                    Value::String(t) => calls[stelle].3.push_str(t),
                    v @ Value::Object(_) => calls[stelle].3 = v.to_string(),
                    _ => {}
                }
            }
        }
        // `usage: null` kommt in fast jedem Chunk -- nur ein Objekt zählt.
        if v["usage"].is_object() {
            usage = v["usage"].clone();
        }
    }
    let mut roh: Vec<Value> = calls
        .into_iter()
        .map(|(idx, id, name, args)| {
            json!({"index": idx, "id": id, "function": {"name": name, "arguments": args}})
        })
        .collect();
    roh.sort_by_key(|c| c["index"].as_i64().unwrap_or(0));
    let mut aus = json!({
        "text": text,
        "denken": gedacht,
        "aufrufe": Value::Array(aufrufe_neutral(&Value::Array(roh))),
        "verbrauch": verbrauch_aus(&usage),
    });
    if let Some(e) = fehler {
        aus["__fehler"] = json!(e);
    }
    aus
}

// ------------------------------------------------------------- Antwort

/// Aus einer gesammelten Antwort die Antwort des Gateways machen.
///
/// `content: ""` ist bei einem Werkzeugaufruf der Normalfall. „leer" ist nur,
/// wenn weder Text noch Aufruf kommt -- und Denktext allein ist keine
/// Antwort: er heisst `nur_gedacht` und wird mit Länge und Auszug benannt,
/// nicht verschwiegen (wie bei Ollama seit 13.11.).
pub fn antwort_aus(gesammelt: &Value, anbieter: &str, modell: &str, host: &str) -> Value {
    let text = gesammelt["text"].as_str().unwrap_or("");
    let aufrufe = gesammelt["aufrufe"].as_array().cloned().unwrap_or_default();
    if text.is_empty() && aufrufe.is_empty() {
        if let Some(gedacht) = gesammelt["denken"].as_str().filter(|s| !s.trim().is_empty()) {
            let mut f = fehlerantwort(
                "nur_gedacht",
                "DeepSeek hat nur gedacht und keine Antwort geliefert.",
            );
            f["fehler"]["denkzeichen"] = json!(gedacht.chars().count());
            f["fehler"]["denkauszug"] = json!(gedacht.chars().take(400).collect::<String>());
            return f;
        }
        return fehlerantwort("leer", "DeepSeek lieferte eine leere Antwort.");
    }
    let mut a = json!({
        "ok": true,
        "text": text,
        "anbieter": anbieter,
        "modell": modell,
        "host": host,
        "verbrauch": gesammelt["verbrauch"].clone(),
    });
    if !aufrufe.is_empty() {
        a["werkzeuge"] = Value::Array(aufrufe);
    }
    a
}

/// Ein HTTP-Status wird zu einem benannten Fehler. „anbieter_fehler" fuer
/// alles ist zu wenig: 402 heisst „Konto leer" (Alarmsignal), 401 „Schlüssel
/// falsch" -- beides verlangt einen anderen Griff als ein 500.
pub fn statusfehler(status: u16, koerper: &Value, host: &str) -> Value {
    let meldung = koerper["error"]["message"]
        .as_str()
        .filter(|m| !m.trim().is_empty())
        .unwrap_or("ohne Angabe");
    let (code, text) = match status {
        400 => (
            "anfrage_falsch",
            format!("{host} lehnt die Anfrage ab (400): {meldung}"),
        ),
        401 => (
            "schluessel_falsch",
            format!("{host} nimmt den Schlüssel nicht an (401): {meldung}"),
        ),
        402 => (
            "kein_guthaben",
            format!("{host} meldet kein Guthaben (402) -- das Konto muss aufgeladen werden: {meldung}"),
        ),
        422 => (
            "parameter_falsch",
            format!("{host} lehnt einen Parameter ab (422): {meldung}"),
        ),
        429 => (
            "ausgelastet",
            format!("{host} ist ausgelastet (429, Nebenläufigkeitsgrenze des Kontos): {meldung}"),
        ),
        500..=599 => (
            "anbieter_fehler",
            format!("{host} antwortet {status}: {meldung}"),
        ),
        _ => (
            "anbieter_fehler",
            format!("{host} antwortet {status}: {meldung}"),
        ),
    };
    fehlerantwort(code, &text)
}

/// Aus einem Aufruffehler die Antwort des Gateways machen (wie bei Ollama:
/// eine Zeitgrenze ist **kein** „nicht erreichbar").
pub fn fehler_bei_aufruf(e: &ureq::Error, host: &str, grenze: Duration) -> Value {
    if matches!(e, ureq::Error::Timeout(_)) {
        return fehlerantwort(
            "zeitgrenze",
            &format!(
                "{host} hat nach {} s nicht geantwortet -- ein Denkmodell kann laenger denken, als die Zeitgrenze erlaubt.",
                grenze.as_secs()
            ),
        );
    }
    fehlerantwort("nicht_erreichbar", &format!("{host} antwortet nicht: {e}"))
}

// ------------------------------------------------------------- Modelle

/// `GET /models` -- die Namen in Serverreihenfolge.
pub fn modelle(basis: &str, schluessel: &str) -> Result<Vec<String>, Value> {
    let url = format!("{basis}/models");
    let host = host_von(basis);
    let mut r = agent(ABFRAGE)
        .get(&url)
        .header("authorization", &format!("Bearer {schluessel}"))
        .header("accept", "application/json")
        .call()
        .map_err(|e| fehler_bei_aufruf(&e, &host, ABFRAGE))?;
    let status = r.status().as_u16();
    let roh: Value = r
        .body_mut()
        .read_json()
        .map_err(|e| fehlerantwort("anbieter_fehler", &format!("Antwort nicht lesbar ({status}): {e}")))?;
    if status != 200 {
        return Err(statusfehler(status, &roh, &host));
    }
    Ok(roh["data"]
        .as_array()
        .map(|l| {
            l.iter()
                .filter_map(|m| m["id"].as_str())
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default())
}

/// Wahl ohne genannte Modellangabe: die Reihenfolge des Nutzers
/// (`wahl.json`, 5h), sonst das erste in Serverreihenfolge.
///
/// Anders als bei Ollama braucht es hier **keine Messung**: DeepSeeks
/// Chat-Modelle können laut Doku alle Werkzeuge, und `/models` liefert keine
/// Eigenschaften. Deshalb entscheidet die Reihenfolge, nicht `tools` -- die
/// Antwort nennt das gewählte Modell, es wird nichts verschwiegen.
pub fn modell_waehlen(modelle: &[String], bevorzugt: &[String]) -> Result<String, String> {
    if modelle.is_empty() {
        return Err("Der Anbieter meldet kein Modell.".to_string());
    }
    for name in bevorzugt {
        if modelle.contains(name) {
            return Ok(name.clone());
        }
    }
    Ok(modelle[0].clone())
}

/// `op: modelle` fuer einen DeepSeek-Anbieter.
pub fn op_modelle(basis: &str, schluessel: Option<&str>, bevorzugt: &[String], anbieter: &str) -> Value {
    let Some(schluessel) = schluessel.filter(|s| !s.trim().is_empty()) else {
        return fehlerantwort(
            "nicht_eingerichtet",
            &format!("Für den Anbieter {anbieter} fehlt der Schlüssel."),
        );
    };
    let host = host_von(basis);
    match modelle(basis, schluessel) {
        Ok(m) => {
            let (wahl, grund) = match modell_waehlen(&m, bevorzugt) {
                Ok(name) => (Value::String(name), Value::Null),
                Err(g) => (Value::Null, Value::String(g)),
            };
            json!({"ok": true, "host": host, "modelle": m, "wahl": wahl, "wahl_grund": grund})
        }
        Err(f) => f,
    }
}

/// `op: chat` fuer einen DeepSeek-Anbieter.
pub fn op_chat(
    anbieter: &str,
    basis: Option<&str>,
    schluessel: Option<&str>,
    anfrage: &Value,
    bevorzugt: &[String],
) -> Value {
    let b = basis_aus(basis);
    let host = host_von(&b);
    let Some(schluessel) = schluessel.map(str::trim).filter(|s| !s.is_empty()) else {
        return fehlerantwort(
            "nicht_eingerichtet",
            &format!(
                "Für den Anbieter {anbieter} fehlt der Schlüssel (DEEPSEEK_API_KEY in der .env oder im Modul „Anbieter“ hinterlegt)."
            ),
        );
    };
    let modell = match anfrage.get("modell").and_then(Value::as_str).filter(|m| !m.is_empty()) {
        Some(m) => m.to_string(),
        None => match modelle(&b, schluessel) {
            Ok(m) => match modell_waehlen(&m, bevorzugt) {
                Ok(name) => name,
                Err(grund) => return fehlerantwort("kein_modell", &grund),
            },
            Err(f) => return f,
        },
    };
    let koerper = chat_koerper(&modell, anfrage);
    // Werkzeuge, die mitgegeben wurden, aber nicht durchkommen, sind ein
    // Fehler und kein stiller Verzicht (DESIGN, „Aufrufe, nicht Text").
    let gewollt = anfrage.get("werkzeuge").and_then(Value::as_array).is_some_and(|a| !a.is_empty());
    if gewollt && koerper.get("tools").is_none() {
        return fehlerantwort(
            "werkzeuge_ungueltig",
            "Kein Werkzeug kam durch: jedes braucht einen Namen (\"name\"), wahlweise in der \
             OpenAI-Form {type:function, function:{...}}.",
        );
    }
    let url = format!("{b}/chat/completions");
    let mut r = match agent(AUFRUF)
        .post(&url)
        .header("authorization", &format!("Bearer {schluessel}"))
        .header("content-type", "application/json")
        .header("accept", if koerper["stream"].as_bool() == Some(true) { "text/event-stream" } else { "application/json" })
        .send_json(&koerper)
    {
        Ok(r) => r,
        Err(e) => return fehler_bei_aufruf(&e, &host, AUFRUF),
    };
    let status = r.status().as_u16();
    let gesammelt: Value = if status != 200 {
        // Ein Fehler kommt als JSON, nie als Strom -- auch bei `stream: true`.
        let roh: Value = r.body_mut().read_json().unwrap_or(Value::Null);
        return statusfehler(status, &roh, &host);
    } else if koerper["stream"].as_bool() == Some(true) {
        use std::io::BufRead;
        let leser = std::io::BufReader::new(r.body_mut().as_reader());
        strom_sammeln(leser.lines().map_while(Result::ok))
    } else {
        let roh: Value = match r.body_mut().read_json() {
            Ok(v) => v,
            Err(e) => {
                return fehlerantwort(
                    "anbieter_fehler",
                    &format!("Antwort nicht lesbar ({status}): {e}"),
                )
            }
        };
        let nachricht = &roh["choices"][0]["message"];
        json!({
            "text": nachricht["content"].as_str().unwrap_or(""),
            "denken": nachricht["reasoning_content"].as_str().unwrap_or(""),
            "aufrufe": Value::Array(aufrufe_neutral(&nachricht["tool_calls"])),
            "verbrauch": verbrauch_aus(&roh["usage"]),
        })
    };
    if let Some(grund) = gesammelt["__fehler"].as_str() {
        return fehlerantwort("anbieter_fehler", &format!("DeepSeek antwortet {status}: {grund}"));
    }
    let mut a = antwort_aus(&gesammelt, anbieter, &modell, &host);
    if let Some(hinweis) = werkzeug_wahl_verworfen(anfrage) {
        a["werkzeug_wahl_ignoriert"] = json!(hinweis);
    }
    a
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ollama::tests::server;

    #[test]
    fn adresse_und_host() {
        assert_eq!(basis_aus(None), BASIS);
        assert_eq!(basis_aus(Some("  ")), BASIS);
        assert_eq!(basis_aus(Some("https://api.deepseek.com/")), "https://api.deepseek.com");
        assert_eq!(basis_aus(Some("https://proxy.example/v1")), "https://proxy.example/v1");
        assert_eq!(host_von("https://api.deepseek.com"), "api.deepseek.com");
        assert_eq!(host_von("api.deepseek.com"), "api.deepseek.com");
    }

    #[test]
    fn koerper_hat_system_verlauf_und_frage_in_dieser_reihenfolge() {
        let a = json!({"system": "S", "verlauf": [{"role":"user","content":"a"},{"role":"assistant","content":"b"}], "prompt": "Q"});
        let k = chat_koerper("deepseek-flash", &a);
        let r: Vec<&str> = k["messages"].as_array().unwrap().iter().map(|m| m["role"].as_str().unwrap()).collect();
        assert_eq!(r, ["system", "user", "assistant", "user"]);
        assert_eq!(k["model"], "deepseek-flash");
        assert_eq!(k["stream"], false);
        // Ohne Strom keine stream_options -- die gehoeren zum Strom.
        assert!(k.get("stream_options").is_none());
        // Ohne Denkangabe wird nichts behauptet: DeepSeek denkt von selbst.
        assert!(k.get("thinking").is_none());
        assert!(k.get("reasoning_effort").is_none());
    }

    #[test]
    fn strom_bekommt_include_usage() {
        let k = chat_koerper("m", &json!({"prompt": "x", "stream": true}));
        assert_eq!(k["stream"], true);
        assert_eq!(k["stream_options"]["include_usage"], true);
    }

    #[test]
    fn denken_wird_uebersetzt_und_nichts_erfunden() {
        let aus = chat_koerper("m", &json!({"prompt": "x", "denken": false}));
        assert_eq!(aus["thinking"]["type"], "disabled");
        assert!(aus.get("reasoning_effort").is_none());

        let an = chat_koerper("m", &json!({"prompt": "x", "denken": true}));
        assert_eq!(an["thinking"]["type"], "enabled");
        assert_eq!(an["reasoning_effort"], "high");

        // DeepSeek kennt kein "medium" -- es bedeutet dort "high" (Doku).
        let mittel = chat_koerper("m", &json!({"prompt": "x", "denken": "medium"}));
        assert_eq!(mittel["reasoning_effort"], "high");
        let max = chat_koerper("m", &json!({"prompt": "x", "denken": "max"}));
        assert_eq!(max["reasoning_effort"], "max");
        // Unbekannte Stufe: nichts mitschicken statt zu raten.
        let murks = chat_koerper("m", &json!({"prompt": "x", "denken": "irgendwas"}));
        assert!(murks.get("reasoning_effort").is_none());
        assert!(murks.get("thinking").is_none());
    }

    #[test]
    fn required_im_denkmodus_wird_weggelassen_und_gemeldet() {
        // Doku 13.11.: tool_choice "required" + Thinking = HTTP 400.
        let a = json!({"prompt": "x", "tool_choice": "required"});
        assert!(chat_koerper("m", &a).get("tool_choice").is_none());
        let hinweis = werkzeug_wahl_verworfen(&a).expect("Hinweis fehlt");
        assert!(hinweis.contains("400"), "{hinweis}");
        // Mit abgeschaltetem Denken ist es erlaubt.
        let b = json!({"prompt": "x", "tool_choice": "required", "denken": false});
        assert_eq!(chat_koerper("m", &b)["tool_choice"], "required");
        assert!(werkzeug_wahl_verworfen(&b).is_none());
        // "auto" ist immer erlaubt.
        let c = json!({"prompt": "x", "tool_choice": "auto"});
        assert_eq!(chat_koerper("m", &c)["tool_choice"], "auto");
    }

    #[test]
    fn werkzeuge_gehen_in_openai_form_mit() {
        let a = json!({"prompt": "x", "werkzeuge": [
            {"name": "list_dir", "description": "d", "parameters": {"type": "object"}}]});
        let k = chat_koerper("m", &a);
        assert_eq!(k["tools"][0]["type"], "function");
        assert_eq!(k["tools"][0]["function"]["name"], "list_dir");
    }

    #[test]
    fn ignorierte_felder_werden_gar_nicht_erst_geschickt() {
        let k = chat_koerper("m", &json!({"prompt": "x", "frequency_penalty": 0.5, "presence_penalty": 0.5}));
        assert!(k.get("frequency_penalty").is_none());
        assert!(k.get("presence_penalty").is_none());
    }

    #[test]
    fn strom_toleriert_keep_alive_und_null_usage() {
        let zeilen = vec![
            ": keep-alive".to_string(),
            String::new(),
            r#"data: {"choices":[{"delta":{"reasoning_content":"ich denke"}}],"usage":null}"#.to_string(),
            r#"data: {"choices":[{"delta":{"content":"Hal"}}],"usage":null}"#.to_string(),
            r#"data: {"choices":[{"delta":{"content":"lo"}}],"usage":null}"#.to_string(),
            r#"data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":9,"completion_tokens":3,"prompt_cache_hit_tokens":7,"prompt_cache_miss_tokens":2,"completion_tokens_details":{"reasoning_tokens":1}}}"#.to_string(),
            "data: [DONE]".to_string(),
            // Was nach [DONE] kommt, ist nicht mehr Teil der Antwort.
            r#"data: {"choices":[{"delta":{"content":"NICHT"}}]}"#.to_string(),
        ];
        let s = strom_sammeln(zeilen.into_iter());
        assert_eq!(s["text"], "Hallo");
        assert_eq!(s["denken"], "ich denke");
        assert_eq!(s["verbrauch"]["eingabe"], 9);
        assert_eq!(s["verbrauch"]["ausgabe"], 3);
        assert_eq!(s["verbrauch"]["cache_treffer"], 7);
        assert_eq!(s["verbrauch"]["cache_neu"], 2);
        assert_eq!(s["verbrauch"]["denken"], 1);
        assert!(s.get("__fehler").is_none());
    }

    #[test]
    fn strom_ohne_usage_zaehlt_nichts_statt_null() {
        let zeilen = vec![r#"data: {"choices":[{"delta":{"content":"x"}}],"usage":null}"#.to_string()];
        let s = strom_sammeln(zeilen.into_iter());
        assert_eq!(s["text"], "x");
        assert!(s["verbrauch"]["eingabe"].is_null(), "ohne Usage ist der Wert unbekannt, nicht 0");
    }

    #[test]
    fn strom_fuehrt_werkzeugaufrufe_ueber_teilstuecke() {
        let zeilen = vec![
            r#"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"read_","arguments":"{\"pfad\":"}}]}}]}"#.to_string(),
            r#"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"file","arguments":"\"/tmp/x\"}"}}]}}]}"#.to_string(),
            r#"data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}"#.to_string(),
        ];
        let s = strom_sammeln(zeilen.into_iter());
        let a = &s["aufrufe"][0];
        assert_eq!(a["name"], "read_file");
        assert_eq!(a["argumente"]["pfad"], "/tmp/x");
        assert_eq!(a["id"], "call_1");
        assert_eq!(s["text"], "");
    }

    #[test]
    fn leere_antwort_ist_ein_fehler_kein_text() {
        let a = antwort_aus(&json!({"text": "", "aufrufe": [], "denken": ""}), "ds", "m", "h");
        assert_eq!(a["ok"], false);
        assert_eq!(a["fehler"]["code"], "leer");
    }

    #[test]
    fn nur_gedacht_ist_ein_eigener_fehler() {
        let a = antwort_aus(
            &json!({"text": "", "aufrufe": [], "denken": "Ich sollte zuerst nachsehen."}),
            "ds", "m", "h");
        assert_eq!(a["fehler"]["code"], "nur_gedacht");
        assert_eq!(a["fehler"]["denkzeichen"], 28);
        assert_eq!(a["fehler"]["denkauszug"], "Ich sollte zuerst nachsehen.");
        assert!(a.get("text").is_none(), "Gedanken dürfen nie als Antwort durchgehen");
    }

    #[test]
    fn aufruf_ohne_text_ist_ein_erfolg_mit_neutraler_liste() {
        let g = json!({"text": "", "denken": "ich nehme list_dir", "verbrauch": {"eingabe": 1},
            "aufrufe": [{"name": "list_dir", "argumente": {"pfad": "/tmp"}, "id": "c1", "index": 0}]});
        let a = antwort_aus(&g, "ds", "deepseek-flash", "api.deepseek.com");
        assert_eq!(a["ok"], true);
        assert_eq!(a["text"], "");
        // Der Vertrag des Agenten (provider/base.py): name + argumente, keine
        // Verschachtelung in "function".
        assert_eq!(a["werkzeuge"][0]["name"], "list_dir");
        assert_eq!(a["werkzeuge"][0]["argumente"]["pfad"], "/tmp");
        assert_eq!(a["anbieter"], "ds");
    }

    #[test]
    fn aufrufe_aus_openai_form_werden_neutral() {
        let roh = json!([{"id": "c9", "type": "function",
            "function": {"name": "ssh", "arguments": "{\"host\":\"radxa\"}"}}]);
        let n = aufrufe_neutral(&roh);
        assert_eq!(n[0]["name"], "ssh");
        assert_eq!(n[0]["argumente"]["host"], "radxa");
        assert_eq!(n[0]["id"], "c9");
        // Namenloses wird verworfen, nicht mit leerem Namen weitergereicht.
        assert!(aufrufe_neutral(&json!([{"function": {"arguments": "{}"}}])).is_empty());
    }

    #[test]
    fn jeder_status_bekommt_seinen_namen() {
        let f = |s: u16| statusfehler(s, &json!({"error": {"message": "m"}}), "h")["fehler"]["code"].clone();
        assert_eq!(f(400), "anfrage_falsch");
        assert_eq!(f(401), "schluessel_falsch");
        assert_eq!(f(402), "kein_guthaben");
        assert_eq!(f(422), "parameter_falsch");
        assert_eq!(f(429), "ausgelastet");
        assert_eq!(f(500), "anbieter_fehler");
        assert_eq!(f(503), "anbieter_fehler");
        let t = statusfehler(402, &json!({"error": {"message": "Insufficient Balance"}}), "api.deepseek.com");
        assert!(t["fehler"]["text"].as_str().unwrap().contains("Insufficient Balance"));
    }

    #[test]
    fn zeitgrenze_ist_nicht_nicht_erreichbar() {
        let e = ureq::Error::Timeout(ureq::Timeout::Global);
        let a = fehler_bei_aufruf(&e, "api.deepseek.com", AUFRUF);
        assert_eq!(a["fehler"]["code"], "zeitgrenze");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("300 s"));
    }

    #[test]
    fn modellwahl_nimmt_die_reihenfolge_des_nutzers_sonst_die_des_servers() {
        let m = vec!["deepseek-flash".to_string(), "deepseek-v4-pro".to_string()];
        assert_eq!(modell_waehlen(&m, &[]).unwrap(), "deepseek-flash");
        assert_eq!(modell_waehlen(&m, &["deepseek-v4-pro".into()]).unwrap(), "deepseek-v4-pro");
        // Ein bevorzugtes Modell, das der Server nicht meldet, gilt nicht.
        assert_eq!(modell_waehlen(&m, &["weg".into()]).unwrap(), "deepseek-flash");
        assert!(modell_waehlen(&[], &[]).is_err());
    }

    #[test]
    fn ohne_schluessel_wird_nichts_geschickt() {
        let a = op_chat("ds", None, None, &json!({"prompt": "x"}), &[]);
        assert_eq!(a["fehler"]["code"], "nicht_eingerichtet");
        let m = op_modelle(BASIS, Some("   "), &[], "ds");
        assert_eq!(m["fehler"]["code"], "nicht_eingerichtet");
    }

    #[test]
    fn chat_gegen_einen_server_schickt_bearer_und_modell() {
        let (b, h) = server(vec![(200, r#"{"choices":[{"message":{"content":"Hallo"}}],
            "usage":{"prompt_tokens":5,"completion_tokens":2}}"#.into())]);
        let a = op_chat("ds", Some(&b), Some("sk-test"), &json!({"modell":"deepseek-flash","prompt":"Hi"}), &[]);
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["text"], "Hallo");
        assert_eq!(a["modell"], "deepseek-flash");
        assert_eq!(a["verbrauch"]["eingabe"], 5);
        let anfragen = h.join().unwrap();
        assert!(anfragen[0].starts_with("POST /chat/completions"), "{}", anfragen[0]);
        let kopf = anfragen[0].to_lowercase();
        assert!(kopf.contains("authorization: bearer sk-test"), "{}", anfragen[0]);
        // Der Schlüssel steht nur im Kopf, nie im Körper.
        let roh = &anfragen[0];
        let koerper = &roh[roh.find("\r\n\r\n").unwrap() + 4..];
        assert!(!koerper.contains("sk-test"), "Schlüssel im Körper: {koerper}");
    }

    #[test]
    fn strom_ueber_http_wird_gesammelt() {
        let sse = "data: {\"choices\":[{\"delta\":{\"reasoning_content\":\"hmm\"}}],\"usage\":null}\n\
                   : keep-alive\n\
                   data: {\"choices\":[{\"delta\":{\"content\":\"Da\"}}],\"usage\":null}\n\
                   data: {\"choices\":[{\"delta\":{\"content\":\"!\"}}],\"usage\":{\"prompt_tokens\":4,\"completion_tokens\":1}}\n\
                   data: [DONE]\n";
        let (b, h) = server(vec![(200, sse.into())]);
        let a = op_chat("ds", Some(&b), Some("k"), &json!({"modell":"m","prompt":"x","stream":true}), &[]);
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["text"], "Da!");
        assert_eq!(a["verbrauch"]["eingabe"], 4);
        let anfragen = h.join().unwrap();
        let roh = &anfragen[0];
        let koerper: Value = serde_json::from_str(&roh[roh.find("\r\n\r\n").unwrap() + 4..]).unwrap();
        assert_eq!(koerper["stream"], true);
        assert_eq!(koerper["stream_options"]["include_usage"], true);
    }

    #[test]
    fn kein_guthaben_wird_als_solches_gemeldet() {
        let (b, h) = server(vec![(402, r#"{"error":{"message":"Insufficient Balance"}}"#.into())]);
        let a = op_chat("ds", Some(&b), Some("k"), &json!({"modell":"m","prompt":"x"}), &[]);
        assert_eq!(a["fehler"]["code"], "kein_guthaben", "{a}");
        h.join().unwrap();
    }

    #[test]
    fn modelle_kommen_in_serverreihenfolge() {
        let (b, h) = server(vec![(200, r#"{"data":[{"id":"deepseek-flash"},{"id":"deepseek-v4-pro"}]}"#.into())]);
        let a = op_modelle(&b, Some("k"), &[], "ds");
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["modelle"], json!(["deepseek-flash", "deepseek-v4-pro"]));
        assert_eq!(a["wahl"], "deepseek-flash");
        assert_eq!(a["host"], host_von(&b));
        h.join().unwrap();
    }

    #[test]
    fn ohne_modellangabe_wird_erst_die_liste_geholt_dann_gewaehlt() {
        let (b, h) = server(vec![
            (200, r#"{"data":[{"id":"deepseek-flash"},{"id":"deepseek-v4-pro"}]}"#.into()),
            (200, r#"{"choices":[{"message":{"content":"ok"}}],"usage":null}"#.into()),
        ]);
        let a = op_chat("ds", Some(&b), Some("k"), &json!({"prompt":"x"}), &["deepseek-v4-pro".into()]);
        assert_eq!(a["modell"], "deepseek-v4-pro", "{a}");
        let anfragen = h.join().unwrap();
        assert!(anfragen[0].starts_with("GET /models"), "{}", anfragen[0]);
        let roh = &anfragen[1];
        let koerper: Value = serde_json::from_str(&roh[roh.find("\r\n\r\n").unwrap() + 4..]).unwrap();
        assert_eq!(koerper["model"], "deepseek-v4-pro");
    }

    #[test]
    fn werkzeuge_ohne_namen_gehen_nicht_still_verloren() {
        let a = op_chat("ds", Some("http://127.0.0.1:1"), Some("k"),
            &json!({"modell": "m", "prompt": "x", "werkzeuge": [{"description": "ohne Namen"}]}), &[]);
        assert_eq!(a["fehler"]["code"], "werkzeuge_ungueltig", "{a}");
    }
}
