//! Die Einstellungen der Telegram-Tuer: **Token und erlaubte Kennungen**,
//! abgelegt in `config/geheim/telegram/einstellung.json` (0600).
//!
//! **Warum eine eigene Ablage und nicht die `.env`** (14.11.2026, Auftrag
//! smilez): Ein Token, den der Nutzer in eine Datei auf dem Gerät tippt,
//! muss er von Hand dorthin bringen — per `ssh`, `sed` oder Editor. Das ist
//! genau die Hürde, an der eine Einrichtung scheitert oder der Token in
//! einer Klartextdatei liegen bleibt, die jeder Dienst liest. Die Ablage
//! gehört `chimera-tor` mit 0600, ist für den Agenten unlesbar (`config/`
//! steht in `InaccessiblePaths`), und der **Wert geht nie zurück** an eine
//! Oberfläche — nur „gesetzt: ja/nein" und der Bot-Name.
//!
//! **Möglichst wenig tippen** (Auftrag): Der Nutzer gibt *nur* den Token von
//! @BotFather ein. Alles andere holt das Gateway selbst: die Bot-Kennung und
//! den Namen über `getMe`, die Chat-Kennungen zum Auswählen über
//! `getUpdates`. Die Server-Adresse ist fest (`api.telegram.org`) und in den
//! Tests über `CHIMERA_TELEGRAM_API` ersetzbar.
//!
//! Wird der Token gespeichert, obwohl Telegram ihn nicht annimmt, steht eine
//! tote Tür in der Ablage und niemand merkt es — deshalb wird **vor** dem
//! Schreiben `getMe` gefragt. Schlägt es fehl, bleibt der alte Stand stehen.

use crate::daten::{atomar_schreiben, Pfade};
use crate::geheim::eigentuemer_des_ordners_uebernehmen;
use crate::telegram::Api;
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::path::PathBuf;
use std::time::Duration;

/// So lang darf ein Token sein (Telegram: `<zahl>:<35 Zeichen>`).
pub const TOKEN_MAX: usize = 200;

pub fn ordner(p: &Pfade) -> PathBuf {
    p.config.join("geheim").join("telegram")
}

pub fn datei(p: &Pfade) -> PathBuf {
    ordner(p).join("einstellung.json")
}

/// Was in der Ablage steht.
#[derive(Debug, Default, Clone, PartialEq)]
pub struct Einstellung {
    pub token: String,
    pub erlaubt: BTreeSet<i64>,
}

impl Einstellung {
    pub fn leer(&self) -> bool {
        self.token.is_empty()
    }
}

/// Die Ablage lesen. Eine kaputte Datei ist ein **Fehler**, kein stiller
/// Rückfall auf „leer" — sonst überschriebe das nächste Speichern die
/// Einträge, die noch zu retten wären.
pub fn lesen(p: &Pfade) -> Result<Einstellung, String> {
    let pfad = datei(p);
    let roh = match std::fs::read_to_string(&pfad) {
        Ok(t) => t,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Einstellung::default()),
        Err(e) => return Err(format!("{} nicht lesbar: {e}", pfad.display())),
    };
    let v: Value = serde_json::from_str(&roh)
        .map_err(|e| format!("{} ist kein JSON: {e}", pfad.display()))?;
    let mut e = Einstellung {
        token: v["token"].as_str().unwrap_or("").trim().to_string(),
        erlaubt: BTreeSet::new(),
    };
    for x in v["erlaubt"].as_array().cloned().unwrap_or_default() {
        if let Some(n) = x.as_i64() {
            e.erlaubt.insert(n);
        }
    }
    Ok(e)
}

pub fn schreiben(p: &Pfade, e: &Einstellung) -> Result<(), String> {
    std::fs::create_dir_all(ordner(p)).map_err(|x| format!("Ordner nicht anlegbar: {x}"))?;
    let daten = json!({
        "token": e.token,
        "erlaubt": e.erlaubt.iter().copied().collect::<Vec<i64>>(),
    });
    let text = serde_json::to_string_pretty(&daten).map_err(|x| x.to_string())?;
    let ziel = datei(p);
    atomar_schreiben(&ziel, text.as_bytes(), 0o600)
        .map_err(|x| format!("nicht gespeichert: {x}"))?;
    // Der Ordner gehört `chimera-tor`; als root geschrieben wäre die Datei
    // für den Dienst unlesbar (Lehre vom 13.11., siehe `geheim.rs`).
    eigentuemer_des_ordners_uebernehmen(&ziel);
    Ok(())
}

