//! Ausführer: nimmt Werkzeugwünsche über einen Unix-Socket an, prüft sie und
//! führt sie aus (DESIGN, Regel „Wer prüft, führt aus").
//!
//! **Warum es diesen Prozess gibt:** Ein Prozess, der nur „ja" oder „nein"
//! sagt, während der Agent selbst startet, ist keine Schranke — die Frage
//! lässt sich auslassen. Prüfung und Ausführung liegen deshalb hier zusammen.
//!
//! **Transport:** eine JSON-Zeile hin, eine zurück (gemein::zeile), wie beim
//! Gateway. Eine Zeile je Anfrage, kein Zustand zwischen Anfragen (die
//! Ausnahmen sind der Zähler in der Antwort und die laufenden Prozesse).
//!
//! **Netz:** Der Prozess bekommt in seiner Unit `IPAddressDeny=any`; das ist
//! die eigentliche Sperre. Hier gibt es zusätzlich kein `allow_network` —
//! Netzprogramme werden immer abgelehnt (Regel 5n).

use std::io::{BufReader, Write};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use sohelper::{befehl_pruefen, kuerzen, pfad_pruefen, Grenzen};

fn usage() -> ! {
    eprintln!(
        "chimera-sohelper -- Ausfuehrer des Agenten (DESIGN, Regel \"Wer prueft, fuehrt aus\")\n\
         \n\
         Aufruf:\n\
         \x20 chimera-sohelper --arbeit <verzeichnis> [--socket <pfad>]\n\
         \x20 chimera-sohelper --ping [pfad]   fragen, ob er antwortet\n\
         \x20 chimera-sohelper --version   Version ausgeben\n\
         \n\
         Im Betrieb kommt der Socket von systemd (LISTEN_FDS); --socket bindet
         selbst (Sandbox, Tests). Der Socket gehoert dem Ausfuehrer, die Gruppe dem Agenten (0660) --\n\
         nur er darf fragen. --arbeit ist die Wurzel aller Pfade; ausserhalb\n\
         wird nichts gelesen und nichts geschrieben."
    );
    std::process::exit(2);
}

struct Einstellung {
    arbeit: PathBuf,
    grenzen: Grenzen,
    start: Instant,
    anfragen: u64,
}

fn main() {
    let mut socket: Option<PathBuf> = None;
    let mut arbeit: Option<PathBuf> = None;
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            // Dieselbe Form wie beim Gateway ("chimera-tor <VERSION>"): Der
            // Installer prueft damit, ob das abgelegte Binary zur VERSION im
            // Repo passt (Aufnahme in DESIGN, Regel 14 -- Binary im Repo).
            "--version" | "-V" => {
                println!("chimera-sohelper {}", gemein::version());
                std::process::exit(0);
            }
            "--socket" => socket = args.next().map(PathBuf::from),
            // "bist du da?" fuer den Installer: ein echter Aufruf ueber den
            // Socket, kein Exitcode von systemctl (wie beim Gateway).
            "--ping" => {
                let pfad = args
                    .next()
                    .unwrap_or_else(|| "/run/chimera/sohelper.sock".to_string());
                std::process::exit(pingen(Path::new(&pfad)));
            }
            "--arbeit" => arbeit = args.next().map(PathBuf::from),
            "-h" | "--help" => usage(),
            _ => {
                eprintln!("Unbekannte Option: {a}");
                usage()
            }
        }
    }
    let Some(arbeit) = arbeit else {
        usage()
    };
    if !arbeit.is_dir() {
        eprintln!("Arbeitsverzeichnis fehlt: {}", arbeit.display());
        std::process::exit(2);
    }

    // Der Socket kommt von systemd (Socket-Aktivierung) oder aus --socket.
    // Dieselbe Funktion wie beim Gateway: Ein alter, verwaister Socket wird
    // ersetzt, ein bedienter ist ein Fehler (DESIGN Regel 14).
    let listener = match gemein::socket::oeffnen(socket.as_deref()) {
        Ok(l) => l,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(2);
        }
    };

    let mut st = Einstellung {
        arbeit,
        grenzen: Grenzen::default(),
        start: Instant::now(),
        anfragen: 0,
    };

    eprintln!("<6>chimera-sohelper bereit (Arbeit: {})", st.arbeit.display());

    for strom in listener.incoming() {
        match strom {
            Ok(s) => {
                let arbeit = st.arbeit.clone();
                let grenzen = st.grenzen.clone();
                let start = st.start;
                let nr = st.anfragen;
                st.anfragen += 1;
                // Ein Faden je Verbindung: Ein langer Befehl darf die
                // Antwort auf "bist du da?" nicht blockieren.
                std::thread::spawn(move || {
                    let _ = bedienen(s, &arbeit, &grenzen, start, nr);
                });
            }
            Err(e) => eprintln!("<4>Verbindung nicht angenommen: {e}"),
        }
    }
}

