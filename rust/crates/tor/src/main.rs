//! chimera-tor -- Chimeras Gateway (DESIGN Regel 5n).
//!
//! Stand Phase 4d Schritt 2: Geruest mit Socket (`ping`, `status`).
//! Anbieter, Telegram und Web folgen (docs/ROADMAP.md, Phase 4d).

mod daten;
mod dienst;
mod modul_vorlage;
mod mojo;
mod netzsuche;
mod neustart;
mod ollama;
mod sitzung;
mod status;
mod telegram;
mod web;

use gemein::protokoll::{melden, Stufe};
use std::path::PathBuf;
use std::process::ExitCode;

/// Wo das Gateway lauscht, wenn nichts anderes gesagt wird.
const SOCKET: &str = "/run/chimera/tor.sock";

const HILFE: &str = "\
chimera-tor -- Gateway von Chimera

  chimera-tor --version   Version ausgeben
  chimera-tor --pruefen   Selbstpruefung als JSON (fuer den Installer)
  chimera-tor --help      diese Hilfe
  chimera-tor --dienst    Dienstbetrieb: den von systemd uebergebenen Socket
                          bedienen, ohne systemd mit --socket PFAD selbst binden
  chimera-tor --passwort-hash  Passwort von stdin lesen, Hash fuer CHIMERA_WEB_PASSWORT_HASH ausgeben
  chimera-tor --ping [PFAD]  Gateway fragen (Vorgabe /run/chimera/tor.sock), rc 0 = antwortet
  chimera-tor --module-neu NAME --titel-de TEXT [--titel-en TEXT] [--symbol Z] [--reihenfolge N]
                          [--recht R]... [--ziel VERZ]   Web-Modul aus der Vorlage anlegen (Regel 5v)
  chimera-tor --module-pruefen VERZ   Web-Modul pruefen, Pruefsumme nennen (JSON)
  chimera-tor --module-vorlage   die Variablen der Vorlage (VARIABLEN.md) ausgeben
  chimera-tor --mojo [--miracle] [--json] [--datei PFAD]   Dienste und Sockets pruefen, Ursache nennen;
                          mit --miracle die sanften Reparaturen, danach Nachpruefung (Regel Mojo).
                          Exitcode 0 sauber, 1 Warnung, 2 Fehler";

fn pruefen() -> serde_json::Value {
    serde_json::json!({
        "ok": true,
        "programm": "chimera-tor",
        "version": gemein::version(),
        "ziel": format!("{}-{}", std::env::consts::ARCH, std::env::consts::OS),
        "dienst": "geruest",
    })
}

/// Argumente von `--module-neu` lesen und das Modul anlegen.
fn modul_neu(a: &[String]) -> Result<PathBuf, String> {
    let name = a.first().filter(|n| !n.starts_with("--")).ok_or("--module-neu braucht einen Namen")?;
    let mut e = modul_vorlage::Eingabe::neu(name);
    let mut ziel = PathBuf::from(".");
    let mut i = 1;
    while i < a.len() {
        let wert = |i: usize| a.get(i + 1).cloned().ok_or_else(|| format!("{} braucht einen Wert", a[i]));
        match a[i].as_str() {
            "--titel-de" => e.titel_de = wert(i)?,
            "--titel-en" => e.titel_en = Some(wert(i)?),
            "--symbol" => e.symbol = wert(i)?,
            "--reihenfolge" => e.reihenfolge = wert(i)?.parse().map_err(|_| "--reihenfolge ist keine ganze Zahl".to_string())?,
            "--recht" => e.rechte.push(wert(i)?),
            "--ziel" => ziel = PathBuf::from(wert(i)?),
            x => return Err(format!("--module-neu kennt {x} nicht")),
        }
        i += 2;
    }
    modul_vorlage::anlegen(&e, &ziel)
}

