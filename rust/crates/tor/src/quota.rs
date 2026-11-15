//! Guthaben je Anbieter (ROADMAP „Guthaben und Kosten je Anbieter", Auftrag
//! smilez 13.11.; Muster bei OpenMinis abgeschaut, `provider/quota/`).
//!
//! Drei Zusagen, die den Bau bestimmen:
//!
//! 1. **Herkunft immer mitliefern.** Jede Zahl nennt Quelle (`offizielle API` /
//!    `Dashboard-API` / `unbekannt`), Belegtheit (`dokumentiert` / `beobachtet`),
//!    Endpunkt und Zeitpunkt. Ein Adapter, der keine Zahl holen kann, sagt das
//!    -- er erfindet keine.
//! 2. **Nie umrechnen, nie summieren.** Guthaben ist je Währung ein eigener
//!    Pool („currencies are never converted or summed", OpenMinis
//!    `QuotaRules.kt`).
//! 3. **Veraltet wird gezeigt, nicht versteckt.** Aktive Abfragen hoechstens
//!    alle 10 Minuten; `Retry-After` bindet auch einen erzwungenen Abruf.
//!
//! Ablage: `state/quota/<id>.json` (Regel 5t). Die Datei enthaelt die **letzte
//! Antwort** samt Zeitpunkt -- nicht den Schluessel.

use gemein::zeile::fehlerantwort;
use serde_json::{json, Value};
use std::time::Duration;

pub use crate::deepseek::{host_von, schluessel_aus_umgebung};

/// Ab welchem Alter eine Zahl als veraltet gilt (10 min, OpenMinis-Muster).
pub const FRISCHE_S: u64 = 600;
/// So kurz darf ein zweiter Abruf nach einem Fehler hoechstens warten.
pub const FEHLER_ABSTAND_S: u64 = 60;
/// Zeitgrenze eines Abrufs: ein Kontostand darf keinen Chat aufhalten.
pub const ABRUF: Duration = Duration::from_secs(10);
pub const VERBINDUNG: Duration = Duration::from_secs(5);

/// Wie lange ein Wechselkurs als aktuell gilt (12 h). Die Quelle nennt
/// Tageskurse der EZB; ein Wert vom Vortag ist am Wochenende normal und
/// wird **mit Datum** gezeigt, nicht versteckt (DESIGN, Euro-Anzeige 15.11.).
pub const KURS_FRISCHE_S: u64 = 12 * 3600;
/// Mindestabstand **auch** fuer einen erzwungenen Abruf (10 min). Der Knopf
/// "Kurs aktualisieren" soll wirken, aber nicht haemmern: die Quelle ist
/// fremd und gibt uns nichts (DESIGN, Euro-Anzeige 15.11.2026).
pub const KURS_MINDESTABSTAND_S: u64 = 600;
/// Die Kursquelle: EZB-Referenzkurse, ohne Schluessel.
pub const KURS_URL: &str = "https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD,CNY";

fn agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_connect(Some(VERBINDUNG))
        .timeout_global(Some(ABRUF))
        .http_status_as_error(false)
        .build()
        .into()
}

// ------------------------------------------------------------- Ablage

fn datei(p: &crate::daten::Pfade, id: &str) -> std::path::PathBuf {
    p.state.join("quota").join(format!("{id}.json"))
}

/// Die letzte gespeicherte Antwort eines Anbieters (`{}`, wenn keine).
pub fn gespeichert(p: &crate::daten::Pfade, id: &str) -> Value {
    if !crate::daten::id_gueltig(id) {
        return json!({});
    }
    std::fs::read_to_string(datei(p, id))
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .unwrap_or_else(|| json!({}))
}

fn schreiben(p: &crate::daten::Pfade, id: &str, wert: &Value) -> Result<(), String> {
    let d = p.state.join("quota");
    std::fs::create_dir_all(&d).map_err(|e| format!("{} nicht anlegbar: {e}", d.display()))?;
    let mut text = serde_json::to_vec_pretty(wert).map_err(|e| e.to_string())?;
    text.push(b'\n');
    crate::daten::atomar_schreiben(&datei(p, id), &text, 0o600)
}

// ------------------------------------------------------------- Adapter

/// Was ein Anbieter-Typ an Guthaben hergibt. `Kontoweit` heisst: die Zahl gilt
/// fuer das ganze Konto, nicht je Modell (OpenMinis: „von allen Modellen dieses
/// Kontos geteilt").
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Art {
    /// Abrufbar ueber einen dokumentierten Endpunkt.
    Abrufbar,
    /// Kein Guthaben noetig (lokal).
    Lokal,
    /// Nicht abrufbar -- mit Grund und gegebenenfalls einem Link.
    NichtAbrufbar,
}

pub fn art_von(typ: &str) -> Art {
    match typ {
        "deepseek" => Art::Abrufbar,
        "ollama" => Art::Lokal,
        // Anthropic mit API-Key: die Usage/Cost-API verlangt einen
        // Admin-Key, den wir nicht haben. OpenMinis zeigt dort bewusst nur
        // den Link zur Abrechnung (`UnsupportedQuotaAdapter`).
        _ => Art::NichtAbrufbar,
    }
}

/// Die Pools aus DeepSeeks `/user/balance`. Rein: keine Umrechnung, keine
/// Summe -- was der Anbieter je Waehrung sagt, steht je Waehrung da.
pub fn pools_deepseek(roh: &Value) -> Vec<Value> {
    let mut raus = Vec::new();
    let Some(liste) = roh["balance_infos"].as_array() else { return raus };
    for b in liste {
        let waehrung = b["currency"].as_str().unwrap_or("").trim();
        if waehrung.is_empty() {
            continue;
        }
        raus.push(json!({
            "waehrung": waehrung,
            "gesamt": b["total_balance"].as_str(),
            "geschenkt": b["granted_balance"].as_str(),
            "aufgeladen": b["topped_up_balance"].as_str(),
        }));
    }
    raus
}

/// `Retry-After` aus einer Antwort: Sekunden oder ein HTTP-Datum -- nur
/// Sekunden werden verstanden, alles andere ist „kein Wert" (nicht raten).
pub fn retry_after(wert: Option<&str>) -> Option<u64> {
    wert?.trim().parse::<u64>().ok()
}

// ------------------------------------------------------------- Kurse

