//! Freigabe je Werkzeug auf Zeit (DESIGN, Regel "Freigabe je Werkzeug auf
//! Zeit").
//!
//! Der Nutzer entscheidet **je Werkzeug**, ob weiter einzeln gefragt wird
//! (`positivliste`) oder ob fuer eine Zeitspanne alles durchgeht, was nicht
//! auf der Negativliste steht (`offen`). `bis: null` heisst "fuer immer".
//!
//! Drei Regeln, die hier zusammenlaufen und deshalb nur hier stehen:
//!
//! * **`negativ` gilt immer** -- auch im offenen Modus, auch bei "fuer immer",
//!   auch gegen einen Eintrag in `positiv`.
//! * **Der Ablauf wird beim Pruefen ausgewertet**, nicht von einem Timer.
//!   Ein neu gestarteter Dienst darf eine Freigabe nicht verlaengern.
//! * **Die Werkzeugliste ist geschlossen.** Ein unbekannter Name wird
//!   abgelehnt, statt still durchzugehen -- ein Tippfehler soll nichts oeffnen.
//!
//! Die Datei gehoert dem Gateway (`config/freigaben.json`, 660). Der Agent
//! liest sie nie; er fragt und bekommt Ja oder Nein mit Grund.

use crate::daten::{atomar_schreiben, Pfade};
use serde_json::{json, Value};
use std::io::Write;

/// Werkzeuge, die freigegeben werden koennen. **Geschlossen**: was hier nicht
/// steht, laesst sich nicht freigeben. Neue Werkzeuge kommen mit ihrem
/// Aufrufer dazu, nicht auf Verdacht.
pub const WERKZEUGE: &[&str] = &["web_suche", "web_abruf", "ssh", "run_command"];

/// Laenger als das Protokoll nicht, bevor es rotiert.
const PROTOKOLL_MAX: u64 = 512 * 1024;

fn jetzt_s() -> u64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

pub fn datei(p: &Pfade) -> std::path::PathBuf {
    p.config.join("freigaben.json")
}

fn protokoll_datei(p: &Pfade) -> std::path::PathBuf {
    p.state.join("log").join("freigabe.log")
}

/// Ein Werkzeug-Eintrag, wie er in der Datei steht. Fehlende Felder haben
/// Vorgaben; die Vorgabe ist immer die vorsichtige Seite.
#[derive(Debug, Clone, PartialEq)]
pub struct Eintrag {
    pub modus_offen: bool,
    /// `None` = fuer immer.
    pub bis: Option<u64>,
    pub positiv: Vec<String>,
    pub negativ: Vec<String>,
}

impl Default for Eintrag {
    fn default() -> Self {
        Eintrag { modus_offen: false, bis: None, positiv: Vec::new(), negativ: Vec::new() }
    }
}

impl Eintrag {
    /// Aus JSON lesen. Unbekannte Modi gelten als `positivliste` (die
    /// vorsichtige Seite), nicht als offen.
    pub fn aus(v: &Value) -> Eintrag {
        let texte = |f: &str| -> Vec<String> {
            v.get(f)
                .and_then(Value::as_array)
                .map(|a| a.iter().filter_map(Value::as_str).map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect())
                .unwrap_or_default()
        };
        Eintrag {
            modus_offen: v.get("modus").and_then(Value::as_str) == Some("offen"),
            bis: v.get("bis").and_then(Value::as_u64),
            positiv: texte("positiv"),
            negativ: texte("negativ"),
        }
    }

    /// Steht die Freigabe noch? `None` bei "fuer immer".
    pub fn offen_bis(&self, jetzt: u64) -> bool {
        self.modus_offen && self.bis.map(|b| b > jetzt).unwrap_or(true)
    }
}

/// Die Datei so lesen, wie sie dasteht. Fehlt sie oder ist sie kaputt, gilt
/// die Vorgabe (alles auf Positivliste) -- nie ein offener Zustand.
fn roh(p: &Pfade) -> Value {
    std::fs::read_to_string(datei(p))
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({}))
}

/// Die ganze Datei fuer die Anzeige: Vorgaben aufgefuellt, **abgelaufene**
/// Freigaben stehen als `positivliste` da. Was die Uhr entschieden hat, soll
/// die Oberflaeche zeigen, nicht die Absicht von gestern.
pub fn laden(p: &Pfade) -> Value {
    aufraeumen(&roh(p), jetzt_s())
}

