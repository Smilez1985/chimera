//! Die Web-Oberflaeche als Plattform aus Modulen (DESIGN Regel 5m).
//!
//! Das Gateway bedient sie selbst. Der Rahmen (Anmeldung, Menue, Router) kennt
//! kein einzelnes Modul: Er liest `module/*/manifest.json` (eingebaut im
//! Binary, dazu Dateien unter `CHIMERA_WEB_MODULE`) und bietet jedes gueltige
//! Modul im Menue an. Ein kaputtes Manifest verwirft nur dieses Modul und
//! wird gemeldet.
//!
//! Ohne Passwort startet die Oberflaeche nicht (Regel 5j).
//!
//! Alles Entscheidende steckt in `behandle()`: reine Funktion von Anfrage zu
//! Antwort, ohne Netz. Die Tests rufen sie direkt; ein Test geht zusaetzlich
//! durch einen echten Server.

use crate::sitzung;
use gemein::protokoll::{melden, Stufe};
use ring::{pbkdf2, rand::{SecureRandom, SystemRandom}};
use serde_json::{json, Value};
use std::collections::{BTreeMap, VecDeque};
use std::io::Read;
use std::num::NonZeroU32;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

pub const PORT_VORGABE: u16 = 8080;
pub const ITERATIONEN: u32 = 100_000;
const KOPF: &str = "pbkdf2-sha256";
/// Wie lange eine Anmeldung gilt.
const SITZUNG_DAUER: Duration = Duration::from_secs(12 * 3600);
/// Fehlversuche je Fenster, danach 429.
const MAX_FEHLVERSUCHE: usize = 5;
const FENSTER: Duration = Duration::from_secs(60);
const MAX_BODY: u64 = 64 * 1024;
/// Long-Poll: so lange wartet eine Anfrage hoechstens auf Ereignisse.
const POLL: Duration = Duration::from_secs(20);
const RING: usize = 500;

// --- eingebaute Module ----------------------------------------------------

struct Eingebaut {
    name: &'static str,
    manifest: &'static str,
    dateien: &'static [(&'static str, &'static str, &'static str)], // (datei, typ, inhalt)
}

const EINGEBAUT: &[Eingebaut] = &[Eingebaut {
    name: "chat",
    manifest: include_str!("../web/module/chat/manifest.json"),
    dateien: &[("chat.js", "text/javascript; charset=utf-8", include_str!("../web/module/chat/chat.js"))],
}];

const RAHMEN_HTML: &str = include_str!("../web/rahmen.html");

// --- Passwort -------------------------------------------------------------

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn unhex(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 || !s.is_ascii() {
        return None;
    }
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok()).collect()
}

/// Aus einem Passwort die Zeile fuer die `.env`: `pbkdf2-sha256$ITER$SALZ$HASH`.
pub fn hash_erzeugen(passwort: &str) -> Result<String, String> {
    let mut salz = [0u8; 16];
    SystemRandom::new().fill(&mut salz).map_err(|_| "kein Zufall verfuegbar")?;
    let mut h = [0u8; 32];
    pbkdf2::derive(
        pbkdf2::PBKDF2_HMAC_SHA256,
        NonZeroU32::new(ITERATIONEN).unwrap(),
        &salz,
        passwort.as_bytes(),
        &mut h,
    );
    Ok(format!("{KOPF}${ITERATIONEN}${}${}", hex(&salz), hex(&h)))
}

/// Stimmt das Passwort mit der Zeile? Vergleich zeitkonstant (ring).
pub fn hash_pruefen(zeile: &str, passwort: &str) -> bool {
    let t: Vec<&str> = zeile.trim().split('$').collect();
    if t.len() != 4 || t[0] != KOPF {
        return false;
    }
    let (Some(n), Some(salz), Some(h)) = (
        t[1].parse::<u32>().ok().and_then(NonZeroU32::new),
        unhex(t[2]),
        unhex(t[3]),
    ) else {
        return false;
    };
    pbkdf2::verify(pbkdf2::PBKDF2_HMAC_SHA256, n, &salz, passwort.as_bytes(), &h).is_ok()
}

