//! JSON-RPC 2.0 mit Zeilenrahmen — der ACP-Kern (DESIGN, Regel „ACP").
//!
//! Bewusst klein und **ohne Laufzeit**: Die Messung vom 6.11.2026
//! (`docs/messungen/2026-11-06-acp-bibliothek.md`) hat gezeigt, dass die
//! fertige Crate `agent-client-protocol` für dieselbe Arbeit das Vier- bis
//! Dreizehnfache an Platz, Speicher und Zeit kostet — und `tokio` in ein
//! Gateway brächte, das ohne Laufzeit läuft. Gebaut wird deshalb der
//! Mindestumfang, den die Regel nennt: `initialize`, `session/new`,
//! `session/prompt`, `session/update`, `session/cancel`.
//!
//! Was hier **nicht** steht, absichtlich:
//! - kein zweiter Zeilenrahmen — Lesen und Schreiben kommen aus
//!   [`gemein::zeile`], samt Längengrenze (Regel 5n/10g);
//! - keine Warteschlange und keine Fäden — der Kern ist synchron; wer ihn
//!   nebenläufig braucht, ruft ihn aus seinem eigenen Faden auf;
//! - keine Kenntnis von Sitzungen, Rechten oder Transporten. Das ist Sache
//!   des Aufrufers (Regel „ACP", Punkt 2 und 3).

use serde_json::{json, Value};

/// Die Fehlercodes aus JSON-RPC 2.0 plus die ACP-eigenen.
pub mod code {
    pub const PARSE: i64 = -32700;
    pub const UNGUELTIGE_ANFRAGE: i64 = -32600;
    pub const UNBEKANNTE_METHODE: i64 = -32601;
    pub const UNGUELTIGE_PARAMETER: i64 = -32602;
    pub const INTERNER_FEHLER: i64 = -32603;
    /// ACP: Die Methode ist bekannt, aber im Moment nicht erlaubt (z. B. ein
    /// zweiter Prompt, während einer läuft, oder eine unbekannte Sitzung).
    pub const NICHT_ERLAUBT: i64 = -32000;
}

/// Ein JSON-RPC-Fehler, so wie er auf die Leitung geht.
#[derive(Clone, Debug, PartialEq)]
pub struct Fehler {
    pub code: i64,
    pub text: String,
    pub daten: Option<Value>,
}

impl Fehler {
    pub fn neu(code: i64, text: impl Into<String>) -> Fehler {
        Fehler { code, text: text.into(), daten: None }
    }

    pub fn parameter(text: impl Into<String>) -> Fehler {
        Fehler::neu(code::UNGUELTIGE_PARAMETER, text)
    }

    pub fn unbekannte_methode(methode: &str) -> Fehler {
        Fehler::neu(code::UNBEKANNTE_METHODE, format!("unbekannte Methode: {methode}"))
    }

    pub fn als_json(&self) -> Value {
        let mut fehler = json!({ "code": self.code, "message": self.text });
        if let Some(d) = &self.daten {
            fehler["data"] = d.clone();
        }
        fehler
    }
}

/// Was von der Leitung kommen darf.
#[derive(Clone, Debug, PartialEq)]
pub enum Nachricht {
    /// Eine Anfrage: hat eine `id` und erwartet genau eine Antwort.
    Anfrage { id: Value, methode: String, params: Value },
    /// Eine Meldung (Notification): keine `id`, keine Antwort.
    Meldung { methode: String, params: Value },
    /// Die Antwort des Gegenübers auf eine eigene Anfrage.
    Antwort { id: Value, ergebnis: Result<Value, Fehler> },
}

/// Eine eingelesene Zeile deuten.
///
/// Alles, was nicht passt, ist `UNGUELTIGE_ANFRAGE` — die Meldung nennt den
/// Grund, damit ein Client nicht raten muss. Eine Anfrage **ohne** `id` ist
/// keine Anfrage, sondern eine Meldung (JSON-RPC 2.0); `id: null` dagegen
/// ist eine Anfrage mit der id `null` und wird beantwortet.
pub fn deuten(wert: &Value) -> Result<Nachricht, Fehler> {
    if !wert.is_object() {
        return Err(Fehler::neu(code::UNGUELTIGE_ANFRAGE, "Nachricht ist kein Objekt"));
    }
    if wert.get("jsonrpc").and_then(Value::as_str) != Some("2.0") {
        return Err(Fehler::neu(code::UNGUELTIGE_ANFRAGE, "jsonrpc muss \"2.0\" sein"));
    }
    let id_vorhanden = wert.get("id").is_some();

    if let Some(methode) = wert.get("method").and_then(Value::as_str) {
        let params = wert.get("params").cloned().unwrap_or(Value::Null);
        if !params.is_null() && !params.is_object() && !params.is_array() {
            return Err(Fehler::neu(
                code::UNGUELTIGE_ANFRAGE,
                "params muss Objekt, Feld oder fehlen",
            ));
        }
        return Ok(if id_vorhanden {
            Nachricht::Anfrage {
                id: wert.get("id").cloned().unwrap_or(Value::Null),
                methode: methode.to_string(),
                params,
            }
        } else {
            Nachricht::Meldung { methode: methode.to_string(), params }
        });
    }

    // Keine Methode: entweder eine Antwort (result oder error) oder Unsinn.
    if !id_vorhanden {
        return Err(Fehler::neu(code::UNGUELTIGE_ANFRAGE, "weder method noch id"));
    }
    let id = wert.get("id").cloned().unwrap_or(Value::Null);
    if let Some(fehler) = wert.get("error") {
        let code = fehler.get("code").and_then(Value::as_i64).unwrap_or(code::INTERNER_FEHLER);
        let text = fehler
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("Fehler ohne Text")
            .to_string();
        let daten = fehler.get("data").cloned();
        return Ok(Nachricht::Antwort { id, ergebnis: Err(Fehler { code, text, daten }) });
    }
    match wert.get("result") {
        Some(r) => Ok(Nachricht::Antwort { id, ergebnis: Ok(r.clone()) }),
        None => Err(Fehler::neu(code::UNGUELTIGE_ANFRAGE, "weder result noch error")),
    }
}