pub fn loeschen(p: &Pfade) -> Result<bool, String> {
    match std::fs::remove_file(datei(p)) {
        Ok(()) => Ok(true),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(e) => Err(format!("nicht gelöscht: {e}")),
    }
}

/// Die Basis-Adresse: fest, für Tests ersetzbar.
pub fn basis() -> String {
    std::env::var("CHIMERA_TELEGRAM_API").unwrap_or_else(|_| crate::telegram::API.to_string())
}

/// Form prüfen, ohne das Netz zu fragen (Lehre: erst sagen, was falsch ist).
pub fn token_form_pruefen(token: &str) -> Result<(), String> {
    let t = token.trim();
    if t.is_empty() {
        return Err("Der Token ist leer.".into());
    }
    if t.len() > TOKEN_MAX {
        return Err(format!("Der Token ist länger als {TOKEN_MAX} Zeichen — das ist kein Bot-Token."));
    }
    if !t.contains(':') {
        return Err("Der Token hat nicht die Form '123456:ABC…' (von @BotFather).".into());
    }
    if t.chars().any(|c| c.is_whitespace() || c.is_control()) {
        return Err("Der Token enthält Leerzeichen oder Steuerzeichen.".into());
    }
    let (vorne, hinten) = t.split_once(':').unwrap_or(("", ""));
    if vorne.parse::<u64>().is_err() || hinten.len() < 10 {
        return Err("Der Token hat nicht die Form '123456:ABC…' (von @BotFather).".into());
    }
    Ok(())
}

/// Was die Oberfläche zeigen darf: **nie** der Token.
pub fn stand(p: &Pfade) -> Value {
    let ablage = lesen(p);
    let (token, erlaubt, fehler) = match &ablage {
        Ok(e) => (e.token.clone(), e.erlaubt.iter().copied().collect::<Vec<i64>>(), None),
        Err(f) => (String::new(), Vec::new(), Some(f.clone())),
    };
    // Die Umgebung bleibt gültig — Altinstallationen tragen den Token in der
    // `.env`, und ein Update darf sie nicht abschalten (Regel: ein
    // Versionssprung bricht nie eine laufende Installation).
    let aus_umgebung = token.is_empty()
        && std::env::var("CHIMERA_TELEGRAM_TOKEN").map(|t| !t.trim().is_empty()).unwrap_or(false);
    let mut v = json!({
        "token_gesetzt": !token.is_empty() || aus_umgebung,
        "quelle": if !token.is_empty() { "ablage" } else if aus_umgebung { "umgebung" } else { "keine" },
        "erlaubt": erlaubt,
        "server": basis(),
        "beschreibbar": true,
    });
    if let Some(f) = fehler {
        v["fehler"] = json!(f);
        v["beschreibbar"] = json!(false);
    }
    v
}

/// Den Token prüfen und **dann** ablegen. Gibt den Bot zurück (Name/Kennung),
/// damit die Oberfläche zeigen kann, wen sie da eingerichtet hat.
pub fn token_setzen(p: &Pfade, token: &str) -> Result<Value, String> {
    let token = token.trim().to_string();
    token_form_pruefen(&token)?;
    let api = Api::mit_basis(&basis(), &token);
    // **Erst fragen, dann schreiben.** Ein Token, den Telegram nicht kennt,
    // wäre eine tote Tür im Gerät — und niemand merkte es.
    let ich = match api.ich() {
        Ok(i) => i,
        Err(e) => return Err(format!("Telegram nimmt diesen Token nicht an: {e}")),
    };
    let mut e = lesen(p)?;
    e.token = token;
    schreiben(p, &e)?;
    Ok(json!({
        "bot": {
            "id": ich["id"].clone(),
            "name": ich["first_name"].as_str().unwrap_or(""),
            "username": ich["username"].as_str().unwrap_or(""),
        },
        "erlaubt": e.erlaubt.iter().copied().collect::<Vec<i64>>(),
    }))
}

