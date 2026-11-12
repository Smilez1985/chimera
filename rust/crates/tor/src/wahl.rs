//! Die Wahl des Gateways (`config/wahl/wahl.json`) fuer alle Tueren.
//!
//! Der eine Ort, an dem ein Feld geaendert wird, ist `daten::wahl_feld_setzen`
//! -- hier stehen nur die Namen, die Telegram, Web und CLI benutzen. Damit gibt
//! es keine zweite Fassung von "lesen, aendern, schreiben", die auseinander-
//! laufen koennte (DESIGN, Regel "Aufrufe, nicht Text": ein Feld, ein Ort).
//!
//! `stream` ist eine Eigenschaft des Gateways, nicht eines Chats: Wer ihn hier
//! umstellt, stellt ihn fuer alle Tueren um.

use crate::dienst::{antworten, Stand};
use serde_json::{json, Value};

/// Die Wahl, wie sie auf der Platte steht. `Err` nennt den Grund (kaputte
/// Datei) -- ein stiller Rueckfall auf "leer" wuerde die Datei beim naechsten
/// Schreiben ueberschreiben.
pub fn lesen(stand: &Stand) -> Result<Value, String> {
    let a = antworten(&json!({"op": "wahl_lesen"}), stand);
    if a["ok"] == true {
        Ok(a["wahl"].clone())
    } else {
        Err(a["fehler"]["text"].as_str().unwrap_or("ohne Grund").to_string())
    }
}

/// Sind die Teilstuecke (Strom) an? Ohne lesbare Wahl: aus (Ollama-Vorgabe ist
/// an, aber eine kaputte Datei ist kein Grund, sie zu erraten).
pub fn strom_an(stand: &Stand) -> bool {
    lesen(stand).ok().and_then(|w| w["stream"].as_bool()).unwrap_or(false)
}

/// Teilstuecke an oder aus.
pub fn strom_setzen(stand: &Stand, an: bool) -> Result<(), String> {
    feld_setzen(stand, "stream", json!(an)).map(|_| ())
}

/// Die Kette (Reihenfolge der Verweise) setzen -- die Oberflaeche schickt die
/// ganze Liste, sortiert oder gekuerzt. Geprueft wird im Dienst
/// (`daten::feld_wert_pruefen`), nicht hier: ein Ort fuer die Regel.
pub fn reihenfolge_setzen(stand: &Stand, reihenfolge: &[String]) -> Result<(), String> {
    feld_setzen(stand, "reihenfolge", json!(reihenfolge)).map(|_| ())
}

