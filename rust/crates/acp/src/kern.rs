//! Der ACP-Kern: Methoden, Parameterprüfung, Antwortformen.
//!
//! Der Kern kennt **drei** Dinge: die Methodennamen, welche Parameter sie
//! brauchen und wie eine Antwort aussieht. Was ein Prompt *inhaltlich* tut,
//! entscheidet der [`Agent`] — hier ist er eine Attrappe, im Betrieb die
//! Hauptsitzung (Regel „ACP", Punkt 1: ein Zug ist ein Turn in der
//! Hauptsitzung, kein zweiter Verlauf).

use serde_json::{json, Value};

use crate::rpc::{self, Fehler, Nachricht};

/// Die ACP-Protokollversion, die wir sprechen.
pub const PROTOKOLL_VERSION: u32 = 1;

/// Was Chimera kann — und was nicht. `initialize` meldet das ehrlich;
/// Fähigkeiten, die hier fehlen, sind nicht vorhanden (Regel „ACP", Punkt 5).
pub fn faehigkeiten() -> Value {
    json!({
        "protocolVersion": PROTOKOLL_VERSION,
        "agentCapabilities": {
            // Keine Sitzung wird aus einer alten geladen: es gibt eine
            // Hauptsitzung, keinen Verlauf je IDE.
            "loadSession": false,
            "promptCapabilities": { "image": false, "audio": false, "embeddedContext": false },
            "mcpCapabilities": { "http": false, "sse": false },
            "sessionCapabilities": {}
        },
        // Keine Anmeldung ueber ACP: Die Tuer liegt am Gateway und prueft vor
        // dem ersten Prompt (Regel „ACP", Punkt 4).
        "authMethods": []
    })
}

/// Der Agent hinter dem Kern.
///
/// Jede Methode bekommt die `params` so, wie sie kamen, und gibt das
/// `result` zurück — oder einen [`Fehler`], den der Kern als Fehlerantwort
/// ausgibt. Der Kern prüft vorher, was **jede** Implementierung braucht
/// (Sitzungs-ID, nicht-leerer Prompt) und lässt den Agenten nur das
/// entscheiden, was er allein wissen kann.
pub trait Agent {
    /// `initialize`: Fähigkeiten und Protokollversion aushandeln.
    fn initialisieren(&mut self, params: &Value) -> Result<Value, Fehler>;
    /// `session/new`: eine Sitzung anlegen; Ergebnis ist die Sitzungs-ID.
    fn neue_sitzung(&mut self, params: &Value) -> Result<String, Fehler>;
    /// `session/prompt`: einen Zug fahren. `bericht` schickt
    /// `session/update`-Meldungen an den Client; der Rückgabewert ist der
    /// `stopReason`.
    fn zusage(&mut self, sitzung: &str, text: &str, bericht: &mut dyn FnMut(Value))
        -> Result<String, Fehler>;
    /// `session/cancel`: den laufenden Zug beenden. Keine Antwort (Meldung).
    /// Der Vorgabewert tut nichts — ein Agent ohne Züge braucht ihn nicht.
    fn abbrechen(&mut self, _sitzung: &str) {}
}

/// Was der Kern aus einer Zeile macht.
#[derive(Debug, PartialEq)]
pub enum Ausgang {
    /// Eine Antwort, die zurück auf die Leitung geht.
    Antwort(Value),
    /// Eine Meldung (Notification): keine Antwort.
    Nichts,
}

pub struct Kern<A: Agent> {
    agent: A,
}

impl<A: Agent> Kern<A> {
    pub fn neu(agent: A) -> Kern<A> {
        Kern { agent }
    }

    pub fn agent(&self) -> &A {
        &self.agent
    }

    pub fn agent_mut(&mut self) -> &mut A {
        &mut self.agent
    }

    /// Eine gelesene Zeile verarbeiten. `None`, wenn keine Antwort fällig ist.
    ///
    /// Fehler werden zu Fehlerantworten, **nicht** zu einem Abbruch: Ein
    /// Client, der eine unbekannte Methode schickt, soll eine Antwort
    /// bekommen und weitermachen können.
    pub fn bediene(&mut self, wert: &Value, bericht: &mut dyn FnMut(Value)) -> Option<Value> {
        let nachricht = match rpc::deuten(wert) {
            Ok(n) => n,
            // Ohne lesbare id gilt `id: null` (JSON-RPC 2.0, Abschnitt 5).
            Err(f) => return Some(rpc::fehlerantwort(&Value::Null, &f)),
        };
        match nachricht {
            Nachricht::Antwort { .. } => None,
            Nachricht::Meldung { methode, params } => {
                self.meldung(&methode, &params);
                None
            }
            Nachricht::Anfrage { id, methode, params } => {
                let ergebnis = self.anfrage(&methode, &params, bericht);
                Some(match ergebnis {
                    Ok(v) => rpc::antwort(&id, v),
                    Err(f) => rpc::fehlerantwort(&id, &f),
                })
            }
        }
    }

