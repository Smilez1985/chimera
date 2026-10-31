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
            _ => {} // unbekannter Befehl: geht als Text an die Sitzung, wie bisher
        }
    }
    Entscheidung::Fragen(e.text.clone())
}

pub const HILFE: &str = "Ich bin Chimera. Schreib einfach los.\n/status -- was gerade laeuft\n/neu -- Gespraech von vorn";
pub const ABGEWIESEN: &str = "Wir kennen uns nicht. Ich rede nur mit Eingetragenen.";

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
            Entscheidung::Fragen(text) => {
                self.api.tippt(e.chat_id);
                if let Err(f) = sitzung::fragen(&self.sitzung, TUER, &text, &format!("tg-{}", e.update_id)) {
                    melden(Stufe::Fehler, &format!("Telegram: Sitzung nicht erreichbar: {f}"));
                    antworten(&self.api, e.chat_id, "Die Sitzung antwortet nicht. Versuch es gleich nochmal.");
                }
            }
        }
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
        assert_eq!(entscheiden(&liste(), &eingang(7, "/neu@chimera_bot")), Entscheidung::Neu);
        assert_eq!(entscheiden(&liste(), &eingang(7, "/reset")), Entscheidung::Neu);
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
