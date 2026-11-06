//! Neustart mit Fortsetzung und Rückfall (DESIGN, Regel gleichen Namens;
//! Vorgabe smilez, 3.11.).
//!
//! Mojo darf einen Neustart auslösen, wenn eine Reparatur ihn verlangt — und
//! muss danach **von selbst weitermachen**. Bringt der Neustart nichts,
//! rollt Mojo auf den Stand vor dem Neustart zurück und meldet den Befund,
//! statt ein zweites Mal zu starten.
//!
//! Der Vertrag zwischen den beiden Prozessen (vor und nach dem Neustart) ist
//! der **Marker** in `state/mojo-fortsetzen.json`. Alles, was der zweite Lauf
//! wissen muss, steht darin: wann, welche Runde, wie viele Neustarts, welche
//! Befunde den Neustart verlangt haben und welche Dateien angefasst wurden.
//!
//! **Der Snapshot ist ein Verzeichnis, kein Archiv.** Er enthält nur die
//! geänderten Dateien, unter ihrer Nummer, plus `stand.tsv` mit Pfad,
//! Prüfsumme und Nummer. Zurückrollen ist damit ein Kopieren mit
//! Prüfsummenvergleich — kein Entpacken, keine Abhängigkeit. Historie 1: Es
//! bleibt ein Snapshot; der vorherige wird als `mojo-snapshot-<zeit>`
//! archiviert und das davor liegende Archiv gelöscht.

use std::io::Write;
use std::path::{Path, PathBuf};

use serde_json::{json, Value};

/// Der Marker, an dem der Lauf nach dem Neustart wieder ansetzt.
pub const MARKER: &str = "mojo-fortsetzen.json";
/// Das Verzeichnis des Snapshots (relativ zum State-Verzeichnis).
pub const SNAPSHOT: &str = "mojo-snapshot";
/// So oft darf ein Marker einen Neustart auslösen. Danach nur noch Bericht —
/// ein Neustart, der nichts ändert, darf sich nicht wiederholen.
pub const NEUSTARTS_MAX: u32 = 2;
/// Untergrenze für den freien Platz vor dem Snapshot. Gilt, wenn die Größe
/// der zu sichernden Dateien klein oder unbekannt ist. Gemessen am 3.11. auf
/// dem Pi: etwa eine Produktivumgebung (`productive/` samt venv, 107 MB).
pub const PLATZ_MIN_MB: u64 = 100;

/// Faktor auf die Summe der zu sichernden Dateien. Kurzzeitig liegen **zwei**
/// Stände auf der Karte: der neue Snapshot und das Archiv des vorherigen
/// (`snapshot_archivieren` verschiebt, bevor der neue geschrieben wird; das
/// ältere Archiv verschwindet erst danach).
pub const PLATZ_FAKTOR: u64 = 2;

/// Eine gesicherte Datei: Pfad auf dem Gerät, Prüfsumme, Nummer der Kopie.
#[derive(Clone, Debug, PartialEq)]
pub struct Dateistand {
    pub pfad: String,
    pub sha256: String,
    pub nummer: usize,
}

/// Was der Lauf vor dem Neustart hinterlässt.
#[derive(Clone, Debug, PartialEq)]
pub struct Marker {
    /// Zeitpunkt des Neustarts (Unix-Sekunden).
    pub zeit: u64,
    /// Die Runde, an der Mojo stand (0 = noch keine Reparatur gelaufen).
    pub runde: u8,
    /// Wie viele Neustarts dieser Marker schon ausgelöst hat.
    pub neustarts: u32,
    /// Warum neu gestartet wurde (lesbarer Grund für Protokoll und Bericht).
    pub grund: String,
    /// Schlüssel (`bereich|gegenstand`) der Befunde, die den Neustart
    /// verlangten. Nach dem Start wird gegen diese Liste verglichen.
    pub befunde: Vec<String>,
    /// Nur die geänderten Dateien, nicht das ganze System.
    pub dateien: Vec<Dateistand>,
}