    fn anfrage(
        &mut self,
        methode: &str,
        params: &Value,
        bericht: &mut dyn FnMut(Value),
    ) -> Result<Value, Fehler> {
        match methode {
            "initialize" => self.agent.initialisieren(params),
            "session/new" => {
                let id = self.agent.neue_sitzung(params)?;
                Ok(json!({ "sessionId": id }))
            }
            "session/prompt" => {
                let sitzung = sitzung_aus(params)?;
                let text = prompt_text(params)?;
                let stop = self.agent.zusage(&sitzung, &text, bericht)?;
                Ok(json!({ "stopReason": stop }))
            }
            other => Err(Fehler::unbekannte_methode(other)),
        }
    }

    fn meldung(&mut self, methode: &str, params: &Value) {
        // `session/cancel` ist die einzige Meldung, die der Kern kennt; alles
        // andere ist unbekannt und wird still verworfen -- eine Meldung hat
        // keine Antwort, in der man sich beschweren koennte.
        if methode == "session/cancel" {
            if let Some(sitzung) = params.get("sessionId").and_then(Value::as_str) {
                self.agent.abbrechen(sitzung);
            }
        }
    }
}

fn sitzung_aus(params: &Value) -> Result<String, Fehler> {
    params
        .get("sessionId")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
        .map(String::from)
        .ok_or_else(|| Fehler::parameter("sessionId fehlt oder ist leer"))
}

