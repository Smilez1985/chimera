//! Websuche als Werkzeug des Gateways (DESIGN Regel 5r).
//!
//! Der Agent hat kein Netz. Wenn er etwas nachschlagen will, fragt er das
//! Gateway (`op: web_suche`); hier wird gesucht, gekürzt und gesagt, woher
//! die Treffer kommen. Das Gateway spricht dabei **nur** die eingetragenen
//! Suchquellen an — nie eine Adresse, die das Modell vorgegeben hat (5n).
//!
//! Quellen, in dieser Reihenfolge (smilez, 12.11.2026: kostenlos zuerst):
//! 1. `searxng` — eigene Instanz, Adresse in `wahl.json`
//!    (`/search?q=…&format=json`; die Instanz muss `json` in
//!    `search.formats` führen, sonst 403).
//! 2. `ollama` — `https://ollama.com/api/web_search` mit `OLLAMA_API_KEY`
//!    (Free-Konto, Limits nicht dokumentiert; 429 wird gemeldet).
//!
//! Keine Quelle eingetragen ist **kein Fehler des Programms**, sondern eine
//! Auskunft: `keine_quelle` mit Klartext. Treffer werden nie auf Platte
//! gelegt (5r, wegen der AGB der Schlüssel-Quellen) und vor der Rückgabe
//! gekürzt.

use gemein::zeile::fehlerantwort;
use serde_json::{json, Value};
use std::time::Duration;

/// Zeitgrenze je Suche. Eine Suche soll den Chat nicht minutenlang halten.
pub const FRIST: Duration = Duration::from_secs(20);

/// So viele Treffer nimmt ein Lauf hoechstens (Vorgabe, per Auftrag aenderbar).
pub const TREFFER: u64 = 5;
pub const TREFFER_MAX: u64 = 10;

/// Zeichen je Auszug und insgesamt. Der Verlauf eines kleinen Modells ist
/// knapp; ein Roman aus einer Suchmaschine hilft niemandem.
pub const AUSZUG: usize = 400;
pub const GESAMT: usize = 8_000;

/// Eine Suchquelle, wie sie in `wahl.json` steht.
#[derive(Debug, PartialEq)]
pub enum Quelle {
    Searxng(String),
    Ollama(String),
}

/// Liest die Quellen aus `wahl.json`, in der Reihenfolge ihres Auftretens.
/// Rein. Erwartet `{"suche": {"quellen": ["searxng:http://…", "ollama"]}}`;
/// abweichende oder fehlende Angaben werden übergangen und benannt.
pub fn quellen_aus(wahl: &Value) -> (Vec<Quelle>, Vec<String>) {
    let mut gut = Vec::new();
    let mut msg = Vec::new();
    let eintraege = wahl["suche"]["quellen"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    for e in &eintraege {
        let Some(text) = e.as_str() else {
            msg.push("Suchquelle ist kein Text".to_string());
            continue;
        };
        let (art, rest) = text.split_once(':').unwrap_or((text, ""));
        match art.trim() {
            "searxng" => {
                let adr = rest.trim().trim_end_matches('/');
                if adr.is_empty() {
                    msg.push(format!("searxng ohne Adresse: {text}"));
                } else {
                    gut.push(Quelle::Searxng(adr.to_string()));
                }
            }
            "ollama" => gut.push(Quelle::Ollama(String::new())),
            anderes => msg.push(format!("unbekannte Suchquelle: {anderes}")),
        }
    }
    (gut, msg)
}

fn kuerzen(t: &str, n: usize) -> String {
    if t.chars().count() <= n {
        return t.to_string();
    }
    let k: String = t.chars().take(n.saturating_sub(1)).collect();
    format!("{k}…")
}

/// Treffer einer Quelle in eine einheitliche Form bringen:
/// `[{"titel", "url", "auszug", "quelle"}]`, gekürzt und ohne Leere.
/// Rein — hier wird nichts nachgeladen.
pub fn treffer_normalisieren(roh: &Value, art: &str, max: u64) -> Vec<Value> {
    let liste = roh["results"].as_array().cloned().unwrap_or_default();
    let mut out = Vec::new();
    let mut gesamt = 0usize;
    for r in liste {
        if out.len() as u64 >= max || gesamt >= GESAMT {
            break;
        }
        let url = r["url"].as_str().unwrap_or("").trim();
        let titel = r["title"].as_str().unwrap_or("").trim();
        let auszug = r["content"].as_str().unwrap_or("").trim();
        if url.is_empty() {
            continue;
        }
        let a = kuerzen(auszug, AUSZUG);
        gesamt += a.chars().count() + url.chars().count() + titel.chars().count();
        out.push(json!({
            "titel": kuerzen(titel, 160),
            "url": url,
            "auszug": a,
            "quelle": art,
        }));
    }
    out
}

fn agent(global: Duration) -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_connect(Some(Duration::from_secs(5)))
        .timeout_global(Some(global))
        // Ein HTTP-Status ist eine Antwort, kein Fehler des Aufrufs --
        // 403 (JSON nicht freigeschaltet) und 429 (Limit) sollen lesbar sein.
        .http_status_as_error(false)
        .build()
        .into()
}

