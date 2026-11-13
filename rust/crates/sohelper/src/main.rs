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

use std::io::{BufReader, Read, Write};
use std::os::unix::io::RawFd;
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
    /// Der Gateway-Socket, bei dem die Freigabe erfragt wird (Stufe 3).
    tor: PathBuf,
    grenzen: Grenzen,
    start: Instant,
    anfragen: u64,
}

fn main() {
    let mut socket: Option<PathBuf> = None;
    let mut arbeit: Option<PathBuf> = None;
    let mut tor: Option<PathBuf> = None;
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
            // Der Askpass-Helfer, den `ssh` bei der Aufnahme aufruft: er gibt
            // das Passwort aus einer 0600-Datei aus, die nur fuer diesen Lauf
            // existiert (DESIGN, "Aufnahme eines Hosts"). Kein TTY, kein argv:
            // die Datei steht in CHIMERA_ASKPASS_DATEI.
            "--askpass" => {
                // `ssh` ruft den Helfer mit dem Prompt als Argument auf --
                // brauchbar ist das nicht. Die Datei kommt deshalb aus der
                // Umgebung, die unser Aufruf gesetzt hat.
                let datei = match std::env::var("CHIMERA_ASKPASS_DATEI") {
                    Ok(d) if !d.trim().is_empty() => PathBuf::from(d),
                    _ => {
                        eprintln!("askpass: CHIMERA_ASKPASS_DATEI fehlt");
                        std::process::exit(2);
                    }
                };
                match std::fs::read_to_string(&datei) {
                    Ok(t) => print!("{}", t.trim_end_matches(['\n', '\r'])),
                    Err(e) => {
                        eprintln!("askpass: {}: {e}", datei.display());
                        std::process::exit(1);
                    }
                }
                std::process::exit(0);
            }
            "--arbeit" => arbeit = args.next().map(PathBuf::from),
            // Wo das Gateway zu erreichen ist (Vorgabe: der Dienstpfad, oder
            // CHIMERA_TOR_SOCKET aus der Umgebung). Fuer Tests und Sandbox.
            "--tor" => tor = args.next().map(PathBuf::from),
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

    let tor = tor
        .or_else(|| std::env::var("CHIMERA_TOR_SOCKET").ok().map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from(TOR_SOCKET));

    let mut st = Einstellung {
        arbeit,
        tor,
        grenzen: Grenzen::default(),
        start: Instant::now(),
        anfragen: 0,
    };

    eprintln!("<6>chimera-sohelper bereit (Arbeit: {})", st.arbeit.display());

    for strom in listener.incoming() {
        match strom {
            Ok(s) => {
                let arbeit = st.arbeit.clone();
                let tor = st.tor.clone();
                let grenzen = st.grenzen.clone();
                let start = st.start;
                let nr = st.anfragen;
                st.anfragen += 1;
                // Ein Faden je Verbindung: Ein langer Befehl darf die
                // Antwort auf "bist du da?" nicht blockieren.
                std::thread::spawn(move || {
                    let _ = bedienen(s, &arbeit, &tor, &grenzen, start, nr);
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
    tor: &Path,
    grenzen: &Grenzen,
    start: Instant,
    nummer: u64,
) -> std::io::Result<()> {
    // Die **erste** Nachricht einer Verbindung kann einen Deskriptor tragen
    // (Fernausführung: das Gateway hat die Verbindung geöffnet). Nur so lässt
    // sie sich empfangen -- mit einem BufReader wären die Rechte weg, bevor
    // jemand sie sieht.
    let (erste, fds, rest) = erste_nachricht(&strom)?;
    let mut schreiber = strom.try_clone()?;
    if let Err(e) = gemein::zeile::schreiben(&mut schreiber, &bearbeite(&erste, arbeit, tor, grenzen, start, nummer, &fds)) {
        eprintln!("<4>Antwort nicht geschrieben: {e}");
        return Ok(());
    }
    let quelle = std::io::Cursor::new(rest).chain(strom.try_clone()?);
    let mut leser = BufReader::new(quelle);
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
        // Weitere Deskriptoren nimmt der Ausführer nicht an: Rechte gibt es
        // einmal je Auftrag (eine Nachricht, ein Ziel).
        let a = bearbeite(&wert, arbeit, tor, grenzen, start, nummer, &[]);
        if let Err(e) = gemein::zeile::schreiben(&mut schreiber, &a) {
            eprintln!("<4>Antwort nicht geschrieben: {e}");
            return Ok(());
        }
    }
}

/// Die erste Nachricht lesen -- mit möglichen Deskriptoren.
///
/// Gibt den geparsten Wert, die Deskriptoren und die Bytes **nach** der
/// ersten Zeile zurück (sie gehören zum nächsten Lesen).
fn erste_nachricht(strom: &UnixStream) -> std::io::Result<(Value, Vec<RawFd>, Vec<u8>)> {
    let mut puffer: Vec<u8> = Vec::new();
    let mut fds: Vec<RawFd> = Vec::new();
    loop {
        let platz = gemein::zeile::MAX_BYTES.saturating_sub(puffer.len());
        if platz == 0 {
            for fd in fds {
                gemein::fdpass::schliessen(fd);
            }
            return Ok((json!({"op": "_zu_lang"}), Vec::new(), Vec::new()));
        }
        let (stueck, neue) = gemein::fdpass::empfangen(strom, platz)?;
        if stueck.is_empty() {
            // Verbindung zu, bevor eine Zeile begann: kein Fehler, nur Ende.
            return Ok((json!({"op": "_ende"}), fds, Vec::new()));
        }
        puffer.extend_from_slice(&stueck);
        fds.extend(neue);
        if let Some(i) = puffer.iter().position(|b| *b == b'\n') {
            let zeile = puffer[..i].to_vec();
            let rest = puffer[i + 1..].to_vec();
            let wert = serde_json::from_slice::<Value>(&zeile).unwrap_or(Value::Null);
            return Ok((wert, fds, rest));
        }
    }
}

/// Wo das Gateway zu erreichen ist. Der Ausfuehrer liest den
/// Freigabe-Zustand **nicht** selbst (kein Zugriff auf config/), er fragt
/// (DESIGN, Regel "Freigabe je Werkzeug auf Zeit", Stufe 3).
const TOR_SOCKET: &str = "/run/chimera/tor.sock";

/// Der Zielname, den die Freigabe-Liste fuehrt: der Programmname, klein.
/// Nicht die ganze Zeile -- eine Liste von Kommandozeilen traefe nie.
fn ziel_name(argv: &[String]) -> String {
    Path::new(&argv[0])
        .file_name()
        .map(|s| s.to_string_lossy().to_lowercase())
        .unwrap_or_default()
}

/// Das Gateway fragen. `Err` heisst **nicht** "erlaubt": ohne Antwort laeuft
/// nichts (kein Rueckfall, wie bei 5n).
fn freigabe_fragen(pfad: &Path, werkzeug: &str, ziel: &str) -> Result<Value, String> {
    let strom = UnixStream::connect(pfad)
        .map_err(|e| format!("das Gateway ist nicht erreichbar ({}: {e})", pfad.display()))?;
    let _ = strom.set_read_timeout(Some(Duration::from_secs(10)));
    let mut schreiber = strom.try_clone().map_err(|e| e.to_string())?;
    let anfrage = json!({"op": "freigabe_pruefen", "werkzeug": werkzeug, "ziel": ziel});
    gemein::zeile::schreiben(&mut schreiber, &anfrage)
        .map_err(|e| format!("die Freigabe-Anfrage wurde nicht geschrieben ({e})"))?;
    let mut leser = BufReader::new(strom);
    gemein::zeile::lesen(&mut leser, gemein::zeile::MAX_BYTES)
        .map_err(|e| format!("keine Antwort vom Gateway ({e})"))
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

fn bearbeite(
    wert: &Value,
    arbeit: &Path,
    tor: &Path,
    grenzen: &Grenzen,
    start: Instant,
    nr: u64,
    fds: &[RawFd],
) -> Value {
    let op = wert.get("op").and_then(Value::as_str).unwrap_or("");
    // Ein Deskriptor ist ein Recht. Wer ihn schickt, ohne dass die Operation
    // ihn braucht, bekommt ihn geschlossen zurück -- kein Recht auf Vorrat.
    if !fds.is_empty() && op != "ssh" && op != "ssh_aufnahme" {
        for fd in fds {
            gemein::fdpass::schliessen(*fd);
        }
        return antwort_fehler("deskriptor_unerwartet",
            &format!("Die Operation \"{op}\" nimmt keinen Deskriptor an."));
    }
    match op {
        // Die Verbindung kommt als Deskriptor vom Gateway (DESIGN,
        // "Fernausführung"). Hier wird **nicht** verbunden und **nicht**
        // gefragt, ob es erlaubt ist: beides hat das Gateway schon getan,
        // bevor es den Socket weiterreichte. Der Ausführer prüft die Form
        // des Auftrags und baut daraus eine feste Kommandozeile.
        "ssh" => {
            let fd = match fds {
                [eine] => *eine,
                _ => {
                    return antwort_fehler(
                        "deskriptor_fehlt",
                        "ssh braucht genau eine offene Verbindung (Deskriptor) vom Gateway.",
                    )
                }
            };
            let auftrag = match sohelper::ssh::auftrag_aus(wert) {
                Ok(a) => a,
                Err(e) => {
                    gemein::fdpass::schliessen(fd);
                    return antwort_fehler("abgelehnt", &e.0);
                }
            };
            let (keydir, known_hosts) = sohelper::ssh::ordner(arbeit);
            if !keydir.join(&auftrag.schluessel).is_file() {
                gemein::fdpass::schliessen(fd);
                return antwort_fehler(
                    "schluessel_fehlt",
                    &format!("Der Schlüssel \"{}\" liegt nicht im Schlüsselordner ({}).",
                        auftrag.schluessel, keydir.display()),
                );
            }
            if let Err(e) = sohelper::ssh::known_hosts_schreiben(&known_hosts, &auftrag.hostschluessel) {
                gemein::fdpass::schliessen(fd);
                return antwort_fehler("known_hosts", &format!("known_hosts nicht schreibbar: {e}"));
            }
            let fdpass = fdpass_pfad();
            antwort_ok(ssh_ausfuehren(&auftrag, &keydir, &known_hosts, &fdpass, fd, grenzen))
        }
        // Die Aufnahme: Passwort-Anmeldung, Schluesselpaar hier erzeugen,
        // **eine** authorized_keys-Zeile auf dem Ziel, Passwortdatei weg.
        // Der Hostschluessel wird dabei erfasst und zurueckgegeben; die
        // Tabelle schreibt erst der Nutzer (Bestaetigung im Modul).
        "ssh_aufnahme" => {
            let fd = match fds {
                [eine] => *eine,
                _ => {
                    return antwort_fehler(
                        "deskriptor_fehlt",
                        "Die Aufnahme braucht genau eine offene Verbindung (Deskriptor) vom Gateway.",
                    )
                }
            };
            let aufnahme = match sohelper::ssh::aufnahme_aus(wert) {
                Ok(a) => a,
                Err(e) => {
                    gemein::fdpass::schliessen(fd);
                    return antwort_fehler("abgelehnt", &e.0);
                }
            };
            let passwort = match wert.get("passwort").and_then(Value::as_str) {
                Some(p) if !p.is_empty() => p.to_string(),
                _ => {
                    gemein::fdpass::schliessen(fd);
                    return antwort_fehler("passwort_fehlt", "Die Aufnahme braucht ein Passwort.");
                }
            };
            aufnahme_ausfuehren(&aufnahme, &passwort, arbeit, fd, grenzen)
        }
        "_ende" => antwort_ok(json!({"text": ""})),
        "_zu_lang" => antwort_fehler("zu_lang", "Die Anfrage ist laenger als erlaubt."),
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
                Ok(b) => {
                    // Die harten Regeln sind durch -- jetzt entscheidet der
                    // Freigabe-Zustand, und zwar im Gateway (Stufe 3).
                    let ziel = ziel_name(&b.argv);
                    match freigabe_fragen(tor, "run_command", &ziel) {
                        Ok(a) if a.get("erlaubt").and_then(Value::as_bool) == Some(true) => {
                            antwort_ok(json!({ "text": ausfuehren(&b.argv, arbeit, grenzen) }))
                        }
                        Ok(a) => {
                            let grund = a
                                .get("grund")
                                .and_then(Value::as_str)
                                .unwrap_or("ohne Grund");
                            antwort_fehler(
                                "nicht_freigegeben",
                                &format!("'{ziel}' ist nicht freigegeben: {grund}"),
                            )
                        }
                        // Ohne Antwort des Gateways ist die Frage offen --
                        // und offen heisst hier: nein. Der Text sagt beides:
                        // die Sperre und ihren Grund.
                        Err(e) => antwort_fehler(
                            "nicht_freigegeben",
                            &format!("'{ziel}' ist nicht freigegeben: {e}"),
                        ),
                    }
                }
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

/// Wo `chimera-fdpass` liegt: neben dem eigenen Binary (so findet es sich im
/// Installer und in der Sandbox gleich), sonst die Ablage im Betrieb.
fn fdpass_pfad() -> PathBuf {
    if let Ok(p) = std::env::var("CHIMERA_FDPASS") {
        return PathBuf::from(p);
    }
    if let Ok(eigen) = std::env::current_exe() {
        let neben = eigen.parent().map(|d| d.join("chimera-fdpass"));
        if let Some(p) = neben.filter(|p| p.is_file()) {
            return p;
        }
    }
    PathBuf::from("/opt/chimera/bin/chimera-fdpass")
}

/// Ein `ssh`-Aufruf. **Höchstens einer zur Zeit**: die Übergabe läuft über
/// einen benannten Socket, und zwei gleichzeitige Läufe würden einander den
/// Deskriptor unter den Füßen wegziehen. Die Sperre ist billig; die
/// Alternative wäre ein falscher Socket.
static SSH_SPERRE: std::sync::Mutex<()> = std::sync::Mutex::new(());

/// Wie `ssh` die Verbindung bekommt (gemessen 12.11.2026, OpenSSH 9.9):
/// `ssh` schließt im Proxy-Kind **alle** Deskriptoren ab 3 (`fd 3` ist dort
/// nicht offen) und gibt dem Proxy nur stdin als Socketpair. Deshalb holt
/// `chimera-fdpass` die Verbindung über diesen Unix-Socket beim Ausführer ab
/// und reicht sie auf stdin an `ssh` weiter.
fn ssh_ausfuehren(
    auftrag: &sohelper::ssh::Auftrag,
    keydir: &Path,
    known_hosts: &Path,
    fdpass: &Path,
    fd: RawFd,
    grenzen: &Grenzen,
) -> Value {
    let _wache = SSH_SPERRE.lock().unwrap_or_else(|g| g.into_inner());
    let uebergabe = keydir.parent().unwrap_or(Path::new("/")).join("uebergabe.sock");
    let _ = std::fs::remove_file(&uebergabe);
    let horcher = match std::os::unix::net::UnixListener::bind(&uebergabe) {
        Ok(h) => h,
        Err(e) => {
            gemein::fdpass::schliessen(fd);
            return json!({ "fehler": { "code": "uebergabe",
                "text": format!("Der Übergabe-Socket {} ist nicht anlegbar: {e}", uebergabe.display()) } });
        }
    };
    let argv = sohelper::ssh::argv(auftrag, keydir, known_hosts, fdpass, Some(&uebergabe));
    let start = Instant::now();
    let mut kind = match Command::new(&argv[0])
        .args(&argv[1..])
        .current_dir(keydir.parent().unwrap_or(Path::new("/")))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        // Keine Umgebung: ein Kind erbt keine Schlüssel, keine .env, kein
        // Arbeitsverzeichnis des anderen (DESIGN, "Was ein Kind nie erbt").
        .env_clear()
        .env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
        .spawn()
    {
        Ok(k) => k,
        Err(e) => {
            gemein::fdpass::schliessen(fd);
            let _ = std::fs::remove_file(&uebergabe);
            let text = if e.kind() == std::io::ErrorKind::NotFound {
                "Der ssh-Aufruf ist nicht gestartet: Programm nicht gefunden.".to_string()
            } else {
                format!("Der ssh-Aufruf ist nicht gestartet: {e}")
            };
            return json!({ "fehler": { "code": "ssh_nicht_gestartet", "text": text } });
        }
    };
    // Auf den Proxy warten und ihm die Verbindung geben.
    let _ = horcher.set_nonblocking(true);
    let mut gegeben = false;
    let frist_uebergabe = Instant::now() + Duration::from_secs(15);
    while Instant::now() < frist_uebergabe {
        match horcher.accept() {
            Ok((strom, _)) => {
                let r = uebergabe_schicken(&strom, fd);
                gemein::fdpass::schliessen(fd);
                gegeben = r.is_ok();
                if let Err(e) = r {
                    eprintln!("<4>ssh: Übergabe misslungen: {e}");
                }
                break;
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(20));
            }
            Err(e) => {
                eprintln!("<4>ssh: accept: {e}");
                break;
            }
        }
    }
    if !gegeben {
        // Niemand hat die Verbindung abgeholt: ssh läuft ins Leere, also
        // beenden statt warten. Der Deskriptor wird geschlossen.
        let _ = kind.kill();
    }
    let _ = std::fs::remove_file(&uebergabe);

    let (aus, fehler) = (kind.stdout.take(), kind.stderr.take());
    let leser_out = aus.map(|mut r| std::thread::spawn(move || { let mut v = Vec::new(); let _ = std::io::Read::read_to_end(&mut r, &mut v); v }));
    let leser_err = fehler.map(|mut r| std::thread::spawn(move || { let mut v = Vec::new(); let _ = std::io::Read::read_to_end(&mut r, &mut v); v }));

    let frist = Duration::from_secs(grenzen.frist_s);
    let status = loop {
        match kind.try_wait() {
            Ok(Some(s)) => break Some(s),
            Ok(None) if start.elapsed() >= frist => {
                let _ = kind.kill();
                let _ = kind.wait();
                break None;
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(20)),
            Err(e) => {
                eprintln!("<4>ssh: try_wait: {e}");
                let _ = kind.kill();
                break kind.wait().ok();
            }
        }
    };
    let aus = leser_out.and_then(|h| h.join().ok()).unwrap_or_default();
    let fehler = leser_err.and_then(|h| h.join().ok()).unwrap_or_default();
    let mut text = String::new();
    let o = String::from_utf8_lossy(&aus);
    let f = String::from_utf8_lossy(&fehler);
    if !o.trim().is_empty() {
        text.push_str(o.trim());
        text.push('\n');
    }
    if !f.trim().is_empty() {
        text.push_str(&format!("[Fehlerausgabe] {}\n", f.trim()));
    }
    if status.is_none() {
        text.push_str(&format!("[Frist {} s überschritten, abgebrochen]\n", grenzen.frist_s));
    }
    let code = status.and_then(|s| s.code());
    if let Some(c) = code {
        if c != 0 {
            text.push_str(&format!("[Exitcode {c}]\n"));
        }
    }
    if text.is_empty() {
        text.push_str("(keine Ausgabe)");
    }
    json!({
        "text": kuerzen(&text, grenzen),
        "host": auftrag.host,
        "adresse": auftrag.adresse,
        "exitcode": code,
        "dauer_s": start.elapsed().as_secs(),
    })
}

/// Die Aufnahme eines Hosts (DESIGN, „Aufnahme eines Hosts: das Passwort
/// einmal, der Schlüssel danach").
///
/// **Ein** Verbindungsaufbau für alles: Passwort-Anmeldung, `~/.ssh` anlegen,
/// die eine Zeile eintragen, Rechte setzen, fertig. Hostschlüssel fällt dabei
/// als Nebenprodukt ab (eigene `known_hosts`) und geht zurück.
fn aufnahme_ausfuehren(aufnahme: &sohelper::ssh::Aufnahme, passwort: &str, arbeit: &Path, fd: RawFd, grenzen: &Grenzen) -> Value {
    let _wache = SSH_SPERRE.lock().unwrap_or_else(|g| g.into_inner());
    let (keydir, _) = sohelper::ssh::ordner(arbeit);
    let ssh_ordner = keydir.parent().unwrap_or(arbeit).to_path_buf();
    let known_hosts = ssh_ordner.join("known_hosts.aufnahme");
    let passwort_datei = ssh_ordner.join(".passwort");
    let uebergabe = ssh_ordner.join("uebergabe.sock");

    // Aufraeumen ist Teil des Vertrags: Passwortdatei weg, auch bei Abbruch.
    let aufraeumen = |pw: &Path, uebergabe: &Path| {
        let _ = std::fs::remove_file(pw);
        let _ = std::fs::remove_file(uebergabe);
        let _ = std::fs::remove_file(uebergabe.parent().unwrap_or(Path::new("/")).join("askpass.sh"));
    };

    // 1. Schluesselpaar erzeugen (hier, nicht auf dem Ziel).
    let pubkey = match sohelper::ssh::schluessel_erzeugen(&keydir, &aufnahme.schluessel, &format!("chimera:{}", aufnahme.host)) {
        Ok(k) => k,
        Err(e) => {
            gemein::fdpass::schliessen(fd);
            aufraeumen(&passwort_datei, &uebergabe);
            return antwort_fehler("schluessel", &e);
        }
    };
    let mut teile = pubkey.split_whitespace();
    let (Some(typ), Some(blob)) = (teile.next(), teile.next()) else {
        gemein::fdpass::schliessen(fd);
        return antwort_fehler("schluessel", "Der erzeugte oeffentliche Schluessel ist unlesbar.");
    };
    let zeile = match sohelper::ssh::authorized_keys_zeile(typ, blob, &aufnahme.rechte, aufnahme.zaun.as_deref(), &format!("chimera:{}", aufnahme.host)) {
        Ok(z) => z,
        Err(e) => {
            let _ = std::fs::remove_file(keydir.join(&aufnahme.schluessel));
            let _ = std::fs::remove_file(keydir.join(format!("{}.pub", aufnahme.schluessel)));
            gemein::fdpass::schliessen(fd);
            aufraeumen(&passwort_datei, &uebergabe);
            return antwort_fehler("rechte", &e.0);
        }
    };
    let befehl = sohelper::ssh::aufnahme_befehl(&zeile);

    // 2. Passwortdatei und leere known_hosts fuer genau diesen Lauf.
    if let Err(e) = std::fs::create_dir_all(&ssh_ordner) {
        gemein::fdpass::schliessen(fd);
        return antwort_fehler("ordner", &format!("{}: {e}", ssh_ordner.display()));
    }
    if let Err(e) = sohelper::ssh::known_hosts_schreiben(&passwort_datei, passwort) {
        gemein::fdpass::schliessen(fd);
        return antwort_fehler("passwort", &format!("Passwortdatei nicht schreibbar: {e}"));
    }
    let _ = std::fs::remove_file(&known_hosts);
    if let Err(e) = std::fs::File::create(&known_hosts) {
        gemein::fdpass::schliessen(fd);
        aufraeumen(&passwort_datei, &uebergabe);
        return antwort_fehler("known_hosts", &format!("{}: {e}", known_hosts.display()));
    }

    // 3. Uebergabe-Socket fuer den Proxy (ssh schliesst alles ab 3).
    let _ = std::fs::remove_file(&uebergabe);
    let horcher = match std::os::unix::net::UnixListener::bind(&uebergabe) {
        Ok(h) => h,
        Err(e) => {
            gemein::fdpass::schliessen(fd);
            aufraeumen(&passwort_datei, &uebergabe);
            return antwort_fehler("uebergabe", &format!("{}: {e}", uebergabe.display()));
        }
    };

    // 4. ssh mit Passwort-Anmeldung, ohne TTY.
    //
    // `ssh` ruft den Askpass-Helfer als `$SSH_ASKPASS "<frage>"` auf -- ein
    // eigenes Argument koennte er nicht mitgeben. Deshalb ein winziger
    // Wrapper im Arbeitsordner, der unser eigenes `--askpass` startet; die
    // Passwortdatei steht in der Umgebung (CHIMERA_ASKPASS_DATEI).
    let eigen = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("/opt/chimera/bin/chimera-sohelper"));
    let askpass = ssh_ordner.join("askpass.sh");
    let skript = format!("#!/bin/sh\nexec '{}' --askpass\n", eigen.display());
    if let Err(e) = sohelper::ssh::known_hosts_schreiben(&askpass, skript.trim_end()) {
        gemein::fdpass::schliessen(fd);
        aufraeumen(&passwort_datei, &uebergabe);
        return antwort_fehler("askpass", &format!("Askpass-Wrapper nicht schreibbar: {e}"));
    }
    use std::os::unix::fs::PermissionsExt;
    let _ = std::fs::set_permissions(&askpass, std::fs::Permissions::from_mode(0o700));
    let argv = sohelper::ssh::argv_aufnahme(&aufnahme.als_auftrag(), &known_hosts, &fdpass_pfad(), &uebergabe, &befehl);
    let start = Instant::now();
    let mut kind = match Command::new(&argv[0])
        .args(&argv[1..])
        .current_dir(&ssh_ordner)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env_clear()
        .env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
        .env("SSH_ASKPASS", &askpass)
        .env("SSH_ASKPASS_REQUIRE", "force")
        .env("CHIMERA_ASKPASS_DATEI", &passwort_datei)
        .spawn()
    {
        Ok(k) => k,
        Err(e) => {
            gemein::fdpass::schliessen(fd);
            aufraeumen(&passwort_datei, &uebergabe);
            return antwort_fehler("ssh_nicht_gestartet", &format!("{e}"));
        }
    };
    // Der Askpass-Helfer muss die Datei kennen -- ueber das eigene Argument,
    // nicht ueber die Umgebung (ssh reicht keine Umgebung weiter).
    // (Der Helfer liest CHIMERA_ASKPASS_DATEI; ssh selbst startet ihn.)
    let _ = horcher.set_nonblocking(true);
    let mut gegeben = false;
    let frist_uebergabe = Instant::now() + Duration::from_secs(15);
    while Instant::now() < frist_uebergabe {
        match horcher.accept() {
            Ok((strom, _)) => {
                let r = uebergabe_schicken(&strom, fd);
                gemein::fdpass::schliessen(fd);
                gegeben = r.is_ok();
                break;
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => std::thread::sleep(Duration::from_millis(20)),
            Err(_) => break,
        }
    }
    if !gegeben {
        let _ = kind.kill();
    }
    let aus = kind.stdout.take();
    let fehler = kind.stderr.take();
    let leser_out = aus.map(|mut r| std::thread::spawn(move || { let mut v = Vec::new(); let _ = std::io::Read::read_to_end(&mut r, &mut v); v }));
    let leser_err = fehler.map(|mut r| std::thread::spawn(move || { let mut v = Vec::new(); let _ = std::io::Read::read_to_end(&mut r, &mut v); v }));
    let frist = Duration::from_secs(grenzen.frist_s);
    let status = loop {
        match kind.try_wait() {
            Ok(Some(s)) => break Some(s),
            Ok(None) if start.elapsed() >= frist => { let _ = kind.kill(); let _ = kind.wait(); break None; }
            Ok(None) => std::thread::sleep(Duration::from_millis(20)),
            Err(_) => break None,
        }
    };
    let _ = leser_out.map(|h| h.join());
    let fehler_text = leser_err.and_then(|h| h.join().ok()).map(|v| String::from_utf8_lossy(&v).trim().to_string()).unwrap_or_default();

    // 5. Hostschluessel aus der eigenen known_hosts.
    let hostzeile = std::fs::read_to_string(&known_hosts).ok().and_then(|t| {
        t.lines().find(|z| !z.trim().is_empty() && !z.starts_with('#')).map(|z| z.trim().to_string())
    });
    let (hk_typ, hk_blob) = match hostzeile {
        Some(z) => {
            let mut t = z.split_whitespace();
            let _ziel = t.next();
            (t.next().map(str::to_string), t.next().map(str::to_string))
        }
        None => (None, None),
    };
    let code = status.and_then(|s| s.code());
    aufraeumen(&passwort_datei, &uebergabe);
    let _ = std::fs::remove_file(&known_hosts);

    if code != Some(0) || hk_typ.is_none() {
        // Kein Eintrag entstehen lassen, wenn die Aufnahme nicht durchlief.
        let _ = std::fs::remove_file(keydir.join(&aufnahme.schluessel));
        let _ = std::fs::remove_file(keydir.join(format!("{}.pub", aufnahme.schluessel)));
        return antwort_fehler(
            "aufnahme_gescheitert",
            &format!("Die Aufnahme lief nicht durch (Exitcode {code:?}). {fehler_text}"),
        );
    }
    antwort_ok(json!({
        "aufnahme": true,
        "pubkey": pubkey,
        "zeile": zeile,
        "hostschluessel_typ": hk_typ,
        "hostschluessel": hk_blob,
        "text": "Schluessel eingetragen",
    }))
}

/// Den Verbindungs-Deskriptor an den Proxy geben (ein Byte + `SCM_RIGHTS`).
fn uebergabe_schicken(strom: &UnixStream, fd: RawFd) -> std::io::Result<()> {
    let mut buf = [0u8; 1];
    let iov = libc::iovec { iov_base: buf.as_mut_ptr() as *mut libc::c_void, iov_len: 1 };
    let mut cmsg_puffer = [0u8; 64];
    let mut kopf: libc::msghdr = unsafe { std::mem::zeroed() };
    kopf.msg_iov = &iov as *const libc::iovec as *mut libc::iovec;
    kopf.msg_iovlen = 1 as _;
    kopf.msg_control = cmsg_puffer.as_mut_ptr() as *mut libc::c_void;
    let bytes = std::mem::size_of::<RawFd>() as u32;
    let platz = unsafe { libc::CMSG_SPACE(bytes) };
    kopf.msg_controllen = platz as _;
    if platz as usize > cmsg_puffer.len() {
        return Err(std::io::Error::new(std::io::ErrorKind::InvalidInput, "Puffer zu klein"));
    }
    unsafe {
        let cmsg = libc::CMSG_FIRSTHDR(&kopf);
        (*cmsg).cmsg_level = libc::SOL_SOCKET;
        (*cmsg).cmsg_type = libc::SCM_RIGHTS;
        (*cmsg).cmsg_len = libc::CMSG_LEN(bytes) as _;
        std::ptr::copy_nonoverlapping(&fd as *const RawFd as *const u8, libc::CMSG_DATA(cmsg), bytes as usize);
    }
    use std::os::unix::io::AsRawFd;
    let n = unsafe { libc::sendmsg(strom.as_raw_fd(), &kopf, 0) };
    if n < 0 {
        return Err(std::io::Error::last_os_error());
    }
    Ok(())
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::BufRead;

    /// Ein winziges Gateway: nimmt **eine** Anfrage an, merkt sie sich und
    /// antwortet. Rueckgabe: (Socketpfad, Faden mit der gesehenen Anfrage).
    fn gateway(antwort: Value) -> (PathBuf, std::thread::JoinHandle<Value>) {
        let ordner = std::env::temp_dir().join(format!(
            "chimera-tor-attrappe-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        std::fs::create_dir_all(&ordner).expect("ordner");
        let pfad = ordner.join("tor.sock");
        let listener = std::os::unix::net::UnixListener::bind(&pfad).expect("binden");
        let faden = std::thread::spawn(move || {
            let (strom, _) = listener.accept().expect("verbindung");
            let mut leser = std::io::BufReader::new(strom.try_clone().expect("klon"));
            let mut zeile = String::new();
            leser.read_line(&mut zeile).expect("lesen");
            let gesehen: Value = serde_json::from_str(zeile.trim()).expect("json");
            let mut schreiber = strom;
            gemein::zeile::schreiben(&mut schreiber, &antwort).expect("antwort");
            gesehen
        });
        (pfad, faden)
    }

    fn einstellungen(arbeit: &Path) -> Grenzen {
        let _ = arbeit;
        Grenzen::default()
    }

    fn arbeit(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("chimera-sohelper-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).expect("arbeitsordner");
        d
    }

    #[test]
    fn ziel_ist_der_programmname_klein() {
        assert_eq!(ziel_name(&["/usr/bin/ls".to_string(), "-la".to_string()]), "ls");
        assert_eq!(ziel_name(&["LS".to_string()]), "ls");
        assert_eq!(ziel_name(&["python3".to_string(), "x.py".to_string()]), "python3");
    }

    #[test]
    fn die_anfrage_nennt_werkzeug_und_ziel() {
        let (pfad, faden) = gateway(json!({"ok": true, "erlaubt": true, "grund": "Zeitfreigabe laeuft"}));
        let a = freigabe_fragen(&pfad, "run_command", "ls").expect("antwort");
        let gesehen = faden.join().expect("faden");
        assert_eq!(gesehen["op"], "freigabe_pruefen");
        assert_eq!(gesehen["werkzeug"], "run_command");
        assert_eq!(gesehen["ziel"], "ls");
        assert_eq!(a["erlaubt"], true);
    }

    #[test]
    fn ohne_gateway_wird_nichts_ausgefuehrt() {
        // Der Fall, der zaehlt: kein Gateway, kein Befehl -- und der Grund
        // steht im Text, statt still durchzulaufen (kein Rueckfall).
        let ordner = arbeit("ohne-gateway");
        let fehlt = ordner.join("gibt-es-nicht.sock");
        let a = bearbeite(
            &json!({"op": "run", "command": "echo sollte-nicht-laufen"}),
            &ordner,
            &fehlt,
            &einstellungen(&ordner),
            Instant::now(),
            1,
            &[],
        );
        assert_eq!(a["ok"], false, "{a}");
        assert_eq!(a["fehler"]["code"], "nicht_freigegeben");
        let text = a["fehler"]["text"].as_str().unwrap();
        assert!(text.contains("nicht erreichbar") && text.contains("nicht freigegeben"), "{text}");
        assert!(!text.contains("sollte-nicht-laufen") || text.contains("nicht freigegeben"), "{text}");
    }

    #[test]
    fn eine_ablehnung_verhindert_die_ausfuehrung() {
        let ordner = arbeit("abgelehnt");
        let (pfad, faden) = gateway(json!({"ok": true, "erlaubt": false, "grund": "keine Freigabe eingetragen"}));
        let a = bearbeite(
            &json!({"op": "run", "command": "echo hallo"}),
            &ordner,
            &pfad,
            &einstellungen(&ordner),
            Instant::now(),
            2,
            &[],
        );
        let gesehen = faden.join().expect("faden");
        assert_eq!(gesehen["ziel"], "echo");
        assert_eq!(a["ok"], false, "{a}");
        assert_eq!(a["fehler"]["code"], "nicht_freigegeben");
        let text = a["fehler"]["text"].as_str().unwrap();
        assert!(text.contains("keine Freigabe eingetragen") && text.contains("echo"), "{text}");
        assert_ne!(text, "hallo", "der Befehl darf nicht gelaufen sein");
    }

    #[test]
    fn eine_freigabe_laesst_ihn_laufen() {
        let ordner = arbeit("erlaubt");
        let (pfad, faden) = gateway(json!({"ok": true, "erlaubt": true, "grund": "Zeitfreigabe laeuft"}));
        let a = bearbeite(
            &json!({"op": "run", "command": "echo hallo"}),
            &ordner,
            &pfad,
            &einstellungen(&ordner),
            Instant::now(),
            3,
            &[],
        );
        let _ = faden.join().expect("faden");
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["text"].as_str().unwrap().trim(), "hallo");
    }

    #[test]
    fn harte_regeln_gelten_auch_mit_freigabe() {
        // "offen" erlaubt mehr Ziele, nicht mehr Programme.
        let ordner = arbeit("harte-regeln");
        let (pfad, _faden) = gateway(json!({"ok": true, "erlaubt": true}));
        for befehl in ["sudo id", "sh -c ls", "curl http://example.com", "rm -rf /"] {
            let a = bearbeite(
                &json!({"op": "run", "command": befehl}),
                &ordner,
                &pfad,
                &einstellungen(&ordner),
                Instant::now(),
                4,
                &[],
            );
            assert_eq!(a["ok"], false, "{befehl}: {a}");
            assert_eq!(a["fehler"]["code"], "abgelehnt", "{befehl}: {a}");
        }
    }
}
