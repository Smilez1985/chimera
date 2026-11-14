//! Freigabe je Werkzeug auf Zeit (DESIGN, Regel "Freigabe je Werkzeug auf
//! Zeit").
//!
//! Der Nutzer entscheidet **je Werkzeug**, in welchem der drei Modi es laeuft
//! (Vorgabe smilez, 14.11.2026: "beide Modi, offen nach Vorschlag, und alles
//! immer offen"):
//!
//! * `positivliste` -- nur Ziele in `positiv` (Vorgabe, vorsichtige Seite),
//! * `offen` -- jedes Ziel ausser `negativ`,
//! * `offen_nach_vorschlag` -- offen **nur fuer Ziele, die der Nutzer
//!   angenommen hat**. Der Agent darf vorschlagen (`freigabe_vorschlag`),
//!   ein Vorschlag wirkt nie von selbst: erst die Annahme traegt das Ziel in
//!   `positiv` ein. Gegenprobe: ein Vorschlag allein oeffnet nichts.
//!
//! **Kein Ablauf mehr (Entscheidung smilez, 13.11.2026).** Eine Freigabe
//! bleibt offen, bis der Nutzer sie schliesst. Ein Ton kann daran erinnern --
//! **opt-in**: `erinnern_alle` ist die Vorgabe **0 (aus)**; wer ihn will,
//! setzt mindestens 60 Sekunden (smilez, 13.11.: der Ton gehoert zu offenen
//! Rueckfragen, nicht zu jeder Freigabe).
//! `bis` steht nur noch als **Lese-Altbestand** in der Datei: ein Eintrag von
//! gestern mit einer Frist in der Vergangenheit gilt weiterhin als
//! `positivliste` -- sonst ginge eine alte Frist rueckwirkend auf.
//!
//! Drei Regeln, die hier zusammenlaufen und deshalb nur hier stehen:
//!
//! * **`negativ` gilt immer** -- auch im offenen Modus, auch gegen einen
//!   Eintrag in `positiv`.
//! * **Der Altbestand wird beim Pruefen ausgewertet**, nicht von einem Timer.
//!   Ein neu gestarteter Dienst darf eine Freigabe nicht verlaengern.
//! * **Die Werkzeugliste ist geschlossen.** Ein unbekannter Name wird
//!   abgelehnt, statt still durchzugehen -- ein Tippfehler soll nichts oeffnen.
//!
//! Die Datei gehoert dem Gateway (`config/freigaben/freigaben.json`, 660). Der Agent
//! liest sie nie; er fragt und bekommt Ja oder Nein mit Grund.

use crate::daten::{atomar_schreiben, Pfade};
use serde_json::{json, Value};
use std::io::Write;

/// Werkzeuge, die freigegeben werden koennen. **Geschlossen**: was hier nicht
/// steht, laesst sich nicht freigeben. Neue Werkzeuge kommen mit ihrem
/// Aufrufer dazu, nicht auf Verdacht.
pub const WERKZEUGE: &[&str] = &["web_suche", "web_abruf", "ssh", "run_command", "tailscale"];

/// Die drei Modi, in denen ein Werkzeug laufen kann. **Geschlossen**: ein
/// unbekannter Modus wird abgelehnt, nicht auf die vorsichtige Seite gebogen --
/// sonst faende niemand, warum seine Einstellung nicht wirkt.
pub const MODI: &[&str] = &["positivliste", "offen", "offen_nach_vorschlag"];

/// So viele Vorschlaege darf ein Werkzeug hoechstens offen haben. Ohne Grenze
/// koennte eine Schleife im Agenten die Datei vollschreiben.
pub const VORSCHLAEGE_MAX: usize = 20;

/// Laenger als das Protokoll nicht, bevor es rotiert.
const PROTOKOLL_MAX: u64 = 512 * 1024;

/// Vorgabe des Erinnerungsabstands: **0 = aus** (opt-in, Entscheidung
/// smilez 13.11.). Der Ton ist fuer offene Rueckfragen gedacht, nicht fuer
/// jede Freigabe.
pub const ERINNERN_VORGABE: u64 = 0;
/// Kuerzer als das waere kein Erinnern, sondern ein Dauerpiepen.
pub const ERINNERN_MIN: u64 = 60;

fn jetzt_s() -> u64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

/// Eigene Ablage unter `config/freigaben/` -- nicht die Datei direkt in
/// `config/`. Grund (am Geraet gefunden, 12.11.2026): Geschrieben wird atomar
/// ueber eine Nebendatei **im selben Ordner**, und `config/` selbst ist fuer
/// das Gateway nur Durchgang (751, Regel 5t). Eine Datei in `config/` waere
/// damit grundsaetzlich nicht speicherbar ("Read-only file system").
pub fn datei(p: &Pfade) -> std::path::PathBuf {
    p.config.join("freigaben").join("freigaben.json")
}

fn protokoll_datei(p: &Pfade) -> std::path::PathBuf {
    p.state.join("log").join("freigabe.log")
}

/// Ein Werkzeug-Eintrag, wie er in der Datei steht. Fehlende Felder haben
/// Vorgaben; die Vorgabe ist immer die vorsichtige Seite.
#[derive(Debug, Clone, PartialEq)]
pub struct Eintrag {
    /// Einer von [`MODI`]. Unbekannte Werte werden beim Lesen zu
    /// `positivliste` -- die vorsichtige Seite.
    pub modus: String,
    /// **Nur Altbestand.** Wann die Freigabe (frueher) ablief. Neue Eintraege
    /// schreiben kein `bis` mehr; gelesen wird es weiter, damit eine Frist von
    /// gestern nicht rueckwirkend aufgeht.
    pub bis: Option<u64>,
    /// Wann die Freigabe geoeffnet wurde. Bleibt beim Speichern der Listen stehen.
    pub seit: Option<u64>,
    /// Alle wie viele Sekunden der Ton erinnert.
    pub erinnern_alle: u64,
    pub positiv: Vec<String>,
    pub negativ: Vec<String>,
    /// Vorschlaege des Agenten, die noch **nicht** angenommen sind. Sie
    /// wirken nie von selbst; erst `annehmen` traegt das Ziel in `positiv`.
    pub vorschlaege: Vec<Vorschlag>,
}

