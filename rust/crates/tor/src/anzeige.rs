//! Anzeigespiegel lesen — das fertige Bild des Renderers für die Oberfläche.
//!
//! Entwurf: DESIGN, Regel „Anzeigespiegel". Dieses Modul **liest nur**. Es
//! öffnet die Datei, die der Renderer atomar umbenennt, deutet den Kopf und
//! gibt die Bytes weiter; geschrieben wird hier nie, und ins Panel schon
//! gar nicht (Regel 5m).
//!
//! Der Kopf ist absichtlich derselbe wie auf der Schreibseite
//! (`src/chimera/display/spiegel.py`): Kennung, Fassung, Format, Breite,
//! Höhe, Reserve, Zähler — Big-Endian, 20 Byte, danach 12 Byte Reserve,
//! zusammen 32 Byte. Die Pixel folgen unverändert als RGB565.

use std::io::Read;
use std::path::{Path, PathBuf};

/// Wie die Schreibseite: 4 Kennung + 1 Fassung + 1 Format + 2 Breite
/// + 2 Höhe + 2 Reserve + 8 Zähler + 12 Reserve.
pub const KOPF: usize = 32;
pub const MAGIC: &[u8; 4] = b"CHSP";
pub const VERSION: u8 = 1;
pub const FORMAT_RGB565_BE: u8 = 1;
/// Länge des gedeuteten Kopfes (ohne die Reserve dahinter).
pub const KOPF_FELDER: usize = 20;

