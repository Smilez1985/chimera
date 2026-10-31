//! Messwerte fuer das Status-Modul der Web-Oberflaeche (DESIGN Regel 5m).
//!
//! **Erweitern:** Eine neue Messung ist
//!   1. eine Struktur mit `impl Sonde` (liefert fertige [`Zeile`]n) und
//!   2. eine Zeile in [`sonden()`].
//! Gateway-Weg und Frontend bleiben unveraendert: Die Seite zeigt nur Zeilen
//! (Bezeichnung, Text, Balken, Stufe). Die Parser sind reine Funktionen von
//! Text zu Wert, damit Tests sie aufrufen statt nachzurechnen. Ein Wert, der
//! sich nicht lesen laesst, ist `None` und erscheint als "nicht lesbar" --
//! nie 0 und nie geraten (GLOBAL: leere Ausgabe ist ein Verdachtsfall).

use serde_json::{json, Value};
use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

// --- Zeile ----------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Stufe {
    Ok,
    Warnung,
    Kritisch,
    Unbekannt,
}

impl Stufe {
    fn name(self) -> &'static str {
        match self {
            Stufe::Ok => "ok",
            Stufe::Warnung => "warnung",
            Stufe::Kritisch => "kritisch",
            Stufe::Unbekannt => "unbekannt",
        }
    }
}

/// Eine Anzeigezeile. `wert`/`einheit` sind fuer spaetere Verlaeufe maschinenlesbar,
/// `text` ist, was der Nutzer liest, `anteil` (0..100) zeichnet den Balken.
#[derive(Debug, Clone, PartialEq)]
pub struct Zeile {
    pub id: String,
    pub gruppe: &'static str,
    pub titel: String,
    pub text: String,
    pub wert: Option<f64>,
    pub einheit: &'static str,
    pub anteil: Option<f64>,
    pub stufe: Stufe,
}

impl Zeile {
    pub fn nicht_lesbar(id: &str, gruppe: &'static str, titel: &str) -> Zeile {
        Zeile {
            id: id.into(),
            gruppe,
            titel: titel.into(),
            text: "nicht lesbar".into(),
            wert: None,
            einheit: "",
            anteil: None,
            stufe: Stufe::Unbekannt,
        }
    }

    pub fn json(&self) -> Value {
        json!({
            "id": self.id, "gruppe": self.gruppe, "titel": self.titel, "text": self.text,
            "wert": self.wert, "einheit": self.einheit, "anteil": self.anteil,
            "stufe": self.stufe.name(),
        })
    }
}

/// Stufe aus einem Anteil (0..100): ab `warn` Warnung, ab `krit` kritisch.
pub fn stufe_aus_anteil(anteil: f64, warn: f64, krit: f64) -> Stufe {
    if anteil >= krit {
        Stufe::Kritisch
    } else if anteil >= warn {
        Stufe::Warnung
    } else {
        Stufe::Ok
    }
}

// --- Formatierung -----------------------------------------------------------

pub fn fmt_mib(mib: u64) -> String {
    if mib >= 1024 {
        format!("{:.1} GB", mib as f64 / 1024.0)
    } else {
        format!("{mib} MB")
    }
}

pub fn fmt_dauer(s: u64) -> String {
    let (t, h, m) = (s / 86_400, (s % 86_400) / 3600, (s % 3600) / 60);
    if t > 0 {
        format!("{t} d {h} h")
    } else if h > 0 {
        format!("{h} h {m} min")
    } else {
        format!("{m} min")
    }
}

// --- Parser (rein) -----------------------------------------------------------

/// Millicelsius aus `thermal_zone0/temp` in Grad.
pub fn temperatur_c(text: &str) -> Option<f64> {
    let m: i64 = text.trim().parse().ok()?;
    // Eine Zahl ausserhalb des Sinnvollen ist ein Lesefehler, keine Temperatur.
    if !(-40_000..=150_000).contains(&m) {
        return None;
    }
    Some(m as f64 / 1000.0)
}

/// `/proc/meminfo`: (gesamt, verfuegbar) in MiB.
pub fn speicher_mib(text: &str) -> Option<(u64, u64)> {
    let feld = |name: &str| -> Option<u64> {
        let z = text.lines().find(|l| l.starts_with(name))?;
        z.split_whitespace().nth(1)?.parse::<u64>().ok()
    };
    let (gesamt, frei) = (feld("MemTotal:")?, feld("MemAvailable:")?);
    if gesamt == 0 || frei > gesamt {
        return None;
    }
    Some((gesamt / 1024, frei / 1024))
}

