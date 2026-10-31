//! Datenschicht des Gateways (DESIGN Regel 5t): vier Ablagen, je ein Schreiber.
//!
//! | Ablage    | Ort                          | Neu aufbaubar |
//! |-----------|------------------------------|---------------|
//! | Anbieter  | `config/anbieter/<id>.json`  | nein          |
//! | Schluessel| `config/geheim/<id>` (0600)  | nein          |
//! | Katalog   | `state/katalog/<id>.json`    | ja            |
//! | Wahl      | `config/wahl/wahl.json`      | nein          |
//!
//! Regeln: atomar schreiben (Sidecar im selben Verzeichnis, dann `mv`);
//! eine kaputte oder unpassende Datei wird gemeldet und uebersprungen, nie
//! geloescht; ein Verweis ins Leere wird gemeldet, nie still entfernt;
//! Geheimnisse tauchen in keiner Rueckgabe auf. Alles hier nimmt Pfade und
//! die Zeit als Parameter, damit Tests ohne Uhr und ohne /opt laufen.

use serde_json::{json, Map, Value};
use std::fs;
use std::io::Write;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

/// Sieben Tage, dann verschwindet ein Katalogeintrag (5t „Frist statt Loeschen“).
pub const KATALOG_FRIST_S: u64 = 7 * 24 * 3600;

/// Wo die vier Ablagen liegen.
#[derive(Clone, Debug)]
pub struct Pfade {
    pub config: PathBuf,
    pub state: PathBuf,
}

impl Pfade {
    pub fn neu(config: impl Into<PathBuf>, state: impl Into<PathBuf>) -> Self {
        Pfade { config: config.into(), state: state.into() }
    }
    /// Aus der Umgebung; Vorgabe sind die Installerpfade.
    pub fn aus_umgebung() -> Self {
        let c = std::env::var("CHIMERA_CONFIG_DIR").unwrap_or_else(|_| "/opt/chimera/config".into());
        let s = std::env::var("CHIMERA_STATE_DIR").unwrap_or_else(|_| "/opt/chimera/state".into());
        Self::neu(c, s)
    }
    pub fn anbieter_dir(&self) -> PathBuf { self.config.join("anbieter") }
    pub fn geheim_dir(&self) -> PathBuf { self.config.join("geheim") }
    pub fn wahl_datei(&self) -> PathBuf { self.config.join("wahl").join("wahl.json") }
    pub fn katalog_dir(&self) -> PathBuf { self.state.join("katalog") }
}

