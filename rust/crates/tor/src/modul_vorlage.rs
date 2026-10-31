//! Vorlage fuer neue Web-Module und Pruefung vorhandener (DESIGN Regel 5v).
//!
//! `--module-neu <name>` setzt Variablen in die Vorlage ein und prueft das
//! Ergebnis mit demselben `web::manifest_lesen`, das auch beim Laden prueft --
//! Vorlage und Gateway koennen so nicht auseinanderlaufen. `--module-pruefen
//! <verzeichnis>` prueft ein vorhandenes Modul und nennt die Pruefsumme, die
//! der Nutzer bei der Freigabe sieht.

use crate::web;
use ring::digest;
use std::path::{Path, PathBuf};

const MANIFEST: &str = include_str!("../web/module/_vorlage/manifest.json");
const MODUL_JS: &str = include_str!("../web/module/_vorlage/modul.js");
pub const VARIABLEN_MD: &str = include_str!("../web/module/_vorlage/VARIABLEN.md");

#[derive(Debug, Clone, PartialEq)]
pub struct Eingabe {
    pub name: String,
    pub titel_de: String,
    pub titel_en: Option<String>,
    pub symbol: String,
    pub reihenfolge: i64,
    pub rechte: Vec<String>,
}

impl Eingabe {
    pub fn neu(name: &str) -> Eingabe {
        Eingabe { name: name.into(), titel_de: String::new(), titel_en: None, symbol: String::new(), reihenfolge: 100, rechte: Vec::new() }
    }
}

/// Ein Text, der in ein JSON-Feld und ein JS-Zeichenkettenliteral wandert:
/// keine Anfuehrungszeichen, Rueckstriche, Zeilenumbrueche, Steuerzeichen, `<`.
fn text_ok(s: &str) -> bool {
    s.chars().count() <= 64 && !s.chars().any(|c| c == '"' || c == '\\' || c == '`' || c == '<' || c == '$' || c.is_control())
}

/// `wetter-karte` -> `WetterKarte`.
pub fn klasse(name: &str) -> String {
    name.split('-')
        .filter(|t| !t.is_empty())
        .map(|t| {
            let mut c = t.chars();
            match c.next() {
                Some(f) => f.to_ascii_uppercase().to_string() + c.as_str(),
                None => String::new(),
            }
        })
        .collect()
}

fn einsetzen(vorlage: &str, e: &Eingabe) -> String {
    let rechte = e.rechte.iter().map(|r| format!("\"{r}\"")).collect::<Vec<_>>().join(", ");
    let titel_en = e.titel_en.clone().unwrap_or_else(|| e.titel_de.clone());
    vorlage
        .replace("{{NAME}}", &e.name)
        .replace("{{TITEL_DE}}", &e.titel_de)
        .replace("{{TITEL_EN}}", &titel_en)
        .replace("{{SYMBOL}}", &e.symbol)
        .replace("{{REIHENFOLGE}}", &e.reihenfolge.to_string())
        .replace("{{RECHTE}}", &rechte)
        .replace("{{KLASSE}}", &klasse(&e.name))
}

/// Erzeugt (Manifest, JavaScript) oder nennt den Grund, warum die Eingabe nicht geht.
pub fn erzeugen(e: &Eingabe) -> Result<(String, String), String> {
    if e.titel_de.trim().is_empty() {
        return Err("--titel-de fehlt".into());
    }
    for (feld, wert) in [("--titel-de", e.titel_de.as_str()), ("--titel-en", e.titel_en.as_deref().unwrap_or("")), ("--symbol", e.symbol.as_str())] {
        if !text_ok(wert) {
            return Err(format!("{feld}: unzulaessige Zeichen oder zu lang (kein \" \\ ` < $, keine Steuerzeichen, hoechstens 64)"));
        }
    }
    let manifest = einsetzen(MANIFEST, e);
    let js = einsetzen(MODUL_JS, e);
    // Pruefen mit demselben Code wie beim Laden.
    web::manifest_lesen(&e.name, &manifest, false).map_err(|f| format!("Manifest ungueltig: {f}"))?;
    if js.contains("{{") {
        return Err("JavaScript enthaelt noch einen Platzhalter".into());
    }
    Ok((manifest, js))
}

