//! Tailscale lesen — **nur anzeigen, nie steuern** (DESIGN, „Fernausführung",
//! Abschnitt „Tailscale/Headscale").
//!
//! **Warum hier und nicht im Netzweg:** `tailscaled` braucht TUN und root und
//! läuft deshalb auf Betriebssystem-Ebene, nicht im Gateway. Chimera spricht
//! das Tailscale-Protokoll **nicht** selbst — das wäre derselbe Netzweg, den
//! die Fernausführung gerade aus dem Gateway herausgehalten hat. Gelesen wird
//! ausschließlich die **LocalAPI** über den Unix-Socket
//! (`/var/run/tailscale/tailscaled.sock`), und ausschließlich `GET`.
//!
//! **Opt-in:** Fehlt der Socket, ist das kein Fehler, sondern der Normalfall —
//! Tailscale ist eine Zutat, die der Nutzer dazunimmt. Die Zeile sagt das
//! dann im Klartext, statt „unbekannt" zu behaupten.

use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::time::{Duration, Instant};

use crate::status::{Stufe, Zeile};

/// Der LocalAPI-Socket, wie ihn das Paket anlegt.
pub const SOCKET: &str = "/var/run/tailscale/tailscaled.sock";

/// Wie lange eine Antwort gilt. Der Netzzustand ändert sich selten; die
/// Statusseite fragt alle 3 s.
const FRIST: Duration = Duration::from_secs(60);

/// Antwort des LocalAPI auf `GET /localapi/v0/status`, so weit wir sie lesen.
#[derive(Debug, Default, PartialEq)]
pub struct Zustand {
    /// `Running`, `Stopped`, `NeedsLogin`, `NeedsMachineAuth` …
    pub backend: String,
    pub hostname: String,
    pub adressen: Vec<String>,
    pub peers_gesamt: usize,
    pub peers_online: usize,
}

/// Den Status holen: erst verbinden, dann eine **einzige** Anfrage.
/// `Err` nennt den Grund im Klartext (die Zeile zeigt ihn).
pub fn holen(socket: &str) -> Result<Zustand, String> {
    let mut s = UnixStream::connect(socket).map_err(|e| format!("{socket}: {e}"))?;
    let _ = s.set_read_timeout(Some(Duration::from_secs(5)));
    let _ = s.set_write_timeout(Some(Duration::from_secs(5)));
    // `GET` und sonst nichts: Die LocalAPI kann auch ändern (POST). Was hier
    // steht, darf das nicht können.
    let anfrage = "GET /localapi/v0/status HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n";
    s.write_all(anfrage.as_bytes()).map_err(|e| format!("schreiben: {e}"))?;
    let mut roh = Vec::new();
    s.read_to_end(&mut roh).map_err(|e| format!("lesen: {e}"))?;
    let text = String::from_utf8_lossy(&roh);
    let (kopf, rumpf) = text.split_once("\r\n\r\n").ok_or("keine HTTP-Antwort")?;
    if !kopf.starts_with("HTTP/1.") {
        return Err("keine HTTP-Antwort".into());
    }
    let status: u16 = kopf
        .split_whitespace()
        .nth(1)
        .and_then(|n| n.parse().ok())
        .ok_or("kein Statuscode")?;
    if status != 200 {
        return Err(format!("LocalAPI antwortet {status}"));
    }
    let rumpf = if kopf.to_ascii_lowercase().contains("transfer-encoding: chunked") {
        entschunkeln(rumpf).ok_or("unlesbare Teilstuecke")?
    } else {
        rumpf.to_string()
    };
    let v: serde_json::Value = serde_json::from_str(rumpf.trim()).map_err(|e| format!("kein JSON: {e}"))?;
    Ok(aus_json(&v))
}

