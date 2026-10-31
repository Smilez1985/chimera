//! chimera-tor -- Chimeras Gateway (DESIGN Regel 5n).
//!
//! Stand Phase 4d Schritt 2: Geruest mit Socket (`ping`, `status`).
//! Anbieter, Telegram und Web folgen (docs/ROADMAP.md, Phase 4d).

mod dienst;
mod modul_vorlage;
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
  chimera-tor --module-vorlage   die Variablen der Vorlage (VARIABLEN.md) ausgeben";

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
    #[test]
    fn pruefen_nennt_version_und_zustand() {
        let p = super::pruefen();
        assert_eq!(p["version"], gemein::version());
        assert_eq!(p["dienst"], "geruest");
    }
}