/// Die Kurstabelle aus der Antwort der Quelle (rein, ohne Netz).
///
/// Die Quelle liefert `{"base":"EUR","rates":{"USD":1.1052,"CNY":7.3738}}` —
/// also **Einheiten je Euro**. Gebraucht wird das Umgekehrte: Euro je
/// Einheit. Genau das passiert hier, und nur hier.
pub fn kurse_aus(roh: &Value) -> (std::collections::BTreeMap<String, f64>, String) {
    let mut tabelle = std::collections::BTreeMap::new();
    if let Some(rates) = roh["rates"].as_object() {
        for (waehrung, wert) in rates {
            if let Some(kurs) = wert.as_f64() {
                if kurs > 0.0 {
                    let euro = 1.0 / kurs;
                    // Auf sechs Nachkommastellen: darunter ist die Quelle
                    // selbst ungenau, mehr wäre eine erfundene Genauigkeit.
                    tabelle.insert(waehrung.to_uppercase(), (euro * 1e6).round() / 1e6);
                }
            }
        }
    }
    let datum = roh["date"].as_str().unwrap_or("").to_string();
    (tabelle, datum)
}

fn kursdatei(p: &crate::daten::Pfade) -> std::path::PathBuf {
    p.state.join("quota").join("kurse.json")
}

/// Die gespeicherten Kurse (`{}`, wenn keine).
pub fn kurse_gespeichert(p: &crate::daten::Pfade) -> Value {
    std::fs::read_to_string(kursdatei(p))
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .unwrap_or_else(|| json!({}))
}

/// Kurse holen, wenn der Stand älter als `KURS_FRISCHE_S` ist (oder `neu`).
///
/// Ein Fehler **überschreibt keinen** vorhandenen Stand: dann bleibt der
/// alte Kurs mit Datum stehen und `fehler` sagt, warum er alt ist. Eine
/// Kursangabe zu löschen, weil das Netz weg ist, wäre der schlechtere Tausch.
pub fn kurse(p: &crate::daten::Pfade, jetzt: u64, neu: bool) -> Value {
    let alt = kurse_gespeichert(p);
    let geholt = alt["geholt"].as_u64().unwrap_or(0);
    let alter = jetzt.saturating_sub(geholt);
    // Zwei Gruende fuer einen Abruf: die Frist ist um (12 h = zweimal am Tag)
    // oder jemand hat ausdruecklich darum gebeten -- aber nie oefter als der
    // Mindestabstand erlaubt.
    let faellig = if geholt == 0 {
        true
    } else if neu {
        alter >= KURS_MINDESTABSTAND_S
    } else {
        alter >= KURS_FRISCHE_S
    };
    let mut stand = alt.clone();
    if faellig {
        match agent()
            .get(KURS_URL)
            .header("accept", "application/json")
            .call()
        {
            Ok(mut r) => {
                let status = r.status().as_u16();
                match r.body_mut().read_json::<Value>() {
                    Ok(roh) if status == 200 => {
                        let (tabelle, datum) = kurse_aus(&roh);
                        if tabelle.is_empty() {
                            stand["fehler"] = json!(format!(
                                "Die Kursquelle antwortete ohne Kurse (HTTP {status})."
                            ));
                        } else {
                            stand = json!({
                                "geholt": jetzt,
                                "datum": datum,
                                "kurse": tabelle,
                                "quelle": "EZB-Referenzkurse ueber frankfurter.dev",
                                "fehler": Value::Null,
                            });
                            if let Err(text) = crate::daten::atomar_schreiben(
                                &kursdatei(p),
                                &serde_json::to_vec_pretty(&stand).unwrap_or_default(),
                                0o600,
                            ) {
                                stand["hinweis"] = json!(format!(
                                    "Kurs geholt, aber nicht abgelegt: {text}"
                                ));
                            }
                        }
                    }
                    Ok(_) => {
                        stand["fehler"] = json!(format!("Die Kursquelle antwortete mit HTTP {status}."));
                    }
                    Err(e) => {
                        stand["fehler"] = json!(format!("Antwort nicht lesbar ({status}): {e}"));
                    }
                }
            }
            Err(e) => {
                stand["fehler"] = json!(format!("Kein Abruf moeglich: {e}"));
            }
        }
    }
    let geholt = stand["geholt"].as_u64().unwrap_or(0);
    stand["alter_s"] = json!(jetzt.saturating_sub(geholt));
    stand["veraltet"] = json!(geholt == 0 || jetzt.saturating_sub(geholt) >= KURS_FRISCHE_S);
    stand["frische_s"] = json!(KURS_FRISCHE_S);
    stand
}

/// Euro-Betrag zu einem Betrag in `waehrung` — `None`, wenn kein Kurs da ist.
///
/// Kein Rückfall auf 1.0 und keine Schätzung: ohne Kurs gibt es keine Zahl
/// (DESIGN, Euro-Anzeige 15.11.).
pub fn in_euro(betrag: &Value, waehrung: &str, kurse: &Value) -> Option<f64> {
    let w = waehrung.trim().to_uppercase();
    if w == "EUR" {
        return betrag.as_str().and_then(|s| s.trim().parse::<f64>().ok());
    }
    let kurs = kurse["kurse"][&w].as_f64()?;
    let zahl = betrag
        .as_str()
        .and_then(|s| s.trim().parse::<f64>().ok())
        .or_else(|| betrag.as_f64())?;
    Some((zahl * kurs * 100.0).round() / 100.0)
}

// ------------------------------------------------------------- Abruf

/// Die Herkunft, die zu einem Anbieter-Typ gehoert. Wird **immer** mitgeliefert.
fn herkunft(typ: &str, basis: &str) -> Value {
    match typ {
        "deepseek" => json!({
            "quelle": "offizielle API",
            "belegtheit": "dokumentiert",
            "endpunkt": format!("GET {basis}/user/balance"),
        }),
        "ollama" => json!({
            "quelle": "kein Abruf noetig",
            "belegtheit": "dokumentiert",
            "endpunkt": "",
        }),
        _ => json!({
            "quelle": "unbekannt",
            "belegtheit": "unbekannt",
            "endpunkt": "",
        }),
    }
}

/// DeepSeek fragen. `Ok(roh)` ist die unveraenderte Antwort, `Err` die
/// Gateway-Antwort mit benanntem Code.
fn deepseek_abrufen(basis: &str, schluessel: &str) -> Result<Value, Value> {
    let host = host_von(basis);
    let url = format!("{basis}/user/balance");
    let mut r = agent()
        .get(&url)
        .header("authorization", &format!("Bearer {schluessel}"))
        .header("accept", "application/json")
        .call()
        .map_err(|e| crate::deepseek::fehler_bei_aufruf(&e, &host, ABRUF))?;
    let status = r.status().as_u16();
    let retry = retry_after(r.headers().get("retry-after").and_then(|v| v.to_str().ok()));
    let roh: Value = r
        .body_mut()
        .read_json()
        .map_err(|e| fehlerantwort("anbieter_fehler", &format!("Antwort nicht lesbar ({status}): {e}")))?;
    if status != 200 {
        let mut f = crate::deepseek::statusfehler(status, &roh, &host);
        if let Some(s) = retry {
            f["fehler"]["retry_after"] = json!(s);
        }
        return Err(f);
    }
    Ok(json!({"roh": roh, "retry_after": retry}))
}