/// Ein Vorschlag des Agenten. `herkunft` steht dabei, damit die Oberflaeche
/// ihn zeigen kann; er ist immer `agent` (der Nutzer schlaegt nichts vor).
#[derive(Debug, Clone, PartialEq)]
pub struct Vorschlag {
    pub ziel: String,
    pub herkunft: String,
    pub seit: u64,
    pub notiz: String,
}

impl Vorschlag {
    fn aus(v: &Value) -> Option<Vorschlag> {
        let ziel = v.get("ziel")?.as_str()?.trim().to_string();
        if ziel.is_empty() {
            return None;
        }
        Some(Vorschlag {
            ziel,
            herkunft: v.get("herkunft").and_then(Value::as_str).unwrap_or("agent").trim().to_string(),
            seit: v.get("seit").and_then(Value::as_u64).unwrap_or(0),
            notiz: v.get("notiz").and_then(Value::as_str).unwrap_or("").trim().to_string(),
        })
    }

    fn als_json(&self) -> Value {
        json!({"ziel": self.ziel, "herkunft": self.herkunft, "seit": self.seit, "notiz": self.notiz})
    }
}

impl Default for Eintrag {
    fn default() -> Self {
        Eintrag {
            modus: "positivliste".into(),
            bis: None,
            seit: None,
            erinnern_alle: ERINNERN_VORGABE,
            positiv: Vec::new(),
            negativ: Vec::new(),
            vorschlaege: Vec::new(),
        }
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
        // 0 heisst "aus"; alles dazwischen (1..59) ist Unsinn und faellt auf
        // die Vorgabe zurueck -- nie auf einen Ton, den niemand bestellt hat.
        let erinnern_alle = v
            .get("erinnern_alle")
            .and_then(Value::as_u64)
            .filter(|s| *s == 0 || *s >= ERINNERN_MIN)
            .unwrap_or(ERINNERN_VORGABE);
        let modus = match v.get("modus").and_then(Value::as_str) {
            Some(m) if MODI.contains(&m) => m.to_string(),
            _ => "positivliste".into(),
        };
        let vorschlaege = v
            .get("vorschlaege")
            .and_then(Value::as_array)
            .map(|a| a.iter().filter_map(Vorschlag::aus).collect())
            .unwrap_or_default();
        Eintrag {
            modus,
            bis: v.get("bis").and_then(Value::as_u64),
            seit: v.get("seit").and_then(Value::as_u64),
            erinnern_alle,
            positiv: texte("positiv"),
            negativ: texte("negativ"),
            vorschlaege,
        }
    }

    /// Heisst der Modus so? Kurzform fuer die Aufrufer.
    pub fn ist_modus(&self, m: &str) -> bool {
        self.modus == m
    }

