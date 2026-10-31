//! Client des Sitzungs-Sockets (DESIGN Regel 5s).
//!
//! Das Gateway ist der EINZIGE Client des Sockets `/run/chimera/sitzung.sock`.
//! Telegram (und spaeter die Web-Oberflaeche) sind Tueren IM Gateway und
//! sprechen alle ueber diesen Weg in die Hauptsitzung. Der Client haelt
//! keinen Verlauf; er kennt nur die Nummer des letzten Ereignisses, das er
//! gesehen hat, und meldet sich damit nach einem Abbruch wieder an.
//!
//! Protokoll (eine JSON-Zeile hin, eine zurueck; danach Ereignisse):
//! - `{"op":"anmelden","seit":N}`            -> `{"ok":true,"nr":M}`, dann `{"ereignis":{..}}`
//! - `{"op":"frage","tuer":..,"text":..,"ref":..}` -> `{"ok":true,"umgeleitet":bool}`
//!
//! Zwei Verbindungen: eine zum Hoeren (`anmelden`, bleibt offen), eine zum
//! Fragen (kurz). So blockiert eine lange Antwort kein Fragen.

use gemein::zeile;
use serde_json::{json, Value};
use std::io::BufReader;
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::time::Duration;

pub const SOCKET: &str = "/run/chimera/sitzung.sock";

/// Ein Ereignis des Stroms, auf das Noetige eingedampft.
#[derive(Debug, Clone, PartialEq)]
pub struct Ereignis {
    pub nr: u64,
    pub art: String,
    pub tuer: String,
    pub text: String,
    pub bezug: String,
}

/// Aus einer Zeile `{"ereignis":{..}}` das Ereignis lesen, sonst `None`.
pub fn ereignis_aus(zeile: &Value) -> Option<Ereignis> {
    let e = zeile.get("ereignis")?;
    Some(Ereignis {
        nr: e.get("nr")?.as_u64()?,
        art: e.get("art")?.as_str()?.to_string(),
        tuer: e.get("tuer")?.as_str()?.to_string(),
        text: e.get("text").and_then(Value::as_str).unwrap_or("").to_string(),
        bezug: e.get("ref").and_then(Value::as_str).unwrap_or("").to_string(),
    })
}

/// Eine Anfrage, eine Antwort. Eine abgelehnte Anfrage (`ok` nicht wahr) ist
/// ein Fehler mit dem Grund des Servers.
pub fn anfragen(pfad: &Path, anfrage: &Value) -> Result<Value, String> {
    let mut s = UnixStream::connect(pfad).map_err(|e| format!("{}: {e}", pfad.display()))?;
    s.set_read_timeout(Some(Duration::from_secs(10))).map_err(|e| e.to_string())?;
    zeile::schreiben(&mut s, anfrage).map_err(|e| e.to_string())?;
    let a = zeile::lesen(&mut BufReader::new(s), zeile::MAX_BYTES).map_err(|e| e.to_string())?;
    if a["ok"] != true {
        return Err(a["fehler"].as_str().unwrap_or("abgelehnt").to_string());
    }
    Ok(a)
}

/// Eine Frage in die Hauptsitzung geben. Gibt zurueck, ob sie umgeleitet wurde.
pub fn fragen(pfad: &Path, tuer: &str, text: &str, bezug: &str) -> Result<bool, String> {
    let a = anfragen(pfad, &json!({"op": "frage", "tuer": tuer, "text": text, "ref": bezug}))?;
    Ok(a["umgeleitet"] == true)
}