/// `/proc/loadavg`: die drei Lastwerte.
pub fn last(text: &str) -> Option<[f64; 3]> {
    let mut t = text.split_whitespace();
    let a = t.next()?.parse().ok()?;
    let b = t.next()?.parse().ok()?;
    let c = t.next()?.parse().ok()?;
    Some([a, b, c])
}

/// `/proc/uptime`: Sekunden seit dem Start.
pub fn laufzeit_s(text: &str) -> Option<u64> {
    let s: f64 = text.split_whitespace().next()?.parse().ok()?;
    if s < 0.0 {
        return None;
    }
    Some(s as u64)
}

/// Ausgabe von `df -Pk`: (gesamt, belegt) in MiB der letzten Zeile.
pub fn platte_mib(text: &str) -> Option<(u64, u64)> {
    let z = text.lines().filter(|l| !l.trim().is_empty()).last()?;
    let t: Vec<&str> = z.split_whitespace().collect();
    if t.len() < 4 {
        return None;
    }
    let (gesamt, belegt) = (t[1].parse::<u64>().ok()?, t[2].parse::<u64>().ok()?);
    if gesamt == 0 || belegt > gesamt {
        return None;
    }
    Some((gesamt / 1024, belegt / 1024))
}

/// Ausgabe von `systemctl is-active`: nur bekannte Zustaende, sonst `unbekannt`.
pub fn dienstzustand(text: &str) -> &'static str {
    match text.trim() {
        "active" => "aktiv",
        "inactive" => "inaktiv",
        "failed" => "gescheitert",
        "activating" => "startet",
        "deactivating" => "stoppt",
        _ => "unbekannt",
    }
}

/// Zaehlerstand einer `cpu`-Zeile aus `/proc/stat`: Summe und Leerlauf (idle + iowait).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Zaehler {
    pub summe: u64,
    pub leer: u64,
}

/// `/proc/stat`: gesamt und je Kern. Weniger als 4 Felder je Zeile = unlesbar.
pub fn cpu_zaehler(text: &str) -> Option<(Zaehler, Vec<Zaehler>)> {
    let zeile = |l: &str| -> Option<Zaehler> {
        let w: Vec<u64> = l.split_whitespace().skip(1).map(|x| x.parse().ok()).collect::<Option<Vec<_>>>()?;
        if w.len() < 4 {
            return None;
        }
        // user nice system idle iowait irq softirq steal (guest steckt schon in user)
        let summe: u64 = w.iter().take(8).sum();
        let leer = w[3] + w.get(4).copied().unwrap_or(0);
        Some(Zaehler { summe, leer })
    };
    let mut gesamt = None;
    let mut kerne = Vec::new();
    for l in text.lines() {
        let kopf = l.split_whitespace().next().unwrap_or("");
        if kopf == "cpu" {
            gesamt = zeile(l);
        } else if kopf.len() > 3 && kopf.starts_with("cpu") && kopf[3..].bytes().all(|b| b.is_ascii_digit()) {
            kerne.push(zeile(l)?);
        }
    }
    Some((gesamt?, kerne))
}

/// Auslastung in % zwischen zwei Staenden. Kein Fortschritt oder rueckwaerts = `None`.
pub fn cpu_prozent(vorher: Zaehler, jetzt: Zaehler) -> Option<f64> {
    if jetzt.summe <= vorher.summe || jetzt.leer < vorher.leer {
        return None;
    }
    let (ds, dl) = ((jetzt.summe - vorher.summe) as f64, (jetzt.leer - vorher.leer) as f64);
    if dl > ds {
        return None;
    }
    Some(((ds - dl) / ds * 100.0).clamp(0.0, 100.0))
}

/// kHz-Zahl aus `scaling_cur_freq` / `cpuinfo_max_freq` in MHz.
pub fn takt_mhz(text: &str) -> Option<u64> {
    let k: u64 = text.trim().parse().ok()?;
    if k == 0 || k > 10_000_000 {
        return None;
    }
    Some(k / 1000)
}

// --- Lesen ---------------------------------------------------------------------

pub struct Kontext<'a> {
    pub wurzel: &'a Path,
    /// `false` in Tests: keine Kindprozesse (`df`, `systemctl`).
    pub mit_befehlen: bool,
}

impl Kontext<'_> {
    fn pfad(&self, p: &str) -> std::path::PathBuf {
        self.wurzel.join(p.trim_start_matches('/'))
    }
    fn lesen(&self, p: &str) -> Option<String> {
        std::fs::read_to_string(self.pfad(p)).ok().filter(|s| !s.trim().is_empty())
    }
}