/// Legt `<ziel>/<name>/` an. Ein vorhandenes Verzeichnis wird nie ueberschrieben.
pub fn anlegen(e: &Eingabe, ziel: &Path) -> Result<PathBuf, String> {
    let (manifest, js) = erzeugen(e)?;
    let dir = ziel.join(&e.name);
    if dir.exists() {
        return Err(format!("{} gibt es schon; nichts ueberschrieben", dir.display()));
    }
    std::fs::create_dir_all(&dir).map_err(|x| format!("{}: {x}", dir.display()))?;
    std::fs::write(dir.join("manifest.json"), manifest).map_err(|x| x.to_string())?;
    std::fs::write(dir.join(format!("{}.js", e.name)), js).map_err(|x| x.to_string())?;
    Ok(dir)
}

/// SHA-256 ueber alle Dateien eines Verzeichnisses, unabhaengig von der
/// Reihenfolge des Dateisystems: Pfade sortiert, je Datei Name und Inhalt.
/// Aendert sich irgendeine Datei (oder kommt eine hinzu), aendert sich die Summe.
pub fn pruefsumme(dir: &Path) -> Result<String, String> {
    let mut dateien = Vec::new();
    sammeln(dir, dir, &mut dateien)?;
    dateien.sort();
    let mut ctx = digest::Context::new(&digest::SHA256);
    for rel in &dateien {
        let inhalt = std::fs::read(dir.join(rel)).map_err(|x| format!("{rel}: {x}"))?;
        // Laenge davor, damit Dateigrenzen nicht verschiebbar sind (a|bc != ab|c).
        ctx.update(&(rel.len() as u64).to_be_bytes());
        ctx.update(rel.as_bytes());
        ctx.update(&(inhalt.len() as u64).to_be_bytes());
        ctx.update(&inhalt);
    }
    Ok(ctx.finish().as_ref().iter().map(|b| format!("{b:02x}")).collect())
}

fn sammeln(wurzel: &Path, dir: &Path, aus: &mut Vec<String>) -> Result<(), String> {
    for e in std::fs::read_dir(dir).map_err(|x| format!("{}: {x}", dir.display()))?.flatten() {
        let p = e.path();
        let typ = e.file_type().map_err(|x| x.to_string())?;
        if typ.is_symlink() {
            // Ein Verweis koennte auf eine Datei ausserhalb zeigen: nicht folgen, aber melden.
            return Err(format!("{}: symbolischer Verweis nicht erlaubt", p.display()));
        }
        if typ.is_dir() {
            sammeln(wurzel, &p, aus)?;
        } else {
            let rel = p.strip_prefix(wurzel).map_err(|x| x.to_string())?.to_string_lossy().replace('\\', "/");
            aus.push(rel);
        }
    }
    Ok(())
}