    /// Steht die Freigabe offen? Ohne Frist (`bis` leer) heisst offen bis zum
    /// Schluss. Ein `bis` aus dem Altbestand zaehlt nur, solange es nicht
    /// vorbei ist -- eine alte Frist darf nicht rueckwirkend aufgehen.
    pub fn ist_offen(&self, jetzt: u64) -> bool {
        // Nur `offen` oeffnet alles. `offen_nach_vorschlag` heisst **nicht**
        // "offen" -- es heisst "offen fuer Angenommenes", und das steht in
        // `positiv`.
        self.ist_modus("offen") && self.bis.map(|b| b > jetzt).unwrap_or(true)
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
            o.modus = "positivliste".into();
        }
        if let Some(m) = e.as_object_mut() {
            m.insert("modus".into(), json!(o.modus));
            // Vorschlaege immer als Liste zeigen -- die Oberflaeche soll nicht
            // zwischen "kein Feld" und "leer" unterscheiden muessen.
            m.insert("vorschlaege".into(), json!(o.vorschlaege.iter().map(Vorschlag::als_json).collect::<Vec<_>>()));
            m.entry("bis").or_insert(Value::Null);
            m.entry("seit").or_insert(o.seit.map(Value::from).unwrap_or(Value::Null));
            m.insert("erinnern_alle".into(), json!(o.erinnern_alle));
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
    // 3. Offene Freigabe: alles andere geht durch, solange sie offen ist.
    if e.ist_offen(jetzt) {
        protokoll(p, jetzt_s(), werkzeug, ziel, "erlaubt", "Freigabe ist offen");
        return antwort(true, "Freigabe ist offen".into(), e.bis);
    }
    // 4. Sonst: fragen, also nicht erlaubt -- mit dem Grund.
    let grund = if e.ist_modus("offen") {
        // Nur Altbestand kann hier landen: ein Eintrag mit `bis` in der
        // Vergangenheit. Neue Eintraege laufen nicht mehr ab.
        "Freigabe ist abgelaufen (Altbestand mit Frist)".to_string()
    } else if e.ist_modus("offen_nach_vorschlag") {
        // Der Modus oeffnet nicht alles -- er oeffnet, was angenommen wurde.
        // Ohne diesen Satz saehe der Agent "keine Freigabe" und schluege
        // nichts vor.
        "nicht angenommen (Modus 'offen nach Vorschlag')".to_string()
    } else if let Some(b) = e.bis {
        format!("keine Freigabe; die letzte lief bis {b} ab")
    } else {
        "keine Freigabe eingetragen".to_string()
    };
    protokoll(p, jetzt, werkzeug, ziel, "abgelehnt", &grund);
    antwort(false, grund, e.bis)
}

fn antwort(erlaubt: bool, grund: String, bis: Option<u64>) -> Value {
    json!({"erlaubt": erlaubt, "grund": grund, "bis": bis})
}

/// Ein Eintrag wird gesetzt. `wert` ist `{modus, erinnern_alle, positiv, negativ}`.
/// Geprueft wird jeder Teil: ein unbekannter Modus, ein zu kurzer
/// Erinnerungsabstand oder ein leeres Ziel waeren sonst stille Fehler.
///
/// **Kein `bis` mehr:** Was ein Aufrufer dennoch mitschickt, wird nicht
/// uebernommen -- eine Frist gaebe es nicht mehr, sie stillschweigend zu
/// speichern waere eine Luege in der Datei. `bis` verschwindet dabei aus dem
/// Eintrag (auch ein alter Altbestand wird damit abgeloest).
pub fn setzen(p: &Pfade, werkzeug: &str, wert: &Value, jetzt: u64) -> Result<Value, (&'static str, String)> {
    if !WERKZEUGE.contains(&werkzeug) {
        return Err((
            "werkzeug_unbekannt",
            format!("Werkzeug \"{werkzeug}\" laesst sich nicht freigeben (bekannt: {}).", WERKZEUGE.join(", ")),
        ));
    }
    let modus = wert.get("modus").and_then(Value::as_str).unwrap_or("positivliste");
    if !MODI.contains(&modus) {
        return Err((
            "wert_ungueltig",
            format!("Modus \"{modus}\" gibt es nicht ({}).", MODI.join(", ")),
        ));
    }
    let erinnern_alle = match wert.get("erinnern_alle") {
        None | Some(Value::Null) => None,
        Some(v) => match v.as_u64() {
            // 0 = aus (Vorgabe, opt-in).
            Some(0) => Some(0),
            Some(s) if s >= ERINNERN_MIN => Some(s),
            Some(s) => {
                return Err((
                    "wert_ungueltig",
                    format!("\"erinnern_alle\" ist 0 (aus) oder mindestens {ERINNERN_MIN} Sekunden (bekam {s}); darunter waere es kein Erinnern, sondern Dauerpiepen."),
                ))
            }
            None => return Err(("wert_ungueltig", format!("\"erinnern_alle\" braucht eine Zahl (Sekunden), bekam {v}."))),
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
    // schicken oft nur `modus`/`erinnern_alle`; wuerden fehlende Listen
    // geleert, loeschte ein Zeitknopf die gepflegten Ziele. Zum Leeren
    // schickt man `[]`.
    let alt = Eintrag::aus(&laden(p)["werkzeuge"][werkzeug]);
    // `seit` gehoert dem Oeffnen: bleibt stehen, solange die Freigabe offen
    // ist, und wird neu gesetzt, wenn sie (wieder) aufgeht.
    let seit = if modus != "offen" || !alt.ist_offen(jetzt) { None } else { alt.seit };
    let seit = if modus == "offen" && seit.is_none() { Some(jetzt) } else { seit };
    let erinnern_alle = erinnern_alle.unwrap_or(alt.erinnern_alle);
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
    // Vorschlaege bleiben stehen: ein Zeitknopf darf nicht die Liste der
    // offenen Vorschlaege loeschen (dieselbe Ueberlegung wie bei `positiv`).
    let vorschlaege: Vec<Value> = alt.vorschlaege.iter().map(Vorschlag::als_json).collect();
    let neu = json!({"modus": modus, "bis": Value::Null, "seit": seit, "erinnern_alle": erinnern_alle,
        "positiv": positiv, "negativ": negativ, "vorschlaege": vorschlaege, "notiz": notiz});
    let mut ganz = laden(p);
    let Some(w) = ganz.get_mut("werkzeuge").and_then(|w| w.as_object_mut()) else {
        return Err(("wert_ungueltig", "Die Freigaben sind kein Objekt.".into()));
    };
    w.insert(werkzeug.to_string(), neu.clone());
    schreiben(p, &ganz).map_err(|e| ("nicht_gespeichert", e))?;
    protokoll(p, jetzt, werkzeug, None, "gesetzt", &beschreibung(&neu));
    Ok(neu)
}

/// Ein Ziel, das ein Werkzeug als Ziel fuehren darf: kein Leerraum, nicht
/// leer, nicht ueberlang. Dieselbe Form prueft `setzen` fuer die Listen --
/// hier steht sie einmal fuer beide.
fn ziel_pruefen(ziel: &str) -> Result<String, (&'static str, String)> {
    let z = ziel.trim();
    if z.is_empty() {
        return Err(("wert_ungueltig", "Das Ziel ist leer.".into()));
    }
    if z.chars().any(char::is_whitespace) {
        return Err(("wert_ungueltig", format!("Das Ziel \"{z}\" enthaelt Leerraum.")));
    }
    if z.chars().count() > 80 {
        return Err(("wert_ungueltig", "Das Ziel ist laenger als 80 Zeichen.".into()));
    }
    Ok(z.to_string())
}

/// Einen Eintrag lesen, aendern, schreiben. Ein Ort fuer das Muster, damit
/// die drei Wege (Vorschlag, annehmen, verwerfen) nicht dreimal verschieden
/// pruefen (Regel 10g).
fn aendern<F>(p: &Pfade, werkzeug: &str, f: F) -> Result<Value, (&'static str, String)>
where
    F: FnOnce(&mut Eintrag) -> Result<String, (&'static str, String)>,
{
    if !WERKZEUGE.contains(&werkzeug) {
        return Err((
            "werkzeug_unbekannt",
            format!("Werkzeug \"{werkzeug}\" lasst sich nicht freigeben (bekannt: {}).", WERKZEUGE.join(", ")),
        ));
    }
    let mut ganz = laden(p);
    let alt = Eintrag::aus(&ganz["werkzeuge"][werkzeug]);
    let mut e = alt.clone();
    let meldung = f(&mut e)?;
    if e == alt {
        return Ok(json!({"ok": true, "meldung": meldung, "freigabe": ganz["werkzeuge"][werkzeug].clone()}));
    }
    let neu = json!({
        "modus": e.modus, "bis": e.bis, "seit": e.seit, "erinnern_alle": e.erinnern_alle,
        "positiv": e.positiv, "negativ": e.negativ,
        "vorschlaege": e.vorschlaege.iter().map(Vorschlag::als_json).collect::<Vec<_>>(),
        "notiz": ganz["werkzeuge"][werkzeug]["notiz"].as_str().unwrap_or("").trim().to_string(),
    });
    let Some(w) = ganz.get_mut("werkzeuge").and_then(|w| w.as_object_mut()) else {
        return Err(("wert_ungueltig", "Die Freigaben sind kein Objekt.".into()));
    };
    w.insert(werkzeug.to_string(), neu.clone());
    schreiben(p, &ganz).map_err(|err| ("nicht_gespeichert", err))?;
    Ok(json!({"ok": true, "meldung": meldung, "freigabe": neu}))
}

/// Der Agent schlaegt ein Ziel vor. **Das ist keine Freigabe.** Der Vorschlag
/// landet in `vorschlaege` und wirkt erst, wenn der Nutzer ihn annimmt --
/// deshalb gibt es hier keinen Weg, `positiv` zu schreiben.
///
/// Nur im Modus `offen_nach_vorschlag`: in den anderen Modi kann ein
/// Vorschlag nichts werden, und ein Werkzeug, das ins Leere schlaegt, ist
/// schlimmer als eines, das den Grund nennt.
pub fn vorschlag(p: &Pfade, werkzeug: &str, ziel: &str, notiz: &str, jetzt: u64) -> Result<Value, (&'static str, String)> {
    let z = ziel_pruefen(ziel)?;
    let n = notiz.trim();
    if n.chars().count() > 200 {
        return Err(("wert_ungueltig", "Die Notiz ist laenger als 200 Zeichen.".into()));
    }
    let r = aendern(p, werkzeug, |e| {
        if !e.ist_modus("offen_nach_vorschlag") {
            return Err((
                "modus_keine_vorschlaege",
                format!(
                    "Dieses Werkzeug nimmt keine Vorschlaege an (Modus \"{}\"). Stell es erst auf \"offen_nach_vorschlag\".",
                    e.modus
                ),
            ));
        }
        if e.negativ.iter().any(|x| x.eq_ignore_ascii_case(&z)) {
            return Err(("abgelehnt", format!("\"{z}\" steht auf der Negativliste - ein Vorschlag aendert das nicht.")));
        }
        if e.positiv.iter().any(|x| x.eq_ignore_ascii_case(&z)) {
            return Ok(format!("\"{z}\" steht schon auf der Positivliste"));
        }
        if e.vorschlaege.iter().any(|v| v.ziel.eq_ignore_ascii_case(&z)) {
            return Ok(format!("\"{z}\" steht schon als Vorschlag"));
        }
        if e.vorschlaege.len() >= VORSCHLAEGE_MAX {
            return Err((
                "zu_viele_vorschlaege",
                format!("Es liegen schon {VORSCHLAEGE_MAX} Vorschlaege; erst entscheiden, dann neue."),
            ));
        }
        e.vorschlaege.push(Vorschlag { ziel: z.clone(), herkunft: "agent".into(), seit: jetzt, notiz: n.to_string() });
        Ok(format!("\"{z}\" vorgeschlagen - wirkt erst nach deiner Annahme"))
    })?;
    protokoll(p, jetzt, werkzeug, Some(&z), "vorschlag", "vom Agenten");
    Ok(r)
}

/// Der Nutzer nimmt einen Vorschlag an: das Ziel wandert in `positiv`, der
/// Vorschlag verschwindet. Ab hier gilt es wie ein selbst eingetragenes Ziel.
pub fn annehmen(p: &Pfade, werkzeug: &str, ziel: &str, jetzt: u64) -> Result<Value, (&'static str, String)> {
    let z = ziel_pruefen(ziel)?;
    if !WERKZEUGE.contains(&werkzeug) {
        return Err((
            "werkzeug_unbekannt",
            format!("Werkzeug \"{werkzeug}\" gibt es nicht (bekannt: {}).", WERKZEUGE.join(", ")),
        ));
    }
    // Die Negativliste gewinnt (Zusage seit 12.11.) -- auch gegen eine
    // Annahme. Das Ziel kann **nach** dem Vorschlag dorthin gekommen sein;
    // dann faellt der Vorschlag weg, statt liegen zu bleiben und spaeter zu
    // wirken, wenn die Negativliste gelockert wird. Geschrieben wird hier
    // trotzdem, deshalb steht der Fall vor `aendern` und nicht darin: `aendern`
    // verwirft bei einem Fehler die Aenderung.
    let vor = Eintrag::aus(&laden(p)["werkzeuge"][werkzeug]);
    if vor.negativ.iter().any(|x| x.eq_ignore_ascii_case(&z)) {
        let _ = aendern(p, werkzeug, |e| {
            if let Some(i) = e.vorschlaege.iter().position(|v| v.ziel.eq_ignore_ascii_case(&z)) {
                e.vorschlaege.remove(i);
            }
            Ok(String::new())
        });
        protokoll(p, jetzt, werkzeug, Some(&z), "abgelehnt", "Annahme: steht auf der Negativliste");
        return Err(("abgelehnt", format!("\"{z}\" steht auf der Negativliste.")));
    }
    let r = aendern(p, werkzeug, |e| {
        let Some(i) = e.vorschlaege.iter().position(|v| v.ziel.eq_ignore_ascii_case(&z)) else {
            return Err(("vorschlag_unbekannt", format!("\"{z}\" steht nicht als Vorschlag.")));
        };
        e.vorschlaege.remove(i);
        if !e.positiv.iter().any(|x| x.eq_ignore_ascii_case(&z)) {
            e.positiv.push(z.clone());
        }
        Ok(format!("\"{z}\" angenommen"))
    })?;
    protokoll(p, jetzt, werkzeug, Some(&z), "angenommen", "durch den Nutzer");
    Ok(r)
}

/// Der Nutzer lehnt ab: der Vorschlag faellt weg, sonst aendert sich nichts.
/// Ein abgelehnter Vorschlag kommt **nicht** auf die Negativliste -- das waere
/// eine Entscheidung, die niemand getroffen hat.
pub fn verwerfen(p: &Pfade, werkzeug: &str, ziel: &str, jetzt: u64) -> Result<Value, (&'static str, String)> {
    let z = ziel_pruefen(ziel)?;
    let r = aendern(p, werkzeug, |e| {
        let Some(i) = e.vorschlaege.iter().position(|v| v.ziel.eq_ignore_ascii_case(&z)) else {
            return Err(("vorschlag_unbekannt", format!("\"{z}\" steht nicht als Vorschlag.")));
        };
        e.vorschlaege.remove(i);
        Ok(format!("\"{z}\" verworfen"))
    })?;
    protokoll(p, jetzt, werkzeug, Some(&z), "verworfen", "durch den Nutzer");
    Ok(r)
}

fn beschreibung(e: &Value) -> String {
    let seit = match e["seit"].as_u64() {
        Some(s) => format!("seit {s}"),
        None => "nicht offen".into(),
    };
    let erinnern = match e["erinnern_alle"].as_u64().unwrap_or(ERINNERN_VORGABE) {
        0 => "ohne Ton".to_string(),
        n => format!("erinnern alle {n}s"),
    };
    format!("{} ({}), {}, positiv {}, negativ {}", e["modus"].as_str().unwrap_or("?"), seit, erinnern,
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
/// Fuer Aufrufer, die eine Entscheidung **vor** `pruefen` treffen (harte
/// Grenzen, z.B. eigene Adressen beim Abruf): dieselbe eine Protokollzeile,
/// damit auch diese Ablehnung nachweisbar ist.
pub fn protokolliere(p: &Pfade, zeit: u64, werkzeug: &str, ziel: Option<&str>, was: &str, grund: &str) {
    protokoll(p, zeit, werkzeug, ziel, was, grund)
}

fn protokoll(p: &Pfade, zeit: u64, werkzeug: &str, ziel: Option<&str>, was: &str, grund: &str) {
    let datei = protokoll_datei(p);
    if let Some(dir) = datei.parent() {
        if let Err(e) = std::fs::create_dir_all(dir) {
            eprintln!("freigabe: Protokollordner {} nicht anlegbar: {e}", dir.display());
        }
    }
    if std::fs::metadata(&datei).map(|m| m.len()).unwrap_or(0) > PROTOKOLL_MAX {
        let alt = datei.with_extension("log.1");
        if let Err(e) = std::fs::rename(&datei, alt) {
            eprintln!("freigabe: Rotation misslungen: {e}");
        }
    }
    let mut zeile = format!("{zeit}\t{was}\t{werkzeug}\t{}\t{grund}\n", ziel.unwrap_or("-"));
    match std::fs::OpenOptions::new().create(true).append(true).open(&datei) {
        Ok(mut f) => {
            if let Err(e) = f.write_all(zeile.as_bytes()) {
                eprintln!("freigabe: Protokollzeile nicht geschrieben: {e}");
            }
        }
        // Ein Protokollfehler dreht die Entscheidung nicht um, aber er bleibt
        // nicht still: ohne diese Meldung waere "nichts protokolliert" von
        // "nichts entschieden" nicht zu unterscheiden (Regel 9, stiller Erfolg).
        Err(e) => eprintln!("freigabe: Protokoll {} nicht schreibbar: {e}", datei.display()),
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

    /// Entscheidung smilez (13.11.2026): **kein Ablauf mehr**. Eine offene
    /// Freigabe bleibt offen, auch wenn sehr viel Zeit vergeht.
    #[test]
    fn offene_freigabe_laeuft_nicht_ab() {
        let p = p("kein_ablauf");
        setzen(&p, "web_abruf", &json!({"modus": "offen"}), 1000).expect("setzen");
        assert_eq!(pruefen(&p, "web_abruf", Some("example.com"), 1500)["erlaubt"], true);
        let spaeter = pruefen(&p, "web_abruf", Some("example.com"), 90_000_000);
        assert_eq!(spaeter["erlaubt"], true, "{spaeter}");
        assert!(spaeter["grund"].as_str().unwrap().contains("offen"), "{spaeter}");
    }

    /// Ein `bis` von gestern ist **Altbestand**: es gilt weiterhin, solange
    /// die Frist laeuft -- aber eine alte Frist darf nicht rueckwirkend
    /// aufgehen. Geprueft wird die Datei, wie sie wirklich dastand.
    #[test]
    fn altbestand_mit_alter_frist_bleibt_zu() {
        let p = p("altbestand");
        schreiben(&p, &json!({"werkzeuge": {"web_abruf": {"modus": "offen", "bis": 2000}}})).expect("datei");
        let spaeter = pruefen(&p, "web_abruf", Some("example.com"), 2500);
        assert_eq!(spaeter["erlaubt"], false, "{spaeter}");
        assert!(spaeter["grund"].as_str().unwrap().contains("Altbestand"), "{spaeter}");
        // Und davor: noch nicht vorbei, also offen.
        assert_eq!(pruefen(&p, "web_abruf", Some("example.com"), 1500)["erlaubt"], true);
    }

    /// Was ein alter Aufrufer dennoch mitschickt, wird nicht gespeichert:
    /// sonst stuende in der Datei eine Frist, die niemand beachtet.
    #[test]
    fn eine_mitgeschickte_frist_wird_nicht_gespeichert() {
        let p = p("frist_ignoriert");
        let neu = setzen(&p, "ssh", &json!({"modus": "offen", "bis": 2000}), 1000).expect("setzen");
        assert!(neu["bis"].is_null(), "{neu}");
        assert_eq!(Eintrag::aus(&roh(&p)["werkzeuge"]["ssh"]).bis, None);
        assert_eq!(pruefen(&p, "ssh", Some("host.example"), 90_000_000)["erlaubt"], true);
    }

    /// `seit` gehoert dem Oeffnen: es steht, solange die Freigabe offen ist,
    /// und wird neu gesetzt, wenn sie wieder aufgeht.
    #[test]
    fn seit_wird_beim_oeffnen_gesetzt_und_bleibt_stehen() {
        let p = p("seit");
        let a = setzen(&p, "run_command", &json!({"modus": "offen"}), 1000).expect("oeffnen");
        assert_eq!(a["seit"], 1000, "{a}");
        // Listen nachtragen (Teilauftrag) laesst `seit` stehen.
        let b = setzen(&p, "run_command", &json!({"modus": "offen", "positiv": ["ls"]}), 1200).expect("listen");
        assert_eq!(b["seit"], 1000, "{b}");
        // Schliessen nimmt `seit` weg ...
        let c = setzen(&p, "run_command", &json!({"modus": "positivliste"}), 1300).expect("zu");
        assert!(c["seit"].is_null(), "{c}");
        // ... und ein neues Oeffnen setzt die neue Zeit.
        let d = setzen(&p, "run_command", &json!({"modus": "offen"}), 1400).expect("wieder");
        assert_eq!(d["seit"], 1400, "{d}");
    }

    #[test]
    fn erinnern_alle_wird_gesetzt_und_zu_klein_abgelehnt() {
        let p = p("erinnern");
        let a = setzen(&p, "ssh", &json!({"modus": "offen", "erinnern_alle": 120}), 1000).expect("setzen");
        assert_eq!(a["erinnern_alle"], 120, "{a}");
        assert_eq!(Eintrag::aus(&roh(&p)["werkzeuge"]["ssh"]).erinnern_alle, 120);
        // Fehlt der Wert, bleibt der gesetzte stehen (Teilauftrag).
        let b = setzen(&p, "ssh", &json!({"modus": "offen"}), 1100).expect("setzen");
        assert_eq!(b["erinnern_alle"], 120, "{b}");
        // Unter der Grenze ist es kein Erinnern, sondern Dauerpiepen.
        let e = setzen(&p, "ssh", &json!({"modus": "offen", "erinnern_alle": 10}), 1000).unwrap_err();
        assert_eq!(e.0, "wert_ungueltig");
        assert!(e.1.contains("mindestens"), "{}", e.1);
        assert_eq!(setzen(&p, "ssh", &json!({"modus": "offen", "erinnern_alle": null}), 1000).unwrap()["erinnern_alle"], 120);
        // **0 heisst aus** und ist ausdruecklich erlaubt (opt-in).
        assert_eq!(setzen(&p, "ssh", &json!({"modus": "offen", "erinnern_alle": 0}), 1000).unwrap()["erinnern_alle"], 0);
        // In der Anzeige steht die Vorgabe -- und die ist **aus**.
        let leer = laden(&p);
        assert_eq!(ERINNERN_VORGABE, 0, "der Ton ist opt-in (Entscheidung smilez, 13.11.)");
        assert_eq!(leer["werkzeuge"]["web_suche"]["erinnern_alle"], 0, "{leer}");
    }

    #[test]
    fn negativliste_gilt_auch_im_offenen_modus() {
        let p = p("negativ");
        setzen(&p, "web_abruf", &json!({"modus": "offen", "negativ": ["bose.example"]}), 1000).expect("setzen");
        assert_eq!(pruefen(&p, "web_abruf", Some("gut.example"), 1001)["erlaubt"], true);
        let b = pruefen(&p, "web_abruf", Some("bose.example"), 1001);
        assert_eq!(b["erlaubt"], false);
        assert!(b["grund"].as_str().unwrap().contains("Negativliste"), "{b}");
    }

    #[test]
    fn positivliste_gilt_auch_wenn_die_freigabe_zu_ist() {
        let p = p("positiv");
        setzen(&p, "web_abruf", &json!({"modus": "positivliste", "positiv": ["dauerhaft.example"]}), 1000)
            .expect("setzen");
        let a = pruefen(&p, "web_abruf", Some("dauerhaft.example"), 5000);
        assert_eq!(a["erlaubt"], true, "{a}");
        assert!(a["grund"].as_str().unwrap().contains("Positivliste"), "{a}");
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

    /// Ein Teil-Auftrag (nur `modus`/`erinnern_alle`) darf die gepflegten
    /// Listen nicht wegwerfen -- so schaltet Telegram die Freigabe, ohne
    /// Ziele zu kennen.
    #[test]
    fn teilauftrag_behaelt_die_listen() {
        let p = p("teil");
        setzen(&p, "ssh", &json!({"modus": "positivliste", "positiv": ["host.example"], "negativ": ["bose.example"]}), 1000)
            .expect("listen");
        setzen(&p, "ssh", &json!({"modus": "offen", "erinnern_alle": 90}), 1000).expect("oeffnen");
        let e = Eintrag::aus(&roh(&p)["werkzeuge"]["ssh"]);
        assert_eq!(e.positiv, vec!["host.example"]);
        assert_eq!(e.negativ, vec!["bose.example"]);
        assert!(e.ist_offen(1500));
        // Und ein ausdrueckliches Leeren geht weiter.
        setzen(&p, "ssh", &json!({"modus": "offen", "negativ": []}), 1000).expect("leeren");
        assert!(Eintrag::aus(&roh(&p)["werkzeuge"]["ssh"]).negativ.is_empty());
    }

    // --- Dritter Modus und Vorschlaege (14.11.2026) ---------------------

    #[test]
    fn drei_modi_werden_angenommen_und_gelesen() {
        let p = p("drei_modi");
        for m in MODI {
            let neu = setzen(&p, "run_command", &json!({"modus": m}), 1000).expect("setzen");
            assert_eq!(neu["modus"], *m, "{neu}");
            let gelesen = laden(&p);
            assert_eq!(gelesen["werkzeuge"]["run_command"]["modus"], *m, "{gelesen}");
        }
        // Ein vierter Modus ist ein Tippfehler und wird abgelehnt, nicht
        // stillschweigend zur vorsichtigen Seite gebogen.
        let e = setzen(&p, "run_command", &json!({"modus": "halb_offen"}), 1000).unwrap_err();
        assert_eq!(e.0, "wert_ungueltig");
        assert!(e.1.contains("offen_nach_vorschlag"), "{}", e.1);
    }

    /// Der dritte Modus ist **nicht** offen: er oeffnet nur, was angenommen
    /// wurde. Das ist die Zusage, die den Modus von `offen` unterscheidet.
    #[test]
    fn offen_nach_vorschlag_oeffnet_nicht_alles() {
        let p = p("dritter_modus");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag"}), 1000).expect("setzen");
        let a = pruefen(&p, "run_command", Some("curl"), 1500);
        assert_eq!(a["erlaubt"], false, "{a}");
        assert!(a["grund"].as_str().unwrap().contains("nicht angenommen"), "{a}");
    }

    /// Die Kernzusage: ein Vorschlag ist **keine** Freigabe.
    #[test]
    fn ein_vorschlag_wirkt_nicht_von_selbst() {
        let p = p("vorschlag_wirkt_nicht");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag"}), 1000).expect("setzen");
        let r = vorschlag(&p, "run_command", "ls", "Verzeichnis lesen", 1100).expect("vorschlagen");
        assert!(r["meldung"].as_str().unwrap().contains("ls"), "{r}");
        let e = Eintrag::aus(&roh(&p)["werkzeuge"]["run_command"]);
        assert!(e.positiv.is_empty(), "positiv bleibt leer: {:?}", e.positiv);
        assert_eq!(e.vorschlaege.len(), 1);
        assert_eq!(e.vorschlaege[0].ziel, "ls");
        assert_eq!(e.vorschlaege[0].herkunft, "agent");
        assert_eq!(pruefen(&p, "run_command", Some("ls"), 1200)["erlaubt"], false);
        // Und das Protokoll nennt den Vorschlag als Vorschlag.
        let text = std::fs::read_to_string(protokoll_datei(&p)).expect("protokoll");
        assert!(text.contains("vorschlag"), "{text}");
    }

    #[test]
    fn annahme_traegt_das_ziel_in_die_positivliste_und_raeumt_den_vorschlag() {
        let p = p("annahme");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag"}), 1000).expect("setzen");
        vorschlag(&p, "run_command", "ls", "", 1100).expect("vorschlagen");
        annehmen(&p, "run_command", "ls", 1200).expect("annehmen");
        let e = Eintrag::aus(&roh(&p)["werkzeuge"]["run_command"]);
        assert_eq!(e.positiv, vec!["ls"]);
        assert!(e.vorschlaege.is_empty(), "{:?}", e.vorschlaege);
        let a = pruefen(&p, "run_command", Some("ls"), 1300);
        assert_eq!(a["erlaubt"], true, "{a}");
        assert!(a["grund"].as_str().unwrap().contains("Positivliste"), "{a}");
        // Zweimal annehmen ist kein Fehler, aber auch kein zweiter Eintrag.
        assert_eq!(annehmen(&p, "run_command", "ls", 1400).unwrap_err().0, "vorschlag_unbekannt");
    }

    #[test]
    fn verwerfen_laesst_alles_wie_es_war() {
        let p = p("verwerfen");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag"}), 1000).expect("setzen");
        vorschlag(&p, "run_command", "df", "", 1100).expect("vorschlagen");
        verwerfen(&p, "run_command", "df", 1200).expect("verwerfen");
        let e = Eintrag::aus(&roh(&p)["werkzeuge"]["run_command"]);
        assert!(e.vorschlaege.is_empty());
        assert!(e.positiv.is_empty());
        // Ein verworfener Vorschlag kommt **nicht** auf die Negativliste --
        // das waere eine Entscheidung, die niemand getroffen hat.
        assert!(e.negativ.is_empty());
        assert_eq!(pruefen(&p, "run_command", Some("df"), 1300)["erlaubt"], false);
    }

    /// Kommt ein Ziel **nach** dem Vorschlag auf die Negativliste, gewinnt die
    /// Negativliste -- das war ihre Zusage seit dem 12.11. Der Vorschlag
    /// faellt dabei weg, statt liegen zu bleiben und spaeter zu wirken.
    #[test]
    fn eine_annahme_gegen_die_negativliste_wird_abgelehnt() {
        let p = p("annahme_negativ");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag"}), 1000).expect("setzen");
        vorschlag(&p, "run_command", "nc", "", 1100).expect("vorschlagen");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag", "negativ": ["nc"]}), 1150)
            .expect("negativ");
        let e = annehmen(&p, "run_command", "nc", 1200).unwrap_err();
        assert_eq!(e.0, "abgelehnt");
        let nach = Eintrag::aus(&roh(&p)["werkzeuge"]["run_command"]);
        assert!(nach.positiv.is_empty(), "{:?}", nach.positiv);
        assert!(nach.vorschlaege.is_empty(), "{:?}", nach.vorschlaege);
        assert_eq!(pruefen(&p, "run_command", Some("nc"), 1300)["erlaubt"], false);
    }

    #[test]
    fn vorschlaege_gibt_es_nur_im_dritten_modus() {
        let p = p("vorschlag_modus");
        setzen(&p, "run_command", &json!({"modus": "positivliste"}), 1000).expect("setzen");
        let e = vorschlag(&p, "run_command", "ls", "", 1100).unwrap_err();
        assert_eq!(e.0, "modus_keine_vorschlaege");
        assert!(e.1.contains("positivliste"), "{}", e.1);
    }

    #[test]
    fn ein_vorschlag_gegen_die_negativliste_wird_abgelehnt() {
        let p = p("vorschlag_negativ");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag", "negativ": ["nc"]}), 1000).expect("setzen");
        let e = vorschlag(&p, "run_command", "nc", "", 1100).unwrap_err();
        assert_eq!(e.0, "abgelehnt");
        assert!(Eintrag::aus(&roh(&p)["werkzeuge"]["run_command"]).vorschlaege.is_empty());
    }

    #[test]
    fn derselbe_vorschlag_kommt_nur_einmal() {
        let p = p("vorschlag_doppelt");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag"}), 1000).expect("setzen");
        vorschlag(&p, "run_command", "ls", "", 1100).expect("erster");
        let zweiter = vorschlag(&p, "run_command", "LS", "", 1200).expect("zweiter");
        assert!(zweiter["meldung"].as_str().unwrap().contains("schon"), "{zweiter}");
        assert_eq!(Eintrag::aus(&roh(&p)["werkzeuge"]["run_command"]).vorschlaege.len(), 1);
    }

    /// Ohne Grenze koennte eine Schleife im Agenten die Datei vollschreiben.
    #[test]
    fn zu_viele_vorschlaege_werden_abgelehnt() {
        let p = p("vorschlag_grenze");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag"}), 1000).expect("setzen");
        for i in 0..VORSCHLAEGE_MAX {
            vorschlag(&p, "run_command", &format!("prog{i}"), "", 1100).expect("vorschlagen");
        }
        let e = vorschlag(&p, "run_command", "einer_zuviel", "", 1200).unwrap_err();
        assert_eq!(e.0, "zu_viele_vorschlaege");
    }

    /// Ein Zeitknopf (nur `modus`) darf die offenen Vorschlaege nicht mit
    /// wegwerfen -- dieselbe Ueberlegung wie bei den Listen.
    #[test]
    fn ein_teilauftrag_behaelt_die_vorschlaege() {
        let p = p("vorschlag_teil");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag"}), 1000).expect("setzen");
        vorschlag(&p, "run_command", "ls", "notiz", 1100).expect("vorschlagen");
        setzen(&p, "run_command", &json!({"modus": "offen", "erinnern_alle": 120}), 1200).expect("oeffnen");
        let e = Eintrag::aus(&roh(&p)["werkzeuge"]["run_command"]);
        assert_eq!(e.vorschlaege.len(), 1);
        assert_eq!(e.vorschlaege[0].ziel, "ls");
        assert_eq!(e.vorschlaege[0].notiz, "notiz");
    }

    /// Ein Vorschlag ist ein Ziel wie jedes andere: Leerraum und Leeres
    /// werden abgelehnt, bevor etwas in der Datei landet.
    #[test]
    fn kaputte_vorschlagsziele_werden_abgelehnt() {
        let p = p("vorschlag_ziel");
        setzen(&p, "run_command", &json!({"modus": "offen_nach_vorschlag"}), 1000).expect("setzen");
        assert_eq!(vorschlag(&p, "run_command", "", "", 1100).unwrap_err().0, "wert_ungueltig");
        assert_eq!(vorschlag(&p, "run_command", "mit leer", "", 1100).unwrap_err().0, "wert_ungueltig");
        assert_eq!(vorschlag(&p, "run_command", &"x".repeat(81), "", 1100).unwrap_err().0, "wert_ungueltig");
        assert_eq!(vorschlag(&p, "gibtesnicht", "ls", "", 1100).unwrap_err().0, "werkzeug_unbekannt");
        assert!(Eintrag::aus(&roh(&p)["werkzeuge"]["run_command"]).vorschlaege.is_empty());
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