/// Einen Befehl mit Frist ausfuehren; die Ausgabe zaehlt auch bei rc != 0 (`is-active`).
fn befehl(prog: &str, args: &[&str], frist: Duration) -> Option<String> {
    let mut kind = Command::new(prog).args(args).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::null()).spawn().ok()?;
    let start = Instant::now();
    loop {
        match kind.try_wait().ok()? {
            Some(_) => break,
            None if start.elapsed() > frist => {
                let _ = kind.kill();
                let _ = kind.wait();
                return None;
            }
            None => std::thread::sleep(Duration::from_millis(20)),
        }
    }
    let mut s = String::new();
    std::io::Read::read_to_string(&mut kind.stdout.take()?, &mut s).ok()?;
    Some(s)
}

// --- Sonden ------------------------------------------------------------------------

/// Eine Messung. Liefert eine oder mehrere Zeilen; Fehlendes als `nicht_lesbar`.
pub trait Sonde: Send + Sync {
    fn messen(&self, k: &Kontext) -> Vec<Zeile>;
}

/// **Hier eintragen**, wenn eine neue Sonde dazukommt. Reihenfolge = Anzeige.
pub fn sonden() -> Vec<Box<dyn Sonde>> {
    vec![
        Box::new(Cpu::neu()),
        Box::new(Takt),
        Box::new(Temperatur),
        Box::new(Systemlast),
        Box::new(Arbeitsspeicher),
        Box::new(Platte),
        Box::new(Laufzeit),
        Box::new(Dienste { namen: DIENSTE }),
    ]
}

/// Units, deren Zustand angezeigt wird.
pub const DIENSTE: &[&str] = &["chimera", "chimera-tor", "chimera-tor.socket", "chimera-sitzung.socket"];

const TEMP_WARN: f64 = 70.0;
const TEMP_KRIT: f64 = 80.0; // Pi drosselt ab etwa 80 Grad

struct CpuStand {
    zeit: Instant,
    gesamt: Zaehler,
    kerne: Vec<Zaehler>,
    ergebnis: Vec<Zeile>,
}

/// CPU-Auslastung in % (gesamt und je Kern). Braucht zwei Staende; der erste
/// Aufruf misst selbst kurz nach. Aufrufe in kurzem Abstand teilen sich das
/// letzte Ergebnis, damit mehrere Browser die Messung nicht verrauschen.
pub struct Cpu {
    stand: Mutex<Option<CpuStand>>,
}

const CPU_MIN_ABSTAND: Duration = Duration::from_secs(1);
const CPU_ERSTMESSUNG: Duration = Duration::from_millis(250);

impl Cpu {
    pub fn neu() -> Cpu {
        Cpu { stand: Mutex::new(None) }
    }

    fn lesen_stat(k: &Kontext) -> Option<(Zaehler, Vec<Zaehler>)> {
        cpu_zaehler(&k.lesen("proc/stat")?)
    }

    fn zeilen(vorher: &(Zaehler, Vec<Zaehler>), jetzt: &(Zaehler, Vec<Zaehler>)) -> Vec<Zeile> {
        let Some(p) = cpu_prozent(vorher.0, jetzt.0) else {
            return vec![Zeile::nicht_lesbar("cpu", "Prozessor", "CPU-Auslastung")];
        };
        let kerne: Vec<String> = vorher
            .1
            .iter()
            .zip(&jetzt.1)
            .map(|(a, b)| cpu_prozent(*a, *b).map(|x| format!("{x:.0}")).unwrap_or_else(|| "?".into()))
            .collect();
        vec![Zeile {
            id: "cpu".into(),
            gruppe: "Prozessor",
            titel: "CPU-Auslastung".into(),
            text: if kerne.is_empty() { format!("{p:.0} %") } else { format!("{p:.0} %  (Kerne: {} %)", kerne.join(" / ")) },
            wert: Some((p * 10.0).round() / 10.0),
            einheit: "%",
            anteil: Some(p),
            stufe: stufe_aus_anteil(p, 80.0, 95.0),
        }]
    }
}

