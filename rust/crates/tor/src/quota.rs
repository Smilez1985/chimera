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
pub fn eintrag(
    p: &crate::daten::Pfade,
    id: &str,
    a: &Value,
    jetzt: u64,
    neu: bool,
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
                    let stand = json!({"geholt": geholt, "roh": alt["roh"], "gesperrt_bis": jetzt + sperre});
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
    if e["pools"].as_array().map(|a| a.is_empty()).unwrap_or(true) && e["zustand"] == "gut" {
        e["zustand"] = json!("unbekannt");
        e["hinweis"] = json!("Der Anbieter hat keine Waehrung gemeldet.");
    }
    e
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
        raus.push(eintrag(p, id, a, jetzt, neu));
    }
    if let Some(id) = nur {
        if raus.is_empty() {
            return fehlerantwort("anbieter_unbekannt", &format!("Unbekannter Anbieter: {id}"));
        }
    }
    json!({"ok": true, "jetzt": jetzt, "frische_s": FRISCHE_S, "anbieter": raus})
}

/// Derselbe Eintrag fuer genau einen Anbieter -- fuer Tests und die Tuer.
pub fn eintrag_von(p: &crate::daten::Pfade, id: &str, jetzt: u64, neu: bool) -> Value {
    let (liste, _) = crate::daten::anbieter_laden(p);
    match liste.iter().find(|(i, _)| i == id) {
        Some((_, a)) => eintrag(p, id, a, jetzt, neu),
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
        // hat keine zweite Antwort mehr).
        let e2 = eintrag_von(&pf, "ds", 1010, true);
        assert!(e2["hinweis"].as_str().unwrap().contains("Naechster Abruf"), "{e2}");
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
}