/// Der Text eines Zuges: ACP schickt `prompt` als Liste von Bloecken, jeder
/// mit `type`. Nur `text` kann Chimera heute verarbeiten; alles andere wird
/// abgelehnt, statt es still zu schlucken (Regel „Was ein anderer Agent
/// schreibt, ist Eingabe").
fn prompt_text(params: &Value) -> Result<String, Fehler> {
    let bloecke = params
        .get("prompt")
        .and_then(Value::as_array)
        .ok_or_else(|| Fehler::parameter("prompt fehlt oder ist keine Liste"))?;
    let mut text = String::new();
    for block in bloecke {
        match block.get("type").and_then(Value::as_str) {
            Some("text") => {
                let t = block
                    .get("text")
                    .and_then(Value::as_str)
                    .ok_or_else(|| Fehler::parameter("Textblock ohne text"))?;
                if !text.is_empty() {
                    text.push('\n');
                }
                text.push_str(t);
            }
            Some(andere) => {
                return Err(Fehler::parameter(format!(
                    "Blocktyp '{andere}' wird nicht unterstuetzt (nur 'text')"
                )))
            }
            None => return Err(Fehler::parameter("Block ohne type")),
        }
    }
    if text.trim().is_empty() {
        return Err(Fehler::parameter("prompt ist leer"));
    }
    Ok(text)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Ein Agent, der nichts tut ausser zu antworten -- damit der Kern
    /// pruefbar ist, ohne dass eine Hauptsitzung laeuft.
    #[derive(Default)]
    struct Attrappe {
        zuege: Vec<String>,
        abgebrochen: Option<String>,
    }

    impl Agent for Attrappe {
        fn initialisieren(&mut self, _params: &Value) -> Result<Value, Fehler> {
            Ok(faehigkeiten())
        }
        fn neue_sitzung(&mut self, _params: &Value) -> Result<String, Fehler> {
            Ok("sitzung-1".into())
        }
        fn zusage(
            &mut self,
            sitzung: &str,
            text: &str,
            bericht: &mut dyn FnMut(Value),
        ) -> Result<String, Fehler> {
            self.zuege.push(format!("{sitzung}:{text}"));
            bericht(rpc::meldung(
                "session/update",
                json!({ "sessionId": sitzung, "update": { "sessionUpdate": "agent_message_chunk",
                          "content": { "type": "text", "text": "hallo" } } }),
            ));
            Ok("end_turn".into())
        }
        fn abbrechen(&mut self, sitzung: &str) {
            self.abgebrochen = Some(sitzung.to_string());
        }
    }

    fn kern() -> Kern<Attrappe> {
        Kern::neu(Attrappe::default())
    }

    fn frage(k: &mut Kern<Attrappe>, text: &str) -> Value {
        let wert: Value = serde_json::from_str(text).unwrap();
        k.bediene(&wert, &mut |_| {}).expect("Antwort erwartet")
    }

    #[test]
    fn initialize_liefert_version_und_faehigkeiten() {
        let mut k = kern();
        let a = frage(&mut k, r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}"#);
        assert_eq!(a["id"], json!(1));
        assert_eq!(a["result"]["protocolVersion"], json!(PROTOKOLL_VERSION));
        // Ehrlichkeit: was nicht da ist, steht nicht drin.
        assert_eq!(a["result"]["agentCapabilities"]["loadSession"], json!(false));
    }

    #[test]
    fn neue_sitzung_gibt_eine_id() {
        let mut k = kern();
        let a = frage(
            &mut k,
            r#"{"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/","mcpServers":[]}}"#,
        );
        assert_eq!(a["result"]["sessionId"], json!("sitzung-1"));
    }

    #[test]
    fn prompt_liefert_stop_reason() {
        let mut k = kern();
        let a = frage(
            &mut k,
            r#"{"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":"s1","prompt":[{"type":"text","text":"hallo"}]}}"#,
        );
        assert_eq!(a["result"]["stopReason"], json!("end_turn"));
        assert_eq!(k.agent().zuege, vec!["s1:hallo".to_string()]);
    }

    // Der Bericht geht als Meldung raus, nicht als Antwort -- sonst waere ein
    // Strom aus Aktualisierungen nicht zu unterscheiden von der Antwort.
    #[test]
    fn aktualisierungen_gehen_als_meldung_raus() {
        let mut k = kern();
        let mut gesammelt: Vec<Value> = Vec::new();
        let wert: Value = serde_json::from_str(
            r#"{"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":"s1","prompt":[{"type":"text","text":"hallo"}]}}"#,
        )
        .unwrap();
        let a = k.bediene(&wert, &mut |v| gesammelt.push(v)).unwrap();
        assert_eq!(gesammelt.len(), 1);
        assert_eq!(gesammelt[0]["method"], json!("session/update"));
        assert!(gesammelt[0].get("id").is_none(), "eine Meldung hat keine id");
        assert_eq!(a["result"]["stopReason"], json!("end_turn"));
    }

    #[test]
    fn cancel_ist_eine_meldung_ohne_antwort() {
        let mut k = kern();
        let wert: Value = serde_json::from_str(
            r#"{"jsonrpc":"2.0","method":"session/cancel","params":{"sessionId":"s1"}}"#,
        )
        .unwrap();
        assert_eq!(k.bediene(&wert, &mut |_| {}), None, "Meldung bekommt keine Antwort");
        assert_eq!(k.agent().abgebrochen.as_deref(), Some("s1"));
    }

    // Fehler sind Antworten, kein Abbruch: Ein Client mit einem Tippfehler
    // soll weiterreden koennen.
    #[test]
    fn unbekannte_methode_ist_eine_fehlerantwort() {
        let mut k = kern();
        let a = frage(&mut k, r#"{"jsonrpc":"2.0","id":4,"method":"gibtsnicht","params":{}}"#);
        assert_eq!(a["error"]["code"], json!(rpc::code::UNBEKANNTE_METHODE));
        assert_eq!(a["id"], json!(4));
    }

    #[test]
    fn kaputte_nachricht_bekommt_id_null() {
        let mut k = kern();
        let a = frage(&mut k, r#"{"jsonrpc":"2.0","id":5}"#);
        assert_eq!(a["id"], Value::Null);
        assert_eq!(a["error"]["code"], json!(rpc::code::UNGUELTIGE_ANFRAGE));
    }

    #[test]
    fn prompt_ohne_sitzung_wird_abgelehnt() {
        let mut k = kern();
        let a = frage(
            &mut k,
            r#"{"jsonrpc":"2.0","id":6,"method":"session/prompt","params":{"prompt":[{"type":"text","text":"x"}]}}"#,
        );
        assert_eq!(a["error"]["code"], json!(rpc::code::UNGUELTIGE_PARAMETER));
        assert!(a["error"]["message"].as_str().unwrap().contains("sessionId"));
    }

    // Ein Bildblock wird abgelehnt, nicht stillschweigend ignoriert: Wer ein
    // Bild schickt, soll wissen, dass es nicht ankommt.
    #[test]
    fn fremder_blocktyp_wird_abgelehnt() {
        let mut k = kern();
        let a = frage(
            &mut k,
            r#"{"jsonrpc":"2.0","id":7,"method":"session/prompt","params":{"sessionId":"s1","prompt":[{"type":"image","data":"x"}]}}"#,
        );
        assert_eq!(a["error"]["code"], json!(rpc::code::UNGUELTIGE_PARAMETER));
        assert!(a["error"]["message"].as_str().unwrap().contains("image"));
    }

    #[test]
    fn leerer_prompt_wird_abgelehnt() {
        let mut k = kern();
        let a = frage(
            &mut k,
            r#"{"jsonrpc":"2.0","id":8,"method":"session/prompt","params":{"sessionId":"s1","prompt":[{"type":"text","text":"   "}]}}"#,
        );
        assert_eq!(a["error"]["code"], json!(rpc::code::UNGUELTIGE_PARAMETER));
    }

    // Mehrere Textbloecke werden mit Zeilenumbruch verbunden, nicht
    // zusammengeklebt -- sonst verschmelzen zwei Saetze ohne Trennung.
    #[test]
    fn mehrere_textbloecke_bleiben_getrennt() {
        let mut k = kern();
        frage(
            &mut k,
            r#"{"jsonrpc":"2.0","id":9,"method":"session/prompt","params":{"sessionId":"s1","prompt":[{"type":"text","text":"eins"},{"type":"text","text":"zwei"}]}}"#,
        );
        assert_eq!(k.agent().zuege, vec!["s1:eins\nzwei".to_string()]);
    }
}