/// `--mojo`: pruefen (und mit `--miracle` sanft reparieren), Bericht ausgeben,
/// den Bericht auch als Datei ablegen (Vorgabe `state/mojo-letzter.json`).
/// Darf das Miracle sein Urteil aus dem abgelegten Oracle-Ergebnis holen?
///
/// Nur, wenn die gestellte Frage dieselbe ist wie damals. Ein genannter
/// Bereich fragt etwas Engeres -- dort antwortet der Cache nicht, sondern
/// es wird geprueft (DESIGN, Regel Mojo).
fn darf_cache_antworten(bereich: Option<&str>) -> bool {
    bereich.is_none()
}

fn mojo_befehl(a: &[String]) -> ExitCode {
    let (mut fix, mut json, mut datei) = (false, false, None::<PathBuf>);
    let mut bereich: Option<String> = None;
    let mut oracle = false;
    let mut miracle = false;
    let mut fortsetzen = false;
    let mut i = 0;
    while i < a.len() {
        match a[i].as_str() {
            // Oracle findet (misst und legt das Ergebnis ab), Miracle repariert.
            "--oracle" => {
                oracle = true;
                fix = false;
            }
            "--miracle" => {
                miracle = true;
                fix = true;
            }
            // Der Lauf nach einem Neustart (DESIGN, Regel "Neustart mit
            // Fortsetzung und Rueckfall"): Der Marker sagt, was vorher stand.
            "--fortsetzen" => {
                fortsetzen = true;
                fix = true;
            }
            "--json" => json = true,
            "--bereich" => match a.get(i + 1) {
                Some(b) => {
                    bereich = Some(b.clone());
                    i += 1;
                }
                None => {
                    melden(Stufe::Fehler, "--bereich braucht einen Namen (etwa netz).");
                    return ExitCode::from(2);
                }
            },
            "--datei" => match a.get(i + 1) {
                Some(p) => {
                    datei = Some(PathBuf::from(p));
                    i += 1;
                }
                None => {
                    melden(Stufe::Fehler, "--datei braucht einen Pfad.");
                    return ExitCode::from(2);
                }
            },
            x => {
                melden(Stufe::Fehler, &format!("--mojo kennt {x} nicht."));
                return ExitCode::from(2);
            }
        }
        i += 1;
    }
    // --bereich netz: nur diese Pruefung. Der Installer fragt so gezielt nach
    // dem Netz, statt bei jedem Netzproblem den ganzen Systemcheck zu fahren.
    let mut pruefungen = mojo::pruefungen();
    if let Some(b) = &bereich {
        pruefungen.retain(|p| p.bereich() == b);
        if pruefungen.is_empty() {
            melden(Stufe::Fehler, &format!("--bereich {b}: keine solche Pruefung."));
            return ExitCode::from(2);
        }
    }
    // Eine Reparatur zur Zeit (DESIGN, Regel Mojo). Der Versuch, eine zweite
    // zu starten, endet hier -- nicht in einer Warteschlange: Ein Lauf, der
    // auf einen anderen wartet, repariert spaeter einen Zustand, den er nicht
    // mehr kennt. Exitcode 75 heisst "spaeter noch einmal" (EX_TEMPFAIL).
    let _sperre: Option<mojo::ReparaturSperre> = if fix {
        match mojo::ReparaturSperre::nehmen(&zustand_dir()) {
            Some(s) => Some(s),
            None => {
                melden(
                    Stufe::Warnung,
                    "Eine andere Reparatur laeuft bereits (state/mojo.lock) -- dieser Lauf tut nichts.",
                );
                return ExitCode::from(75);
            }
        }
    } else {
        None
    };

    // Miracle greift auf das letzte Oracle-Ergebnis zurueck, wenn es nicht
    // aelter als 6 Stunden ist. Fehlt es (oder ist es alt), laeuft Oracle
    // zuerst -- Miracle prueft dann selbst, statt blind zu reparieren.
    //
    // Ausnahme: Ist ein Bereich genannt, wird der Cache NICHT befragt. Sein
    // "exitcode 0" gilt fuer die Pruefungen, die damals liefen -- ueber
    // "--bereich netz" sagt es nichts (DESIGN, Regel Mojo: "ein Cache
    // antwortet nur auf die Frage, die er beantwortet hat"). Der Lauf
    // prueft dann selbst, auf den gefilterten Bereich.
    if miracle && !fortsetzen && !darf_cache_antworten(bereich.as_deref()) {
        let pfad = datei.clone().unwrap_or_else(mojo::oracle_pfad);
        match mojo::oracle_lesen(&pfad) {
            Some(alt) => {
                let ok = alt.get("exitcode").and_then(|v| v.as_u64()).unwrap_or(1) == 0;
                if ok {
                    melden(
                        Stufe::Info,
                        "Miracle: Oracle hat nichts gefunden (Ergebnis juenger als 6 h) -- nichts zu tun.",
                    );
                    return ExitCode::from(0);
                }
                melden(
                    Stufe::Info,
                    "Miracle: Oracle-Ergebnis ist juenger als 6 h -- es wird darauf aufgebaut.",
                );
            }
            None => {
                // Ohne Befund weiss Miracle nicht, was zu reparieren ist. Also
                // laeuft Oracle JETZT -- als eigener Durchgang, dessen Ergebnis
                // abgelegt wird. Erst danach wird repariert.
                melden(
                    Stufe::Info,
                    "Miracle: kein gueltiges Oracle-Ergebnis (fehlt oder aelter als 6 h) -- Oracle laeuft zuerst.",
                );
                let vorlauf = mojo::lauf(&mojo::Echt, &pruefungen, false);
                let jetzt = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_secs())
                    .unwrap_or(0);
                let vj = vorlauf.als_json(jetzt);
                mojo::ablegen(&vj, datei.as_deref());
                if vorlauf.exitcode() == 0 {
                    melden(Stufe::Info, "Miracle: Oracle hat nichts gefunden -- nichts zu reparieren.");
                    return ExitCode::from(0);
                }
                melden(
                    Stufe::Info,
                    "Miracle: Oracle hat Befunde -- jetzt wird repariert.",
                );
            }
        }
    }
    let bericht = mojo::lauf(&mojo::Echt, &pruefungen, fix);
    let jetzt = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let j = bericht.als_json(jetzt);
    if json {
        println!("{j}");
    } else {
        print!("{}", mojo::als_text(&bericht));
    }
    mojo::laut_melden(&bericht);
    // Jeder Lauf legt sein Ergebnis ab und ueberschreibt das vorherige --
    // so gilt immer der letzte Oracle-Stand, hoechstens 6 Stunden lang.
    mojo::ablegen(&j, datei.as_deref());
    let _ = oracle;

    // Nach einem Neustart: erst vergleichen, dann entscheiden. Kein zweiter
    // Neustart, wenn derselbe Befund noch steht (DESIGN, Regel "Neustart mit
    // Fortsetzung und Rueckfall").
    if fortsetzen {
        return fortsetzung_abschluss(&zustand_dir(), &bericht, jetzt);
    }
    // Sonst: Verlangt ein stehengebliebener Befund einen Neustart, wird er
    // jetzt vorbereitet -- mit Marker, Platzpruefung und Sperre.
    if fix {
        neustart_vorbereiten(&mojo::Echt, &zustand_dir(), &bericht, jetzt);
    }
    ExitCode::from(bericht.exitcode())
}

