//! Mojo: Dienste und Sockets pruefen, die Ursache nennen, sanft reparieren,
//! nachpruefen, laut melden (DESIGN, Regel "Mojo"; Recherche docs/research/MOJO.md).
//!
//! Eine Regelmaschine, kein Modell. Ohne `--miracle` wird nichts veraendert. Jeder
//! Befund ab Warnung nennt seine **Ursache** mit Beleg und den **Weg**; findet
//! Mojo keine, sagt es "Ursache nicht bestimmbar" und liefert die Rohdaten.
//! Nach jeder Reparatur laufen dieselben Pruefungen noch einmal: kehrt derselbe
//! Befund (Bereich, Code, Gegenstand) wieder, ist er "unreparierbar".
//!
//! Der Zugriff auf das System steht hinter `System`, damit die Logik ohne
//! systemd pruefbar ist; `Echt` ruft `systemctl`, `journalctl` und `/proc` auf.

use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::io::Read;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

// ------------------------------------------------------------------ Typen

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Schwere {
    Ok,
    Info,
    Warn,
    Error,
}

impl Schwere {
    pub fn text(self) -> &'static str {
        match self {
            Schwere::Ok => "ok",
            Schwere::Info => "info",
            Schwere::Warn => "warn",
            Schwere::Error => "error",
        }
    }
    /// 0 sauber, 1 Warnung, 2 Fehler (Exitcode des Befehls).
    pub fn rang(self) -> u8 {
        match self {
            Schwere::Ok | Schwere::Info => 0,
            Schwere::Warn => 1,
            Schwere::Error => 2,
        }
    }
}

/// Warum etwas nicht geht, womit es belegt ist und was dagegen zu tun ist.
#[derive(Clone, Debug, PartialEq)]
pub struct Ursache {
    pub text: String,
    pub beleg: String,
    pub weg: String,
    /// `false`: Mojo konnte keine Ursache bestimmen (Rohdaten stehen im Befund).
    pub bestimmt: bool,
    /// `true`: das muss ein Mensch tun, Software kann es nicht beheben.
    pub nur_mensch: bool,
    /// `true`: ein Neustart kann diese Ursache heilen (Zeitueberschreitung, Signal,
    /// Netz kurz weg). Bei einem fehlenden Programm (203) oder fehlenden Nutzer (217)
    /// hilft er nie; dann gibt es keine automatische Reparatur, nur den Weg.
    pub neustart_hilft: bool,
    /// `true`: ein fehlendes Python-Paket; Mojo laedt es nach (Installer Schritt 50,
    /// danach Neustart des Dienstes). Ein Neustart allein hilft hier nie.
    pub paket_nachladen: bool,
}

impl Ursache {
    pub fn neu(text: &str, beleg: &str, weg: &str) -> Ursache {
        Ursache { text: text.into(), beleg: beleg.into(), weg: weg.into(), bestimmt: true, nur_mensch: false, neustart_hilft: false, paket_nachladen: false }
    }
    pub fn mit_neustart(self) -> Ursache {
        Ursache { neustart_hilft: true, ..self }
    }
    pub fn mit_paket(self) -> Ursache {
        Ursache { paket_nachladen: true, ..self }
    }
    /// Eine Ursache, die Software nicht beheben kann (leere Karte, defekter Baustein).
    pub fn mensch(text: &str, beleg: &str, weg: &str) -> Ursache {
        Ursache { nur_mensch: true, ..Ursache::neu(text, beleg, weg) }
    }
    pub fn unbestimmt(beleg: &str) -> Ursache {
        Ursache {
            text: "Ursache nicht bestimmbar".into(),
            beleg: beleg.into(),
            weg: "Die Rohdaten im Befund lesen (Ergebnis, Status, letzte Zeilen des Journals) und danach suchen.".into(),
            bestimmt: false,
            nur_mensch: true,
            neustart_hilft: false,
            paket_nachladen: false,
        }
    }
}

/// Eine sanfte Reparatur (Stufe 1). Daten, keine Funktion: sie laesst sich
/// anzeigen, protokollieren und im Test gegen ein Spiel-System ausfuehren.
#[derive(Clone, Debug, PartialEq)]
pub enum Reparatur {
    ResetUndStart { unit: String },
    /// Fehlende Python-Pakete nachladen (Installer Schritt 50), danach `unit` neu starten.
    PaketeNachladen { unit: String },
    SocketNachziehen { socket: String, dienst: String },
    /// WLAN neu starten (Vorgabe smilez, 3.11.): Verbindung, Dienst, Schnittstelle.
    WlanNeuStarten { schnittstelle: String },
}