/// Ein Eintrag je Anbieter: was wir wissen, woher, wie alt.
///
/// `neu` erzwingt einen Abruf -- aber **nicht** gegen ein laufendes
/// `Retry-After` (ROADMAP: „`Retry-After` bindet auch den Knopf").
/// `kurse` ist der Stand aus [`kurse`]; leer heisst: keine Umrechnung, und
/// dann steht `euro: null` da statt einer erfundenen Zahl.
pub fn eintrag(
    p: &crate::daten::Pfade,
    id: &str,
    a: &Value,
    jetzt: u64,
    neu: bool,
    kurse: &Value,
) -> Value {
    let typ = a["typ"].as_str().unwrap_or("").trim().to_string();
    let basis = match typ.as_str() {
        "deepseek" => crate::deepseek::basis_aus(a["adresse"].as_str()),
        _ => a["adresse"].as_str().unwrap_or("").trim_end_matches('/').to_string(),
    };
    let mut e = json!({
        "id": id,
        "bezeichnung": a["bezeichnung"].as_str().unwrap_or(id),
        "typ": typ,
        "herkunft": herkunft(&typ, &basis),
        "pools": [],
        "zustand": "unbekannt",
    });
    match art_von(&typ) {
        Art::Lokal => {
            e["zustand"] = json!("kein_guthaben_noetig");
            e["hinweis"] = json!("Laeuft im eigenen Netz -- es gibt kein Guthaben abzurechnen.");
            e["herkunft"]["belegtheit"] = json!("dokumentiert");
            return e;
        }
        Art::NichtAbrufbar => {
            e["zustand"] = json!("nicht_abrufbar");
            e["hinweis"] = json!(nicht_abrufbar_grund(&typ));
            return e;
        }
        Art::Abrufbar => {}
    }
    // Ab hier: Abruf moeglich. Erst der gespeicherte Stand.
    let alt = gespeichert(p, id);
    let mut geholt = alt["geholt"].as_u64();
    let gesperrt_bis = alt["gesperrt_bis"].as_u64().unwrap_or(0);
    let faellig = neu || geholt.map(|g| jetzt.saturating_sub(g) >= FRISCHE_S).unwrap_or(true);
    let durch_retry_gesperrt = jetzt < gesperrt_bis;
    let mut grund_kein_abruf: Option<String> = None;
    if faellig && durch_retry_gesperrt {
        grund_kein_abruf = Some(format!(
            "Naechster Abruf erst in {} s (Retry-After des Anbieters oder Abstand nach einem Fehler).",
            gesperrt_bis - jetzt
        ));
    }
    if faellig && !durch_retry_gesperrt {
        let schluessel = crate::daten::schluessel_lesen(p, id)
            .or_else(schluessel_aus_umgebung);
        match schluessel.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
            None => {
                e["zustand"] = json!("nicht_abrufbar");
                e["hinweis"] = json!(format!(
                    "Kein Schluessel fuer {id} -- Guthaben ist ohne Anmeldung nicht abrufbar."
                ));
                return e;
            }
            Some(k) => match deepseek_abrufen(&basis, k) {
                Ok(r) => {
                    let roh = &r["roh"];
                    let pools = pools_deepseek(roh);
                    // Der Stand gehoert in den Verlauf -- daraus entsteht die
                    // Abrechnungsseite (DESIGN „Verbrauch" 15.11.2026).
                    verlauf_notieren(p, id, jetzt, &pools);
                    e["pools"] = Value::Array(pools);
                    e["verfuegbar"] = roh["is_available"].clone();
                    e["zustand"] = json!("gut");
                    e["geholt"] = json!(jetzt);
                    geholt = Some(jetzt);
                    let neu_stand = json!({
                        "geholt": jetzt,
                        "roh": roh,
                        "gesperrt_bis": r["retry_after"].as_u64().map(|s| jetzt + s).unwrap_or(0),
                    });
                    if let Err(text) = schreiben(p, id, &neu_stand) {
                        // Gespeichert oder nicht: die Zahl ist gemessen. Der
                        // Fehler wird gesagt, nicht verschluckt.
                        e["hinweis"] = json!(format!("Abruf gelungen, aber nicht abgelegt: {text}"));
                    }
                }
                Err(f) => {
                    e["zustand"] = json!("abruf_gescheitert");
                    e["fehler"] = f["fehler"].clone();
                    // Auch ein Fehler wird festgehalten: `Retry-After` des
                    // Anbieters, sonst der Mindestabstand. Ohne das fragte
                    // jeder Aufruf der Oberflaeche den Anbieter erneut --
                    // bei 401 wie bei 500.
                    let sperre = f["fehler"]["retry_after"].as_u64().unwrap_or(FEHLER_ABSTAND_S);
                    // Die Ursache wird mit abgelegt: sonst stuende waehrend der
                    // Sperre nur "wartet noch" da, und der Grund (falscher
                    // Schluessel, kein Guthaben) waere unsichtbar.
                    let stand = json!({"geholt": geholt, "roh": alt["roh"],
                                       "gesperrt_bis": jetzt + sperre, "letzter_fehler": f["fehler"]});
                    let _ = schreiben(p, id, &stand);
                    e["gesperrt_bis"] = json!(jetzt + sperre);
                    // Ist ein alter Stand da, wird er gezeigt -- als alter.
                    if let Some(roh) = alt.get("roh").filter(|r| !r.is_null()) {
                        e["pools"] = Value::Array(pools_deepseek(roh));
                        e["verfuegbar"] = roh["is_available"].clone();
                    }
                }
            },
        }
    } else if geholt.is_some() {
        // Nicht faellig: den gespeicherten Stand zeigen.
        if let Some(roh) = alt.get("roh").filter(|r| !r.is_null()) {
            e["pools"] = Value::Array(pools_deepseek(roh));
            e["verfuegbar"] = roh["is_available"].clone();
            e["zustand"] = json!("gut");
        }
    }
    if let Some(g) = geholt {
        e["geholt"] = json!(g);
        e["alter_s"] = json!(jetzt.saturating_sub(g));
        e["veraltet"] = json!(jetzt.saturating_sub(g) >= FRISCHE_S);
    } else {
        e["veraltet"] = json!(true);
    }
    if gesperrt_bis > jetzt {
        e["gesperrt_bis"] = json!(gesperrt_bis);
    }
    if let Some(g) = grund_kein_abruf {
        e["hinweis"] = json!(g);
    }
    // Waehrend der Sperre bleibt die letzte Ursache sichtbar.
    if e["fehler"].is_null() {
        if let Some(f) = alt.get("letzter_fehler").filter(|f| f.is_object()) {
            if e["pools"].as_array().map(|a| a.is_empty()).unwrap_or(true) {
                e["fehler"] = f.clone();
            }
        }
    }
    if e["pools"].as_array().map(|a| a.is_empty()).unwrap_or(true) && e["zustand"] == "gut" {
        e["zustand"] = json!("unbekannt");
        e["hinweis"] = json!("Der Anbieter hat keine Waehrung gemeldet.");
    }
    mit_euro(&mut e, kurse);
    e
}

