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

/// Der Auftrag einer **Aufnahme**: derselbe Bauplan wie oben, aber ohne
/// Hostschluessel (der wird ja gerade erst geholt) und mit Passwort.
#[derive(Clone, Debug, PartialEq)]
pub struct Aufnahme {
    pub host: String,
    pub nutzer: String,
    pub adresse: String,
    pub port: u16,
    pub schluessel: String,
    pub rechte: String,
    pub zaun: Option<String>,
}

pub fn aufnahme_aus(wert: &Value) -> Result<Aufnahme, Abgelehnt> {
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
        return Err(Abgelehnt(format!("Schluessel \"{schluessel}\": nur ein Name aus dem Schluesselordner.")));
    }
    let rechte = wert.get("rechte").and_then(Value::as_str).unwrap_or("zaun").trim().to_string();
    if !matches!(rechte.as_str(), "zaun" | "force" | "voll") {
        return Err(Abgelehnt(format!("Rechte \"{rechte}\" gibt es nicht (zaun, force, voll).")));
    }
    let zaun = wert.get("zaun").and_then(Value::as_str).map(|z| z.trim().to_string()).filter(|z| !z.is_empty());
    Ok(Aufnahme { host: host.to_string(), nutzer: nutzer.to_string(), adresse: adresse.to_string(), port, schluessel: schluessel.to_string(), rechte, zaun })
}

