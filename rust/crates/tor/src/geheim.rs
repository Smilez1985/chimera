//! Geheimnisse, die **nie** durch den Chat gehen (DESIGN, „Aufnahme eines
//! Hosts: das Passwort einmal, der Schlüssel danach").
//!
//! **Warum es diese Ablage gibt:** Ein Passwort, das der Nutzer in den Prompt
//! tippt, ist schon unterwegs — es liegt im Verlauf, in der Sitzungsablage und
//! in jeder Zusammenfassung, bevor irgendjemand es maskieren könnte. Deshalb
//! gibt es für Geheimnisse einen eigenen Kanal: Der Nutzer schreibt sie über
//! eine seiner Türen (Web-Modul, Kommandozeile ohne Echo, Telegram) in diese
//! Ablage; das Gateway liest sie von dort. Der Agent kann sie nicht lesen —
//! `config/` ist für ihn gesperrt (`InaccessiblePaths`), und diese Dateien
//! gehören `chimera-tor` mit Modus 0600.
//!
//! **Ein Geheimnis ist kein Zustand, den man anzeigt.** Es gibt hier
//! absichtlich keine Funktion, die den Inhalt zurückgibt, ohne dass der
//! Aufrufer ihn braucht (`lesen`), und keine, die ihn protokolliert. Was
//! geschrieben oder gelöscht wurde, wird als *das* gemeldet — nie der Wert.
//!
//! **Kurzlebig.** Nach der Aufnahme eines Hosts wird das Passwort sofort
//! gelöscht (Vorgabe smilez, 12.11.): es hat einen Zweck gehabt.

use crate::daten::atomar_schreiben;
use crate::daten::Pfade;
use std::path::PathBuf;

/// Der Ordner für SSH-Geheimnisse unterhalb der Geheim-Ablage.
pub fn ordner(p: &Pfade) -> PathBuf {
    p.config.join("geheim").join("ssh")
}

/// Der Name muss ein Bezeichner sein — er wird zum Dateinamen und darf keinen
/// Pfad bilden.
fn name_ok(n: &str) -> bool {
    !n.is_empty()
        && n.len() <= 32
        && n.chars().next().map(|c| c.is_ascii_lowercase() || c.is_ascii_digit()).unwrap_or(false)
        && n.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-' || c == '_' || c == '.')
}

fn datei(p: &Pfade, host: &str) -> Option<PathBuf> {
    if !name_ok(host) {
        return None;
    }
    Some(ordner(p).join(host))
}

/// Das Geheimnis ablegen. Gibt **nichts** vom Wert zurück — nur, dass es steht.
pub fn setzen(p: &Pfade, host: &str, passwort: &str) -> Result<(), (&'static str, String)> {
    let Some(ziel) = datei(p, host) else {
        return Err(("name_ungueltig", format!("\"{host}\" ist kein Host-Name für die Geheim-Ablage.")));
    };
    let passwort = passwort.trim_end_matches(['\n', '\r']);
    if passwort.is_empty() {
        return Err(("passwort_leer", "Das Passwort ist leer.".into()));
    }
    if passwort.len() > 1024 {
        return Err(("passwort_zu_lang", "Das Passwort ist länger als 1024 Bytes.".into()));
    }
    if passwort.chars().any(|c| c.is_control()) {
        return Err((
            "passwort_ungueltig",
            "Das Passwort enthält Steuerzeichen (Zeilenumbruch?) — es wird als eine Zeile abgelegt.".into(),
        ));
    }
    atomar_schreiben(&ziel, passwort.as_bytes(), 0o600).map_err(|e| ("nicht_gespeichert", e))
}

/// Das Geheimnis lesen. `None`, wenn keines abgelegt ist.
pub fn lesen(p: &Pfade, host: &str) -> Option<String> {
    let ziel = datei(p, host)?;
    std::fs::read_to_string(ziel).ok().map(|t| t.trim_end_matches(['\n', '\r']).to_string()).filter(|t| !t.is_empty())
}

/// Ob eines abgelegt ist — **ohne** den Wert zu holen. Das ist die Auskunft,
/// die eine Oberfläche zeigen darf.
pub fn vorhanden(p: &Pfade, host: &str) -> bool {
    datei(p, host).map(|z| z.is_file()).unwrap_or(false)
}

/// Löschen. `Ok(true)` heißt: es war eines da und ist jetzt weg.
pub fn loeschen(p: &Pfade, host: &str) -> Result<bool, (&'static str, String)> {
    let Some(ziel) = datei(p, host) else {
        return Err(("name_ungueltig", format!("\"{host}\" ist kein Host-Name für die Geheim-Ablage.")));
    };
    match std::fs::remove_file(&ziel) {
        Ok(()) => Ok(true),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(e) => Err(("nicht_geloescht", format!("{}: {e}", ziel.display()))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn p(name: &str) -> Pfade {
        let d = std::env::temp_dir().join(format!("chimera-geheim-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        Pfade::neu(d.join("config"), d.join("state"))
    }

    #[test]
    fn ablegen_lesen_loeschen() {
        let p = p("weg");
        assert!(!vorhanden(&p, "box"));
        setzen(&p, "box", "Geheim123").unwrap();
        assert!(vorhanden(&p, "box"));
        assert_eq!(lesen(&p, "box").as_deref(), Some("Geheim123"));
        assert_eq!(loeschen(&p, "box").unwrap(), true);
        assert!(!vorhanden(&p, "box"));
        assert_eq!(loeschen(&p, "box").unwrap(), false);
    }

    #[test]
    fn die_datei_ist_0600_und_enthaelt_nur_das_geheimnis() {
        let p = p("rechte");
        setzen(&p, "box", "Geheim123").unwrap();
        let ziel = datei(&p, "box").unwrap();
        let modus = std::fs::metadata(&ziel).unwrap().permissions().mode() & 0o777;
        assert_eq!(modus, 0o600);
        assert_eq!(std::fs::read_to_string(&ziel).unwrap(), "Geheim123");
    }

    #[test]
    fn ein_zeilenumbruch_wird_nicht_abgeschnitten_sondern_abgelehnt() {
        let p = p("zeile");
        assert_eq!(setzen(&p, "box", "zwei\nzeilen").unwrap_err().0, "passwort_ungueltig");
        // Ein einzelner Umbruch am Ende ist der Normalfall (Shell) und fliegt raus.
        setzen(&p, "box", "Geheim123\n").unwrap();
        assert_eq!(lesen(&p, "box").as_deref(), Some("Geheim123"));
    }

    #[test]
    fn namen_sind_bezeichner_kein_pfad() {
        let p = p("namen");
        for boese in ["", "../x", "Mit Gross", "a/b"] {
            assert_eq!(setzen(&p, boese, "x").unwrap_err().0, "name_ungueltig", "{boese:?}");
            assert_eq!(lesen(&p, boese), None);
        }
    }
}