/// Euro-Betraege und die Summe je Anbieter eintragen (DESIGN, Euro-Anzeige
/// 15.11.2026). Die **einzige** Stelle, die rechnet -- die Oberflaeche zeigt
/// nur, was hier steht (Regel 10g: nicht zwei Stellen dasselbe rechnen).
///
/// Der Originalbetrag bleibt die Zahl; `euro` steht daneben. `summe_euro`
/// wird nur gesetzt, wenn **alle** Pools umgerechnet werden konnten --
/// sonst waere die Summe kleiner als das Konto und saehe trotzdem aus wie
/// das Ganze (Regel: Summen gegen die Gesamtzahl pruefen).
pub fn mit_euro(e: &mut Value, kurse: &Value) {
    let Some(pools) = e["pools"].as_array().cloned() else { return };
    let mut neu = Vec::with_capacity(pools.len());
    let mut summe = 0.0f64;
    let mut vollstaendig = !pools.is_empty();
    let mut waehrungen = Vec::new();
    for mut pool in pools {
        let waehrung = pool["waehrung"].as_str().unwrap_or("").to_string();
        waehrungen.push(waehrung.clone());
        match in_euro(&pool["gesamt"], &waehrung, kurse) {
            Some(v) => {
                summe += v;
                pool["euro"] = json!((v * 100.0).round() / 100.0);
            }
            None => {
                pool["euro"] = Value::Null;
                vollstaendig = false;
            }
        }
        // Dieselbe Umrechnung fuer die beiden Teilbetraege -- nicht in der
        // Oberflaeche nachgerechnet (Regel 10g).
        for feld in ["aufgeladen", "geschenkt"] {
            let wert = in_euro(&pool[feld], &waehrung, kurse);
            pool[format!("euro_{feld}")] = match wert {
                Some(v) => json!((v * 100.0).round() / 100.0),
                None => Value::Null,
            };
        }
        neu.push(pool);
    }
    if !neu.is_empty() {
        e["pools"] = Value::Array(neu);
    }
    if vollstaendig {
        e["summe_euro"] = json!((summe * 100.0).round() / 100.0);
        e["summe_waehrungen"] = json!(waehrungen);
    } else if !waehrungen.is_empty() {
        e["summe_waehrungen"] = json!(waehrungen);
    }
}

/// Warum dieser Typ nichts liefert -- im Klartext, nie stillschweigend leer.
fn nicht_abrufbar_grund(typ: &str) -> String {
    match typ {
        "anthropic" => concat!(
            "Anthropic gibt das Guthaben nur ueber die Usage/Cost-API heraus, ",
            "und die verlangt einen Admin-Schluessel. Abrechnung ansehen: ",
            "console.anthropic.com/settings/billing"
        )
        .to_string(),
        "" => "Der Anbieter hat keinen Typ -- ohne Typ gibt es keinen Adapter.".to_string(),
        andere => format!(
            "Fuer den Typ '{andere}' gibt es keinen Adapter -- es wird keine Zahl erfunden."
        ),
    }
}

// ------------------------------------------------- Kontostand-Verlauf

/// So viele Staende werden behalten. Bei einem Abruf alle 10 Minuten sind
/// das gut drei Tage im Minutenraster -- genug fuer einen Vergleich, klein
/// genug fuer ein Geraet mit 462 MB.
pub const VERLAUF_MAX: usize = 500;

fn verlaufdatei(p: &crate::daten::Pfade, id: &str) -> std::path::PathBuf {
    p.state.join("quota").join(format!("{id}-verlauf.json"))
}

/// Einen Kontostand an den Verlauf haengen (Ringpuffer, aeltestes faellt weg).
///
/// Ohne diesen Verlauf gibt es keine Abrechnungsseite: DeepSeek hat **keinen**
/// Usage-Endpunkt, nur `/user/balance` (DESIGN „Verbrauch" 15.11.2026).
pub fn verlauf_notieren(p: &crate::daten::Pfade, id: &str, jetzt: u64, pools: &[Value]) {
    if !crate::daten::id_gueltig(id) || pools.is_empty() {
        return;
    }
    let mut liste: Vec<Value> = std::fs::read_to_string(verlaufdatei(p, id))
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .and_then(|v| v.as_array().cloned())
        .unwrap_or_default();
    let betraege: Vec<Value> = pools
        .iter()
        .map(|b| json!({"waehrung": b["waehrung"], "gesamt": b["gesamt"]}))
        .collect();
    liste.push(json!({"zeit": jetzt, "pools": betraege}));
    if liste.len() > VERLAUF_MAX {
        let weg = liste.len() - VERLAUF_MAX;
        liste.drain(0..weg);
    }
    let d = p.state.join("quota");
    if std::fs::create_dir_all(&d).is_err() {
        return;
    }
    if let Ok(text) = serde_json::to_vec(&Value::Array(liste)) {
        // Der Verlauf ist Beiwerk: ein Schreibfehler darf den Abruf nicht
        // kippen, aber er wird auch nicht als Erfolg ausgegeben.
        let _ = crate::daten::atomar_schreiben(&verlaufdatei(p, id), &text, 0o600);
    }
}

/// Die Aenderung je Waehrung zwischen dem aeltesten und dem neuesten Stand
/// eines Anbieters (positiv = mehr Guthaben). Je Waehrung getrennt -- die
/// Waehrungen werden hier nicht vermischt (Regel der Guthaben-Anzeige).
pub fn veraenderung(staende: &[Value]) -> Value {
    let mut raus = serde_json::Map::new();
    // Ohne zwei Staende gibt es keine Veraenderung -- 0.0 waere die
    // Behauptung "nichts verbraucht", und die ist nicht gemessen.
    if staende.len() < 2 {
        return Value::Object(raus);
    }
    let (Some(erst), Some(letzt)) = (staende.first(), staende.last()) else {
        return Value::Object(raus);
    };
    let leer = Vec::new();
    let a = erst["pools"].as_array().unwrap_or(&leer);
    let b = letzt["pools"].as_array().unwrap_or(&leer);
    for e in a {
        let w = e["waehrung"].as_str().unwrap_or("");
        let alt = e["gesamt"].as_str().and_then(|s| s.trim().parse::<f64>().ok());
        let neu = b
            .iter()
            .find(|x| x["waehrung"].as_str() == Some(w))
            .and_then(|x| x["gesamt"].as_str())
            .and_then(|s| s.trim().parse::<f64>().ok());
        if let (Some(alt), Some(neu)) = (alt, neu) {
            raus.insert(w.to_string(), json!(((neu - alt) * 100.0).round() / 100.0));
        }
    }
    Value::Object(raus)
}

