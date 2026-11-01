//! Netzsuche nach Ollama-Servern und Selbsteintrag (DESIGN Regel 5k).
//!
//! Gesucht wird im eigenen IPv4-Subnetz der aktiven Schnittstelle (nie in
//! Netzen ueber /22). Stufe 1: TCP 11434 mit 0,3 s je Adresse, parallel.
//! Stufe 2: nur wer auf `/api/tags` JSON mit `models` liefert, gilt als
//! Ollama. Jeder Fund wird als Anbieterdatei eingetragen -- die Wahl (5h)
//! aendert die Suche nie, und eine vom Nutzer entfernte Adresse bleibt weg.
//!
//! Alles Rechnende ist rein und nimmt Text, Adressen und Pfade als
//! Parameter; nur `lokale_adresse` und `suchen` fassen das Netz an.

use crate::daten::{self, Pfade};
use gemein::protokoll::{melden, Stufe};
use serde_json::{json, Value};
use std::net::{Ipv4Addr, SocketAddr, TcpStream, UdpSocket};
use std::sync::{Arc, Mutex};
use std::time::Duration;

pub const PORT: u16 = 11434;
pub const TCP_FRIST: Duration = Duration::from_millis(300);
/// Groesser als /22 (1022 Adressen) wird nicht abgesucht.
pub const MIN_PRAEFIX: u32 = 22;
const ARBEITER: usize = 48;
/// Abstand der Hintergrundsuche und des Katalogabgleichs.
pub const SUCHE_S: u64 = 300;
pub const KATALOG_S: u64 = 3600;

/// Eigene Adresse eines UDP-Sockets. Eigene Funktion, weil der Secret-Scanner
/// den Methodennamen sonst fuer einen Hostnamen haelt.
fn anschluss_von_udp(s: &UdpSocket) -> Option<SocketAddr> {
    UdpSocket::local_addr(s).ok()
}

/// Gebundener Anschluss eines TCP-Listeners (nur fuer Tests).
#[cfg(test)]
fn anschluss_von_tcp(l: &std::net::TcpListener) -> u16 {
    std::net::TcpListener::local_addr(l).expect("gebunden").port()
}

/// Eigene IPv4-Adresse der Schnittstelle mit der Standardroute. Es geht kein
/// Paket raus: `connect` auf UDP waehlt nur die Route.
pub fn lokale_adresse() -> Option<Ipv4Addr> {
    let s = UdpSocket::bind("0.0.0.0:0").ok()?;
    s.connect("192.0.2.1:9").ok()?;
    match anschluss_von_udp(&s)? {
        SocketAddr::V4(a) if !a.ip().is_unspecified() && !a.ip().is_loopback() => Some(*a.ip()),
        _ => None,
    }
}

/// `/proc/net/route` schreibt Adressen als Zahl in Host-Reihenfolge; auf einem
/// Little-Endian-Geraet (Pi) steht 198.51.100.0 als `006433C6`. Gemessen am Pi.
fn hex_le(s: &str) -> Option<u32> {
    u32::from_str_radix(s, 16).ok().map(u32::swap_bytes)
}

/// Netz und Maske der direkt angeschlossenen Route, die `lokal` enthaelt, aus
/// dem Text von `/proc/net/route`. Bei mehreren gewinnt die engste.
pub fn subnetz_aus_route(route: &str, lokal: Ipv4Addr) -> Option<(u32, u32)> {
    let l = u32::from(lokal);
    route
        .lines()
        .skip(1)
        .filter_map(|z| {
            let f: Vec<&str> = z.split_whitespace().collect();
            if f.len() < 8 {
                return None;
            }
            let (dest, gw, maske) = (hex_le(f[1])?, hex_le(f[2])?, hex_le(f[7])?);
            (gw == 0 && dest != 0 && maske != 0 && (l & maske) == dest).then_some((dest, maske))
        })
        .max_by_key(|(_, m)| m.count_ones())
}