/// Ist die Zeile ueberhaupt ein Hash dieser Form? (Fuer die Konfigpruefung.)
pub fn hash_gueltig(zeile: &str) -> bool {
    let t: Vec<&str> = zeile.trim().split('$').collect();
    t.len() == 4
        && t[0] == KOPF
        && t[1].parse::<u32>().map(|n| n > 0).unwrap_or(false)
        && unhex(t[2]).map(|s| s.len() >= 8).unwrap_or(false)
        && unhex(t[3]).map(|s| s.len() == 32).unwrap_or(false)
}

// --- Module ---------------------------------------------------------------

#[derive(Debug, Clone, PartialEq)]
pub struct Modul {
    pub name: String,
    pub titel: Value,
    pub symbol: String,
    pub reihenfolge: i64,
    pub einstieg: String,
    pub element: String,
    pub rechte: Vec<String>,
    pub eingebaut: bool,
}

fn name_ok(s: &str) -> bool {
    !s.is_empty() && s.len() <= 32 && s.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

fn datei_ok(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 64
        && s != "."
        && !s.contains("..")
        && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'_' || b == b'-')
}

/// Ein Manifest pruefen. Fehler nennt den Grund (wird gemeldet, nicht verschluckt).
pub fn manifest_lesen(verzeichnis: &str, text: &str, eingebaut: bool) -> Result<Modul, String> {
    let v: Value = serde_json::from_str(text).map_err(|e| format!("kein JSON: {e}"))?;
    let name = v["name"].as_str().ok_or("name fehlt")?;
    if !name_ok(name) {
        return Err(format!("name '{name}' unzulaessig (a-z, 0-9, -)"));
    }
    if name != verzeichnis {
        return Err(format!("name '{name}' passt nicht zum Verzeichnis '{verzeichnis}'"));
    }
    let titel = match &v["titel"] {
        Value::String(_) | Value::Object(_) => v["titel"].clone(),
        _ => return Err("titel fehlt (Text oder je Sprache)".into()),
    };
    let einstieg = v["einstieg"].as_str().ok_or("einstieg fehlt")?;
    if !datei_ok(einstieg) {
        return Err(format!("einstieg '{einstieg}' unzulaessig"));
    }
    let element = v["element"].as_str().ok_or("element fehlt (Name des Web Components)")?;
    if !element.contains('-') || !element.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-') {
        return Err(format!("element '{element}' ist kein gueltiger Elementname"));
    }
    let rechte = v["rechte"]
        .as_array()
        .ok_or("rechte fehlt (Liste, darf leer sein)")?
        .iter()
        .map(|r| r.as_str().map(str::to_string).ok_or("rechte: nur Texte"))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(Modul {
        name: name.to_string(),
        titel,
        symbol: v["symbol"].as_str().unwrap_or("").to_string(),
        reihenfolge: v["reihenfolge"].as_i64().unwrap_or(100),
        einstieg: einstieg.to_string(),
        element: element.to_string(),
        rechte,
        eingebaut,
    })
}

/// Alle gueltigen Module: eingebaute, dann Dateien aus `dir`. Gleicher Name:
/// das eingebaute gewinnt (ein nachgelegtes darf es nicht ersetzen). Ergebnis
/// sortiert nach Reihenfolge, dann Name; zweiter Teil sind die Meldungen.
pub fn module_erkennen(dir: Option<&Path>) -> (Vec<Modul>, Vec<String>) {
    let mut ok: BTreeMap<String, Modul> = BTreeMap::new();
    let mut fehler = Vec::new();
    for e in EINGEBAUT {
        match manifest_lesen(e.name, e.manifest, true) {
            Ok(m) => {
                ok.insert(m.name.clone(), m);
            }
            Err(f) => fehler.push(format!("eingebautes Modul {}: {f}", e.name)),
        }
    }
    if let Some(d) = dir {
        if let Ok(rd) = std::fs::read_dir(d) {
            let mut namen: Vec<String> =
                rd.flatten().filter(|e| e.path().is_dir()).filter_map(|e| e.file_name().into_string().ok()).collect();
            namen.sort();
            for n in namen {
                let pfad = d.join(&n).join("manifest.json");
                match std::fs::read_to_string(&pfad) {
                    Err(e) => fehler.push(format!("Modul {n}: manifest.json nicht lesbar: {e}")),
                    Ok(t) => match manifest_lesen(&n, &t, false) {
                        Err(f) => fehler.push(format!("Modul {n}: {f}")),
                        Ok(m) if ok.contains_key(&m.name) => {
                            fehler.push(format!("Modul {n}: Name schon vergeben, uebergangen"))
                        }
                        Ok(m) => {
                            ok.insert(m.name.clone(), m);
                        }
                    },
                }
            }
        }
    }
    let mut v: Vec<Modul> = ok.into_values().collect();
    v.sort_by(|a, b| (a.reihenfolge, &a.name).cmp(&(b.reihenfolge, &b.name)));
    (v, fehler)
}