impl Aufnahme {
    /// Fuer die gemeinsamen Bausteine (`argv_aufnahme` nimmt einen `Auftrag`).
    pub fn als_auftrag(&self) -> Auftrag {
        Auftrag {
            host: self.host.clone(),
            nutzer: self.nutzer.clone(),
            adresse: self.adresse.clone(),
            port: self.port,
            schluessel: self.schluessel.clone(),
            hostschluessel: String::new(),
            befehl: String::new(),
        }
    }
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

/// Die Kommandozeile der **Aufnahme**: Passwort-Anmeldung ohne TTY, mit
/// eigener `known_hosts`, in die der Hostschlüssel geschrieben wird.
///
/// Unterschiede zum Dauerbetrieb, und nur hier erlaubt:
/// `StrictHostKeyChecking=no` (der Schlüssel ist noch unbekannt),
/// `PreferredAuthentications=password` (es gibt noch kein Schlüsselpaar beim
/// Ziel) und `BatchMode=no`. Der Lauf endet, sobald die Zeile geschrieben
/// ist; danach gilt wieder der gepinnte Weg über `argv`.
pub fn argv_aufnahme(
    a: &Auftrag,
    known_hosts: &Path,
    fdpass: &Path,
    uebergabe: &Path,
    befehl: &str,
) -> Vec<String> {
    let s = |p: &Path| p.display().to_string();
    vec![
        "ssh".to_string(),
        "-T".into(),
        "-o".into(),
        "BatchMode=no".into(),
        "-o".into(),
        "StrictHostKeyChecking=no".into(),
        "-o".into(),
        format!("UserKnownHostsFile={}", s(known_hosts)),
        "-o".into(),
        "PreferredAuthentications=password".into(),
        "-o".into(),
        "PubkeyAuthentication=no".into(),
        "-o".into(),
        "NumberOfPasswordPrompts=1".into(),
        "-o".into(),
        "ProxyUseFdpass=yes".into(),
        "-o".into(),
        format!("ProxyCommand={} {}", s(fdpass), s(uebergabe)),
        "-l".into(),
        a.nutzer.clone(),
        "-p".into(),
        a.port.to_string(),
        a.adresse.clone(),
        "--".into(),
        befehl.to_string(),
    ]
}

/// Die `authorized_keys`-Zeile, die auf dem Ziel landet — **eine** Zeile,
/// sonst nichts (DESIGN, „Die Aufnahme schreibt genau eine Zeile").
///
/// `zaun` (Vorgabe) → `restrict`; `force` → `restrict,command="<pfad>"`;
/// `voll` → keine Optionen. Ein unbekannter Wert ist ein Fehler.
pub fn authorized_keys_zeile(typ: &str, blob: &str, rechte: &str, zaun: Option<&str>, kommentar: &str) -> Result<String, Abgelehnt> {
    if !typ_ok(typ) {
        return Err(Abgelehnt(format!("Hostschlüssel-Typ \"{typ}\" ist unbekannt.")));
    }
    if blob.is_empty() || blob.chars().any(|c| c.is_whitespace()) {
        return Err(Abgelehnt("Der öffentliche Schlüssel ist kein einzelner Blob.".into()));
    }
    let optionen = match rechte {
        "zaun" => "restrict".to_string(),
        "voll" => String::new(),
        "force" => {
            let Some(z) = zaun.map(str::trim).filter(|z| !z.is_empty()) else {
                return Err(Abgelehnt(
                    "force braucht einen Zaun-Pfad (zaun=\"/pfad/auf/dem/ziel\"): ohne ihn wäre die Zeile nur eine Weiterleitung.".into(),
                ));
            };
            // Im Pfad darf nichts stehen, was die Zeile zerlegt: Leerraum,
            // Anfuehrungszeichen, Komma.
            if z.len() > 200 || !z.starts_with('/') || z.chars().any(|c| c.is_whitespace() || c == '"' || c == ',' || c.is_control()) {
                return Err(Abgelehnt(format!(
                    "Der Zaun-Pfad \"{z}\" muss absolut sein und darf keinen Leerraum, kein \" und kein , enthalten."
                )));
            }
            format!("restrict,command=\"{z}\"")
        }
        andere => return Err(Abgelehnt(format!("Rechte \"{andere}\" gibt es nicht (zaun, force, voll)."))),
    };
    let kommentar = kommentar.trim();
    let k = if kommentar.is_empty() { String::new() } else { format!(" {kommentar}") };
    Ok(if optionen.is_empty() {
        format!("{typ} {blob}{k}")
    } else {
        format!("{optionen} {typ} {blob}{k}")
    })
}

/// Der Befehl auf dem Ziel: `~/.ssh` anlegen, die Zeile **einmal** eintragen,
/// Rechte setzen. Kein Skript, kein Dienst — nur diese Zeile.
///
/// `grep -qxF … || printf … >>` macht den Lauf wiederholbar: eine zweite
/// Aufnahme erzeugt keinen zweiten Eintrag.
pub fn aufnahme_befehl(zeile: &str) -> String {
    // Die Zeile steht in einfachen Anfuehrungszeichen; ein ' darin gibt es
    // nicht (Blob und Kommentar sind geprueft), aber sicher ist sicher.
    let z = zeile.replace('\'', "");
    format!(
        "set -e; mkdir -p ~/.ssh; chmod 700 ~/.ssh; touch ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys; grep -qxF '{z}' ~/.ssh/authorized_keys || printf '%s\\n' '{z}' >> ~/.ssh/authorized_keys; echo eingerichtet"
    )
}

/// Ein Schluesselpaar im Ordner des Ausfuehrers erzeugen (ed25519, ohne
/// Passphrase: ssh liest ihn ohne TTY) und den **oeffentlichen** Teil
/// zurueckgeben. Der private verlaesst den Ordner nie.
pub fn schluessel_erzeugen(keydir: &Path, name: &str, kommentar: &str) -> Result<String, String> {
    if !schluessel_ok(name) {
        return Err(format!("Schluesselname \"{name}\" ist kein Name."));
    }
    std::fs::create_dir_all(keydir).map_err(|e| format!("{}: {e}", keydir.display()))?;
    let pfad = keydir.join(name);
    if pfad.exists() {
        // Neu-Aufnahme (Ziel neu installiert, Zeile geloescht): derselbe
        // Schluessel wird weiterbenutzt, kein zweiter erzeugt. Der Name steht
        // je Host in der Tabelle -- ein fremdes Paar kann hier nicht landen.
        let oeffentlich = pfad.with_extension("pub");
        let text = std::fs::read_to_string(&oeffentlich)
            .map_err(|e| format!("Der Schluessel \"{name}\" liegt da, sein oeffentlicher Teil ist aber nicht lesbar: {e}"))?;
        let text = text.trim().to_string();
        if !text.starts_with("ssh-") && !text.starts_with("ecdsa-") {
            return Err(format!("\"{name}\" liegt da, ist aber kein oeffentlicher Schluessel."));
        }
        return Ok(text);
    }
    let o = std::process::Command::new("ssh-keygen")
        .args(["-q", "-t", "ed25519", "-N", "", "-C", kommentar, "-f"])
        .arg(&pfad)
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .output()
        .map_err(|e| format!("ssh-keygen nicht gestartet: {e}"))?;
    if !o.status.success() {
        let _ = std::fs::remove_file(&pfad);
        return Err(format!("ssh-keygen scheiterte: {}", String::from_utf8_lossy(&o.stderr).trim()));
    }
    // Rechte am Ergebnis pruefen, nicht annehmen.
    use std::os::unix::fs::PermissionsExt;
    if let Ok(m) = std::fs::metadata(&pfad) {
        if m.permissions().mode() & 0o077 != 0 {
            std::fs::set_permissions(&pfad, std::fs::Permissions::from_mode(0o600))
                .map_err(|e| format!("Rechte am Schluessel nicht setzbar: {e}"))?;
        }
    }
    std::fs::read_to_string(pfad.with_extension("pub"))
        .map(|t| t.trim().to_string())
        .map_err(|e| format!("oeffentlicher Schluessel nicht lesbar: {e}"))
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
    fn die_aufnahme_zeile_folgt_den_rechten() {
        // Vorgabe: ein Wort, sonst nichts.
        assert_eq!(
            authorized_keys_zeile("ssh-ed25519", "AAAA", "zaun", None, "chimera:radxa").unwrap(),
            "restrict ssh-ed25519 AAAA chimera:radxa"
        );
        // voll: gar keine Optionen (ssh-copy-id-Verhalten).
        assert_eq!(
            authorized_keys_zeile("ssh-ed25519", "AAAA", "voll", None, "").unwrap(),
            "ssh-ed25519 AAAA"
        );
        // force: nur mit Zaun-Pfad, und der wird geprueft.
        assert_eq!(
            authorized_keys_zeile("ssh-ed25519", "AAAA", "force", Some("/usr/local/bin/chimera-zaun"), "").unwrap(),
            "restrict,command=\"/usr/local/bin/chimera-zaun\" ssh-ed25519 AAAA"
        );
        assert!(authorized_keys_zeile("ssh-ed25519", "AAAA", "force", None, "").is_err());
        for boese in ["relativ/zaun", "/pfad mit leer", "/x\"y", "/x,y"] {
            assert!(authorized_keys_zeile("ssh-ed25519", "AAAA", "force", Some(boese), "").is_err(), "{boese}");
        }
        assert!(authorized_keys_zeile("ssh-ed25519", "AAAA", "rbash", None, "").is_err());
    }

    #[test]
    fn der_aufnahme_befehl_schreibt_genau_eine_zeile_und_ist_wiederholbar() {
        let z = authorized_keys_zeile("ssh-ed25519", "AAAA", "zaun", None, "chimera:radxa").unwrap();
        let b = aufnahme_befehl(&z);
        assert!(b.contains("mkdir -p ~/.ssh"));
        assert!(b.contains("chmod 700 ~/.ssh"));
        assert!(b.contains("chmod 600 ~/.ssh/authorized_keys"));
        // Kein doppelter Eintrag: erst pruefen, dann anhaengen.
        assert!(b.contains("grep -qxF 'restrict ssh-ed25519 AAAA chimera:radxa'"));
        assert!(b.contains("printf"));
        assert!(!b.contains("ssh-keygen"), "auf dem Ziel wird kein Schluessel erzeugt");
    }

    #[test]
    fn schluessel_entsteht_im_ordner_und_der_private_bleibt_dort() {
        let d = std::env::temp_dir().join(format!("chimera-keygen-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let pubkey = schluessel_erzeugen(&d, "testkey", "chimera:test").unwrap();
        assert!(pubkey.starts_with("ssh-ed25519 "), "{pubkey}");
        assert!(pubkey.ends_with("chimera:test"), "{pubkey}");
        use std::os::unix::fs::PermissionsExt;
        let privat = d.join("testkey");
        assert!(privat.is_file());
        assert_eq!(std::fs::metadata(&privat).unwrap().permissions().mode() & 0o777, 0o600);
        // Ein zweiter Lauf erzeugt keinen zweiten Schluessel, sondern nimmt
        // denselben (Neu-Aufnahme ist der Normalfall).
        let nochmal = schluessel_erzeugen(&d, "testkey", "x").unwrap();
        assert_eq!(nochmal, pubkey, "derselbe Schluessel, kein neuer");
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
