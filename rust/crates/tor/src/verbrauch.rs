//! Verbrauch: die eigene Zählung gegen die Abrechnung des Anbieters
//! (DESIGN, „Verbrauch" 15.11.2026, Auftrag smilez).
//!
//! Zwei Zahlen, zwei Herkünfte:
//!
//! * **Eigene Zählung** — je Tag und Modell die Token-Summen aus dem
//!   `verbrauch`-Block jeder Antwort. Der Dienst meldet sie hierher
//!   (`op: verbrauch_notieren`), weil `state/` dem Gateway gehört (Regel 5t)
//!   und der Dienst dort nicht schreiben darf.
//! * **Abrechnung** — der Kontostand-Verlauf aus [`crate::quota`]. Die
//!   Differenz zweier Stände ist die tatsächlich abgerechnete Summe.
//!
//! Es wird **nichts umgerechnet und nichts geschätzt**: Tokens bleiben
//! Tokens, Geld bleibt Geld, und wo eine Seite fehlt, steht der Grund.

use serde_json::{json, Map, Value};

/// So viele Tage werden höchstens gelesen (Ringpuffer der Ablage).
pub const TAGE_MAX: usize = 366;

fn verzeichnis(p: &crate::daten::Pfade) -> std::path::PathBuf {
    p.state.join("verbrauch")
}

fn datei(p: &crate::daten::Pfade, tag: &str) -> std::path::PathBuf {
    verzeichnis(p).join(format!("{tag}.json"))
}

/// Ein Tag wie `2026-11-15` — alles andere wird abgelehnt, nicht geraten
/// (ein Pfad aus einer Zeichenkette ist eine Einladung).
pub fn tag_gueltig(tag: &str) -> bool {
    tag.len() == 10
        && tag.as_bytes()[4] == b'-'
        && tag.as_bytes()[7] == b'-'
        && tag
            .bytes()
            .enumerate()
            .all(|(i, b)| if i == 4 || i == 7 { b == b'-' } else { b.is_ascii_digit() })
}

/// Ein leeres Tagesblatt.
fn leer(tag: &str) -> Value {
    json!({"tag": tag, "aufrufe": 0, "eingabe": 0, "ausgabe": 0,
           "cache_neu": 0, "cache_treffer": 0, "denken": 0, "je_modell": {}})
}

/// Einen Tag lesen (`leer`, wenn es ihn nicht gibt).
pub fn tag_lesen(p: &crate::daten::Pfade, tag: &str) -> Value {
    if !tag_gueltig(tag) {
        return json!({});
    }
    std::fs::read_to_string(datei(p, tag))
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .filter(|v| v.is_object())
        .unwrap_or_else(|| leer(tag))
}

fn zahl(v: &Value, feld: &str) -> u64 {
    v[feld].as_u64().unwrap_or(0)
}

/// Eine Meldung in das Tagesblatt addieren (rein, ohne Platte).
pub fn addieren(blatt: &mut Value, meldung: &Value) -> Value {
    let modell = meldung["modell"].as_str().unwrap_or("").trim();
    let anbieter = meldung["anbieter"].as_str().unwrap_or("").trim();
    let schluessel = match (anbieter.is_empty(), modell.is_empty()) {
        (false, false) => format!("{anbieter}/{modell}"),
        (true, false) => modell.to_string(),
        (false, true) => anbieter.to_string(),
        (true, true) => "unbekannt".to_string(),
    };
    blatt["aufrufe"] = json!(zahl(blatt, "aufrufe") + 1);
    for feld in ["eingabe", "ausgabe", "cache_neu", "cache_treffer", "denken"] {
        blatt[feld] = json!(zahl(blatt, feld) + zahl(meldung, feld));
    }
    if !blatt["je_modell"].is_object() {
        blatt["je_modell"] = json!({});
    }
    let Some(je) = blatt["je_modell"].as_object_mut() else {
        return blatt.clone();
    };
    let mut eintrag = je.get(&schluessel).cloned().unwrap_or_else(
        || json!({"aufrufe": 0, "eingabe": 0, "ausgabe": 0,
                  "cache_neu": 0, "cache_treffer": 0, "denken": 0}));
    eintrag["aufrufe"] = json!(zahl(&eintrag, "aufrufe") + 1);
    for feld in ["eingabe", "ausgabe", "cache_neu", "cache_treffer", "denken"] {
        eintrag[feld] = json!(zahl(&eintrag, feld) + zahl(meldung, feld));
    }
    je.insert(schluessel, eintrag);
    blatt.clone()
}

