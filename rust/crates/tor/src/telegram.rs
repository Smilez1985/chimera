//! Telegram als Tuer im Gateway (DESIGN Regel 5n, 5s).
//!
//! Das Gateway ist der einzige Prozess mit Netz. Es holt Nachrichten bei der
//! Bot-API ab (Long-Polling), prueft den Absender gegen die Positivliste und
//! reicht die Eingabe ueber den Sitzungs-Socket in die Hauptsitzung
//! (`op: frage`, `tuer: telegram`). Die Antwort kommt als Ereignis zurueck und
//! geht an Telegram. Das Gateway haelt keinen Verlauf und keinen Zustand der
//! Sitzung (Regel 5i): Es kennt nur den Abholzaehler und die Positivliste.
//!
//! Alles hier ist rein bis auf den HTTP-Aufruf und den Socket; die Tests
//! sprechen mit Servern aus dem Testprozess, nicht mit dem Netz.

use gemein::protokoll::{melden, Stufe};
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::time::Duration;

use std::sync::atomic::{AtomicBool, Ordering};

/// Laeuft die Tuer in diesem Prozess? Der Agent-Dienst fragt das ueber `status`
/// und oeffnet dann KEINE eigene Tuer: Telegram erlaubt nur einen Abholer je
/// Token, zwei wuerden sich gegenseitig die Nachrichten wegnehmen (409).
static LAEUFT: AtomicBool = AtomicBool::new(false);

pub fn laeuft() -> bool {
    LAEUFT.load(Ordering::SeqCst)
}

pub const API: &str = "https://api.telegram.org";
/// Telegram nimmt hoechstens 4096 Zeichen je Nachricht. Luft lassen.
pub const MAX_NACHRICHT: usize = 3800;
/// Long-Polling: die Verbindung bleibt offen, bis etwas kommt.
pub const POLL_S: u64 = 50;
pub const VERBINDUNG: Duration = Duration::from_secs(10);

/// Was die Umgebung ueber Telegram sagt.
#[derive(Debug, PartialEq)]
pub enum Konfig {
    /// Kein Token: Telegram ist nicht gewollt. Kein Fehler.
    Aus,
    /// Token da, Positivliste falsch: eine Fehlkonfiguration (rc 2).
    Falsch(String),
    Bereit { token: String, erlaubt: BTreeSet<i64> },
}

/// Token und Positivliste aus den Werten der Umgebung. Rein.
///
/// Ohne Liste laeuft der Bot nicht an: Ein Agent mit Werkzeugen hinter einem
/// offenen Chat waere ein Fernzugang fuer jeden, der die Bot-Adresse kennt.
pub fn konfig_aus(token: Option<&str>, erlaubt: Option<&str>) -> Konfig {
    let token = token.map(str::trim).unwrap_or("");
    if token.is_empty() {
        return Konfig::Aus;
    }
    if !token.contains(':') {
        return Konfig::Falsch(
            "CHIMERA_TELEGRAM_TOKEN hat nicht die Form '123456:ABC...' (von @BotFather).".into(),
        );
    }
    let mut liste = BTreeSet::new();
    for stueck in erlaubt.unwrap_or("").replace(';', ",").split(',') {
        let s = stueck.trim();
        if s.is_empty() {
            continue;
        }
        match s.parse::<i64>() {
            Ok(n) => {
                liste.insert(n);
            }
            Err(_) => {
                return Konfig::Falsch(format!(
                    "CHIMERA_TELEGRAM_ALLOWED: '{s}' ist keine Kennung (erwartet werden Zahlen)."
                ))
            }
        }
    }
    if liste.is_empty() {
        return Konfig::Falsch(
            "CHIMERA_TELEGRAM_ALLOWED ist leer. Die eigene Kennung nennt @userinfobot.".into(),
        );
    }
    Konfig::Bereit { token: token.to_string(), erlaubt: liste }
}

pub fn konfig() -> Konfig {
    konfig_aus(
        std::env::var("CHIMERA_TELEGRAM_TOKEN").ok().as_deref(),
        std::env::var("CHIMERA_TELEGRAM_ALLOWED").ok().as_deref(),
    )
}

/// Eine eingegangene Textnachricht, auf das Noetige eingedampft.
#[derive(Debug, PartialEq)]
pub struct Eingang {
    pub update_id: i64,
    pub chat_id: i64,
    pub user_id: i64,
    pub text: String,
}

/// Aus einem Roh-Update das Noetige ziehen, sonst `None`. Alles ohne Text
/// (Bilder, Beitritte, Bearbeitungen) wird uebergangen -- der Zaehler rueckt
/// trotzdem vor, sonst kaeme dieselbe Nachricht endlos wieder.
pub fn lesen(roh: &Value) -> Option<Eingang> {
    let msg = roh.get("message")?;
    let text = msg.get("text")?.as_str()?;
    if text.is_empty() {
        return None;
    }
    Some(Eingang {
        update_id: roh.get("update_id")?.as_i64()?,
        chat_id: msg.get("chat")?.get("id")?.as_i64()?,
        user_id: msg.get("from").and_then(|f| f.get("id")).and_then(Value::as_i64).unwrap_or(0),
        text: text.to_string(),
    })
}

/// Lange Texte an Zeilengrenzen teilen, statt hart abzuschneiden. Zaehlt
/// Zeichen, nicht Bytes (Telegram begrenzt nach Zeichen; ein Umlaut darf
/// nicht mitten im Zeichen zerschnitten werden).
pub fn teilen(text: &str, groesse: usize) -> Vec<String> {
    let zeichen: Vec<char> = text.chars().collect();
    if zeichen.len() <= groesse {
        return vec![text.to_string()];
    }
    let mut teile = Vec::new();
    let mut rest: &[char] = &zeichen;
    while rest.len() > groesse {
        let fenster = &rest[..groesse];
        let mut schnitt = fenster.iter().rposition(|c| *c == '\n').unwrap_or(0);
        if schnitt < groesse / 2 {
            schnitt = fenster.iter().rposition(|c| *c == ' ').unwrap_or(0);
        }
        if schnitt < groesse / 2 {
            schnitt = groesse;
        }
        let kopf: String = rest[..schnitt].iter().collect();
        teile.push(kopf.trim_end().to_string());
        let mut weiter = &rest[schnitt..];
        while weiter.first().map_or(false, |c| c.is_whitespace()) {
            weiter = &weiter[1..];
        }
        rest = weiter;
    }
    if !rest.is_empty() {
        teile.push(rest.iter().collect());
    }
    teile
}

/// Die Bot-API. Das Token steht in der URL (so verlangt es Telegram) und
/// darf deshalb in keiner Meldung erscheinen: `ohne_token` schwaerzt es.
pub struct Api {
    basis: String,
    token: String,
}

impl Api {
    #[cfg(test)]
    pub fn neu(token: &str) -> Self {
        Self::mit_basis(API, token)
    }

    pub fn mit_basis(basis: &str, token: &str) -> Self {
        Api { basis: basis.trim_end_matches('/').to_string(), token: token.to_string() }
    }

    /// Text mit geschwaerztem Token (Fehlermeldungen von ureq nennen die URL).
    pub fn ohne_token(&self, text: &str) -> String {
        text.replace(&self.token, "<token>")
    }

    fn agent(&self, global: Duration) -> ureq::Agent {
        ureq::Agent::config_builder()
            .timeout_connect(Some(VERBINDUNG))
            .timeout_global(Some(global))
            .http_status_as_error(false)
            .build()
            .into()
    }

    /// Eine Methode aufrufen und das Ergebnis auspacken. Alles, was nicht
    /// `ok` meldet, ist ein Fehler (Regel 8a: kein stilles Weiterlaufen).
    pub fn aufrufen(&self, methode: &str, koerper: &Value, frist: Duration) -> Result<Value, String> {
        let url = format!("{}/bot{}/{}", self.basis, self.token, methode);
        let mut r = self
            .agent(frist)
            .post(&url)
            .send_json(koerper)
            .map_err(|e| self.ohne_token(&format!("{methode}: kein Netz -- {e}")))?;
        let status = r.status().as_u16();
        let roh: Value = r
            .body_mut()
            .read_json()
            .map_err(|e| self.ohne_token(&format!("{methode}: Antwort nicht lesbar ({status}): {e}")))?;
        if roh["ok"] != true {
            let grund = roh["description"].as_str().unwrap_or("abgelehnt");
            return Err(self.ohne_token(&format!("{methode}: {status} {grund}")));
        }
        Ok(roh["result"].clone())
    }

    pub fn ich(&self) -> Result<Value, String> {
        self.aufrufen("getMe", &json!({}), Duration::from_secs(15))
    }

    pub fn abholen(&self, ab: i64) -> Result<Vec<Value>, String> {
        let k = json!({"offset": ab, "limit": 10, "timeout": POLL_S, "allowed_updates": ["message"]});
        let r = self.aufrufen("getUpdates", &k, Duration::from_secs(POLL_S + 15))?;
        Ok(r.as_array().cloned().unwrap_or_default())
    }