/// Wo das Bild liegt. Übersteuerbar, damit Test und Messung nicht ins echte
/// Verzeichnis greifen müssen; der Vorgabewert ist der des Renderers.
pub fn pfad() -> PathBuf {
    std::env::var("CHIMERA_ANZEIGE_BILD")
        .ok()
        .filter(|p| !p.trim().is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/run/chimera/anzeige/bild"))
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Kopf {
    pub format: u8,
    pub breite: u16,
    pub hoehe: u16,
    pub zaehler: u64,
}

impl Kopf {
    /// Die erwartete Länge der Pixel — aus dem Kopf, nicht aus einer Annahme
    /// (Regel 6c: das Panel ist eine Eigenschaft, 240×280 ist nur die Vorgabe).
    pub fn pixel_laenge(&self) -> usize {
        self.breite as usize * self.hoehe as usize * 2
    }
}

/// Einen Kopf deuten. `None` heißt: keine Kennung, falsche Fassung oder zu
/// kurz — dann gibt es kein Bild (Regel 10g: nicht raten).
pub fn kopf_lesen(daten: &[u8]) -> Option<Kopf> {
    if daten.len() < KOPF_FELDER || &daten[0..4] != MAGIC {
        return None;
    }
    let fassung = daten[4];
    if fassung != VERSION {
        return None;
    }
    let format = daten[5];
    let breite = u16::from_be_bytes([daten[6], daten[7]]);
    let hoehe = u16::from_be_bytes([daten[8], daten[9]]);
    let mut z = [0u8; 8];
    z.copy_from_slice(&daten[12..20]);
    if breite == 0 || hoehe == 0 {
        return None;
    }
    Some(Kopf { format, breite, hoehe, zaehler: u64::from_be_bytes(z) })
}

/// Was beim Lesen herauskam.
#[derive(Debug)]
pub enum Gelesen {
    /// Der Zähler ist der angefragte — es gibt nichts zu senden.
    Unveraendert,
    /// Ein vollständiges Bild: Kopf plus Pixel, genau die Bytes der Datei.
    Bild { kopf: Kopf, daten: Vec<u8> },
}

/// Das Bild lesen. `seit` ist der Zähler, den der Aufrufer schon hat.
///
/// Der Zähler wird **vor** den Pixeln geprüft: Ist er gleich, wird der Rest
/// der Datei nicht angefasst. Bei einem neuen Bild wird alles in einem Zug
/// aus **einem** Deskriptor gelesen — der Renderer benennt atomar um, also
/// gehört der Deskriptor zu genau einem vollständigen Stand, auch wenn
/// inzwischen das nächste Bild entsteht.
pub fn lesen(datei: &Path, seit: u64) -> Result<Gelesen, String> {
    let mut f = std::fs::File::open(datei).map_err(|e| {
        format!("{} nicht lesbar: {e}", datei.display())
    })?;
    let mut kopf_roh = [0u8; KOPF];
    f.read_exact(&mut kopf_roh)
        .map_err(|e| format!("Kopf unvollständig: {e}"))?;
    let kopf = kopf_lesen(&kopf_roh)
        .ok_or_else(|| "kein gültiger Bildkopf (Kennung oder Fassung falsch)".to_string())?;
    if kopf.zaehler == seit {
        return Ok(Gelesen::Unveraendert);
    }
    let mut daten = Vec::with_capacity(KOPF + kopf.pixel_laenge());
    daten.extend_from_slice(&kopf_roh);
    let mut pixel = vec![0u8; kopf.pixel_laenge()];
    f.read_exact(&mut pixel)
        .map_err(|e| format!("Bild unvollständig ({e}) — Länge passt nicht zum Kopf"))?;
    daten.extend_from_slice(&pixel);
    Ok(Gelesen::Bild { kopf, daten })
}

/// Nur für Tests: einen Kopf wie die Schreibseite bauen.
#[cfg(test)]
pub fn kopf_bauen_fuer_test(breite: u16, hoehe: u16, zaehler: u64) -> Vec<u8> {
    let mut v = Vec::new();
    v.extend_from_slice(MAGIC);
    v.push(VERSION);
    v.push(FORMAT_RGB565_BE);
    v.extend_from_slice(&breite.to_be_bytes());
    v.extend_from_slice(&hoehe.to_be_bytes());
    v.extend_from_slice(&0u16.to_be_bytes());
    v.extend_from_slice(&zaehler.to_be_bytes());
    v.extend_from_slice(&[0u8; 12]);
    v
}

#[cfg(test)]
mod tests {
    use super::*;

    fn kopf_bytes(breite: u16, hoehe: u16, zaehler: u64) -> Vec<u8> {
        let mut v = Vec::new();
        v.extend_from_slice(MAGIC);
        v.push(VERSION);
        v.push(FORMAT_RGB565_BE);
        v.extend_from_slice(&breite.to_be_bytes());
        v.extend_from_slice(&hoehe.to_be_bytes());
        v.extend_from_slice(&0u16.to_be_bytes());
        v.extend_from_slice(&zaehler.to_be_bytes());
        v.extend_from_slice(&[0u8; 12]);
        assert_eq!(v.len(), KOPF);
        v
    }

    fn datei(name: &str, breite: u16, hoehe: u16, zaehler: u64) -> (PathBuf, Vec<u8>) {
        let d = std::env::temp_dir().join(format!("chimera-spiegel-{}-{name}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        let p = d.join("bild");
        let mut inhalt = kopf_bytes(breite, hoehe, zaehler);
        inhalt.extend(std::iter::repeat(0x5Au8).take(breite as usize * hoehe as usize * 2));
        std::fs::write(&p, &inhalt).unwrap();
        (p, inhalt)
    }

    #[test]
    fn kopf_wird_gedeutet() {
        let k = kopf_lesen(&kopf_bytes(240, 280, 7)).unwrap();
        assert_eq!(k, Kopf { format: FORMAT_RGB565_BE, breite: 240, hoehe: 280, zaehler: 7 });
        assert_eq!(k.pixel_laenge(), 134_400);
    }

    #[test]
    fn fremde_kennung_ist_kein_bild() {
        let mut v = kopf_bytes(240, 280, 1);
        v[0] = b'X';
        assert!(kopf_lesen(&v).is_none());
        // Gegenprobe: dasselbe mit richtiger Kennung wird gedeutet.
        v[0] = b'C';
        assert!(kopf_lesen(&v).is_some());
    }

    #[test]
    fn falsche_fassung_ist_kein_bild() {
        let mut v = kopf_bytes(240, 280, 1);
        v[4] = 2;
        assert!(kopf_lesen(&v).is_none());
    }

    #[test]
    fn gleicher_zaehler_liest_keine_pixel() {
        let (p, inhalt) = datei("gleich", 4, 4, 42);
        match lesen(&p, 42).unwrap() {
            Gelesen::Unveraendert => {}
            _ => panic!("gleicher Zähler muss unverändert heißen"),
        }
        // Gegenprobe: mit anderem Zähler kommt genau die Datei zurück.
        match lesen(&p, 41).unwrap() {
            Gelesen::Bild { kopf, daten } => {
                assert_eq!(kopf.zaehler, 42);
                assert_eq!(daten, inhalt);
            }
            _ => panic!("anderer Zähler muss ein Bild liefern"),
        }
    }

    #[test]
    fn abgeschnittenes_bild_ist_ein_fehler() {
        let (p, inhalt) = datei("kurz", 8, 8, 3);
        std::fs::write(&p, &inhalt[..inhalt.len() - 4]).unwrap();
        let e = lesen(&p, 0).unwrap_err();
        assert!(e.contains("unvollständig"), "Meldung nennt den Grund: {e}");
    }

    #[test]
    fn fehlende_datei_ist_ein_fehler_mit_pfad() {
        let p = std::env::temp_dir().join("chimera-spiegel-gibtsnicht/bild");
        let e = lesen(&p, 0).unwrap_err();
        assert!(e.contains("nicht lesbar"), "{e}");
    }

    #[test]
    fn masse_kommen_aus_dem_kopf() {
        // Ein 240×240-Panel (GamePi13) hat 115 200 Byte, nicht 134 400.
        let (p, _) = datei("gamepi", 240, 240, 1);
        match lesen(&p, 0).unwrap() {
            Gelesen::Bild { kopf, daten } => {
                assert_eq!(kopf.pixel_laenge(), 115_200);
                assert_eq!(daten.len(), KOPF + 115_200);
            }
            _ => panic!("Bild erwartet"),
        }
    }
}
