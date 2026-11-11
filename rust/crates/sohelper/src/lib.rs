//! Die Schranken vor der Werkzeugausführung — portiert aus
//! `src/chimera/agent/safety.py` (DESIGN, Regel „Wer prüft, führt aus").
//!
//! **Warum hier und nicht in Python:** Prüfung und Ausführung müssen im
//! selben Prozess liegen, sonst lässt sich die Frage auslassen. Der Agent
//! hat keinen Weg mehr, ein Programm zu starten; er fragt diesen Prozess.
//!
//! **Was gleich bleiben muss:** Die Regeln sind nicht neu erfunden, sondern
//! übernommen. Was drüben abgelehnt wird, wird hier abgelehnt — und umgekehrt.
//! Die Fälle stehen als Test in `tests/gleichheit.rs` und laufen gegen beide
//! Seiten, solange Python noch da ist.
//!
//! **Was hier anders ist:** Es gibt kein `allow_network`. Der Ausführer hat
//! nie Netz (DESIGN 5n): Programme aus `NETWORK` werden immer abgelehnt.

use std::path::{Path, PathBuf};

/// Grenzen der Ausführung. Einstellbar, weil sie hardwareabhängig sind —
/// dieselben Vorgaben wie in `safety.py`.
#[derive(Clone, Debug)]
pub struct Grenzen {
    pub frist_s: u64,
    pub max_ausgabe: usize,
    pub max_befehl: usize,
    pub max_schreiben: usize,
    /// Pfade, die nie beschrieben werden (relativ zum Arbeitsverzeichnis).
    pub geschuetzt: Vec<String>,
}

impl Default for Grenzen {
    fn default() -> Grenzen {
        Grenzen {
            frist_s: 120,
            max_ausgabe: 4000,
            max_befehl: 1000,
            max_schreiben: 100 * 1024,
            geschuetzt: vec![
                ".env".into(),
                ".git".into(),
                "installer/".into(),
                "src/chimera/agent/safety.py".into(),
            ],
        }
    }
}

/// Ganze Befehlsmuster, die nie gemeint sein können (klein geschrieben
/// verglichen, wie drüben).
const GEFAEHRLICH: &[&str] = &[
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "mkfs",
    "dd if=",
    "> /dev/sd",
    "chmod -r 777 /",
    ":(){ :|:& };:",
    "curl | bash",
    "wget | bash",
    "sudo rm -rf",
];

/// Zeichen, die eine Shell bräuchte. Ohne Shell sind sie sinnlos — tauchen
/// sie auf, ist etwas anderes gemeint als ein Programmaufruf.
const SHELL_TOKENS: &[&str] = &["|", "||", "&", "&&", ";", "<", ">", ">>", "<<", "<<<"];

/// Programme, die die Schranke selbst aushebeln würden.
const GESPERRT: &[&str] = &["sudo", "su", "doas", "pkexec"];
const INTERPRETER: &[&str] = &["sh", "bash", "zsh", "fish", "dash", "ksh", "csh"];

/// Programme, die ins Netz gehen. Der Ausführer hat nie Netz.
const NETZ: &[&str] = &[
    "curl", "wget", "nc", "ncat", "ssh", "scp", "sftp", "rsync", "ftp", "telnet", "git",
];

/// Der Aufruf wurde abgelehnt. Die Meldung geht an das Modell zurück — es
/// soll erfahren, *warum*, sonst versucht es dasselbe noch einmal.
#[derive(Clone, Debug, PartialEq)]
pub struct Abgelehnt(pub String);