/// Prueft ein Modulverzeichnis: Manifest gueltig, Einstieg vorhanden, Pruefsumme.
pub fn pruefen(dir: &Path) -> Result<serde_json::Value, String> {
    let name = dir.file_name().and_then(|n| n.to_str()).ok_or("Verzeichnisname nicht lesbar")?;
    let text = std::fs::read_to_string(dir.join("manifest.json")).map_err(|x| format!("manifest.json nicht lesbar: {x}"))?;
    let m = web::manifest_lesen(name, &text, false)?;
    if !dir.join(&m.einstieg).is_file() {
        return Err(format!("Einstiegsdatei '{}' fehlt", m.einstieg));
    }
    Ok(serde_json::json!({
        "ok": true, "name": m.name, "element": m.element, "rechte": m.rechte,
        "pruefsumme": pruefsumme(dir)?,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(n: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("chimera-vorlage-{}-{n}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    fn beispiel() -> Eingabe {
        // Die Beispielwerte aus VARIABLEN.md.
        Eingabe { name: "wetter".into(), titel_de: "Wetter".into(), titel_en: Some("Weather".into()), symbol: "🌤".into(), reihenfolge: 50, rechte: vec!["status".into()] }
    }

    #[test]
    fn die_beispielwerte_aus_der_doku_ergeben_ein_gueltiges_modul() {
        // Rechnet nichts nach: ruft dieselbe Pruefung wie das Gateway beim Laden.
        let d = tmp("beispiel");
        let dir = anlegen(&beispiel(), &d).unwrap();
        let r = pruefen(&dir).unwrap();
        assert_eq!(r["name"], "wetter");
        assert_eq!(r["element"], "chimera-wetter");
        assert_eq!(r["rechte"], serde_json::json!(["status"]));
        assert_eq!(r["pruefsumme"].as_str().unwrap().len(), 64);
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn die_doku_nennt_jede_variable_der_vorlage() {
        // Gegen "Vorlage bekommt eine Variable, die Doku kennt sie nicht".
        for v in ["{{NAME}}", "{{TITEL_DE}}", "{{TITEL_EN}}", "{{SYMBOL}}", "{{REIHENFOLGE}}", "{{RECHTE}}", "{{KLASSE}}"] {
            assert!(VARIABLEN_MD.contains(v), "{v} fehlt in VARIABLEN.md");
        }
        let mut alle = String::new();
        alle.push_str(MANIFEST);
        alle.push_str(MODUL_JS);
        let mut rest = alle.as_str();
        while let Some(i) = rest.find("{{") {
            let j = rest[i..].find("}}").expect("offene Variable") + i + 2;
            assert!(VARIABLEN_MD.contains(&rest[i..j]), "{} steht in der Vorlage, nicht in VARIABLEN.md", &rest[i..j]);
            rest = &rest[j..];
        }
    }

    #[test]
    fn ein_fehlender_oder_unzulaessiger_wert_wird_mit_grund_abgelehnt() {
        let mut e = beispiel();
        e.titel_de = String::new();
        assert!(erzeugen(&e).unwrap_err().contains("--titel-de"));
        let mut e = beispiel();
        e.titel_de = "Wetter\"; alert(1); \"".into();
        assert!(erzeugen(&e).unwrap_err().contains("unzulaessig"));
        let mut e = beispiel();
        e.symbol = "<b>".into();
        assert!(erzeugen(&e).is_err());
        let mut e = beispiel();
        e.name = "Gross".into();
        assert!(erzeugen(&e).unwrap_err().contains("Manifest ungueltig"));
        let mut e = beispiel();
        e.rechte = vec!["root".into()];
        assert!(erzeugen(&e).unwrap_err().contains("unbekanntes Recht"));
        let mut e = beispiel();
        e.titel_de = "x".repeat(65);
        assert!(erzeugen(&e).is_err());
    }

    #[test]
    fn die_vorlage_enthaelt_keine_ungeprueften_texte_im_javascript() {
        let (_, js) = erzeugen(&beispiel()).unwrap();
        assert!(js.contains("class ChimeraWetter extends HTMLElement"));
        assert!(js.contains("customElements.define(\"chimera-wetter\", ChimeraWetter)"));
        assert!(!js.contains("{{"));
    }

    #[test]
    fn klassenname_aus_dem_modulnamen() {
        assert_eq!(klasse("wetter"), "Wetter");
        assert_eq!(klasse("wetter-karte"), "WetterKarte");
        assert_eq!(klasse("a-1"), "A1");
    }

    #[test]
    fn ein_vorhandenes_verzeichnis_wird_nie_ueberschrieben() {
        let d = tmp("vorhanden");
        anlegen(&beispiel(), &d).unwrap();
        std::fs::write(d.join("wetter/eigene.txt"), "meins").unwrap();
        assert!(anlegen(&beispiel(), &d).unwrap_err().contains("schon"));
        assert_eq!(std::fs::read_to_string(d.join("wetter/eigene.txt")).unwrap(), "meins");
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn pruefsumme_aendert_sich_bei_jeder_aenderung_und_ist_sonst_stabil() {
        let d = tmp("summe");
        let dir = anlegen(&beispiel(), &d).unwrap();
        let s0 = pruefsumme(&dir).unwrap();
        assert_eq!(s0, pruefsumme(&dir).unwrap(), "stabil");
        // Inhalt geaendert
        std::fs::write(dir.join("wetter.js"), "//anders").unwrap();
        let s1 = pruefsumme(&dir).unwrap();
        assert_ne!(s0, s1);
        // Datei hinzu
        std::fs::write(dir.join("neu.js"), "").unwrap();
        let s2 = pruefsumme(&dir).unwrap();
        assert_ne!(s1, s2);
        // Datei umbenannt (gleicher Inhalt)
        std::fs::rename(dir.join("neu.js"), dir.join("neu2.js")).unwrap();
        assert_ne!(s2, pruefsumme(&dir).unwrap());
        // Datei in Unterverzeichnis zaehlt auch
        std::fs::create_dir_all(dir.join("u")).unwrap();
        let vor = pruefsumme(&dir).unwrap();
        std::fs::write(dir.join("u/x.js"), "a").unwrap();
        assert_ne!(vor, pruefsumme(&dir).unwrap());
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn dateigrenzen_sind_nicht_verschiebbar() {
        // "a"+"bc" darf nicht dieselbe Summe haben wie "ab"+"c".
        let (d1, d2) = (tmp("g1"), tmp("g2"));
        std::fs::write(d1.join("f1"), "a").unwrap();
        std::fs::write(d1.join("f2"), "bc").unwrap();
        std::fs::write(d2.join("f1"), "ab").unwrap();
        std::fs::write(d2.join("f2"), "c").unwrap();
        assert_ne!(pruefsumme(&d1).unwrap(), pruefsumme(&d2).unwrap());
        let _ = (std::fs::remove_dir_all(&d1), std::fs::remove_dir_all(&d2));
    }

    #[test]
    fn umbenennen_mit_gleicher_laenge_aendert_die_summe() {
        // Ohne den Namen im Hash wuerde nur die Laenge unterscheiden -- gleiche Laenge faellt durch.
        let d = tmp("gleichlang");
        std::fs::write(d.join("aaa.js"), "x").unwrap();
        let vor = pruefsumme(&d).unwrap();
        std::fs::rename(d.join("aaa.js"), d.join("bbb.js")).unwrap();
        assert_ne!(vor, pruefsumme(&d).unwrap());
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn eine_datei_kann_nicht_wie_zwei_dateien_aussehen() {
        // Gebaute Kollision: Der Inhalt einer Datei enthaelt exakt, was der Hash fuer eine
        // zweite Datei einspeisen wuerde. Ohne Inhaltslaenge waeren beide Summen gleich.
        let (einzeln, zwei) = (tmp("eins"), tmp("zwei"));
        std::fs::write(zwei.join("a"), "q").unwrap();
        std::fs::write(zwei.join("b"), "data").unwrap();
        let mut c = Vec::new();
        c.extend_from_slice(b"q");
        c.extend_from_slice(&1u64.to_be_bytes()); // Namenslaenge von "b"
        c.extend_from_slice(b"b");
        c.extend_from_slice(b"data");
        std::fs::write(einzeln.join("a"), &c).unwrap();
        assert_ne!(pruefsumme(&einzeln).unwrap(), pruefsumme(&zwei).unwrap());
        let _ = (std::fs::remove_dir_all(&einzeln), std::fs::remove_dir_all(&zwei));
    }

    #[test]
    fn ein_symbolischer_verweis_im_modul_wird_abgelehnt() {
        let d = tmp("verweis");
        let dir = anlegen(&beispiel(), &d).unwrap();
        std::os::unix::fs::symlink("/etc/passwd", dir.join("x.js")).unwrap();
        assert!(pruefsumme(&dir).unwrap_err().contains("symbolischer Verweis"));
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn pruefen_meldet_fehlenden_einstieg_und_falschen_verzeichnisnamen() {
        let d = tmp("pruef");
        let dir = anlegen(&beispiel(), &d).unwrap();
        std::fs::remove_file(dir.join("wetter.js")).unwrap();
        assert!(pruefen(&dir).unwrap_err().contains("fehlt"));
        let anders = d.join("anders");
        std::fs::rename(&dir, &anders).unwrap();
        assert!(pruefen(&anders).unwrap_err().contains("passt nicht zum Verzeichnis"));
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn die_mitgelieferte_vorlage_selbst_ist_kein_ladbares_modul() {
        // `_vorlage` hat Platzhalter im Namen und darf nie als Modul erscheinen.
        assert!(web::manifest_lesen("_vorlage", MANIFEST, false).is_err());
    }
}
