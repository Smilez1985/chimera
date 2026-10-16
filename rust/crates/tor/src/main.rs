//! chimera-tor -- Chimeras Gateway (DESIGN Regel 5n).
//!
//! Stand Phase 4d Schritt 1: nur das Geruest fuer Build, CI und
//! Installer. Socket, Anbieter und Web folgen in den naechsten Schritten
//! (docs/ROADMAP.md, Phase 4d). Bis dahin startet das Binary keinen
//! Dienst und sagt das, statt still zu laufen.

use gemein::protokoll::{melden, Stufe};
use std::process::ExitCode;

const HILFE: &str = "\
chimera-tor -- Gateway von Chimera

  chimera-tor --version   Version ausgeben
  chimera-tor --pruefen   Selbstpruefung als JSON (fuer den Installer)
  chimera-tor --help      diese Hilfe

Der Dienstbetrieb (Socket /run/chimera/tor.sock) ist noch nicht gebaut.";

fn pruefen() -> serde_json::Value {
    serde_json::json!({
        "ok": true,
        "programm": "chimera-tor",
        "version": gemein::version(),
        "ziel": format!("{}-{}", std::env::consts::ARCH, std::env::consts::OS),
        "dienst": "nicht gebaut",
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
        Some(anderes) => {
            melden(Stufe::Fehler, &format!("unbekannte Option: {anderes}"));
            eprintln!("{HILFE}");
            ExitCode::from(2)
        }
        None => {
            melden(Stufe::Fehler, "Dienstbetrieb noch nicht gebaut (Phase 4d Schritt 2).");
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
        assert_eq!(p["dienst"], "nicht gebaut");
    }
}