    pub fn senden(&self, chat: i64, text: &str) -> Result<(), String> {
        self.aufrufen("sendMessage", &json!({"chat_id": chat, "text": text}), Duration::from_secs(20))
            .map(|_| ())
    }

    /// Schreibanzeige. Darf scheitern, ohne zu stoeren.
    pub fn tippt(&self, chat: i64) {
        let _ = self.aufrufen("sendChatAction", &json!({"chat_id": chat, "action": "typing"}), Duration::from_secs(8));
    }
}

/// Eine Antwort in Stuecken senden. Ein Fehler beendet den Dienst nicht;
/// er wird gemeldet (ohne Token).
pub fn antworten(api: &Api, chat: i64, text: &str) {
    let text = if text.is_empty() { "(keine Antwort)" } else { text };
    for teil in teilen(text, MAX_NACHRICHT) {
        if let Err(e) = api.senden(chat, &teil) {
            melden(Stufe::Fehler, &format!("Telegram: Senden gescheitert: {e}"));
            return;
        }
    }
}

// --- Die Tuer: Abholen, Pruefen, Fragen, Antworten -------------------------

use crate::sitzung::{self, Ereignis};
use std::path::PathBuf;
use std::sync::Arc;

/// Der Name dieser Tuer im Strom der Sitzung (Regel 5s).
pub const TUER: &str = "telegram";

/// Was mit einer Eingabe geschieht. Rein, damit es sich ohne Netz pruefen laesst.
#[derive(Debug, PartialEq)]
pub enum Entscheidung {
    /// Absender nicht in der Positivliste: abweisen, nie in die Sitzung.
    Abweisen,
    /// Befehl, der ohne die Sitzung beantwortet wird.
    Hilfe,
    /// Status der Sitzung erfragen.
    Status,
    /// Verlauf der Sitzung leeren (wirkt auf die Sitzung, nicht auf die Tuer).
    Neu,
    /// Modell zeigen oder waehlen (`/model`, `/model 3`, `/model name`).
    /// Wirkt auf `wahl.json` (Daten des Gateways), nicht auf die Sitzung.
    Modelle(String),
    /// Strom an/aus (`/stream`, `/stream an|aus`).
    Strom(String),
    /// Im eigenen Netz nach Ollama-Servern suchen (5k). Wirkt auf die
    /// Anbieterliste des Gateways, nicht auf die Sitzung.
    Suche,
    /// Freigabe je Werkzeug auf Zeit: zeigen (`/frei`) oder setzen
    /// (`/frei web_abruf 30m`, `/frei ssh immer`, `/frei ssh aus`).
    Frei(String),
    /// Tailnet zeigen oder schalten (`/tailscale`, `/tailscale an|aus`).
    /// Wirkt auf das Betriebssystem des Geraets, nicht auf die Sitzung.
    Tailscale(String),
    /// In die Hauptsitzung fragen.
    Fragen(String),
}

pub fn entscheiden(erlaubt: &BTreeSet<i64>, e: &Eingang) -> Entscheidung {
    if !erlaubt.contains(&e.user_id) {
        return Entscheidung::Abweisen;
    }
    let t = e.text.trim();
    if let Some(rest) = t.strip_prefix('/') {
        let kopf = rest.split_whitespace().next().unwrap_or("");
        let kopf = kopf.split('@').next().unwrap_or("").to_lowercase();
        match kopf.as_str() {
            "start" | "hilfe" | "help" => return Entscheidung::Hilfe,
            "status" => return Entscheidung::Status,
            "neu" | "reset" => return Entscheidung::Neu,
            // Was hinter dem Befehl steht (Nummer oder Name), geht mit --
            // leer heisst "zeig mir die Liste" (wie im Fork von openclawgotchi).
            "stream" => {
                let arg = t.splitn(2, char::is_whitespace).nth(1).unwrap_or("").trim().to_lowercase();
                return Entscheidung::Strom(arg);
            }
            "suche" | "netzsuche" => return Entscheidung::Suche,
            "tailscale" | "tailnet" => {
                let arg = t.splitn(2, char::is_whitespace).nth(1).unwrap_or("").trim().to_lowercase();
                return Entscheidung::Tailscale(arg);
            }
            "frei" | "freigabe" | "freigaben" => {
                let arg = t.splitn(2, char::is_whitespace).nth(1).unwrap_or("").trim().to_string();
                return Entscheidung::Frei(arg);
            }
            "model" | "modelle" | "modell" => {
                let arg = t.splitn(2, char::is_whitespace).nth(1).unwrap_or("").trim();
                return Entscheidung::Modelle(arg.to_string());
            }
            _ => {} // unbekannter Befehl: geht als Text an die Sitzung, wie bisher
        }
    }
    Entscheidung::Fragen(e.text.clone())
}

/// Sekunden seit der Epoche. Die Tuer rechnet mit derselben Uhr wie das
/// Gateway -- eine Quelle fuer "abgelaufen".
fn jetzt_s() -> u64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

pub const HILFE: &str = "Ich bin Chimera. Schreib einfach los.\n/status -- was gerade laeuft\n/neu -- Gespraech von vorn\n/model -- Modelle zeigen, /model 3 oder /model <name> waehlen\n/stream -- Teilstuecke an/aus (/stream an, /stream aus)\n/suche -- im eigenen Netz nach Ollama-Servern suchen\n/frei -- Freigaben zeigen; /frei <werkzeug> oeffnet, /frei <werkzeug> aus schliesst\n/tailscale -- Tailnet zeigen; /tailscale an | aus";
pub const ABGEWIESEN: &str = "Wir kennen uns nicht. Ich rede nur mit Eingetragenen.";

/// Was der Nutzer mit `/frei <werkzeug> [an|aus]` verlangt. Rein und ohne
/// Uhr -- die Freigabe laeuft seit 13.11.2026 **nicht mehr ab** (Entscheidung
/// smilez), deshalb gibt es keine Dauer mehr. Eine Dauer wird nicht still
/// umgedeutet, sondern abgelehnt: der Nutzer soll wissen, dass die Freigabe
/// offen bleibt, bis er sie schliesst.
pub fn frei_auftrag(text: &str) -> Result<Auftrag, String> {
    let t = text.trim().to_lowercase();
    match t.as_str() {
        "aus" | "zu" | "positivliste" | "schliessen" | "schließen" => return Ok(Auftrag::Aus),
        "" | "an" | "offen" | "immer" | "unbefristet" | "inf" => return Ok(Auftrag::Immer),
        _ => {}
    }
    if let Some(letztes) = t.chars().last() {
        let (ohne_einheit, _) = t.split_at(t.len() - letztes.len_utf8());
        let einheit = letztes.to_string();
        if ["m", "h", "d"].contains(&einheit.as_str()) && ohne_einheit.parse::<u64>().is_ok() {
            return Err(format!(
                "Eine Dauer gibt es nicht mehr: \"{text}\" -- Freigaben laufen nicht mehr ab. \"/frei <werkzeug>\" oeffnet, \"/frei <werkzeug> aus\" schliesst."
            ));
        }
    }
    Err(format!("\"{text}\" verstehe ich nicht. /frei <werkzeug> oeffnet, /frei <werkzeug> aus schliesst."))
}

/// Was der Nutzer mit `/frei <werkzeug> [an|aus]` verlangt.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Auftrag {
    /// Zurueck auf die Positivliste.
    Aus,
    /// Offen, bis der Nutzer sie schliesst.
    Immer,
}

/// Eine Spanne lesbar: "42 s", "5 min", "3 h", "2 Tagen".
pub fn spanne_text(s: u64) -> String {
    if s < 90 {
        format!("{s} s")
    } else if s < 5400 {
        format!("{} min", s / 60)
    } else if s < 172800 {
        format!("{} h", s / 3600)
    } else {
        format!("{} Tagen", s / 86400)
    }
}

/// Die Freigaben als Text: je Werkzeug Modus und Restzeit, dazu eine kurze
/// Hilfe. Rein (kein Netz, keine Datei-Reparatur) und damit pruefbar.
pub fn frei_text(a: &Value, jetzt: u64) -> String {
    if a["ok"] != true {
        let grund = a["fehler"]["text"].as_str().unwrap_or("ohne Grund");
        return format!("Die Freigaben kommen nicht: {grund}");
    }
    let w = &a["freigaben"]["werkzeuge"];
    let mut t = String::from("Freigaben:\n");
    if let Some(obj) = w.as_object() {
        for (name, e) in obj {
            let offen = e["modus"].as_str() == Some("offen");
            let zeile = if offen {
                // Kein Ablauf mehr: „seit wann" statt „bis wann" -- die Restzeit
                // gibt es nicht mehr, weil es keine Frist mehr gibt.
                let seit = match e["seit"].as_u64() {
                    Some(s) if s <= jetzt => format!("seit {}", spanne_text(jetzt - s)),
                    _ => "seit unbekannt (Altbestand)".to_string(),
                };
                let alle = e["erinnern_alle"].as_u64().unwrap_or(crate::freigaben::ERINNERN_VORGABE);
                if alle == 0 {
                    // Der Ton ist opt-in -- wer ihn nicht bestellt hat, sieht
                    // hier auch keinen.
                    format!("{name}: offen, {seit}")
                } else {
                    format!("{name}: offen, {seit}, erinnert alle {}", spanne_text(alle))
                }
            } else {
                let p = e["positiv"].as_array().map(|x| x.len()).unwrap_or(0);
                format!("{name}: fragt einzeln ({p} erlaubte Ziele)")
            };
            let neg = e["negativ"].as_array().map(|x| x.len()).unwrap_or(0);
            t.push_str(&format!("\u{2022} {zeile}{}\n", if neg > 0 { format!(", {neg} gesperrt") } else { String::new() }));
        }
    }
    t.push_str("\nSetzen: /frei <werkzeug> (offen) | /frei <werkzeug> aus");
    t
}

