//! Gemeinsames fuer Chimeras Rust-Prozesse (DESIGN Regel 14).
//!
//! - [`version`]: die eine Versionsnummer aus `VERSION` im Repo-Root.
//! - [`zeile`]: das Socket-Protokoll -- eine JSON-Zeile hin, eine zurueck
//!   (Regel 5n, Grenze Python <-> Gateway).
//! - [`protokoll`]: Zeilen fuer journald, mit Stufe als Praefix.

/// Die Version kommt aus der VERSION-Datei im Repo-Root (einzige
/// Wahrheitsquelle, GLOBAL). Die Cargo-Manifeste tragen bewusst 0.0.0.
pub fn version() -> &'static str {
    VERSION.trim()
}

const VERSION: &str = include_str!("../../../../VERSION");

pub mod zeile {
    //! Eine Nachricht ist genau eine Zeile JSON, abgeschlossen mit `\n`.
    //!
    //! Die Laenge ist begrenzt. Ein Gegenueber, das ohne Zeilenende
    //! endlos schreibt, darf den Speicher nicht fuellen (Gateway-Grenze
    //! 10 MB, Regel 5n). Zu lang ist ein Fehler, kein stilles Kuerzen.

    use serde_json::Value;
    use std::io::{BufRead, Write};

    /// Obergrenze einer Zeile in Bytes. Ein Verlauf mit Werkzeugen passt
    /// hinein; ein Fehler im Gegenueber nicht unbegrenzt.
    pub const MAX_BYTES: usize = 4 * 1024 * 1024;

    #[derive(Debug, PartialEq)]
    pub enum Fehler {
        /// Das Gegenueber hat die Verbindung geschlossen, bevor eine
        /// Zeile begann. Kein Fehler im Protokoll, sondern sein Ende.
        Ende,
        /// Zeile laenger als erlaubt.
        ZuLang(usize),
        /// Verbindung brach mitten in einer Zeile ab.
        Abgebrochen,
        /// Kein gueltiges JSON oder kein Objekt.
        KeinObjekt(String),
        Io(String),
    }

    impl std::fmt::Display for Fehler {
        fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            match self {
                Fehler::Ende => write!(f, "Verbindung beendet"),
                Fehler::ZuLang(n) => write!(f, "Zeile zu lang (ueber {n} Bytes)"),
                Fehler::Abgebrochen => write!(f, "Verbindung mitten in der Zeile abgebrochen"),
                Fehler::KeinObjekt(g) => write!(f, "kein JSON-Objekt: {g}"),
                Fehler::Io(g) => write!(f, "E/A-Fehler: {g}"),
            }
        }
    }

    /// Liest genau eine Zeile und erwartet darin ein JSON-Objekt.
    pub fn lesen<R: BufRead>(r: &mut R, max: usize) -> Result<Value, Fehler> {
        let mut puffer: Vec<u8> = Vec::new();
        loop {
            let verfuegbar = r.fill_buf().map_err(|e| Fehler::Io(e.to_string()))?;
            if verfuegbar.is_empty() {
                return Err(if puffer.is_empty() { Fehler::Ende } else { Fehler::Abgebrochen });
            }
            let (teil, fertig) = match verfuegbar.iter().position(|&b| b == b'\n') {
                Some(i) => (&verfuegbar[..i], Some(i + 1)),
                None => (verfuegbar, None),
            };
            if puffer.len() + teil.len() > max {
                return Err(Fehler::ZuLang(max));
            }
            puffer.extend_from_slice(teil);
            let verbraucht = fertig.unwrap_or(verfuegbar.len());
            r.consume(verbraucht);
            if fertig.is_some() {
                break;
            }
        }
        let wert: Value = serde_json::from_slice(&puffer)
            .map_err(|e| Fehler::KeinObjekt(e.to_string()))?;
        if !wert.is_object() {
            return Err(Fehler::KeinObjekt("Wert ist kein Objekt".into()));
        }
        Ok(wert)
    }

    /// Schreibt ein Objekt als eine Zeile. serde_json maskiert
    /// Zeilenumbrueche in Strings, die Zeile bleibt also eine Zeile.
    pub fn schreiben<W: Write>(w: &mut W, wert: &Value) -> Result<(), Fehler> {
        let mut text = serde_json::to_vec(wert).map_err(|e| Fehler::Io(e.to_string()))?;
        text.push(b'\n');
        w.write_all(&text).map_err(|e| Fehler::Io(e.to_string()))?;
        w.flush().map_err(|e| Fehler::Io(e.to_string()))
    }

    /// Einheitliche Fehlerantwort, damit der Client nicht raten muss.
    pub fn fehlerantwort(code: &str, text: &str) -> Value {
        serde_json::json!({ "ok": false, "fehler": { "code": code, "text": text } })
    }
}