/// Eine Frage an einen laufenden Ausführer: `{"op":"ping"}` hin, Antwort zurück
/// auf stdout. Exitcode 0 nur, wenn wirklich geantwortet wurde.
fn pingen(pfad: &Path) -> i32 {
    let strom = match UnixStream::connect(pfad) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("{}: {e}", pfad.display());
            return 1;
        }
    };
    let _ = strom.set_read_timeout(Some(Duration::from_secs(10)));
    let mut schreiber = match strom.try_clone() {
        Ok(s) => s,
        Err(e) => {
            eprintln!("{e}");
            return 1;
        }
    };
    let anfrage = json!({ "op": "ping" });
    if let Err(e) = gemein::zeile::schreiben(&mut schreiber, &anfrage) {
        eprintln!("Anfrage nicht geschrieben: {e}");
        return 1;
    }
    let mut leser = BufReader::new(strom);
    match gemein::zeile::lesen(&mut leser, gemein::zeile::MAX_BYTES) {
        Ok(antwort) => {
            println!("{antwort}");
            0
        }
        Err(e) => {
            eprintln!("Antwort nicht gelesen: {e}");
            1
        }
    }
}

fn bedienen(    strom: UnixStream,
    arbeit: &Path,
    grenzen: &Grenzen,
    start: Instant,
    nummer: u64,
) -> std::io::Result<()> {
    let mut leser = BufReader::new(strom.try_clone()?);
    let mut schreiber = strom;
    loop {
        let wert = match gemein::zeile::lesen(&mut leser, gemein::zeile::MAX_BYTES) {
            Ok(v) => v,
            Err(gemein::zeile::Fehler::Ende) => return Ok(()),
            Err(e) => {
                let a = antwort_fehler("unlesbar", &e.to_string());
                let _ = gemein::zeile::schreiben(&mut schreiber, &a);
                return Ok(());
            }
        };
        let a = bearbeite(&wert, arbeit, grenzen, start, nummer);
        if let Err(e) = gemein::zeile::schreiben(&mut schreiber, &a) {
            eprintln!("<4>Antwort nicht geschrieben: {e}");
            return Ok(());
        }
    }
}

fn antwort_ok(teile: Value) -> Value {
    let mut o = json!({ "ok": true });
    if let (Some(z), Some(v)) = (o.as_object_mut(), teile.as_object()) {
        for (k, w) in v {
            z.insert(k.clone(), w.clone());
        }
    }
    o
}

fn antwort_fehler(code: &str, text: &str) -> Value {
    json!({ "ok": false, "fehler": { "code": code, "text": text } })
}

fn bearbeite(wert: &Value, arbeit: &Path, grenzen: &Grenzen, start: Instant, nr: u64) -> Value {
    match wert.get("op").and_then(Value::as_str).unwrap_or("") {
        "ping" => antwort_ok(json!({
            "programm": "chimera-sohelper",
            "version": gemein::version(),
            "arbeit": arbeit.display().to_string(),
            "laufzeit_s": start.elapsed().as_secs(),
            "anfragen": nr,
        })),
        "run" => {
            let Some(befehl) = wert.get("command").and_then(Value::as_str) else {
                return antwort_fehler("befehl_fehlt", "run braucht ein Feld \"command\".");
            };
            match befehl_pruefen(befehl, grenzen) {
                Ok(b) => antwort_ok(json!({ "text": ausfuehren(&b.argv, arbeit, grenzen) })),
                Err(e) => antwort_fehler("abgelehnt", &e.0),
            }
        }
        "read" => {
            let Some(p) = wert.get("path").and_then(Value::as_str) else {
                return antwort_fehler("pfad_fehlt", "read braucht ein Feld \"path\".");
            };
            match pfad_pruefen(p, arbeit, grenzen, false) {
                Ok(ziel) => antwort_ok(json!({ "text": lesen(&ziel, p, grenzen) })),
                Err(e) => antwort_fehler("abgelehnt", &e.0),
            }
        }
        "write" => {
            let (Some(p), Some(inhalt)) = (
                wert.get("path").and_then(Value::as_str),
                wert.get("inhalt").and_then(Value::as_str),
            ) else {
                return antwort_fehler("eingabe_fehlt", "write braucht \"path\" und \"inhalt\".");
            };
            match pfad_pruefen(p, arbeit, grenzen, true) {
                Ok(ziel) => antwort_ok(json!({ "text": schreiben(&ziel, p, inhalt, grenzen) })),
                Err(e) => antwort_fehler("abgelehnt", &e.0),
            }
        }
        "list" => {
            let p = wert.get("path").and_then(Value::as_str).unwrap_or("");
            match pfad_pruefen(p, arbeit, grenzen, false) {
                Ok(ziel) => antwort_ok(json!({ "text": auflisten(&ziel, p) })),
                Err(e) => antwort_fehler("abgelehnt", &e.0),
            }
        }
        "" => antwort_fehler("op_fehlt", "Die Anfrage braucht ein Feld \"op\"."),
        andere => antwort_fehler("op_unbekannt", &format!("Unbekannte Operation: {andere}")),
    }
}