/// Auf den Strom hoeren: meldet sich ab Nummer `seit` an und ruft `f` fuer
/// jedes Ereignis. Kehrt zurueck, wenn die Verbindung endet; die Nummer des
/// letzten gesehenen Ereignisses steht in `seit`, der Aufrufer meldet sich
/// damit erneut an (Nachlieferung, nichts geht verloren, nichts doppelt).
pub fn hoeren<F: FnMut(&Ereignis)>(pfad: &Path, seit: &mut u64, mut f: F) -> Result<(), String> {
    let s = UnixStream::connect(pfad).map_err(|e| format!("{}: {e}", pfad.display()))?;
    let mut schreiber = s.try_clone().map_err(|e| e.to_string())?;
    // Kein Lese-Zeitlimit auf dem Strom: Stille ist normal. Ein totes
    // Gegenueber meldet das Betriebssystem als Ende der Verbindung.
    zeile::schreiben(&mut schreiber, &json!({"op": "anmelden", "seit": *seit}))
        .map_err(|e| e.to_string())?;
    let mut leser = BufReader::new(s);
    let a = zeile::lesen(&mut leser, zeile::MAX_BYTES).map_err(|e| e.to_string())?;
    if a["ok"] != true {
        return Err(a["fehler"].as_str().unwrap_or("Anmeldung abgelehnt").to_string());
    }
    loop {
        match zeile::lesen(&mut leser, zeile::MAX_BYTES) {
            Ok(z) => {
                if let Some(e) = ereignis_aus(&z) {
                    // Doppelte vermeiden: nur Neueres zaehlt (die Nachlieferung
                    // und der laufende Strom duerfen sich nicht ueberschneiden).
                    if e.nr > *seit {
                        *seit = e.nr;
                        f(&e);
                    }
                }
            }
            Err(zeile::Fehler::Ende) => return Ok(()),
            Err(e) => return Err(e.to_string()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::os::unix::net::UnixListener;

    fn tmp(name: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("chimera-sitzung-test-{}-{name}", std::process::id()));
        let _ = std::fs::remove_file(&d);
        d
    }

    #[test]
    fn ein_ereignis_wird_gelesen() {
        let z = json!({"ereignis": {"nr": 3, "art": "antwort", "tuer": "web", "text": "hi", "ref": "r"}});
        assert_eq!(
            ereignis_aus(&z),
            Some(Ereignis { nr: 3, art: "antwort".into(), tuer: "web".into(), text: "hi".into(), bezug: "r".into() })
        );
    }

    #[test]
    fn eine_antwortzeile_ist_kein_ereignis() {
        assert_eq!(ereignis_aus(&json!({"ok": true, "nr": 3})), None);
        assert_eq!(ereignis_aus(&json!({"ereignis": {"art": "antwort"}})), None);
    }

    #[test]
    fn fragen_meldet_umleitung() {
        let p = tmp("frage");
        let l = UnixListener::bind(&p).unwrap();
        let h = std::thread::spawn(move || {
            let (s, _) = l.accept().unwrap();
            let mut w = s.try_clone().unwrap();
            let a = zeile::lesen(&mut BufReader::new(s), 4096).unwrap();
            zeile::schreiben(&mut w, &json!({"ok": true, "umgeleitet": true})).unwrap();
            a
        });
        assert_eq!(fragen(&p, "telegram", "hi", "t-1"), Ok(true));
        let a = h.join().unwrap();
        assert_eq!(a["op"], "frage");
        assert_eq!(a["tuer"], "telegram");
        assert_eq!(a["ref"], "t-1");
    }

    #[test]
    fn fragen_ohne_server_ist_ein_fehler() {
        assert!(fragen(Path::new("/nonexistent/sitzung.sock"), "t", "x", "").is_err());
    }

    #[test]
    fn hoeren_liefert_nur_neueres_und_merkt_sich_die_nummer() {
        let p = tmp("hoeren");
        let l = UnixListener::bind(&p).unwrap();
        let h = std::thread::spawn(move || {
            let (s, _) = l.accept().unwrap();
            let mut w = s.try_clone().unwrap();
            let a = zeile::lesen(&mut BufReader::new(s), 4096).unwrap();
            zeile::schreiben(&mut w, &json!({"ok": true, "nr": 4})).unwrap();
            // 2 ist aelter als der Stand (seit=2): darf nicht durchkommen.
            for nr in [2u64, 3, 3, 4] {
                zeile::schreiben(&mut w, &json!({"ereignis": {"nr": nr, "art": "antwort", "tuer": "x", "text": "t"}}))
                    .unwrap();
            }
            w.flush().unwrap();
            a
        });
        let mut seit = 2;
        let mut gesehen = Vec::new();
        hoeren(&p, &mut seit, |e| gesehen.push(e.nr)).unwrap();
        assert_eq!(gesehen, vec![3, 4]);
        assert_eq!(seit, 4);
        assert_eq!(h.join().unwrap()["seit"], 2);
    }

    #[test]
    fn abgelehnte_anmeldung_ist_ein_fehler() {
        let p = tmp("abgelehnt");
        let l = UnixListener::bind(&p).unwrap();
        std::thread::spawn(move || {
            let (s, _) = l.accept().unwrap();
            let mut w = s.try_clone().unwrap();
            let _ = zeile::lesen(&mut BufReader::new(s), 4096);
            zeile::schreiben(&mut w, &json!({"ok": false, "fehler": "nein"})).unwrap();
        });
        let mut seit = 0;
        let e = hoeren(&p, &mut seit, |_| {}).unwrap_err();
        assert_eq!(e, "nein");
    }
}