impl Sonde for Cpu {
    fn messen(&self, k: &Kontext) -> Vec<Zeile> {
        let mut g = self.stand.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(s) = g.as_ref() {
            if s.zeit.elapsed() < CPU_MIN_ABSTAND {
                return s.ergebnis.clone();
            }
        }
        let Some(jetzt) = Self::lesen_stat(k) else {
            return vec![Zeile::nicht_lesbar("cpu", "Prozessor", "CPU-Auslastung")];
        };
        let vorher = match g.as_ref() {
            Some(s) => (s.gesamt, s.kerne.clone()),
            None => {
                // Erster Aufruf: kurz warten und neu lesen.
                std::thread::sleep(CPU_ERSTMESSUNG);
                let z = match Self::lesen_stat(k) {
                    Some(z) => z,
                    None => return vec![Zeile::nicht_lesbar("cpu", "Prozessor", "CPU-Auslastung")],
                };
                let ergebnis = Self::zeilen(&jetzt, &z);
                *g = Some(CpuStand { zeit: Instant::now(), gesamt: z.0, kerne: z.1, ergebnis: ergebnis.clone() });
                return ergebnis;
            }
        };
        let ergebnis = Self::zeilen(&vorher, &jetzt);
        *g = Some(CpuStand { zeit: Instant::now(), gesamt: jetzt.0, kerne: jetzt.1, ergebnis: ergebnis.clone() });
        ergebnis
    }
}

/// Aktueller Takt gegen den Hoechsttakt.
pub struct Takt;
impl Sonde for Takt {
    fn messen(&self, k: &Kontext) -> Vec<Zeile> {
        let cur = k.lesen("sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq").and_then(|t| takt_mhz(&t));
        let max = k.lesen("sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq").and_then(|t| takt_mhz(&t));
        match (cur, max) {
            (Some(c), Some(m)) => vec![Zeile {
                id: "takt".into(),
                gruppe: "Prozessor",
                titel: "Takt".into(),
                text: format!("{c} MHz von {m} MHz"),
                wert: Some(c as f64),
                einheit: "MHz",
                anteil: Some((c as f64 / m as f64 * 100.0).min(100.0)),
                stufe: Stufe::Ok,
            }],
            (Some(c), None) => vec![Zeile {
                id: "takt".into(),
                gruppe: "Prozessor",
                titel: "Takt".into(),
                text: format!("{c} MHz"),
                wert: Some(c as f64),
                einheit: "MHz",
                anteil: None,
                stufe: Stufe::Ok,
            }],
            _ => vec![Zeile::nicht_lesbar("takt", "Prozessor", "Takt")],
        }
    }
}

pub struct Temperatur;
impl Sonde for Temperatur {
    fn messen(&self, k: &Kontext) -> Vec<Zeile> {
        match k.lesen("sys/class/thermal/thermal_zone0/temp").and_then(|t| temperatur_c(&t)) {
            Some(t) => vec![Zeile {
                id: "temperatur".into(),
                gruppe: "Prozessor",
                titel: "Temperatur".into(),
                text: format!("{t:.1} °C"),
                wert: Some(t),
                einheit: "°C",
                anteil: Some((t / 85.0 * 100.0).clamp(0.0, 100.0)),
                stufe: if t >= TEMP_KRIT { Stufe::Kritisch } else if t >= TEMP_WARN { Stufe::Warnung } else { Stufe::Ok },
            }],
            None => vec![Zeile::nicht_lesbar("temperatur", "Prozessor", "Temperatur")],
        }
    }
}

pub struct Arbeitsspeicher;
impl Sonde for Arbeitsspeicher {
    fn messen(&self, k: &Kontext) -> Vec<Zeile> {
        match k.lesen("proc/meminfo").and_then(|t| speicher_mib(&t)) {
            Some((gesamt, frei)) => {
                let belegt = gesamt - frei;
                let p = belegt as f64 / gesamt as f64 * 100.0;
                vec![Zeile {
                    id: "speicher".into(),
                    gruppe: "Speicher",
                    titel: "Arbeitsspeicher".into(),
                    text: format!("{} von {} belegt ({p:.0} %)", fmt_mib(belegt), fmt_mib(gesamt)),
                    wert: Some(belegt as f64),
                    einheit: "MiB",
                    anteil: Some(p),
                    stufe: stufe_aus_anteil(p, 85.0, 95.0),
                }]
            }
            None => vec![Zeile::nicht_lesbar("speicher", "Speicher", "Arbeitsspeicher")],
        }
    }
}

pub struct Platte;
impl Sonde for Platte {
    fn messen(&self, k: &Kontext) -> Vec<Zeile> {
        let r = if k.mit_befehlen { befehl("df", &["-Pk", "/"], Duration::from_secs(2)).and_then(|t| platte_mib(&t)) } else { None };
        match r {
            Some((gesamt, belegt)) => {
                let p = belegt as f64 / gesamt as f64 * 100.0;
                vec![Zeile {
                    id: "platte".into(),
                    gruppe: "Speicher",
                    titel: "Platte".into(),
                    text: format!("{} von {} belegt ({p:.0} %)", fmt_mib(belegt), fmt_mib(gesamt)),
                    wert: Some(belegt as f64),
                    einheit: "MiB",
                    anteil: Some(p),
                    stufe: stufe_aus_anteil(p, 85.0, 95.0),
                }]
            }
            None => vec![Zeile::nicht_lesbar("platte", "Speicher", "Platte")],
        }
    }
}