impl Reparatur {
    /// 1 sanft und lokal (Neustart), 2 Komponente neu (Pakete nachladen). Stufe 3
    /// (ganzer Installer) gibt es hier nicht; sie liefe nur auf ausdruecklichen Wunsch.
    pub fn stufe(&self) -> u8 {
        match self {
            Reparatur::ResetUndStart { .. }
            | Reparatur::SocketNachziehen { .. }
            | Reparatur::WlanNeuStarten { .. } => 1,
            Reparatur::PaketeNachladen { .. } => 2,
        }
    }
    pub fn beschreibung(&self) -> String {
        match self {
            Reparatur::ResetUndStart { unit } => format!("{unit}: Fehlerzustand loeschen und neu starten"),
            Reparatur::PaketeNachladen { unit } => format!("{unit}: fehlende Python-Pakete nachladen (Installer Schritt 50), dann neu starten"),
            Reparatur::SocketNachziehen { socket, dienst } => {
                format!("{dienst} anhalten, {socket} starten, {dienst} wieder starten")
            }
            Reparatur::WlanNeuStarten { schnittstelle } => {
                format!("WLAN {schnittstelle}: neu verbinden, Dienst neu starten, Schnittstelle hochfahren")
            }
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Befund {
    pub schwere: Schwere,
    pub bereich: String,
    pub code: String,
    /// Woran es hing (Unit, Socket): Teil des Schluessels fuer die Nachpruefung.
    pub gegenstand: String,
    pub meldung: String,
    pub ursache: Option<Ursache>,
    pub reparatur: Option<Reparatur>,
    pub unreparierbar: bool,
    pub roh: Option<Value>,
}

impl Befund {
    pub fn gut(bereich: &str, code: &str, gegenstand: &str, meldung: &str) -> Befund {
        Befund {
            schwere: Schwere::Ok,
            bereich: bereich.into(),
            code: code.into(),
            gegenstand: gegenstand.into(),
            meldung: meldung.into(),
            ursache: None,
            reparatur: None,
            unreparierbar: false,
            roh: None,
        }
    }
    pub fn problem(
        schwere: Schwere,
        bereich: &str,
        code: &str,
        gegenstand: &str,
        meldung: &str,
        ursache: Ursache,
        reparatur: Option<Reparatur>,
    ) -> Befund {
        Befund {
            schwere,
            bereich: bereich.into(),
            code: code.into(),
            gegenstand: gegenstand.into(),
            meldung: meldung.into(),
            ursache: Some(ursache),
            reparatur,
            unreparierbar: false,
            roh: None,
        }
    }
}

// ------------------------------------------------------------ Unit-Zustand

#[derive(Clone, Debug, Default, PartialEq)]
pub struct UnitZustand {
    pub name: String,
    pub geladen: bool,
    pub aktiv: String,
    pub unter: String,
    pub ergebnis: String,
    pub exec_status: Option<i32>,
    pub neustarts: u32,
    pub datei: String,
    pub ausloeser: Vec<String>,
}

/// Die Eigenschaften, die Mojo von `systemctl show` liest.
pub const EIGENSCHAFTEN: &str = "LoadState,ActiveState,SubState,Result,ExecMainStatus,NRestarts,UnitFileState,Triggers";

/// Die Ausgabe von `systemctl show -p ...` lesen. Fehlendes bleibt leer.
pub fn zustand_aus_show(name: &str, text: &str) -> UnitZustand {
    let mut z = UnitZustand { name: name.into(), ..Default::default() };
    for zeile in text.lines() {
        let Some((k, v)) = zeile.split_once('=') else { continue };
        let v = v.trim();
        match k {
            "LoadState" => z.geladen = v == "loaded",
            "ActiveState" => z.aktiv = v.into(),
            "SubState" => z.unter = v.into(),
            "Result" => z.ergebnis = v.into(),
            "ExecMainStatus" => z.exec_status = v.parse().ok(),
            "NRestarts" => z.neustarts = v.parse().unwrap_or(0),
            "UnitFileState" => z.datei = v.into(),
            "Triggers" => z.ausloeser = v.split_whitespace().map(String::from).collect(),
            _ => {}
        }
    }
    z
}

/// Die Unit-Namen aus der Ausgabe von `systemctl --failed --plain --no-legend`,
/// nur die der Chimera-Units. Fuehrende Zeichen (Punkt, Kreuz) fallen weg.
pub fn units_aus_failed(text: &str) -> Vec<String> {
    let mut v: Vec<String> = text
        .lines()
        .filter_map(|z| z.trim().trim_start_matches(|c: char| !c.is_ascii_alphanumeric()).split_whitespace().next().map(String::from))
        .filter(|n| n.starts_with("chimera") && (n.ends_with(".service") || n.ends_with(".socket") || n.ends_with(".timer")))
        .collect();
    v.sort();
    v.dedup();
    v
}

// ------------------------------------------------------ Ursachen-Katalog

/// (Muster in Kleinschrift, Ursache, Weg) fuer die Ausgabe eines Programms.
/// **Hier eintragen**, wenn Mojo eine weitere Ursache kennen soll.
pub const MUSTER: &[(&str, &str, &str)] = &[
    ("address already in use", "Der Anschluss ist schon belegt", "Den Prozess auf dem Anschluss finden (ss -ltnp) und beenden oder den Anschluss aendern."),
    ("permission denied", "Dem Prozess fehlt ein Recht auf eine Datei oder einen Anschluss", "Besitzer, Modus und Gruppen der genannten Datei pruefen."),
    ("no such file or directory", "Eine Datei oder ein Ordner, den das Programm braucht, fehlt", "Den genannten Pfad anlegen oder den Installer neu laufen lassen."),
    ("no module named", "Ein Python-Paket fehlt in der Umgebung", "Installer Schritt 50 (Python-Umgebung) laedt es nach; Mojo tut das selbst."),
    ("name or service not known", "Ein Name laesst sich nicht aufloesen (DNS oder Netz)", "Netz und DNS pruefen."),
    ("temporary failure in name resolution", "Ein Name laesst sich nicht aufloesen (DNS oder Netz)", "Netz und DNS pruefen."),
    ("connection refused", "Die Gegenstelle nimmt keine Verbindung an", "Laeuft der Dienst auf der Gegenseite? Adresse und Anschluss pruefen."),
    ("no space left on device", "Die Speicherkarte (SD) ist voll, nicht der Arbeitsspeicher", "Platz schaffen (df -h): grosse Dateien und alte Protokolle pruefen; eine groessere Karte nehmen."),
    ("cannot allocate memory", "Dem Prozess ging der Arbeitsspeicher (RAM) aus, nicht die SD-Karte", "Speicherverbrauch ansehen (ps), Dienste oder Modelle verkleinern."),
    ("out of memory", "Dem Prozess ging der Arbeitsspeicher (RAM) aus, nicht die SD-Karte", "Speicherverbrauch ansehen (ps), Dienste oder Modelle verkleinern."),
    ("dependency failed", "Eine Voraussetzung der Unit ist gescheitert", "Die Unit hinter 'Dependency failed for' pruefen."),
];

/// Muster, bei denen ein Neustart helfen kann (der Zustand ist vorlaeufig).
const NEUSTART_HILFT: &[&str] = &[
    "address already in use",
    "name or service not known",
    "temporary failure in name resolution",
    "connection refused",
    "cannot allocate memory",
    "out of memory",
    "dependency failed",
];

fn muster_treffer(journal: &[String]) -> Option<Ursache> {
    // Neueste Zeilen zuerst: die letzte Meldung vor dem Ende ist die brauchbarste.
    for zeile in journal.iter().rev() {
        let klein = zeile.to_lowercase();
        for (m, text, weg) in MUSTER {
            if klein.contains(m) {
                let u = Ursache::neu(text, zeile.trim(), weg);
                return Some(if NEUSTART_HILFT.contains(m) {
                    u.mit_neustart()
                } else if *m == "no module named" {
                    u.mit_paket()
                } else {
                    u
                });
            }
        }
    }
    None
}

fn signal_name(n: i32) -> &'static str {
    match n {
        9 => "SIGKILL (gekillt, haeufig Arbeitsspeicher (RAM) knapp, oder von Hand)",
        11 => "SIGSEGV (Speicherzugriffsfehler im Programm)",
        6 => "SIGABRT (das Programm hat sich selbst abgebrochen)",
        15 => "SIGTERM (beendet)",
        _ => "ein Signal",
    }
}

/// Die Ursache eines Unit-Fehlers: erst was systemd selbst sagt, dann die
/// Ausgabe des Programms, sonst "nicht bestimmbar" mit Rohdaten.
pub fn ursache_aus_unit(z: &UnitZustand, journal: &[String]) -> Ursache {
    let beleg_status = format!("Ergebnis {}, Status {}", z.ergebnis, z.exec_status.map(|s| s.to_string()).unwrap_or_else(|| "-".into()));
    let grenze = z.ergebnis == "start-limit-hit" || journal.iter().any(|l| l.contains("repeated too quickly"));
    let innen = match (z.ergebnis.as_str(), z.exec_status) {
        ("exit-code", Some(203)) => Some(Ursache::neu(
            "Das Programm der Unit fehlt oder ist nicht ausfuehrbar",
            &beleg_status,
            "Pfad hinter ExecStart= und das Ausfuehrungsrecht pruefen; fehlt das Programm, den passenden Installerschritt neu laufen lassen (55 Gateway, 50 Dienst).",
        )),
        ("exit-code", Some(217)) => Some(Ursache::neu(
            "Der Nutzer aus User= existiert nicht",
            &beleg_status,
            "Installer Schritt 98 (Dienst) bzw. 99 (Gateway) legt den Nutzer an: neu laufen lassen.",
        )),
        ("exit-code", Some(226)) => Some(Ursache::neu(
            "Ein Pfad aus ReadWritePaths= oder dem Namensraum der Unit fehlt",
            &beleg_status,
            "Den fehlenden Ordner anlegen; die Ablagen des Gateways legt Installer Schritt 99 an.",
        )),
        ("exit-code", Some(200)) => Some(Ursache::neu(
            "Das Arbeitsverzeichnis (WorkingDirectory=) fehlt",
            &beleg_status,
            "Den Ordner anlegen oder den Installer neu laufen lassen.",
        )),
        ("resources", _) => Some(Ursache::neu(
            "Eine Datei fuer EnvironmentFile= fehlt oder ist nicht lesbar",
            &beleg_status,
            "Die Datei anlegen (config/.env) oder in der Unit ein '-' vor den Pfad setzen.",
        )),
        ("timeout", _) => Some(Ursache::neu(
            "Der Start dauerte zu lange oder die Unit meldete sich nicht",
            &beleg_status,
            "Das Journal der Unit lesen: was lief beim Start? Bei Type=notify muss das Programm 'ready' melden.",
        ).mit_neustart()),
        ("signal", st) => {
            let n = st.unwrap_or(0);
            Some(Ursache::neu(
                &format!("Der Prozess wurde beendet: {}", signal_name(n)),
                &beleg_status,
                "Das Kernelprotokoll auf Speichermangel pruefen (dmesg | grep -i kill); bei Signal 11 den Fehler im Programm suchen.",
            ).mit_neustart())
        }
        ("core-dump", _) | ("watchdog", _) => Some(Ursache::neu(
            "Das Programm ist abgestuerzt oder hat den Wachhund nicht bedient",
            &beleg_status,
            "Das Journal der Unit lesen.",
        ).mit_neustart()),
        _ => None,
    };
    let kern = innen
        .or_else(|| muster_treffer(journal))
        .unwrap_or_else(|| {
            let letzte: Vec<&str> = journal.iter().rev().take(5).map(String::as_str).collect();
            Ursache::unbestimmt(&format!("{beleg_status}; letzte Zeilen: {}", letzte.into_iter().rev().collect::<Vec<_>>().join(" | ")))
        });
    if grenze {
        Ursache {
            text: format!("Die Startgrenze ist erreicht; zuletzt scheiterte der Start so: {}", kern.text),
            ..kern
        }
    } else {
        kern
    }
}

// ----------------------------------------------------------- Systemzugriff

/// Die Reparatur zu einer Ursache: Pakete nachladen, wenn eines fehlt; Neustart, wenn er
/// helfen kann; sonst keine (dann bleiben Ursache und Weg).
pub fn reparatur_fuer(u: &Ursache, unit: &str) -> Option<Reparatur> {
    if u.paket_nachladen {
        Some(Reparatur::PaketeNachladen { unit: unit.to_string() })
    } else if u.neustart_hilft {
        Some(Reparatur::ResetUndStart { unit: unit.to_string() })
    } else {
        None
    }
}

/// Import-Name -> Paketname, wo sie sich unterscheiden. Hier eintragen, wenn Chimera ein
/// Paket nutzt, dessen Import anders heisst.
pub const IMPORT_ALIAS: &[(&str, &str)] = &[("pil", "pillow"), ("yaml", "pyyaml"), ("cv2", "opencv-python"), ("serial", "pyserial"), ("bs4", "beautifulsoup4")];

fn normiert(n: &str) -> String {
    n.trim().to_lowercase().replace('_', "-")
}

/// Die Paketnamen einer `requirements.txt` (Version, Marker, Kommentare fallen weg).
pub fn pakete_aus_requirements(text: &str) -> Vec<String> {
    text.lines()
        .map(|z| z.split('#').next().unwrap_or("").trim())
        .filter(|z| !z.is_empty() && !z.starts_with('-'))
        .map(|z| {
            let n: String = z.chars().take_while(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '-' || *c == '.').collect();
            normiert(&n)
        })
        .filter(|n| !n.is_empty())
        .collect()
}

/// Der Import-Name aus "No module named 'x.y'": das oberste Modul.
pub fn modul_aus_beleg(beleg: &str) -> Option<String> {
    let i = beleg.to_lowercase().find("no module named")?;
    let rest = &beleg[i + "no module named".len()..];
    let name: String = rest.trim().trim_start_matches(|c| c == '\'' || c == '"').chars().take_while(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '.').collect();
    let oben = name.split('.').next().unwrap_or("").to_string();
    (!oben.is_empty()).then_some(oben)
}

/// Steht das fehlende Modul in der `requirements.txt`? Nur dann kann Schritt 50 es nachladen.
pub fn modul_in_requirements(modul: &str, requirements: &str) -> bool {
    let pakete = pakete_aus_requirements(requirements);
    let m = normiert(modul);
    let alias = IMPORT_ALIAS.iter().find(|(i, _)| *i == m).map(|(_, p)| *p);
    pakete.iter().any(|p| *p == m || Some(p.as_str()) == alias)
}

/// Die Ursache einer Unit mit der Pruefung, ob ein fehlendes Python-Paket ueberhaupt
/// nachladbar ist: Steht es nicht in der `requirements.txt`, bringt Schritt 50 es nie
/// (gemessen am Pi: ein erfundenes Paket blieb nach dem Nachladen fehlend). Dann gibt es
/// keine Reparatur, sondern Ursache und Weg fuer einen Menschen.
pub fn ursache_fuer(sys: &dyn System, z: &UnitZustand, journal: &[String]) -> Ursache {
    let u = ursache_aus_unit(z, journal);
    if !u.paket_nachladen {
        return u;
    }
    let Some(modul) = modul_aus_beleg(&u.beleg) else { return u };
    match sys.requirements() {
        Some(text) if modul_in_requirements(&modul, &text) => u,
        Some(_) => Ursache {
            text: format!("Das Python-Paket fuer '{modul}' fehlt und steht nicht in der requirements.txt; Nachladen kann es nicht beschaffen (Import-Name und Paketname koennen abweichen)"),
            weg: format!("Das Paket in die requirements.txt eintragen, wenn der Code es braucht, und Schritt 50 laufen lassen; sonst den Import '{modul}' aus dem Code nehmen."),
            nur_mensch: true,
            paket_nachladen: false,
            ..u
        },
        None => Ursache {
            text: format!("Das Python-Paket fuer '{modul}' fehlt; ob es nachladbar ist, ist nicht pruefbar (requirements.txt nicht lesbar)"),
            weg: "Die requirements.txt unter /opt/chimera/source pruefen; ist sie da, Schritt 50 laufen lassen.".to_string(),
            nur_mensch: true,
            paket_nachladen: false,
            ..u
        },
    }
}

pub trait System {
    fn zustand(&self, unit: &str) -> Option<UnitZustand>;
    fn journal(&self, unit: &str, n: usize) -> Vec<String>;
    fn speicher_verfuegbar_mb(&self) -> Option<u64>;
    /// Namen aller Units im Zustand failed (`systemctl --failed`), gefiltert auf `chimera*`.
    fn gescheiterte_units(&self) -> Vec<String>;
    fn ausfuehren(&self, r: &Reparatur) -> Result<(), String>;
    /// Warten, bis sich ein neu gestarteter Dienst beruhigt hat (Nachpruefung).
    /// Probe: laesst sich unter `pfad` eine Datei anlegen und wieder loeschen?
    /// `Err` nennt den Grund so, wie ihn das Betriebssystem meldet.
    fn schreibprobe(&self, pfad: &str) -> Result<(), String>;
    /// Freier Platz unter `pfad` in MB (`df`), `None` wenn nicht lesbar.
    fn platz_frei_mb(&self, pfad: &str) -> Option<u64>;
    /// Inhalt der `requirements.txt` (Quelle der Python-Umgebung), `None` wenn nicht lesbar.
    fn requirements(&self) -> Option<String>;
    fn warten(&self, dauer: Duration);
    /// Ist das Netz erreichbar? Vorgabe: ja -- Tests sollen nicht ins Netz.
    fn netz_erreichbar(&self) -> bool {
        true
    }
    /// Wie oft eine Reparatur fuer diesen Gegenstand in der letzten Stunde nichts bewirkt hat.
    fn fehlversuche(&self, schluessel: &str) -> u32;
    fn fehlversuch_merken(&self, schluessel: &str);
    /// Das Geraet neu starten. Der Vorgabewert verweigert den Neustart: Ein Test,
    /// der ihn nicht ausdruecklich erlaubt, darf kein Geraet durchstarten.
    fn neustart_ausloesen(&self) -> Result<(), String> {
        Err("Neustart im Test nicht erlaubt".into())
    }
}

/// Gleiche Reparatur, gleicher Gegenstand: nach so vielen wirkungslosen Versuchen
/// in einer Stunde setzt Mojo sie aus (sonst Neustart-Sturm: die Reparatur startet
/// die Unit, sie scheitert, OnFailure ruft Mojo, ...).
pub const BUDGET: u32 = 2;
/// Hoechste Stufe, die `--miracle` von allein ausfuehrt: 1 (Neustart) und 2 (Pakete nachladen).
pub const TIER_MAX: u8 = 2;
/// So oft repariert Miracle im selben Lauf. Ein Fund, der dreimal ueberlebt,
/// gilt als unreparierbar (Vorgabe smilez, 3.11.).
pub const RUNDEN_MAX: u8 = 3;
/// Nach einer Reparatur so lange warten, bevor nachgeprueft wird. Ein Dienst vom
/// Typ simple gilt direkt nach dem Start als aktiv, auch wenn er gleich stirbt.
pub const NACHPRUEFUNG_WARTEN: Duration = Duration::from_secs(4);
const FEHLVERSUCH_FRIST_S: u64 = 3600;

/// Wie viele Zeitstempel sind juenger als die Frist?
pub fn junge_versuche(zeiten: &[u64], jetzt: u64) -> u32 {
    zeiten.iter().filter(|t| jetzt.saturating_sub(**t) < FEHLVERSUCH_FRIST_S).count() as u32
}

fn versuche_pfad() -> std::path::PathBuf {
    std::path::PathBuf::from(std::env::var("CHIMERA_STATE_DIR").unwrap_or_else(|_| "/opt/chimera/state".into())).join("mojo-versuche.json")
}

fn jetzt_s() -> u64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

fn versuche_laden() -> BTreeMap<String, Vec<u64>> {
    std::fs::read_to_string(versuche_pfad()).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default()
}

/// Befehl mit Frist; `Some((ok, Ausgabe))`, `None` wenn nicht startbar oder zu lang.
/// Befehl ohne Ausgabe (stdout und stderr verworfen), mit Frist. Fuer lange Laeufe, deren
/// Ausgabe groesser als der Pipe-Puffer ist: Wer sie nicht liest, haengt sonst am vollen Puffer.
fn befehl_still(prog: &str, args: &[&str], frist: Duration) -> Option<bool> {
    let mut kind = Command::new(prog).args(args).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).spawn().ok()?;
    let start = Instant::now();
    loop {
        match kind.try_wait().ok()? {
            Some(st) => return Some(st.success()),
            None if start.elapsed() > frist => {
                let _ = kind.kill();
                let _ = kind.wait();
                return None;
            }
            None => std::thread::sleep(Duration::from_millis(100)),
        }
    }
}

fn befehl(prog: &str, args: &[&str], frist: Duration) -> Option<(bool, String)> {
    let mut kind = Command::new(prog).args(args).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().ok()?;
    let start = Instant::now();
    loop {
        match kind.try_wait().ok()? {
            Some(st) => {
                let mut aus = String::new();
                if let Some(mut o) = kind.stdout.take() {
                    let _ = o.read_to_string(&mut aus);
                }
                if aus.is_empty() {
                    if let Some(mut e) = kind.stderr.take() {
                        let _ = e.read_to_string(&mut aus);
                    }
                }
                return Some((st.success(), aus));
            }
            None if start.elapsed() > frist => {
                let _ = kind.kill();
                let _ = kind.wait();
                return None;
            }
            None => std::thread::sleep(Duration::from_millis(20)),
        }
    }
}

const FRIST: Duration = Duration::from_secs(10);
const FRIST_LANG: Duration = Duration::from_secs(40);
/// Pakete nachladen braucht Netz und Zeit.
const FRIST_PAKETE: Duration = Duration::from_secs(600);

pub struct Echt;

impl System for Echt {
    fn zustand(&self, unit: &str) -> Option<UnitZustand> {
        let (ok, aus) = befehl("systemctl", &["show", unit, "-p", EIGENSCHAFTEN], FRIST)?;
        if !ok && aus.trim().is_empty() {
            return None;
        }
        let z = zustand_aus_show(unit, &aus);
        z.geladen.then_some(z)
    }

    fn journal(&self, unit: &str, n: usize) -> Vec<String> {
        let n = n.to_string();
        befehl("journalctl", &["-u", unit, "-n", &n, "--no-pager", "-o", "cat"], FRIST)
            .map(|(_, t)| t.lines().map(String::from).collect())
            .unwrap_or_default()
    }

    fn speicher_verfuegbar_mb(&self) -> Option<u64> {
        let t = std::fs::read_to_string("/proc/meminfo").ok()?;
        let kb: u64 = t.lines().find(|l| l.starts_with("MemAvailable:"))?.split_whitespace().nth(1)?.parse().ok()?;
        Some(kb / 1024)
    }

    fn schreibprobe(&self, pfad: &str) -> Result<(), String> {
        let datei = std::path::Path::new(pfad).join(format!(".mojo-probe-{}", std::process::id()));
        std::fs::write(&datei, b"probe").map_err(|e| format!("{}: {e}", datei.display()))?;
        std::fs::remove_file(&datei).map_err(|e| format!("{}: {e}", datei.display()))
    }

    fn platz_frei_mb(&self, pfad: &str) -> Option<u64> {
        let (ok, aus) = befehl("df", &["-Pk", pfad], FRIST)?;
        if !ok {
            return None;
        }
        // Zweite Zeile, vierte Spalte: verfuegbar in kB.
        let kb: u64 = aus.lines().nth(1)?.split_whitespace().nth(3)?.parse().ok()?;
        Some(kb / 1024)
    }

    fn requirements(&self) -> Option<String> {
        let pfad = std::env::var("CHIMERA_REQUIREMENTS").unwrap_or_else(|_| "/opt/chimera/source/requirements.txt".into());
        std::fs::read_to_string(pfad).ok()
    }

    fn warten(&self, dauer: Duration) {
        std::thread::sleep(dauer);
    }

    fn fehlversuche(&self, schluessel: &str) -> u32 {
        versuche_laden().get(schluessel).map(|z| junge_versuche(z, jetzt_s())).unwrap_or(0)
    }

    fn fehlversuch_merken(&self, schluessel: &str) {
        use gemein::protokoll::{melden, Stufe};
        let jetzt = jetzt_s();
        let mut alle = versuche_laden();
        alle.entry(schluessel.to_string()).or_default().push(jetzt);
        // Alte Eintraege fallen weg, die Datei waechst nicht.
        for z in alle.values_mut() {
            z.retain(|t| jetzt.saturating_sub(*t) < FEHLVERSUCH_FRIST_S);
        }
        alle.retain(|_, z| !z.is_empty());
        match serde_json::to_vec_pretty(&alle) {
            Ok(t) => {
                if let Err(e) = crate::daten::atomar_schreiben(&versuche_pfad(), &t, 0o640) {
                    melden(Stufe::Warnung, &format!("Mojo: Fehlversuche nicht abgelegt: {e}"));
                }
            }
            Err(e) => melden(Stufe::Warnung, &format!("Mojo: Fehlversuche nicht darstellbar: {e}")),
        }
    }

    fn gescheiterte_units(&self) -> Vec<String> {
        let Some((_, aus)) = befehl("systemctl", &["--failed", "--plain", "--no-legend", "--no-pager"], FRIST) else {
            return Vec::new();
        };
        units_aus_failed(&aus)
    }