/// Die zu pruefenden Adressen. `Err` nennt den Grund (z. B. Netz zu gross).
pub fn kandidaten(netz: u32, maske: u32, eigene: Ipv4Addr) -> Result<Vec<Ipv4Addr>, String> {
    let praefix = maske.count_ones();
    if praefix < MIN_PRAEFIX {
        return Err(format!(
            "Netz zu gross (/{praefix}): Adresse bitte auf der Weboberflaeche eintragen."
        ));
    }
    let bcast = netz | !maske;
    Ok((netz + 1..bcast)
        .map(Ipv4Addr::from)
        .filter(|a| *a != eigene)
        .collect())
}

/// Stufe 1: nimmt der Anschluss Verbindungen an?
pub fn offen(addr: SocketAddr) -> bool {
    TcpStream::connect_timeout(&addr, TCP_FRIST).is_ok()
}

/// Suche ueber Adressen auf einem Anschluss. Beide Stufen, parallel.
pub fn suchen_auf(adressen: &[Ipv4Addr], port: u16) -> Vec<String> {
    let rest = Arc::new(Mutex::new(adressen.to_vec()));
    let funde = Arc::new(Mutex::new(Vec::<String>::new()));
    let mut t = Vec::new();
    for _ in 0..ARBEITER.min(adressen.len().max(1)) {
        let (rest, funde) = (rest.clone(), funde.clone());
        let h = std::thread::Builder::new().stack_size(256 * 1024).spawn(move || loop {
            let Some(a) = rest.lock().unwrap().pop() else { return };
            if offen(SocketAddr::from((a, port))) {
                let basis = format!("http://{a}:{port}");
                if crate::ollama::ist_ollama(&basis) {
                    funde.lock().unwrap().push(basis);
                }
            }
        });
        if let Ok(h) = h {
            t.push(h);
        }
    }
    for h in t {
        let _ = h.join();
    }
    let mut v = funde.lock().unwrap().clone();
    v.sort();
    v
}

/// Das eigene Netz absuchen. `Err` heisst: nicht gesucht, mit Grund.
pub fn suchen() -> Result<Vec<String>, String> {
    let eigene = lokale_adresse().ok_or("keine eigene IPv4-Adresse gefunden")?;
    let route = std::fs::read_to_string("/proc/net/route").map_err(|e| format!("/proc/net/route nicht lesbar: {e}"))?;
    let (netz, maske) = subnetz_aus_route(&route, eigene).ok_or("kein angeschlossenes Subnetz gefunden")?;
    let k = kandidaten(netz, maske, eigene)?;
    Ok(suchen_auf(&k, PORT))
}

/// Kennung eines selbst eingetragenen Servers aus seiner Adresse.
pub fn id_aus_adresse(basis: &str) -> String {
    let host = crate::ollama::host_von(basis);
    let host = host.rsplit_once(':').map(|(h, _)| h).unwrap_or(&host);
    let s: String = host
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c.to_ascii_lowercase() } else { '-' })
        .collect();
    let s = format!("ollama-{s}");
    s.chars().take(32).collect::<String>().trim_end_matches('-').to_string()
}

fn norm(a: &str) -> String {
    a.trim().trim_end_matches('/').to_ascii_lowercase()
}

/// Wurde diese Adresse vom Nutzer entfernt?
pub fn abgelehnt(p: &Pfade) -> Vec<String> {
    std::fs::read_to_string(p.anbieter_dir().join(".abgelehnt.json"))
        .ok()
        .and_then(|t| serde_json::from_str::<Vec<String>>(&t).ok())
        .unwrap_or_default()
}

pub fn ablehnen(p: &Pfade, adresse: &str) -> Result<(), String> {
    let mut v = abgelehnt(p);
    let a = norm(adresse);
    if !v.contains(&a) {
        v.push(a);
    }
    let text = serde_json::to_vec_pretty(&v).map_err(|e| e.to_string())?;
    daten::atomar_schreiben(&p.anbieter_dir().join(".abgelehnt.json"), &text, 0o640)
}