/// Last (1/5/15 min); der Balken zeigt Last je Kern, 100 % = alle Kerne ausgelastet.
pub struct Systemlast;
impl Sonde for Systemlast {
    fn messen(&self, k: &Kontext) -> Vec<Zeile> {
        let l = k.lesen("proc/loadavg").and_then(|t| last(&t));
        let kerne = k.lesen("proc/stat").and_then(|t| cpu_zaehler(&t)).map(|(_, k)| k.len()).filter(|n| *n > 0);
        match l {
            Some(l) => {
                let anteil = kerne.map(|n| (l[0] / n as f64 * 100.0).clamp(0.0, 100.0));
                vec![Zeile {
                    id: "last".into(),
                    gruppe: "Prozessor",
                    titel: "Last (1/5/15 min)".into(),
                    text: format!("{:.2} / {:.2} / {:.2}", l[0], l[1], l[2]),
                    wert: Some(l[0]),
                    einheit: "",
                    anteil,
                    stufe: anteil.map(|a| stufe_aus_anteil(a, 90.0, 150.0)).unwrap_or(Stufe::Ok),
                }]
            }
            None => vec![Zeile::nicht_lesbar("last", "Prozessor", "Last (1/5/15 min)")],
        }
    }
}

pub struct Laufzeit;
impl Sonde for Laufzeit {
    fn messen(&self, k: &Kontext) -> Vec<Zeile> {
        match k.lesen("proc/uptime").and_then(|t| laufzeit_s(&t)) {
            Some(s) => vec![Zeile {
                id: "laufzeit".into(),
                gruppe: "System",
                titel: "Laufzeit".into(),
                text: fmt_dauer(s),
                wert: Some(s as f64),
                einheit: "s",
                anteil: None,
                stufe: Stufe::Ok,
            }],
            None => vec![Zeile::nicht_lesbar("laufzeit", "System", "Laufzeit")],
        }
    }
}

/// Stufe eines Dienstzustands (Ausgabe von `dienstzustand`).
pub fn dienststufe(zustand: &str) -> Stufe {
    match zustand {
        "aktiv" => Stufe::Ok,
        "startet" | "stoppt" => Stufe::Warnung,
        "unbekannt" => Stufe::Unbekannt,
        _ => Stufe::Kritisch,
    }
}

pub struct Dienste {
    pub namen: &'static [&'static str],
}
impl Sonde for Dienste {
    fn messen(&self, k: &Kontext) -> Vec<Zeile> {
        self.namen
            .iter()
            .map(|d| {
                let z = if k.mit_befehlen {
                    befehl("systemctl", &["is-active", d], Duration::from_secs(2)).map(|t| dienstzustand(&t)).unwrap_or("unbekannt")
                } else {
                    "unbekannt"
                };
                Zeile {
                    id: format!("dienst-{d}"),
                    gruppe: "Dienste",
                    titel: (*d).into(),
                    text: z.into(),
                    wert: None,
                    einheit: "",
                    anteil: None,
                    stufe: dienststufe(z),
                }
            })
            .collect()
    }
}

/// Alle Sonden fragen. Die Liste lebt fuer die Laufzeit des Gateways, damit
/// zustandsbehaftete Sonden (CPU) ihren letzten Stand behalten.
pub fn messen(k: &Kontext) -> Value {
    static LISTE: OnceLock<Vec<Box<dyn Sonde>>> = OnceLock::new();
    let liste = LISTE.get_or_init(sonden);
    messen_mit(liste, k)
}