/// Aus der LocalAPI-Antwort das, was angezeigt wird. Bewusst **kein** ganzer
/// Durchstich: Der Status enthält Schlüssel, Adressen und Peer-Daten, die
/// niemand auf einer Statusseite braucht.
pub fn aus_json(v: &serde_json::Value) -> Zustand {
    let mut z = Zustand {
        backend: v["BackendState"].as_str().unwrap_or("unbekannt").to_string(),
        hostname: v["Self"]["HostName"].as_str().unwrap_or("").to_string(),
        ..Zustand::default()
    };
    if let Some(a) = v["Self"]["TailscaleIPs"].as_array() {
        z.adressen = a.iter().filter_map(|x| x.as_str()).map(str::to_string).collect();
    }
    if let Some(p) = v["Peer"].as_object() {
        z.peers_gesamt = p.len();
        z.peers_online = p.values().filter(|x| x["Online"].as_bool() == Some(true)).count();
    }
    z
}

/// `Transfer-Encoding: chunked` auflösen (die LocalAPI benutzt es).
fn entschunkeln(t: &str) -> Option<String> {
    let mut aus = String::new();
    let mut rest = t;
    loop {
        let (zeile, danach) = rest.split_once("\r\n")?;
        let groesse = usize::from_str_radix(zeile.trim(), 16).ok()?;
        if groesse == 0 {
            return Some(aus);
        }
        if danach.len() < groesse {
            return None;
        }
        aus.push_str(&danach[..groesse]);
        rest = danach[groesse..].strip_prefix("\r\n")?;
    }
}

/// Die Zeile für die Statusseite.
pub fn zeile(socket: &str) -> Zeile {
    let basis = |text: String, stufe: Stufe| Zeile {
        id: "tailnet".into(),
        gruppe: "Netz",
        titel: "Tailnet".into(),
        text,
        wert: None,
        einheit: "",
        anteil: None,
        stufe,
    };
    if !std::path::Path::new(socket).exists() {
        // Opt-in: nicht installiert ist kein Fehler.
        return basis("nicht eingerichtet (tailscaled läuft hier nicht)".into(), Stufe::Unbekannt);
    }
    match holen(socket) {
        Ok(z) => {
            let stufe = match z.backend.as_str() {
                "Running" => Stufe::Ok,
                "Stopped" => Stufe::Unbekannt,
                _ => Stufe::Warnung,
            };
            let ip = z.adressen.first().cloned().unwrap_or_default();
            let text = if z.peers_gesamt > 0 {
                format!("{} {}{} · {}/{} Peers online", z.backend, z.hostname, if ip.is_empty() { String::new() } else { format!(" {ip}") }, z.peers_online, z.peers_gesamt)
            } else {
                format!("{} {}{}", z.backend, z.hostname, if ip.is_empty() { String::new() } else { format!(" {ip}") })
            };
            basis(text, stufe)
        }
        Err(e) => basis(format!("nicht lesbar: {e}"), Stufe::Warnung),
    }
}

/// Sonde für die Statusseite — mit Frist, damit nicht alle 3 s ein
/// Socket-Aufruf nötig ist.
pub struct Tailnet {
    socket: String,
    stand: std::sync::Mutex<Option<(Instant, Zeile)>>,
}

impl Tailnet {
    pub fn neu(socket: &str) -> Tailnet {
        Tailnet { socket: socket.to_string(), stand: std::sync::Mutex::new(None) }
    }
}

