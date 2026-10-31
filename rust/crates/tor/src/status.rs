//! Messwerte fuer das Status-Modul der Web-Oberflaeche (DESIGN Regel 5m).
//!
//! Die Parser sind reine Funktionen von Text zu Wert, damit die Tests sie
//! aufrufen statt nachzurechnen. Ein Wert, der sich nicht lesen laesst, ist
//! `null` -- nie 0 und nie geraten (GLOBAL: leere Ausgabe ist ein Verdachtsfall).

use serde_json::{json, Value};
use std::path::Path;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

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

fn lesen(pfad: &Path) -> Option<String> {
    std::fs::read_to_string(pfad).ok().filter(|s| !s.trim().is_empty())
}

/// Einen Befehl mit Frist ausfuehren; Ausgabe nur bei Erfolg oder `is-active`-Rueckgabe.
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

/// Alles messen. `wurzel` ist `/` (Tests zeigen auf ein Verzeichnis mit
/// nachgebauten `proc/` und `sys/`), `dienste` sind die abzufragenden Units.
pub fn messen(wurzel: &Path, dienste: &[&str], mit_befehlen: bool) -> Value {
    let w = |p: &str| wurzel.join(p.trim_start_matches('/'));
    let temp = lesen(&w("sys/class/thermal/thermal_zone0/temp")).and_then(|t| temperatur_c(&t));
    let mem = lesen(&w("proc/meminfo")).and_then(|t| speicher_mib(&t));
    let lst = lesen(&w("proc/loadavg")).and_then(|t| last(&t));
    let lz = lesen(&w("proc/uptime")).and_then(|t| laufzeit_s(&t));
    let platte = if mit_befehlen {
        befehl("df", &["-Pk", "/"], Duration::from_secs(2)).and_then(|t| platte_mib(&t))
    } else {
        None
    };
    let dl: Vec<Value> = dienste
        .iter()
        .map(|d| {
            let z = if mit_befehlen {
                // `is-active` gibt bei "inactive" rc 3 zurueck, die Ausgabe zaehlt.
                befehl("systemctl", &["is-active", d], Duration::from_secs(2))
                    .map(|t| dienstzustand(&t))
                    .unwrap_or("unbekannt")
            } else {
                "unbekannt"
            };
            json!({"name": d, "zustand": z})
        })
        .collect();
    json!({
        "ok": true,
        "temperatur_c": temp,
        "speicher_mib": mem.map(|(g, f)| json!({"gesamt": g, "verfuegbar": f})),
        "last": lst,
        "laufzeit_s": lz,
        "platte_mib": platte.map(|(g, b)| json!({"gesamt": g, "belegt": b})),
        "dienste": dl,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

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

    #[test]
    fn messen_liest_aus_nachgebauter_wurzel_und_meldet_fehlendes_als_null() {
        let d = std::env::temp_dir().join(format!("chimera-status-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(d.join("proc")).unwrap();
        std::fs::write(d.join("proc/loadavg"), "1.5 1.0 0.5 1/2 3\n").unwrap();
        let v = messen(&d, &["chimera"], false);
        assert_eq!(v["last"], json!([1.5, 1.0, 0.5]));
        assert!(v["temperatur_c"].is_null());
        assert!(v["speicher_mib"].is_null());
        assert!(v["laufzeit_s"].is_null());
        assert_eq!(v["dienste"][0]["zustand"], "unbekannt");
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn echtes_proc_liefert_werte() {
        // Auf jedem Linux vorhanden; prueft, dass der Weg ueber die echte Wurzel geht.
        // Nicht jede Umgebung erlaubt jede Datei (die Sandbox sperrt /proc/loadavg):
        // ein nicht lesbarer Wert muss null sein, ein lesbarer plausibel.
        let v = messen(Path::new("/"), &[], false);
        assert!(v["last"].is_array() || v["last"].is_null());
        assert!(v["speicher_mib"]["gesamt"].as_u64().unwrap() > 0);
    }
}