/// `abrechnung` fuer die Verbrauchsseite: je Anbieter die Staende und die
/// Veraenderung ueber den Zeitraum. `tage` begrenzt die Zahl der Staende
/// nicht (der Verlauf ist schon ein Ringpuffer), sondern nur die Auswahl.
pub fn guthaben_verlauf(p: &crate::daten::Pfade, _tage: usize) -> Value {
    let (liste, _) = crate::daten::anbieter_laden(p);
    let mut raus = Vec::new();
    for (id, a) in &liste {
        if a.get("an").and_then(Value::as_bool) == Some(false) {
            continue;
        }
        if art_von(a["typ"].as_str().unwrap_or("")) != Art::Abrufbar {
            continue;
        }
        let staende: Vec<Value> = std::fs::read_to_string(verlaufdatei(p, id))
            .ok()
            .and_then(|t| serde_json::from_str::<Value>(&t).ok())
            .and_then(|v| v.as_array().cloned())
            .unwrap_or_default();
        let mut e = json!({
            "id": id,
            "bezeichnung": a["bezeichnung"].as_str().unwrap_or(id),
            "staende": staende,
            "anzahl": staende.len(),
            "veraenderung": veraenderung(&staende),
        });
        if staende.len() < 2 {
            e["hinweis"] = json!(concat!(
                "Noch kein Verlauf: die Abrechnung braucht mindestens zwei ",
                "Kontostaende. Der Anbieter hat keinen Usage-Endpunkt, ",
                "deshalb wird der Kontostand mitgeschrieben."
            ));
        }
        raus.push(e);
    }
    json!({
        "anbieter": raus,
        "hinweis": "Abrechnung laut Anbieter (Kontostand-Verlauf). Tokens zaehlt Chimera selbst -- beides steht nebeneinander, umgerechnet wird nichts.",
    })
}

// ------------------------------------------------------------- Op

/// `op: quota_lesen`. `{ "neu": true }` erzwingt einen Abruf (Knopf),
/// `{ "id": "…" }` beschraenkt sich auf einen Anbieter.
pub fn op_lesen(p: &crate::daten::Pfade, anfrage: &Value, jetzt: u64) -> Value {
    let neu = anfrage.get("neu").and_then(Value::as_bool).unwrap_or(false);
    let nur = anfrage.get("id").and_then(Value::as_str).filter(|s| !s.is_empty());
    if let Some(id) = nur {
        if !crate::daten::id_gueltig(id) {
            return fehlerantwort("id_ungueltig", "Die Anfrage braucht eine gueltige \"id\".");
        }
    }
    let (liste, _) = crate::daten::anbieter_laden(p);
    // Erst die Ablage lesen. Ein Netzabruf fuer Kurse lohnt nur, wenn
    // ueberhaupt ein Eintrag Betraege hat -- sonst fragt ein Geraet ohne
    // Anbieter bei jedem Aufruf der Oberflaeche eine Kursquelle (DESIGN,
    // Euro-Anzeige 15.11.).
    let mut kursstand = kurse_gespeichert(p);
    let mut raus = Vec::new();
    for (id, a) in &liste {
        if let Some(n) = nur {
            if n != id {
                continue;
            }
        }
        if a.get("an").and_then(Value::as_bool) == Some(false) {
            continue;
        }
        raus.push(eintrag(p, id, a, jetzt, neu, &kursstand));
    }
    if let Some(id) = nur {
        if raus.is_empty() {
            return fehlerantwort("anbieter_unbekannt", &format!("Unbekannter Anbieter: {id}"));
        }
    }
    // Jetzt lohnt der Kurs: nur wenn ein Eintrag Betraege traegt.
    let braucht = raus.iter().any(|e| {
        e["pools"].as_array().map(|a| !a.is_empty()).unwrap_or(false)
    });
    if braucht {
        // `neu` heisst: der Nutzer hat den Knopf gedrueckt. Dann darf auch
        // der Kurs nachgeladen werden -- hoechstens alle 10 Minuten.
        let frisch = kurse(p, jetzt, neu);
        if frisch["kurse"].is_object() {
            kursstand = frisch;
            for e in &mut raus {
                mit_euro(e, &kursstand);
            }
        } else if kursstand["kurse"].is_null() {
            kursstand = frisch;             // kein Stand da: Fehler zeigen
        }
    }
    json!({"ok": true, "jetzt": jetzt, "frische_s": FRISCHE_S,
           "kurse": kursstand, "anbieter": raus})
}

