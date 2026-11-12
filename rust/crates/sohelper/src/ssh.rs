//! Fernausführung: feste Form des `ssh`-Aufrufs (DESIGN, Regel „Jedes
//! Werkzeug bekommt nur seine Rechte", Abschnitt „Fernausführung").
//!
//! **Der Ausführer bekommt kein `argv`.** Er bekommt einen *Auftrag*
//! (Host-Name, Nutzer, Adresse, Port, Schlüsselname, Hostschlüssel-Zeile,
//! Befehl) und baut daraus **eine** Kommandozeile. Was nicht in diesem
//! Bauplan steht, kann nicht entstehen — `-D`, `-L`, `-R`, `-A`, ein freies
//! `-o` oder ein zweiter Host sind keine Optionen, die abgelehnt werden
//! müssten: sie haben keinen Platz, an dem sie stehen könnten.
//!
//! **Die Verbindung kommt als Deskriptor.** Das Gateway hat sie geöffnet und
//! per `SCM_RIGHTS` geschickt; `ProxyUseFdpass=yes` und
//! `ProxyCommand=chimera-fdpass 3` lassen `ssh` sie übernehmen. `ssh` selbst
//! kann keine zweite aufbauen: seine Umgebung ist `IPAddressDeny=any`
//! (Unit), nicht eine Zeile Code.
//!
//! **Der Hostschlüssel ist gepinnt.** Die erwartete Zeile kommt aus der
//! Host-Tabelle des Gateways (eine Wahrheit); sie wird hier in die
//! `known_hosts` geschrieben, gegen die `ssh` prüft.
//! `StrictHostKeyChecking=yes` heißt: passt sie nicht, bricht der Lauf ab und
//! meldet es. Kein `accept-new`, kein Nachfragen.

use serde_json::Value;
use std::path::{Path, PathBuf};

use crate::Abgelehnt;

/// Ein geprüfter Auftrag. Alle Felder sind schon durch die Form gegangen.
#[derive(Clone, Debug, PartialEq)]
pub struct Auftrag {
    pub host: String,
    pub nutzer: String,
    pub adresse: String,
    pub port: u16,
    pub schluessel: String,
    pub hostschluessel: String,
    pub befehl: String,
}

fn feld<'a>(wert: &'a Value, name: &str) -> Result<&'a str, Abgelehnt> {
    match wert.get(name).and_then(Value::as_str) {
        Some(t) if !t.trim().is_empty() => Ok(t.trim()),
        _ => Err(Abgelehnt(format!("ssh braucht ein Feld \"{name}\"."))),
    }
}

fn bezeichner(t: &str, was: &str, max: usize) -> Result<(), Abgelehnt> {
    if t.len() > max {
        return Err(Abgelehnt(format!("{was} ist länger als {max} Zeichen.")));
    }
    if t.starts_with('-') {
        return Err(Abgelehnt(format!("{was} darf nicht mit \"-\" beginnen (das wäre ein Argument).")));
    }
    Ok(())
}

/// Adresse: Name, IPv4 oder IPv6 (mit `:`). Leerraum und Schrägstrich sind
/// keine Adresse; ein führender Bindestrich wäre ein Argument.
pub fn adresse_ok(a: &str) -> bool {
    !a.is_empty()
        && a.len() <= 253
        && !a.starts_with('-')
        && a.chars().all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '-' || c == ':' || c == '_')
        && !a.contains("..")
}

pub fn nutzer_ok(n: &str) -> bool {
    !n.is_empty()
        && n.len() <= 32
        && n.chars().next().map(|c| c.is_ascii_alphanumeric() || c == '_').unwrap_or(false)
        && n.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
}

/// Der Schlüssel**name** aus dem Schlüsselordner — kein Pfad.
pub fn schluessel_ok(n: &str) -> bool {
    !n.is_empty()
        && n.len() <= 64
        && !n.starts_with('-')
        && n.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
        && !n.contains("..")
}

/// Die Hostschlüssel-Zeile, wie sie in `known_hosts` steht:
/// `<ziel> <typ> <blob>`. Das Ziel wird hier nicht geglaubt, sondern aus
/// Adresse und Port gebaut — eine Zeile für einen anderen Host wäre eine
/// stille Umleitung des Pins.
pub fn hostschluessel_zeile(adresse: &str, port: u16, typ: &str, blob: &str) -> String {
    let ziel = if port == 22 { adresse.to_string() } else { format!("[{adresse}]:{port}") };
    format!("{ziel} {typ} {blob}")
}

fn typ_ok(t: &str) -> bool {
    matches!(t, "ssh-ed25519" | "ssh-rsa" | "ecdsa-sha2-nistp256" | "ecdsa-sha2-nistp384" | "ecdsa-sha2-nistp521")
}