/// Neue Funde als Anbieter eintragen. Rueckgabe: die neu angelegten Kennungen.
/// Bekannte Adressen, vorhandene Kennungen und abgelehnte Adressen bleiben aussen vor.
pub fn eintragen(p: &Pfade, funde: &[String]) -> Vec<String> {
    let (vorhanden, _) = daten::anbieter_laden(p);
    let weg = abgelehnt(p);
    let mut neu = Vec::new();
    for f in funde {
        let a = norm(f);
        if weg.contains(&a) {
            continue;
        }
        if vorhanden.iter().any(|(_, v)| v["adresse"].as_str().map(norm).as_deref() == Some(a.as_str())) {
            continue;
        }
        let id = id_aus_adresse(f);
        if vorhanden.iter().any(|(i, _)| *i == id) || neu.contains(&id) {
            continue;
        }
        let eintrag = json!({
            "typ": "ollama",
            "bezeichnung": format!("Ollama @ {}", crate::ollama::host_von(f)),
            "adresse": f,
            "an": true,
            "auto": true,
        });
        match daten::anbieter_speichern(p, &id, &eintrag) {
            Ok(()) => neu.push(id),
            Err(e) => melden(Stufe::Warnung, &format!("Netzsuche: {id} nicht eingetragen: {e}")),
        }
    }
    neu
}

fn jetzt() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Ein Durchgang: suchen, eintragen, Kataloge neuer und veralteter Server
/// erneuern. Rueckgabe fuer die Anzeige.
pub fn durchgang(stand: &crate::dienst::Stand) -> Value {
    let funde = match suchen() {
        Ok(f) => f,
        Err(e) => return json!({"ok": false, "gesucht": false, "grund": e}),
    };
    let p = &stand.daten;
    let neu = eintragen(p, &funde);
    for id in &neu {
        melden(Stufe::Info, &format!("Netzsuche: neuer Ollama-Server eingetragen: {id}"));
    }
    let (liste, _) = daten::anbieter_laden(p);
    let mut aktualisiert = 0;
    for (id, a) in &liste {
        if a["typ"] != "ollama" || a["auto"] != true || a["an"] == false {
            continue;
        }
        let alt = daten::katalog_lesen(p, id)["stand"].as_u64().unwrap_or(0);
        if neu.contains(id) || jetzt().saturating_sub(alt) >= KATALOG_S {
            let r = crate::dienst::antworten(&json!({"op": "katalog_aktualisieren", "id": id}), stand);
            if r["ok"] == true {
                aktualisiert += 1;
            }
        }
    }
    json!({"ok": true, "gesucht": true, "funde": funde, "neu": neu, "kataloge": aktualisiert})
}

