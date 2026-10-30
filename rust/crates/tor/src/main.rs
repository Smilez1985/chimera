//! chimera-tor -- Chimeras Gateway (DESIGN Regel 5n).
//!
//! Stand Phase 4d Schritt 2: Geruest mit Socket (`ping`, `status`).
//! Anbieter, Telegram und Web folgen (docs/ROADMAP.md, Phase 4d).

mod dienst;
mod ollama;

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
  chimera-tor --ping [PFAD]  Gateway fragen (Vorgabe /run/chimera/tor.sock), rc 0 = antwortet";

fn pruefen() -> serde_json::Value {
    serde_json::json!({
        "ok": true,
        "programm": "chimera-tor",
        "version": gemein::version(),
        "ziel": format!("{}-{}", std::env::consts::ARCH, std::env::consts::OS),
        "dienst": "geruest",
    })
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
                    dienst::lauschen(l)
                }
            }
        }
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