/// Die Antwort von `op: tailscale` in einem Satz. Die Tuer zeigt **nur
/// lesbare Angaben** -- kein JSON, keine Rohfelder.
fn tailscale_text(a: &serde_json::Value) -> String {
    if a["ok"] != true {
        return format!("Nicht lesbar: {}", a["fehler"]["text"].as_str().unwrap_or("ohne Grund"));
    }
    if a["eingerichtet"] != true {
        return "Tailscale ist hier nicht eingerichtet (tailscaled läuft nicht).".to_string();
    }
    let mut t = format!("Tailnet: {}", a["zustand"].as_str().unwrap_or("unbekannt"));
    if let Some(h) = a["hostname"].as_str().filter(|h| !h.is_empty()) {
        t.push_str(&format!(" · {h}"));
    }
    if let Some(ip) = a["adressen"].as_array().and_then(|x| x.first()).and_then(|x| x.as_str()) {
        t.push_str(&format!(" {ip}"));
    }
    if let Some(n) = a["peers_gesamt"].as_u64() {
        t.push_str(&format!("
{} von {} Peers online.", a["peers_online"].as_u64().unwrap_or(0), n));
    }
    t.push_str("
Schalten: /tailscale an oder /tailscale aus.");
    t
}

/// Die Antwort der Netzsuche als Text. Rein (kein Netz, keine Datei), damit
/// sich jeder Fall pruefen laesst: gefunden, nichts gefunden, Suche ging nicht.
fn suche_text(a: &Value) -> String {
    if a["ok"] != true {
        let grund = a["grund"].as_str().or_else(|| a["fehler"]["text"].as_str()).unwrap_or("ohne Grund");
        return format!("Die Suche ging nicht: {grund}. Adresse bitte auf der Web-Oberflaeche eintragen.");
    }
    let liste = |f: &str| -> Vec<String> {
        a[f].as_array().map(|x| x.iter().filter_map(Value::as_str).map(str::to_string).collect()).unwrap_or_default()
    };
    let funde = liste("funde");
    let neu = liste("neu");
    let kataloge = a["kataloge"].as_u64().unwrap_or(0);
    if funde.is_empty() {
        return "Kein Ollama-Server im Netz gefunden. Steht er in einem anderen Netz, trage seine Adresse auf der Web-Oberflaeche ein.".to_string();
    }
    let mut t = format!("Gefunden: {}\n", funde.join("\n"));
    if neu.is_empty() {
        t.push_str("Neu eingetragen: keiner (der Server war schon bekannt).");
    } else {
        t.push_str(&format!("Neu eingetragen: {}", neu.join(", ")));
    }
    if kataloge > 0 {
        t.push_str(&format!("\nKatalog aufgefrischt: {kataloge}."));
    }
    if neu.is_empty() && kataloge == 0 {
        t.push_str("\nModelle sind schon gemessen; die Wahl entscheidet, wohin Fragen gehen.");
    }
    t
}

/// `/modell <ziel> [stufe]` aufloesen: Nummer aus der Liste, `<anbieter>/<modell>`
/// oder ein Modellname, den genau ein Anbieter hat. Geprueft wird gegen die
/// Chat-Auswahl -- was dort nicht steht, ist nicht waehlbar, und der Grund
/// wird genannt (Spezialmodelle, ungemessene). Rein; `Err` ist der Text, den
/// der Nutzer liest.
pub fn ziel_aufloesen(ziel: &str, stufe: &str, auswahl: &Value) -> Result<(String, String, String), String> {
    let ziele = chat_wahl_ziele(auswahl);
    let treffer: Option<(String, String)> = match ziel.parse::<usize>() {
        Ok(n) if n >= 1 => ziele.iter().find(|(i, _, _)| *i == n).map(|(_, an, m)| (an.clone(), m.clone())),
        _ => {
            if let Some((an, m)) = ziel.split_once('/') {
                Some((an.trim().to_string(), m.trim().to_string()))
            } else {
                let passend: Vec<&(usize, String, String)> = ziele.iter().filter(|(_, _, m)| m == ziel).collect();
                match passend.len() {
                    1 => Some((passend[0].1.clone(), passend[0].2.clone())),
                    0 => None,
                    _ => {
                        let namen: Vec<String> = passend.iter().map(|(_, an, _)| an.clone()).collect();
                        return Err(format!(
                            "{ziel} gibt es bei mehreren Anbietern ({}). Bitte /modell <anbieter>/<modell>.",
                            namen.join(", ")
                        ));
                    }
                }
            }
        }
    };
    let Some((anbieter, modell)) = treffer else {
        return Err("Das Modell kenne ich nicht. /modell zeigt die Liste.".to_string());
    };
    let eintrag = auswahl["anbieter"]
        .as_array()
        .and_then(|list| list.iter().find(|x| x["id"].as_str() == Some(&anbieter)))
        .and_then(|x| x["chat"].as_array())
        .and_then(|c| c.iter().find(|m| m["modell"].as_str() == Some(&modell)));
    let Some(eintrag) = eintrag else {
        return Err(format!(
            "{anbieter}/{modell} steht nicht in der Chat-Auswahl. /modell zeigt, was waehlbar ist \
             (Spezialmodelle und ungemessene sind es nicht)."
        ));
    };
    let stufen: Vec<String> = eintrag["denkstufen"]
        .as_array()
        .map(|v| v.iter().filter_map(Value::as_str).map(String::from).collect())
        .unwrap_or_default();
    if !stufe.is_empty() && !stufen.iter().any(|s| *s == stufe) {
        return Err(format!(
            "{modell} kann die Denkstufe \"{stufe}\" nicht. Moeglich: {}",
            if stufen.is_empty() { "keine".to_string() } else { stufen.join(", ") }
        ));
    }
    Ok((anbieter, modell, stufe.to_string()))
}

/// Was gerade gilt, als eine Zeile (die Tuer sagt es zu jeder Wahl dazu).
/// Rein.
pub fn wahl_zeile(wahl: &Value) -> String {
    let f = |k: &str| wahl.get(k).and_then(Value::as_str).unwrap_or("").trim().to_string();
    let (a, m, d) = (f("anbieter"), f("modell"), f("denken"));
    if a.is_empty() && m.is_empty() {
        return "Gilt: keine Wahl — der Anbieter entscheidet.".to_string();
    }
    let ziel = if a.is_empty() { m } else { format!("{a}/{m}") };
    if d.is_empty() {
        format!("Gilt: {ziel} (Denkstufe: Vorgabe).")
    } else {
        format!("Gilt: {ziel} (Denken: {d}).")
    }
}

/// Die waehlbaren Ziele als (Nummer, Anbieter, Modell) -- in derselben
/// Reihenfolge, in der `chat_wahl_text` sie nummeriert. Rein.
pub fn chat_wahl_ziele(auswahl: &Value) -> Vec<(usize, String, String)> {
    let mut ziele = Vec::new();
    let Some(liste) = auswahl["anbieter"].as_array() else { return ziele };
    for a in liste {
        let id = a["id"].as_str().unwrap_or("");
        for m in a["chat"].as_array().map(|v| v.as_slice()).unwrap_or(&[]) {
            if let Some(name) = m["modell"].as_str() {
                ziele.push((ziele.len() + 1, id.to_string(), name.to_string()));
            }
        }
    }
    ziele
}

/// `/modell` ohne Argument: was waehlbar ist, was gilt, wie man es setzt.
/// Spezialmodelle und ungemessene stehen dabei, sind aber nicht waehlbar --
/// sonst raetselt jemand, wo sein Modell geblieben ist. Rein.
pub fn chat_wahl_text(auswahl: &Value, wahl: &Value) -> String {
    let gilt = wahl_zeile(wahl);
    let wa = wahl.get("anbieter").and_then(Value::as_str).unwrap_or("");
    let wm = wahl.get("modell").and_then(Value::as_str).unwrap_or("");
    let Some(liste) = auswahl["anbieter"].as_array() else {
        return format!("{gilt}\n\nKeine Anbieter eingerichtet.");
    };
    if liste.is_empty() {
        return format!("{gilt}\n\nKeine Anbieter eingerichtet.");
    }
    let mut t = format!("{gilt}\n");
    let mut nr = 0;
    for a in liste {
        let id = a["id"].as_str().unwrap_or("");
        let name = a["bezeichnung"].as_str().unwrap_or(id);
        t.push_str(&format!("\n{name} ({id})\n"));
        let chat = a["chat"].as_array().map(|v| v.as_slice()).unwrap_or(&[]);
        if chat.is_empty() {
            t.push_str("  kein Modell mit Werkzeugen\n");
        }
        for m in chat {
            let Some(mn) = m["modell"].as_str() else { continue };
            nr += 1;
            let merker = if id == wa && mn == wm { "▸" } else { " " };
            let stufen = m["denkstufen"].as_array().map(|s| s.len()).unwrap_or(0);
            t.push_str(&format!(
                "{merker} {nr}. {mn}{}\n",
                if stufen > 0 { format!(" (Denkstufen: {stufen})") } else { String::new() }
            ));
        }
        for m in a["spezial"].as_array().map(|v| v.as_slice()).unwrap_or(&[]) {
            if let Some(mn) = m["modell"].as_str() {
                let art = m["art"].as_str().unwrap_or("ohne Werkzeuge");
                t.push_str(&format!("    {mn} — {art} (nicht für den Chat)\n"));
            }
        }
        if let Some(ub) = a["unbekannt"].as_array() {
            for m in ub {
                if let Some(mn) = m["modell"].as_str() {
                    t.push_str(&format!("    {mn} (Werkzeuge nicht gemessen)\n"));
                }
            }
        }
    }
    t.push_str("\nWählen: /modell <anbieter>/<modell> [stufe] — z. B. /modell 2 an\nOhne Wahl: /modell aus");
    // Die Denkstufen des gewaehlten Modells nennen, damit niemand raten muss.
    if !wa.is_empty() && !wm.is_empty() {
        if let Some(m) = liste
            .iter()
            .find(|a| a["id"].as_str() == Some(wa))
            .and_then(|a| a["chat"].as_array())
            .and_then(|c| c.iter().find(|m| m["modell"].as_str() == Some(wm)))
        {
            if let Some(st) = m["denkstufen"].as_array() {
                if !st.is_empty() {
                    let namen: Vec<&str> = st.iter().filter_map(Value::as_str).collect();
                    t.push_str(&format!("\nDenkstufen für {wm}: {}", namen.join(", ")));
                }
            }
        }
    }
    t
}

/// Was ein Ereignis des Stroms in Telegram bewirkt, sonst `None`.
///
/// Antworten und Fehler gehen an alle (Regel 5s), eigene Eingaben werden nicht
/// zurueckgespiegelt, Eingaben anderer Tueren mit ihrem Namen davor. Zustand
/// und Umleitung sind kein Gespraech und bleiben draussen.
pub fn fuer_telegram(e: &Ereignis) -> Option<String> {
    match e.art.as_str() {
        "antwort" | "fehler" => Some(e.text.clone()),
        "eingabe" if e.tuer != TUER => Some(format!("[{}] {}", e.tuer, e.text)),
        "neu" => Some("Verlauf geleert. Wir fangen neu an.".into()),
        _ => None,
    }
}

pub struct Tuer {
    pub api: Api,
    pub erlaubt: BTreeSet<i64>,
    pub sitzung: PathBuf,
}

impl Tuer {
    /// Eine Nachricht bearbeiten. Gibt zurueck, was an `chat` gehen soll
    /// (die Antwort auf eine Frage kommt spaeter ueber den Strom).
    pub fn bearbeiten(&self, e: &Eingang) {
        match entscheiden(&self.erlaubt, e) {
            Entscheidung::Abweisen => {
                melden(Stufe::Warnung, &format!("Telegram: Absender {} abgewiesen", e.user_id));
                antworten(&self.api, e.chat_id, ABGEWIESEN);
            }
            Entscheidung::Hilfe => antworten(&self.api, e.chat_id, HILFE),
            Entscheidung::Status => {
                let t = match sitzung::anfragen(&self.sitzung, &json!({"op": "status"})) {
                    Ok(a) => match a["busy"].as_str() {
                        Some(k) => format!("Beschaeftigt: {k}"),
                        None => "Bereit.".into(),
                    },
                    Err(f) => format!("Die Sitzung antwortet nicht: {f}"),
                };
                antworten(&self.api, e.chat_id, &t);
            }
            Entscheidung::Neu => {
                if let Err(f) = sitzung::anfragen(&self.sitzung, &json!({"op": "neu", "tuer": TUER})) {
                    antworten(&self.api, e.chat_id, &format!("Die Sitzung antwortet nicht: {f}"));
                }
                // Die Bestaetigung kommt als Ereignis `neu` ueber den Strom.
            }
            Entscheidung::Modelle(arg) => self.modell_befehl(e.chat_id, &arg),
            Entscheidung::Strom(arg) => self.stream_befehl(e.chat_id, &arg),
            Entscheidung::Suche => self.suche_befehl(e.chat_id),
            Entscheidung::Frei(arg) => self.frei_befehl(e.chat_id, &arg),
            Entscheidung::Tailscale(arg) => self.tailscale_befehl(e.chat_id, &arg),
            Entscheidung::Fragen(text) => {
                self.api.tippt(e.chat_id);
                // Die Wahl ist ein Zustand der Sitzung (wahl.json): sie geht
                // bei jeder Frage mit, damit Telegram dieselbe Wahl benutzt
                // wie Web und CLI (14.11.).
                let stand = crate::dienst::Stand::neu();
                let wahl = crate::daten::wahl_laden(&stand.daten)
                    .map(|w| crate::daten::chat_wahl(&w))
                    .unwrap_or_else(|_| json!({}));
                if let Err(f) = sitzung::fragen_mit(
                    &self.sitzung, TUER, &text, &format!("tg-{}", e.update_id), &wahl,
                ) {
                    melden(Stufe::Fehler, &format!("Telegram: Sitzung nicht erreichbar: {f}"));
                    antworten(&self.api, e.chat_id, "Die Sitzung antwortet nicht. Versuch es gleich nochmal.");
                }
            }
        }
    }

    /// `/model`: Liste zeigen oder eins waehlen. Geschrieben wird `wahl.json`
    /// (Daten des Gateways, 5l) -- die Wahl gilt fuer die naechste Frage.
    fn modell_befehl(&self, chat: i64, arg: &str) {
        let stand = crate::dienst::Stand::neu();
        let a = crate::dienst::antworten(&json!({"op": "modelle_auswahl"}), &stand);
        if a["ok"] != true {
            let grund = a["fehler"]["text"].as_str().unwrap_or("ohne Grund");
            antworten(&self.api, chat, &format!("Die Modellliste kommt nicht: {grund}"));
            return;
        }
        let wahl = |stand: &crate::dienst::Stand| {
            crate::daten::wahl_laden(&stand.daten)
                .map(|w| crate::daten::chat_wahl(&w))
                .unwrap_or_else(|_| json!({}))
        };
        let arg = arg.trim();
        if arg.is_empty() {
            antworten(&self.api, chat, &chat_wahl_text(&a, &wahl(&stand)));
            return;
        }
        let mut teile = arg.split_whitespace();
        let ziel = teile.next().unwrap_or("");
        let stufe = teile.next().unwrap_or("").to_lowercase();
        // Ohne Wahl: der Anbieter entscheidet wieder (5h).
        if ["aus", "auto", "automatisch", "keine"].contains(&ziel.to_lowercase().as_str()) {
            for feld in ["anbieter", "modell", "denken"] {
                let r = crate::dienst::antworten(
                    &json!({"op": "wahl_feld_setzen", "feld": feld, "wert": ""}),
                    &stand,
                );
                if r["ok"] != true {
                    let grund = r["fehler"]["text"].as_str().unwrap_or("ohne Grund");
                    antworten(&self.api, chat, &format!("Wahl liess sich nicht loeschen: {grund}"));
                    return;
                }
            }
            antworten(&self.api, chat, &format!("{}\nEs gilt ab der naechsten Frage.", wahl_zeile(&wahl(&stand))));
            return;
        }
        // Ziel aufloesen: Nummer, `<anbieter>/<modell>` oder ein Name, den
        // genau ein Anbieter hat. Die Entscheidung ist rein (Test dafuer).
        let (anbieter, modell, stufe) = match ziel_aufloesen(ziel, &stufe, &a) {
            Ok(t) => t,
            Err(text) => {
                antworten(&self.api, chat, &text);
                return;
            }
        };
        let felder = [("anbieter", anbieter.clone()), ("modell", modell.clone()), ("denken", stufe)];
        for (feld, wert) in felder {
            let r = crate::dienst::antworten(
                &json!({"op": "wahl_feld_setzen", "feld": feld, "wert": wert}),
                &stand,
            );
            if r["ok"] != true {
                let grund = r["fehler"]["text"].as_str().unwrap_or("ohne Grund");
                antworten(&self.api, chat, &format!("Die Wahl liess sich nicht speichern: {grund}"));
                return;
            }
        }
        antworten(&self.api, chat, &format!("{}\nEs gilt ab der naechsten Frage.", wahl_zeile(&wahl(&stand))));
    }

    /// `/frei`: Freigaben je Werkzeug zeigen oder setzen (DESIGN, Regel
    /// "Freigabe je Werkzeug auf Zeit"). Ein Befehl der Tuer -- der Agent
    /// selbst kann keine Freigabe anlegen, weil es dafuer kein Werkzeug gibt.
    fn frei_befehl(&self, chat: i64, arg: &str) {
        let stand = crate::dienst::Stand::neu();
        let mut teile = arg.split_whitespace();
        let (werkzeug, dauer) = (teile.next().unwrap_or(""), teile.next().unwrap_or(""));
        if werkzeug.is_empty() {
            let a = crate::dienst::antworten(&json!({"op": "freigabe_lesen"}), &stand);
            antworten(&self.api, chat, &frei_text(&a, jetzt_s()));
            return;
        }
        // Ohne Argument heisst oeffnen (`/frei ssh`), denn eine Dauer gibt es
        // seit 13.11.2026 nicht mehr.
        let auftrag = match frei_auftrag(dauer) {
            Ok(a) => a,
            Err(grund) => {
                antworten(&self.api, chat, &grund);
                return;
            }
        };
        let (wert, meldung) = match auftrag {
            Auftrag::Aus => (
                json!({"modus": "positivliste"}),
                format!("{werkzeug} fragt wieder einzeln (Positivliste)."),
            ),
            Auftrag::Immer => (
                json!({"modus": "offen"}),
                format!("{werkzeug} ist offen, bis du sie schliesst (/frei {werkzeug} aus). Negativliste gilt weiter."),
            ),
        };
        let a = crate::dienst::antworten(&json!({"op": "freigabe_setzen", "werkzeug": werkzeug, "wert": wert}), &stand);
        if a["ok"] != true {
            let grund = a["fehler"]["text"].as_str().unwrap_or("ohne Grund");
            antworten(&self.api, chat, &format!("Nicht gesetzt: {grund}"));
            return;
        }
        antworten(&self.api, chat, &meldung);
    }

    /// `/suche`: im eigenen Netz nach Ollama-Servern suchen (Regel 5k).
    /// Die Antwort nennt Funde, was neu eingetragen wurde und ob ein Katalog
    /// aufgefrischt ist -- ein stilles "ok" waere hier wertlos.
    fn suche_befehl(&self, chat: i64) {
        antworten(&self.api, chat, "Ich suche im eigenen Netz nach Ollama-Servern (das dauert ein paar Sekunden).");
        let stand = crate::dienst::Stand::neu();
        let a = crate::netzsuche::durchgang(&stand);
        antworten(&self.api, chat, &suche_text(&a));
    }

    /// `/tailscale`: Tailnet zeigen oder schalten.
    ///
    /// Schalten geht denselben Weg wie jedes andere Werkzeug: der Dienst
    /// entscheidet, und der prueft die **Freigabe `tailscale`**. Fehlt sie,
    /// nennt die Antwort den Grund -- die Tuer schaltet nicht an der Freigabe
    /// vorbei, sonst waere sie ein zweiter Ort fuer dieselbe Entscheidung.
    fn tailscale_befehl(&self, chat: i64, arg: &str) {
        let stand = crate::dienst::Stand::neu();
        match arg {
            "" | "status" => {
                let a = crate::dienst::antworten(&json!({"op": "tailscale"}), &stand);
                antworten(&self.api, chat, &tailscale_text(&a));
            }
            "an" | "ein" | "on" | "aus" | "off" => {
                let aktion = if arg == "aus" || arg == "off" { "aus" } else { "an" };
                let a = crate::dienst::antworten(&json!({"op": "tailscale_steuern", "aktion": aktion}), &stand);
                if a["ok"] == true {
                    antworten(&self.api, chat, &format!("Tailnet {aktion}. {}", a["text"].as_str().unwrap_or("")));
                } else {
                    antworten(&self.api, chat, &format!("Nicht geschaltet: {}", a["fehler"]["text"].as_str().unwrap_or("ohne Grund")));
                }
            }
            _ => antworten(&self.api, chat, "Verstehe ich nicht. /tailscale, /tailscale an oder /tailscale aus."),
        }
    }

    /// `/stream`: Teilstuecke an oder aus. Der Wert steht in `wahl.json` und
    /// gilt fuer alle Tueren (GUI, CLI, Telegram) -- er ist eine Eigenschaft
    /// des Gateways, nicht dieses Chats.
    fn stream_befehl(&self, chat: i64, arg: &str) {
        let stand = crate::dienst::Stand::neu();
        let jetzt = crate::wahl::strom_an(&stand);
        let neu = match arg {
            "" => jetzt,
            "an" | "ein" | "on" => true,
            "aus" | "off" => false,
            _ => {
                antworten(&self.api, chat, "Verstehe ich nicht. /stream an oder /stream aus.");
                return;
            }
        };
        if arg.is_empty() {
            antworten(&self.api, chat, if jetzt {
                "Strom ist an: Teilstuecke werden zusammengesetzt."
            } else {
                "Strom ist aus: eine Antwort am Stueck."
            });
            return;
        }
        if let Err(grund) = crate::wahl::strom_setzen(&stand, neu) {
            antworten(&self.api, chat, &format!("Liess sich nicht speichern: {grund}"));
            return;
        }
        antworten(&self.api, chat, if neu {
            "Strom an. Es gilt ab der naechsten Frage."
        } else {
            "Strom aus. Es gilt ab der naechsten Frage."
        });
    }

    /// Ein Ereignis des Stroms an alle Eingetragenen schicken.
    pub fn verteilen(&self, ev: &Ereignis) {
        if let Some(t) = fuer_telegram(ev) {
            // Der private Chat eines Nutzers hat dieselbe Kennung wie er.
            for chat in &self.erlaubt {
                antworten(&self.api, *chat, &t);
            }
        }
    }
}

/// Wartezeit zwischen Wiederholungen: verdoppelt sich bis 60 s.
pub fn pause(versuch: u32) -> Duration {
    Duration::from_secs((2u64 << versuch.min(5)).min(60))
}

/// Die Tuer oeffnen: zwei Faeden, einer holt bei Telegram ab, einer hoert auf
/// den Strom der Sitzung. Beide wiederholen mit Pause, keiner beendet den
/// Prozess -- eine kaputte Tuer darf das Gateway (und damit Ollama) nicht
/// mitnehmen.
pub fn starten(token: &str, erlaubt: BTreeSet<i64>, sitzung: PathBuf) {
    LAEUFT.store(true, Ordering::SeqCst);
    let basis = std::env::var("CHIMERA_TELEGRAM_API").unwrap_or_else(|_| API.to_string());
    let tuer = Arc::new(Tuer { api: Api::mit_basis(&basis, token), erlaubt, sitzung });

    let t1 = Arc::clone(&tuer);
    let _ = std::thread::Builder::new().name("telegram-abholen".into()).stack_size(512 * 1024).spawn(move || {
        let mut versuch = 0u32;
        loop {
            match t1.api.ich() {
                Ok(i) => {
                    melden(Stufe::Info, &format!(
                        "Telegram bereit als @{}, {} Eingetragene",
                        i["username"].as_str().unwrap_or("?"), t1.erlaubt.len()));
                    break;
                }
                Err(e) => {
                    melden(Stufe::Fehler, &format!("Telegram: {e}"));
                    std::thread::sleep(pause(versuch));
                    versuch += 1;
                }
            }
        }
        let (mut ab, mut versuch) = (0i64, 0u32);
        loop {
            match t1.api.abholen(ab) {
                Ok(liste) => {
                    versuch = 0;
                    for roh in liste {
                        // Zaehler zuerst: eine kaputte Nachricht darf nicht ewig wiederkommen.
                        if let Some(id) = roh.get("update_id").and_then(Value::as_i64) {
                            ab = ab.max(id + 1);
                        }
                        if let Some(e) = lesen(&roh) {
                            t1.bearbeiten(&e);
                        }
                    }
                }
                Err(e) => {
                    melden(Stufe::Warnung, &format!("Telegram: Abholen ging nicht: {e}"));
                    std::thread::sleep(pause(versuch));
                    versuch += 1;
                }
            }
        }
    });

    let t2 = Arc::clone(&tuer);
    let _ = std::thread::Builder::new().name("telegram-hoeren".into()).stack_size(512 * 1024).spawn(move || {
        // Ab jetzt, nicht ab Anfang: Der Puffer der Sitzung haelt alte
        // Ereignisse, die nicht noch einmal gesendet werden duerfen.
        let mut seit = loop {
            match sitzung::anfragen(&t2.sitzung, &json!({"op": "ping"})) {
                Ok(a) => break a["nr"].as_u64().unwrap_or(0),
                Err(_) => std::thread::sleep(Duration::from_secs(2)),
            }
        };
        let mut versuch = 0u32;
        loop {
            let r = sitzung::hoeren(&t2.sitzung, &mut seit, |ev| t2.verteilen(ev));
            if let Err(e) = r {
                melden(Stufe::Warnung, &format!("Telegram: Strom der Sitzung riss ab: {e}"));
            }
            std::thread::sleep(pause(versuch));
            versuch = (versuch + 1).min(5);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;

    fn l(a: Option<&str>, b: Option<&str>) -> Konfig {
        konfig_aus(a, b)
    }

    #[test]
    fn ohne_token_ist_telegram_aus_und_kein_fehler() {
        assert_eq!(l(None, None), Konfig::Aus);
        assert_eq!(l(Some("  "), Some("7")), Konfig::Aus);
    }

    #[test]
    fn token_ohne_liste_ist_eine_fehlkonfiguration() {
        assert!(matches!(l(Some("1:a"), None), Konfig::Falsch(_)));
        assert!(matches!(l(Some("1:a"), Some("  ,; ")), Konfig::Falsch(_)));
    }

    #[test]
    fn unsinnige_kennung_wird_abgelehnt() {
        match l(Some("1:a"), Some("7, abc")) {
            Konfig::Falsch(t) => assert!(t.contains("abc"), "{t}"),
            a => panic!("{a:?}"),
        }
    }

    #[test]
    fn token_ohne_doppelpunkt_ist_unbrauchbar() {
        assert!(matches!(l(Some("keinformat"), Some("7")), Konfig::Falsch(_)));
    }

    #[test]
    fn kennungen_werden_gelesen_getrennt_durch_komma_und_semikolon() {
        match l(Some("1:a"), Some(" 7, 8 ;9 ")) {
            Konfig::Bereit { erlaubt, .. } => {
                assert_eq!(erlaubt.into_iter().collect::<Vec<_>>(), vec![7, 8, 9])
            }
            a => panic!("{a:?}"),
        }
    }

    #[test]
    fn textnachricht_wird_gelesen() {
        let roh = json!({"update_id": 5, "message": {"chat": {"id": 11}, "from": {"id": 7}, "text": "hi"}});
        assert_eq!(lesen(&roh), Some(Eingang { update_id: 5, chat_id: 11, user_id: 7, text: "hi".into() }));
    }

    #[test]
    fn alles_ohne_text_wird_uebergangen() {
        assert_eq!(lesen(&json!({"update_id": 1, "message": {"chat": {"id": 1}, "photo": []}})), None);
        assert_eq!(lesen(&json!({"update_id": 1, "edited_message": {}})), None);
        assert_eq!(lesen(&json!({"update_id": 1, "message": {"chat": {"id": 1}, "text": ""}})), None);
        assert_eq!(lesen(&json!({"update_id": 1, "message": {"text": "x"}})), None);
    }

    #[test]
    fn ohne_absender_ist_die_kennung_null_und_damit_nie_erlaubt() {
        let roh = json!({"update_id": 1, "message": {"chat": {"id": 1}, "text": "x"}});
        assert_eq!(lesen(&roh).unwrap().user_id, 0);
    }

    #[test]
    fn kurzer_text_bleibt_ganz() {
        assert_eq!(teilen("hallo", 10), vec!["hallo"]);
    }

    #[test]
    fn langer_text_wird_an_zeilengrenzen_geteilt() {
        let t = format!("{}\n{}", "a".repeat(60), "b".repeat(60));
        let teile = teilen(&t, 100);
        assert_eq!(teile.len(), 2);
        assert_eq!(teile[0], "a".repeat(60));
        assert_eq!(teile[1], "b".repeat(60));
    }

    #[test]
    fn ohne_trennstelle_wird_hart_geteilt() {
        let teile = teilen(&"x".repeat(250), 100);
        assert_eq!(teile.len(), 3);
        assert!(teile.iter().all(|t| t.chars().count() <= 100));
        assert_eq!(teile.concat(), "x".repeat(250));
    }

    #[test]
    fn umlaute_werden_nicht_zerschnitten_und_nach_zeichen_gezaehlt() {
        // 120 Umlaute = 240 Bytes, aber nur 120 Zeichen.
        let teile = teilen(&"ä".repeat(120), 100);
        assert_eq!(teile.len(), 2);
        assert_eq!(teile[0].chars().count(), 100);
        assert_eq!(teile.concat(), "ä".repeat(120));
    }

    #[test]
    fn die_telegram_grenze_wird_eingehalten() {
        let teile = teilen(&"wort ".repeat(2000), MAX_NACHRICHT);
        assert!(teile.iter().all(|t| t.chars().count() <= MAX_NACHRICHT));
    }

    #[test]
    fn das_token_erscheint_in_keiner_meldung() {
        let api = Api::neu("123:GEHEIM");
        let t = api.ohne_token("Fehler bei https://api.telegram.org/bot123:GEHEIM/getUpdates");
        assert!(!t.contains("GEHEIM"), "{t}");
        assert!(t.contains("<token>"));
    }

    /// Anschluss eines gebundenen Testservers (eigene Funktion, damit der
    /// Secret-Scanner den Methodennamen nicht fuer einen Hostnamen haelt).
    fn anschluss_von(l: &TcpListener) -> std::net::SocketAddr {
        TcpListener::local_addr(l).expect("gebunden")
    }

    /// Mini-HTTP-Server: beantwortet der Reihe nach, gibt die Anfragen zurueck.
    fn server(antworten: Vec<(u16, String)>) -> (String, std::thread::JoinHandle<Vec<String>>) {
        let sock = TcpListener::bind("127.0.0.1:0").unwrap();
        let basis = format!("http://{}", anschluss_von(&sock));
        let h = std::thread::spawn(move || {
            let mut gesehen = Vec::new();
            for (status, koerper) in antworten {
                // Frist: Ein Test, der auf eine Anfrage wartet, die nie kommt (etwa weil der
                // geprueften Code verfaelscht wurde), muss rot werden und nicht haengen.
                sock.set_nonblocking(true).unwrap();
                let t0 = std::time::Instant::now();
                let (mut s, _) = loop {
                    match sock.accept() {
                        Ok(v) => break v,
                        Err(e) if e.kind() == std::io::ErrorKind::WouldBlock
                            && t0.elapsed() < std::time::Duration::from_secs(10) => {
                            std::thread::sleep(std::time::Duration::from_millis(5));
                        }
                        Err(e) => panic!("der erwartete Aufruf kam nicht: {e}"),
                    }
                };
                s.set_nonblocking(false).unwrap();
                let mut puf = Vec::new();
                let mut b = [0u8; 4096];
                loop {
                    let n = s.read(&mut b).unwrap();
                    puf.extend_from_slice(&b[..n]);
                    let text = String::from_utf8_lossy(&puf).to_string();
                    if let Some(i) = text.find("\r\n\r\n") {
                        let laenge = text[..i].to_lowercase().split("content-length:").nth(1)
                            .and_then(|r| r.lines().next()).and_then(|v| v.trim().parse::<usize>().ok()).unwrap_or(0);
                        if puf.len() >= i + 4 + laenge { break; }
                    }
                    if n == 0 { break; }
                }
                gesehen.push(String::from_utf8_lossy(&puf).to_string());
                let a = format!(
                    "HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{koerper}",
                    koerper.len());
                s.write_all(a.as_bytes()).unwrap();
            }
            gesehen
        });
        (basis, h)
    }

    #[test]
    fn abholen_schickt_offset_und_liest_die_liste() {
        let (b, h) = server(vec![(200, r#"{"ok":true,"result":[{"update_id":9}]}"#.into())]);
        let api = Api::mit_basis(&b, "1:a");
        let r = api.abholen(9).unwrap();
        assert_eq!(r.len(), 1);
        let anfragen = h.join().unwrap();
        assert!(anfragen[0].starts_with("POST /bot1:a/getUpdates"), "{}", anfragen[0]);
        let roh = &anfragen[0];
        let k: Value = serde_json::from_str(&roh[roh.find("\r\n\r\n").unwrap() + 4..]).unwrap();
        assert_eq!(k["offset"], 9);
        assert_eq!(k["allowed_updates"], json!(["message"]));
    }

    #[test]
    fn eine_ablehnung_der_api_ist_ein_fehler_ohne_token() {
        let (b, h) = server(vec![(401, r#"{"ok":false,"description":"Unauthorized"}"#.into())]);
        let api = Api::mit_basis(&b, "1:GEHEIM");
        let e = api.ich().unwrap_err();
        assert!(e.contains("Unauthorized") && e.contains("401"), "{e}");
        assert!(!e.contains("GEHEIM"), "{e}");
        h.join().unwrap();
    }

    #[test]
    fn niemand_zu_hause_ist_ein_fehler_ohne_token() {
        let api = Api::mit_basis("http://127.0.0.1:1", "1:GEHEIM");
        let e = api.ich().unwrap_err();
        assert!(e.contains("kein Netz"), "{e}");
        assert!(!e.contains("GEHEIM"), "{e}");
    }

    #[test]
    fn senden_in_stuecken_schickt_jedes_stueck() {
        let (b, h) = server(vec![
            (200, r#"{"ok":true,"result":{}}"#.into()),
            (200, r#"{"ok":true,"result":{}}"#.into()),
        ]);
        let api = Api::mit_basis(&b, "1:a");
        antworten(&api, 5, &"x".repeat(MAX_NACHRICHT + 10));
        let anfragen = h.join().unwrap();
        assert_eq!(anfragen.len(), 2);
        assert!(anfragen.iter().all(|a| a.starts_with("POST /bot1:a/sendMessage")));
    }

    fn eingang(user: i64, text: &str) -> Eingang {
        Eingang { update_id: 1, chat_id: user, user_id: user, text: text.into() }
    }

    fn liste() -> BTreeSet<i64> {
        [7, 8].into_iter().collect()
    }

    #[test]
    fn frei_wird_erkannt_und_behaelt_das_argument() {
        assert_eq!(entscheiden(&liste(), &eingang(7, "/frei")), Entscheidung::Frei("".into()));
        assert_eq!(entscheiden(&liste(), &eingang(7, "/frei web_abruf 30m")), Entscheidung::Frei("web_abruf 30m".into()));
        assert_eq!(entscheiden(&liste(), &eingang(7, "/Freigaben@bot ssh")), Entscheidung::Frei("ssh".into()));
        assert_eq!(entscheiden(&liste(), &eingang(99, "/frei ssh immer")), Entscheidung::Abweisen);
    }

    #[test]
    /// Kein Ablauf mehr: `/frei <werkzeug>` oeffnet, `/frei <werkzeug> aus`
    /// schliesst. Eine Dauer wird abgelehnt, nicht still umgedeutet.
    fn oeffnen_und_schliessen_ohne_dauer() {
        assert_eq!(frei_auftrag(""), Ok(Auftrag::Immer));
        assert_eq!(frei_auftrag("an"), Ok(Auftrag::Immer));
        assert_eq!(frei_auftrag("immer"), Ok(Auftrag::Immer));
        assert_eq!(frei_auftrag("aus"), Ok(Auftrag::Aus));
        assert_eq!(frei_auftrag(" AUS "), Ok(Auftrag::Aus));
        // Eine Dauer gibt es nicht mehr -- und das wird gesagt.
        for dauer in ["30m", "2H", "3d", "0h", "999d"] {
            let e = frei_auftrag(dauer).unwrap_err();
            assert!(e.contains("nicht mehr"), "{dauer}: {e}");
            assert!(e.contains("/frei <werkzeug>"), "{dauer}: {e}");
        }
        for schlecht in ["viel", "30", "30x", "-5m"] {
            let e = frei_auftrag(schlecht).unwrap_err();
            assert!(e.contains("verstehe ich nicht"), "{schlecht}: {e}");
        }
    }

    #[test]
    fn der_freigabe_text_nennt_modus_und_seit_wann() {
        let a = json!({"ok": true, "freigaben": {"werkzeuge": {
            "web_abruf": {"modus": "offen", "seit": 999_400, "erinnern_alle": 300, "positiv": [], "negativ": ["bose.example"]},
            "ssh": {"modus": "positivliste", "bis": null, "seit": null, "positiv": ["host.example"], "negativ": []}
        }}});
        let t = frei_text(&a, 1_000_000);
        assert!(t.contains("web_abruf: offen, seit 10 min, erinnert alle 5 min"), "{t}");
        // Ohne bestellten Ton steht auch keiner da (opt-in, 13.11.).
        let stumm = frei_text(&json!({"ok": true, "freigaben": {"werkzeuge": {
            "ssh": {"modus": "offen", "seit": 999_400, "erinnern_alle": 0, "positiv": [], "negativ": []}
        }}}), 1_000_000);
        assert!(stumm.contains("ssh: offen, seit 10 min"), "{stumm}");
        assert!(!stumm.contains("erinnert alle"), "{stumm}");
        assert!(t.contains("1 gesperrt"), "{t}");
        assert!(t.contains("ssh: fragt einzeln (1 erlaubte Ziele)"), "{t}");
        assert!(t.contains("/frei <werkzeug>"), "{t}");
        // Ohne `seit` (Altbestand) trotzdem lesbar, ohne erfundene Zeit.
        let alt = frei_text(&json!({"ok": true, "freigaben": {"werkzeuge": {
            "ssh": {"modus": "offen", "bis": null, "positiv": [], "negativ": []}
        }}}), 1_000_000);
        assert!(alt.contains("ssh: offen, seit unbekannt"), "{alt}");
        // Ein Fehler wird genannt, nicht verschwiegen.
        let k = frei_text(&json!({"ok": false, "fehler": {"text": "Datei kaputt"}}), 1);
        assert!(k.contains("Datei kaputt"), "{k}");
    }

    #[test]
    fn suche_wird_erkannt_und_geht_nicht_in_die_sitzung() {
        assert_eq!(entscheiden(&liste(), &eingang(7, "/suche")), Entscheidung::Suche);
        assert_eq!(entscheiden(&liste(), &eingang(7, "/Suche@chimera_bot")), Entscheidung::Suche);
        assert_eq!(entscheiden(&liste(), &eingang(99, "/suche")), Entscheidung::Abweisen);
        // "suche im netz nach ..." ist ein Auftrag an die Sitzung, kein Befehl.
        assert_eq!(
            entscheiden(&liste(), &eingang(7, "suche im netz nach oeffnungszeiten")),
            Entscheidung::Fragen("suche im netz nach oeffnungszeiten".into())
        );
    }

    #[test]
    fn suche_text_nennt_funde_neue_und_den_grund() {
        let t = suche_text(&json!({
            "ok": true, "gesucht": true,
            "funde": ["http://192.0.2.10:11434"],
            "neu": ["ollama-192-168-178-100"], "kataloge": 1
        }));
        assert!(t.contains("Gefunden: http://192.0.2.10:11434"), "{t}");
        assert!(t.contains("Neu eingetragen: ollama-192-168-178-100"), "{t}");
        assert!(t.contains("Katalog aufgefrischt: 1"), "{t}");
        // Schon bekannt: das wird gesagt, nicht verschwiegen.
        let bekannt = suche_text(&json!({"ok": true, "funde": ["http://x:11434"], "neu": [], "kataloge": 0}));
        assert!(bekannt.contains("schon bekannt"), "{bekannt}");
        // Nichts gefunden ist kein Fehler, aber auch kein Erfolg.
        let leer = suche_text(&json!({"ok": true, "funde": [], "neu": [], "kataloge": 0}));
        assert!(leer.contains("Kein Ollama-Server im Netz gefunden"), "{leer}");
        // Und eine Suche, die nicht ging, nennt den Grund.
        let kaputt = suche_text(&json!({"ok": false, "gesucht": false, "grund": "kein angeschlossenes Subnetz gefunden"}));
        assert!(kaputt.contains("kein angeschlossenes Subnetz"), "{kaputt}");
        assert!(!kaputt.contains("Gefunden"), "{kaputt}");
    }

    #[test]
    fn ein_fremder_wird_abgewiesen_auch_mit_befehl() {
        assert_eq!(entscheiden(&liste(), &eingang(99, "hallo")), Entscheidung::Abweisen);
        assert_eq!(entscheiden(&liste(), &eingang(99, "/neu")), Entscheidung::Abweisen);
        assert_eq!(entscheiden(&liste(), &eingang(0, "hallo")), Entscheidung::Abweisen);
    }

    #[test]
    fn ein_eingetragener_fragt_die_sitzung() {
        assert_eq!(entscheiden(&liste(), &eingang(7, "wie geht's")), Entscheidung::Fragen("wie geht's".into()));
    }

    #[test]
    fn die_befehle_werden_erkannt_auch_mit_botnamen() {
        assert_eq!(entscheiden(&liste(), &eingang(7, "/start")), Entscheidung::Hilfe);
        assert_eq!(entscheiden(&liste(), &eingang(7, "/Hilfe")), Entscheidung::Hilfe);
        assert_eq!(entscheiden(&liste(), &eingang(7, "/status")), Entscheidung::Status);
        // /tailscale traegt sein Argument mit; ohne Argument heisst "zeigen".
        assert_eq!(entscheiden(&liste(), &eingang(7, "/tailscale")), Entscheidung::Tailscale("".into()));
        assert_eq!(entscheiden(&liste(), &eingang(7, "/tailscale an")), Entscheidung::Tailscale("an".into()));
        assert_eq!(entscheiden(&liste(), &eingang(7, "/TAILSCALE aus")), Entscheidung::Tailscale("aus".into()));
        // Ein Fremder schaltet nichts.
        assert_eq!(entscheiden(&liste(), &eingang(99, "/tailscale aus")), Entscheidung::Abweisen);
        assert_eq!(entscheiden(&liste(), &eingang(7, "/neu@chimera_bot")), Entscheidung::Neu);
        assert_eq!(entscheiden(&liste(), &eingang(7, "/reset")), Entscheidung::Neu);
    }

    #[test]
    fn model_zeigt_die_liste_oder_nimmt_nummer_und_namen() {
        assert_eq!(entscheiden(&liste(), &eingang(7, "/model")), Entscheidung::Modelle("".into()));
        assert_eq!(entscheiden(&liste(), &eingang(7, "/model 3")), Entscheidung::Modelle("3".into()));
        assert_eq!(
            entscheiden(&liste(), &eingang(7, "/model@chimera_bot qwen2.5:14b")),
            Entscheidung::Modelle("qwen2.5:14b".into())
        );
    }

    #[test]
    fn ziele_werden_aufgeloest_und_falsche_mit_grund_abgelehnt() {
        let auswahl = json!({"anbieter": [
            {"id": "ollama", "bezeichnung": "Ollama", "chat": [
                {"modell": "a:7b", "denkstufen": []},
                {"modell": "denker:8b", "denkstufen": ["aus", "an"]}],
             "spezial": [{"modell": "ocr", "art": "vision"}], "unbekannt": []},
            {"id": "deepseek", "bezeichnung": "DeepSeek", "chat": [
                {"modell": "deepseek-flash", "denkstufen": ["aus", "niedrig", "hoch", "max"]}],
             "spezial": [], "unbekannt": [{"modell": "deepseek-x"}]}
        ]});
        // Nummer, Anbieter/Modell, bloßer Name -- alle drei Wege.
        assert_eq!(ziel_aufloesen("2", "an", &auswahl), Ok(("ollama".into(), "denker:8b".into(), "an".into())));
        assert_eq!(
            ziel_aufloesen("deepseek/deepseek-flash", "hoch", &auswahl),
            Ok(("deepseek".into(), "deepseek-flash".into(), "hoch".into()))
        );
        assert_eq!(
            ziel_aufloesen("deepseek-flash", "", &auswahl),
            Ok(("deepseek".into(), "deepseek-flash".into(), "".into()))
        );
        // Nicht waehlbar: Spezialmodell und ungemessenes werden benannt, nicht gewaehlt.
        let e = ziel_aufloesen("ollama/ocr", "", &auswahl).unwrap_err();
        assert!(e.contains("steht nicht in der Chat-Auswahl"), "{e}");
        let e = ziel_aufloesen("deepseek-x", "", &auswahl).unwrap_err();
        assert!(e.contains("kenne ich nicht"), "{e}");
        // Denkstufe, die das Modell nicht kann -- mit den moeglichen.
        let e = ziel_aufloesen("ollama/denker:8b", "hoch", &auswahl).unwrap_err();
        assert!(e.contains("Moeglich: aus, an"), "{e}");
        let e = ziel_aufloesen("ollama/a:7b", "an", &auswahl).unwrap_err();
        assert!(e.contains("Moeglich: keine"), "ohne Denkstufen: {e}");
        // Mehrdeutig: derselbe Name bei zwei Anbietern.
        let zwei = json!({"anbieter": [
            {"id": "a", "chat": [{"modell": "gleich", "denkstufen": []}]},
            {"id": "b", "chat": [{"modell": "gleich", "denkstufen": []}]}
        ]});
        let e = ziel_aufloesen("gleich", "", &zwei).unwrap_err();
        assert!(e.contains("bei mehreren Anbietern (a, b)"), "{e}");
    }

    #[test]
    fn die_wahltexte_nennen_was_gilt_und_was_waehlbar_ist() {
        let auswahl = json!({"anbieter": [
            {"id": "ollama", "bezeichnung": "Ollama im LAN", "chat": [
                {"modell": "gross:27b", "denkstufen": []},
                {"modell": "denker:8b", "denkstufen": ["aus", "an"]}],
             "spezial": [{"modell": "ocr", "art": "vision"}],
             "unbekannt": [{"modell": "stumm:1b"}]},
            {"id": "deepseek", "bezeichnung": "DeepSeek", "chat": [
                {"modell": "deepseek-flash", "denkstufen": ["aus", "niedrig", "hoch", "max"]}],
             "spezial": [], "unbekannt": []}
        ]});
        let wahl = json!({"anbieter": "ollama", "modell": "denker:8b", "denken": "an"});
        let t = chat_wahl_text(&auswahl, &wahl);
        assert!(t.starts_with("Gilt: ollama/denker:8b (Denken: an)."), "{t}");
        assert!(t.contains("  1. gross:27b\n"), "{t}");
        assert!(t.contains("\u{25b8} 2. denker:8b (Denkstufen: 2)\n"), "die Wahl ist markiert: {t}");
        assert!(t.contains("    ocr — vision (nicht für den Chat)\n"), "{t}");
        assert!(t.contains("    stumm:1b (Werkzeuge nicht gemessen)\n"), "{t}");
        assert!(t.contains("Denkstufen für denker:8b: aus, an"), "{t}");

        // Nummern in derselben Reihenfolge wie im Text.
        let ziele = chat_wahl_ziele(&auswahl);
        assert_eq!(ziele.len(), 3);
        assert_eq!(ziele[1], (2, "ollama".to_string(), "denker:8b".to_string()));
        assert_eq!(ziele[2], (3, "deepseek".to_string(), "deepseek-flash".to_string()));

        // Ohne Wahl: die Zeile sagt es, statt eine zu erfinden.
        assert_eq!(wahl_zeile(&json!({})), "Gilt: keine Wahl — der Anbieter entscheidet.");
        assert_eq!(
            wahl_zeile(&json!({"anbieter": "deepseek", "modell": "deepseek-flash"})),
            "Gilt: deepseek/deepseek-flash (Denkstufe: Vorgabe)."
        );
        // Kein Anbieter eingerichtet: der Text bleibt wahr.
        assert!(chat_wahl_text(&json!({"anbieter": []}), &json!({})).contains("Keine Anbieter eingerichtet"));
    }

    #[test]
    fn modell_wird_als_befehl_erkannt_auch_auf_deutsch() {
        for text in ["/modell", "/modell deepseek/deepseek-flash", "/model", "/modelle"] {
            assert!(matches!(entscheiden(&liste(), &eingang(7, text)), Entscheidung::Modelle(_)), "{text}");
        }
        assert_eq!(
            entscheiden(&liste(), &eingang(7, "/modell deepseek/deepseek-flash hoch")),
            Entscheidung::Modelle("deepseek/deepseek-flash hoch".into())
        );
    }

    #[test]
    fn stream_wird_erkannt_mit_und_ohne_wert() {
        assert_eq!(entscheiden(&liste(), &eingang(7, "/stream")), Entscheidung::Strom("".into()));
        assert_eq!(entscheiden(&liste(), &eingang(7, "/stream an")), Entscheidung::Strom("an".into()));
        assert_eq!(entscheiden(&liste(), &eingang(7, "/stream AUS")), Entscheidung::Strom("aus".into()));
    }

    #[test]
    fn ein_unbekannter_befehl_geht_als_text_an_die_sitzung() {
        assert_eq!(entscheiden(&liste(), &eingang(7, "/quatsch x")), Entscheidung::Fragen("/quatsch x".into()));
    }

    fn ev(art: &str, tuer: &str, text: &str) -> Ereignis {
        Ereignis { nr: 1, art: art.into(), tuer: tuer.into(), text: text.into(), bezug: String::new() }
    }

    #[test]
    fn antworten_und_fehler_gehen_an_telegram_egal_aus_welcher_tuer() {
        assert_eq!(fuer_telegram(&ev("antwort", "web", "hi")), Some("hi".into()));
        assert_eq!(fuer_telegram(&ev("antwort", "telegram", "hi")), Some("hi".into()));
        assert_eq!(fuer_telegram(&ev("fehler", "briefkasten", "oops")), Some("oops".into()));
    }

    #[test]
    fn die_eigene_eingabe_wird_nicht_zurueckgespiegelt_die_fremde_schon() {
        assert_eq!(fuer_telegram(&ev("eingabe", "telegram", "frage")), None);
        assert_eq!(fuer_telegram(&ev("eingabe", "web", "frage")), Some("[web] frage".into()));
        assert_eq!(fuer_telegram(&ev("eingabe", "briefkasten", "Post")), Some("[briefkasten] Post".into()));
    }

    #[test]
    fn zustand_und_umleitung_sind_kein_gespraech() {
        assert_eq!(fuer_telegram(&ev("zustand", "web", "denkt")), None);
        assert_eq!(fuer_telegram(&ev("umgeleitet", "web", "x")), None);
    }

    #[test]
    fn die_pause_waechst_und_ist_begrenzt() {
        assert_eq!(pause(0), Duration::from_secs(2));
        assert_eq!(pause(1), Duration::from_secs(4));
        assert_eq!(pause(5), Duration::from_secs(60));
        assert_eq!(pause(99), Duration::from_secs(60));
    }

    #[test]
    fn leere_antwort_wird_benannt_statt_leer_gesendet() {
        let (b, h) = server(vec![(200, r#"{"ok":true,"result":{}}"#.into())]);
        let api = Api::mit_basis(&b, "1:a");
        antworten(&api, 5, "");
        let anfragen = h.join().unwrap();
        assert!(anfragen[0].contains("keine Antwort"), "{}", anfragen[0]);
    }
}