/// Eine Anfrage gegen eine feste Adresse. Gibt `(status, koerper)` zurück —
/// der Aufrufer entscheidet, was ein Fehler ist.
fn holen(req: ureq::RequestBuilder<ureq::typestate::WithoutBody>) -> Result<Value, String> {
    let mut r = req
        .header("accept", "application/json")
        .call()
        .map_err(|e| format!("nicht erreichbar: {e}"))?;
    let status = r.status().as_u16();
    if status != 200 {
        return Err(match status {
            403 => "403 -- die Instanz gibt kein JSON heraus (search.formats muss json fuehren)"
                .to_string(),
            429 => "429 -- Limit erreicht, spaeter erneut versuchen".to_string(),
            _ => format!("Antwort {status}"),
        });
    }
    r.body_mut()
        .read_json::<Value>()
        .map_err(|e| format!("Antwort nicht lesbar: {e}"))
}

fn searxng_suchen(adr: &str, frage: &str, max: u64) -> Result<Value, String> {
    let url = format!("{adr}/search");
    holen(
        agent(FRIST)
            .get(&url)
            .query("q", frage)
            .query("format", "json")
            .query("language", "de")
            .query("safesearch", "1"),
    )
    .and_then(|roh| Ok(json!({"results": treffer_normalisieren(&roh, "searxng", max)})))
}

fn ollama_suchen(schluessel: &str, frage: &str, max: u64) -> Result<Value, String> {
    if schluessel.trim().is_empty() {
        return Err("OLLAMA_API_KEY fehlt fuer die Quelle ollama".to_string());
    }
    let fest = "https://ollama.com/api/web_search";
    let mut r = agent(FRIST)
        .post(fest)
        .header("authorization", &format!("Bearer {schluessel}"))
        .header("accept", "application/json")
        .send_json(json!({"query": frage, "max_results": max}))
        .map_err(|e| format!("nicht erreichbar: {e}"))?;
    let status = r.status().as_u16();
    if status != 200 {
        return Err(match status {
            401 | 403 => format!("{status} -- Schluessel abgelehnt"),
            429 => "429 -- Limit erreicht".to_string(),
            _ => format!("Antwort {status}"),
        });
    }
    let roh: Value = r.body_mut().read_json().map_err(|e| format!("Antwort nicht lesbar: {e}"))?;
    Ok(json!({"results": treffer_normalisieren(&roh, "ollama", max)}))
}