/// Ids werden Dateinamen: nur Kleinbuchstaben, Ziffern, Bindestrich.
/// So kann keine Id aus dem Verzeichnis ausbrechen.
pub fn id_gueltig(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 32
        && !id.starts_with('-')
        && id.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

/// Atomar schreiben: Sidecar neben dem Ziel, fsync, dann umbenennen.
/// Prueft, dass die Datei danach die erwartete Laenge hat (stiller Erfolg
/// ist die gefaehrlichste Fehlerart).
pub fn atomar_schreiben(ziel: &Path, inhalt: &[u8], modus: u32) -> Result<(), String> {
    let dir = ziel.parent().ok_or("Ziel ohne Verzeichnis")?;
    fs::create_dir_all(dir).map_err(|e| format!("{} nicht anlegbar: {e}", dir.display()))?;
    let name = ziel.file_name().and_then(|n| n.to_str()).ok_or("Ziel ohne Namen")?;
    let tmp = dir.join(format!(".{name}.neu"));
    let _ = fs::remove_file(&tmp);
    {
        let mut f = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(modus)
            .open(&tmp)
            .map_err(|e| format!("{} nicht schreibbar: {e}", tmp.display()))?;
        f.write_all(inhalt).map_err(|e| format!("Schreiben misslungen: {e}"))?;
        f.sync_all().map_err(|e| format!("fsync misslungen: {e}"))?;
    }
    // create_new beachtet die umask; Modus ausdruecklich setzen.
    fs::set_permissions(&tmp, fs::Permissions::from_mode(modus))
        .map_err(|e| format!("Modus nicht setzbar: {e}"))?;
    let laenge = fs::metadata(&tmp).map(|m| m.len()).unwrap_or(0);
    if laenge != inhalt.len() as u64 {
        let _ = fs::remove_file(&tmp);
        return Err(format!("Sidecar hat {laenge} statt {} Byte", inhalt.len()));
    }
    fs::rename(&tmp, ziel).map_err(|e| {
        let _ = fs::remove_file(&tmp);
        format!("Umbenennen misslungen: {e}")
    })
}

fn json_schreiben(ziel: &Path, wert: &Value, modus: u32) -> Result<(), String> {
    let mut text = serde_json::to_vec_pretty(wert).map_err(|e| e.to_string())?;
    text.push(b'\n');
    atomar_schreiben(ziel, &text, modus)
}

/// Eine Meldung beim Laden: welche Datei, was ist falsch.
#[derive(Clone, Debug, PartialEq)]
pub struct Meldung {
    pub quelle: String,
    pub text: String,
}

fn meldung(quelle: &str, text: impl Into<String>) -> Meldung {
    Meldung { quelle: quelle.to_string(), text: text.into() }
}

// ---------------------------------------------------------------- Anbieter

/// Pflichtfelder einer Anbieterdatei pruefen. `Ok` heisst: brauchbar.
pub fn anbieter_pruefen(id: &str, a: &Value) -> Result<(), String> {
    if !id_gueltig(id) {
        return Err(format!("Id \"{id}\" ist ungueltig (a-z, 0-9, Bindestrich, hoechstens 32)"));
    }
    let o = a.as_object().ok_or("keine JSON-Struktur")?;
    for feld in ["typ", "bezeichnung"] {
        match o.get(feld).and_then(Value::as_str) {
            Some(s) if !s.trim().is_empty() => {}
            _ => return Err(format!("Feld \"{feld}\" fehlt oder ist leer")),
        }
    }
    if let Some(v) = o.get("an") {
        if !v.is_boolean() {
            return Err("Feld \"an\" muss wahr/falsch sein".into());
        }
    }
    if let Some(m) = o.get("modelle") {
        if !m.is_object() {
            return Err("Feld \"modelle\" muss ein Objekt sein".into());
        }
    }
    Ok(())
}

pub fn anbieter_speichern(p: &Pfade, id: &str, a: &Value) -> Result<(), String> {
    anbieter_pruefen(id, a)?;
    json_schreiben(&p.anbieter_dir().join(format!("{id}.json")), a, 0o640)
}

pub fn anbieter_entfernen(p: &Pfade, id: &str) -> Result<(), String> {
    if !id_gueltig(id) {
        return Err(format!("Id \"{id}\" ist ungueltig"));
    }
    let f = p.anbieter_dir().join(format!("{id}.json"));
    fs::remove_file(&f).map_err(|e| format!("{} nicht entfernbar: {e}", f.display()))
}

/// Alle brauchbaren Anbieter (nach Id sortiert) plus Meldungen zu den
/// uebersprungenen. Eine kaputte Datei bleibt liegen.
pub fn anbieter_laden(p: &Pfade) -> (Vec<(String, Value)>, Vec<Meldung>) {
    let mut gut = Vec::new();
    let mut msg = Vec::new();
    let Ok(rd) = fs::read_dir(p.anbieter_dir()) else { return (gut, msg) };
    let mut namen: Vec<String> = rd
        .filter_map(|e| e.ok())
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|n| !n.starts_with('.'))
        .collect();
    namen.sort();
    for n in namen {
        let Some(id) = n.strip_suffix(".json") else {
            msg.push(meldung(&n, "keine .json-Datei, uebersprungen"));
            continue;
        };
        let pfad = p.anbieter_dir().join(&n);
        let inhalt = match fs::read_to_string(&pfad) {
            Ok(t) => t,
            Err(e) => { msg.push(meldung(&n, format!("nicht lesbar: {e}"))); continue; }
        };
        let wert: Value = match serde_json::from_str(&inhalt) {
            Ok(v) => v,
            Err(e) => { msg.push(meldung(&n, format!("kein gueltiges JSON: {e}"))); continue; }
        };
        match anbieter_pruefen(id, &wert) {
            Ok(()) => gut.push((id.to_string(), wert)),
            Err(e) => msg.push(meldung(&n, e)),
        }
    }
    (gut, msg)
}