fn modul_datei(dir: Option<&Path>, name: &str, datei: &str) -> Option<(String, Vec<u8>)> {
    if !name_ok(name) || !datei_ok(datei) {
        return None;
    }
    if let Some(e) = EINGEBAUT.iter().find(|e| e.name == name) {
        return e
            .dateien
            .iter()
            .find(|(d, _, _)| *d == datei)
            .map(|(_, t, i)| (t.to_string(), i.as_bytes().to_vec()));
    }
    let p = dir?.join(name).join(datei);
    let typ = match p.extension().and_then(|e| e.to_str()) {
        Some("js") => "text/javascript; charset=utf-8",
        Some("css") => "text/css; charset=utf-8",
        Some("json") => "application/json",
        Some("svg") => "image/svg+xml",
        Some("png") => "image/png",
        _ => return None, // unbekannte Endung: nicht ausliefern
    };
    std::fs::read(&p).ok().map(|b| (typ.to_string(), b))
}

// --- Zustand --------------------------------------------------------------

/// Puffer der Ereignisse der Hauptsitzung fuer die Seite (Long-Poll).
pub struct Strom {
    inner: Mutex<VecDeque<sitzung::Ereignis>>,
    cv: Condvar,
}

impl Strom {
    pub fn neu() -> Arc<Strom> {
        Arc::new(Strom { inner: Mutex::new(VecDeque::new()), cv: Condvar::new() })
    }
    pub fn ein(&self, e: sitzung::Ereignis) {
        let mut q = self.inner.lock().unwrap();
        q.push_back(e);
        while q.len() > RING {
            q.pop_front();
        }
        self.cv.notify_all();
    }
    /// Ereignisse mit Nummer > `seit`; wartet bis `frist`, wenn keine da sind.
    pub fn seit(&self, seit: u64, frist: Duration) -> Vec<sitzung::Ereignis> {
        let ende = Instant::now() + frist;
        let mut q = self.inner.lock().unwrap();
        loop {
            let r: Vec<_> = q.iter().filter(|e| e.nr > seit).cloned().collect();
            if !r.is_empty() {
                return r;
            }
            let rest = ende.saturating_duration_since(Instant::now());
            if rest.is_zero() {
                return r;
            }
            q = self.cv.wait_timeout(q, rest).unwrap().0;
        }
    }
}

pub struct Zustand {
    pub hash: String,
    pub modul_dir: Option<PathBuf>,
    pub sitzung_socket: PathBuf,
    pub strom: Arc<Strom>,
    /// Nur Anfragen aus dem eigenen Netz bedienen (Vorgabe an, `CHIMERA_WEB_LAN_NUR=0` schaltet ab).
    pub lan_nur: bool,
    angemeldet: Mutex<BTreeMap<String, Instant>>,
    fehlversuche: Mutex<VecDeque<Instant>>,
}

impl Zustand {
    pub fn neu(hash: String, modul_dir: Option<PathBuf>, sitzung_socket: PathBuf, strom: Arc<Strom>) -> Zustand {
        Zustand {
            hash,
            modul_dir,
            sitzung_socket,
            strom,
            lan_nur: true,
            angemeldet: Mutex::new(BTreeMap::new()),
            fehlversuche: Mutex::new(VecDeque::new()),
        }
    }

    fn token_neu(&self) -> String {
        let mut b = [0u8; 32];
        SystemRandom::new().fill(&mut b).expect("Zufall");
        let t = hex(&b);
        let mut m = self.angemeldet.lock().unwrap();
        let jetzt = Instant::now();
        m.retain(|_, ende| *ende > jetzt);
        m.insert(t.clone(), jetzt + SITZUNG_DAUER);
        t
    }