impl Marker {
    /// Ein frischer Marker, bevor ein Neustart ausgelöst wurde.
    pub fn neu(zeit: u64, runde: u8, grund: &str, befunde: Vec<String>, dateien: Vec<Dateistand>) -> Marker {
        Marker { zeit, runde, neustarts: 0, grund: grund.into(), befunde, dateien }
    }

    pub fn als_json(&self) -> Value {
        json!({
            "zeit": self.zeit,
            "runde": self.runde,
            "neustarts": self.neustarts,
            "grund": self.grund,
            "befunde": self.befunde,
            "dateien": self.dateien.iter().map(|d| json!({
                "pfad": d.pfad, "sha256": d.sha256, "nummer": d.nummer,
            })).collect::<Vec<_>>(),
        })
    }

    /// Aus JSON lesen. Fehlt ein Feld, gilt der Vorgabewert — nur `befunde`
    /// muss lesbar sein, sonst ist der Marker wertlos (dann `None`).
    pub fn aus_json(v: &Value) -> Option<Marker> {
        let befunde: Vec<String> = v
            .get("befunde")?
            .as_array()?
            .iter()
            .filter_map(|x| x.as_str().map(String::from))
            .collect();
        let dateien = v
            .get("dateien")
            .and_then(|d| d.as_array())
            .map(|a| {
                a.iter()
                    .filter_map(|x| {
                        Some(Dateistand {
                            pfad: x.get("pfad")?.as_str()?.to_string(),
                            sha256: x.get("sha256")?.as_str()?.to_string(),
                            nummer: x.get("nummer")?.as_u64()? as usize,
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();
        Some(Marker {
            zeit: v.get("zeit").and_then(Value::as_u64).unwrap_or(0),
            runde: v.get("runde").and_then(Value::as_u64).unwrap_or(0) as u8,
            neustarts: v.get("neustarts").and_then(Value::as_u64).unwrap_or(1) as u32,
            grund: v.get("grund").and_then(Value::as_str).unwrap_or("ohne Angabe").into(),
            befunde,
            dateien,
        })
    }
}

/// Was der Lauf nach dem Neustart daraus macht.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Ausgang {
    /// Keiner der Befunde, die den Neustart verlangten, steht noch.
    Erledigt,
    /// Dieselben Befunde stehen noch: zurückrollen und berichten.
    Rueckfall,
}

pub fn marker_pfad(dir: &Path) -> PathBuf {
    dir.join(MARKER)
}

pub fn marker_lesen(dir: &Path) -> Option<Marker> {
    let text = std::fs::read_to_string(marker_pfad(dir)).ok()?;
    let v: Value = serde_json::from_str(&text).ok()?;
    Marker::aus_json(&v)
}

pub fn marker_schreiben(dir: &Path, m: &Marker) -> Result<(), String> {
    std::fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    let pfad = marker_pfad(dir);
    let text = serde_json::to_string_pretty(&m.als_json()).map_err(|e| e.to_string())?;
    std::fs::write(&pfad, text).map_err(|e| format!("{}: {e}", pfad.display()))
}

pub fn marker_loeschen(dir: &Path) {
    let _ = std::fs::remove_file(marker_pfad(dir));
}

/// Darf dieser Marker noch einen Neustart auslösen?
pub fn darf_neustarten(m: &Marker) -> Result<(), String> {
    if m.neustarts >= NEUSTARTS_MAX {
        return Err(format!(
            "Sperre: {} Neustarts ohne Wirkung — kein weiterer (Handeingriff noetig)",
            m.neustarts
        ));
    }
    Ok(())
}

/// Nach dem Neustart: sind die Befunde, die ihn verlangten, noch da?
pub fn fortsetzung(m: &Marker, jetzt: &[String]) -> Ausgang {
    if m.befunde.iter().any(|s| jetzt.contains(s)) {
        Ausgang::Rueckfall
    } else {
        Ausgang::Erledigt
    }
}

/// Prüfsumme einer Datei (SHA-256, hexadezimal).
pub fn sha256_datei(pfad: &Path) -> Option<String> {
    let inhalt = std::fs::read(pfad).ok()?;
    let digest = ring::digest::digest(&ring::digest::SHA256, &inhalt);
    Some(digest.as_ref().iter().map(|b| format!("{b:02x}")).collect())
}

fn archiv_pfad(dir: &Path, jetzt: u64) -> PathBuf {
    dir.join(format!("{SNAPSHOT}-{jetzt}"))
}

/// Alte Archive entfernen, dann den stehenden Snapshot archivieren (Historie 1).
///
/// Der Archivname trägt den Zeitpunkt, an dem der Snapshot **angelegt** wurde
/// (aus seiner eigenen `zeit`-Datei), nicht den des Archivierens — sonst
/// hieße ein alter Stand nach einem neuen.
pub fn snapshot_archivieren(dir: &Path, jetzt: u64) -> Result<(), String> {
    let snap = dir.join(SNAPSHOT);
    if !snap.exists() {
        return Ok(());
    }
    let eigen = std::fs::read_to_string(snap.join("zeit"))
        .ok()
        .and_then(|t| t.trim().parse::<u64>().ok())
        .unwrap_or(jetzt);
    let ziel = archiv_pfad(dir, eigen);
    let _ = std::fs::remove_dir_all(&ziel);
    std::fs::rename(&snap, &ziel).map_err(|e| format!("{} -> {}: {e}", snap.display(), ziel.display()))?;
    // Historie 1: alles, was jetzt noch nach Archiv aussieht, ist aelter.
    let Ok(eintraege) = std::fs::read_dir(dir) else { return Ok(()) };
    for e in eintraege.flatten() {
        let name = e.file_name().to_string_lossy().to_string();
        if name.starts_with(&format!("{SNAPSHOT}-")) && e.path() != ziel {
            let _ = std::fs::remove_dir_all(e.path());
        }
    }
    Ok(())
}

/// Wie viel Platz der Snapshot braucht, in MB — aus der Summe der
/// Dateigrößen, nicht aus einem festen Richtwert. `None`, wenn eine Größe
/// nicht lesbar ist: Dann ist der Bedarf unbekannt und es gilt die
/// Untergrenze (Regel „Nie raten" — eine geratene Summe wäre schlimmer als
/// die bewusste Untergrenze).
pub fn platzbedarf_mb(dateien: &[String]) -> Option<u64> {
    let mut summe: u64 = 0;
    for p in dateien {
        let groesse = std::fs::metadata(p).ok()?.len();
        summe = summe.saturating_add(groesse);
    }
    // Aufrunden: ein halber MB ist ein halber MB zu wenig.
    let mb = summe.saturating_mul(PLATZ_FAKTOR).div_ceil(1024 * 1024);
    // usize -> u64 ist auf jedem Ziel erlaubt; max() haelt die Untergrenze.
    Some(mb.max(PLATZ_MIN_MB))
}

/// Snapshot der **geänderten** Dateien anlegen. Gibt den Stand zurück, der in
/// den Marker gehört. `platz_mb` ist der freie Platz auf dem Datenträger; ist
/// er zu knapp, wird **nichts** gesichert (ein halber Snapshot ist schlimmer
/// als keiner) und der Grund genannt.
///
/// Geprüft wird gegen den **Bedarf** (`platzbedarf_mb`), nicht gegen einen
/// festen Wert: Ein Snapshot von 200 MB passt nicht in 150 MB frei, auch wenn
/// 150 über jedem Richtwert liegen.
pub fn snapshot_anlegen(
    dir: &Path,
    dateien: &[String],
    platz_mb: Option<u64>,
    jetzt: u64,
) -> Result<Vec<Dateistand>, String> {
    if dateien.is_empty() {
        return Ok(Vec::new());
    }
    let bedarf = platzbedarf_mb(dateien).unwrap_or(PLATZ_MIN_MB);
    if let Some(mb) = platz_mb {
        if mb < bedarf {
            return Err(format!(
                "zu wenig Platz: {mb} MB frei, {bedarf} MB noetig ({} Datei(en), doppelt fuer den Vorgaengerstand, Untergrenze {PLATZ_MIN_MB} MB) -- kein Snapshot, kein Neustart",
                dateien.len()
            ));
        }
    }
    snapshot_archivieren(dir, jetzt)?;

    let snap = dir.join(SNAPSHOT);
    let ablage = snap.join("dateien");
    std::fs::create_dir_all(&ablage).map_err(|e| format!("{}: {e}", ablage.display()))?;

    let mut stand = Vec::new();
    let mut tsv = std::fs::File::create(snap.join("stand.tsv"))
        .map_err(|e| format!("{}: {e}", snap.join("stand.tsv").display()))?;
    // Der eigene Zeitpunkt: der Archivname soll diesen Stand benennen, nicht
    // den Zeitpunkt des naechsten Snapshots.
    std::fs::write(snap.join("zeit"), format!("{jetzt}\n"))
        .map_err(|e| format!("{}: {e}", snap.join("zeit").display()))?;
    for (i, pfad) in dateien.iter().enumerate() {
        let quelle = Path::new(pfad);
        let sha = sha256_datei(quelle)
            .ok_or_else(|| format!("{pfad} nicht lesbar -- kein Snapshot"))?;
        let ziel = ablage.join(i.to_string());
        std::fs::copy(quelle, &ziel)
            .map_err(|e| format!("{pfad} -> {}: {e}", ziel.display()))?;
        // Prüfsumme der Kopie: Ein Snapshot, dem man nicht trauen kann, ist keiner.
        let nach = sha256_datei(&ziel).unwrap_or_default();
        if nach != sha {
            return Err(format!("Kopie von {pfad} weicht von der Quelle ab"));
        }
        writeln!(tsv, "{pfad}\t{sha}\t{i}").map_err(|e| e.to_string())?;
        stand.push(Dateistand { pfad: pfad.clone(), sha256: sha, nummer: i });
    }
    Ok(stand)
}

/// Dateien aus dem Snapshot zurückschreiben. Gibt die wiederhergestellten
/// Pfade zurück; jede Kopie wird vorher gegen ihre Prüfsumme geprüft.
pub fn zurueckrollen(dir: &Path) -> Result<Vec<String>, String> {
    let snap = dir.join(SNAPSHOT);
    let tsv = std::fs::read_to_string(snap.join("stand.tsv"))
        .map_err(|e| format!("kein Snapshot ({}): {e}", snap.join("stand.tsv").display()))?;
    let mut fertig = Vec::new();
    for zeile in tsv.lines().filter(|z| !z.trim().is_empty()) {
        let mut felder = zeile.split('\t');
        let (Some(pfad), Some(sha), Some(nummer)) = (felder.next(), felder.next(), felder.next())
        else {
            return Err(format!("stand.tsv unlesbar: {zeile}"));
        };
        let kopie = snap.join("dateien").join(nummer);
        let ist = sha256_datei(&kopie)
            .ok_or_else(|| format!("Kopie {} fehlt", kopie.display()))?;
        if ist != sha {
            return Err(format!("Kopie von {pfad} stimmt nicht mit der Pruefsumme ueberein"));
        }
        std::fs::copy(&kopie, pfad)
            .map_err(|e| format!("{pfad} zurueckschreiben: {e}"))?;
        fertig.push(pfad.to_string());
    }
    Ok(fertig)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn feld(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("chimera-neustart-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    fn datei(d: &Path, name: &str, inhalt: &str) -> String {
        let p = d.join(name);
        std::fs::write(&p, inhalt).unwrap();
        p.to_string_lossy().to_string()
    }

    #[test]
    fn marker_ueberlebt_schreiben_und_lesen() {
        let d = feld("marker");
        let m = Marker::neu(1_700_000_000, 2, "Ursache nennt Neustart",
                            vec!["dienste|chimera.service".into()],
                            vec![Dateistand { pfad: "/x/a.conf".into(), sha256: "ab".into(), nummer: 0 }]);
        marker_schreiben(&d, &m).unwrap();
        assert_eq!(marker_lesen(&d), Some(m));
        assert!(marker_pfad(&d).exists());
    }

    #[test]
    fn kaputter_marker_gilt_als_keiner() {
        let d = feld("marker-kaputt");
        std::fs::write(marker_pfad(&d), "{kein json").unwrap();
        assert_eq!(marker_lesen(&d), None);
        // JSON ohne Befundliste ist wertlos: ohne sie gibt es nichts zu vergleichen.
        std::fs::write(marker_pfad(&d), "{\"zeit\":1}").unwrap();
        assert_eq!(marker_lesen(&d), None);
    }

    #[test]
    fn sperre_nach_zwei_neustarts() {
        let mut m = Marker::neu(1, 0, "grund", vec![], vec![]);
        m.neustarts = 1;
        assert!(darf_neustarten(&m).is_ok());
        m.neustarts = NEUSTARTS_MAX;
        let fehler = darf_neustarten(&m).unwrap_err();
        assert!(fehler.contains("Sperre"), "{fehler}");
    }

    #[test]
    fn fortsetzung_vergleicht_die_befunde() {
        let m = Marker::neu(1, 0, "grund", vec!["a|b".into(), "c|d".into()], vec![]);
        assert_eq!(fortsetzung(&m, &["x|y".into()]), Ausgang::Erledigt);
        // Ein einzelner wiederkehrender Befund genuegt fuer den Rueckfall.
        assert_eq!(fortsetzung(&m, &["x|y".into(), "c|d".into()]), Ausgang::Rueckfall);
    }

    #[test]
    fn snapshot_sichert_nur_die_geaenderten_dateien() {
        let d = feld("snap");
        let a = datei(&d, "a.conf", "eins");
        let b = datei(&d, "b.conf", "zwei");
        let stand = snapshot_anlegen(&d, &[a.clone(), b.clone()], Some(500), 1000).unwrap();
        assert_eq!(stand.len(), 2);
        assert_eq!(stand[0].sha256, sha256_datei(Path::new(&a)).unwrap());
        assert!(d.join(SNAPSHOT).join("stand.tsv").exists());
        assert!(d.join(SNAPSHOT).join("dateien/1").exists());
    }

    #[test]
    fn zu_wenig_platz_heisst_kein_snapshot() {
        let d = feld("platz");
        let a = datei(&d, "a.conf", "eins");
        let fehler = snapshot_anlegen(&d, &[a], Some(PLATZ_MIN_MB - 1), 1000).unwrap_err();
        assert!(fehler.contains("zu wenig Platz"), "{fehler}");
        assert!(!d.join(SNAPSHOT).exists());
    }

    /// Eine Datei der gewuenschten Groesse, ohne sie zu schreiben (sparse).
    fn grosse_datei(d: &Path, name: &str, mb: u64) -> String {
        let p = d.join(name);
        let f = std::fs::File::create(&p).unwrap();
        f.set_len(mb * 1024 * 1024).unwrap();
        p.to_string_lossy().to_string()
    }

    // Die 100 MB sind eine Untergrenze, kein Bedarf: Ein Snapshot von 60 MB
    // braucht 120 MB frei (zwei Staende), auch wenn 100 "reichen" wuerden.
    #[test]
    fn platzbedarf_zaehlt_die_dateien_und_nicht_nur_die_untergrenze() {
        let d = feld("bedarf");
        let gross = grosse_datei(&d, "gross.bin", 60);
        assert_eq!(platzbedarf_mb(std::slice::from_ref(&gross)), Some(120));
    }

    #[test]
    fn platzbedarf_haelt_die_untergrenze_bei_kleinen_dateien() {
        let d = feld("bedarf-klein");
        let a = datei(&d, "a.conf", "eins");
        assert_eq!(platzbedarf_mb(&[a]), Some(PLATZ_MIN_MB));
    }

    // Groesse nicht lesbar -> Bedarf unbekannt. Dann gilt die Untergrenze,
    // und der Snapshot scheitert spaeter an der nicht lesbaren Datei --
    // geraten wird hier nichts.
    #[test]
    fn platzbedarf_ohne_lesbare_datei_ist_unbekannt() {
        assert_eq!(platzbedarf_mb(&["/gibt/es/nicht".to_string()]), None);
    }

    // Gegenprobe zum Bedarf: 110 MB frei reichen fuer 60 MB Dateien NICHT,
    // obwohl sie ueber der Untergrenze von 100 MB liegen. Und es entsteht
    // kein halber Snapshot.
    #[test]
    fn grosse_dateien_brauchen_mehr_als_die_untergrenze() {
        let d = feld("platz-gross");
        let gross = grosse_datei(&d, "gross.bin", 60);
        let fehler = snapshot_anlegen(&d, &[gross], Some(110), 1000).unwrap_err();
        assert!(fehler.contains("120 MB noetig"), "{fehler}");
        assert!(!d.join(SNAPSHOT).exists(), "kein halber Snapshot");
    }

    #[test]
    fn zurueckrollen_stellt_den_alten_inhalt_wieder_her() {
        let d = feld("rollback");
        let a = datei(&d, "a.conf", "original");
        snapshot_anlegen(&d, &[a.clone()], Some(500), 1000).unwrap();
        std::fs::write(&a, "verpfuscht").unwrap();
        let fertig = zurueckrollen(&d).unwrap();
        assert_eq!(fertig, vec![a.clone()]);
        assert_eq!(std::fs::read_to_string(&a).unwrap(), "original");
    }

    #[test]
    fn manipulierte_kopie_wird_nicht_zurueckgeschrieben() {
        let d = feld("manipuliert");
        let a = datei(&d, "a.conf", "original");
        snapshot_anlegen(&d, &[a.clone()], Some(500), 1000).unwrap();
        std::fs::write(d.join(SNAPSHOT).join("dateien/0"), "fremd").unwrap();
        std::fs::write(&a, "verpfuscht").unwrap();
        let fehler = zurueckrollen(&d).unwrap_err();
        assert!(fehler.contains("Pruefsumme"), "{fehler}");
        assert_eq!(std::fs::read_to_string(&a).unwrap(), "verpfuscht");
    }

    #[test]
    fn historie_1_haelt_ein_archiv() {
        let d = feld("historie");
        let a = datei(&d, "a.conf", "alt");
        snapshot_anlegen(&d, &[a.clone()], Some(500), 1000).unwrap();
        std::fs::write(&a, "neu").unwrap();
        snapshot_anlegen(&d, &[a.clone()], Some(500), 2000).unwrap();
        let archive: Vec<String> = std::fs::read_dir(&d)
            .unwrap()
            .flatten()
            .map(|e| e.file_name().to_string_lossy().to_string())
            .filter(|n| n.starts_with(&format!("{SNAPSHOT}-")))
            .collect();
        assert_eq!(archive, vec![format!("{SNAPSHOT}-1000")]);
        // Der neue Snapshot enthaelt den neuen Inhalt, das Archiv den alten.
        assert_eq!(std::fs::read_to_string(d.join(SNAPSHOT).join("dateien/0")).unwrap(), "neu");
        assert_eq!(std::fs::read_to_string(d.join(&archive[0]).join("dateien/0")).unwrap(), "alt");
    }

    #[test]
    fn ohne_dateien_gibt_es_nichts_zu_sichern() {
        let d = feld("leer");
        assert_eq!(snapshot_anlegen(&d, &[], Some(0), 1000).unwrap(), Vec::new());
        assert!(!d.join(SNAPSHOT).exists());
    }
}