/// Vorgaben auffuellen: `vorgabe`, je Werkzeug ein Eintrag. Was in der Datei
/// steht, bleibt stehen -- hier wird nichts erfunden.
fn aufraeumen(roh: &Value, jetzt: u64) -> Value {
    let mut werkzeuge = serde_json::Map::new();
    for name in WERKZEUGE {
        let e = roh.get("werkzeuge").and_then(|w| w.get(*name)).cloned().unwrap_or_else(|| json!({}));
        let mut e = e;
        let mut o = Eintrag::aus(&e);
        // Ein bis in der Vergangenheit bleibt stehen (der Aufrufer sieht so,
        // dass es abgelaufen ist), aber der Modus ist dann nicht mehr "offen".
        if !o.bis.map(|b| b > jetzt).unwrap_or(true) {
            o.modus_offen = false;
        }
        if let Some(m) = e.as_object_mut() {
            m.insert("modus".into(), json!(if o.modus_offen { "offen" } else { "positivliste" }));
            m.entry("bis").or_insert(Value::Null);
            m.entry("positiv").or_insert(json!(o.positiv));
            m.entry("negativ").or_insert(json!(o.negativ));
        }
        werkzeuge.insert((*name).to_string(), e);
    }
    let mut out = roh.as_object().cloned().unwrap_or_default();
    out.insert("vorgabe".into(), roh.get("vorgabe").cloned().unwrap_or(json!({"modus": "positivliste"})));
    out.insert("werkzeuge".into(), Value::Object(werkzeuge));
    Value::Object(out)
}

/// Darf das Werkzeug das Ziel? `ziel: None` heisst "das Werkzeug ohne Ziel"
/// (z.B. `web_suche` ohne feste Quelle -- dann entscheidet der Modus allein).
///
/// Antwort: `{"erlaubt": bool, "grund": "...", "bis": <u64|null>}`.
pub fn pruefen(p: &Pfade, werkzeug: &str, ziel: Option<&str>, jetzt: u64) -> Value {
    if !WERKZEUGE.contains(&werkzeug) {
        return antwort(false, format!("Werkzeug \"{werkzeug}\" ist nicht freigebbar (bekannt: {}).", WERKZEUGE.join(", ")), None);
    }
    // Bewusst die rohe Datei: die Entscheidung faellt hier, mit der Uhr des
    // Aufrufers -- nicht in der Aufbereitung fuer die Anzeige (die schreibt
    // abgelaufene Freigaben auf `positivliste` um, damit die Oberflaeche die
    // Wahrheit zeigt).
    let ganz = roh(p);
    let e = Eintrag::aus(&ganz["werkzeuge"][werkzeug]);
    let z = ziel.map(str::trim).unwrap_or("").to_lowercase();

    // 1. Negativliste: immer, auch im offenen Modus, auch "fuer immer".
    if !z.is_empty() && e.negativ.iter().any(|n| n.to_lowercase() == z) {
        protokoll(p, jetzt, werkzeug, ziel, "abgelehnt", "steht auf der Negativliste");
        return antwort(false, "steht auf der Negativliste".into(), e.bis);
    }
    // 2. Positivliste: gilt in beiden Modi -- ein eingetragenes Ziel ist
    //    immer erlaubt, auch wenn die Freigabe abgelaufen ist.
    if !z.is_empty() && e.positiv.iter().any(|x| x.to_lowercase() == z) {
        protokoll(p, jetzt, werkzeug, ziel, "erlaubt", "steht auf der Positivliste");
        return antwort(true, "steht auf der Positivliste".into(), e.bis);
    }
    // 3. Zeitfreigabe: alles andere, solange sie laeuft.
    if e.offen_bis(jetzt) {
        protokoll(p, zeit_ok(jetzt, e.bis), werkzeug, ziel, "erlaubt", "Zeitfreigabe laeuft");
        return antwort(true, "Zeitfreigabe laeuft".into(), e.bis);
    }
    // 4. Sonst: fragen, also nicht erlaubt -- mit dem Grund.
    let grund = if e.modus_offen {
        "Zeitfreigabe abgelaufen".to_string()
    } else if let Some(b) = e.bis {
        format!("keine Freigabe; die letzte lief bis {b} ab")
    } else {
        "keine Freigabe eingetragen".to_string()
    };
    protokoll(p, jetzt, werkzeug, ziel, "abgelehnt", &grund);
    antwort(false, grund, e.bis)
}