    fn token_gueltig(&self, t: &str) -> bool {
        let m = self.angemeldet.lock().unwrap();
        m.get(t).map(|e| *e > Instant::now()).unwrap_or(false)
    }

    /// Darf ein weiterer Versuch stattfinden?
    fn versuch_frei(&self) -> bool {
        let mut q = self.fehlversuche.lock().unwrap();
        let jetzt = Instant::now();
        while q.front().map(|t| jetzt.duration_since(*t) > FENSTER).unwrap_or(false) {
            q.pop_front();
        }
        q.len() < MAX_FEHLVERSUCHE
    }
    fn fehlversuch(&self) {
        self.fehlversuche.lock().unwrap().push_back(Instant::now());
    }
}

// --- Anfrage und Antwort --------------------------------------------------

pub struct Anfrage<'a> {
    pub methode: &'a str,
    pub pfad: &'a str,
    pub query: &'a str,
    pub cookie: &'a str,
    /// Wert des Kopfes `X-Chimera` (Schutz gegen fremde Seiten, zusaetzlich zu SameSite).
    pub marke: &'a str,
    pub body: &'a [u8],
}

pub struct Antwort {
    pub status: u16,
    pub typ: String,
    pub body: Vec<u8>,
    pub cookie: Option<String>,
}

fn json_antwort(status: u16, v: Value) -> Antwort {
    Antwort { status, typ: "application/json".into(), body: v.to_string().into_bytes(), cookie: None }
}
fn fehler(status: u16, text: &str) -> Antwort {
    json_antwort(status, json!({"ok": false, "fehler": text}))
}

fn cookie_wert<'a>(kopf: &'a str, name: &str) -> Option<&'a str> {
    kopf.split(';').filter_map(|p| p.trim().split_once('=')).find(|(k, _)| *k == name).map(|(_, v)| v)
}

fn query_wert(q: &str, name: &str) -> Option<String> {
    q.split('&').filter_map(|p| p.split_once('=')).find(|(k, _)| *k == name).map(|(_, v)| v.to_string())
}

const COOKIE: &str = "chimera_sitzung";

/// Die ganze Entscheidung: Anfrage rein, Antwort raus.
pub fn behandle(z: &Zustand, a: &Anfrage) -> Antwort {
    let ist_post = a.methode == "POST";
    if a.methode != "GET" && !ist_post {
        return fehler(405, "Methode nicht erlaubt");
    }
    // Aenderungen nur mit Marke: eine fremde Seite kann sie nicht setzen.
    if ist_post && a.marke != "1" {
        return fehler(403, "Marke fehlt");
    }

    // Offen: nur die Huelle und die Anmeldung. Kein Inhalt, kein Modul.
    match (a.methode, a.pfad) {
        ("GET", "/") => {
            return Antwort {
                status: 200,
                typ: "text/html; charset=utf-8".into(),
                body: RAHMEN_HTML.as_bytes().to_vec(),
                cookie: None,
            }
        }
        ("POST", "/api/login") => return login(z, a),
        _ => {}
    }

    let angemeldet = cookie_wert(a.cookie, COOKIE).map(|t| z.token_gueltig(t)).unwrap_or(false);
    if !angemeldet {
        return fehler(401, "nicht angemeldet");
    }

    match (a.methode, a.pfad) {
        ("POST", "/api/logout") => {
            if let Some(t) = cookie_wert(a.cookie, COOKIE) {
                z.angemeldet.lock().unwrap().remove(t);
            }
            let mut r = json_antwort(200, json!({"ok": true}));
            r.cookie = Some(format!("{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"));
            r
        }
        ("GET", "/api/module") => {
            let (m, f) = module_erkennen(z.modul_dir.as_deref());
            for x in &f {
                melden(Stufe::Warnung, &format!("Web-Modul verworfen: {x}"));
            }
            json_antwort(
                200,
                json!({"ok": true, "version": gemein::version(), "module": m.iter().map(|m| json!({
                    "name": m.name, "titel": m.titel, "symbol": m.symbol,
                    "reihenfolge": m.reihenfolge, "einstieg": m.einstieg,
                    "element": m.element, "rechte": m.rechte,
                })).collect::<Vec<_>>(), "verworfen": f}),
            )
        }
        ("GET", p) if p.starts_with("/module/") => {
            let rest = &p["/module/".len()..];
            match rest.split_once('/') {
                Some((n, d)) => match modul_datei(z.modul_dir.as_deref(), n, d) {
                    Some((typ, body)) => Antwort { status: 200, typ, body, cookie: None },
                    None => fehler(404, "nicht gefunden"),
                },
                None => fehler(404, "nicht gefunden"),
            }
        }
        (_, p) if p.starts_with("/api/chat/") => chat_api(z, a, &p["/api/chat/".len()..]),
        _ => fehler(404, "nicht gefunden"),
    }
}