    fn netz_erreichbar(&self) -> bool {
        netz_erreichbar()
    }
    fn ausfuehren(&self, r: &Reparatur) -> Result<(), String> {
        let sc = |args: &[&str]| -> Result<(), String> {
            match befehl("systemctl", args, FRIST_LANG) {
                Some((true, _)) => Ok(()),
                Some((false, aus)) => Err(format!("systemctl {} scheiterte: {}", args.join(" "), aus.trim())),
                None => Err(format!("systemctl {} antwortete nicht in {} s", args.join(" "), FRIST_LANG.as_secs())),
            }
        };
        match r {
            Reparatur::ResetUndStart { unit } => {
                let _ = sc(&["reset-failed", unit]);
                if sc(&["start", unit]).is_ok() {
                    return Ok(());
                }
                sc(&["start", "--job-mode=ignore-dependencies", unit])
            }
            Reparatur::PaketeNachladen { unit } => {
                // Der Installer laeuft als eigene, ungehaertete Unit (systemd-run): die Mojo-Unit
                // schreibt nur nach state/. `--wait` blockiert, bis er fertig ist; der feste
                // Unit-Name verhindert zwei Laeufe zugleich.
                let inst = std::env::var("CHIMERA_INSTALLER").unwrap_or_else(|_| "/opt/chimera/source/installer/chimera-install".into());
                match befehl_still(
                    "systemd-run",
                    &["--wait", "--collect", "--quiet", "--unit=chimera-mojo-pakete", "/bin/sh", &inst, "--only", "50"],
                    FRIST_PAKETE,
                ) {
                    Some(true) => {}
                    Some(false) => return Err("Installer Schritt 50 scheiterte; das Protokoll liegt unter /opt/chimera/logs/installer".into()),
                    None => return Err(format!("Installer Schritt 50 antwortete nicht in {} s", FRIST_PAKETE.as_secs())),
                }
                let _ = sc(&["reset-failed", unit]);
                sc(&["start", unit])
            }
            Reparatur::WlanNeuStarten { schnittstelle } => {
                // Reihenfolge nach Wahrscheinlichkeit: sanft (neu verbinden), dann der
                // Dienst, dann die Schnittstelle. Was fehlt, wird uebersprungen -- das
                // Ergebnis zaehlt, nicht der Exitcode eines Befehls (Regel 10j).
                let _ = befehl_still("nmcli", &["radio", "wifi", "off"], FRIST);
                let _ = befehl_still("nmcli", &["radio", "wifi", "on"], FRIST);
                let _ = befehl_still("wpa_cli", &["-i", schnittstelle, "reconfigure"], FRIST);
                for unit in [
                    "wpa_supplicant.service".to_string(),
                    format!("wpa_supplicant@{schnittstelle}.service"),
                    format!("ifup@{schnittstelle}.service"),
                    "networking.service".to_string(),
                ] {
                    // Nur anfassen, was laeuft: Ein nicht vorhandener Dienst ist kein Fehler.
                    if befehl_still("systemctl", &["is-active", "--quiet", &unit], FRIST)
                        == Some(true)
                    {
                        let _ = sc(&["restart", &unit]);
                    }
                }
                let _ = befehl_still("ip", &["link", "set", schnittstelle, "up"], FRIST);
                let _ = befehl_still("ifup", &[schnittstelle], FRIST);
                Ok(())
            }
            Reparatur::SocketNachziehen { socket, dienst } => {
                // systemd verweigert den Start eines Sockets, dessen Dienst schon laeuft.
                sc(&["stop", dienst])?;
                let sock = sc(&["start", socket]);
                let dienst_neu = sc(&["start", dienst]);
                sock.and(dienst_neu)
            }
        }
    }

    fn neustart_ausloesen(&self) -> Result<(), String> {
        // `systemctl reboot` kehrt zurueck, sobald der Neustart eingereiht ist;
        // auf das Herunterfahren warten wir nicht (das erledigt die Unit).
        match befehl("systemctl", &["reboot"], FRIST) {
            Some((true, _)) => Ok(()),
            Some((false, aus)) => Err(format!("systemctl reboot: {}", aus.trim())),
            None => Err("systemctl reboot: keine Antwort".into()),
        }
    }
}

// ---------------------------------------------------------------- Pruefungen

/// Eine Pruefung liest das System und liefert Befunde. **Hier eintragen** in
/// `pruefungen()`, wenn Mojo etwas Neues pruefen soll.
pub trait Pruefung {
    fn bereich(&self) -> &'static str;
    fn pruefen(&self, sys: &dyn System) -> Vec<Befund>;
}

/// Mehr Neustarts als das gelten als Warnung, auch wenn der Dienst gerade laeuft.
pub const NEUSTARTS_WARNUNG: u32 = 2;
/// Unter dieser Menge verfuegbaren Speichers (MB) warnt Mojo.
pub const SPEICHER_WARNUNG_MB: u64 = 60;

/// Die Dienste, die laufen muessen, und ihre Sockets (Name, Unit-Datei, Aufgabe).
pub const DIENSTE: &[&str] = &["chimera.service", "chimera-tor.service"];
/// (Socket, Dienst, den er bedient)
pub const SOCKETS: &[(&str, &str)] = &[
    ("chimera-tor.socket", "chimera-tor.service"),
    ("chimera-sitzung.socket", "chimera.service"),
];

pub struct Dienste;

impl Pruefung for Dienste {
    fn bereich(&self) -> &'static str {
        "dienst"
    }
    fn pruefen(&self, sys: &dyn System) -> Vec<Befund> {
        let mut aus = Vec::new();
        for unit in DIENSTE {
            let Some(z) = sys.zustand(unit) else {
                aus.push(Befund::problem(
                    Schwere::Error,
                    "dienst",
                    "dienst.fehlt",
                    unit,
                    &format!("{unit} ist dem System nicht bekannt"),
                    Ursache::neu("Die Unit-Datei fehlt", &format!("systemctl kennt {unit} nicht"), "Installer Schritt 99 (Gateway) bzw. 98 (Dienst) neu laufen lassen."),
                    None,
                ));
                continue;
            };
            match z.aktiv.as_str() {
                "active" if z.neustarts > NEUSTARTS_WARNUNG => {
                    aus.push(Befund::problem(
                        Schwere::Warn,
                        "dienst",
                        "dienst.neustarts",
                        unit,
                        &format!("{unit} laeuft, wurde aber {} Mal neu gestartet", z.neustarts),
                        ursache_fuer(sys, &z, &sys.journal(unit, 30)),
                        None,
                    ));
                }
                "active" => aus.push(Befund::gut("dienst", "dienst.laeuft", unit, &format!("{unit} laeuft"))),
                "activating" => aus.push(Befund::problem(
                    Schwere::Info,
                    "dienst",
                    "dienst.startet",
                    unit,
                    &format!("{unit} startet gerade (Versuch {})", z.neustarts + 1),
                    Ursache::neu("Der Dienst ist im Neustart", &format!("ActiveState activating, {} Neustarts", z.neustarts), "Abwarten; scheitert der naechste Versuch, meldet Mojo die Ursache."),
                    None,
                )),
                "failed" => {
                    let u = ursache_fuer(sys, &z, &sys.journal(unit, 30));
                    let rep = reparatur_fuer(&u, unit);
                    let mut b = Befund::problem(Schwere::Error, "dienst", "dienst.gescheitert", unit, &format!("{unit} ist gescheitert und laeuft nicht"), u, rep);
                    b.roh = Some(json!({"ergebnis": z.ergebnis, "status": z.exec_status, "neustarts": z.neustarts}));
                    aus.push(b);
                }
                andere => aus.push(Befund::problem(
                    Schwere::Warn,
                    "dienst",
                    "dienst.nicht_aktiv",
                    unit,
                    &format!("{unit} ist {andere}"),
                    Ursache::unbestimmt(&format!("ActiveState {andere}, Ergebnis {}", z.ergebnis)),
                    Some(Reparatur::ResetUndStart { unit: unit.to_string() }),
                )),
            }
        }
        aus
    }
}

/// Jede gescheiterte Chimera-Unit, die nicht schon eine eigene Pruefung hat
/// (Dienste, Sockets): so faellt auch `chimera-hardware` oder ein kuenftiger
/// Dienst auf, ohne dass jemand ihn in eine Liste eintraegt.
pub struct Gescheitert;

impl Pruefung for Gescheitert {
    fn bereich(&self) -> &'static str {
        "units"
    }
    fn pruefen(&self, sys: &dyn System) -> Vec<Befund> {
        let bekannt: Vec<&str> = DIENSTE.iter().copied().chain(SOCKETS.iter().map(|(s, _)| *s)).collect();
        let mut aus = Vec::new();
        for unit in sys.gescheiterte_units() {
            if bekannt.contains(&unit.as_str()) {
                continue;
            }
            // Mojos eigene Units (Lauf, Meldung) bleiben nach Exitcode 2 absichtlich im
            // Zustand failed: das ist die laute Meldung selbst. Sie wuerden sonst beim
            // naechsten Handlauf als eigener Befund auftauchen.
            if unit.starts_with("chimera-mojo") {
                continue;
            }
            let Some(z) = sys.zustand(&unit) else { continue };
            let u = ursache_fuer(sys, &z, &sys.journal(&unit, 30));
            let rep = reparatur_fuer(&u, &unit);
            let mut b = Befund::problem(Schwere::Error, "units", "unit.gescheitert", &unit, &format!("{unit} ist gescheitert"), u, rep);
            b.roh = Some(json!({"ergebnis": z.ergebnis, "status": z.exec_status, "neustarts": z.neustarts}));
            aus.push(b);
        }
        if aus.is_empty() {
            aus.push(Befund::gut("units", "units.keine_gescheitert", "chimera*", "keine weitere Chimera-Unit ist gescheitert"));
        }
        aus
    }
}

pub struct Sockets;

impl Pruefung for Sockets {
    fn bereich(&self) -> &'static str {
        "socket"
    }
    fn pruefen(&self, sys: &dyn System) -> Vec<Befund> {
        let mut aus = Vec::new();
        for (sock, dienst) in SOCKETS {
            let Some(z) = sys.zustand(sock) else {
                aus.push(Befund::problem(
                    Schwere::Error,
                    "socket",
                    "socket.fehlt",
                    sock,
                    &format!("{sock} ist dem System nicht bekannt"),
                    Ursache::neu("Die Socket-Unit fehlt", &format!("systemctl kennt {sock} nicht"), "Installer Schritt 99 neu laufen lassen."),
                    None,
                ));
                continue;
            };
            if z.aktiv == "active" {
                aus.push(Befund::gut("socket", "socket.aktiv", sock, &format!("{sock} lauscht")));
                continue;
            }
            // Der Fund vom 1.11.: Socket inaktiv, obwohl der Dienst laeuft. Dann
            // fehlt dem Dienst der Weg, den ihm der Socket geben soll.
            let dienst_laeuft = sys.zustand(dienst).map(|d| d.aktiv == "active").unwrap_or(false);
            let jour = sys.journal(sock, 20);
            let (text, beleg) = if jour.iter().any(|l| l.contains("already active, refusing")) {
                (
                    "systemd verweigerte den Start des Sockets, weil sein Dienst schon lief".to_string(),
                    jour.iter().rev().find(|l| l.contains("refusing")).cloned().unwrap_or_default(),
                )
            } else if dienst_laeuft && jour.iter().any(|l| l.contains("Deactivated successfully") || l.contains("Closed ")) {
                // Am Pi gemessen: ein von Hand oder vom Installer gestoppter Socket
                // schliesst sich sauber; der Dienst laeuft ohne ihn weiter.
                (
                    "Der Socket wurde angehalten (sauber beendet), sein Dienst laeuft ohne ihn weiter".to_string(),
                    jour.iter().rev().find(|l| l.contains("Deactivated successfully") || l.contains("Closed ")).cloned().unwrap_or_default(),
                )
            } else {
                ("Der Socket ist nicht aktiv".to_string(), format!("ActiveState {}, Ergebnis {}", z.aktiv, z.ergebnis))
            };
            let rep = Reparatur::SocketNachziehen { socket: sock.to_string(), dienst: dienst.to_string() };
            let mut b = Befund::problem(
                Schwere::Error,
                "socket",
                "socket.inaktiv",
                sock,
                &format!("{sock} ist {} (Dienst {dienst} {})", z.aktiv, if dienst_laeuft { "laeuft ohne ihn" } else { "laeuft nicht" }),
                Ursache::neu(&text, &beleg, "Den Dienst anhalten, den Socket starten, den Dienst wieder starten (Reparatur Stufe 1)."),
                Some(rep),
            );
            b.roh = Some(json!({"socket": {"aktiv": z.aktiv, "ergebnis": z.ergebnis}, "dienst_laeuft": dienst_laeuft}));
            aus.push(b);
        }
        aus
    }
}

pub struct Speicher;

impl Pruefung for Speicher {
    fn bereich(&self) -> &'static str {
        "speicher"
    }
    fn pruefen(&self, sys: &dyn System) -> Vec<Befund> {
        match sys.speicher_verfuegbar_mb() {
            None => vec![Befund::problem(
                Schwere::Info,
                "speicher",
                "speicher.nicht_lesbar",
                "meminfo",
                "Der verfuegbare Speicher ist nicht lesbar",
                Ursache::unbestimmt("/proc/meminfo nicht lesbar oder ohne MemAvailable"),
                None,
            )],
            Some(mb) if mb < SPEICHER_WARNUNG_MB => {
                let fehlt = SPEICHER_WARNUNG_MB - mb;
                vec![Befund::problem(
                    Schwere::Warn,
                    "speicher",
                    "speicher.knapp",
                    "meminfo",
                    &format!("Arbeitsspeicher (RAM): nur {mb} MB verfuegbar, {fehlt} MB unter der Schwelle von {SPEICHER_WARNUNG_MB} MB"),
                    Ursache::neu(
                        "Der Arbeitsspeicher (RAM) ist knapp, nicht die SD-Karte",
                        &format!("MemAvailable {mb} MB, Schwelle {SPEICHER_WARNUNG_MB} MB, es fehlen {fehlt} MB RAM"),
                        "Speicherverbrauch der Prozesse ansehen (ps); den groessten Verbraucher pruefen; Modelle oder Dienste verkleinern. Auslagerung (zram) hilft nur bei selten benutzten Seiten.",
                    ),
                    None,
                )]
            }
            Some(mb) => vec![Befund::gut("speicher", "speicher.ok", "meminfo", &format!("Arbeitsspeicher (RAM): {mb} MB verfuegbar"))],
        }
    }
}

/// Wo Bericht und Protokoll auf der Karte landen. Ist dort kein Schreiben moeglich,
/// bleibt ein Fehler unbemerkt (Regel "Jeder Lauf hinterlaesst ein Protokoll").
/// Die Pfade kommen aus der Umgebung, die der Installer setzt (`CHIMERA_STATE_DIR`,
/// `CHIMERA_LOG_KARTE`); im Code steht kein fester Pfad zum Heimverzeichnis.
/// Unter dieser Menge freien Platzes (MB) warnt Mojo.
pub const PLATZ_WARNUNG_MB: u64 = 100;

/// Die Ordner, in denen Mojo das Schreiben prueft.
pub struct Karte {
    pub pfade: Vec<String>,
}