/// Der Auftrag aus der Anfrage — mit genau den Feldern, die es gibt.
pub fn auftrag_aus(wert: &Value) -> Result<Auftrag, Abgelehnt> {
    let host = feld(wert, "host")?;
    bezeichner(host, "Der Host-Name", 32)?;
    if !host.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-' || c == '_' || c == '.') {
        return Err(Abgelehnt(format!("Host-Name \"{host}\" ist kein Bezeichner (klein, Ziffern, - _ .).")));
    }
    let nutzer = feld(wert, "nutzer")?;
    if !nutzer_ok(nutzer) {
        return Err(Abgelehnt(format!("Nutzer \"{nutzer}\" ist kein Nutzername.")));
    }
    let adresse = feld(wert, "adresse")?;
    if !adresse_ok(adresse) {
        return Err(Abgelehnt(format!("Adresse \"{adresse}\" ist keine Adresse und kein Name.")));
    }
    let port = match wert.get("port") {
        None | Some(Value::Null) => 22u16,
        Some(v) => match v.as_u64() {
            Some(n) if (1..=65535).contains(&n) => n as u16,
            _ => return Err(Abgelehnt(format!("\"port\" braucht eine Zahl zwischen 1 und 65535 (bekam {v})."))),
        },
    };
    let schluessel = feld(wert, "schluessel")?;
    if !schluessel_ok(schluessel) {
        return Err(Abgelehnt(format!(
            "Schlüssel \"{schluessel}\": nur ein Name aus dem Schlüsselordner, kein Pfad."
        )));
    }
    let typ = feld(wert, "hostschluessel_typ")?;
    if !typ_ok(typ) {
        return Err(Abgelehnt(format!("Hostschlüssel-Typ \"{typ}\" ist unbekannt.")));
    }
    let blob = feld(wert, "hostschluessel")?;
    if blob.len() > 4096 || !blob.chars().all(|c| c.is_ascii_alphanumeric() || c == '+' || c == '/' || c == '=') {
        return Err(Abgelehnt("Der Hostschlüssel ist kein base64-Blob.".into()));
    }
    let befehl = feld(wert, "befehl")?;
    if befehl.len() > 4096 {
        return Err(Abgelehnt("Der Befehl ist länger als 4096 Zeichen.".into()));
    }
    if befehl.chars().any(|c| c.is_control() || c == '\0') {
        return Err(Abgelehnt("Der Befehl enthält Steuerzeichen.".into()));
    }
    Ok(Auftrag {
        host: host.to_string(),
        nutzer: nutzer.to_string(),
        adresse: adresse.to_string(),
        port,
        schluessel: schluessel.to_string(),
        hostschluessel: hostschluessel_zeile(adresse, port, typ, blob),
        befehl: befehl.to_string(),
    })
}

/// Die **eine** Kommandozeile. Jedes Element steht hier; es gibt keinen Weg,
/// ein weiteres einzuschmuggeln.
///
/// `ProxyCommand` nennt den Übergabe-Socket: `ssh` gibt dem Proxy nur stdin
/// und schließt alles ab 3, deshalb holt `chimera-fdpass` die Verbindung dort
/// ab (gemessen 12.11.2026, siehe `fdpass_main.rs`).
pub fn argv(a: &Auftrag, keydir: &Path, known_hosts: &Path, fdpass: &Path, uebergabe: Option<&Path>) -> Vec<String> {
    let s = |p: &Path| p.display().to_string();
    vec![
        "ssh".to_string(),
        "-T".into(),
        "-o".into(),
        "BatchMode=yes".into(),
        "-o".into(),
        "StrictHostKeyChecking=yes".into(),
        "-o".into(),
        format!("UserKnownHostsFile={}", s(known_hosts)),
        "-o".into(),
        "ProxyUseFdpass=yes".into(),
        "-o".into(),
        format!("ProxyCommand={} {}", s(fdpass), uebergabe.map(|p| s(p)).unwrap_or_default()),
        "-i".into(),
        s(&keydir.join(&a.schluessel)),
        "-l".into(),
        a.nutzer.clone(),
        "-p".into(),
        a.port.to_string(),
        a.adresse.clone(),
        "--".into(),
        a.befehl.clone(),
    ]
}

/// Wo die Schlüssel liegen (unterhalb des Arbeitsordners, nichts darüber
/// hinaus) und wo die `known_hosts` dieses Laufs hinschreibt.
pub fn ordner(arbeit: &Path) -> (PathBuf, PathBuf) {
    let wurzel = arbeit.join("ssh");
    (wurzel.join("keys"), wurzel.join("known_hosts"))
}