/// Wo Mojo seinen Zustand ablegt (`CHIMERA_STATE_DIR`, sonst wie im Installer).
fn zustand_dir() -> PathBuf {
    PathBuf::from(
        std::env::var("CHIMERA_STATE_DIR").unwrap_or_else(|_| "/opt/chimera/state".into()),
    )
}

/// Schluessel eines Befunds: Bereich und Gegenstand, wie im Bericht.
fn befund_schluessel(b: &mojo::Befund) -> String {
    format!("{}|{}", b.bereich, b.gegenstand)
}

/// Braucht ein stehengebliebener Befund einen Neustart? Dann Marker schreiben,
/// die geaenderten Dateien sichern und neu starten. `Some((exitcode, meldung))`
/// heisst: es wurde etwas gemeldet (Neustart eingeleitet oder verweigert).
fn neustart_vorbereiten(
    sys: &dyn mojo::System,
    state: &std::path::Path,
    bericht: &mojo::Bericht,
    jetzt: u64,
) {
    let offen: Vec<&mojo::Befund> = bericht
        .befunde
        .iter()
        .filter(|b| {
            b.schwere >= mojo::Schwere::Warn
                && b.unreparierbar
                && b.ursache.as_ref().map(|u| u.neustart_hilft).unwrap_or(false)
        })
        .collect();
    if offen.is_empty() {
        return;
    }
    let mut marker = neustart::marker_lesen(state).unwrap_or_else(|| {
        neustart::Marker::neu(jetzt, mojo::RUNDEN_MAX, "", Vec::new(), Vec::new())
    });
    if let Err(grund) = neustart::darf_neustarten(&marker) {
        melden(Stufe::Fehler, &format!("Neustart unterlassen: {grund}"));
        return;
    }
    // Nur die geaenderten Dateien. Heute aendert keine Reparatur eine Datei
    // (alle vier starten Dienste oder laden Pakete) -- die Liste ist deshalb
    // leer, und ein Rueckfall stellt dann nichts wieder her. Das ist kein
    // fehlender Baustein, sondern derzeit die Wahrheit; sobald eine Reparatur
    // eine Datei anfasst, traegt sie hier ihren Pfad ein.
    let dateien: Vec<String> = Vec::new();
    let stand = match neustart::snapshot_anlegen(state, &dateien, sys.platz_frei_mb("/"), jetzt) {
        Ok(s) => s,
        Err(grund) => {
            melden(Stufe::Fehler, &format!("Neustart unterlassen: {grund}"));
            return;
        }
    };
    marker.runde = mojo::RUNDEN_MAX;
    marker.grund = offen[0]
        .ursache
        .as_ref()
        .map(|u| u.text.clone())
        .unwrap_or_else(|| "Befund nennt einen Neustart".into());
    marker.befunde = offen.iter().map(|b| befund_schluessel(b)).collect();
    marker.dateien = stand;
    marker.neustarts += 1;
    marker.zeit = jetzt;
    if let Err(e) = neustart::marker_schreiben(state, &marker) {
        melden(Stufe::Fehler, &format!("Neustart unterlassen: Marker nicht schreibbar: {e}"));
        return;
    }
    match sys.neustart_ausloesen() {
        Ok(()) => melden(
            Stufe::Warnung,
            &format!(
                "Neustart eingeleitet (Grund: {}, {} Befund(e), Versuch {}/{}). Nach dem Start laeuft die Fortsetzung.",
                marker.grund,
                marker.befunde.len(),
                marker.neustarts,
                neustart::NEUSTARTS_MAX
            ),
        ),
        Err(e) => {
            // Ohne Neustart kein Marker: Ein liegengebliebener Marker wuerde
            // beim naechsten Start eine Fortsetzung vortaeuschen.
            neustart::marker_loeschen(state);
            melden(Stufe::Fehler, &format!("Neustart gescheitert: {e}"));
        }
    }
}