/// Beim Pruefen ist die Uhr die Wahrheit; im Protokoll soll trotzdem die
/// tatsaechliche Zeit stehen (auch in Tests, die eine feste Zeit vorgeben).
fn zeit_ok(_jetzt: u64, _bis: Option<u64>) -> u64 {
    jetzt_s()
}

fn antwort(erlaubt: bool, grund: String, bis: Option<u64>) -> Value {
    json!({"erlaubt": erlaubt, "grund": grund, "bis": bis})
}

/// Ein Eintrag wird gesetzt. `wert` ist `{modus, bis, positiv, negativ}`.
/// Geprueft wird jeder Teil: ein unbekannter Modus, eine Dauer in der
/// Vergangenheit oder ein leeres Ziel waeren sonst stille Fehler.
pub fn setzen(p: &Pfade, werkzeug: &str, wert: &Value, jetzt: u64) -> Result<Value, (&'static str, String)> {
    if !WERKZEUGE.contains(&werkzeug) {
        return Err((
            "werkzeug_unbekannt",
            format!("Werkzeug \"{werkzeug}\" laesst sich nicht freigeben (bekannt: {}).", WERKZEUGE.join(", ")),
        ));
    }
    let modus = wert.get("modus").and_then(Value::as_str).unwrap_or("positivliste");
    if modus != "offen" && modus != "positivliste" {
        return Err(("wert_ungueltig", format!("Modus \"{modus}\" gibt es nicht (offen, positivliste).")));
    }
    let bis = match wert.get("bis") {
        None | Some(Value::Null) => None,
        Some(v) => match v.as_u64() {
            Some(b) if b > jetzt => Some(b),
            Some(b) => {
                return Err((
                    "wert_ungueltig",
                    format!("Der Zeitpunkt {b} liegt in der Vergangenheit; eine Freigabe, die schon abgelaufen ist, waere eine stille Luege."),
                ))
            }
            None => return Err(("wert_ungueltig", format!("\"bis\" braucht eine Zahl (Sekunden) oder null, bekam {v}."))),
        },
    };
    let liste = |feld: &str| -> Result<Vec<String>, (&'static str, String)> {
        let Some(v) = wert.get(feld) else { return Ok(Vec::new()) };
        let Some(a) = v.as_array() else {
            return Err(("wert_ungueltig", format!("\"{feld}\" braucht eine Liste (bekam {v}).")));
        };
        let mut out = Vec::with_capacity(a.len());
        for e in a {
            let Some(t) = e.as_str() else {
                return Err(("wert_ungueltig", format!("Eintrag {e} in \"{feld}\" ist kein Text.")));
            };
            let t = t.trim();
            if t.is_empty() || t.chars().any(char::is_whitespace) {
                return Err(("wert_ungueltig", format!("Ziel \"{t}\" in \"{feld}\" ist leer oder enthaelt Leerraum.")));
            }
            if !out.iter().any(|x: &String| x.eq_ignore_ascii_case(t)) {
                out.push(t.to_string());
            }
        }
        Ok(out)
    };
    // **Fehlt heisst behalten, nicht leeren.** Telegram und eine spaetere CLI
    // schicken oft nur `modus`/`bis`; wuerden fehlende Listen geleert, loeschte
    // ein Zeitknopf die gepflegten Ziele. Zum Leeren schickt man `[]`.
    let alt = Eintrag::aus(&laden(p)["werkzeuge"][werkzeug]);
    let positiv = if wert.get("positiv").is_some() { liste("positiv")? } else { alt.positiv.clone() };
    let negativ = if wert.get("negativ").is_some() { liste("negativ")? } else { alt.negativ.clone() };
    if let Some(doppelt) = positiv.iter().find(|x| negativ.iter().any(|n| n.eq_ignore_ascii_case(x))) {
        return Err(("wert_ungueltig", format!("\"{doppelt}\" steht auf beiden Listen; die Negativliste gewinnt, das waere verwirrend.")));
    }
    let notiz = match wert.get("notiz").and_then(Value::as_str) {
        Some(n) => n.trim().to_string(),
        None => laden(p)["werkzeuge"][werkzeug]["notiz"].as_str().unwrap_or("").trim().to_string(),
    };
    if notiz.chars().count() > 200 {
        return Err(("wert_ungueltig", "Die Notiz ist laenger als 200 Zeichen.".into()));
    }
    let neu = json!({"modus": modus, "bis": bis, "positiv": positiv, "negativ": negativ, "notiz": notiz});
    let mut ganz = laden(p);
    let Some(w) = ganz.get_mut("werkzeuge").and_then(|w| w.as_object_mut()) else {
        return Err(("wert_ungueltig", "Die Freigaben sind kein Objekt.".into()));
    };
    w.insert(werkzeug.to_string(), neu.clone());
    schreiben(p, &ganz).map_err(|e| ("nicht_gespeichert", e))?;
    protokoll(p, jetzt, werkzeug, None, "gesetzt", &beschreibung(&neu));
    Ok(neu)
}