/// Die `known_hosts` schreiben: 0600, atomar, nur die eine Zeile. Die Datei
/// entsteht je Lauf neu aus der Tabelle — es gibt keinen zweiten Ort, der
/// veralten könnte.
pub fn known_hosts_schreiben(ziel: &Path, zeile: &str) -> std::io::Result<()> {
    if let Some(dir) = ziel.parent() {
        std::fs::create_dir_all(dir)?;
        let mut rechte = std::fs::metadata(dir)?.permissions();
        use std::os::unix::fs::PermissionsExt;
        rechte.set_mode(0o700);
        let _ = std::fs::set_permissions(dir, rechte);
    }
    use std::os::unix::fs::OpenOptionsExt;
    let tmp = ziel.with_extension(format!("neu{}", std::process::id()));
    {
        let mut f = std::fs::OpenOptions::new()
            .create(true)
            .truncate(true)
            .write(true)
            .mode(0o600)
            .open(&tmp)?;
        use std::io::Write;
        f.write_all(zeile.as_bytes())?;
        f.write_all(b"\n")?;
        f.sync_all()?;
    }
    std::fs::rename(&tmp, ziel)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn anfrage() -> Value {
        json!({
            "op": "ssh", "host": "radxa", "nutzer": "dietpi", "adresse": "box.example",
            "port": 22, "schluessel": "radxa_ed25519",
            "hostschluessel_typ": "ssh-ed25519", "hostschluessel": "AAAA",
            "befehl": "uptime",
        })
    }

    #[test]
    fn argv_ist_fest_und_vollstaendig() {
        let a = auftrag_aus(&anfrage()).unwrap();
        let v = argv(&a, Path::new("/k"), Path::new("/k/known_hosts"), Path::new("/opt/chimera/bin/chimera-fdpass"), Some(Path::new("/k/uebergabe.sock")));
        assert_eq!(
            v,
            vec![
                "ssh", "-T",
                "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=yes",
                "-o", "UserKnownHostsFile=/k/known_hosts",
                "-o", "ProxyUseFdpass=yes",
                "-o", "ProxyCommand=/opt/chimera/bin/chimera-fdpass /k/uebergabe.sock",
                "-i", "/k/radxa_ed25519",
                "-l", "dietpi",
                "-p", "22",
                "box.example",
                "--", "uptime",
            ]
        );
    }

    #[test]
    fn ein_zweiter_host_ist_nicht_ausdrueckbar() {
        // Der Befehl steht als **ein** Argument hinter "--": was wie ein
        // zweiter Host aussieht, ist Inhalt des Befehls auf dem Ziel.
        let mut a = anfrage();
        a["befehl"] = json!("box2.example uptime");
        let o = auftrag_aus(&a).unwrap();
        let v = argv(&o, Path::new("/k"), Path::new("/k/kh"), Path::new("/f"), Some(Path::new("/k/u.sock")));
        assert_eq!(v[v.len() - 1], "box2.example uptime");
        assert_eq!(v.iter().filter(|x| *x == "--").count(), 1);
    }

    #[test]
    fn freie_optionen_werden_abgelehnt() {
        for (feld, wert) in [
            ("nutzer", "-oProxyCommand=boese"),
            ("adresse", "-L8080:localhost:80"),
            ("schluessel", "../etc/shadow"),
            ("host", "Mit Gross"),
            ("port", "0"),
            ("hostschluessel_typ", "ssh-dss-unsinn"),
            ("befehl", "a\nb"),
        ] {
            let mut a = anfrage();
            a[feld] = json!(wert);
            assert!(auftrag_aus(&a).is_err(), "{feld}={wert:?} wurde angenommen");
        }
    }

    #[test]
    fn die_known_hosts_zeile_baut_das_ziel_selbst() {
        let mut a = anfrage();
        a["adresse"] = json!("box.example");
        let o = auftrag_aus(&a).unwrap();
        assert_eq!(o.hostschluessel, "box.example ssh-ed25519 AAAA");
        a["port"] = json!(2222);
        let o = auftrag_aus(&a).unwrap();
        assert_eq!(o.hostschluessel, "[box.example]:2222 ssh-ed25519 AAAA");
    }

    #[test]
    fn known_hosts_wird_0600_geschrieben_und_ersetzt() {
        let d = std::env::temp_dir().join(format!("chimera-kh-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let ziel = d.join("known_hosts");
        known_hosts_schreiben(&ziel, "box.example ssh-ed25519 AAAA").unwrap();
        let text = std::fs::read_to_string(&ziel).unwrap();
        assert_eq!(text, "box.example ssh-ed25519 AAAA\n");
        use std::os::unix::fs::PermissionsExt;
        let modus = std::fs::metadata(&ziel).unwrap().permissions().mode() & 0o777;
        assert_eq!(modus, 0o600);
        known_hosts_schreiben(&ziel, "zwei.example ssh-ed25519 BBBB").unwrap();
        assert_eq!(std::fs::read_to_string(&ziel).unwrap(), "zwei.example ssh-ed25519 BBBB\n");
    }
}