/// Der Lauf nach dem Neustart: hat er gewirkt? Wenn nicht, zurueckrollen und
/// laut melden -- statt ein zweites Mal zu starten.
fn fortsetzung_abschluss(
    state: &std::path::Path,
    bericht: &mojo::Bericht,
    jetzt: u64,
) -> ExitCode {
    let Some(marker) = neustart::marker_lesen(state) else {
        melden(Stufe::Warnung, "Fortsetzung ohne Marker -- es gab keinen Neustart. Lauf als normaler Durchgang gewertet.");
        return ExitCode::from(bericht.exitcode());
    };
    let noch: Vec<String> = bericht
        .befunde
        .iter()
        .filter(|b| b.schwere >= mojo::Schwere::Warn)
        .map(befund_schluessel)
        .collect();
    match neustart::fortsetzung(&marker, &noch) {
        neustart::Ausgang::Erledigt => {
            neustart::marker_loeschen(state);
            melden(
                Stufe::Info,
                &format!(
                    "Fortsetzung: der Neustart hat gewirkt (Grund war: {}, vor {} s). Marker entfernt.",
                    marker.grund,
                    jetzt.saturating_sub(marker.zeit)
                ),
            );
            ExitCode::from(bericht.exitcode())
        }
        neustart::Ausgang::Rueckfall => {
            let stelle = if marker.dateien.is_empty() {
                "keine Datei war geaendert -- nichts zurueckzurollen".to_string()
            } else {
                match neustart::zurueckrollen(state) {
                    Ok(p) => format!("{} Datei(en) zurueckgerollt: {}", p.len(), p.join(", ")),
                    Err(e) => format!("Rueckrollen gescheitert: {e}"),
                }
            };
            neustart::marker_loeschen(state);
            melden(
                Stufe::Fehler,
                &format!(
                    "Fortsetzung: derselbe Befund steht nach dem Neustart noch (Grund war: {}). {stelle}. Kein zweiter Neustart -- hier muss ein Mensch ran.",
                    marker.grund
                ),
            );
            ExitCode::from(bericht.exitcode().max(2))
        }
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("--version") | Some("-V") => {
            println!("chimera-tor {}", gemein::version());
            ExitCode::SUCCESS
        }
        Some("--pruefen") => {
            println!("{}", pruefen());
            ExitCode::SUCCESS
        }
        Some("--help") | Some("-h") => {
            println!("{HILFE}");
            ExitCode::SUCCESS
        }
        Some("--dienst") => {
            let pfad = match (args.get(1).map(String::as_str), args.get(2)) {
                (Some("--socket"), Some(p)) => Some(PathBuf::from(p)),
                (None, _) => None,
                _ => {
                    melden(Stufe::Fehler, "--dienst kennt nur --socket PFAD.");
                    return ExitCode::from(2);
                }
            };
            let listener = match pfad {
                Some(p) => dienst::binden(&p),
                None => dienst::von_systemd().ok_or_else(|| {
                    "kein Socket von systemd uebergeben (LISTEN_FDS) und kein --socket PFAD".to_string()
                }),
            };
            match listener {
                // Exitcode 2: Konfiguration falsch, ein Neustart hilft nicht.
                Err(e) => {
                    melden(Stufe::Fehler, &e);
                    ExitCode::from(2)
                }
                Ok(l) => {
                    melden(Stufe::Info, &format!("chimera-tor {} bereit", gemein::version()));
                    // Telegram ist eine Tuer im Gateway (Regel 5s). Ohne Token
                    // bleibt sie zu; mit Token aber falscher Liste ist es eine
                    // Fehlkonfiguration (rc 2, kein Neustart hilft).
                    match telegram::konfig() {
                        telegram::Konfig::Aus => melden(Stufe::Info, "Telegram nicht eingerichtet (CHIMERA_TELEGRAM_TOKEN leer)."),
                        telegram::Konfig::Falsch(f) => {
                            melden(Stufe::Fehler, &format!("Telegram falsch eingerichtet: {f}"));
                            return ExitCode::from(2);
                        }
                        telegram::Konfig::Bereit { token, erlaubt } => {
                            let pfad = std::env::var("CHIMERA_SITZUNG_SOCKET")
                                .unwrap_or_else(|_| sitzung::SOCKET.to_string());
                            telegram::starten(&token, erlaubt, PathBuf::from(pfad));
                        }
                    }
                    // Netzsuche (Regel 5k): gefundene Ollama-Server tragen sich selbst ein.
                    netzsuche::starten();
                    // Web-Oberflaeche (Regel 5m): ohne Passwort-Hash bleibt sie zu (5j).
                    match web::konfig() {
                        web::Konfig::Aus => melden(Stufe::Info, "Web-Oberflaeche nicht eingerichtet (CHIMERA_WEB_PASSWORT_HASH leer)."),
                        web::Konfig::Falsch(f) => {
                            melden(Stufe::Fehler, &format!("Web falsch eingerichtet: {f}"));
                            return ExitCode::from(2);
                        }
                        web::Konfig::Bereit { hash, adresse } => {
                            let sock = std::env::var("CHIMERA_SITZUNG_SOCKET")
                                .unwrap_or_else(|_| sitzung::SOCKET.to_string());
                            match web::starten(hash, &adresse, web::modul_verzeichnis(), PathBuf::from(sock)) {
                                Ok(a) => melden(Stufe::Info, &format!("Web-Oberflaeche auf http://{a} (unverschluesselt, nur im eigenen Netz).")),
                                Err(e) => {
                                    melden(Stufe::Fehler, &format!("Web-Oberflaeche startet nicht: {e}"));
                                    return ExitCode::from(2);
                                }
                            }
                        }
                    }
                    dienst::lauschen(l)
                }
            }
        }
        Some("--passwort-hash") => {
            // Passwort von der Standardeingabe lesen (nie als Argument: sonst
            // steht es in der Prozessliste und im Verlauf der Shell).
            let mut pw = String::new();
            if std::io::stdin().read_line(&mut pw).is_err() {
                melden(Stufe::Fehler, "Passwort nicht lesbar.");
                return ExitCode::from(2);
            }
            let pw = pw.trim_end_matches(['\n', '\r']);
            if pw.chars().count() < 8 {
                melden(Stufe::Fehler, "Das Passwort braucht mindestens 8 Zeichen.");
                return ExitCode::from(2);
            }
            match web::hash_erzeugen(pw) {
                Ok(h) => {
                    println!("{h}");
                    ExitCode::SUCCESS
                }
                Err(e) => {
                    melden(Stufe::Fehler, &e);
                    ExitCode::from(2)
                }
            }
        }
        Some("--module-vorlage") => {
            print!("{}", modul_vorlage::VARIABLEN_MD);
            ExitCode::SUCCESS
        }
        Some("--module-pruefen") => match args.get(1) {
            None => {
                melden(Stufe::Fehler, "--module-pruefen braucht ein Verzeichnis.");
                ExitCode::from(2)
            }
            Some(p) => match modul_vorlage::pruefen(&PathBuf::from(p)) {
                Ok(j) => {
                    println!("{j}");
                    ExitCode::SUCCESS
                }
                Err(e) => {
                    melden(Stufe::Fehler, &format!("Modul unzulaessig: {e}"));
                    ExitCode::from(1)
                }
            },
        },
        Some("--module-neu") => match modul_neu(&args[1..]) {
            Ok(d) => {
                println!("{}", d.display());
                ExitCode::SUCCESS
            }
            Err(e) => {
                melden(Stufe::Fehler, &e);
                ExitCode::from(2)
            }
        },
        Some("--mojo") => mojo_befehl(&args[1..]),
        Some("--ping") => {
            let pfad = PathBuf::from(args.get(1).map(String::as_str).unwrap_or(SOCKET));
            match dienst::anfragen(&pfad, &serde_json::json!({"op": "ping"})) {
                Ok(a) if a["ok"] == true => {
                    println!("{a}");
                    ExitCode::SUCCESS
                }
                Ok(a) => {
                    melden(Stufe::Fehler, &format!("unerwartete Antwort: {a}"));
                    ExitCode::from(1)
                }
                Err(e) => {
                    melden(Stufe::Fehler, &format!("Gateway antwortet nicht: {e}"));
                    ExitCode::from(1)
                }
            }
        }
        Some(anderes) => {
            melden(Stufe::Fehler, &format!("unbekannte Option: {anderes}"));
            eprintln!("{HILFE}");
            ExitCode::from(2)
        }
        None => {
            melden(Stufe::Fehler, "Ohne Option tut chimera-tor nichts; --dienst startet den Betrieb.");
            ExitCode::from(2)
        }
    }
}

#[cfg(test)]
mod tests {
    // Regel Mojo: Ein Cache antwortet nur auf die Frage, die er beantwortet
    // hat. Ein "alles in Ordnung" von vorhin beendet keinen Lauf, der nur
    // das Netz pruefen soll.
    #[test]
    fn cache_antwortet_nicht_auf_einen_bereich() {
        assert!(super::darf_cache_antworten(None));
        assert!(!super::darf_cache_antworten(Some("netz")));
        assert!(!super::darf_cache_antworten(Some("dienste")));
    }

    #[test]
    fn pruefen_nennt_version_und_zustand() {
        let p = super::pruefen();
        assert_eq!(p["version"], gemein::version());
        assert_eq!(p["dienst"], "geruest");
    }
}
