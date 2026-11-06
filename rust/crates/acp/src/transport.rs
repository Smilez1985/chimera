//! Transportschicht: Der Kern kennt nur einen Bytestrom.
//!
//! Regel „ACP", Punkt 2: Der ACP-Kern spricht JSON-RPC 2.0 mit Zeilenrahmen
//! und kennt **nur einen Bytestrom**. Darunter liegen austauschbare
//! Transporte, jeder ein eigenes Stück Code mit eigenem Test — stdio
//! (Vermittler auf dem Rechner der IDE), Unix-Socket am Gateway, später
//! HTTP/WebSocket. Ein Transport kennt weder Sitzungen noch Rechte.
//!
//! Der eigentliche Zeilenrahmen ist `gemein::zeile` — hier wird nur
//! entschieden, *woher* die Bytes kommen und *wohin* sie gehen.

use std::io::{BufRead, Write};

use serde_json::Value;

use crate::kern::Kern;
use crate::Agent;

/// Ein Strom von JSON-Nachrichten, je eine Zeile.
///
/// Absichtlich klein: `lesen` liefert genau eine Nachricht oder einen Fehler
/// (`gemein::zeile::Fehler::Ende` heisst: das Gegenüber hat geschlossen).
pub trait Strom {
    fn lesen(&mut self) -> Result<Value, gemein::zeile::Fehler>;
    fn schreiben(&mut self, wert: &Value) -> Result<(), gemein::zeile::Fehler>;
}

/// Der Standardfall: stdin/stdout. Genau das, was eine IDE erwartet, wenn sie
/// einen Agenten als Prozess startet.
pub struct Stdio<R: BufRead, W: Write> {
    leser: R,
    schreiber: W,
}

impl<R: BufRead, W: Write> Stdio<R, W> {
    pub fn neu(leser: R, schreiber: W) -> Stdio<R, W> {
        Stdio { leser, schreiber }
    }
}

impl<R: BufRead, W: Write> Strom for Stdio<R, W> {
    fn lesen(&mut self) -> Result<Value, gemein::zeile::Fehler> {
        gemein::zeile::lesen(&mut self.leser, gemein::zeile::MAX_BYTES)
    }

    fn schreiben(&mut self, wert: &Value) -> Result<(), gemein::zeile::Fehler> {
        gemein::zeile::schreiben(&mut self.schreiber, wert)
    }
}

/// Wie eine Sitzung endet.
#[derive(Debug, PartialEq)]
pub enum Ende {
    /// Das Gegenüber hat die Verbindung geschlossen (der Normalfall).
    VerbindungZu,
    /// Ein Fehler im Strom: zu lange Zeile, kaputtes JSON, E/A.
    Fehler(String),
}