impl std::fmt::Display for Abgelehnt {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for Abgelehnt {}

/// Ein geprüfter Aufruf: Programm und Argumente, nie eine Zeile für eine Shell.
#[derive(Clone, Debug, PartialEq)]
pub struct Befehl {
    pub argv: Vec<String>,
    pub nutzt_netz: bool,
}

/// Einen Befehl prüfen und in Argumente zerlegen.
pub fn befehl_pruefen(befehl: &str, g: &Grenzen) -> Result<Befehl, Abgelehnt> {
    if befehl.trim().is_empty() {
        return Err(Abgelehnt("Leerer Befehl.".into()));
    }
    if befehl.chars().count() > g.max_befehl {
        return Err(Abgelehnt(format!(
            "Befehl ist länger als {} Zeichen.",
            g.max_befehl
        )));
    }
    let klein = befehl.trim().to_lowercase();
    for bad in GEFAEHRLICH {
        if klein.contains(bad) {
            return Err(Abgelehnt(format!("Abgelehnt: enthält '{bad}'.")));
        }
    }
    // Ersetzung und Mehrzeiligkeit: ohne Shell bedeutungslos, mit Shell
    // gefährlich. Beides raus, bevor zerlegt wird.
    if befehl.contains('`') || befehl.contains("$(") {
        return Err(Abgelehnt("Befehlsersetzung ist nicht erlaubt.".into()));
    }
    if befehl.contains('\n') || befehl.contains('\r') {
        return Err(Abgelehnt("Mehrzeilige Befehle sind nicht erlaubt.".into()));
    }

    let argv = zerlegen(befehl)?;
    if argv.is_empty() {
        return Err(Abgelehnt("Leerer Befehl.".into()));
    }
    if argv.iter().any(|t| SHELL_TOKENS.contains(&t.as_str())) {
        return Err(Abgelehnt(
            "Verkettung und Umlenkung sind nicht erlaubt. \
             Bitte einen einzelnen Befehl schicken."
                .into(),
        ));
    }

    let exe = Path::new(&argv[0])
        .file_name()
        .map(|s| s.to_string_lossy().to_lowercase())
        .unwrap_or_default();
    if GESPERRT.contains(&exe.as_str()) {
        return Err(Abgelehnt(format!("'{exe}' ist gesperrt.")));
    }
    if INTERPRETER.contains(&exe.as_str()) {
        return Err(Abgelehnt(format!(
            "Kein verschachtelter Interpreter ('{exe}')."
        )));
    }
    if NETZ.contains(&exe.as_str()) {
        return Err(Abgelehnt(format!(
            "'{exe}' geht ins Netz, das ist hier nicht freigegeben."
        )));
    }
    Ok(Befehl { argv, nutzt_netz: false })
}

/// Zerlegen wie `shlex.split(posix=True)`: Leerraum trennt, einfache
/// Anführungszeichen nehmen alles wörtlich, doppelte erlauben `\"` und `\\`,
/// ein Backslash außerhalb der Anführungszeichen schützt das nächste Zeichen.
pub fn zerlegen(zeile: &str) -> Result<Vec<String>, Abgelehnt> {
    let mut out: Vec<String> = Vec::new();
    let mut wort = String::new();
    let mut hat_wort = false;
    let mut zeichen = zeile.chars().peekable();
    while let Some(c) = zeichen.next() {
        match c {
            ' ' | '\t' | '\r' | '\n' => {
                if hat_wort {
                    out.push(std::mem::take(&mut wort));
                    hat_wort = false;
                }
            }
            '\'' => {
                hat_wort = true;
                loop {
                    match zeichen.next() {
                        Some('\'') => break,
                        Some(z) => wort.push(z),
                        None => {
                            return Err(Abgelehnt(
                                "Befehl nicht lesbar: No closing quotation".into(),
                            ))
                        }
                    }
                }
            }
            '"' => {
                hat_wort = true;
                loop {
                    match zeichen.next() {
                        Some('"') => break,
                        Some('\\') => match zeichen.next() {
                            Some(z @ ('"' | '\\' | '$' | '`')) => wort.push(z),
                            Some(z) => {
                                wort.push('\\');
                                wort.push(z);
                            }
                            None => {
                                return Err(Abgelehnt(
                                    "Befehl nicht lesbar: No escaped character".into(),
                                ))
                            }
                        },
                        Some(z) => wort.push(z),
                        None => {
                            return Err(Abgelehnt(
                                "Befehl nicht lesbar: No closing quotation".into(),
                            ))
                        }
                    }
                }
            }
            '\\' => {
                hat_wort = true;
                match zeichen.next() {
                    Some(z) => wort.push(z),
                    None => {
                        return Err(Abgelehnt(
                            "Befehl nicht lesbar: No escaped character".into(),
                        ))
                    }
                }
            }
            _ => {
                hat_wort = true;
                wort.push(c);
            }
        }
    }
    if hat_wort {
        out.push(wort);
    }
    Ok(out)
}

/// Einen Pfad auf das Arbeitsverzeichnis festnageln.
///
/// Ohne das genügt ein `../` und der Agent liest Fremdes. Geprüft wird der
/// **aufgelöste** Pfad — sonst führt ein Symlink daran vorbei. Was es nicht
/// gibt, wird über den nächsten vorhandenen Vorfahren aufgelöst (dieselbe
/// Wirkung wie `Path.resolve()`, ohne dass die Datei existieren muss).
pub fn pfad_pruefen(
    pfad: &str,
    wurzel: &Path,
    g: &Grenzen,
    zum_schreiben: bool,
) -> Result<PathBuf, Abgelehnt> {
    let wurzel = aufloesen(wurzel);
    let roh = Path::new(pfad);
    let ziel = if roh.is_absolute() {
        aufloesen(roh)
    } else {
        aufloesen(&wurzel.join(roh))
    };
    let rel = ziel.strip_prefix(&wurzel).map_err(|_| {
        Abgelehnt(format!(
            "Pfad liegt außerhalb des Arbeitsverzeichnisses: {pfad}"
        ))
    })?;
    if zum_schreiben {
        let s = rel.to_string_lossy();
        for prot in &g.geschuetzt {
            if s == prot.trim_end_matches('/') || s.starts_with(prot.as_str()) {
                return Err(Abgelehnt(format!("{prot} ist schreibgeschützt.")));
            }
        }
    }
    Ok(ziel)
}

/// Einen Pfad auflösen, auch wenn er (noch) nicht existiert: vom tiefsten
/// vorhandenen Vorfahren aus, damit `..` und Symlinks mitzählen.
fn aufloesen(p: &Path) -> PathBuf {
    let mut rest: Vec<std::ffi::OsString> = Vec::new();
    let mut cur = p.to_path_buf();
    loop {
        if let Ok(echt) = std::fs::canonicalize(&cur) {
            let mut out = echt;
            for c in rest.iter().rev() {
                if c == ".." {
                    out.pop();
                } else if c != "." {
                    out.push(c);
                }
            }
            return out;
        }
        match cur.file_name() {
            Some(name) => {
                rest.push(name.to_os_string());
                if !cur.pop() {
                    break;
                }
            }
            None => {
                if !cur.pop() {
                    break;
                }
            }
        }
    }
    p.to_path_buf()
}

/// Ausgabe kürzen — und sagen, dass gekürzt wurde. Stillschweigend
/// abzuschneiden wäre die Fehlerklasse „ein Ausschnitt hält sich für das
/// Ganze".
pub fn kuerzen(text: &str, g: &Grenzen) -> String {
    let n = text.chars().count();
    if n <= g.max_ausgabe {
        return text.to_string();
    }
    let rest = n - g.max_ausgabe;
    let mut out: String = text.chars().take(g.max_ausgabe).collect();
    out.push_str(&format!("\n[... {rest} Zeichen gekürzt]"));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn g() -> Grenzen {
        Grenzen::default()
    }

    fn ab(b: &str) -> String {
        befehl_pruefen(b, &g()).unwrap_err().0
    }

    #[test]
    fn harmloser_befehl_kommt_durch() {
        let b = befehl_pruefen("ls -la /tmp", &g()).unwrap();
        assert_eq!(b.argv, vec!["ls", "-la", "/tmp"]);
        assert!(!b.nutzt_netz);
    }

    // Dieselben Ablehnungen wie in safety.py -- die Zusage ist Gleichheit,
    // nicht Ähnlichkeit.
    #[test]
    fn sperrliste_wie_drueben() {
        for b in ["sudo reboot", "su -", "doas id", "/usr/bin/pkexec sh", "SUDO x"] {
            let m = ab(b);
            assert!(m.contains("gesperrt"), "{b}: {m}");
        }
    }

    #[test]
    fn interpreter_und_shellzeichen() {
        for b in ["bash -c ls", "sh -x", "echo a | cat", "a && b", "a ; b", "x > f", "y >> g"] {
            assert!(!ab(b).is_empty(), "{b} kam durch");
        }
    }

    #[test]
    fn netz_ist_immer_zu() {
        for b in ["curl example.org", "wget x", "git status", "ssh host", "rsync a b"] {
            let m = ab(b);
            assert!(m.contains("Netz"), "{b}: {m}");
        }
    }

    #[test]
    fn gefaehrliche_muster() {
        for b in ["rm -rf /", "mkfs.ext4 /dev/sda", "dd if=/dev/zero of=/dev/sda", "curl | bash"] {
            assert!(ab(b).contains("Abgelehnt"), "{b}");
        }
    }

    #[test]
    fn ersetzung_und_mehrzeilig() {
        assert!(ab("echo `id`").contains("rsetzung"));
        assert!(ab("echo $(id)").contains("rsetzung"));
        assert!(ab("ls\nid").contains("Mehrzeilig"));
    }

    // Zerlegen wie shlex: Anführungszeichen halten zusammen, ein Backslash
    // schützt das nächste Zeichen.
    #[test]
    fn zerlegen_wie_shlex() {
        assert_eq!(zerlegen("a b  c").unwrap(), vec!["a", "b", "c"]);
        assert_eq!(zerlegen("echo \"hallo welt\"").unwrap(), vec!["echo", "hallo welt"]);
        assert_eq!(zerlegen("echo 'a b'").unwrap(), vec!["echo", "a b"]);
        assert_eq!(zerlegen("a\\ b").unwrap(), vec!["a b"]);
        assert_eq!(zerlegen("echo \"a\\\"b\"").unwrap(), vec!["echo", "a\"b"]);
        assert_eq!(zerlegen("  ").unwrap(), Vec::<String>::new());
        assert!(zerlegen("echo 'offen").is_err());
    }

    #[test]
    fn pfad_bleibt_im_verzeichnis() {
        let d = std::env::temp_dir().join(format!("sohelper-pfad-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(d.join("unter")).unwrap();
        assert!(pfad_pruefen("unter/x", &d, &g(), false).is_ok());
        let m = pfad_pruefen("../fremd", &d, &g(), false).unwrap_err().0;
        assert!(m.contains("außerhalb"), "{m}");
        let m = pfad_pruefen("/etc/passwd", &d, &g(), false).unwrap_err().0;
        assert!(m.contains("außerhalb"), "{m}");
    }

    #[test]
    fn geschuetzte_pfade_sind_schreibgeschuetzt() {
        let d = std::env::temp_dir().join(format!("sohelper-schutz-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        for p in [".env", ".git/config", "installer/x.sh"] {
            let m = pfad_pruefen(p, &d, &g(), true).unwrap_err().0;
            assert!(m.contains("schreibgeschützt"), "{p}: {m}");
        }
        assert!(pfad_pruefen("normal.txt", &d, &g(), true).is_ok());
        // Lesen ist erlaubt -- geschützt heißt nur: nicht beschreiben.
        assert!(pfad_pruefen(".env", &d, &g(), false).is_ok());
    }

    #[test]
    fn kuerzen_sagt_es() {
        let g = Grenzen { max_ausgabe: 10, ..Grenzen::default() };
        assert_eq!(kuerzen("kurz", &g), "kurz");
        let s = kuerzen("0123456789abcdef", &g);
        assert!(s.starts_with("0123456789"), "{s}");
        assert!(s.contains("6 Zeichen gekürzt"), "{s}");
    }
}