/// Eine Meldung ablegen. `tag` kommt vom Aufrufer (der Dienst kennt seine
/// Ortszeit; das Gateway rechnet sie nicht aus einer Ziffernfolge).
pub fn notieren(p: &crate::daten::Pfade, tag: &str, meldung: &Value) -> Value {
    if !tag_gueltig(tag) {
        return json!({"ok": false,
                      "fehler": {"code": "tag_ungueltig",
                                 "text": format!("Kein Tag im Format JJJJ-MM-TT: {tag:?}")}});
    }
    let mut blatt = tag_lesen(p, tag);
    if blatt["tag"].is_null() {
        blatt["tag"] = json!(tag);
    }
    addieren(&mut blatt, meldung);
    blatt["geaendert"] = json!(jetzt_s());
    let d = verzeichnis(p);
    if let Err(e) = std::fs::create_dir_all(&d) {
        return json!({"ok": false, "fehler": {"code": "ablage",
                       "text": format!("{} nicht anlegbar: {e}", d.display())}});
    }
    let text = match serde_json::to_vec_pretty(&blatt) {
        Ok(t) => t,
        Err(e) => {
            return json!({"ok": false, "fehler": {"code": "ablage", "text": e.to_string()}})
        }
    };
    if let Err(e) = crate::daten::atomar_schreiben(&datei(p, tag), &text, 0o640) {
        return json!({"ok": false, "fehler": {"code": "ablage", "text": e}});
    }
    json!({"ok": true, "tag": blatt["tag"].clone(), "aufrufe": blatt["aufrufe"].clone(),
           "eingabe": blatt["eingabe"].clone(), "ausgabe": blatt["ausgabe"].clone()})
}

fn jetzt_s() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Die letzten `tage` Tagesblätter, neueste zuerst.
pub fn lesen(p: &crate::daten::Pfade, tage: usize) -> Value {
    let tage = tage.clamp(1, TAGE_MAX);
    let d = verzeichnis(p);
    let mut namen: Vec<String> = match std::fs::read_dir(&d) {
        Ok(rd) => rd
            .filter_map(|e| e.ok())
            .filter_map(|e| e.file_name().to_str().map(str::to_string))
            .filter(|n| n.ends_with(".json"))
            .map(|n| n.trim_end_matches(".json").to_string())
            .filter(|n| tag_gueltig(n))
            .collect(),
        Err(_) => Vec::new(),
    };
    namen.sort();
    namen.reverse();
    namen.truncate(tage);
    let mut blaetter = Vec::new();
    let (mut aufrufe, mut eingabe, mut ausgabe) = (0u64, 0u64, 0u64);
    for tag in &namen {
        let b = tag_lesen(p, tag);
        aufrufe += zahl(&b, "aufrufe");
        eingabe += zahl(&b, "eingabe");
        ausgabe += zahl(&b, "ausgabe");
        blaetter.push(b);
    }
    json!({
        "ok": true,
        "tage": tage,
        "tag": blaetter,
        "summe": {"aufrufe": aufrufe, "eingabe": eingabe, "ausgabe": ausgabe},
        "quelle": "eigene Zaehlung (verbrauch-Block jeder Antwort)",
    })
}