fn login(z: &Zustand, a: &Anfrage) -> Antwort {
    if !z.versuch_frei() {
        return fehler(429, "zu viele Fehlversuche, bitte eine Minute warten");
    }
    let v: Value = match serde_json::from_slice(a.body) {
        Ok(v) => v,
        Err(_) => return fehler(400, "kein JSON"),
    };
    let pw = v["passwort"].as_str().unwrap_or("");
    if !pw.is_empty() && hash_pruefen(&z.hash, pw) {
        let t = z.token_neu();
        let mut r = json_antwort(200, json!({"ok": true}));
        r.cookie = Some(format!(
            "{COOKIE}={t}; HttpOnly; SameSite=Strict; Path=/; Max-Age={}",
            SITZUNG_DAUER.as_secs()
        ));
        r
    } else {
        z.fehlversuch();
        melden(Stufe::Warnung, "Web: Anmeldung mit falschem Passwort.");
        fehler(401, "Passwort falsch")
    }
}

fn ereignis_json(e: &sitzung::Ereignis) -> Value {
    json!({"nr": e.nr, "art": e.art, "tuer": e.tuer, "text": e.text, "ref": e.bezug})
}

/// Darf das Modul `name` das Recht `recht` ausueben? Nur, was sein Manifest nennt.
fn hat_recht(module: &[Modul], name: &str, recht: &str) -> bool {
    module.iter().any(|x| x.name == name && x.rechte.iter().any(|r| r == recht))
}

fn chat_api(z: &Zustand, a: &Anfrage, was: &str) -> Antwort {
    // Das Recht steht im Manifest; das Gateway reicht nur durch, was eingetragen ist.
    let (m, _) = module_erkennen(z.modul_dir.as_deref());
    if !hat_recht(&m, "chat", "chat") {
        return fehler(403, "Modul chat hat das Recht 'chat' nicht");
    }
    match (a.methode, was) {
        ("POST", "senden") => {
            let v: Value = match serde_json::from_slice(a.body) {
                Ok(v) => v,
                Err(_) => return fehler(400, "kein JSON"),
            };
            let text = v["text"].as_str().unwrap_or("").trim();
            if text.is_empty() {
                return fehler(400, "text fehlt");
            }
            // Immer an `haupt`. Eine andere Sitzung wird vom Dienst umgeleitet (5s).
            let sid = v["sitzung"].as_str().unwrap_or("haupt");
            match sitzung::anfragen(
                &z.sitzung_socket,
                &json!({"op": "frage", "tuer": "web", "text": text, "sitzung": sid, "ref": ""}),
            ) {
                Ok(r) => json_antwort(200, json!({"ok": true, "umgeleitet": r["umgeleitet"] == true})),
                Err(e) => fehler(502, &format!("Sitzung nicht erreichbar: {e}")),
            }
        }
        ("GET", "strom") => {
            let seit = query_wert(a.query, "seit").and_then(|s| s.parse().ok()).unwrap_or(0u64);
            let frist = if query_wert(a.query, "warten").as_deref() == Some("0") { Duration::ZERO } else { POLL };
            let ev = z.strom.seit(seit, frist);
            json_antwort(200, json!({"ok": true, "ereignisse": ev.iter().map(ereignis_json).collect::<Vec<_>>()}))
        }
        ("GET", "sitzungen") => match sitzung::anfragen(&z.sitzung_socket, &json!({"op": "sitzungen"})) {
            Ok(r) => json_antwort(200, r),
            Err(e) => fehler(502, &format!("Sitzung nicht erreichbar: {e}")),
        },
        ("GET", "lesen") => {
            let sid = query_wert(a.query, "sitzung").unwrap_or_default();
            if sid.is_empty() || !sid.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_' || b == b'.') {
                return fehler(400, "sitzung fehlt oder ungueltig");
            }
            match sitzung::anfragen(&z.sitzung_socket, &json!({"op": "lesen", "sitzung": sid, "max": 200})) {
                Ok(r) => json_antwort(200, r),
                Err(e) => fehler(502, &format!("Sitzung nicht erreichbar: {e}")),
            }
        }
        _ => fehler(404, "nicht gefunden"),
    }
}