/// Wer dem Bot geschrieben hat — zum **Auswählen** statt Abtippen der Zahl.
///
/// `getUpdates` mit `offset=-1` und kurzer Frist: Es geht um den letzten
/// Stand, nicht um Long-Polling. Je Absender eine Zeile, doppelte fallen
/// zusammen, der jüngste Eintrag gewinnt.
pub fn absender(p: &Pfade) -> Result<Value, String> {
    let e = lesen(p)?;
    if e.token.is_empty() {
        return Err("Ohne Token fragt das Gateway nicht bei Telegram nach.".into());
    }
    let api = Api::mit_basis(&basis(), &e.token);
    let roh = api
        .aufrufen("getUpdates", &json!({"limit": 100, "timeout": 0, "allowed_updates": ["message"]}),
                  Duration::from_secs(20))?;
    let mut gesehen: Vec<(i64, Value)> = Vec::new();
    for u in roh.as_array().cloned().unwrap_or_default() {
        let Some(msg) = u.get("message") else { continue };
        let Some(chat) = msg.get("chat") else { continue };
        let Some(id) = chat["id"].as_i64() else { continue };
        let zeile = json!({
            "id": id,
            "art": chat["type"].as_str().unwrap_or("?"),
            "name": chat["first_name"].as_str().or(chat["title"].as_str()).unwrap_or(""),
            "benutzer": msg["from"]["username"].as_str().unwrap_or(""),
            "text": msg["text"].as_str().unwrap_or("").chars().take(40).collect::<String>(),
        });
        match gesehen.iter_mut().find(|(x, _)| *x == id) {
            Some(slot) => slot.1 = zeile,
            None => gesehen.push((id, zeile)),
        }
    }
    Ok(json!({"absender": gesehen.into_iter().map(|(_, z)| z).collect::<Vec<_>>()}))
}