// --------------------------------------------------------------- Schluessel

pub fn schluessel_setzen(p: &Pfade, id: &str, wert: &str) -> Result<(), String> {
    if !id_gueltig(id) {
        return Err(format!("Id \"{id}\" ist ungueltig"));
    }
    if wert.trim().is_empty() {
        return Err("leerer Schluessel".into());
    }
    atomar_schreiben(&p.geheim_dir().join(id), wert.trim().as_bytes(), 0o600)
}

/// Nur fuer den Aufruf beim Anbieter; wandert nie in eine Antwort.
pub fn schluessel_lesen(p: &Pfade, id: &str) -> Option<String> {
    if !id_gueltig(id) {
        return None;
    }
    let t = fs::read_to_string(p.geheim_dir().join(id)).ok()?;
    let t = t.trim();
    (!t.is_empty()).then(|| t.to_string())
}

/// Fuer Anzeige und Menue: gibt es einen Schluessel? Nie der Wert.
pub fn schluessel_da(p: &Pfade, id: &str) -> bool {
    schluessel_lesen(p, id).is_some()
}

/// Ein Schluessel ohne Anbieter oder mit zu offenem Modus ist ein Befund.
pub fn schluessel_pruefen(p: &Pfade, anbieter_ids: &[String]) -> Vec<Meldung> {
    let mut msg = Vec::new();
    let Ok(rd) = fs::read_dir(p.geheim_dir()) else { return msg };
    for e in rd.filter_map(|e| e.ok()) {
        let Ok(n) = e.file_name().into_string() else { continue };
        if n.starts_with('.') { continue; }
        if !anbieter_ids.contains(&n) {
            msg.push(meldung(&n, "Schluessel ohne Anbieter (bleibt liegen)"));
        }
        if let Ok(m) = e.metadata() {
            if m.permissions().mode() & 0o077 != 0 {
                msg.push(meldung(&n, format!("Modus {:o} ist offener als 0600", m.permissions().mode() & 0o777)));
            }
        }
    }
    msg
}

// ------------------------------------------------------------------ Katalog

/// Neuen Katalog aus der alten Datei und der Abfrage bilden.
/// `gemeldet`: Modellname -> Eigenschaften (z. B. `{"tools":true}`).
/// Fehlt ein bekanntes Modell, bekommt es `fehlt_seit`; nach der Frist
/// verschwindet es. Ein wieder gemeldetes Modell verliert `fehlt_seit`.
pub fn katalog_abgleichen(alt: &Value, gemeldet: &Map<String, Value>, jetzt: u64) -> Value {
    let mut neu = Map::new();
    for (name, eig) in gemeldet {
        let mut e = eig.as_object().cloned().unwrap_or_default();
        e.remove("fehlt_seit");
        neu.insert(name.clone(), Value::Object(e));
    }
    if let Some(alte) = alt.get("modelle").and_then(Value::as_object) {
        for (name, eig) in alte {
            if neu.contains_key(name) { continue; }
            let mut e = eig.as_object().cloned().unwrap_or_default();
            let seit = e.get("fehlt_seit").and_then(Value::as_u64).unwrap_or(jetzt);
            if jetzt.saturating_sub(seit) >= KATALOG_FRIST_S { continue; }
            e.insert("fehlt_seit".into(), json!(seit));
            neu.insert(name.clone(), Value::Object(e));
        }
    }
    json!({"stand": jetzt, "modelle": Value::Object(neu)})
}

pub fn katalog_lesen(p: &Pfade, id: &str) -> Value {
    if !id_gueltig(id) { return json!({}); }
    fs::read_to_string(p.katalog_dir().join(format!("{id}.json")))
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_else(|| json!({}))
}

