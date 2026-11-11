//! Wie ein Prozess an seinen Unix-Socket kommt (DESIGN Regel 14).
//!
//! Zwei Wege, in dieser Reihenfolge:
//!
//! 1. **Socket-Aktivierung** (`LISTEN_FDS`): systemd haelt den Socket und
//!    reicht ihn als Handle 3 herein. Der Prozess braucht dann kein Recht am
//!    Verzeichnis -- er muss die Datei nicht anlegen. Das ist der Weg im
//!    Betrieb: Der Socket steht, bevor der Dienst laeuft.
//! 2. **Selbst binden** (`--socket PFAD`): fuer die Sandbox und fuer Tests,
//!    wo kein systemd da ist.
//!
//! **Warum das hier liegt und nicht zweimal dort:** Gateway und Ausfuehrer
//! stellen dieselbe Frage. Zwei Kopien waeren der Anfang davon, dass eine
//! davon stillschweigend anders prueft (Regel 10g) -- und die Pruefung
//! "wird der Socket schon bedient?" ist genau die, die man nicht zweimal
//! leicht verschieden schreiben will.

use std::os::unix::io::FromRawFd;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;

use super::protokoll::{melden, Stufe};

/// Den von systemd uebergebenen Socket holen (`LISTEN_FDS`, Handle 3).
/// `None`, wenn der Prozess nicht per Socket-Aktivierung gestartet wurde.
pub fn von_systemd() -> Option<UnixListener> {
    let pid: u32 = std::env::var("LISTEN_PID").ok()?.parse().ok()?;
    if pid != std::process::id() {
        return None;
    }
    let n: u32 = std::env::var("LISTEN_FDS").ok()?.parse().ok()?;
    if n != 1 {
        melden(Stufe::Fehler, &format!("LISTEN_FDS={n}, erwartet 1."));
        return None;
    }
    // SAFETY: systemd uebergibt Handle 3 genau dann, wenn LISTEN_PID und
    // LISTEN_FDS gesetzt sind (sd_listen_fds(3)); niemand sonst besitzt es.
    Some(unsafe { UnixListener::from_raw_fd(3) })
}

/// Selbst an einen Pfad binden. Eine alte Socket-Datei, hinter der niemand
/// mehr lauscht, wird ersetzt; antwortet dort noch jemand, ist es ein
/// Fehler (zwei Prozesse am selben Socket waeren einer zu viel).
pub fn binden(pfad: &Path) -> Result<UnixListener, String> {
    if pfad.exists() {
        if UnixStream::connect(pfad).is_ok() {
            return Err(format!("{} wird schon bedient", pfad.display()));
        }
        // Es lauscht niemand mehr: Der Rest eines abgebrochenen Laufs darf
        // den Start nicht verhindern. Der Ordner gehoert ohnehin uns.
        std::fs::remove_file(pfad)
            .map_err(|e| format!("alter Socket {} nicht entfernbar: {e}", pfad.display()))?;
    }
    if let Some(d) = pfad.parent() {
        std::fs::create_dir_all(d)
            .map_err(|e| format!("Ordner {} nicht anlegbar: {e}", d.display()))?;
    }
    let l = UnixListener::bind(pfad)
        .map_err(|e| format!("Socket nicht anlegbar ({}): {e}", pfad.display()))?;
    // 0660: Der Eigentuemer bedient, seine Gruppe darf fragen, andere nicht.
    // Bei Socket-Aktivierung setzt systemd das (SocketMode); hier tun wir es.
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(pfad, std::fs::Permissions::from_mode(0o660))
        .map_err(|e| format!("Rechte auf {}: {e}", pfad.display()))?;
    Ok(l)
}

/// Den Socket holen: erst von systemd, sonst selbst binden.
/// `Err` nennt den Grund im Klartext, damit die Unit ihn ins Journal schreibt.
pub fn oeffnen(pfad: Option<&Path>) -> Result<UnixListener, String> {
    if let Some(l) = von_systemd() {
        return Ok(l);
    }
    match pfad {
        Some(p) => binden(p),
        None => Err(
            "kein Socket von systemd uebergeben (LISTEN_FDS) und kein --socket PFAD".to_string(),
        ),
    }
}