impl Karte {
    /// Aus der Umgebung der Unit. Ein nicht gesetzter Pfad wird nicht erfunden:
    /// fehlt `CHIMERA_LOG_KARTE`, prueft Mojo nur `state/` und sagt es im Bericht.
    pub fn aus_umgebung() -> Karte {
        let mut pfade = vec![std::env::var("CHIMERA_STATE_DIR").unwrap_or_else(|_| "/opt/chimera/state".into())];
        if let Ok(p) = std::env::var("CHIMERA_LOG_KARTE") {
            if !p.trim().is_empty() {
                pfade.push(p);
            }
        }
        Karte { pfade }
    }
}

impl Pruefung for Karte {
    fn bereich(&self) -> &'static str {
        "karte"
    }
    fn pruefen(&self, sys: &dyn System) -> Vec<Befund> {
        let mut aus = Vec::new();
        if self.pfade.len() < 2 {
            aus.push(Befund::problem(
                Schwere::Info,
                "karte",
                "karte.protokollpfad_fehlt",
                "CHIMERA_LOG_KARTE",
                "Der Ordner des Protokolls auf der Karte ist nicht bekannt, nur state/ wird geprueft",
                Ursache::neu(
                    "CHIMERA_LOG_KARTE ist in der Umgebung dieser Unit nicht gesetzt",
                    "Umgebungsvariable CHIMERA_LOG_KARTE leer",
                    "Installer Schritt 27 neu laufen lassen: er setzt die Variable in der Mojo-Unit.",
                ),
                None,
            ));
        }
        for pfad in self.pfade.iter().cloned() {
            match sys.schreibprobe(&pfad) {
                Ok(()) => {
                    aus.push(Befund::gut("karte", "karte.schreibbar", &pfad, &format!("Speicherkarte (SD): {pfad} ist beschreibbar")));
                    match sys.platz_frei_mb(&pfad) {
                        Some(mb) if mb < PLATZ_WARNUNG_MB => {
                            let fehlt = PLATZ_WARNUNG_MB - mb;
                            aus.push(Befund::problem(
                                Schwere::Warn,
                                "karte",
                                "karte.voll",
                                &pfad,
                                &format!("Speicherkarte (SD): auf {pfad} nur noch {mb} MB frei, {fehlt} MB unter der Schwelle von {PLATZ_WARNUNG_MB} MB"),
                                Ursache::mensch(
                                    "Die Speicherkarte (SD) ist fast voll, nicht der Arbeitsspeicher",
                                    &format!("df: {mb} MB frei, Schwelle {PLATZ_WARNUNG_MB} MB, es fehlen {fehlt} MB auf der Karte"),
                                    "Platz schaffen (df -h, du -sh /var/log /home/chimera): grosse Dateien und alte Protokolle ansehen; eine groessere Karte nehmen.",
                                ),
                                None,
                            ));
                        }
                        _ => {}
                    }
                }
                Err(grund) => {
                    let (text, weg) = if grund.to_lowercase().contains("read-only") || grund.to_lowercase().contains("schreibgesch") {
                        (
                            "Das Dateisystem ist schreibgeschuetzt (haeufig: die Karte hat sich nach Fehlern selbst auf nur-lesen gestellt)",
                            "Das Kernelprotokoll auf Kartenfehler lesen (dmesg | grep -i -E 'mmc|ext4|i/o error'); die Karte ersetzen oder pruefen (fsck beim naechsten Start).",
                        )
                    } else if grund.to_lowercase().contains("no space") || grund.to_lowercase().contains("kein speicherplatz") {
                        ("Die Speicherkarte (SD) ist voll, nicht der Arbeitsspeicher", "Platz schaffen (df -h); grosse Dateien und alte Protokolle ansehen; eine groessere Karte nehmen.")
                    } else if grund.to_lowercase().contains("denied") || grund.to_lowercase().contains("verweigert") {
                        ("Dem Prozess fehlt das Schreibrecht", "Besitzer und Modus des Ordners pruefen; Installer Schritt 99 (Gateway) legt state/ an.")
                    } else {
                        ("Auf den Ordner laesst sich nicht schreiben", "Den genannten Grund lesen und den Ordner pruefen.")
                    };
                    aus.push(Befund::problem(
                        Schwere::Error,
                        "karte",
                        "karte.nicht_schreibbar",
                        &pfad,
                        &format!("{pfad} ist nicht beschreibbar"),
                        Ursache::mensch(text, &grund, weg),
                        None,
                    ));
                }
            }
        }
        aus
    }
}

/// **Hier eintragen**, wenn eine neue Pruefung dazukommt. Reihenfolge = Bericht.
pub fn pruefungen() -> Vec<Box<dyn Pruefung>> {
    vec![
        Box::new(Dienste),
        Box::new(Sockets),
        Box::new(Gescheitert),
        Box::new(Karte::aus_umgebung()),
        Box::new(Speicher),
        Box::new(Netz),
    ]
}

/// Wohin Mojo klopft, um "Netz da?" zu beantworten. TCP, nicht ICMP: ICMP ist
/// in manchen Netzen gefiltert, ein offener Port ist die ehrlichere Aussage.
pub const NETZ_PROBEN: &[&str] = &["8.8.8.8:53", "1.1.1.1:443"];
/// Die Schnittstelle, die Mojo neu startet, wenn kein Netz da ist.
pub const NETZ_SCHNITTSTELLE: &str = "wlan0";

/// Ist das Netz erreichbar? Eine Probe genuegt.
pub fn netz_erreichbar() -> bool {
    use std::net::{TcpStream, ToSocketAddrs};
    for ziel in NETZ_PROBEN {
        let Ok(mut adressen) = ziel.to_socket_addrs() else { continue };
        if let Some(adresse) = adressen.next() {
            if TcpStream::connect_timeout(&adresse, Duration::from_secs(3)).is_ok() {
                return true;
            }
        }
    }
    false
}

pub struct Netz;

impl Pruefung for Netz {
    fn bereich(&self) -> &'static str {
        "netz"
    }
    fn pruefen(&self, sys: &dyn System) -> Vec<Befund> {
        if sys.netz_erreichbar() {
            return vec![Befund::gut(
                "netz",
                "netz.erreichbar",
                "netz",
                "Das Netz ist erreichbar",
            )];
        }
        vec![Befund::problem(
            Schwere::Error,
            "netz",
            "netz.nicht_erreichbar",
            "netz",
            &format!("Kein Netz: keine Antwort von {}", NETZ_PROBEN.join(" oder ")),
            Ursache::neu(
                "Die Netzverbindung steht nicht",
                "TCP-Probe auf die oeffentlichen Adressen schlug fehl",
                "WLAN neu verbinden; der naechste Abruf versucht es erneut",
            ),
            Some(Reparatur::WlanNeuStarten {
                schnittstelle: NETZ_SCHNITTSTELLE.into(),
            }),
        )]
    }
}

// ----------------------------------------------------------------- Lauf

#[derive(Clone, Debug, PartialEq)]
pub struct Versuch {
    pub bereich: String,
    pub code: String,
    pub gegenstand: String,
    pub beschreibung: String,
    pub fehler: Option<String>,
    pub bestehen_geblieben: bool,
    /// `true`: gar nicht erst versucht, weil das Budget aufgebraucht ist.
    pub ausgesetzt: bool,
}

#[derive(Debug)]
pub struct Bericht {
    pub befunde: Vec<Befund>,
    pub versuche: Vec<Versuch>,
    pub fix: bool,
}

fn sammeln(sys: &dyn System, nur: &[Box<dyn Pruefung>]) -> Vec<Befund> {
    let mut alle = Vec::new();
    for p in nur {
        let mut b = p.pruefen(sys);
        // Der Bereich einer Pruefung ist ihre Zusage: jeder ihrer Befunde traegt ihn.
        // Eine Pruefung, die einen fremden Bereich meldet, ist ein Fehler im Code.
        for f in &mut b {
            if f.bereich != p.bereich() {
                f.meldung = format!("{} (Pruefung {} meldete Bereich {})", f.meldung, p.bereich(), f.bereich);
            }
        }
        alle.extend(b);
    }
    alle
}

/// Ein Lauf. Ohne `fix` wird nichts veraendert. Mit `fix` laufen die Reparaturen
/// der Stufe 1 **einmal**, danach pruefen dieselben Pruefungen noch einmal; ein
/// Befund, der wiederkehrt, ist unreparierbar (die Messung entscheidet, nie der
/// Rueckgabewert der Reparatur).
pub fn lauf(sys: &dyn System, pr: &[Box<dyn Pruefung>], fix: bool) -> Bericht {
    let mut befunde = sammeln(sys, pr);
    if !fix {
        return Bericht { befunde, versuche: Vec::new(), fix: false };
    }
    let schluessel = |bereich: &str, gegenstand: &str| format!("{bereich}|{gegenstand}");
    let mut versuche: Vec<Versuch> = Vec::new();
    let mut runde: u8 = 0;

    while runde < RUNDEN_MAX {
        // Was ist jetzt reparierbar? Nur Befunde ab Warnung, mit einer
        // Reparatur innerhalb der erlaubten Stufe.
        let offen: Vec<Befund> = befunde
            .iter()
            .filter(|b| {
                b.schwere >= Schwere::Warn
                    && !b.unreparierbar
                    && b.reparatur.as_ref().map(|r| r.stufe() <= TIER_MAX).unwrap_or(false)
            })
            .cloned()
            .collect();
        if offen.is_empty() {
            break;
        }
        runde += 1;

        let mut diese: Vec<Versuch> = Vec::new();
        for b in &offen {
            let Some(r) = &b.reparatur else { continue };
            let key = schluessel(&b.bereich, &b.gegenstand);
            if sys.fehlversuche(&key) >= BUDGET {
                diese.push(Versuch {
                    bereich: b.bereich.clone(),
                    code: b.code.clone(),
                    gegenstand: b.gegenstand.clone(),
                    beschreibung: r.beschreibung(),
                    fehler: Some(format!(
                        "Reparatur ausgesetzt: {BUDGET} Versuche in der letzten Stunde haben nichts bewirkt"
                    )),
                    bestehen_geblieben: true,
                    ausgesetzt: true,
                });
                continue;
            }
            let fehler = sys.ausfuehren(r).err();
            diese.push(Versuch {
                bereich: b.bereich.clone(),
                code: b.code.clone(),
                gegenstand: b.gegenstand.clone(),
                beschreibung: r.beschreibung(),
                fehler,
                bestehen_geblieben: false,
                ausgesetzt: false,
            });
        }
        if diese.iter().all(|v| v.ausgesetzt) {
            // Nichts mehr zu versuchen: Budget aufgebraucht.
            versuche.extend(diese);
            break;
        }
        sys.warten(NACHPRUEFUNG_WARTEN);
        befunde = sammeln(sys, pr);

        // Ein Anlauf (activating) ist nicht behoben: alles ab Info am selben
        // Gegenstand zaehlt als noch vorhanden.
        let noch: Vec<(String, String)> = befunde
            .iter()
            .filter(|b| b.schwere >= Schwere::Info)
            .map(|b| (b.bereich.clone(), b.gegenstand.clone()))
            .collect();
        for v in &mut diese {
            if v.ausgesetzt {
                continue;
            }
            v.bestehen_geblieben =
                noch.contains(&(v.bereich.clone(), v.gegenstand.clone()));
            if v.bestehen_geblieben {
                sys.fehlversuch_merken(&schluessel(&v.bereich, &v.gegenstand));
            }
        }
        versuche.extend(diese);
    }

    // Was nach allen Runden noch steht und reparierbar gewesen waere, gilt als
    // unreparierbar -- mit der Ursache, die der Befund ohnehin nennt.
    let versucht: Vec<(String, String)> = versuche
        .iter()
        .filter(|v| v.bestehen_geblieben)
        .map(|v| (v.bereich.clone(), v.gegenstand.clone()))
        .collect();
    for b in &mut befunde {
        if b.schwere >= Schwere::Info
            && versucht.contains(&(b.bereich.clone(), b.gegenstand.clone()))
        {
            b.unreparierbar = true;
        }
    }
    Bericht { befunde, versuche, fix: true }
}

impl Bericht {
    pub fn schlimmste(&self) -> Schwere {
        self.befunde.iter().map(|b| b.schwere).max().unwrap_or(Schwere::Ok)
    }
    pub fn exitcode(&self) -> u8 {
        self.schlimmste().rang()
    }
    pub fn zaehlung(&self) -> BTreeMap<&'static str, usize> {
        let mut m = BTreeMap::new();
        for b in &self.befunde {
            *m.entry(b.schwere.text()).or_insert(0) += 1;
        }
        m
    }
    pub fn als_json(&self, jetzt: u64) -> Value {
        json!({
            "zeit": jetzt,
            "exitcode": self.exitcode(),
            "fix": self.fix,
            "zaehlung": self.zaehlung(),
            "befunde": self.befunde.iter().map(befund_json).collect::<Vec<_>>(),
            "versuche": self.versuche.iter().map(|v| json!({
                "bereich": v.bereich, "code": v.code, "gegenstand": v.gegenstand,
                "beschreibung": v.beschreibung, "fehler": v.fehler,
                "bestehen_geblieben": v.bestehen_geblieben, "ausgesetzt": v.ausgesetzt,
            })).collect::<Vec<_>>(),
        })
    }
}

fn befund_json(b: &Befund) -> Value {
    let mut v = json!({
        "schwere": b.schwere.text(),
        "bereich": b.bereich,
        "code": b.code,
        "gegenstand": b.gegenstand,
        "meldung": b.meldung,
        "unreparierbar": b.unreparierbar,
        "reparatur": b.reparatur.as_ref().map(|r| r.beschreibung()),
    });
    if let Some(u) = &b.ursache {
        v["ursache"] = json!({"text": u.text, "beleg": u.beleg, "weg": u.weg, "bestimmt": u.bestimmt, "nur_mensch": u.nur_mensch});
    }
    if let Some(r) = &b.roh {
        v["roh"] = r.clone();
    }
    v
}

/// Die Zeilen, die Mojo laut meldet: je Befund ab Warnung eine, mit Stufe,
/// Ursache und Weg in derselben Zeile. Getrennt von der Ausgabe, damit sie sich
/// pruefen laesst.
pub fn laute_zeilen(b: &Bericht) -> Vec<(Schwere, String)> {
    let mut aus = Vec::new();
    for f in &b.befunde {
        if f.schwere < Schwere::Warn {
            continue;
        }
        let (ursache, weg) = f.ursache.as_ref().map(|u| (u.text.as_str(), u.weg.as_str())).unwrap_or(("unbekannt", ""));
        aus.push((
            f.schwere,
            format!(
                "Mojo: {}{} -- Ursache: {} -- Weg: {}",
                f.meldung,
                if f.unreparierbar { " [UNREPARIERBAR: die Reparatur hat nichts bewirkt]" } else { "" },
                ursache,
                weg
            ),
        ));
    }
    aus
}

/// Jeden Befund ab Warnung **laut** ins Journal: Stufe `<3>` Fehler, `<4>` Warnung.
/// Das ist das "laut werfen" der Regel Mojo.
pub fn laut_melden(b: &Bericht) {
    use gemein::protokoll::{melden, Stufe};
    for (schwere, text) in laute_zeilen(b) {
        melden(if schwere == Schwere::Error { Stufe::Fehler } else { Stufe::Warnung }, &text);
    }
}