// --- Betrieb --------------------------------------------------------------

/// Was die Umgebung ueber die Web-Oberflaeche sagt.
#[derive(Debug, PartialEq)]
pub enum Konfig {
    Aus,
    Falsch(String),
    Bereit { hash: String, adresse: String },
}

/// `CHIMERA_WEB_PASSWORT_HASH` leer: aus (kein Fehler, Regel 5j). Gesetzt, aber
/// kein gueltiger Hash: Fehlkonfiguration.
pub fn konfig_aus(hash: Option<&str>, port: Option<&str>, bind: Option<&str>) -> Konfig {
    let h = hash.map(str::trim).unwrap_or("");
    if h.is_empty() {
        return Konfig::Aus;
    }
    if !hash_gueltig(h) {
        return Konfig::Falsch("CHIMERA_WEB_PASSWORT_HASH hat nicht die Form pbkdf2-sha256$N$SALZ$HASH (chimera-tor --passwort-hash).".into());
    }
    let p = match port.map(str::trim).filter(|s| !s.is_empty()) {
        None => PORT_VORGABE,
        Some(s) => match s.parse::<u16>() {
            Ok(p) if p > 0 => p,
            _ => return Konfig::Falsch(format!("CHIMERA_WEB_PORT '{s}' ist keine Portnummer.")),
        },
    };
    let b = bind.map(str::trim).filter(|s| !s.is_empty()).unwrap_or("0.0.0.0");
    Konfig::Bereit { hash: h.to_string(), adresse: format!("{b}:{p}") }
}

pub fn konfig() -> Konfig {
    konfig_aus(
        std::env::var("CHIMERA_WEB_PASSWORT_HASH").ok().as_deref(),
        std::env::var("CHIMERA_WEB_PORT").ok().as_deref(),
        std::env::var("CHIMERA_WEB_BIND").ok().as_deref(),
    )
}

/// Dem Strom der Hauptsitzung zuhoeren und in den Puffer legen; bei Abbruch
/// mit der letzten Nummer neu anmelden (nichts doppelt, nichts verloren).
fn strom_halten(sock: PathBuf, strom: Arc<Strom>) {
    let mut seit = 0u64;
    let mut pause = 1u64;
    loop {
        let vorher = seit;
        let s = strom.clone();
        let r = sitzung::hoeren(&sock, &mut seit, |e| s.ein(e.clone()));
        if seit > vorher {
            pause = 1;
        }
        if let Err(e) = r {
            melden(Stufe::Warnung, &format!("Web: Sitzungsstrom: {e}; neuer Versuch in {pause} s."));
        }
        std::thread::sleep(Duration::from_secs(pause));
        pause = (pause * 2).min(30);
    }
}

/// Gehoert die Quelladresse zum eigenen Netz? Loopback, private (RFC 1918),
/// Link-Local und IPv6-ULA ja; alles andere (oeffentlich) nein. IPv4 in
/// IPv6-Schreibweise wird als IPv4 beurteilt.
pub fn ip_im_lan(ip: std::net::IpAddr) -> bool {
    use std::net::IpAddr;
    match ip {
        IpAddr::V4(a) => a.is_loopback() || a.is_private() || a.is_link_local(),
        IpAddr::V6(a) => match a.to_ipv4_mapped() {
            Some(v4) => ip_im_lan(IpAddr::V4(v4)),
            None => a.is_loopback() || (a.segments()[0] & 0xfe00) == 0xfc00 || (a.segments()[0] & 0xffc0) == 0xfe80,
        },
    }
}