fn beschreibung(e: &Value) -> String {
    let bis = match e["bis"].as_u64() {
        Some(b) => format!("bis {b}"),
        None => "unbefristet".into(),
    };
    format!("{} ({}), positiv {}, negativ {}", e["modus"].as_str().unwrap_or("?"), bis,
        e["positiv"].as_array().map(|a| a.len()).unwrap_or(0),
        e["negativ"].as_array().map(|a| a.len()).unwrap_or(0))
}

fn schreiben(p: &Pfade, wert: &Value) -> Result<(), String> {
    let mut text = serde_json::to_vec_pretty(wert).map_err(|e| e.to_string())?;
    text.push(b'\n');
    atomar_schreiben(&datei(p), &text, 0o660)
}

/// Eine Zeile je Entscheidung. Auch das Ja wird protokolliert -- "stiller
/// Erfolg" ist hier die gefaehrlichste Fehlerart. Ein Protokollfehler darf
/// die Entscheidung nicht umdrehen (die Warnung geht ins Dienstprotokoll).
fn protokoll(p: &Pfade, zeit: u64, werkzeug: &str, ziel: Option<&str>, was: &str, grund: &str) {
    let datei = protokoll_datei(p);
    if let Some(dir) = datei.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    if std::fs::metadata(&datei).map(|m| m.len()).unwrap_or(0) > PROTOKOLL_MAX {
        let alt = datei.with_extension("log.1");
        let _ = std::fs::rename(&datei, alt);
    }
    let mut zeile = format!("{zeit}\t{was}\t{werkzeug}\t{}\t{grund}\n", ziel.unwrap_or("-"));
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(&datei) {
        let _ = f.write_all(zeile.as_bytes());
    }
    zeile.clear();
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(name: &str) -> Pfade {
        let d = std::env::temp_dir().join(format!("chimera-freigaben-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        Pfade::neu(d.join("config"), d.join("state"))
    }

    #[test]
    fn ohne_datei_gilt_die_positivliste() {
        let p = p("leer");
        let a = pruefen(&p, "web_abruf", Some("example.com"), 1000);
        assert_eq!(a["erlaubt"], false);
        assert!(a["grund"].as_str().unwrap().contains("keine Freigabe"), "{a}");
    }

    #[test]
    fn unbekanntes_werkzeug_wird_abgelehnt() {
        let p = p("unbekannt");
        let a = pruefen(&p, "gibtesnicht", None, 1000);
        assert_eq!(a["erlaubt"], false);
        assert!(a["grund"].as_str().unwrap().contains("nicht freigebbar"), "{a}");
        let e = setzen(&p, "gibtesnicht", &json!({"modus": "offen"}), 1000).unwrap_err();
        assert_eq!(e.0, "werkzeug_unbekannt");
    }

    #[test]
    fn zeitfreigabe_gilt_bis_zum_ablauf_dann_wieder_positivliste() {
        let p = p("ablauf");
        setzen(&p, "web_abruf", &json!({"modus": "offen", "bis": 2000}), 1000).expect("setzen");
        assert_eq!(pruefen(&p, "web_abruf", Some("example.com"), 1500)["erlaubt"], true);
        let spaeter = pruefen(&p, "web_abruf", Some("example.com"), 2500);
        assert_eq!(spaeter["erlaubt"], false);
        assert!(spaeter["grund"].as_str().unwrap().contains("abgelaufen"), "{spaeter}");
    }

    #[test]
    fn fuer_immer_bleibt_offen() {
        let p = p("immer");
        setzen(&p, "ssh", &json!({"modus": "offen", "bis": null}), 1000).expect("setzen");
        assert_eq!(pruefen(&p, "ssh", Some("host.example"), 9_999_999)["erlaubt"], true);
    }

    #[test]
    fn negativliste_gilt_auch_im_offenen_modus() {
        let p = p("negativ");
        setzen(&p, "web_abruf", &json!({"modus": "offen", "bis": null, "negativ": ["bose.example"]}), 1000)
            .expect("setzen");
        assert_eq!(pruefen(&p, "web_abruf", Some("gut.example"), 1001)["erlaubt"], true);
        let b = pruefen(&p, "web_abruf", Some("bose.example"), 1001);
        assert_eq!(b["erlaubt"], false);
        assert!(b["grund"].as_str().unwrap().contains("Negativliste"), "{b}");
    }

    #[test]
    fn positivliste_gilt_auch_nach_ablauf() {
        let p = p("positiv");
        setzen(&p, "web_abruf", &json!({"modus": "offen", "bis": 2000, "positiv": ["dauerhaft.example"]}), 1000)
            .expect("setzen");
        let a = pruefen(&p, "web_abruf", Some("dauerhaft.example"), 5000);
        assert_eq!(a["erlaubt"], true, "{a}");
        assert!(a["grund"].as_str().unwrap().contains("Positivliste"), "{a}");
    }

    #[test]
    fn abgelaufener_zeitpunkt_ist_kein_gueltiger_auftrag() {
        let p = p("vergangen");
        let e = setzen(&p, "web_abruf", &json!({"modus": "offen", "bis": 500}), 1000).unwrap_err();
        assert_eq!(e.0, "wert_ungueltig");
        assert!(e.1.contains("Vergangenheit"), "{}", e.1);
    }

    #[test]
    fn falscher_modus_und_kaputte_listen_werden_abgelehnt() {
        let p = p("abwehr");
        assert_eq!(setzen(&p, "ssh", &json!({"modus": "vielleicht"}), 1000).unwrap_err().0, "wert_ungueltig");
        assert_eq!(setzen(&p, "ssh", &json!({"modus": "offen", "positiv": "host"}), 1000).unwrap_err().0, "wert_ungueltig");
        assert_eq!(setzen(&p, "ssh", &json!({"modus": "offen", "positiv": ["mit leer"]}), 1000).unwrap_err().0, "wert_ungueltig");
        assert_eq!(
            setzen(&p, "ssh", &json!({"modus": "offen", "positiv": ["a.example"], "negativ": ["A.example"]}), 1000).unwrap_err().0,
            "wert_ungueltig"
        );
        assert!(!datei(&p).exists(), "nichts geschrieben");
    }

    /// Ein Teil-Auftrag (nur `modus`/`bis`) darf die gepflegten Listen nicht
    /// wegwerfen -- so schaltet Telegram die Dauer, ohne Ziele zu kennen.
    #[test]
    fn teilauftrag_behaelt_die_listen() {
        let p = p("teil");
        setzen(&p, "ssh", &json!({"modus": "positivliste", "positiv": ["host.example"], "negativ": ["bose.example"]}), 1000)
            .expect("listen");
        setzen(&p, "ssh", &json!({"modus": "offen", "bis": 2000}), 1000).expect("dauer");
        // Die rohe Sicht: `laden` zeigt fuer die Anzeige "abgelaufen", weil die
        // echte Uhr 2026 steht und `bis` 2000 ist.
        let e = Eintrag::aus(&roh(&p)["werkzeuge"]["ssh"]);
        assert_eq!(e.positiv, vec!["host.example"]);
        assert_eq!(e.negativ, vec!["bose.example"]);
        assert!(e.offen_bis(1500));
        // Und ein ausdrueckliches Leeren geht weiter.
        setzen(&p, "ssh", &json!({"modus": "offen", "bis": 2000, "negativ": []}), 1000).expect("leeren");
        assert!(Eintrag::aus(&roh(&p)["werkzeuge"]["ssh"]).negativ.is_empty());
    }

    #[test]
    fn die_entscheidung_wird_protokolliert() {
        let p = p("protokoll");
        pruefen(&p, "web_abruf", Some("example.com"), 111);
        let text = std::fs::read_to_string(protokoll_datei(&p)).expect("protokoll");
        assert!(text.contains("abgelehnt"), "{text}");
        assert!(text.contains("web_abruf"), "{text}");
        assert!(text.contains("example.com"), "{text}");
    }
}