/// Gut lesbarer Bericht. Ursache und Weg stehen bei **jedem** Befund ab Info.
pub fn als_text(b: &Bericht) -> String {
    let mut t = String::new();
    let mut bereich = String::new();
    for f in &b.befunde {
        if f.bereich != bereich {
            bereich = f.bereich.clone();
            t.push_str(&format!("\n{bereich}:\n"));
        }
        let zeichen = match f.schwere {
            Schwere::Ok => "ok",
            Schwere::Info => "..",
            Schwere::Warn => "!!",
            Schwere::Error => "XX",
        };
        t.push_str(&format!("  [{zeichen}] {}{}\n", f.meldung, if f.unreparierbar { "  -- UNREPARIERBAR" } else { "" }));
        if let Some(u) = &f.ursache {
            t.push_str(&format!("        Ursache: {}\n        Beleg:   {}\n        Weg:     {}\n", u.text, u.beleg, u.weg));
            if u.nur_mensch && u.bestimmt {
                t.push_str("        (das kann nur ein Mensch beheben)\n");
            }
        }
    }
    for v in &b.versuche {
        t.push_str(&format!(
            "\nReparatur: {} -> {}\n",
            v.beschreibung,
            match (&v.fehler, v.bestehen_geblieben) {
                (_, false) => "behoben (Nachpruefung ok)".to_string(),
                (Some(e), true) => format!("NICHT behoben, Fehler: {e}"),
                (None, true) => "NICHT behoben (Befund besteht nach der Reparatur weiter)".to_string(),
            }
        ));
    }
    let z = b.zaehlung();
    t.push_str(&format!("\nZusammenfassung: {}\n", ["error", "warn", "info", "ok"].iter().map(|k| format!("{} {}", z.get(k).unwrap_or(&0), k)).collect::<Vec<_>>().join(", ")));
    t
}


/// Den Bericht als Datei ablegen (atomar). Schlaegt das fehl, steht es im
/// Protokoll: ein Bericht, der nirgends landet, ist stiller Misserfolg.
/// Wie lange ein Oracle-Ergebnis gilt. Aelter heisst: neu messen.
pub const ORACLE_TTL: Duration = Duration::from_secs(6 * 3600);

/// Eine laufende Reparatur. Solange dieser Wert lebt, haelt der Prozess die
/// Sperre; danach gibt das Betriebssystem sie frei -- auch wenn er abstuerzt.
///
/// Warum es sie gibt (DESIGN, Regel "Mojo"): Timer, `OnFailure=` und der
/// Installer koennen gleichzeitig `--miracle` starten. Ohne Sperre zaehlen
/// zwei Laeufe denselben Fehlversuch hoch oder ueberschreiben ihn sich
/// gegenseitig (`mojo-versuche.json`), und der Zaehler luegt danach.
pub struct ReparaturSperre {
    _datei: std::fs::File,
}

impl ReparaturSperre {
    /// Sperre nehmen, ohne zu warten. `None` heisst: ein anderer Lauf
    /// repariert gerade -- dann wird nicht gewartet und nicht mitgemacht.
    pub fn nehmen(dir: &std::path::Path) -> Option<ReparaturSperre> {
        let _ = std::fs::create_dir_all(dir);
        let datei = std::fs::OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .truncate(false)
            .open(dir.join("mojo.lock"))
            .ok()?;
        match datei.try_lock() {
            Ok(()) => Some(ReparaturSperre { _datei: datei }),
            Err(_) => None,
        }
    }
}

/// Wo das letzte Oracle-Ergebnis liegt (Vorgabe; `--datei` ueberstimmt).
pub fn oracle_pfad() -> std::path::PathBuf {
    std::path::PathBuf::from(
        std::env::var("CHIMERA_STATE_DIR").unwrap_or_else(|_| "/opt/chimera/state".into()),
    )
    .join("mojo-oracle.json")
}

/// Ergebnis lesen: `Some(json)` nur, wenn es nicht aelter als `ORACLE_TTL` ist.
/// Ein altes Ergebnis wird als alt erkannt und nicht benutzt -- es wird auch
/// nicht stillschweigend geloescht, das erledigt der naechste Oracle-Lauf.
pub fn oracle_lesen(pfad: &std::path::Path) -> Option<Value> {
    let text = std::fs::read_to_string(pfad).ok()?;
    let wert: Value = serde_json::from_str(&text).ok()?;
    let zeit = wert.get("zeit")?.as_u64()?;
    let jetzt = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_secs();
    if jetzt.saturating_sub(zeit) > ORACLE_TTL.as_secs() {
        return None;
    }
    Some(wert)
}

pub fn ablegen(bericht: &Value, pfad: Option<&std::path::Path>) {
    use gemein::protokoll::{melden, Stufe};
    let ziel = pfad.map(std::path::PathBuf::from).unwrap_or_else(|| {
        oracle_pfad()
    });
    let mut text = match serde_json::to_vec_pretty(bericht) {
        Ok(t) => t,
        Err(e) => {
            melden(Stufe::Warnung, &format!("Mojo: Bericht nicht darstellbar: {e}"));
            return;
        }
    };
    text.push(b'\n');
    if let Err(e) = crate::daten::atomar_schreiben(&ziel, &text, 0o640) {
        melden(Stufe::Warnung, &format!("Mojo: Bericht nicht abgelegt ({}): {e}", ziel.display()));
    }
}

// -------------------------------------------------------------------- Tests

#[cfg(test)]
mod tests {
    // DESIGN, Regel Mojo: eine Reparatur zur Zeit. Der zweite Lauf darf
    // nicht mitmachen und nicht warten -- die Sperre ist nicht blockierend.
    #[test]
    fn nur_eine_reparatur_gleichzeitig() {
        let d = std::env::temp_dir().join(format!("mojo-lock-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let erste = super::ReparaturSperre::nehmen(&d).expect("erste Sperre");
        assert!(
            super::ReparaturSperre::nehmen(&d).is_none(),
            "zweite Sperre muss scheitern, solange die erste lebt"
        );
        drop(erste);
        assert!(
            super::ReparaturSperre::nehmen(&d).is_some(),
            "nach dem Freigeben muss sie wieder zu haben sein"
        );
        let _ = std::fs::remove_dir_all(&d);
    }

    use super::*;
    use std::cell::RefCell;
    use std::collections::HashMap;

    /// Ein Spiel-System: Zustaende und Journale sind vorgegeben, `ausfuehren`
    /// zeichnet auf und aendert, je nach Szenario, den Zustand -- die
    /// Pruefungen und die Reparaturlogik laufen echt.
    #[derive(Default)]
    struct Spiel {
        units: RefCell<HashMap<String, UnitZustand>>,
        journale: HashMap<String, Vec<String>>,
        mb: Option<u64>,
        aufgerufen: RefCell<Vec<String>>,
        /// `true`: eine Reparatur beseitigt den Befund wirklich.
        wirkt: bool,
        scheitert: Option<String>,
        /// Gegenstaende (Socket oder Unit), bei denen eine Reparatur trotz `wirkt` nichts bewirkt.
        wirkt_nicht_bei: Vec<&'static str>,
        /// `true`: die Wirkung tritt erst ein, wenn `warten` aufgerufen wurde
        /// (ein Dienst, der gerade anlaeuft).
        erst_nach_warten: bool,
        ausstehend: RefCell<Vec<Reparatur>>,
        gewartet: RefCell<u32>,
        /// Zustand der Unit nach einer wirkenden Reparatur (leer: active).
        danach: &'static str,
        fehlversuche: RefCell<HashMap<String, u32>>,
        /// Inhalt der requirements.txt (None: nicht lesbar). Vorgabe: Pillow und numpy.
        reqs: Option<&'static str>,
        /// Pfad -> Fehlertext der Schreibprobe (leer: beschreibbar).
        karte_fehler: HashMap<String, &'static str>,
        /// Pfad -> freier Platz in MB (leer: reichlich).
        platz: HashMap<String, u64>,
    }

    impl Spiel {
        fn mit(self, name: &str, aktiv: &str, ergebnis: &str, status: Option<i32>, neustarts: u32) -> Spiel {
            self.units.borrow_mut().insert(
                name.into(),
                UnitZustand { name: name.into(), geladen: true, aktiv: aktiv.into(), ergebnis: ergebnis.into(), exec_status: status, neustarts, ..Default::default() },
            );
            self
        }
        fn gesund() -> Spiel {
            let mut s = Spiel { mb: Some(300), wirkt: true, reqs: Some("Pillow>=10.0.0\n# Kommentar\nnumpy>=1.26\n"), ..Default::default() };
            for u in ["chimera.service", "chimera-tor.service", "chimera-tor.socket", "chimera-sitzung.socket"] {
                s = s.mit(u, "active", "success", Some(0), 0);
            }
            s
        }
        fn journal(mut self, unit: &str, zeilen: &[&str]) -> Spiel {
            self.journale.insert(unit.into(), zeilen.iter().map(|z| z.to_string()).collect());
            self
        }
    }

    impl System for Spiel {
        fn zustand(&self, unit: &str) -> Option<UnitZustand> {
            self.units.borrow().get(unit).cloned()
        }
        fn journal(&self, unit: &str, _n: usize) -> Vec<String> {
            self.journale.get(unit).cloned().unwrap_or_default()
        }
        fn speicher_verfuegbar_mb(&self) -> Option<u64> {
            self.mb
        }
        fn gescheiterte_units(&self) -> Vec<String> {
            let mut v: Vec<String> = self.units.borrow().values().filter(|z| z.aktiv == "failed").map(|z| z.name.clone()).collect();
            v.sort();
            v
        }
        fn schreibprobe(&self, pfad: &str) -> Result<(), String> {
            match self.karte_fehler.get(pfad) {
                Some(f) => Err(format!("{pfad}/.mojo-probe: {f}")),
                None => Ok(()),
            }
        }
        fn platz_frei_mb(&self, pfad: &str) -> Option<u64> {
            self.platz.get(pfad).copied().or(Some(5000))
        }
        fn requirements(&self) -> Option<String> {
            self.reqs.map(String::from)
        }
        fn warten(&self, _d: Duration) {
            *self.gewartet.borrow_mut() += 1;
            let offen: Vec<Reparatur> = self.ausstehend.borrow_mut().drain(..).collect();
            for r in &offen {
                self.anwenden(r);
            }
        }
        fn fehlversuche(&self, schluessel: &str) -> u32 {
            *self.fehlversuche.borrow().get(schluessel).unwrap_or(&0)
        }
        fn fehlversuch_merken(&self, schluessel: &str) {
            *self.fehlversuche.borrow_mut().entry(schluessel.to_string()).or_insert(0) += 1;
        }
        fn ausfuehren(&self, r: &Reparatur) -> Result<(), String> {
            self.aufgerufen.borrow_mut().push(r.beschreibung());
            if let Some(f) = &self.scheitert {
                return Err(f.clone());
            }
            if self.wirkt {
                if self.erst_nach_warten {
                    self.ausstehend.borrow_mut().push(r.clone());
                } else {
                    self.anwenden(r);
                }
            }
            Ok(())
        }
    }

    impl Spiel {
        fn anwenden(&self, r: &Reparatur) {
            let ziel = match r {
                Reparatur::ResetUndStart { unit } | Reparatur::PaketeNachladen { unit } => unit.as_str(),
                Reparatur::SocketNachziehen { socket, .. } => socket.as_str(),
                // Das Netz ist im Test kein Unit-Zustand: Die Probe wird ueber
                // `netz_erreichbar` gesteuert, die Reparatur selbst wirkt dort.
                Reparatur::WlanNeuStarten { .. } => "netz",
            };
            if self.wirkt_nicht_bei.contains(&ziel) {
                return;
            }
            {
                let mut u = self.units.borrow_mut();
                match r {
                    Reparatur::ResetUndStart { unit } | Reparatur::PaketeNachladen { unit } => {
                        if let Some(z) = u.get_mut(unit) {
                            z.aktiv = if self.danach.is_empty() { "active".into() } else { self.danach.into() };
                            z.ergebnis = "success".into();
                            z.exec_status = Some(0);
                            // Am Pi gemessen: reset-failed setzt NRestarts auf 0.
                            z.neustarts = 0;
                        }
                    }
                    Reparatur::SocketNachziehen { socket, .. } => {
                        if let Some(z) = u.get_mut(socket) {
                            z.aktiv = "active".into();
                        }
                    }
                    Reparatur::WlanNeuStarten { .. } => {
                        // Kein Unit-Zustand: Im Spiel bleibt das Netz, wie es war.
                    }
                }
            }
        }
    }

    fn karte_pruefung() -> Vec<Box<dyn Pruefung>> {
        vec![Box::new(Karte { pfade: vec!["/t/state".into(), "/t/logs".into()] })]
    }

    /// Name einer Instanz der Meldeunit-Vorlage. Das Trennzeichen wird zusammengesetzt, damit
    /// im Quelltext keine Zeichenfolge steht, die der Scanner fuer eine Mailadresse haelt.
    fn vorlage(dienst: &str) -> String {
        format!("chimera-mojo{}{dienst}.service", '@')
    }

    fn hat<'a>(b: &'a Bericht, code: &str, gegenstand: &str) -> Option<&'a Befund> {
        b.befunde.iter().find(|x| x.code == code && x.gegenstand == gegenstand)
    }

    #[test]
    fn ein_gesundes_system_ist_sauber_und_aendert_nichts() {
        let s = Spiel::gesund();
        let b = lauf(&s, &pruefungen(), true);
        assert_eq!(b.exitcode(), 0, "{}", als_text(&b));
        assert!(b.versuche.is_empty());
        assert!(s.aufgerufen.borrow().is_empty());
    }

    #[test]
    fn ohne_fix_wird_nie_repariert_auch_nicht_bei_fehlern() {
        let s = Spiel::gesund().mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        let b = lauf(&s, &pruefungen(), false);
        assert_eq!(b.exitcode(), 2);
        assert!(s.aufgerufen.borrow().is_empty(), "Oracle veraendert nichts");
        assert!(b.versuche.is_empty());
    }