pub fn messen_mit(liste: &[Box<dyn Sonde>], k: &Kontext) -> Value {
    let zeilen: Vec<Value> = liste.iter().flat_map(|s| s.messen(k)).map(|z| z.json()).collect();
    json!({"ok": true, "zeilen": zeilen})
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ctx<'a>(w: &'a Path) -> Kontext<'a> {
        Kontext { wurzel: w, mit_befehlen: false }
    }

    fn tmp(n: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("chimera-status-{}-{n}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(d.join("proc")).unwrap();
        d
    }

    #[test]
    fn temperatur_wird_gelesen_und_unsinn_verworfen() {
        assert_eq!(temperatur_c("40780\n"), Some(40.78));
        assert_eq!(temperatur_c(""), None);
        assert_eq!(temperatur_c("abc"), None);
        assert_eq!(temperatur_c("999999999"), None);
        assert_eq!(temperatur_c("-90000"), None);
    }

    #[test]
    fn speicher_braucht_beide_felder_und_ist_stimmig() {
        let t = "MemTotal:         473792 kB\nMemFree:           73164 kB\nMemAvailable:     349384 kB\n";
        assert_eq!(speicher_mib(t), Some((462, 341)));
        assert_eq!(speicher_mib("MemTotal: 100 kB\n"), None);
        assert_eq!(speicher_mib("MemTotal: 100 kB\nMemAvailable: 200 kB\n"), None);
        assert_eq!(speicher_mib("MemTotal: 0 kB\nMemAvailable: 0 kB\n"), None);
    }

    #[test]
    fn last_und_laufzeit() {
        assert_eq!(last("0.66 0.64 0.58 1/132 285847\n"), Some([0.66, 0.64, 0.58]));
        assert_eq!(last("0.66 0.64"), None);
        assert_eq!(laufzeit_s("1689045.67 6182591.27\n"), Some(1689045));
        assert_eq!(laufzeit_s(""), None);
        assert_eq!(laufzeit_s("-5 1"), None);
    }

    #[test]
    fn platte_nimmt_die_letzte_zeile() {
        let t = "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/root 122594184 18654968 98912036 16% /\n";
        assert_eq!(platte_mib(t), Some((119720, 18217)));
        assert_eq!(platte_mib("nur kopf"), None);
        assert_eq!(platte_mib("/dev/x 10 20 0 100% /"), None);
    }

    #[test]
    fn dienstzustand_kennt_nur_bekanntes() {
        assert_eq!(dienstzustand("active\n"), "aktiv");
        assert_eq!(dienstzustand("failed"), "gescheitert");
        assert_eq!(dienstzustand(""), "unbekannt");
        assert_eq!(dienstzustand("Failed to connect to bus"), "unbekannt");
    }

    const STAT1: &str = "cpu  100 0 100 800 0 0 0 0 0 0\ncpu0 50 0 50 400 0 0 0 0 0 0\ncpu1 50 0 50 400 0 0 0 0 0 0\nintr 1\n";
    const STAT2: &str = "cpu  200 0 200 1000 0 0 0 0 0 0\ncpu0 150 0 150 400 0 0 0 0 0 0\ncpu1 50 0 50 600 0 0 0 0 0 0\nintr 2\n";

    #[test]
    fn cpu_zaehler_liest_gesamt_und_kerne() {
        let (g, k) = cpu_zaehler(STAT1).unwrap();
        assert_eq!(g, Zaehler { summe: 1000, leer: 800 });
        assert_eq!(k.len(), 2);
        assert_eq!(k[0], Zaehler { summe: 500, leer: 400 });
        assert_eq!(cpu_zaehler("intr 1\n"), None);
        assert_eq!(cpu_zaehler("cpu 1 2\n"), None);
        assert_eq!(cpu_zaehler("cpu a b c d\n"), None);
    }

    #[test]
    fn cpu_prozent_aus_zwei_staenden() {
        let (a, ak) = cpu_zaehler(STAT1).unwrap();
        let (b, bk) = cpu_zaehler(STAT2).unwrap();
        // gesamt: Summe +400, leer +200 -> 50 % belegt
        assert_eq!(cpu_prozent(a, b), Some(50.0));
        // Kern 0: Summe +200, leer +0 -> 100 %; Kern 1: Summe +200, leer +200 -> 0 %
        assert_eq!(cpu_prozent(ak[0], bk[0]), Some(100.0));
        assert_eq!(cpu_prozent(ak[1], bk[1]), Some(0.0));
        // Kein Fortschritt, rueckwaerts, Leerlauf groesser als Summe: nicht lesbar.
        assert_eq!(cpu_prozent(a, a), None);
        assert_eq!(cpu_prozent(b, a), None);
        assert_eq!(cpu_prozent(Zaehler { summe: 10, leer: 0 }, Zaehler { summe: 20, leer: 30 }), None);
    }

    #[test]
    fn takt_in_mhz() {
        assert_eq!(takt_mhz("700000\n"), Some(700));
        assert_eq!(takt_mhz("0"), None);
        assert_eq!(takt_mhz("x"), None);
        assert_eq!(takt_mhz("99999999"), None);
    }

    #[test]
    fn formatierung() {
        assert_eq!(fmt_mib(341), "341 MB");
        assert_eq!(fmt_mib(1024), "1.0 GB");
        assert_eq!(fmt_mib(18217), "17.8 GB");
        assert_eq!(fmt_dauer(1_689_045), "19 d 13 h");
        assert_eq!(fmt_dauer(3 * 3600 + 120), "3 h 2 min");
        assert_eq!(fmt_dauer(59), "0 min");
    }

    #[test]
    fn dienststufe_trennt_ok_warnung_kritisch_unbekannt() {
        assert_eq!(dienststufe("aktiv"), Stufe::Ok);
        assert_eq!(dienststufe("startet"), Stufe::Warnung);
        assert_eq!(dienststufe("stoppt"), Stufe::Warnung);
        assert_eq!(dienststufe("unbekannt"), Stufe::Unbekannt);
        assert_eq!(dienststufe("gescheitert"), Stufe::Kritisch);
        assert_eq!(dienststufe("inaktiv"), Stufe::Kritisch);
        // Ein Dienst ohne Befehl-Antwort darf nie als "ok" erscheinen.
        let d = tmp("dienste");
        let z = &Dienste { namen: &["x"] }.messen(&ctx(&d))[0];
        assert_eq!((z.text.as_str(), z.stufe), ("unbekannt", Stufe::Unbekannt));
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn iowait_zaehlt_als_leerlauf() {
        // user nice system idle iowait: Leerlauf = idle + iowait = 800 + 100
        let (g, _) = cpu_zaehler("cpu  100 0 100 800 100 0 0 0\n").unwrap();
        assert_eq!(g, Zaehler { summe: 1100, leer: 900 });
        // 400 Schritte, davon 100 iowait und 100 idle: nur 200 sind Arbeit -> 50 %
        let (a, _) = cpu_zaehler("cpu  100 0 100 800 100 0 0 0\n").unwrap();
        let (b, _) = cpu_zaehler("cpu  200 0 200 900 200 0 0 0\n").unwrap();
        assert_eq!(cpu_prozent(a, b), Some(50.0));
    }

    #[test]
    fn last_je_kern_ist_nicht_die_rohe_last() {
        let d = tmp("lastkern");
        std::fs::write(d.join("proc/stat"), STAT1).unwrap(); // zwei Kerne
        std::fs::write(d.join("proc/loadavg"), "1.00 1.00 1.00 1/2 3\n").unwrap();
        // Last 1.0 auf 2 Kernen = 50 %, nicht 100 %
        assert_eq!(Systemlast.messen(&ctx(&d))[0].anteil, Some(50.0));
        std::fs::write(d.join("proc/loadavg"), "0.20 1.00 1.00 1/2 3\n").unwrap();
        assert_eq!(Systemlast.messen(&ctx(&d))[0].anteil, Some(10.0));
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn stufen_schwellen() {
        assert_eq!(stufe_aus_anteil(79.9, 80.0, 95.0), Stufe::Ok);
        assert_eq!(stufe_aus_anteil(80.0, 80.0, 95.0), Stufe::Warnung);
        assert_eq!(stufe_aus_anteil(95.0, 80.0, 95.0), Stufe::Kritisch);
    }

    #[test]
    fn eine_sonde_ohne_quelle_liefert_nicht_lesbar_statt_null() {
        let d = tmp("leer");
        for z in Arbeitsspeicher.messen(&ctx(&d)).into_iter().chain(Temperatur.messen(&ctx(&d))).chain(Laufzeit.messen(&ctx(&d))) {
            assert_eq!(z.text, "nicht lesbar", "{}", z.id);
            assert_eq!(z.wert, None);
            assert_eq!(z.stufe, Stufe::Unbekannt);
        }
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn sonden_lesen_aus_nachgebauter_wurzel() {
        let d = tmp("voll");
        std::fs::create_dir_all(d.join("sys/class/thermal/thermal_zone0")).unwrap();
        std::fs::create_dir_all(d.join("sys/devices/system/cpu/cpu0/cpufreq")).unwrap();
        std::fs::write(d.join("sys/class/thermal/thermal_zone0/temp"), "82000\n").unwrap();
        std::fs::write(d.join("sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"), "600000\n").unwrap();
        std::fs::write(d.join("sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"), "1000000\n").unwrap();
        std::fs::write(d.join("proc/meminfo"), "MemTotal: 1048576 kB\nMemAvailable: 262144 kB\n").unwrap();
        std::fs::write(d.join("proc/loadavg"), "2.00 1.00 0.50 1/2 3\n").unwrap();
        std::fs::write(d.join("proc/stat"), STAT1).unwrap();
        let t = &Temperatur.messen(&ctx(&d))[0];
        assert_eq!((t.text.as_str(), t.stufe), ("82.0 °C", Stufe::Kritisch));
        let tk = &Takt.messen(&ctx(&d))[0];
        assert_eq!((tk.text.as_str(), tk.anteil), ("600 MHz von 1000 MHz", Some(60.0)));
        let m = &Arbeitsspeicher.messen(&ctx(&d))[0];
        assert_eq!(m.text, "768 MB von 1.0 GB belegt (75 %)");
        let l = &Systemlast.messen(&ctx(&d))[0];
        // Last 2.0 auf 2 Kernen = 100 %
        assert_eq!((l.anteil, l.text.as_str()), (Some(100.0), "2.00 / 1.00 / 0.50"));
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn cpu_sonde_misst_zwischen_zwei_aufrufen_und_teilt_kurze_abstaende() {
        let d = tmp("cpu");
        std::fs::write(d.join("proc/stat"), STAT1).unwrap();
        let s = Cpu::neu();
        // Erster Aufruf: liest zweimal (mit Wartezeit) -> gleicher Stand -> nicht lesbar, kein Absturz.
        let erste = s.messen(&ctx(&d));
        assert_eq!(erste[0].stufe, Stufe::Unbekannt);
        // Innerhalb des Mindestabstands kommt dasselbe Ergebnis, auch wenn die Datei sich aendert.
        std::fs::write(d.join("proc/stat"), STAT2).unwrap();
        assert_eq!(s.messen(&ctx(&d)), erste);
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn cpu_zeilen_zeigen_gesamt_und_kerne() {
        let a = cpu_zaehler(STAT1).unwrap();
        let b = cpu_zaehler(STAT2).unwrap();
        let z = &Cpu::zeilen(&a, &b)[0];
        assert_eq!(z.text, "50 %  (Kerne: 100 / 0 %)");
        assert_eq!(z.wert, Some(50.0));
        assert_eq!(z.stufe, Stufe::Ok);
    }

    #[test]
    fn die_liste_ist_stimmig_ids_eindeutig_titel_nicht_leer() {
        let d = tmp("liste");
        let liste = sonden();
        assert!(!liste.is_empty());
        let mut ids = Vec::new();
        for s in &liste {
            for z in s.messen(&ctx(&d)) {
                assert!(!z.titel.is_empty() && !z.gruppe.is_empty() && !z.id.is_empty(), "{z:?}");
                assert!(!ids.contains(&z.id), "doppelte Zeilen-ID {}", z.id);
                ids.push(z.id);
            }
        }
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn gleiche_gruppen_stehen_beieinander() {
        // Eine Gruppe, die in der Liste zweimal auftaucht, wuerde in der Anzeige zwei Ueberschriften bekommen.
        let d = tmp("gruppen");
        let mut gesehen: Vec<&str> = Vec::new();
        let mut letzte = "";
        for s in &sonden() {
            for z in s.messen(&ctx(&d)) {
                if z.gruppe != letzte {
                    assert!(!gesehen.contains(&z.gruppe), "Gruppe {} ist zerrissen", z.gruppe);
                    gesehen.push(z.gruppe);
                    letzte = z.gruppe;
                }
            }
        }
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn eine_neue_sonde_laesst_sich_ohne_aenderung_am_weg_einhaengen() {
        struct Eigene;
        impl Sonde for Eigene {
            fn messen(&self, _: &Kontext) -> Vec<Zeile> {
                vec![Zeile { id: "x".into(), gruppe: "Test", titel: "X".into(), text: "42".into(), wert: Some(42.0), einheit: "", anteil: None, stufe: Stufe::Ok }]
            }
        }
        let d = tmp("eigene");
        let liste: Vec<Box<dyn Sonde>> = vec![Box::new(Eigene)];
        let v = messen_mit(&liste, &ctx(&d));
        assert_eq!(v["zeilen"][0]["text"], "42");
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn echtes_system_liefert_zeilen_und_stuerzt_nicht() {
        // Nicht jede Umgebung erlaubt jede Datei (die Sandbox sperrt /proc/loadavg).
        let v = messen(&Kontext { wurzel: Path::new("/"), mit_befehlen: false });
        assert!(v["zeilen"].as_array().unwrap().len() >= DIENSTE.len());
        assert!(v["zeilen"].as_array().unwrap().iter().any(|z| z["id"] == "speicher" && z["wert"].is_number()));
    }
}