/// Derselbe Eintrag fuer genau einen Anbieter -- fuer Tests und die Tuer.
pub fn eintrag_von(p: &crate::daten::Pfade, id: &str, jetzt: u64, neu: bool) -> Value {
    let (liste, _) = crate::daten::anbieter_laden(p);
    // Kurse nur aus der Ablage: `eintrag_von` ist die Tuer fuer einen
    // einzelnen Anbieter und soll keinen zweiten Netzweg oeffnen (Regel 5n).
    let kurse = kurse_gespeichert(p);
    match liste.iter().find(|(i, _)| i == id) {
        Some((_, a)) => eintrag(p, id, a, jetzt, neu, &kurse),
        None => fehlerantwort("anbieter_unbekannt", &format!("Unbekannter Anbieter: {id}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(n: &str) -> crate::daten::Pfade {
        let d = std::env::temp_dir().join(format!("chimera-quota-{n}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        crate::daten::Pfade::neu(d.join("config"), d.join("state"))
    }

    fn deepseek(pf: &crate::daten::Pfade, adresse: &str) {
        crate::daten::anbieter_speichern(
            pf,
            "ds",
            &json!({"typ": "deepseek", "bezeichnung": "DeepSeek", "adresse": adresse}),
        )
        .unwrap();
        crate::daten::schluessel_setzen(pf, "ds", "sk-test").unwrap();
    }

    #[test]
    fn pools_bleiben_je_waehrung_getrennt() {
        // OpenMinis: "currencies are never converted or summed". Zwei
        // Waehrungen sind zwei Pools, nicht eine Zahl.
        let roh = json!({"is_available": true, "balance_infos": [
            {"currency": "CNY", "total_balance": "12.34", "granted_balance": "2.34", "topped_up_balance": "10.00"},
            {"currency": "USD", "total_balance": "1.00", "granted_balance": "0.00", "topped_up_balance": "1.00"},
        ]});
        let p = pools_deepseek(&roh);
        assert_eq!(p.len(), 2);
        assert_eq!(p[0]["waehrung"], "CNY");
        assert_eq!(p[1]["waehrung"], "USD");
        assert_eq!(p[0]["gesamt"], "12.34");
        // Kein Summenfeld, keine Umrechnung.
        assert!(p[0].get("gesamt_eur").is_none());
    }

    #[test]
    fn pools_ohne_waehrung_werden_nicht_erfunden() {
        let p = pools_deepseek(&json!({"balance_infos": [{"total_balance": "3"}]}));
        assert!(p.is_empty());
        assert!(pools_deepseek(&json!({})).is_empty());
    }

    #[test]
    fn nur_sekunden_bei_retry_after_sonst_nichts() {
        assert_eq!(retry_after(Some("42")), Some(42));
        assert_eq!(retry_after(Some(" 7 ")), Some(7));
        // Ein HTTP-Datum wird nicht gedeutet -- lieber kein Wert als ein falscher.
        assert_eq!(retry_after(Some("Wed, 21 Oct 2026 07:28:00 GMT")), None);
        assert_eq!(retry_after(None), None);
    }

    #[test]
    fn jeder_typ_hat_seine_art() {
        assert_eq!(art_von("deepseek"), Art::Abrufbar);
        assert_eq!(art_von("ollama"), Art::Lokal);
        assert_eq!(art_von("anthropic"), Art::NichtAbrufbar);
        assert_eq!(art_von("litellm"), Art::NichtAbrufbar);
    }

    #[test]
    fn lokal_und_unbekannt_sagen_warum_ohne_netz() {
        let pf = p("arten");
        crate::daten::anbieter_speichern(&pf, "lan", &json!({"typ": "ollama", "bezeichnung": "L", "adresse": "http://x:11434"})).unwrap();
        let e = eintrag_von(&pf, "lan", 1000, false);
        assert_eq!(e["zustand"], "kein_guthaben_noetig");
        assert!(e["hinweis"].as_str().unwrap().contains("eigenen Netz"));

        crate::daten::anbieter_speichern(&pf, "abo", &json!({"typ": "anthropic", "bezeichnung": "A"})).unwrap();
        let e = eintrag_von(&pf, "abo", 1000, false);
        assert_eq!(e["zustand"], "nicht_abrufbar");
        let h = e["hinweis"].as_str().unwrap();
        assert!(h.contains("Admin-Schluessel"), "{h}");
        assert!(h.contains("console.anthropic.com"), "Link fehlt: {h}");

        crate::daten::anbieter_speichern(&pf, "fremd", &json!({"typ": "litellm", "bezeichnung": "F"})).unwrap();
        let e = eintrag_von(&pf, "fremd", 1000, false);
        assert!(e["hinweis"].as_str().unwrap().contains("litellm"));
    }

    #[test]
    fn ohne_schluessel_kein_abruf_aber_eine_auskunft() {
        let pf = p("kein-key");
        crate::daten::anbieter_speichern(&pf, "ds", &json!({"typ": "deepseek", "bezeichnung": "D", "adresse": "http://127.0.0.1:1"})).unwrap();
        let e = eintrag_von(&pf, "ds", 1000, false);
        assert_eq!(e["zustand"], "nicht_abrufbar");
        assert!(e["hinweis"].as_str().unwrap().contains("Kein Schluessel"));
    }

    #[test]
    fn herkunft_wird_immer_mitgeliefert() {
        let pf = p("herkunft");
        deepseek(&pf, "http://127.0.0.1:1");
        let e = eintrag_von(&pf, "ds", 1000, false);
        assert_eq!(e["herkunft"]["quelle"], "offizielle API");
        assert_eq!(e["herkunft"]["belegtheit"], "dokumentiert");
        assert!(e["herkunft"]["endpunkt"].as_str().unwrap().contains("/user/balance"));
    }

    #[test]
    fn abruf_holt_die_zahlen_und_legt_sie_ab() {
        let (b, h) = crate::ollama::tests::server(vec![
            (200, r#"{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"12.34","granted_balance":"2.34","topped_up_balance":"10.00"}]}"#.into()),
        ]);
        let pf = p("abruf");
        deepseek(&pf, &b);
        let e = eintrag_von(&pf, "ds", 5000, false);
        assert_eq!(e["zustand"], "gut", "{e}");
        assert_eq!(e["pools"][0]["waehrung"], "CNY");
        assert_eq!(e["pools"][0]["gesamt"], "12.34");
        assert_eq!(e["verfuegbar"], true);
        assert_eq!(e["geholt"], 5000);
        assert_eq!(e["alter_s"], 0);
        assert_eq!(e["veraltet"], false);
        // Abgelegt: ein zweiter Aufruf fragt nicht wieder (der Testserver
        // haette keine zweite Antwort und wuerde als fehlender Aufruf enden).
        let anfragen = h.join().unwrap();
        assert!(anfragen[0].starts_with("GET /user/balance"), "{}", anfragen[0]);
        assert!(anfragen[0].to_lowercase().contains("authorization: bearer sk-test"));
        let e2 = eintrag_von(&pf, "ds", 5100, false);
        assert_eq!(e2["pools"][0]["gesamt"], "12.34", "{e2}");
        assert_eq!(e2["alter_s"], 100);
        // Und es wurde **nicht** wieder gefragt: der Testserver haette keine
        // zweite Antwort, der Zustand waere dann "abruf_gescheitert".
        assert_eq!(e2["zustand"], "gut", "innerhalb der Frist wird nicht neu geholt: {e2}");
    }

    #[test]
    fn veraltet_wird_gezeigt_nicht_versteckt_und_dann_erneuert() {
        let (b, h) = crate::ollama::tests::server(vec![
            (200, r#"{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"1.00"}]}"#.into()),
            (200, r#"{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"2.00"}]}"#.into()),
        ]);
        let pf = p("alter");
        deepseek(&pf, &b);
        assert_eq!(eintrag_von(&pf, "ds", 1000, false)["pools"][0]["gesamt"], "1.00");
        // Nach der Frist: der alte Wert wird gezeigt, aber als veraltet --
        // und gleichzeitig neu geholt.
        let e = eintrag_von(&pf, "ds", 1000 + FRISCHE_S, false);
        assert_eq!(e["pools"][0]["gesamt"], "2.00", "{e}");
        assert_eq!(e["geholt"], 1000 + FRISCHE_S);
        h.join().unwrap();
    }

    #[test]
    fn retry_after_bindet_auch_den_knopf() {
        let (b, h) = crate::ollama::tests::server(vec![(
            429,
            r#"{"error":{"message":"slow down"}}"#.into(),
        )]);
        let pf = p("retry");
        deepseek(&pf, &b);
        // Der Testserver schickt kein Retry-After -- also zaehlt hier der
        // Fehler selbst: kein alter Stand, Zustand gescheitert.
        let e = eintrag_von(&pf, "ds", 1000, false);
        assert_eq!(e["zustand"], "abruf_gescheitert", "{e}");
        assert_eq!(e["fehler"]["code"], "ausgelastet");
        h.join().unwrap();

        // Jetzt mit gesetztem Retry-After: der erzwungene Abruf darf nicht
        // rausgehen. Der Testserver hat keine Antwort mehr uebrig -- ginge
        // doch einer raus, scheiterte der Test beim join.
        let pf2 = p("retry2");
        let (b2, h2) = crate::ollama::tests::server(vec![
            (429, r#"{"error":{"message":"slow down"}}"#.into()),
        ]);
        deepseek(&pf2, &b2);
        eintrag_von(&pf2, "ds", 1000, false);
        h2.join().unwrap();
        // Retry-After von Hand in die Ablage schreiben, wie es die Antwort
        // mit Kopfzeile getan haette.
        let mut stand = gespeichert(&pf2, "ds");
        stand["gesperrt_bis"] = json!(2000);
        schreiben(&pf2, "ds", &stand).unwrap();
        let e = eintrag_von(&pf2, "ds", 1500, true);
        assert!(e["hinweis"].as_str().unwrap().contains("Retry-After"), "{e}");
        assert_eq!(e["gesperrt_bis"], 2000);
    }

    /// Ein kleiner Server, der **Kopfzeilen** setzen kann -- die Attrappe in
    /// `ollama::tests` schickt nur Content-Type und -Length, `Retry-After`
    /// kaeme damit nie an.
    fn antwort_mit_kopf(status: u16, kopf: &'static str, koerper: &'static str) -> String {
        use std::io::{Read, Write};
        let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let basis = format!("http://{}", l.local_addr().unwrap());
        std::thread::spawn(move || {
            let (mut s, _) = l.accept().unwrap();
            let mut puf = [0u8; 4096];
            let _ = s.read(&mut puf);
            let a = format!(
                "HTTP/1.1 {status} X\r\nContent-Type: application/json\r\n{kopf}Content-Length: {}\r\nConnection: close\r\n\r\n{koerper}",
                koerper.len()
            );
            s.write_all(a.as_bytes()).unwrap();
        });
        basis
    }

    #[test]
    fn retry_after_aus_der_kopfzeile_sperrt_den_abruf() {
        let b = antwort_mit_kopf(429, "Retry-After: 120\r\n", r#"{"error":{"message":"slow"}}"#);
        let pf = p("kopfzeile");
        deepseek(&pf, &b);
        let e = eintrag_von(&pf, "ds", 1000, false);
        assert_eq!(e["zustand"], "abruf_gescheitert", "{e}");
        assert_eq!(e["fehler"]["retry_after"], 120, "{e}");
        // Die Sperre steht in der Ablage und bindet den naechsten Abruf --
        // auch den erzwungenen, ohne dass ein zweiter Aufruf rausgeht.
        assert_eq!(gespeichert(&pf, "ds")["gesperrt_bis"], 1120);
        let e2 = eintrag_von(&pf, "ds", 1050, true);
        assert!(e2["hinweis"].as_str().unwrap().contains("Retry-After"), "{e2}");
    }

    #[test]
    fn ein_fehler_bremst_den_naechsten_abruf() {
        let (b, h) = crate::ollama::tests::server(vec![(
            401,
            r#"{"error":{"message":"bad key"}}"#.into(),
        )]);
        let pf = p("fehler-bremst");
        deepseek(&pf, &b);
        let e = eintrag_von(&pf, "ds", 1000, false);
        assert_eq!(e["zustand"], "abruf_gescheitert", "{e}");
        assert_eq!(e["gesperrt_bis"], 1000 + FEHLER_ABSTAND_S);
        h.join().unwrap();
        // Ein erzwungener Abruf direkt danach geht nicht raus (der Server
        // hat keine zweite Antwort mehr) -- und der Grund bleibt sichtbar.
        let e2 = eintrag_von(&pf, "ds", 1010, true);
        assert!(e2["hinweis"].as_str().unwrap().contains("Naechster Abruf"), "{e2}");
        assert_eq!(e2["fehler"]["code"], "schluessel_falsch", "Grund fehlt: {e2}");
    }

    #[test]
    fn abruf_gescheitert_zeigt_den_alten_stand_als_alten() {
        let (b, h) = crate::ollama::tests::server(vec![
            (200, r#"{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"5.00"}]}"#.into()),
            (500, r#"{"error":{"message":"kaputt"}}"#.into()),
        ]);
        let pf = p("alt-bleibt");
        deepseek(&pf, &b);
        eintrag_von(&pf, "ds", 1000, false);
        let e = eintrag_von(&pf, "ds", 1000 + FRISCHE_S, false);
        assert_eq!(e["zustand"], "abruf_gescheitert", "{e}");
        assert_eq!(e["pools"][0]["gesamt"], "5.00", "der alte Stand fehlt");
        assert_eq!(e["veraltet"], true);
        h.join().unwrap();
    }

    #[test]
    fn ein_abgeschalteter_anbieter_wird_nicht_gefragt() {
        let pf = p("aus");
        crate::daten::anbieter_speichern(&pf, "ds", &json!({"typ": "deepseek", "bezeichnung": "D", "an": false, "adresse": "http://127.0.0.1:1"})).unwrap();
        let a = op_lesen(&pf, &json!({}), 1000);
        assert_eq!(a["ok"], true);
        assert_eq!(a["anbieter"].as_array().unwrap().len(), 0, "{a}");
    }

    #[test]
    fn unbekannter_anbieter_wird_benannt() {
        let pf = p("unbekannt");
        let a = op_lesen(&pf, &json!({"id": "gibtesnicht"}), 1000);
        assert_eq!(a["fehler"]["code"], "anbieter_unbekannt");
        let a = op_lesen(&pf, &json!({"id": "../x"}), 1000);
        assert_eq!(a["fehler"]["code"], "id_ungueltig");
    }

    // ------------------------------------------------------------ Kurse

    #[test]
    fn kurse_werden_zu_euro_je_einheit_gedreht() {
        // Die Quelle nennt Einheiten je Euro; gebraucht wird Euro je Einheit.
        let roh = json!({"base": "EUR", "date": "2026-11-13",
                         "rates": {"USD": 1.1052, "CNY": 7.3738}});
        let (tab, datum) = kurse_aus(&roh);
        assert_eq!(datum, "2026-11-13");
        assert!((tab["USD"] - 0.90481).abs() < 0.00001, "{:?}", tab);
        assert!((tab["CNY"] - 0.13562).abs() < 0.00001, "{:?}", tab);
        // Ein Kurs von 0 waere keine Umrechnung, sondern eine Division durch
        // null -- er wird weggelassen, nicht uebernommen.
        let (tab, _) = kurse_aus(&json!({"rates": {"XXX": 0.0, "YYY": 2.0}}));
        assert!(!tab.contains_key("XXX"));
        assert!(tab.contains_key("YYY"));
    }

    #[test]
    fn ohne_kurs_keine_zahl() {
        let k = json!({"kurse": {"USD": 0.9}});
        assert_eq!(in_euro(&json!("2.00"), "USD", &k), Some(1.8));
        assert_eq!(in_euro(&json!("2.00"), "EUR", &k), Some(2.0));
        // Unbekannte Waehrung: keine Zahl, kein Rueckfall auf 1.0.
        assert_eq!(in_euro(&json!("2.00"), "GBP", &k), None);
        // Kursstand ohne Kurse: ebenfalls keine Zahl.
        assert_eq!(in_euro(&json!("2.00"), "USD", &json!({"fehler": "x"})), None);
        // Unsinniger Betrag: keine Zahl (nicht 0).
        assert_eq!(in_euro(&json!("viel"), "USD", &k), None);
    }

    #[test]
    fn summe_nur_wenn_alle_pools_umgerechnet_sind() {
        let k = json!({"kurse": {"USD": 0.9, "CNY": 0.13}});
        let mut e = json!({"pools": [
            {"waehrung": "USD", "gesamt": "10.00"},
            {"waehrung": "CNY", "gesamt": "100.00"},
        ]});
        mit_euro(&mut e, &k);
        assert_eq!(e["pools"][0]["euro"], 9.0);
        assert_eq!(e["pools"][1]["euro"], 13.0);
        assert_eq!(e["summe_euro"], 22.0);
        assert_eq!(e["summe_waehrungen"], json!(["USD", "CNY"]));

        // Fehlt ein Kurs, gibt es KEINE Summe -- eine kleinere Summe, die wie
        // das ganze Konto aussieht, waere schlimmer als keine.
        let mut e2 = json!({"pools": [
            {"waehrung": "USD", "gesamt": "10.00"},
            {"waehrung": "GBP", "gesamt": "5.00"},
        ]});
        mit_euro(&mut e2, &k);
        assert!(e2.get("summe_euro").is_none(), "{e2}");
        assert_eq!(e2["pools"][1]["euro"], Value::Null);
    }

    #[test]
    fn euro_aendert_den_originalbetrag_nicht() {
        let k = json!({"kurse": {"USD": 0.9}});
        let mut e = json!({"pools": [{"waehrung": "USD", "gesamt": "10.00"}]});
        mit_euro(&mut e, &k);
        assert_eq!(e["pools"][0]["gesamt"], "10.00");
    }

    #[test]
    fn gespeicherte_kurse_werden_gelesen_und_altern() {
        let pf = p("kurse");
        let d = pf.state.join("quota");
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(d.join("kurse.json"),
            json!({"geholt": 1000, "datum": "2026-11-13",
                   "kurse": {"USD": 0.9}}).to_string()).unwrap();
        let k = kurse_gespeichert(&pf);
        assert_eq!(k["datum"], "2026-11-13");
        assert_eq!(k["kurse"]["USD"], 0.9);
        // Ein leerer Pfad ergibt einen leeren Stand, keinen Fehler.
        let leer = p("keine-kurse");
        assert!(kurse_gespeichert(&leer)["kurse"].is_null());
    }

    // -------------------------------------------------- Kontostand-Verlauf

    #[test]
    fn verlauf_haengt_an_und_kippt_das_aelteste() {
        let pf = p("verlauf");
        for i in 0..3u64 {
            verlauf_notieren(&pf, "ds", 1000 + i,
                             &[json!({"waehrung": "USD", "gesamt": format!("{}.00", 10 - i)})]);
        }
        let st: Vec<Value> = serde_json::from_str(
            &std::fs::read_to_string(pf.state.join("quota").join("ds-verlauf.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(st.len(), 3);
        assert_eq!(st[2]["pools"][0]["gesamt"], "8.00");
    }

    #[test]
    fn veraenderung_ist_je_waehrung_und_mit_vorzeichen() {
        let staende = vec![
            json!({"zeit": 1, "pools": [{"waehrung": "USD", "gesamt": "10.00"},
                                        {"waehrung": "CNY", "gesamt": "50.00"}]}),
            json!({"zeit": 2, "pools": [{"waehrung": "USD", "gesamt": "7.50"},
                                        {"waehrung": "CNY", "gesamt": "50.00"}]}),
        ];
        let v = veraenderung(&staende);
        // Abnahme ist negativ: verbraucht heisst weniger Guthaben.
        assert_eq!(v["USD"], -2.5);
        assert_eq!(v["CNY"], 0.0);
        // Ein einzelner Stand ergibt keine Veraenderung, keine Null.
        assert_eq!(veraenderung(&staende[..1]), json!({}));
        assert_eq!(veraenderung(&[]), json!({}));
    }

    #[test]
    fn ohne_verlauf_keine_zahlen_sondern_ein_hinweis() {
        let pf = p("kein-verlauf");
        crate::daten::anbieter_speichern(&pf, "ds", &json!({"typ": "deepseek", "bezeichnung": "D"})).unwrap();
        let a = guthaben_verlauf(&pf, 7);
        let e = &a["anbieter"][0];
        assert_eq!(e["anzahl"], 0);
        assert!(e["hinweis"].as_str().unwrap().contains("Kontostaende"), "{e}");
    }

    #[test]
    fn ein_erzwungener_kursabruf_haelt_den_mindestabstand_ein() {
        let pf = p("kursabstand");
        let d = pf.state.join("quota");
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(d.join("kurse.json"),
            json!({"geholt": 1000, "datum": "2026-11-13",
                   "kurse": {"USD": 0.9}}).to_string()).unwrap();
        // Frisch genug: auch `neu` loest keinen zweiten Abruf aus.
        let k = kurse(&pf, 1000 + 60, true);
        assert_eq!(k["geholt"], 1000, "{k}");
        // Nach dem Mindestabstand darf `neu` wieder -- der Stand kommt dann
        // aus dem Netz oder, ohne Netz, bleibt der alte mit Fehlertext.
        assert!(KURS_MINDESTABSTAND_S < KURS_FRISCHE_S);
    }
}