/// `op: web_suche`. `a` trägt `frage` (Pflicht), `anzahl` (optional) und
/// `quellen` (optional: ausdrückliche Wahl, sonst aus `wahl.json`).
/// `schluessel` ist `OLLAMA_API_KEY` — leer heißt: die Quelle fehlt.
pub fn op_web_suche(a: &Value, wahl: &Value, schluessel: Option<&str>) -> Value {
    let frage = a["frage"]
        .as_str()
        .map(str::trim)
        .filter(|f| !f.is_empty())
        .unwrap_or("");
    if frage.is_empty() {
        return fehlerantwort("frage_fehlt", "Die Suche braucht ein Feld \"frage\".");
    }
    if frage.chars().count() > 300 {
        return fehlerantwort("frage_zu_lang", "Die Frage ist laenger als 300 Zeichen.");
    }
    let max = a["anzahl"].as_u64().unwrap_or(TREFFER).clamp(1, TREFFER_MAX);
    let (quellen, meldungen) = match a["quellen"].as_array() {
        Some(_) => quellen_aus(&json!({"suche": {"quellen": a["quellen"]}})),
        None => quellen_aus(wahl),
    };
    if quellen.is_empty() {
        return json!({
            "ok": false,
            "fehler": {"code": "keine_quelle", "text":
                "Es ist keine Suchquelle eingetragen. In wahl.json unter suche.quellen, z. B. \"searxng:http://127.0.0.1:8888\"."},
            "meldungen": meldungen,
        });
    }
    let mut gruende: Vec<String> = Vec::new();
    for q in &quellen {
        let r = match q {
            Quelle::Searxng(adr) => searxng_suchen(adr, frage, max),
            Quelle::Ollama(_) => ollama_suchen(schluessel.unwrap_or(""), frage, max),
        };
        match r {
            Ok(v) => {
                let treffer = v["results"].clone();
                let art = match q {
                    Quelle::Searxng(_) => "searxng",
                    Quelle::Ollama(_) => "ollama",
                };
                return json!({
                    "ok": true, "frage": frage, "quelle": art,
                    "treffer": treffer, "meldungen": meldungen,
                });
            }
            Err(g) => gruende.push(format!(
                "{}: {g}",
                match q {
                    Quelle::Searxng(_) => "searxng",
                    Quelle::Ollama(_) => "ollama",
                }
            )),
        }
    }
    json!({
        "ok": false,
        "fehler": {"code": "suche_gescheitert", "text":
            format!("Keine Suchquelle hat geantwortet: {}", gruende.join("; "))},
        "meldungen": meldungen,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quellen_werden_in_ihrer_reihenfolge_gelesen_und_falsches_wird_benannt() {
        let wahl = json!({"suche": {"quellen": [
            "searxng:http://127.0.0.1:8888/",
            "ollama",
            "google",
            "searxng:",
            7,
        ]}});
        let (gut, msg) = quellen_aus(&wahl);
        assert_eq!(
            gut,
            vec![
                Quelle::Searxng("http://127.0.0.1:8888".into()),
                Quelle::Ollama(String::new()),
            ]
        );
        assert_eq!(msg.len(), 3, "{msg:?}");
        let (leer, _) = quellen_aus(&json!({}));
        assert!(leer.is_empty(), "ohne Angabe keine Quelle");
    }

    #[test]
    fn treffer_werden_gekuerzt_gefiltert_und_benannt() {
        let lang = "x".repeat(1000);
        let roh = json!({"results": [
            {"title": "A", "url": "https://a", "content": lang},
            {"title": "ohne url", "content": "y"},
            {"title": "B", "url": "https://b", "content": "kurz"},
        ]});
        let t = treffer_normalisieren(&roh, "searxng", 5);
        assert_eq!(t.len(), 2, "ohne URL faellt raus");
        assert_eq!(t[0]["quelle"], "searxng");
        assert!(t[0]["auszug"].as_str().unwrap().chars().count() <= AUSZUG);
        assert!(t[0]["auszug"].as_str().unwrap().ends_with('…'));
        // Grenze je Lauf wird eingehalten.
        assert_eq!(treffer_normalisieren(&roh, "ollama", 1).len(), 1);
    }

    #[test]
    fn ohne_quelle_ist_die_antwort_eine_auskunft() {
        let a = op_web_suche(&json!({"frage": "was ist ollama"}), &json!({}), None);
        assert_eq!(a["ok"], false);
        assert_eq!(a["fehler"]["code"], "keine_quelle");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("wahl.json"));
    }

    #[test]
    fn frage_fehlt_und_zu_lang_werden_abgelehnt() {
        assert_eq!(op_web_suche(&json!({}), &json!({}), None)["fehler"]["code"], "frage_fehlt");
        assert_eq!(
            op_web_suche(&json!({"frage": "  "}), &json!({}), None)["fehler"]["code"],
            "frage_fehlt"
        );
        let lang = "a".repeat(301);
        assert_eq!(
            op_web_suche(&json!({"frage": lang}), &json!({}), None)["fehler"]["code"],
            "frage_zu_lang"
        );
    }

    #[test]
    fn searxng_liefert_treffer_ueber_den_server() {
        let (b, h) = crate::ollama::tests::server(vec![(
            200,
            r#"{"query":"x","results":[{"title":"Ollama","url":"https://ollama.com","content":"lokal"}]}"#
                .into(),
        )]);
        let wahl = json!({"suche": {"quellen": [format!("searxng:{b}")]}});
        let a = op_web_suche(&json!({"frage": "was ist ollama"}), &wahl, None);
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["quelle"], "searxng");
        assert_eq!(a["treffer"][0]["titel"], "Ollama");
        let gesehen = h.join().unwrap();
        assert!(gesehen[0].starts_with("GET /search?"), "{}", gesehen[0]);
        assert!(gesehen[0].contains("format=json"), "{}", gesehen[0]);
        assert!(gesehen[0].contains("q=was"), "Frage mitgeschickt: {}", gesehen[0]);
    }

    #[test]
    fn ein_403_der_instanz_wird_als_json_problem_benannt() {
        // 403 heisst bei SearXNG: das Format ist nicht freigeschaltet. Ohne
        // diesen Text sucht jemand stundenlang an der falschen Stelle.
        let (b, h) = crate::ollama::tests::server(vec![(403, "{}".into())]);
        let wahl = json!({"suche": {"quellen": [format!("searxng:{b}")]}});
        let a = op_web_suche(&json!({"frage": "x"}), &wahl, None);
        assert_eq!(a["fehler"]["code"], "suche_gescheitert");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("search.formats"), "{a}");
        h.join().unwrap();
    }

    #[test]
    fn faellt_die_erste_quelle_aus_wird_die_naechste_versucht() {
        let (b, h) = crate::ollama::tests::server(vec![(200, r#"{"results":[]}"#.into())]);
        // Erste Quelle ist nicht erreichbar (Port 1), die zweite antwortet.
        let wahl = json!({"suche": {"quellen": ["searxng:http://127.0.0.1:1", format!("searxng:{b}")]}});
        let a = op_web_suche(&json!({"frage": "x"}), &wahl, None);
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["treffer"], json!([]), "leere Trefferliste ist eine gueltige Antwort");
        h.join().unwrap();
    }

    #[test]
    fn ollama_ohne_schluessel_wird_benannt_nicht_versucht() {
        let wahl = json!({"suche": {"quellen": ["ollama"]}});
        let a = op_web_suche(&json!({"frage": "x"}), &wahl, None);
        assert_eq!(a["fehler"]["code"], "suche_gescheitert");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("OLLAMA_API_KEY"));
    }
}