pub fn katalog_speichern(p: &Pfade, id: &str, katalog: &Value) -> Result<(), String> {
    if !id_gueltig(id) {
        return Err(format!("Id \"{id}\" ist ungueltig"));
    }
    json_schreiben(&p.katalog_dir().join(format!("{id}.json")), katalog, 0o640)
}

// --------------------------------------------------------------------- Wahl

/// Zerlegt `<anbieter-id>/<modell>`. Das Modell darf selbst `/` enthalten
/// (z. B. `fredrezones55/Gemopus-4-it:latest`); getrennt wird am ersten.
pub fn verweis_teilen(v: &str) -> Option<(&str, &str)> {
    let (a, m) = v.split_once('/')?;
    (id_gueltig(a) && !m.is_empty()).then_some((a, m))
}

pub fn wahl_laden(p: &Pfade) -> Result<Value, Meldung> {
    let f = p.wahl_datei();
    let Ok(t) = fs::read_to_string(&f) else { return Ok(json!({"reihenfolge": []})) };
    serde_json::from_str::<Value>(&t)
        .map_err(|e| meldung("wahl.json", format!("kein gueltiges JSON: {e}")))
}

pub fn wahl_speichern(p: &Pfade, wahl: &Value) -> Result<(), String> {
    if !wahl.is_object() {
        return Err("die Wahl muss ein Objekt sein".into());
    }
    json_schreiben(&p.wahl_datei(), wahl, 0o640)
}

/// Verweise der Reihenfolge gegen Anbieter und Katalog pruefen.
/// Rueckgabe: (brauchbare Verweise in Reihenfolge, Meldungen zu den
/// uebrigen). Nichts wird geloescht. Eine leere Kette ist selbst eine
/// Meldung (5h).
pub fn wahl_aufloesen(
    wahl: &Value,
    anbieter: &[(String, Value)],
    kataloge: &Map<String, Value>,
) -> (Vec<String>, Vec<Meldung>) {
    let mut gut = Vec::new();
    let mut msg = Vec::new();
    let liste = wahl.get("reihenfolge").and_then(Value::as_array).cloned().unwrap_or_default();
    for v in &liste {
        let Some(text) = v.as_str() else {
            msg.push(meldung("wahl.json", "Eintrag ist kein Text"));
            continue;
        };
        let Some((aid, modell)) = verweis_teilen(text) else {
            msg.push(meldung(text, "kein Verweis der Form <anbieter>/<modell>"));
            continue;
        };
        let Some((_, a)) = anbieter.iter().find(|(i, _)| i == aid) else {
            msg.push(meldung(text, format!("Anbieter \"{aid}\" fehlt")));
            continue;
        };
        if a.get("an").and_then(Value::as_bool) == Some(false) {
            msg.push(meldung(text, format!("Anbieter \"{aid}\" ist ausgeschaltet")));
            continue;
        }
        let im_katalog = kataloge
            .get(aid)
            .and_then(|k| k.get("modelle"))
            .and_then(|m| m.get(modell))
            .is_some();
        if !im_katalog {
            msg.push(meldung(text, format!("Modell \"{modell}\" steht nicht im Katalog von \"{aid}\"")));
            continue;
        }
        gut.push(text.to_string());
    }
    if gut.is_empty() {
        msg.push(meldung("wahl.json", "keine brauchbare Kette: kein Modell gewaehlt oder erreichbar"));
    }
    (gut, msg)
}

// ---------------------------------------------------------------------- Ops

fn fehler(code: &str, text: &str) -> Value {
    gemein::zeile::fehlerantwort(code, text)
}

fn id_aus(a: &Value) -> Result<&str, Value> {
    match a.get("id").and_then(Value::as_str) {
        Some(i) if id_gueltig(i) => Ok(i),
        Some(i) => Err(fehler("id_ungueltig", &format!("Id \"{i}\" ist ungueltig"))),
        None => Err(fehler("id_fehlt", "Die Anfrage braucht ein Feld \"id\".")),
    }
}