pub mod protokoll {
    //! Zeilen fuer journald. systemd liest das Praefix `<N>` als Stufe
    //! (sd-daemon(3)), dadurch filtert `journalctl -p` richtig.

    #[derive(Clone, Copy, Debug)]
    pub enum Stufe {
        Fehler,
        Warnung,
        Info,
    }

    pub fn praefix(s: Stufe) -> &'static str {
        match s {
            Stufe::Fehler => "<3>",
            Stufe::Warnung => "<4>",
            Stufe::Info => "<6>",
        }
    }

    /// Eine Meldung, eine Zeile: Zeilenumbrueche im Text werden ersetzt,
    /// sonst zerfiele ein Eintrag im Journal in mehrere ohne Stufe.
    pub fn zeile(s: Stufe, text: &str) -> String {
        format!("{}{}", praefix(s), text.replace(['\n', '\r'], " | "))
    }

    pub fn melden(s: Stufe, text: &str) {
        eprintln!("{}", zeile(s, text));
    }
}

#[cfg(test)]
mod tests {
    use super::zeile::{self, Fehler};
    use super::*;
    use std::io::Cursor;

    #[test]
    fn version_ist_die_aus_der_datei() {
        // Gegen die Datei selbst, nicht gegen eine abgeschriebene Zahl.
        let datei = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../../VERSION"))
            .expect("VERSION im Repo-Root");
        assert_eq!(version(), datei.trim());
        assert!(!version().is_empty());
    }

    #[test]
    fn zeile_hin_und_zurueck() {
        let wert = serde_json::json!({"art": "status", "text": "zwei\nzeilen"});
        let mut puffer = Vec::new();
        zeile::schreiben(&mut puffer, &wert).unwrap();
        assert_eq!(puffer.iter().filter(|&&b| b == b'\n').count(), 1);
        let mut r = Cursor::new(puffer);
        assert_eq!(zeile::lesen(&mut r, zeile::MAX_BYTES).unwrap(), wert);
        assert_eq!(zeile::lesen(&mut r, zeile::MAX_BYTES), Err(Fehler::Ende));
    }

    #[test]
    fn zwei_zeilen_nacheinander() {
        let mut r = Cursor::new(b"{\"a\":1}\n{\"b\":2}\n".to_vec());
        assert_eq!(zeile::lesen(&mut r, 100).unwrap()["a"], 1);
        assert_eq!(zeile::lesen(&mut r, 100).unwrap()["b"], 2);
    }

    #[test]
    fn zu_lang_wird_abgelehnt() {
        let mut r = Cursor::new(format!("{{\"x\":\"{}\"}}\n", "a".repeat(200)).into_bytes());
        assert_eq!(zeile::lesen(&mut r, 100), Err(Fehler::ZuLang(100)));
    }

    #[test]
    fn genau_an_der_grenze_geht() {
        let text = format!("{{\"x\":\"{}\"}}", "a".repeat(10));
        let n = text.len();
        let mut r = Cursor::new(format!("{text}\n").into_bytes());
        assert!(zeile::lesen(&mut r, n).is_ok());
        let mut r = Cursor::new(format!("{text}\n").into_bytes());
        assert_eq!(zeile::lesen(&mut r, n - 1), Err(Fehler::ZuLang(n - 1)));
    }

    #[test]
    fn abbruch_mitten_in_der_zeile() {
        let mut r = Cursor::new(b"{\"a\":1".to_vec());
        assert_eq!(zeile::lesen(&mut r, 100), Err(Fehler::Abgebrochen));
    }

    #[test]
    fn kein_objekt() {
        for eingabe in ["[1,2]\n", "42\n", "kaputt\n"] {
            let mut r = Cursor::new(eingabe.as_bytes().to_vec());
            assert!(matches!(zeile::lesen(&mut r, 100), Err(Fehler::KeinObjekt(_))), "{eingabe}");
        }
    }

    #[test]
    fn fehlerantwort_hat_feste_form() {
        let f = zeile::fehlerantwort("gateway_weg", "x");
        assert_eq!(f["ok"], false);
        assert_eq!(f["fehler"]["code"], "gateway_weg");
    }

    #[test]
    fn protokollzeile_bleibt_eine_zeile() {
        let z = protokoll::zeile(protokoll::Stufe::Warnung, "a\nb\rc");
        assert_eq!(z, "<4>a | b | c");
    }
}