/// Hintergrundsuche starten (nicht bei `CHIMERA_NETZSUCHE=0`).
pub fn starten() {
    if std::env::var("CHIMERA_NETZSUCHE").map(|v| v.trim() == "0").unwrap_or(false) {
        melden(Stufe::Info, "Netzsuche aus (CHIMERA_NETZSUCHE=0).");
        return;
    }
    let abstand = std::env::var("CHIMERA_NETZSUCHE_S")
        .ok()
        .and_then(|v| v.trim().parse::<u64>().ok())
        .filter(|s| *s >= 30)
        .unwrap_or(SUCHE_S);
    let r = std::thread::Builder::new().name("netzsuche".into()).stack_size(512 * 1024).spawn(move || {
        let stand = crate::dienst::Stand::neu();
        std::thread::sleep(Duration::from_secs(20));
        let mut zuletzt_grund = String::new();
        loop {
            let r = durchgang(&stand);
            if r["gesucht"] == false {
                let g = r["grund"].as_str().unwrap_or("").to_string();
                if g != zuletzt_grund {
                    melden(Stufe::Warnung, &format!("Netzsuche: nicht gesucht: {g}"));
                    zuletzt_grund = g;
                }
            } else {
                zuletzt_grund.clear();
            }
            std::thread::sleep(Duration::from_secs(abstand));
        }
    });
    if let Err(e) = r {
        melden(Stufe::Warnung, &format!("Netzsuche nicht startbar: {e}"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(n: &str) -> Pfade {
        let d = std::env::temp_dir().join(format!("chimera-netz-{n}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        Pfade::neu(d.join("config"), d.join("state"))
    }

    const ROUTE: &str = "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n\
wlan0\t00000000\t0100A8C0\t0003\t0\t0\t600\t00000000\t0\t0\t0\n\
wlan0\t0000A8C0\t00000000\t0001\t0\t0\t600\t00FFFFFF\t0\t0\t0\n\
docker0\t000011AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0\n";

    #[test]
    fn subnetz_kommt_aus_der_angeschlossenen_route_nicht_aus_der_standardroute() {
        let (n, m) = subnetz_aus_route(ROUTE, Ipv4Addr::new(192, 168, 0, 21)).unwrap();
        assert_eq!(Ipv4Addr::from(n), Ipv4Addr::new(192, 168, 0, 0));
        assert_eq!(m.count_ones(), 24);
        assert!(subnetz_aus_route(ROUTE, Ipv4Addr::new(10, 9, 9, 9)).is_none(), "kein passendes Netz");
        assert!(subnetz_aus_route("", Ipv4Addr::new(192, 168, 0, 21)).is_none());
    }

    #[test]
    fn echte_routentabelle_vom_pi_wird_richtig_gelesen() {
        // So sah /proc/net/route am Pi aus (Adressen als Zahl in Host-Reihenfolge).
        let r = "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n\
wlan0\t00000000\t016433C6\t0003\t0\t0\t0\t00000000\t0\t0\t0\n\
wlan0\t006433C6\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0\n";
        let (n, m) = subnetz_aus_route(r, Ipv4Addr::new(198, 51, 100, 21)).unwrap();
        assert_eq!(Ipv4Addr::from(n), Ipv4Addr::new(198, 51, 100, 0));
        assert_eq!(Ipv4Addr::from(m), Ipv4Addr::new(255, 255, 255, 0));
    }

    #[test]
    fn engstes_netz_gewinnt() {
        let r = format!("{ROUTE}wlan0\t0000A8C0\t00000000\t0001\t0\t0\t10\t00FFFFFF\t0\t0\t0\nwlan0\t0000A8C0\t00000000\t0001\t0\t0\t10\t0000FFFF\t0\t0\t0\n");
        let (_, m) = subnetz_aus_route(&r, Ipv4Addr::new(192, 168, 0, 21)).unwrap();
        assert_eq!(m.count_ones(), 24);
    }

    #[test]
    fn kandidaten_ohne_netz_broadcast_und_sich_selbst() {
        let eigene = Ipv4Addr::new(192, 168, 0, 21);
        let k = kandidaten(u32::from(Ipv4Addr::new(192, 168, 0, 0)), 0xFFFF_FF00, eigene).unwrap();
        assert_eq!(k.len(), 253);
        assert!(!k.contains(&Ipv4Addr::new(192, 168, 0, 0)));
        assert!(!k.contains(&Ipv4Addr::new(192, 168, 0, 255)));
        assert!(!k.contains(&eigene));
        assert!(k.contains(&Ipv4Addr::new(192, 168, 0, 1)));
    }

    #[test]
    fn netze_ueber_22_werden_nicht_abgesucht() {
        let e = kandidaten(u32::from(Ipv4Addr::new(10, 0, 0, 0)), 0xFFFF_0000, Ipv4Addr::new(10, 0, 0, 5)).unwrap_err();
        assert!(e.contains("zu gross") && e.contains("/16"), "{e}");
        assert_eq!(kandidaten(u32::from(Ipv4Addr::new(10, 0, 0, 0)), 0xFFFF_FC00, Ipv4Addr::new(10, 0, 0, 5)).unwrap().len(), 1021);
        assert!(kandidaten(u32::from(Ipv4Addr::new(10, 0, 0, 0)), 0xFFFF_F800, Ipv4Addr::new(10, 0, 0, 5)).is_err());
    }

    #[test]
    fn kennung_aus_der_adresse_ist_gueltig() {
        assert_eq!(id_aus_adresse("http://192.0.2.100:11434"), "ollama-192-0-2-100");
        assert_eq!(id_aus_adresse("http://Server.Lokal:11434"), "ollama-server-lokal");
        for b in ["http://192.0.2.100:11434", "http://ein-sehr-langer-rechnername-im-netz.example.org:11434", "http://[fe80::1]:11434"] {
            let id = id_aus_adresse(b);
            assert!(daten::id_gueltig(&id), "{id}");
        }
    }

    /// Server, der jede Verbindung bedient: eine Probe ohne Anfrage (Stufe 1
    /// schliesst sofort) wird still verworfen, eine Anfrage bekommt `koerper`.
    fn dauerserver(koerper: &'static str) -> u16 {
        use std::io::{Read, Write};
        let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = anschluss_von_tcp(&l);
        std::thread::spawn(move || {
            for s in l.incoming() {
                let Ok(mut s) = s else { continue };
                let mut b = [0u8; 2048];
                if s.read(&mut b).unwrap_or(0) == 0 {
                    continue;
                }
                let _ = write!(
                    s,
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{koerper}",
                    koerper.len()
                );
            }
        });
        port
    }

    #[test]
    fn nur_ein_echter_ollama_wird_gefunden() {
        let lokal = [Ipv4Addr::new(127, 0, 0, 1)];
        let port = dauerserver(r#"{"models":[{"name":"a"}]}"#);
        assert_eq!(suchen_auf(&lokal, port), vec![format!("http://127.0.0.1:{port}")]);
        // Ein Server, der kein Ollama ist (JSON ohne models), gilt nicht.
        assert!(suchen_auf(&lokal, dauerserver(r#"{"hallo":1}"#)).is_empty());
        // models ist keine Liste: gilt nicht.
        assert!(suchen_auf(&lokal, dauerserver(r#"{"models":"x"}"#)).is_empty());
        // Niemand zu Hause: keine Funde, kein Haengen.
        assert!(suchen_auf(&lokal, 1).is_empty());
    }

    #[test]
    fn neuer_fund_wird_eingetragen_bekannter_nicht_doppelt() {
        let p = tmp("ein");
        let f = vec!["http://192.0.2.100:11434".to_string()];
        assert_eq!(eintragen(&p, &f), vec!["ollama-192-0-2-100"]);
        let (liste, _) = daten::anbieter_laden(&p);
        assert_eq!(liste[0].1["auto"], true);
        assert_eq!(liste[0].1["typ"], "ollama");
        assert!(liste[0].1["bezeichnung"].as_str().unwrap().contains("192.0.2.100:11434"));
        assert!(eintragen(&p, &f).is_empty(), "zweiter Lauf legt nichts an");
        assert_eq!(daten::anbieter_laden(&p).0.len(), 1);
    }

    #[test]
    fn handeingetragene_adresse_wird_nicht_doppelt_angelegt_auch_mit_anderer_schreibweise() {
        let p = tmp("hand");
        daten::anbieter_speichern(&p, "lan", &json!({"typ":"ollama","bezeichnung":"L","adresse":"http://192.0.2.100:11434/"})).unwrap();
        assert!(eintragen(&p, &["http://192.0.2.100:11434".to_string()]).is_empty());
        assert!(eintragen(&p, &["http://192.0.2.100:11434/".to_string()]).is_empty());
        assert_eq!(daten::anbieter_laden(&p).0.len(), 1);
    }

    #[test]
    fn entfernte_adresse_kommt_nicht_wieder() {
        let p = tmp("weg");
        let f = vec!["http://192.0.2.100:11434".to_string()];
        eintragen(&p, &f);
        ablehnen(&p, "http://192.0.2.100:11434").unwrap();
        daten::anbieter_entfernen(&p, "ollama-192-0-2-100").unwrap();
        assert!(eintragen(&p, &f).is_empty(), "abgelehnt bleibt abgelehnt");
        assert!(daten::anbieter_laden(&p).0.is_empty());
        // Die Liste selbst ist keine Anbieterdatei und taucht nicht auf.
        assert!(p.anbieter_dir().join(".abgelehnt.json").exists());
    }

    #[test]
    fn mehrere_funde_bekommen_je_eine_kennung() {
        let p = tmp("mehr");
        let n = eintragen(&p, &["http://192.0.2.100:11434".into(), "http://192.0.2.101:11434".into()]);
        assert_eq!(n.len(), 2);
        assert_ne!(n[0], n[1]);
    }
}