/// Ein Feld setzen und die Antwort des Dienstes in ein `Result` uebersetzen.
fn feld_setzen(stand: &Stand, feld: &str, wert: Value) -> Result<Value, String> {
    let a = antworten(&json!({"op": "wahl_feld_setzen", "feld": feld, "wert": wert}), stand);
    if a["ok"] == true {
        Ok(a["wert"].clone())
    } else {
        Err(a["fehler"]["text"].as_str().unwrap_or("ohne Grund").to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stand(name: &str) -> Stand {
        let d = std::env::temp_dir().join(format!("chimera-wahl-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        Stand::mit(None, crate::daten::Pfade::neu(d.join("config"), d.join("state")))
    }

    #[test]
    fn strom_ist_aus_ohne_wahl() {
        let s = stand("leer");
        assert!(!strom_an(&s));
    }

    #[test]
    fn strom_setzen_und_wieder_lesen() {
        let s = stand("setzen");
        strom_setzen(&s, true).expect("setzen");
        assert!(strom_an(&s));
        strom_setzen(&s, false).expect("aus");
        assert!(!strom_an(&s));
    }

    /// Der Rest der Datei bleibt stehen: die Wahl ist eine Datei mit mehreren
    /// Feldern, und ein Strom-Schalter darf die Modellreihenfolge nicht wegwerfen.
    #[test]
    fn reihenfolge_ueberlebt_den_stromschalter() {
        let s = stand("erhalt");
        let mut w = json!({"reihenfolge": ["ollama/qwen2.5:14b"], "stream": false});
        crate::daten::wahl_speichern(&s.daten, &w).expect("schreiben");
        strom_setzen(&s, true).expect("setzen");
        w["stream"] = json!(true);
        assert_eq!(lesen(&s).expect("lesen"), w);
    }

    /// Nur bekannte Felder, nur der richtige Typ -- sonst schriebe die Tuer
    /// beliebiges JSON in die Wahl.
    #[test]
    fn fremdes_feld_und_falscher_typ_werden_abgelehnt() {
        let s = stand("abwehr");
        let a = antworten(&json!({"op": "wahl_feld_setzen", "feld": "suche", "wert": {}}), &s);
        assert_eq!(a["fehler"]["code"], "feld_unbekannt");
        let b = antworten(&json!({"op": "wahl_feld_setzen", "feld": "stream", "wert": "an"}), &s);
        assert_eq!(b["fehler"]["code"], "wert_ungueltig");
        // und nichts geschrieben
        assert!(!s.daten.wahl_datei().exists());
    }

    /// Die Kette wird sortiert und gekuerzt -- die Oberflaeche schickt die
    /// ganze Liste. Geprueft wird jeder Eintrag: kein Schrott in `wahl.json`.
    #[test]
    fn reihenfolge_wird_gesetzt_sortiert_und_gekuerzt() {
        let s = stand("kette");
        reihenfolge_setzen(&s, &["ollama/a".into(), "ollama/b".into()]).expect("setzen");
        assert_eq!(lesen(&s).unwrap()["reihenfolge"], json!(["ollama/a", "ollama/b"]));
        // sortieren
        reihenfolge_setzen(&s, &["ollama/b".into(), "ollama/a".into()]).expect("tauschen");
        assert_eq!(lesen(&s).unwrap()["reihenfolge"], json!(["ollama/b", "ollama/a"]));
        // kuerzen
        reihenfolge_setzen(&s, &["ollama/a".into()]).expect("kuerzen");
        assert_eq!(lesen(&s).unwrap()["reihenfolge"], json!(["ollama/a"]));
        // und der Strom bleibt, wie er war
        assert_eq!(lesen(&s).unwrap().get("stream"), None);
    }

    #[test]
    fn kette_nimmt_nur_gueltige_verweise_ohne_doppelte() {
        let s = stand("ketteabwehr");
        for (liste, grund) in [
            (json!(["ollama/a", "ollama/a"]), "doppelt"),
            (json!(["ohne-schraegstrich"]), "verweis"),
            (json!(["../x/y"]), "verweis"),
            (json!(["ollama/"]), "verweis"),
        ] {
            let a = antworten(&json!({"op": "wahl_feld_setzen", "feld": "reihenfolge", "wert": liste}), &s);
            assert_eq!(a["fehler"]["code"], "wert_ungueltig", "{grund}");
        }
        let zuviel: Vec<String> = (0..crate::daten::KETTE_MAX + 1).map(|i| format!("ollama/m{i}")).collect();
        let a = antworten(&json!({"op": "wahl_feld_setzen", "feld": "reihenfolge", "wert": zuviel}), &s);
        assert_eq!(a["fehler"]["code"], "wert_ungueltig");
        assert!(!s.daten.wahl_datei().exists());
    }

    /// Eine kaputte Datei wird gemeldet, nicht ueberschrieben.
    #[test]
    fn kaputte_wahl_wird_gemeldet() {
        let s = stand("kaputt");
        std::fs::create_dir_all(s.daten.wahl_datei().parent().unwrap()).expect("ordner");
        std::fs::write(s.daten.wahl_datei(), "{nicht json").expect("schreiben");
        assert!(lesen(&s).is_err());
        let a = antworten(&json!({"op": "wahl_feld_setzen", "feld": "stream", "wert": true}), &s);
        assert_eq!(a["fehler"]["code"], "wahl_kaputt");
        assert_eq!(std::fs::read_to_string(s.daten.wahl_datei()).unwrap(), "{nicht json");
    }
}