/// Die Antwort auf eine Anfrage.
pub fn antwort(id: &Value, ergebnis: Value) -> Value {
    json!({ "jsonrpc": "2.0", "id": id, "result": ergebnis })
}

/// Die Fehlerantwort auf eine Anfrage. `id` ist `null`, wenn die Anfrage
/// selbst nicht lesbar war (JSON-RPC 2.0, Abschnitt 5).
pub fn fehlerantwort(id: &Value, fehler: &Fehler) -> Value {
    json!({ "jsonrpc": "2.0", "id": id, "error": fehler.als_json() })
}

/// Eine Meldung (Notification) an den Client — ohne `id`, ohne Antwort.
pub fn meldung(methode: &str, params: Value) -> Value {
    json!({ "jsonrpc": "2.0", "method": methode, "params": params })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(text: &str) -> Value {
        serde_json::from_str(text).unwrap()
    }

    #[test]
    fn anfrage_mit_id_wird_erkannt() {
        let n = deuten(&parse(r#"{"jsonrpc":"2.0","id":7,"method":"initialize","params":{}}"#))
            .unwrap();
        assert_eq!(
            n,
            Nachricht::Anfrage {
                id: json!(7),
                methode: "initialize".into(),
                params: json!({}),
            }
        );
    }

    // Ohne id ist es eine Meldung -- und Meldungen bekommen keine Antwort
    // (JSON-RPC 2.0). Das ist der Unterschied, an dem sich `session/cancel`
    // und `session/update` entscheiden.
    #[test]
    fn ohne_id_ist_es_eine_meldung() {
        let n = deuten(&parse(r#"{"jsonrpc":"2.0","method":"session/cancel","params":{}}"#)).unwrap();
        assert!(matches!(n, Nachricht::Meldung { .. }));
    }

    // id:null ist eine echte id und wird beantwortet -- nicht mit "Meldung"
    // verwechseln, sonst geht eine Antwort verloren.
    #[test]
    fn id_null_ist_eine_anfrage() {
        let n = deuten(&parse(r#"{"jsonrpc":"2.0","id":null,"method":"initialize"}"#)).unwrap();
        assert!(matches!(n, Nachricht::Anfrage { .. }));
    }

    #[test]
    fn antworten_werden_erkannt() {
        let ok = deuten(&parse(r#"{"jsonrpc":"2.0","id":1,"result":{"a":1}}"#)).unwrap();
        assert!(matches!(ok, Nachricht::Antwort { ergebnis: Ok(_), .. }));
        let fehler = deuten(
            &parse(r#"{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"nein"}}"#),
        )
        .unwrap();
        match fehler {
            Nachricht::Antwort { ergebnis: Err(f), .. } => {
                assert_eq!(f.code, code::UNBEKANNTE_METHODE);
                assert_eq!(f.text, "nein");
            }
            andere => panic!("erwartet Antwort, bekam {andere:?}"),
        }
    }

    // Jede kaputte Zeile nennt einen Grund -- und den Code, den ein Client
    // erwartet. Ein stilles Verwerfen waere der schlimmere Fehler.
    #[test]
    fn kaputte_nachrichten_werden_benannt() {
        for (text, erwartet) in [
            (r#"[1,2,3]"#, "kein Objekt"),
            (r#"{"id":1,"method":"x"}"#, "jsonrpc"),
            (r#"{"jsonrpc":"2.0","id":1}"#, "weder result noch error"),
            (r#"{"jsonrpc":"2.0","method":"x","params":5}"#, "params"),
        ] {
            let f = deuten(&parse(text)).unwrap_err();
            assert_eq!(f.code, code::UNGUELTIGE_ANFRAGE, "{text}");
            assert!(f.text.contains(erwartet), "{text}: {}", f.text);
        }
    }

    #[test]
    fn fehlerantwort_traegt_code_und_text() {
        let v = fehlerantwort(&json!(3), &Fehler::unbekannte_methode("gibtsnicht"));
        assert_eq!(v["id"], json!(3));
        assert_eq!(v["error"]["code"], json!(-32601));
        assert!(v["error"]["message"].as_str().unwrap().contains("gibtsnicht"));
        assert!(v.get("result").is_none(), "eine Fehlerantwort hat kein result");
    }
}