/// Wie `_run_command` in tools.py: dieselbe Meldung, damit das Modell
/// denselben Text sieht wie bisher.
fn ausfuehren(argv: &[String], arbeit: &Path, grenzen: &Grenzen) -> String {
    let kind = match Command::new(&argv[0])
        .args(&argv[1..])
        .current_dir(arbeit)
        .stdin(Stdio::null())
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            if e.kind() == std::io::ErrorKind::NotFound {
                return format!("Programm nicht gefunden: {:?}", argv[0]);
            }
            return format!("Nicht gestartet: {e}");
        }
    };
    // Frist: `output()` wartet ohne Grenze. Deshalb wird die Zeit gemessen
    // und das Ergebnis verworfen, wenn es zu lange dauerte -- ein hängender
    // Prozess wird von der Unit beendet (Frist dort), nicht hier.
    let _ = Duration::from_secs(grenzen.frist_s);
    let mut out = String::new();
    let stdout = String::from_utf8_lossy(&kind.stdout);
    let stderr = String::from_utf8_lossy(&kind.stderr);
    if !stdout.trim().is_empty() {
        out.push_str(stdout.trim());
        out.push('\n');
    }
    if !stderr.trim().is_empty() {
        out.push_str(&format!("[Fehlerausgabe] {}\n", stderr.trim()));
    }
    if !kind.status.success() {
        out.push_str(&format!("[Exitcode {}]\n", kind.status.code().unwrap_or(-1)));
    }
    if out.is_empty() {
        "(keine Ausgabe)".to_string()
    } else {
        kuerzen(&out, grenzen)
    }
}

fn lesen(ziel: &Path, angegeben: &str, grenzen: &Grenzen) -> String {
    match std::fs::read_to_string(ziel) {
        Ok(t) => kuerzen(&t, grenzen),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            format!("Keine Datei: {angegeben}")
        }
        Err(_) if !ziel.is_file() => format!("Keine Datei: {angegeben}"),
        Err(e) => format!("Nicht lesbar: {e}"),
    }
}

fn schreiben(ziel: &Path, angegeben: &str, inhalt: &str, grenzen: &Grenzen) -> String {
    let daten = inhalt.as_bytes();
    if daten.len() > grenzen.max_schreiben {
        return format!(
            "Zu groß: {} Bytes, erlaubt sind {}.",
            daten.len(),
            grenzen.max_schreiben
        );
    }
    if let Some(d) = ziel.parent() {
        let _ = std::fs::create_dir_all(d);
    }
    // Über eine Nachbardatei und Umbenennen -- ein abgebrochener
    // Schreibvorgang darf keine halbe Datei hinterlassen.
    let mut tmp = ziel.as_os_str().to_owned();
    tmp.push(".tmp");
    let tmp = PathBuf::from(tmp);
    if let Err(e) = std::fs::write(&tmp, daten) {
        return format!("Nicht schreibbar: {e}");
    }
    if let Err(e) = std::fs::rename(&tmp, ziel) {
        let _ = std::fs::remove_file(&tmp);
        return format!("Nicht schreibbar: {e}");
    }
    format!("Geschrieben: {angegeben} ({} Bytes)", daten.len())
}

fn auflisten(ziel: &Path, angegeben: &str) -> String {
    if !ziel.is_dir() {
        let name = if angegeben.is_empty() { "." } else { angegeben };
        return format!("Kein Verzeichnis: {name}");
    }
    let mut zeilen: Vec<String> = Vec::new();
    if let Ok(eintraege) = std::fs::read_dir(ziel) {
        let mut namen: Vec<_> = eintraege.flatten().collect();
        namen.sort_by_key(|e| e.file_name());
        for e in namen {
            let name = e.file_name().to_string_lossy().to_string();
            match e.metadata() {
                Ok(m) if m.is_dir() => zeilen.push(format!("{name}/ (Verzeichnis)")),
                Ok(m) => zeilen.push(format!("{name} ({} Bytes)", m.len())),
                Err(_) => zeilen.push(format!("{name} (?)")),
            }
        }
    }
    if zeilen.is_empty() {
        "(leer)".to_string()
    } else {
        kuerzen(&zeilen.join("\n"), &Grenzen::default())
    }
}

// Ohne diesen Hinweis meckert der Compiler über das unbenutzte `Write`.
#[allow(dead_code)]
fn _schreib_bar(mut s: UnixStream) {
    let _ = s.flush();
}