/// Die Operationen der Datenschicht. `None`: gehoert nicht hierher.
/// Antworten enthalten nie einen Schluesselwert, nur `schluessel: true/false`.
pub fn op(name: &str, a: &Value, p: &Pfade) -> Option<Value> {
    Some(match name {
        "anbieter_liste" => {
            let (liste, mut msg) = anbieter_laden(p);
            let ids: Vec<String> = liste.iter().map(|(i, _)| i.clone()).collect();
            msg.extend(schluessel_pruefen(p, &ids));
            let eintraege: Vec<Value> = liste
                .iter()
                .map(|(i, v)| {
                    let mut v = v.clone();
                    v["id"] = json!(i);
                    v["schluessel"] = json!(schluessel_da(p, i));
                    v
                })
                .collect();
            json!({"ok": true, "anbieter": eintraege, "meldungen": meldungen_json(&msg)})
        }
        "anbieter_setzen" => {
            let id = match id_aus(a) { Ok(i) => i, Err(e) => return Some(e) };
            let Some(daten) = a.get("anbieter") else {
                return Some(fehler("anbieter_fehlt", "Die Anfrage braucht ein Feld \"anbieter\"."));
            };
            match anbieter_speichern(p, id, daten) {
                Ok(()) => json!({"ok": true, "id": id}),
                Err(e) => fehler("anbieter_ungueltig", &e),
            }
        }
        "anbieter_entfernen" => {
            let id = match id_aus(a) { Ok(i) => i, Err(e) => return Some(e) };
            match anbieter_entfernen(p, id) {
                Ok(()) => json!({"ok": true, "id": id}),
                Err(e) => fehler("nicht_entfernt", &e),
            }
        }
        "schluessel_setzen" => {
            let id = match id_aus(a) { Ok(i) => i, Err(e) => return Some(e) };
            let wert = a.get("wert").and_then(Value::as_str).unwrap_or("");
            match schluessel_setzen(p, id, wert) {
                Ok(()) => json!({"ok": true, "id": id, "neustart": true}),
                Err(e) => fehler("schluessel_ungueltig", &e),
            }
        }
        "wahl_lesen" => {
            let (liste, _) = anbieter_laden(p);
            let mut kat = Map::new();
            for (i, _) in &liste {
                kat.insert(i.clone(), katalog_lesen(p, i));
            }
            match wahl_laden(p) {
                Ok(w) => {
                    let (gut, msg) = wahl_aufloesen(&w, &liste, &kat);
                    json!({"ok": true, "wahl": w, "brauchbar": gut, "meldungen": meldungen_json(&msg)})
                }
                Err(m) => fehler("wahl_kaputt", &format!("{}: {}", m.quelle, m.text)),
            }
        }
        "wahl_setzen" => match a.get("wahl") {
            Some(w) => match wahl_speichern(p, w) {
                Ok(()) => json!({"ok": true}),
                Err(e) => fehler("wahl_ungueltig", &e),
            },
            None => fehler("wahl_fehlt", "Die Anfrage braucht ein Feld \"wahl\"."),
        },
        _ => return None,
    })
}