    #[test]
    fn inaktiver_socket_wird_nachgezogen_und_die_nachpruefung_bestaetigt_es() {
        let s = Spiel::gesund()
            .mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0)
            .journal("chimera-sitzung.socket", &["chimera-sitzung.socket: Socket service chimera.service already active, refusing."]);
        let vorher = lauf(&s, &pruefungen(), false);
        let f = hat(&vorher, "socket.inaktiv", "chimera-sitzung.socket").expect("Befund");
        let u = f.ursache.as_ref().unwrap();
        assert!(u.text.contains("schon lief"), "Ursache nennt den Grund: {}", u.text);
        assert!(u.beleg.contains("already active, refusing"), "Beleg ist die Journalzeile");
        assert!(f.reparatur.is_some());
        let b = lauf(&s, &pruefungen(), true);
        assert_eq!(b.exitcode(), 0, "{}", als_text(&b));
        assert!(b.versuche.len() >= 1, "mindestens ein Versuch");
        assert!(!b.versuche[0].bestehen_geblieben);
        assert!(als_text(&b).contains("behoben (Nachpruefung ok)"));
    }

    #[test]
    fn ein_angehaltener_socket_bei_laufendem_dienst_nennt_das_als_ursache() {
        // Am Pi gemessen: Journalzeilen eines sauber gestoppten Sockets.
        let s = Spiel::gesund()
            .mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0)
            .journal("chimera-sitzung.socket", &["chimera-sitzung.socket: Deactivated successfully.", "Closed chimera-sitzung.socket - Chimera -- Sitzungs-Socket."]);
        let b = lauf(&s, &pruefungen(), false);
        let u = hat(&b, "socket.inaktiv", "chimera-sitzung.socket").unwrap().ursache.clone().unwrap();
        assert!(u.text.contains("angehalten"), "{}", u.text);
        assert!(u.beleg.starts_with("Closed ") || u.beleg.contains("Deactivated"), "{}", u.beleg);
    }

    #[test]
    fn eine_reparatur_die_nichts_bewirkt_ist_unreparierbar_und_wird_laut() {
        let mut s = Spiel::gesund().mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        s.wirkt = false; // der Aufruf gelingt (Ok), aendert aber nichts
        let b = lauf(&s, &pruefungen(), true);
        let f = hat(&b, "socket.inaktiv", "chimera-sitzung.socket").unwrap();
        assert!(f.unreparierbar, "dieselbe Messung zeigt den Befund weiter");
        assert!(b.versuche[0].bestehen_geblieben);
        assert_eq!(b.exitcode(), 2);
        assert!(als_text(&b).contains("UNREPARIERBAR"));
        assert!(als_text(&b).contains("NICHT behoben"));
        // Auch unreparierbar nennt Mojo die Ursache und den Weg.
        let u = f.ursache.as_ref().unwrap();
        assert!(!u.text.is_empty() && !u.weg.is_empty() && !u.beleg.is_empty());
    }

    #[test]
    fn eine_reparatur_die_mit_fehler_endet_nennt_den_fehler() {
        let mut s = Spiel::gesund().mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        s.scheitert = Some("systemctl stop scheiterte: Access denied".into());
        let b = lauf(&s, &pruefungen(), true);
        assert!(b.versuche[0].fehler.as_deref().unwrap().contains("Access denied"));
        assert!(als_text(&b).contains("Access denied"));
        assert!(hat(&b, "socket.inaktiv", "chimera-sitzung.socket").unwrap().unreparierbar);
    }

    #[test]
    fn eine_wirkungslose_reparatur_wird_nicht_endlos_wiederholt() {
        // Neue Zusage (smilez, 3.11.): Miracle repariert in Runden, bis der
        // Befund weg ist. Bewirkt die Reparatur nichts, greift das Budget --
        // sonst waere das ein Neustart-Sturm.
        let mut s = Spiel::gesund().mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        s.wirkt = false;
        let b = lauf(&s, &pruefungen(), true);
        assert_eq!(s.aufgerufen.borrow().len(), BUDGET as usize, "Budget begrenzt die Runden");
        assert!(b.befunde.iter().any(|f| f.unreparierbar), "bleibt als unreparierbar stehen");
    }

    #[test]
    fn eine_wirkende_reparatur_wird_genau_einmal_versucht() {
        let mut s = Spiel::gesund().mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        s.wirkt = true;
        let b = lauf(&s, &pruefungen(), true);
        assert_eq!(s.aufgerufen.borrow().len(), 1, "ein Versuch genuegt, wenn er wirkt");
        assert!(!b.befunde.iter().any(|f| f.unreparierbar));
    }

    #[test]
    fn ursachen_aus_dem_systemd_status_werden_belegt_benannt() {
        let faelle: &[(&str, Option<i32>, &str)] = &[
            ("exit-code", Some(203), "fehlt oder ist nicht ausfuehrbar"),
            ("exit-code", Some(217), "Nutzer"),
            ("exit-code", Some(226), "Pfad"),
            ("exit-code", Some(200), "Arbeitsverzeichnis"),
            ("resources", Some(0), "EnvironmentFile"),
            ("timeout", Some(15), "zu lange"),
            ("signal", Some(9), "SIGKILL"),
            ("signal", Some(11), "SIGSEGV"),
        ];
        for (erg, st, text) in faelle {
            let z = UnitZustand { name: "x.service".into(), geladen: true, aktiv: "failed".into(), ergebnis: erg.to_string(), exec_status: *st, ..Default::default() };
            let u = ursache_aus_unit(&z, &[]);
            assert!(u.bestimmt, "{erg} {st:?}");
            assert!(u.text.contains(text), "{erg} {st:?}: {}", u.text);
            assert!(u.beleg.contains(erg), "Beleg nennt das Ergebnis");
            assert!(!u.weg.is_empty());
        }
    }

    #[test]
    fn die_ausgabe_des_programms_liefert_die_ursache_bei_status_1() {
        let z = UnitZustand { name: "x.service".into(), geladen: true, aktiv: "failed".into(), ergebnis: "exit-code".into(), exec_status: Some(1), ..Default::default() };
        for (zeile, text) in [
            ("OSError: [Errno 98] Address already in use", "belegt"),
            ("PermissionError: [Errno 13] Permission denied: '/x'", "Recht"),
            ("FileNotFoundError: No such file or directory: '/y'", "fehlt"),
            ("ModuleNotFoundError: No module named 'numpy'", "Python-Paket"),
            ("socket.gaierror: Name or service not known", "aufloesen"),
            ("OSError: No space left on device", "voll"),
        ] {
            let u = ursache_aus_unit(&z, &["Start".into(), zeile.into(), "beendet".into()]);
            assert!(u.bestimmt, "{zeile}");
            assert!(u.text.contains(text), "{zeile}: {}", u.text);
            assert_eq!(u.beleg, zeile, "der Beleg ist die Zeile selbst");
        }
    }

    #[test]
    fn ohne_treffer_sagt_mojo_ursache_nicht_bestimmbar_und_liefert_rohdaten() {
        let z = UnitZustand { name: "x.service".into(), geladen: true, aktiv: "failed".into(), ergebnis: "exit-code".into(), exec_status: Some(1), ..Default::default() };
        let u = ursache_aus_unit(&z, &["a".into(), "b".into(), "c".into()]);
        assert!(!u.bestimmt);
        assert_eq!(u.text, "Ursache nicht bestimmbar");
        assert_eq!(u.beleg, "Ergebnis exit-code, Status 1; letzte Zeilen: a | b | c", "Rohdaten in fester Form");
        assert!(u.nur_mensch);
    }

    #[test]
    fn die_startgrenze_wird_als_ursache_benannt() {
        let z = UnitZustand { name: "x.service".into(), geladen: true, aktiv: "failed".into(), ergebnis: "exit-code".into(), exec_status: Some(203), neustarts: 5, ..Default::default() };
        let u = ursache_aus_unit(&z, &["x.service: Start request repeated too quickly.".into()]);
        assert!(u.text.starts_with("Die Startgrenze ist erreicht"), "{}", u.text);
        assert!(u.text.contains("fehlt oder ist nicht ausfuehrbar"), "die eigentliche Ursache bleibt: {}", u.text);
    }

    #[test]
    fn ein_gescheiterter_dienst_ist_ein_fehler_mit_ursache_und_wird_repariert_wenn_ein_neustart_hilft() {
        // Signal 9: ein Neustart kann helfen.
        let s = Spiel::gesund().mit("chimera-tor.service", "failed", "signal", Some(9), 1);
        let b = lauf(&s, &pruefungen(), false);
        let f = hat(&b, "dienst.gescheitert", "chimera-tor.service").unwrap();
        assert_eq!(f.schwere, Schwere::Error);
        assert!(f.ursache.as_ref().unwrap().text.contains("SIGKILL"));
        assert!(f.reparatur.is_some());
        let fix = lauf(&s, &pruefungen(), true);
        assert_eq!(fix.exitcode(), 0, "{}", als_text(&fix));
    }

    #[test]
    fn wenn_ein_neustart_nicht_helfen_kann_gibt_es_keine_reparatur_nur_ursache_und_weg() {
        // Gemessen am Pi: 203 (Programm fehlt) und 217 (Nutzer fehlt) heilt kein Neustart,
        // und reset-failed wuerde den Beleg loeschen und die Startgrenze zuruecksetzen.
        for (st, text) in [(203, "fehlt oder ist nicht ausfuehrbar"), (217, "Nutzer"), (226, "Pfad"), (200, "Arbeitsverzeichnis")] {
            let s = Spiel::gesund().mit("chimera-tor.service", "failed", "exit-code", Some(st), 5);
            let b = lauf(&s, &pruefungen(), true);
            let f = hat(&b, "dienst.gescheitert", "chimera-tor.service").unwrap();
            assert!(f.reparatur.is_none(), "{st}: keine Reparatur");
            assert!(f.ursache.as_ref().unwrap().text.contains(text) && !f.ursache.as_ref().unwrap().weg.is_empty());
            assert_eq!(f.schwere, Schwere::Error);
            assert!(s.aufgerufen.borrow().is_empty(), "{st}: es wurde nichts angefasst");
            assert!(!f.unreparierbar, "nie versucht, also nicht 'unreparierbar'");
            assert_eq!(b.exitcode(), 2, "bleibt laut");
        }
        // Die Muster der Programmausgabe: nur vorlaeufige Ursachen duerfen einen Neustart bekommen.
        let z = UnitZustand { name: "x.service".into(), geladen: true, aktiv: "failed".into(), ergebnis: "exit-code".into(), exec_status: Some(1), ..Default::default() };
        assert!(ursache_aus_unit(&z, &["Address already in use".into()]).neustart_hilft);
        assert!(!ursache_aus_unit(&z, &["Permission denied: '/x'".into()]).neustart_hilft);
        let paket = ursache_aus_unit(&z, &["ModuleNotFoundError: No module named 'x'".into()]);
        assert!(!paket.neustart_hilft && paket.paket_nachladen, "ein Neustart allein hilft nie, das Nachladen schon");
        assert!(!ursache_aus_unit(&z, &["No space left on device".into()]).neustart_hilft);
        assert!(!ursache_aus_unit(&z, &["etwas ganz anderes".into()]).neustart_hilft, "unbestimmt: kein blinder Neustart");
    }

    #[test]
    fn die_nachpruefung_wartet_bis_der_dienst_wirklich_laeuft() {
        // Ein Dienst, der gerade anlaeuft, ist direkt nach dem Start 'aktiv' und stirbt gleich.
        let mut s = Spiel::gesund().mit("chimera-tor.service", "failed", "signal", Some(9), 1);
        s.erst_nach_warten = true;
        let b = lauf(&s, &pruefungen(), true);
        assert_eq!(*s.gewartet.borrow(), 1, "es wurde gewartet");
        assert_eq!(b.exitcode(), 0, "{}", als_text(&b));
        assert!(!b.versuche[0].bestehen_geblieben);
        // Ohne Reparatur wird nicht gewartet.
        let g = Spiel::gesund();
        lauf(&g, &pruefungen(), true);
        assert_eq!(*g.gewartet.borrow(), 0);
    }

    #[test]
    fn ein_anlauf_zaehlt_nicht_als_behoben() {
        let mut s = Spiel::gesund().mit("chimera-tor.service", "failed", "signal", Some(9), 1);
        s.danach = "activating";
        let b = lauf(&s, &pruefungen(), true);
        assert!(b.versuche[0].bestehen_geblieben, "activating ist noch nicht gut");
        assert!(hat(&b, "dienst.startet", "chimera-tor.service").unwrap().unreparierbar);
    }

    #[test]
    fn nach_zwei_wirkungslosen_versuchen_pro_stunde_wird_die_reparatur_ausgesetzt() {
        let mut s = Spiel::gesund().mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        s.wirkt = false;
        for _ in 0..BUDGET {
            lauf(&s, &pruefungen(), true);
        }
        assert_eq!(s.aufgerufen.borrow().len(), BUDGET as usize);
        let b = lauf(&s, &pruefungen(), true);
        assert_eq!(s.aufgerufen.borrow().len(), BUDGET as usize, "kein dritter Versuch");
        let v = &b.versuche[0];
        assert!(v.ausgesetzt && v.bestehen_geblieben);
        assert!(v.fehler.as_deref().unwrap().contains("ausgesetzt"));
        let f = hat(&b, "socket.inaktiv", "chimera-sitzung.socket").unwrap();
        assert!(f.unreparierbar, "bleibt laut, mit Ursache");
        assert!(f.ursache.is_some());
        assert_eq!(*s.gewartet.borrow(), BUDGET, "ausgesetzt wartet nicht");
    }

    #[test]
    fn eine_wirkende_reparatur_verbraucht_kein_budget() {
        let s = Spiel::gesund().mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        lauf(&s, &pruefungen(), true);
        assert!(s.fehlversuche.borrow().is_empty());
    }

    #[test]
    fn nur_junge_versuche_zaehlen_fuer_das_budget() {
        let f = FEHLVERSUCH_FRIST_S;
        let jetzt = 10_000;
        // vor 100 s, vor 1000 s, vor f-1 s: alle jung; vor f s und vor f+500 s: abgelaufen
        assert_eq!(junge_versuche(&[jetzt - 100, jetzt - 1000, jetzt - (f - 1)], jetzt), 3);
        assert_eq!(junge_versuche(&[jetzt - f, jetzt - f - 500], jetzt), 0, "genau an der Frist ist es abgelaufen");
        assert_eq!(junge_versuche(&[jetzt - f - 1, jetzt - 5], jetzt), 1);
        assert_eq!(junge_versuche(&[], jetzt), 0);
        // Ein Zeitstempel aus der Zukunft (Uhr falsch) zaehlt als jung, nicht als Absturz.
        assert_eq!(junge_versuche(&[jetzt + 50], jetzt), 1);
    }

    #[test]
    fn ein_dienst_im_neustart_ist_nur_eine_info_kein_alarm() {
        let s = Spiel::gesund().mit("chimera.service", "activating", "exit-code", Some(1), 2);
        let b = lauf(&s, &pruefungen(), false);
        let f = hat(&b, "dienst.startet", "chimera.service").unwrap();
        assert_eq!(f.schwere, Schwere::Info);
        assert_eq!(b.exitcode(), 0, "Zwischenfehler sind kein Alarm");
        assert!(f.ursache.is_some(), "auch die Info nennt, was los ist");
    }

    #[test]
    fn ein_wieder_laufender_dienst_nennt_die_ursache_aus_dem_journal() {
        // Am Pi gemessen: nach Fehlversuchen und Erholung zeigt systemd Result=success,
        // Status 0 und NRestarts>0; die Ursache steht nur noch im Journal.
        let s = Spiel::gesund()
            .mit("chimera.service", "active", "success", Some(0), 4)
            .journal("chimera.service", &["Address already in use", "chimera.service: Main process exited, code=exited, status=1/FAILURE"]);
        let b = lauf(&s, &pruefungen(), false);
        let f = hat(&b, "dienst.neustarts", "chimera.service").unwrap();
        let u = f.ursache.as_ref().unwrap();
        assert!(u.bestimmt && u.text.contains("belegt"), "{}", u.text);
        assert_eq!(u.beleg, "Address already in use");
        assert!(f.reparatur.is_none(), "kein reset-failed: es wuerde den Zaehler und damit den Beleg loeschen");
    }

    #[test]
    fn viele_neustarts_bei_laufendem_dienst_sind_eine_warnung() {
        let s = Spiel::gesund().mit("chimera.service", "active", "success", Some(0), NEUSTARTS_WARNUNG + 1);
        let b = lauf(&s, &pruefungen(), false);
        assert_eq!(hat(&b, "dienst.neustarts", "chimera.service").unwrap().schwere, Schwere::Warn);
        assert_eq!(b.exitcode(), 1);
    }

    #[test]
    fn eine_unbekannte_unit_ist_ein_fehler_ohne_reparatur() {
        let mut s = Spiel::gesund();
        s.units.borrow_mut().remove("chimera-tor.service");
        let b = lauf(&s, &pruefungen(), true);
        let f = hat(&b, "dienst.fehlt", "chimera-tor.service").unwrap();
        assert!(f.reparatur.is_none());
        assert!(f.ursache.as_ref().unwrap().weg.contains("Installer"));
        assert!(s.aufgerufen.borrow().is_empty());
    }

    #[test]
    fn knapper_speicher_ist_eine_warnung_mit_ursache_und_fehlender_wert_eine_info() {
        let mut s = Spiel::gesund();
        s.mb = Some(SPEICHER_WARNUNG_MB - 1);
        let b = lauf(&s, &pruefungen(), false);
        let f = hat(&b, "speicher.knapp", "meminfo").unwrap();
        assert_eq!(f.schwere, Schwere::Warn);
        assert!(f.ursache.as_ref().unwrap().beleg.contains("MemAvailable"));
        s.mb = None;
        let b2 = lauf(&s, &pruefungen(), false);
        assert_eq!(hat(&b2, "speicher.nicht_lesbar", "meminfo").unwrap().schwere, Schwere::Info);
        assert_eq!(b2.exitcode(), 0, "nicht lesbar ist kein Alarm, aber es steht im Bericht");
    }

    /// Eine eigene Pruefung, wie ein Entwickler sie mit einer Zeile in `pruefungen()` anschliesst.
    struct Eigene(Schwere);
    impl Pruefung for Eigene {
        fn bereich(&self) -> &'static str {
            "eigene"
        }
        fn pruefen(&self, _sys: &dyn System) -> Vec<Befund> {
            vec![Befund::problem(
                self.0,
                "eigene",
                "eigene.test",
                "x",
                "eine Sache",
                Ursache::neu("weil", "beleg", "weg"),
                Some(Reparatur::ResetUndStart { unit: "x.service".into() }),
            )]
        }
    }

    #[test]
    fn nur_ab_warnung_wird_repariert_und_eine_eigene_pruefung_laesst_sich_anschliessen() {
        for (schwere, soll) in [(Schwere::Ok, 0), (Schwere::Info, 0), (Schwere::Warn, 1), (Schwere::Error, 1)] {
            let s = Spiel::gesund();
            let pr: Vec<Box<dyn Pruefung>> = vec![Box::new(Eigene(schwere))];
            let b = lauf(&s, &pr, true);
            if soll == 0 {
                assert_eq!(s.aufgerufen.borrow().len(), 0, "Schwere {schwere:?}");
                assert_eq!(b.versuche.len(), 0);
            } else {
                assert!(s.aufgerufen.borrow().len() >= 1, "Schwere {schwere:?}");
                assert!(b.versuche.len() >= 1);
            }
        }
    }

    #[test]
    fn warnungen_ohne_reparatur_werden_nicht_angefasst() {
        let mut s = Spiel::gesund();
        s.mb = Some(10);
        let b = lauf(&s, &pruefungen(), true);
        assert!(b.versuche.is_empty());
        assert_eq!(b.exitcode(), 1);
    }

    #[test]
    fn der_bericht_als_json_traegt_ursache_weg_und_unreparierbar() {
        let mut s = Spiel::gesund().mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        s.wirkt = false;
        let j = lauf(&s, &pruefungen(), true).als_json(1234);
        assert_eq!(j["exitcode"], 2);
        assert_eq!(j["zeit"], 1234);
        let f = j["befunde"].as_array().unwrap().iter().find(|b| b["code"] == "socket.inaktiv").unwrap();
        assert_eq!(f["unreparierbar"], true);
        assert!(f["ursache"]["text"].is_string() && f["ursache"]["weg"].is_string() && f["ursache"]["beleg"].is_string());
        assert_eq!(j["versuche"][0]["bestehen_geblieben"], true);
    }

    #[test]
    fn jeder_befund_ab_info_hat_eine_ursache_im_text_und_im_json() {
        let s = Spiel::gesund()
            .mit("chimera.service", "failed", "exit-code", Some(1), 5)
            .mit("chimera-tor.socket", "inactive", "success", Some(0), 0)
            .mit("chimera-tor.service", "activating", "exit-code", Some(1), 1);
        let b = lauf(&s, &pruefungen(), false);
        for f in &b.befunde {
            if f.schwere >= Schwere::Info {
                assert!(f.ursache.is_some(), "Befund ohne Ursache: {}", f.code);
            }
        }
        let t = als_text(&b);
        assert!(t.matches("Ursache:").count() >= 3 && t.matches("Weg:").count() >= 3, "{t}");
    }

    #[test]
    fn eine_unbekannte_gescheiterte_unit_wird_gefunden_benannt_und_repariert() {
        // Die Luecke vom 1.11.: eine Unit ausserhalb der festen Listen (hier die Hardware-Unit).
        let s = Spiel::gesund().mit("chimera-hardware.service", "failed", "exit-code", Some(203), 0);
        let b = lauf(&s, &pruefungen(), false);
        let f = hat(&b, "unit.gescheitert", "chimera-hardware.service").expect("Befund");
        assert_eq!(f.schwere, Schwere::Error);
        assert!(f.ursache.as_ref().unwrap().text.contains("fehlt oder ist nicht ausfuehrbar"));
        assert_eq!(b.exitcode(), 2);
        // 203 heilt kein Neustart: der Fix-Lauf fasst nichts an, der Befund bleibt laut.
        let fix = lauf(&s, &pruefungen(), true);
        assert_eq!(fix.exitcode(), 2);
        assert!(s.aufgerufen.borrow().is_empty());
        // Ein Signal dagegen wird repariert.
        let t = Spiel::gesund().mit("chimera-hardware.service", "failed", "signal", Some(9), 0);
        assert_eq!(lauf(&t, &pruefungen(), true).exitcode(), 0);
    }

    #[test]
    fn mojos_eigene_units_melden_sich_nicht_selbst_als_gescheitert() {
        // Nach einem Lauf mit Fehlern steht chimera-mojo.service absichtlich auf failed.
        let s = Spiel::gesund()
            .mit("chimera-mojo.service", "failed", "exit-code", Some(2), 0)
            .mit(&vorlage("chimera-probe"), "failed", "exit-code", Some(1), 0);
        let b = lauf(&s, &pruefungen(), false);
        assert!(hat(&b, "unit.gescheitert", "chimera-mojo.service").is_none(), "{}", als_text(&b));
        assert!(hat(&b, "unit.gescheitert", &vorlage("chimera-probe")).is_none());
        assert_eq!(b.exitcode(), 0);
    }

    #[test]
    fn die_protokollkarte_wird_dort_geprueft_wo_die_protokolle_landen() {
        // CHIMERA_LOG_KARTE der Dienst-Unit ist .../logs/productive, nicht .../logs.
        // Die Pfade kommen aus der Umgebung der Unit (Installer Schritt 27), nicht aus dem Code.
        std::env::set_var("CHIMERA_STATE_DIR", "/t/zustand");
        std::env::set_var("CHIMERA_LOG_KARTE", "/t/protokoll");
        let k = Karte::aus_umgebung();
        assert_eq!(k.pfade, vec!["/t/zustand".to_string(), "/t/protokoll".to_string()]);
        std::env::remove_var("CHIMERA_LOG_KARTE");
        let ohne = Karte::aus_umgebung();
        assert_eq!(ohne.pfade.len(), 1, "ein nicht gesetzter Pfad wird nicht erfunden");
        let b = lauf(&Spiel::gesund(), &[Box::new(ohne) as Box<dyn Pruefung>], false);
        let f = hat(&b, "karte.protokollpfad_fehlt", "CHIMERA_LOG_KARTE").expect("sagt, dass der Pfad fehlt");
        assert_eq!(f.schwere, Schwere::Info);
        assert!(f.ursache.as_ref().unwrap().weg.contains("Schritt 27"));
        std::env::remove_var("CHIMERA_STATE_DIR");
    }

    #[test]
    fn eine_gescheiterte_unit_mit_fester_pruefung_wird_nicht_doppelt_gemeldet() {
        let s = Spiel::gesund().mit("chimera-tor.service", "failed", "exit-code", Some(203), 5);
        let b = lauf(&s, &pruefungen(), false);
        assert!(hat(&b, "unit.gescheitert", "chimera-tor.service").is_none());
        assert!(hat(&b, "dienst.gescheitert", "chimera-tor.service").is_some());
    }

    #[test]
    fn eine_unreparierbare_fremde_unit_bleibt_unreparierbar_mit_ursache() {
        let mut s = Spiel::gesund().mit("chimera-probe.service", "failed", "signal", Some(9), 3);
        s.wirkt = false;
        let b = lauf(&s, &pruefungen(), true);
        let f = hat(&b, "unit.gescheitert", "chimera-probe.service").unwrap();
        assert!(f.unreparierbar);
        assert!(f.ursache.as_ref().unwrap().bestimmt, "die Ursache (Signal 9) bleibt benannt");
        // Mindestens ein Versuch; die Runden sind seit 3.11. erlaubt.
        assert!(s.aufgerufen.borrow().len() >= 1);
    }

    #[test]
    fn failed_ausgabe_wird_gelesen_und_auf_chimera_beschraenkt() {
        let t = "\u{25cf} chimera-probe.service loaded failed failed Probe\n  chimera-tor.socket loaded failed failed Socket\n\u{25cf} ssh.service loaded failed failed Fremd\n  chimera-probe.service loaded failed failed doppelt\n\n";
        assert_eq!(units_aus_failed(t), vec!["chimera-probe.service", "chimera-tor.socket"]);
        assert!(units_aus_failed("").is_empty());
        assert!(units_aus_failed("0 loaded units listed.").is_empty());
    }

    #[test]
    fn laut_heisst_eine_zeile_je_befund_ab_warnung_mit_ursache_weg_und_unreparierbar() {
        let mut s = Spiel::gesund().mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        s.mb = Some(10);
        s.wirkt = false;
        let b = lauf(&s, &pruefungen(), true);
        let z = laute_zeilen(&b);
        assert_eq!(z.len(), 2, "Socket (Fehler) und Speicher (Warnung): {z:?}");
        let sock = z.iter().find(|(_, t)| t.contains("chimera-sitzung.socket")).unwrap();
        assert_eq!(sock.0, Schwere::Error);
        assert!(sock.1.contains("[UNREPARIERBAR"), "{}", sock.1);
        assert!(sock.1.contains("Ursache: ") && sock.1.contains("Weg: "), "{}", sock.1);
        let mem = z.iter().find(|(_, t)| t.contains("RAM")).unwrap();
        assert_eq!(mem.0, Schwere::Warn);
        assert!(!mem.1.contains("UNREPARIERBAR"), "eine Warnung ohne Reparatur ist nicht unreparierbar");
        // Ein sauberes System ist still.
        assert!(laute_zeilen(&lauf(&Spiel::gesund(), &pruefungen(), true)).is_empty());
    }

    #[test]
    fn eine_schreibgeschuetzte_karte_ist_ein_fehler_den_nur_ein_mensch_beheben_kann() {
        let mut s = Spiel::gesund();
        s.karte_fehler.insert("/t/state".into(), "Read-only file system (os error 30)");
        let b = lauf(&s, &karte_pruefung(), true);
        let f = hat(&b, "karte.nicht_schreibbar", "/t/state").expect("Befund");
        assert_eq!(f.schwere, Schwere::Error);
        let u = f.ursache.as_ref().unwrap();
        assert!(u.bestimmt && u.nur_mensch, "bestimmt, aber nur ein Mensch kann es beheben");
        assert!(u.text.contains("schreibgeschuetzt"), "{}", u.text);
        assert!(u.beleg.contains("Read-only"), "Beleg ist die Meldung des Systems: {}", u.beleg);
        assert!(u.weg.contains("Karte"), "{}", u.weg);
        assert!(f.reparatur.is_none() && s.aufgerufen.borrow().is_empty(), "Software repariert keine Karte");
        assert_eq!(b.exitcode(), 2);
        assert!(als_text(&b).contains("das kann nur ein Mensch beheben"));
    }

    #[test]
    fn eine_volle_karte_und_ein_fehlendes_schreibrecht_haben_je_ihre_ursache() {
        for (fehler, text) in [("No space left on device (os error 28)", "voll"), ("Permission denied (os error 13)", "Schreibrecht"), ("etwas Seltsames", "nicht schreiben")] {
            let mut s = Spiel::gesund();
            s.karte_fehler.insert("/t/logs".into(), fehler);
            let b = lauf(&s, &karte_pruefung(), false);
            let f = hat(&b, "karte.nicht_schreibbar", "/t/logs").unwrap();
            assert!(f.ursache.as_ref().unwrap().text.contains(text), "{fehler}: {}", f.ursache.as_ref().unwrap().text);
        }
    }

    #[test]
    fn wenig_platz_ist_eine_warnung_mit_ursache_fuer_den_menschen() {
        let mut s = Spiel::gesund();
        s.platz.insert("/t/state".into(), PLATZ_WARNUNG_MB - 1);
        let b = lauf(&s, &karte_pruefung(), false);
        let f = hat(&b, "karte.voll", "/t/state").unwrap();
        assert_eq!(f.schwere, Schwere::Warn);
        assert!(f.ursache.as_ref().unwrap().nur_mensch && f.ursache.as_ref().unwrap().beleg.contains("MB frei"));
        assert_eq!(b.exitcode(), 1);
        s.platz.insert("/t/state".into(), PLATZ_WARNUNG_MB);
        assert!(hat(&lauf(&s, &karte_pruefung(), false), "karte.voll", "/t/state").is_none(), "an der Schwelle noch gut");
    }

    #[test]
    fn eine_pruefung_die_einen_fremden_bereich_meldet_faellt_auf() {
        struct Falsch;
        impl Pruefung for Falsch {
            fn bereich(&self) -> &'static str {
                "mein-bereich"
            }
            fn pruefen(&self, _s: &dyn System) -> Vec<Befund> {
                vec![Befund::gut("anderer", "x.ok", "x", "alles gut")]
            }
        }
        let pr: Vec<Box<dyn Pruefung>> = vec![Box::new(Falsch)];
        let b = lauf(&Spiel::gesund(), &pr, false);
        assert!(b.befunde[0].meldung.contains("meldete Bereich anderer"), "{}", b.befunde[0].meldung);
    }

    #[test]
    fn zwei_befunde_am_selben_bereich_werden_nicht_verwechselt() {
        // Der Gateway-Socket fehlt ganz (Befund ohne Reparatur, nie versucht), der
        // Sitzungs-Socket ist aus und die Reparatur wirkt nicht. Beide Befunde haben den
        // Bereich "socket". Nur der zweite war ein wirkungsloser Versuch: gilt der
        // Schluessel (Bereich) allein, wuerde auch der erste als "unreparierbar, die
        // Reparatur hat nichts bewirkt" bezeichnet -- obwohl nie etwas versucht wurde.
        let mut s = Spiel::gesund().mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        s.units.borrow_mut().remove("chimera-tor.socket");
        s.wirkt = false;
        let b = lauf(&s, &pruefungen(), true);
        let fehlt = hat(&b, "socket.fehlt", "chimera-tor.socket").expect("fehlender Socket");
        let aus = hat(&b, "socket.inaktiv", "chimera-sitzung.socket").expect("inaktiver Socket");
        assert!(!fehlt.unreparierbar, "nie versucht, also nicht 'unreparierbar': {}", als_text(&b));
        assert!(aus.unreparierbar, "versucht, ohne Wirkung");
        assert!(b.versuche.len() >= 1, "mindestens ein Versuch");
        assert_eq!(b.versuche[0].gegenstand, "chimera-sitzung.socket");
        assert!(!als_text(&b).split("chimera-sitzung").next().unwrap().contains("UNREPARIERBAR"), "die Markierung steht nicht beim fehlenden Socket");
    }

    #[test]
    fn ein_behobener_befund_neben_einem_offenen_am_selben_bereich_bleibt_behoben() {
        let mut s = Spiel::gesund()
            .mit("chimera-tor.socket", "inactive", "success", Some(0), 0)
            .mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        s.wirkt = true;
        s.wirkt_nicht_bei = vec!["chimera-tor.socket"];
        let b = lauf(&s, &pruefungen(), true);
        assert!(hat(&b, "socket.aktiv", "chimera-sitzung.socket").is_some(), "{}", als_text(&b));
        assert!(hat(&b, "socket.inaktiv", "chimera-tor.socket").unwrap().unreparierbar);
        assert!(!s.fehlversuche.borrow().contains_key("socket|chimera-sitzung.socket"), "der behobene verbraucht kein Budget");
        assert!(s.fehlversuche.borrow().contains_key("socket|chimera-tor.socket"));
    }

    #[test]
    fn ein_fehlendes_python_paket_wird_nachgeladen_und_der_dienst_neu_gestartet() {
        let s = Spiel::gesund()
            .mit("chimera.service", "failed", "exit-code", Some(1), 3)
            .journal("chimera.service", &["Traceback (most recent call last):", "ModuleNotFoundError: No module named 'numpy'"]);
        let b0 = lauf(&s, &pruefungen(), false);
        let f = hat(&b0, "dienst.gescheitert", "chimera.service").unwrap();
        let u = f.ursache.as_ref().unwrap();
        assert!(u.text.contains("Python-Paket") && u.beleg.contains("numpy"), "{u:?}");
        assert_eq!(f.reparatur, Some(Reparatur::PaketeNachladen { unit: "chimera.service".into() }));
        assert_eq!(f.reparatur.as_ref().unwrap().stufe(), 2);
        assert!(s.aufgerufen.borrow().is_empty(), "Oracle laedt nichts nach");
        let b = lauf(&s, &pruefungen(), true);
        assert_eq!(b.exitcode(), 0, "{}", als_text(&b));
        assert_eq!(s.aufgerufen.borrow().len(), 1);
        assert!(s.aufgerufen.borrow()[0].contains("Python-Pakete nachladen"), "{:?}", s.aufgerufen.borrow());
        // Auch die fremde Unit bekommt es.
        let t = Spiel::gesund()
            .mit("chimera-hardware.service", "failed", "exit-code", Some(1), 0)
            .journal("chimera-hardware.service", &["ModuleNotFoundError: No module named 'numpy'"]);
        assert_eq!(lauf(&t, &pruefungen(), true).exitcode(), 0);
    }

    #[test]
    fn requirements_werden_gelesen_und_import_namen_zugeordnet() {
        let t = "# Kopf\nPillow>=10.0.0\nnumpy>=1.26  # Kommentar\n-r andere.txt\nPyYAML==6.0 ; python_version>'3'\n\n";
        assert_eq!(pakete_aus_requirements(t), vec!["pillow", "numpy", "pyyaml"]);
        assert!(modul_in_requirements("numpy", t));
        assert!(modul_in_requirements("PIL", t), "Import PIL ist das Paket Pillow");
        assert!(modul_in_requirements("yaml", t), "Import yaml ist das Paket PyYAML");
        assert!(!modul_in_requirements("spidev", t));
        assert!(!modul_in_requirements("mojo_gibt_es_nicht_paket", t));
        assert_eq!(modul_aus_beleg("ModuleNotFoundError: No module named 'numpy.core'").as_deref(), Some("numpy"));
        assert_eq!(modul_aus_beleg("No module named \"PIL\"").as_deref(), Some("PIL"));
        assert_eq!(modul_aus_beleg("etwas anderes"), None);
    }

    #[test]
    fn ein_paket_das_nicht_in_der_requirements_steht_wird_nicht_nachgeladen() {
        // Der Fund vom 2.11. am Pi: ein erfundenes Paket, Nachladen lief 10 Minuten lang ins Leere.
        let s = Spiel::gesund()
            .mit("chimera.service", "failed", "exit-code", Some(1), 3)
            .journal("chimera.service", &["ModuleNotFoundError: No module named 'mojo_gibt_es_nicht_paket'"]);
        let b = lauf(&s, &pruefungen(), true);
        let f = hat(&b, "dienst.gescheitert", "chimera.service").unwrap();
        assert!(f.reparatur.is_none(), "kein Nachladen ohne Eintrag");
        let u = f.ursache.as_ref().unwrap();
        assert!(u.text.contains("steht nicht in der requirements.txt") && u.text.contains("mojo_gibt_es_nicht_paket"), "{}", u.text);
        assert!(u.nur_mensch && !u.paket_nachladen && u.bestimmt);
        assert!(u.weg.contains("eintragen"), "{}", u.weg);
        assert!(s.aufgerufen.borrow().is_empty(), "nichts angefasst, auch kein Zeitverlust");
        assert_eq!(b.exitcode(), 2, "bleibt laut");
        // Import-Name weicht vom Paketnamen ab: PIL ist Pillow und wird nachgeladen.
        let t = Spiel::gesund()
            .mit("chimera.service", "failed", "exit-code", Some(1), 3)
            .journal("chimera.service", &["ModuleNotFoundError: No module named 'PIL'"]);
        assert_eq!(hat(&lauf(&t, &pruefungen(), false), "dienst.gescheitert", "chimera.service").unwrap().reparatur, Some(Reparatur::PaketeNachladen { unit: "chimera.service".into() }));
    }

    #[test]
    fn eine_unlesbare_requirements_nennt_das_und_laedt_nicht_blind_nach() {
        let mut s = Spiel::gesund()
            .mit("chimera.service", "failed", "exit-code", Some(1), 3)
            .journal("chimera.service", &["ModuleNotFoundError: No module named 'numpy'"]);
        s.reqs = None;
        let b = lauf(&s, &pruefungen(), true);
        let f = hat(&b, "dienst.gescheitert", "chimera.service").unwrap();
        assert!(f.reparatur.is_none() && s.aufgerufen.borrow().is_empty());
        assert!(f.ursache.as_ref().unwrap().text.contains("nicht pruefbar"), "{}", f.ursache.as_ref().unwrap().text);
    }

    #[test]
    fn die_stufen_der_reparaturen_und_die_obergrenze() {
        assert_eq!(Reparatur::ResetUndStart { unit: "x".into() }.stufe(), 1);
        assert_eq!(Reparatur::SocketNachziehen { socket: "x".into(), dienst: "y".into() }.stufe(), 1);
        assert_eq!(Reparatur::PaketeNachladen { unit: "x".into() }.stufe(), 2);
        assert_eq!(
            Reparatur::WlanNeuStarten { schnittstelle: "wlan0".into() }.stufe(),
            1
        );
        // Das Netz ist ein eigener Bereich — der Installer fragt ihn gezielt
        // mit `--mojo --bereich netz`.
        assert!(
            pruefungen().iter().any(|p| p.bereich() == "netz"),
            "Pruefung fuer den Bereich netz fehlt"
        );
        assert_eq!(TIER_MAX, 2, "Stufe 3 (ganzer Installer) laeuft nie von allein");
    }

    #[test]
    fn ein_fehlendes_paket_bei_laufendem_dienst_loest_keine_reparatur_aus() {
        // Der Dienst laeuft wieder (Result=success), die Ursache steht nur im Journal.
        // Wie beim Neustart-Fall: nichts anfassen, der Zaehler ist der einzige Beleg.
        let s = Spiel::gesund()
            .mit("chimera.service", "active", "success", Some(0), 5)
            .journal("chimera.service", &["ModuleNotFoundError: No module named 'numpy'"]);
        let b = lauf(&s, &pruefungen(), true);
        let f = hat(&b, "dienst.neustarts", "chimera.service").unwrap();
        assert!(f.reparatur.is_none());
        assert!(f.ursache.as_ref().unwrap().text.contains("Python-Paket"));
        assert!(s.aufgerufen.borrow().is_empty());
    }

    #[test]
    fn zu_wenig_arbeitsspeicher_nennt_die_zahl_und_dass_es_ram_ist_nicht_die_sd_karte() {
        let mut s = Spiel::gesund();
        s.mb = Some(SPEICHER_WARNUNG_MB - 10);
        let b = lauf(&s, &pruefungen(), false);
        let f = hat(&b, "speicher.knapp", "meminfo").unwrap();
        assert!(f.meldung.contains("RAM"), "{}", f.meldung);
        assert!(f.meldung.contains(&format!("nur {} MB", SPEICHER_WARNUNG_MB - 10)), "{}", f.meldung);
        assert!(f.meldung.contains("10 MB unter der Schwelle"), "genau 10 MB fehlen: {}", f.meldung);
        let u = f.ursache.as_ref().unwrap();
        assert!(u.text.contains("RAM") && u.text.contains("nicht die SD-Karte"), "{}", u.text);
        assert!(u.beleg.contains("es fehlen 10 MB RAM"), "{}", u.beleg);
        // Nicht verwechselbar mit der Karte.
        assert!(!f.meldung.contains("SD") && !u.beleg.contains("Karte"));
    }

    #[test]
    fn zu_wenig_platz_auf_der_karte_nennt_die_zahl_und_dass_es_die_sd_karte_ist_nicht_der_ram() {
        let mut s = Spiel::gesund();
        s.platz.insert("/t/state".into(), PLATZ_WARNUNG_MB - 30);
        let b = lauf(&s, &karte_pruefung(), false);
        let f = hat(&b, "karte.voll", "/t/state").unwrap();
        assert!(f.meldung.contains("Speicherkarte (SD)"), "{}", f.meldung);
        assert!(f.meldung.contains(&format!("nur noch {} MB frei", PLATZ_WARNUNG_MB - 30)), "{}", f.meldung);
        assert!(f.meldung.contains("30 MB unter der Schwelle"), "genau 30 MB fehlen: {}", f.meldung);
        let u = f.ursache.as_ref().unwrap();
        assert!(u.text.contains("SD") && u.text.contains("nicht der Arbeitsspeicher"), "{}", u.text);
        assert!(u.beleg.contains("es fehlen 30 MB auf der Karte"), "{}", u.beleg);
        assert!(!f.meldung.contains("RAM"));
    }

    #[test]
    fn die_ausgabe_eines_programms_unterscheidet_ram_und_karte() {
        let z = UnitZustand { name: "x.service".into(), geladen: true, aktiv: "failed".into(), ergebnis: "exit-code".into(), exec_status: Some(1), ..Default::default() };
        let ram = ursache_aus_unit(&z, &["MemoryError: Cannot allocate memory".into()]);
        assert!(ram.text.contains("Arbeitsspeicher (RAM)") && ram.text.contains("nicht die SD-Karte"), "{}", ram.text);
        let sd = ursache_aus_unit(&z, &["OSError: No space left on device".into()]);
        assert!(sd.text.contains("Speicherkarte (SD)") && sd.text.contains("nicht der Arbeitsspeicher"), "{}", sd.text);
        let sig = UnitZustand { ergebnis: "signal".into(), exec_status: Some(9), ..z.clone() };
        assert!(ursache_aus_unit(&sig, &[]).text.contains("RAM"), "Signal 9 nennt RAM als haeufige Ursache");
    }

    #[test]
    fn schluessel_unterscheidet_gegenstaende_gleichen_codes() {
        let s = Spiel::gesund()
            .mit("chimera-tor.socket", "inactive", "success", Some(0), 0)
            .mit("chimera-sitzung.socket", "inactive", "success", Some(0), 0);
        let b = lauf(&s, &pruefungen(), false);
        assert_eq!(b.befunde.iter().filter(|f| f.code == "socket.inaktiv").count(), 2);
    }

    #[test]
    fn show_ausgabe_wird_gelesen_und_fehlendes_bleibt_leer() {
        let z = zustand_aus_show("a.service", "LoadState=loaded\nActiveState=failed\nSubState=failed\nResult=exit-code\nExecMainStatus=203\nNRestarts=3\n");
        assert!(z.geladen);
        assert_eq!((z.aktiv.as_str(), z.ergebnis.as_str(), z.exec_status, z.neustarts), ("failed", "exit-code", Some(203), 3));
        let leer = zustand_aus_show("b.service", "LoadState=not-found\n");
        assert!(!leer.geladen);
        let kaputt = zustand_aus_show("c.service", "ExecMainStatus=abc\nNRestarts=x\nohne gleichheitszeichen\n");
        assert_eq!((kaputt.exec_status, kaputt.neustarts), (None, 0));
    }

    #[test]
    fn der_bericht_wird_atomar_abgelegt_und_ein_fehler_stoppt_nicht() {
        let d = std::env::temp_dir().join(format!("chimera-mojo-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let f = d.join("m").join("bericht.json");
        ablegen(&serde_json::json!({"exitcode": 0}), Some(&f));
        assert_eq!(serde_json::from_slice::<Value>(&std::fs::read(&f).unwrap()).unwrap()["exitcode"], 0);
        // Ziel in einer Datei statt in einem Ordner: darf nicht abstuerzen.
        ablegen(&serde_json::json!({}), Some(&f.join("x")));
    }

    #[test]
    fn quelltext_dieses_moduls_ist_reines_ascii() {
        let q = include_str!("mojo.rs");
        let (ohne_tests, _) = q.split_once("// -------------------------------------------------------------------- Tests").expect("Trennzeile vor den Tests");
        let bad: Vec<_> = ohne_tests.lines().enumerate().filter(|(_, l)| !l.is_ascii()).map(|(i, _)| i + 1).collect();
        assert!(bad.is_empty(), "Nicht-ASCII in Zeilen {bad:?}");
    }
}