/// `op: verbrauch_lesen` und `op: verbrauch_notieren`.
pub fn op(p: &crate::daten::Pfade, anfrage: &Value) -> Value {
    let was = anfrage.get("op").and_then(Value::as_str).unwrap_or("");
    match was {
        "verbrauch_lesen" => {
            let tage = anfrage.get("tage").and_then(Value::as_u64).unwrap_or(7) as usize;
            lesen(p, tage)
        }
        "verbrauch_notieren" => {
            let tag = anfrage.get("tag").and_then(Value::as_str).unwrap_or("");
            let mut m = Map::new();
            for feld in ["anbieter", "modell", "eingabe", "ausgabe",
                         "cache_neu", "cache_treffer", "denken"] {
                if let Some(v) = anfrage.get(feld) {
                    m.insert(feld.to_string(), v.clone());
                }
            }
            notieren(p, tag, &Value::Object(m))
        }
        _ => json!({"ok": false, "fehler": {"code": "unbekannt", "text": was}}),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(n: &str) -> crate::daten::Pfade {
        let d = std::env::temp_dir().join(format!("chimera-verbrauch-{n}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        crate::daten::Pfade::neu(d.join("config"), d.join("state"))
    }

    #[test]
    fn ein_tag_wird_aufaddiert_nicht_ueberschrieben() {
        let pf = p("add");
        let a = notieren(&pf, "2026-11-15", &json!({"anbieter": "deepseek", "modell": "flash",
                                                    "eingabe": 100, "ausgabe": 10}));
        assert_eq!(a["ok"], true, "{a}");
        let b = notieren(&pf, "2026-11-15", &json!({"anbieter": "deepseek", "modell": "flash",
                                                    "eingabe": 50, "ausgabe": 5}));
        assert_eq!(b["aufrufe"], 2);
        assert_eq!(b["eingabe"], 150);
        assert_eq!(b["ausgabe"], 15);
    }

    #[test]
    fn je_modell_getrennt() {
        let pf = p("modell");
        notieren(&pf, "2026-11-15", &json!({"anbieter": "deepseek", "modell": "flash", "eingabe": 10}));
        notieren(&pf, "2026-11-15", &json!({"anbieter": "ollama", "modell": "qwen", "eingabe": 7}));
        let t = tag_lesen(&pf, "2026-11-15");
        assert_eq!(t["je_modell"]["deepseek/flash"]["eingabe"], 10);
        assert_eq!(t["je_modell"]["ollama/qwen"]["eingabe"], 7);
        assert_eq!(t["eingabe"], 17);
    }

    #[test]
    fn lesen_zaehlt_neueste_zuerst_und_summiert() {
        let pf = p("lesen");
        notieren(&pf, "2026-11-14", &json!({"anbieter": "a", "modell": "m", "eingabe": 1}));
        notieren(&pf, "2026-11-15", &json!({"anbieter": "a", "modell": "m", "eingabe": 2}));
        let l = lesen(&pf, 7);
        assert_eq!(l["tag"][0]["tag"], "2026-11-15");
        assert_eq!(l["tag"][1]["tag"], "2026-11-14");
        assert_eq!(l["summe"]["eingabe"], 3);
        // Nur so viele Tage, wie verlangt.
        assert_eq!(lesen(&pf, 1)["tag"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn ein_kaputter_tag_ist_kein_pfad() {
        let pf = p("tag");
        let a = notieren(&pf, "../../etc/passwd", &json!({"eingabe": 1}));
        assert_eq!(a["fehler"]["code"], "tag_ungueltig");
        assert!(!tag_gueltig("2026-11-15\n"));
        assert!(!tag_gueltig("20261115"));
        assert!(tag_gueltig("2026-11-15"));
        // Ein unbekannter Tag liefert ein leeres Blatt, keine Datei.
        assert_eq!(tag_lesen(&pf, "2026-01-01")["aufrufe"], 0);
    }

    #[test]
    fn fehlende_felder_zaehlen_als_null_und_kippen_nicht() {
        let pf = p("leer");
        let a = notieren(&pf, "2026-11-15", &json!({}));
        assert_eq!(a["ok"], true);
        let t = tag_lesen(&pf, "2026-11-15");
        assert_eq!(t["aufrufe"], 1);
        assert_eq!(t["eingabe"], 0);
        assert_eq!(t["je_modell"]["unbekannt"]["aufrufe"], 1);
    }

    #[test]
    fn op_liest_und_schreibt() {
        let pf = p("op");
        let a = op(&pf, &json!({"op": "verbrauch_notieren", "tag": "2026-11-15",
                                "anbieter": "x", "modell": "y", "eingabe": 4}));
        assert_eq!(a["ok"], true);
        let b = op(&pf, &json!({"op": "verbrauch_lesen", "tage": 3}));
        assert_eq!(b["summe"]["eingabe"], 4);
    }
}