/// Die Positivliste setzen. Ohne Eintrag startet die Tuer nicht — das ist
/// Absicht (ein Agent mit Werkzeugen hinter einem offenen Chat wäre ein
/// Fernzugang für jeden, der die Bot-Adresse kennt).
pub fn erlaubt_setzen(p: &Pfade, ids: &[i64]) -> Result<Value, String> {
    let mut e = lesen(p)?;
    if e.token.is_empty() {
        return Err("Erst den Token eintragen — ohne ihn gibt es keine Tuer.".into());
    }
    e.erlaubt = ids.iter().copied().collect();
    schreiben(p, &e)?;
    Ok(json!({"erlaubt": e.erlaubt.iter().copied().collect::<Vec<i64>>()}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn p(name: &str) -> Pfade {
        let d = std::env::temp_dir()
            .join(format!("chimera-tg-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        Pfade::neu(d.join("config"), d.join("state"))
    }

    #[test]
    fn form_verlangt_zahl_doppelpunkt_und_geheimnis() {
        assert!(token_form_pruefen("123456:ABCdefghijklmnopqrstuvwxyz0").is_ok());
        assert!(token_form_pruefen("").is_err());
        assert!(token_form_pruefen("ohne-doppelpunkt").is_err());
        assert!(token_form_pruefen("abc:ABCdefghijklmnopqrstuvwxyz").is_err());
        assert!(token_form_pruefen("123456:kurz").is_err());
        assert!(token_form_pruefen("123456:ABCdefghijklmnopqrstuvwxyz 0").is_err());
        assert!(token_form_pruefen(&"1".repeat(TOKEN_MAX + 1)).is_err());
    }

    #[test]
    fn ablage_schreibt_0600_und_liest_zurueck() {
        let p = p("ablage");
        let mut e = Einstellung::default();
        e.token = "123456:ABCdefghijklmnopqrstuvwxyz0".into(); // noqa: Attrappe
        e.erlaubt.insert(42);
        e.erlaubt.insert(7);
        schreiben(&p, &e).unwrap();
        let m = std::fs::metadata(datei(&p)).unwrap();
        assert_eq!(m.permissions().mode() & 0o777, 0o600, "Geheimnis ist nicht 0600");
        let gelesen = lesen(&p).unwrap();
        assert_eq!(gelesen, e);
        // Die Reihenfolge ist die der Menge, nicht der Eingabe — wichtig,
        // damit zwei Läufe dieselbe Datei ergeben.
        assert_eq!(gelesen.erlaubt.iter().copied().collect::<Vec<_>>(), vec![7, 42]);
    }

    #[test]
    fn kaputte_ablage_ist_ein_fehler_kein_leerer_stand() {
        let p = p("kaputt");
        std::fs::create_dir_all(ordner(&p)).unwrap();
        std::fs::write(datei(&p), "{kein json").unwrap();
        assert!(lesen(&p).is_err());
        // Und `stand` sagt es, statt „nicht eingerichtet" zu behaupten.
        let s = stand(&p);
        assert_eq!(s["beschreibbar"], json!(false));
        assert!(s["fehler"].as_str().unwrap_or("").contains("JSON"));
    }

    #[test]
    fn unlesbare_ablage_ist_auch_ein_fehler() {
        // Ein echter Lesefehler (die „Datei" ist ein Verzeichnis) — nicht nur
        // kaputtes JSON. Beides muss als Fehler ankommen, sonst überschreibt
        // das nächste Speichern, was noch zu retten wäre.
        let p = p("unlesbar");
        std::fs::create_dir_all(datei(&p)).unwrap();
        let r = lesen(&p);
        assert!(r.is_err());
        assert!(r.unwrap_err().contains("nicht lesbar"));
        assert_eq!(stand(&p)["beschreibbar"], json!(false));
    }

    #[test]
    fn stand_verraet_den_token_nicht() {
        let p = p("stand");
        let mut e = Einstellung::default();
        e.token = "123456:GEHEIMgeheimGEHEIMgeheim123".into(); // noqa: Attrappe
        e.erlaubt.insert(5);
        schreiben(&p, &e).unwrap();
        let s = stand(&p).to_string();
        assert!(!s.contains("GEHEIM"), "der Token steht in der Auskunft: {s}");
        let v: Value = serde_json::from_str(&s).unwrap();
        assert_eq!(v["token_gesetzt"], json!(true));
        assert_eq!(v["quelle"], json!("ablage"));
        assert_eq!(v["erlaubt"], json!([5]));
    }

    #[test]
    fn falscher_token_wird_nicht_abgelegt() {
        // Kein Netz im Test: Der Aufruf scheitert, und die Ablage bleibt leer.
        // Genau das ist die Zusage — sonst stünde eine tote Tür im Gerät.
        let p = p("falsch");
        std::env::set_var("CHIMERA_TELEGRAM_API", "http://127.0.0.1:9");
        let r = token_setzen(&p, "123456:ABCdefghijklmnopqrstuvwxyz0");
        std::env::remove_var("CHIMERA_TELEGRAM_API");
        assert!(r.is_err());
        assert!(r.unwrap_err().contains("nimmt diesen Token nicht an"));
        assert!(lesen(&p).unwrap().token.is_empty(), "toter Token wurde abgelegt");
    }

    #[test]
    fn erlaubt_ohne_token_wird_abgelehnt() {
        let p = p("ohne-token");
        let r = erlaubt_setzen(&p, &[1, 2]);
        assert!(r.is_err());
        assert!(r.unwrap_err().contains("Erst den Token"));
    }

    #[test]
    fn loeschen_ist_wahr_und_wiederholbar() {
        let p = p("loeschen");
        let mut e = Einstellung::default();
        e.token = "123456:ABCdefghijklmnopqrstuvwxyz0".into(); // noqa: Attrappe
        schreiben(&p, &e).unwrap();
        assert_eq!(loeschen(&p).unwrap(), true);
        assert_eq!(loeschen(&p).unwrap(), false);
    }
}