fn meldungen_json(m: &[Meldung]) -> Vec<Value> {
    m.iter().map(|x| json!({"quelle": x.quelle, "text": x.text})).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> Pfade {
        let d = std::env::temp_dir().join(format!("chimera-daten-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&d);
        Pfade::neu(d.join("config"), d.join("state"))
    }

    fn ollama() -> Value {
        json!({"typ": "ollama", "bezeichnung": "Ollama im LAN", "adresse": "http://x:11434", "an": true})
    }

    #[test]
    fn ids_koennen_nicht_ausbrechen() {
        for schlecht in ["", "../x", "a/b", "A", "a b", "-a", "a.json", &"a".repeat(33)] {
            assert!(!id_gueltig(schlecht), "{schlecht:?}");
        }
        for gut in ["ollama", "ollama-2", "a1"] {
            assert!(id_gueltig(gut), "{gut:?}");
        }
    }

    #[test]
    fn atomar_schreibt_ersetzt_und_hinterlaesst_keinen_sidecar() {
        let p = tmp("atomar");
        let z = p.config.join("x").join("datei");
        atomar_schreiben(&z, b"eins", 0o640).unwrap();
        atomar_schreiben(&z, b"zwei", 0o640).unwrap();
        assert_eq!(fs::read(&z).unwrap(), b"zwei");
        let rest: Vec<_> = fs::read_dir(z.parent().unwrap()).unwrap().collect();
        assert_eq!(rest.len(), 1, "Sidecar blieb liegen");
    }

    #[test]
    fn halbes_schreiben_laesst_das_alte_ganz() {
        // Ein Sidecar von einem frueheren Abbruch darf das Ziel nicht
        // beruehren und den naechsten Schreibvorgang nicht blockieren.
        let p = tmp("halb");
        let z = p.config.join("d");
        atomar_schreiben(&z, b"alt", 0o640).unwrap();
        fs::write(p.config.join(".d.neu"), b"hal").unwrap();
        assert_eq!(fs::read(&z).unwrap(), b"alt");
        atomar_schreiben(&z, b"neu", 0o640).unwrap();
        assert_eq!(fs::read(&z).unwrap(), b"neu");
    }

    #[test]
    fn modus_wird_gesetzt_unabhaengig_von_der_umask() {
        let p = tmp("modus");
        let z = p.config.join("geheim");
        atomar_schreiben(&z, b"s", 0o600).unwrap();
        assert_eq!(fs::metadata(&z).unwrap().permissions().mode() & 0o777, 0o600);
    }

    #[test]
    fn anbieter_hin_und_zurueck() {
        let p = tmp("anb");
        anbieter_speichern(&p, "ollama", &ollama()).unwrap();
        let (a, m) = anbieter_laden(&p);
        assert!(m.is_empty(), "{m:?}");
        assert_eq!(a.len(), 1);
        assert_eq!(a[0].0, "ollama");
        assert_eq!(a[0].1["bezeichnung"], "Ollama im LAN");
    }

    #[test]
    fn kaputte_anbieterdatei_wird_gemeldet_und_bleibt_liegen() {
        let p = tmp("kaputt");
        anbieter_speichern(&p, "gut", &ollama()).unwrap();
        fs::write(p.anbieter_dir().join("schlecht.json"), b"{nicht json").unwrap();
        fs::write(p.anbieter_dir().join("leer.json"), b"{}").unwrap();
        fs::write(p.anbieter_dir().join("notiz.txt"), b"x").unwrap();
        let (a, m) = anbieter_laden(&p);
        assert_eq!(a.len(), 1, "nur der gute Anbieter");
        assert_eq!(m.len(), 3, "{m:?}");
        assert!(p.anbieter_dir().join("schlecht.json").exists(), "nichts geloescht");
        assert!(m.iter().any(|x| x.quelle == "schlecht.json" && x.text.contains("JSON")));
    }

    #[test]
    fn anbieter_mit_falschen_feldtypen_wird_abgelehnt() {
        let mut a = ollama();
        a["an"] = json!("ja");
        assert!(anbieter_pruefen("o", &a).is_err());
        let mut b = ollama();
        b["modelle"] = json!([1]);
        assert!(anbieter_pruefen("o", &b).is_err());
        let mut c = ollama();
        c["typ"] = json!("  ");
        assert!(anbieter_pruefen("o", &c).is_err());
        assert!(anbieter_speichern(&tmp("id"), "../x", &ollama()).is_err());
    }

    #[test]
    fn schluessel_0600_und_nie_in_der_pruefung() {
        let p = tmp("key");
        schluessel_setzen(&p, "anthropic", "  sk-geheim \n").unwrap();
        assert_eq!(schluessel_lesen(&p, "anthropic").as_deref(), Some("sk-geheim"));
        assert!(schluessel_da(&p, "anthropic"));
        assert!(!schluessel_da(&p, "fehlt"));
        let m = schluessel_pruefen(&p, &["anthropic".into()]);
        assert!(m.is_empty(), "{m:?}");
        assert!(schluessel_setzen(&p, "x", "   ").is_err());
        assert!(schluessel_lesen(&p, "../anthropic").is_none());
    }

    #[test]
    fn schluessel_ohne_anbieter_und_offener_modus_sind_befunde() {
        let p = tmp("keybefund");
        schluessel_setzen(&p, "waise", "x").unwrap();
        fs::set_permissions(p.geheim_dir().join("waise"), fs::Permissions::from_mode(0o644)).unwrap();
        let m = schluessel_pruefen(&p, &[]);
        assert_eq!(m.len(), 2, "{m:?}");
        assert!(p.geheim_dir().join("waise").exists(), "nichts geloescht");
    }

    fn gemeldet(namen: &[&str]) -> Map<String, Value> {
        namen.iter().map(|n| (n.to_string(), json!({"tools": true}))).collect()
    }

    #[test]
    fn katalog_markiert_fehlende_und_vergisst_sie_nach_der_frist() {
        let t0 = 1_000_000;
        let k1 = katalog_abgleichen(&json!({}), &gemeldet(&["a", "b"]), t0);
        let k2 = katalog_abgleichen(&k1, &gemeldet(&["a"]), t0 + 10);
        assert_eq!(k2["modelle"]["b"]["fehlt_seit"], t0 + 10);
        assert!(k2["modelle"]["a"].get("fehlt_seit").is_none());
        // fehlt_seit bleibt beim naechsten Abgleich, wird nicht erneuert
        let k3 = katalog_abgleichen(&k2, &gemeldet(&["a"]), t0 + 100);
        assert_eq!(k3["modelle"]["b"]["fehlt_seit"], t0 + 10);
        // knapp vor der Frist noch da, danach weg
        assert!(katalog_abgleichen(&k3, &gemeldet(&["a"]), t0 + 10 + KATALOG_FRIST_S - 1)["modelle"].get("b").is_some());
        assert!(katalog_abgleichen(&k3, &gemeldet(&["a"]), t0 + 10 + KATALOG_FRIST_S)["modelle"].get("b").is_none());
        // wieder da: Marke weg
        let k4 = katalog_abgleichen(&k3, &gemeldet(&["a", "b"]), t0 + 200);
        assert!(k4["modelle"]["b"].get("fehlt_seit").is_none());
    }

    #[test]
    fn katalog_hin_und_zurueck_und_kaputt_ist_leer() {
        let p = tmp("kat");
        assert_eq!(katalog_lesen(&p, "ollama"), json!({}));
        let k = katalog_abgleichen(&json!({}), &gemeldet(&["a"]), 5);
        katalog_speichern(&p, "ollama", &k).unwrap();
        assert_eq!(katalog_lesen(&p, "ollama"), k);
        fs::write(p.katalog_dir().join("ollama.json"), b"kaputt").unwrap();
        assert_eq!(katalog_lesen(&p, "ollama"), json!({}), "Katalog ist neu aufbaubar");
    }

    #[test]
    fn verweis_trennt_am_ersten_schraegstrich() {
        assert_eq!(verweis_teilen("ollama/qwen3.5:latest"), Some(("ollama", "qwen3.5:latest")));
        assert_eq!(verweis_teilen("ollama/fred/Gemopus:latest"), Some(("ollama", "fred/Gemopus:latest")));
        assert_eq!(verweis_teilen("ohne"), None);
        assert_eq!(verweis_teilen("ollama/"), None);
        assert_eq!(verweis_teilen("../x/y"), None);
    }

    fn kataloge(id: &str, namen: &[&str]) -> Map<String, Value> {
        let mut m = Map::new();
        m.insert(id.into(), katalog_abgleichen(&json!({}), &gemeldet(namen), 1));
        m
    }

    #[test]
    fn wahl_meldet_verwaiste_verweise_und_loescht_keinen() {
        let anb = vec![("ollama".to_string(), ollama())];
        let w = json!({"reihenfolge": ["ollama/qwen", "weg/qwen", "ollama/fehlt", "murks", 7]});
        let (gut, msg) = wahl_aufloesen(&w, &anb, &kataloge("ollama", &["qwen"]));
        assert_eq!(gut, vec!["ollama/qwen"]);
        assert_eq!(msg.len(), 4, "{msg:?}");
        assert_eq!(w["reihenfolge"].as_array().unwrap().len(), 5, "Wahl unveraendert");
    }

    #[test]
    fn ausgeschalteter_anbieter_wird_uebersprungen_und_gemeldet() {
        let mut o = ollama();
        o["an"] = json!(false);
        let (gut, msg) = wahl_aufloesen(
            &json!({"reihenfolge": ["ollama/qwen"]}),
            &[("ollama".to_string(), o)],
            &kataloge("ollama", &["qwen"]),
        );
        assert!(gut.is_empty());
        assert!(msg.iter().any(|m| m.text.contains("ausgeschaltet")));
    }

    #[test]
    fn leere_kette_ist_eine_meldung() {
        let (gut, msg) = wahl_aufloesen(&json!({"reihenfolge": []}), &[], &Map::new());
        assert!(gut.is_empty());
        assert!(msg.iter().any(|m| m.text.contains("keine brauchbare Kette")));
    }

    #[test]
    fn wahl_hin_und_zurueck_fehlende_datei_ist_leer_kaputte_wird_gemeldet() {
        let p = tmp("wahl");
        assert_eq!(wahl_laden(&p).unwrap(), json!({"reihenfolge": []}));
        wahl_speichern(&p, &json!({"reihenfolge": ["a/b"]})).unwrap();
        assert_eq!(wahl_laden(&p).unwrap()["reihenfolge"][0], "a/b");
        fs::write(p.wahl_datei(), b"{kaputt").unwrap();
        assert!(wahl_laden(&p).is_err());
        assert!(fs::read(p.wahl_datei()).unwrap() == b"{kaputt", "nicht ueberschrieben");
        assert!(wahl_speichern(&p, &json!([1])).is_err());
    }

    #[test]
    fn op_liste_nennt_schluessel_nur_als_ja_nein() {
        let p = tmp("op");
        anbieter_speichern(&p, "ollama", &ollama()).unwrap();
        schluessel_setzen(&p, "ollama", "sk-sehr-geheim").unwrap();
        let r = op("anbieter_liste", &json!({}), &p).unwrap();
        assert_eq!(r["anbieter"][0]["schluessel"], true);
        assert!(!r.to_string().contains("sk-sehr-geheim"));
    }

    #[test]
    fn op_setzen_prueft_id_und_inhalt_und_unbekanntes_ist_none() {
        let p = tmp("op2");
        assert_eq!(op("anbieter_setzen", &json!({"id": "../x", "anbieter": ollama()}), &p).unwrap()["fehler"]["code"], "id_ungueltig");
        assert_eq!(op("anbieter_setzen", &json!({"id": "o", "anbieter": {}}), &p).unwrap()["fehler"]["code"], "anbieter_ungueltig");
        assert_eq!(op("anbieter_setzen", &json!({"id": "o", "anbieter": ollama()}), &p).unwrap()["ok"], true);
        assert_eq!(op("schluessel_setzen", &json!({"id": "o", "wert": "k"}), &p).unwrap()["neustart"], true);
        assert!(op("chat", &json!({}), &p).is_none());
    }

    #[test]
    fn op_wahl_meldet_verwaiste_verweise() {
        let p = tmp("op3");
        anbieter_speichern(&p, "ollama", &ollama()).unwrap();
        wahl_speichern(&p, &json!({"reihenfolge": ["ollama/x"]})).unwrap();
        let r = op("wahl_lesen", &json!({}), &p).unwrap();
        assert_eq!(r["brauchbar"].as_array().unwrap().len(), 0);
        assert!(!r["meldungen"].as_array().unwrap().is_empty());
        assert_eq!(r["wahl"]["reihenfolge"][0], "ollama/x", "nicht still geloescht");
    }
}