/// Den Kern an einen Strom hängen, bis der Strom endet.
///
/// Jede Anfrage bekommt ihre Antwort, jede Meldung des Agenten geht sofort
/// danach raus. Ein Fehler in **einer** Zeile beendet die Verbindung nicht:
/// Der Kern antwortet mit einem Fehler und macht weiter — sonst reißt ein
/// einziger Tippfehler des Clients die ganze Sitzung ab.
pub fn bedienen<A: Agent, S: Strom>(kern: &mut Kern<A>, strom: &mut S) -> Ende {
    loop {
        let wert = match strom.lesen() {
            Ok(v) => v,
            Err(gemein::zeile::Fehler::Ende) => return Ende::VerbindungZu,
            Err(gemein::zeile::Fehler::KeinObjekt(grund)) => {
                // Kein JSON: das ist ein Fehler *einer* Zeile, kein Ende.
                // Der Client bekommt die Antwort nach JSON-RPC 2.0 und darf
                // weitermachen.
                let f = crate::rpc::Fehler::neu(crate::rpc::code::PARSE, format!("kein JSON: {grund}"));
                let antwort = crate::rpc::fehlerantwort(&Value::Null, &f);
                if let Err(e) = strom.schreiben(&antwort) {
                    return Ende::Fehler(e.to_string());
                }
                continue;
            }
            Err(e) => return Ende::Fehler(e.to_string()),
        };

        let mut meldungen: Vec<Value> = Vec::new();
        // Der Bericht sammelt in einen Puffer, statt direkt in den Strom zu
        // schreiben: Kern und Strom waeren sonst gleichzeitig ausgeliehen.
        // Fuer den Mindestumfang reicht das (eine Antwort, danach ihre
        // Meldungen); echtes Streaming waehrend eines Zuges bekommt eine
        // eigene Form, wenn `session/prompt` wirklich streamt.
        let antwort = kern.bediene(&wert, &mut |m| meldungen.push(m));
        for m in &meldungen {
            if let Err(e) = strom.schreiben(m) {
                return Ende::Fehler(e.to_string());
            }
        }
        if let Some(a) = antwort {
            if let Err(e) = strom.schreiben(&a) {
                return Ende::Fehler(e.to_string());
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rpc;
    use std::io::Cursor;

    /// Ein Agent, der nur `initialize` beantwortet und einen Zug mit einer
    /// Aktualisierung fuehrt.
    struct Attrappe;

    impl Agent for Attrappe {
        fn initialisieren(&mut self, _params: &Value) -> Result<Value, rpc::Fehler> {
            Ok(crate::faehigkeiten())
        }
        fn neue_sitzung(&mut self, _params: &Value) -> Result<String, rpc::Fehler> {
            Ok("s1".into())
        }
        fn zusage(
            &mut self,
            sitzung: &str,
            _text: &str,
            bericht: &mut dyn FnMut(Value),
        ) -> Result<String, rpc::Fehler> {
            bericht(rpc::meldung(
                "session/update",
                serde_json::json!({ "sessionId": sitzung, "update": { "sessionUpdate": "agent_message_chunk" } }),
            ));
            Ok("end_turn".into())
        }
    }

    /// Ein Strom aus einer festen Eingabe; die Ausgabe sammelt in `Vec<u8>`.
    fn strom(eingabe: &str) -> Stdio<Cursor<Vec<u8>>, Vec<u8>> {
        Stdio::neu(Cursor::new(eingabe.as_bytes().to_vec()), Vec::new())
    }

    fn ausgaben(s: &Stdio<Cursor<Vec<u8>>, Vec<u8>>) -> Vec<Value> {
        String::from_utf8_lossy(&s.schreiber)
            .lines()
            .map(|z| serde_json::from_str(z).unwrap())
            .collect()
    }

    #[test]
    fn drei_anfragen_drei_antworten() {
        let mut s = strom(concat!(
            r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}"#,
            "\n",
            r#"{"jsonrpc":"2.0","id":2,"method":"session/new","params":{}}"#,
            "\n",
            r#"{"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":"s1","prompt":[{"type":"text","text":"hi"}]}}"#,
            "\n"
        ));
        let mut k = Kern::neu(Attrappe);
        assert_eq!(bedienen(&mut k, &mut s), Ende::VerbindungZu);
        let a = ausgaben(&s);
        assert_eq!(a.len(), 4, "drei Antworten und eine Aktualisierung: {a:?}");
        assert_eq!(a[0]["id"], serde_json::json!(1));
        assert_eq!(a[1]["result"]["sessionId"], serde_json::json!("s1"));
        // Die Meldung kommt VOR der Antwort des Zuges -- sonst saehe der
        // Client die Aktualisierung erst nach dem Ende.
        assert_eq!(a[2]["method"], serde_json::json!("session/update"));
        assert_eq!(a[3]["result"]["stopReason"], serde_json::json!("end_turn"));
    }

    // Eine kaputte Zeile beendet die Sitzung NICHT: Der Client bekommt einen
    // Fehler und die naechste Anfrage wird noch beantwortet.
    #[test]
    fn kaputte_zeile_beendet_die_verbindung_nicht() {
        let mut s = strom(concat!(
            "das ist kein json\n",
            r#"{"jsonrpc":"2.0","id":5,"method":"initialize","params":{}}"#,
            "\n"
        ));
        let mut k = Kern::neu(Attrappe);
        assert_eq!(bedienen(&mut k, &mut s), Ende::VerbindungZu);
        let a = ausgaben(&s);
        assert_eq!(a.len(), 2);
        assert_eq!(a[0]["error"]["code"], serde_json::json!(rpc::code::PARSE));
        assert_eq!(a[1]["id"], serde_json::json!(5));
    }

    #[test]
    fn leere_eingabe_endet_ohne_ausgabe() {
        let mut s = strom("");
        let mut k = Kern::neu(Attrappe);
        assert_eq!(bedienen(&mut k, &mut s), Ende::VerbindungZu);
        assert!(ausgaben(&s).is_empty());
    }

    // Eine Meldung bekommt keine Antwort -- weder vorher noch nachher.
    #[test]
    fn meldung_ohne_id_erzeugt_keine_ausgabe() {
        let mut s = strom(concat!(
            r#"{"jsonrpc":"2.0","method":"session/cancel","params":{"sessionId":"s1"}}"#,
            "\n"
        ));
        let mut k = Kern::neu(Attrappe);
        bedienen(&mut k, &mut s);
        assert!(ausgaben(&s).is_empty());
    }

    // Jede Ausgabe ist genau eine Zeile -- auch wenn der Text im Prompt einen
    // Zeilenumbruch enthaelt.
    #[test]
    fn ausgabe_ist_eine_zeile_je_nachricht() {
        let mut s = strom(concat!(
            r#"{"jsonrpc":"2.0","id":1,"method":"session/prompt","params":{"sessionId":"s1","prompt":[{"type":"text","text":"zeile1\nzeile2"}]}}"#,
            "\n"
        ));
        let mut k = Kern::neu(Attrappe);
        bedienen(&mut k, &mut s);
        let roh = String::from_utf8_lossy(&s.schreiber).to_string();
        assert_eq!(roh.lines().count(), 2, "Meldung und Antwort, je eine Zeile");
        assert!(roh.ends_with('\n'));
    }
}