impl crate::status::Sonde for Tailnet {
    fn messen(&self, _k: &crate::status::Kontext) -> Vec<Zeile> {
        let mut stand = match self.stand.lock() {
            Ok(s) => s,
            Err(_) => return vec![zeile(&self.socket)],
        };
        if let Some((zeit, z)) = stand.as_ref() {
            if zeit.elapsed() < FRIST {
                return vec![z.clone()];
            }
        }
        let z = zeile(&self.socket);
        *stand = Some((Instant::now(), z.clone()));
        vec![z]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn antwort(rumpf: &str, chunked: bool) -> String {
        if chunked {
            let mut s = String::from("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n");
            for stueck in rumpf.as_bytes().chunks(7) {
                s.push_str(&format!("{:x}\r\n{}\r\n", stueck.len(), String::from_utf8_lossy(stueck)));
            }
            s.push_str("0\r\n\r\n");
            s
        } else {
            format!("HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n{}", rumpf.len(), rumpf)
        }
    }

    /// Ein winziger LocalAPI-Ersatz auf einem Socket im Testordner.
    ///
    /// Der Listener wird **vor** dem Faden gebunden: sonst verbindet der Test
    /// sich, bevor jemand lauscht (`ENOENT`), und der Faden wartet danach für
    /// immer in `accept` — der Test hängt statt rot zu werden (am 13.11. genau
    /// so passiert, 1800 s Timeout).
    fn attrappe(listener: std::os::unix::net::UnixListener, antworttext: String) -> std::thread::JoinHandle<()> {
        std::thread::spawn(move || {
            if let Ok((mut c, _)) = listener.accept() {
                let mut puffer = [0u8; 1024];
                let _ = c.read(&mut puffer);
                let _ = c.write_all(antworttext.as_bytes());
            }
        })
    }

    fn lauscher(d: &std::path::Path) -> std::os::unix::net::UnixListener {
        std::os::unix::net::UnixListener::bind(d.join("s.sock")).unwrap()
    }

    fn ordner(n: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("ts-{}-{}", n, std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn der_status_wird_gelesen_und_gekuerzt() {
        let d = ordner("lesen");
        let pfad = d.join("s.sock");
        let l = lauscher(&d);
        let json = r#"{"BackendState":"Running","Self":{"HostName":"pi","TailscaleIPs":["100.64.0.7"]},
                       "Peer":{"a":{"Online":true},"b":{"Online":false}}}"#;
        let h = attrappe(l, antwort(json, false));
        let z = holen(pfad.to_str().unwrap()).unwrap();
        h.join().unwrap();
        assert_eq!(z.backend, "Running");
        assert_eq!(z.hostname, "pi");
        assert_eq!(z.adressen, vec!["100.64.0.7".to_string()]);
        assert_eq!((z.peers_online, z.peers_gesamt), (1, 2));
        // Kein ganzes Abbild: was nicht gebraucht wird, steht nicht drin.
        assert!(!format!("{z:?}").contains("Peer"));
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn teilstuecke_der_localapi_werden_ausgepackt() {
        let d = ordner("chunked");
        let pfad = d.join("s.sock");
        let l = lauscher(&d);
        let json = r#"{"BackendState":"NeedsLogin","Self":{"HostName":"pi"}}"#;
        let h = attrappe(l, antwort(json, true));
        let z = holen(pfad.to_str().unwrap()).unwrap();
        h.join().unwrap();
        assert_eq!(z.backend, "NeedsLogin");
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn ohne_socket_ist_die_zeile_ein_opt_out() {
        let z = zeile("/gibt/es/nicht.sock");
        assert_eq!(z.stufe, Stufe::Unbekannt);
        assert!(z.text.contains("nicht eingerichtet"), "{}", z.text);
        // Und mit Socket nennt sie den Zustand.
        let d = ordner("zeile");
        let pfad = d.join("s.sock");
        let l = lauscher(&d);
        let json = r#"{"BackendState":"Running","Self":{"HostName":"pi","TailscaleIPs":["100.64.0.7"]},"Peer":{}}"#;
        let h = attrappe(l, antwort(json, false));
        let z = zeile(pfad.to_str().unwrap());
        h.join().unwrap();
        assert_eq!(z.stufe, Stufe::Ok);
        assert!(z.text.contains("pi 100.64.0.7"), "{}", z.text);
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn ein_fehler_der_localapi_wird_nicht_als_zustand_verkauft() {
        let d = ordner("fehler");
        let pfad = d.join("s.sock");
        let l = lauscher(&d);
        let h = attrappe(l, "HTTP/1.1 403 Forbidden\r\nContent-Length: 2\r\n\r\n{}".into());
        let e = holen(pfad.to_str().unwrap()).unwrap_err();
        h.join().unwrap();
        assert!(e.contains("403"), "{e}");
        let _ = std::fs::remove_dir_all(&d);
    }
}