fn kopf(name: &str, wert: &str) -> tiny_http::Header {
    tiny_http::Header::from_bytes(name.as_bytes(), wert.as_bytes()).expect("Kopf")
}

fn bedienen(z: &Zustand, mut req: tiny_http::Request) {
    if z.lan_nur {
        // Ohne erkennbare Quelladresse wird nicht bedient (Verdachtsfall, kein Durchlass).
        let im_lan = req.remote_addr().map(|a| ip_im_lan(a.ip())).unwrap_or(false);
        if !im_lan {
            melden(Stufe::Warnung, &format!("Web: Anfrage von ausserhalb des eigenen Netzes abgewiesen ({}).", req.remote_addr().map(|a| a.ip().to_string()).unwrap_or_else(|| "?".into())));
            let _ = req.respond(tiny_http::Response::from_string("nur im eigenen Netz").with_status_code(403));
            return;
        }
    }
    let methode = req.method().as_str().to_string();
    let url = req.url().to_string();
    let (pfad, query) = url.split_once('?').unwrap_or((url.as_str(), ""));
    let (pfad, query) = (pfad.to_string(), query.to_string());
    let hole = |n: &str| {
        req.headers()
            .iter()
            .find(|h| h.field.as_str().as_str().eq_ignore_ascii_case(n))
            .map(|h| h.value.as_str().to_string())
            .unwrap_or_default()
    };
    let cookie = hole("Cookie");
    let marke = hole("X-Chimera");
    let mut body = Vec::new();
    let _ = req.as_reader().take(MAX_BODY).read_to_end(&mut body);
    let a = Anfrage { methode: &methode, pfad: &pfad, query: &query, cookie: &cookie, marke: &marke, body: &body };
    let r = behandle(z, &a);
    let mut resp = tiny_http::Response::from_data(r.body)
        .with_status_code(r.status)
        .with_header(kopf("Content-Type", &r.typ))
        .with_header(kopf("Cache-Control", "no-store"))
        .with_header(kopf("X-Content-Type-Options", "nosniff"))
        .with_header(kopf("X-Frame-Options", "SAMEORIGIN"))
        .with_header(kopf(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:",
        ));
    if let Some(c) = r.cookie {
        resp = resp.with_header(kopf("Set-Cookie", &c));
    }
    let _ = req.respond(resp);
}

/// Server binden und bedienen (Hintergrund). Gibt die gebundene Adresse zurueck.
pub fn starten(hash: String, adresse: &str, z_modul: Option<PathBuf>, sitzung_socket: PathBuf) -> Result<String, String> {
    let server = tiny_http::Server::http(adresse).map_err(|e| format!("{adresse}: {e}"))?;
    let gebunden = server.server_addr().to_string();
    let server = Arc::new(server);
    let strom = Strom::neu();
    {
        let (s, st) = (sitzung_socket.clone(), strom.clone());
        std::thread::Builder::new().name("web-strom".into()).spawn(move || strom_halten(s, st)).map_err(|e| e.to_string())?;
    }
    let mut zs = Zustand::neu(hash, z_modul, sitzung_socket, strom);
    zs.lan_nur = std::env::var("CHIMERA_WEB_LAN_NUR").map(|v| v.trim() != "0").unwrap_or(true);
    let z = Arc::new(zs);
    // Mehrere Arbeiter: ein wartender Long-Poll darf die anderen nicht aufhalten.
    for i in 0..6 {
        let (srv, z) = (server.clone(), z.clone());
        std::thread::Builder::new()
            .name(format!("web-{i}"))
            .spawn(move || {
                while let Ok(req) = srv.recv() {
                    bedienen(&z, req);
                }
            })
            .map_err(|e| e.to_string())?;
    }
    Ok(gebunden)
}

pub fn modul_verzeichnis() -> Option<PathBuf> {
    match std::env::var("CHIMERA_WEB_MODULE") {
        Ok(p) if !p.trim().is_empty() => Some(PathBuf::from(p.trim())),
        _ => {
            let p = PathBuf::from("/opt/chimera/web/module");
            p.is_dir().then_some(p)
        }
    }
}

#[cfg(test)]
mod tests;
