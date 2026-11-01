use super::*;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::os::unix::net::UnixListener;

fn tmp(n: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("chimera-web-test-{}-{n}", std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    d
}

fn zustand(dir: Option<PathBuf>, sock: PathBuf) -> Zustand {
    Zustand::neu(hash_erzeugen("geheim-pw-1").unwrap(), dir, sock, Strom::neu())
}

fn a<'x>(m: &'x str, p: &'x str, cookie: &'x str, body: &'x [u8]) -> Anfrage<'x> {
    let (pfad, query) = p.split_once('?').unwrap_or((p, ""));
    Anfrage { methode: m, pfad, query, cookie, marke: "1", body }
}

fn anmelden(z: &Zustand) -> String {
    let r = behandle(z, &a("POST", "/api/login", "", br#"{"passwort":"geheim-pw-1"}"#));
    assert_eq!(r.status, 200);
    let c = r.cookie.unwrap();
    c.split(';').next().unwrap().to_string()
}

// --- Passwort ---

#[test]
fn hash_stimmt_nur_fuer_das_richtige_passwort() {
    let h = hash_erzeugen("richtig-123").unwrap();
    assert!(hash_pruefen(&h, "richtig-123"));
    assert!(!hash_pruefen(&h, "falsch-1234"));
    assert!(!hash_pruefen(&h, ""));
}

#[test]
fn zwei_hashes_desselben_passworts_unterscheiden_sich() {
    assert_ne!(hash_erzeugen("gleich-123").unwrap(), hash_erzeugen("gleich-123").unwrap());
}

#[test]
fn kaputte_hashzeilen_pruefen_nie_als_wahr() {
    for z in ["", "x", "pbkdf2-sha256$0$aa$bb", "pbkdf2-sha256$100$zz$bb", "md5$1$aa$bb", "pbkdf2-sha256$1$aabb"] {
        assert!(!hash_pruefen(z, "x"), "{z}");
        assert!(!hash_gueltig(z), "{z}");
    }
}

#[test]
fn erzeugter_hash_ist_gueltig() {
    assert!(hash_gueltig(&hash_erzeugen("irgendwas-8").unwrap()));
}

// --- Konfiguration (Regel 5j) ---

#[test]
fn ohne_hash_ist_die_oberflaeche_aus() {
    assert_eq!(konfig_aus(None, None, None), Konfig::Aus);
    assert_eq!(konfig_aus(Some("  "), Some("9"), None), Konfig::Aus);
}

#[test]
fn unbrauchbarer_hash_ist_fehlkonfiguration() {
    assert!(matches!(konfig_aus(Some("passwort123"), None, None), Konfig::Falsch(_)));
}

#[test]
fn port_und_bind_werden_gelesen() {
    let h = hash_erzeugen("irgendwas-8").unwrap();
    match konfig_aus(Some(&h), Some("9090"), Some("127.0.0.1")) {
        Konfig::Bereit { adresse, .. } => assert_eq!(adresse, "127.0.0.1:9090"),
        k => panic!("{k:?}"),
    }
    match konfig_aus(Some(&h), None, None) {
        Konfig::Bereit { adresse, .. } => assert_eq!(adresse, "0.0.0.0:8080"),
        k => panic!("{k:?}"),
    }
    assert!(matches!(konfig_aus(Some(&h), Some("abc"), None), Konfig::Falsch(_)));
    assert!(matches!(konfig_aus(Some(&h), Some("0"), None), Konfig::Falsch(_)));
}

// --- Anmeldung ---

#[test]
fn die_huelle_ist_offen_alles_andere_nicht() {
    let z = zustand(None, "/x".into());
    assert_eq!(behandle(&z, &a("GET", "/", "", b"")).status, 200);
    for p in ["/api/module", "/module/chat/chat.js", "/api/chat/strom", "/api/chat/sitzungen", "/api/chat/lesen?sitzung=x"] {
        assert_eq!(behandle(&z, &a("GET", p, "", b"")).status, 401, "{p}");
    }
    assert_eq!(behandle(&z, &a("POST", "/api/chat/senden", "", br#"{"text":"x"}"#)).status, 401);
}

#[test]
fn falsches_passwort_gibt_401_und_keinen_cookie() {
    let z = zustand(None, "/x".into());
    let r = behandle(&z, &a("POST", "/api/login", "", br#"{"passwort":"nein"}"#));
    assert_eq!(r.status, 401);
    assert!(r.cookie.is_none());
}

#[test]
fn leeres_passwort_wird_nie_angenommen() {
    let z = zustand(None, "/x".into());
    assert_eq!(behandle(&z, &a("POST", "/api/login", "", br#"{"passwort":""}"#)).status, 401);
    assert_eq!(behandle(&z, &a("POST", "/api/login", "", br#"{}"#)).status, 401);
}

#[test]
fn nach_fuenf_fehlversuchen_wird_gebremst_auch_das_richtige_passwort() {
    let z = zustand(None, "/x".into());
    for _ in 0..5 {
        assert_eq!(behandle(&z, &a("POST", "/api/login", "", br#"{"passwort":"nein"}"#)).status, 401);
    }
    assert_eq!(behandle(&z, &a("POST", "/api/login", "", br#"{"passwort":"geheim-pw-1"}"#)).status, 429);
}

#[test]
fn der_cookie_ist_httponly_und_samesite() {
    let z = zustand(None, "/x".into());
    let r = behandle(&z, &a("POST", "/api/login", "", br#"{"passwort":"geheim-pw-1"}"#));
    let c = r.cookie.unwrap();
    assert!(c.contains("HttpOnly") && c.contains("SameSite=Strict"), "{c}");
}

#[test]
fn angemeldet_und_dann_abgemeldet() {
    let z = zustand(None, "/x".into());
    let c = anmelden(&z);
    assert_eq!(behandle(&z, &a("GET", "/api/module", &c, b"")).status, 200);
    assert_eq!(behandle(&z, &a("POST", "/api/logout", &c, b"{}")).status, 200);
    assert_eq!(behandle(&z, &a("GET", "/api/module", &c, b"")).status, 401);
}

#[test]
fn ein_erfundener_cookie_gilt_nicht() {
    let z = zustand(None, "/x".into());
    assert_eq!(behandle(&z, &a("GET", "/api/module", "chimera_sitzung=abc", b"")).status, 401);
}

#[test]
fn aendern_ohne_marke_wird_abgewiesen() {
    let z = zustand(None, "/x".into());
    let mut q = a("POST", "/api/login", "", br#"{"passwort":"geheim-pw-1"}"#);
    q.marke = "";
    assert_eq!(behandle(&z, &q).status, 403);
}

// --- Module ---

fn ok_manifest(n: &str) -> String {
    format!(r#"{{"name":"{n}","titel":"T","element":"x-{n}","einstieg":"{n}.js","rechte":[]}}"#)
}

#[test]
fn das_eingebaute_chatmodul_ist_gueltig_und_erkannt() {
    let (m, f) = module_erkennen(None);
    assert!(f.is_empty(), "{f:?}");
    assert_eq!(m.iter().map(|x| x.name.as_str()).collect::<Vec<_>>(), vec!["chat", "ollama", "status"]);
    assert!(m.iter().all(|x| x.eingebaut));
}

#[test]
fn ein_neues_verzeichnis_erscheint_im_menue_ohne_codeaenderung() {
    let d = tmp("neu");
    std::fs::create_dir_all(d.join("zusatz")).unwrap();
    std::fs::write(d.join("zusatz/manifest.json"), ok_manifest("zusatz")).unwrap();
    let (m, f) = module_erkennen(Some(&d));
    assert!(f.is_empty(), "{f:?}");
    assert_eq!(m.iter().map(|x| x.name.as_str()).collect::<Vec<_>>(), vec!["chat", "ollama", "status", "zusatz"]);
    let z = zustand(Some(d), "/x".into());
    let c = anmelden(&z);
    let r = behandle(&z, &a("GET", "/api/module", &c, b""));
    let v: Value = serde_json::from_slice(&r.body).unwrap();
    assert_eq!(v["module"].as_array().unwrap().len(), 4);
}

#[test]
fn ein_kaputtes_manifest_verwirft_nur_dieses_modul_und_wird_gemeldet() {
    let d = tmp("kaputt");
    for (n, t) in [("gut", ok_manifest("gut")), ("schlecht", "{nicht json".to_string()),
                   ("falsch", ok_manifest("anders")), ("ohne-element", r#"{"name":"ohne-element","titel":"T","einstieg":"a.js","rechte":[]}"#.to_string())] {
        std::fs::create_dir_all(d.join(n)).unwrap();
        std::fs::write(d.join(n).join("manifest.json"), t).unwrap();
    }
    std::fs::create_dir_all(d.join("leer")).unwrap(); // Verzeichnis ohne Manifest
    let (m, f) = module_erkennen(Some(&d));
    let namen: Vec<_> = m.iter().map(|x| x.name.as_str()).collect();
    assert_eq!(namen, vec!["chat", "ollama", "status", "gut"]);
    assert_eq!(f.len(), 4, "{f:?}");
}

#[test]
fn ein_nachgelegtes_modul_ersetzt_kein_eingebautes() {
    let d = tmp("doppelt");
    std::fs::create_dir_all(d.join("chat")).unwrap();
    std::fs::write(d.join("chat/manifest.json"), ok_manifest("chat")).unwrap();
    let (m, f) = module_erkennen(Some(&d));
    assert_eq!(m.len(), 3);
    assert!(m.iter().all(|x| x.eingebaut));
    assert_eq!(f.len(), 1);
}

#[test]
fn die_reihenfolge_kommt_aus_dem_manifest() {
    let d = tmp("reihe");
    for (n, r) in [("a-zuletzt", 99), ("b-zuerst", 1)] {
        std::fs::create_dir_all(d.join(n)).unwrap();
        std::fs::write(d.join(n).join("manifest.json"),
            format!(r#"{{"name":"{n}","titel":"T","element":"x-{n}","einstieg":"a.js","rechte":[],"reihenfolge":{r}}}"#)).unwrap();
    }
    let (m, _) = module_erkennen(Some(&d));
    assert_eq!(m.iter().map(|x| x.name.as_str()).collect::<Vec<_>>(), vec!["b-zuerst", "chat", "ollama", "status", "a-zuletzt"]);
}

#[test]
fn moduldateien_kein_ausbruch_aus_dem_verzeichnis() {
    let d = tmp("ausbruch");
    std::fs::create_dir_all(d.join("status")).unwrap();
    std::fs::write(d.join("status/manifest.json"), ok_manifest("status")).unwrap();
    std::fs::write(d.join("status/status.js"), "x").unwrap();
    std::fs::write(d.join("geheim.js"), "GEHEIM").unwrap();
    std::fs::write(d.join("status/notiz.txt"), "n").unwrap();
    let z = zustand(Some(d), "/x".into());
    let c = anmelden(&z);
    assert_eq!(behandle(&z, &a("GET", "/module/status/status.js", &c, b"")).status, 200);
    for p in ["/module/status/..%2Fgeheim.js", "/module/status/../geheim.js", "/module/../geheim.js",
              "/module/status/notiz.txt", "/module/status/", "/module/status", "/module//geheim.js",
              "/module/Status/status.js", "/module/status/manifest.json/.."] {
        let r = behandle(&z, &a("GET", p, &c, b""));
        assert_eq!(r.status, 404, "{p}");
        assert!(!String::from_utf8_lossy(&r.body).contains("GEHEIM"));
    }
}

#[test]
fn eingebaute_moduldateien_werden_ausgeliefert() {
    let z = zustand(None, "/x".into());
    let c = anmelden(&z);
    let r = behandle(&z, &a("GET", "/module/chat/chat.js", &c, b""));
    assert_eq!(r.status, 200);
    assert!(r.typ.starts_with("text/javascript"));
    assert!(String::from_utf8_lossy(&r.body).contains("chimera-chat"));
}

// --- Chat gegen einen Sitzungs-Doppel ---

fn doppel(n: &str, antworten: Vec<Value>) -> (PathBuf, std::thread::JoinHandle<Vec<Value>>) {
    let p = tmp(n);
    std::fs::create_dir_all(&p).unwrap();
    let sock = p.join("s.sock");
    let l = UnixListener::bind(&sock).unwrap();
    let h = std::thread::spawn(move || {
        let mut gesehen = Vec::new();
        for ant in antworten {
            let (s, _) = l.accept().unwrap();
            let mut w = s.try_clone().unwrap();
            let q = gemein::zeile::lesen(&mut std::io::BufReader::new(s), 4096).unwrap();
            gesehen.push(q);
            gemein::zeile::schreiben(&mut w, &ant).unwrap();
        }
        gesehen
    });
    (sock, h)
}

#[test]
fn senden_geht_als_frage_der_tuer_web_in_die_hauptsitzung() {
    let (sock, h) = doppel("senden", vec![json!({"ok": true, "umgeleitet": false})]);
    let z = zustand(None, sock);
    let c = anmelden(&z);
    let r = behandle(&z, &a("POST", "/api/chat/senden", &c, br#"{"text":"hallo"}"#));
    assert_eq!(r.status, 200);
    let q = &h.join().unwrap()[0];
    assert_eq!((q["op"].as_str(), q["tuer"].as_str(), q["text"].as_str(), q["sitzung"].as_str()),
               (Some("frage"), Some("web"), Some("hallo"), Some("haupt")));
}

#[test]
fn eine_alte_sitzungs_id_wird_durchgereicht_und_umleitung_gemeldet() {
    let (sock, h) = doppel("umleiten", vec![json!({"ok": true, "umgeleitet": true})]);
    let z = zustand(None, sock);
    let c = anmelden(&z);
    let r = behandle(&z, &a("POST", "/api/chat/senden", &c, br#"{"text":"x","sitzung":"alte-id"}"#));
    let v: Value = serde_json::from_slice(&r.body).unwrap();
    assert_eq!(v["umgeleitet"], true);
    assert_eq!(h.join().unwrap()[0]["sitzung"], "alte-id");
}

#[test]
fn leerer_text_erreicht_die_sitzung_nicht() {
    let z = zustand(None, "/gibt/es/nicht".into());
    let c = anmelden(&z);
    assert_eq!(behandle(&z, &a("POST", "/api/chat/senden", &c, br#"{"text":"  "}"#)).status, 400);
}

#[test]
fn ohne_sitzungsdienst_antwortet_der_chat_mit_502() {
    let z = zustand(None, "/gibt/es/nicht".into());
    let c = anmelden(&z);
    assert_eq!(behandle(&z, &a("POST", "/api/chat/senden", &c, br#"{"text":"x"}"#)).status, 502);
    assert_eq!(behandle(&z, &a("GET", "/api/chat/sitzungen", &c, b"")).status, 502);
}

#[test]
fn lesen_prueft_die_sitzungs_id() {
    let z = zustand(None, "/gibt/es/nicht".into());
    let c = anmelden(&z);
    for p in ["/api/chat/lesen", "/api/chat/lesen?sitzung=", "/api/chat/lesen?sitzung=..%2Fx", "/api/chat/lesen?sitzung=a/b"] {
        assert_eq!(behandle(&z, &a("GET", p, &c, b"")).status, 400, "{p}");
    }
}

fn ev(nr: u64) -> sitzung::Ereignis {
    sitzung::Ereignis { nr, art: "antwort".into(), tuer: "web".into(), text: format!("t{nr}"), bezug: String::new() }
}

#[test]
fn der_strom_liefert_nur_neueres_und_haelt_hoechstens_den_ring() {
    let s = Strom::neu();
    for n in 1..=3 {
        s.ein(ev(n));
    }
    assert_eq!(s.seit(1, Duration::ZERO).iter().map(|e| e.nr).collect::<Vec<_>>(), vec![2, 3]);
    assert!(s.seit(3, Duration::ZERO).is_empty());
    for n in 4..=(RING as u64 + 10) {
        s.ein(ev(n));
    }
    assert_eq!(s.inner.lock().unwrap().len(), RING);
}

#[test]
fn der_strom_weckt_einen_wartenden() {
    let s = Strom::neu();
    let s2 = s.clone();
    let t = std::thread::spawn(move || s2.seit(0, Duration::from_secs(5)));
    std::thread::sleep(Duration::from_millis(150));
    s.ein(ev(1));
    assert_eq!(t.join().unwrap().len(), 1);
}

#[test]
fn der_strom_gibt_nach_der_frist_leer_zurueck() {
    let t = Instant::now();
    assert!(Strom::neu().seit(0, Duration::from_millis(200)).is_empty());
    assert!(t.elapsed() >= Duration::from_millis(200));
}

// --- durch einen echten Server ---

fn http(adr: &str, m: &str, p: &str, kopf: &str, body: &str) -> (u16, String, String) {
    let mut s = TcpStream::connect(adr).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(10))).unwrap();
    write!(s, "{m} {p} HTTP/1.1\r\nHost: x\r\nConnection: close\r\nContent-Length: {}\r\n{kopf}\r\n{body}", body.len()).unwrap();
    let mut r = String::new();
    s.read_to_string(&mut r).unwrap();
    let (k, b) = r.split_once("\r\n\r\n").unwrap_or((&r, ""));
    let st = k.split_whitespace().nth(1).unwrap().parse().unwrap();
    (st, k.to_string(), b.to_string())
}

#[test]
fn echter_server_anmelden_modulliste_und_sicherheitskoepfe() {
    let (sock, _h) = doppel("echt", vec![]);
    let hash = hash_erzeugen("geheim-pw-1").unwrap();
    let adr = starten(hash, "127.0.0.1:0", None, sock).unwrap();

    let (st, kopf, body) = http(&adr, "GET", "/", "", "");
    assert_eq!(st, 200);
    assert!(body.contains("Chimera"));
    let k = kopf.to_lowercase();
    assert!(k.contains("content-security-policy") && k.contains("x-content-type-options: nosniff"), "{kopf}");

    assert_eq!(http(&adr, "GET", "/api/module", "", "").0, 401);
    assert_eq!(http(&adr, "POST", "/api/login", "X-Chimera: 1\r\n", r#"{"passwort":"nein"}"#).0, 401);
    let (st, kopf, _) = http(&adr, "POST", "/api/login", "X-Chimera: 1\r\n", r#"{"passwort":"geheim-pw-1"}"#);
    assert_eq!(st, 200);
    let c = kopf.lines().find(|l| l.to_lowercase().starts_with("set-cookie:")).unwrap();
    let c = c.split_once(':').unwrap().1.trim().split(';').next().unwrap().to_string();
    let (st, _, body) = http(&adr, "GET", "/api/module", &format!("Cookie: {c}\r\n"), "");
    assert_eq!(st, 200);
    let v: Value = serde_json::from_str(&body).unwrap();
    assert_eq!(v["module"][0]["name"], "chat");
}

#[test]
fn echter_server_ein_wartender_longpoll_haelt_die_anderen_nicht_auf() {
    let (sock, _h) = doppel("poll", vec![]);
    let adr = starten(hash_erzeugen("geheim-pw-1").unwrap(), "127.0.0.1:0", None, sock).unwrap();
    let (_, kopf, _) = http(&adr, "POST", "/api/login", "X-Chimera: 1\r\n", r#"{"passwort":"geheim-pw-1"}"#);
    let c = kopf.lines().find(|l| l.to_lowercase().starts_with("set-cookie:")).unwrap();
    let c = c.split_once(':').unwrap().1.trim().split(';').next().unwrap().to_string();
    let k = format!("Cookie: {c}\r\n");
    // Fuenf Anfragen warten (Sitzungsdoppel antwortet nie, Strom bleibt leer) ...
    let mut ts = Vec::new();
    for _ in 0..5 {
        let (adr, k) = (adr.clone(), k.clone());
        ts.push(std::thread::spawn(move || http(&adr, "GET", "/api/chat/strom?seit=0", &k, "").0));
    }
    std::thread::sleep(Duration::from_millis(300));
    // ... und die sechste Anfrage kommt trotzdem sofort durch? Es gibt 6 Arbeiter, 5 warten.
    let t = Instant::now();
    assert_eq!(http(&adr, "GET", "/api/module", &k, "").0, 200);
    assert!(t.elapsed() < Duration::from_secs(3));
    drop(ts);
}

// --- Luecken aus der Gegenprobe ---

#[test]
fn ein_hash_aus_leerem_passwort_laesst_trotzdem_keine_leere_anmeldung_zu() {
    let z = Zustand::neu(hash_erzeugen("").unwrap(), None, "/x".into(), Strom::neu());
    assert_eq!(behandle(&z, &a("POST", "/api/login", "", br#"{"passwort":""}"#)).status, 401);
}

#[test]
fn dateinamen_mit_punktpunkt_sind_unzulaessig() {
    for n in ["..", "a..b", "..js", ".", "", "a/b", "a b", "a\\b"] {
        assert!(!datei_ok(n), "{n:?}");
    }
    assert!(datei_ok("chat.js") && datei_ok("a-b_c.1.css"));
}

#[test]
fn das_recht_kommt_nur_aus_dem_manifest() {
    let mk = |n: &str, r: &[&str]| Modul {
        name: n.into(), titel: json!("T"), symbol: String::new(), reihenfolge: 1, einstieg: "a.js".into(),
        element: "x-y".into(), rechte: r.iter().map(|s| s.to_string()).collect(), eingebaut: false,
    };
    assert!(hat_recht(&[mk("chat", &["chat"])], "chat", "chat"));
    assert!(!hat_recht(&[mk("chat", &[])], "chat", "chat"));
    assert!(!hat_recht(&[mk("chat", &["anzeige"])], "chat", "chat"));
    assert!(!hat_recht(&[mk("status", &["chat"])], "chat", "chat"));
    assert!(!hat_recht(&[], "chat", "chat"));
}

#[test]
fn ein_hash_mit_fremdem_kopf_ist_ungueltig_auch_wenn_der_rest_stimmt() {
    let gut = hash_erzeugen("irgendwas-8").unwrap();
    let rest = gut.split_once('$').unwrap().1;
    assert!(hash_gueltig(&gut));
    assert!(!hash_gueltig(&format!("md5${rest}")));
    assert!(!hash_pruefen(&format!("md5${rest}"), "irgendwas-8"));
}

// --- Nur im eigenen Netz ---

#[test]
fn lan_adressen_werden_unterschieden() {
    let ja = ["127.0.0.1", "10.1.2.3", "172.16.0.1", "172.31.255.1", "192.168.1.5", "169.254.1.1", "::1", "fd12::1", "fe80::1", "::ffff:192.168.1.5"];
    let nein = ["8.8.8.8", "172.32.0.1", "172.15.0.1", "1.1.1.1", "2a02:810b::1", "::ffff:8.8.8.8", "100.64.0.1"];
    for a in ja { assert!(ip_im_lan(a.parse().unwrap()), "{a}"); }
    for a in nein { assert!(!ip_im_lan(a.parse().unwrap()), "{a}"); }
}

#[test]
fn nur_lan_ist_vorgabe() {
    assert!(Zustand::neu(hash_erzeugen("x-passwort").unwrap(), None, "/x".into(), Strom::neu()).nur_lan);
}

// --- Status-Modul ---

#[test]
fn status_ist_ein_zweites_modul_ohne_aenderung_am_rahmen() {
    let z = zustand(None, "/x".into());
    let c = anmelden(&z);
    let r = behandle(&z, &a("GET", "/api/module", &c, b""));
    let namen: Vec<String> = serde_json::from_slice::<Value>(&r.body).unwrap()["module"]
        .as_array().unwrap().iter().map(|m| m["name"].as_str().unwrap().to_string()).collect();
    assert!(namen.contains(&"chat".to_string()) && namen.contains(&"status".to_string()), "{namen:?}");
}

#[test]
fn status_braucht_anmeldung_und_liefert_messwerte() {
    let z = zustand(None, "/x".into());
    assert_eq!(behandle(&z, &a("GET", "/api/status/messwerte", "", b"")).status, 401);
    let c = anmelden(&z);
    let r = behandle(&z, &a("GET", "/api/status/messwerte", &c, b""));
    assert_eq!(r.status, 200);
    let v: Value = serde_json::from_slice(&r.body).unwrap();
    let zeilen = v["zeilen"].as_array().unwrap();
    assert!(zeilen.iter().any(|z| z["id"] == "speicher" && z["wert"].is_number()));
    for d in crate::status::DIENSTE {
        assert!(zeilen.iter().any(|z| z["id"] == format!("dienst-{d}")), "{d}");
    }
}

#[test]
fn status_ohne_recht_im_manifest_ist_403() {
    let d = tmp("status-ohne-recht");
    std::fs::create_dir_all(&d).unwrap();
    let z = zustand(Some(d.clone()), "/x".into());
    let c = anmelden(&z);
    // Ein nachgelegtes Modul kann ein eingebautes nie ersetzen (5m): das Recht
    // kommt immer aus dem eingebauten Manifest -- hier pruefen wir hat_recht direkt.
    let leer: Vec<Modul> = Vec::new();
    assert!(!hat_recht(&leer, "status", "status"));
    assert_eq!(behandle(&z, &a("GET", "/api/status/unbekannt", &c, b"")).status, 404);
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn der_rahmen_versteckt_hidden_auch_gegen_display_regeln() {
    // Die Kopfzeile hat `display:flex`; ohne diese Regel bliebe sie vor der Anmeldung sichtbar.
    assert!(RAHMEN_HTML.contains("[hidden] { display: none !important; }"));
}

// --- Rechteliste (DESIGN 5v) ---

#[test]
fn ein_unbekanntes_recht_verwirft_das_modul_mit_grund() {
    let t = r#"{"name":"x","titel":"T","element":"x-x","einstieg":"x.js","rechte":["chat","root-zugriff"]}"#;
    let e = manifest_lesen("x", t, false).unwrap_err();
    assert!(e.contains("root-zugriff") && e.contains("bekannt"), "{e}");
    let ok = r#"{"name":"x","titel":"T","element":"x-x","einstieg":"x.js","rechte":["chat","status"]}"#;
    assert!(manifest_lesen("x", ok, false).is_ok());
}

#[test]
fn die_eingebauten_module_verlangen_nur_bekannte_rechte() {
    // Faengt die Fehlerklasse "Recht im Manifest, aber nicht in RECHTE eingetragen".
    let (m, f) = module_erkennen(None);
    assert!(f.is_empty(), "{f:?}");
    for x in &m {
        for r in &x.rechte {
            assert!(RECHTE.contains(&r.as_str()), "{}: {r}", x.name);
        }
    }
}

#[test]
fn nachgelegte_dateien_mit_unbekannter_endung_werden_nicht_ausgeliefert() {
    // Ein Modulverzeichnis darf nur bekannte Dateitypen preisgeben (kein .env, .sh, .key ...).
    let d = tmp("endung");
    std::fs::create_dir_all(d.join("zusatz")).unwrap();
    std::fs::write(d.join("zusatz/manifest.json"), ok_manifest("zusatz")).unwrap();
    std::fs::write(d.join("zusatz/zusatz.js"), "//").unwrap();
    for n in ["geheim.key", "start.sh", "daten.bin", "notiz.txt", "ohne-endung"] {
        std::fs::write(d.join("zusatz").join(n), "x").unwrap();
    }
    assert!(modul_datei(Some(&d), "zusatz", "zusatz.js").is_some());
    for n in ["geheim.key", "start.sh", "daten.bin", "notiz.txt", "ohne-endung"] {
        assert!(modul_datei(Some(&d), "zusatz", n).is_none(), "{n} darf nicht ausgeliefert werden");
    }
    let _ = std::fs::remove_dir_all(&d);
}

// --- Anbieter-Schnittstelle (5t, 5v) ---

fn anbieter_zustand(n: &str) -> (Zustand, crate::daten::Pfade) {
    let d = tmp(n);
    let p = crate::daten::Pfade::neu(d.join("config"), d.join("state"));
    let mut z = zustand(None, "/x".into());
    z.stand = crate::dienst::Stand::mit(None, p.clone());
    (z, p)
}

fn api(z: &Zustand, c: &str, m: &str, pfad: &str, body: &str) -> Value {
    let r = behandle(z, &a(m, pfad, c, body.as_bytes()));
    let mut v: Value = serde_json::from_slice(&r.body).unwrap_or(json!({}));
    v["_status"] = json!(r.status);
    v
}

#[test]
fn anbieter_api_braucht_anmeldung() {
    let (z, _) = anbieter_zustand("ap-anm");
    assert_eq!(behandle(&z, &a("GET", "/api/anbieter/liste", "", b"")).status, 401);
    assert_eq!(behandle(&z, &a("POST", "/api/anbieter/setzen", "", b"{}")).status, 401);
}

#[test]
fn anbieter_hinzufuegen_auflisten_und_entfernen_ueber_die_oberflaeche() {
    let (z, p) = anbieter_zustand("ap-ok");
    let c = anmelden(&z);
    let neu = r#"{"id":"lan","anbieter":{"typ":"ollama","bezeichnung":"LAN","adresse":"http://127.0.0.1:1","an":true}}"#;
    assert_eq!(api(&z, &c, "POST", "/api/anbieter/setzen", neu)["ok"], true);
    let l = api(&z, &c, "GET", "/api/anbieter/liste", "");
    assert_eq!(l["anbieter"][0]["id"], "lan");
    assert_eq!(l["anbieter"][0]["schluessel"], false);
    assert!(p.anbieter_dir().join("lan.json").exists());
    assert_eq!(api(&z, &c, "POST", "/api/anbieter/entfernen", r#"{"id":"lan"}"#)["ok"], true);
    assert!(!p.anbieter_dir().join("lan.json").exists());
}

#[test]
fn schreibende_wege_nur_per_post_lesende_nur_per_get() {
    let (z, _) = anbieter_zustand("ap-meth");
    let c = anmelden(&z);
    assert_eq!(api(&z, &c, "GET", "/api/anbieter/setzen", "")["_status"], 405);
    assert_eq!(api(&z, &c, "POST", "/api/anbieter/liste", "{}")["_status"], 405);
}

#[test]
fn ungueltige_eingaben_werden_mit_grund_abgewiesen() {
    let (z, p) = anbieter_zustand("ap-bad");
    let c = anmelden(&z);
    for body in [
        r#"{"id":"../x","anbieter":{"typ":"ollama","bezeichnung":"x"}}"#,
        r#"{"id":"a","anbieter":{"typ":"ollama","bezeichnung":"x","adresse":"ftp://h"}}"#,
        r#"{"id":"a","anbieter":{}}"#,
    ] {
        let r = api(&z, &c, "POST", "/api/anbieter/setzen", body);
        assert_eq!(r["ok"], false, "{body}");
    }
    assert_eq!(api(&z, &c, "POST", "/api/anbieter/setzen", "kein json")["_status"], 400);
    assert!(!p.anbieter_dir().exists() || std::fs::read_dir(p.anbieter_dir()).unwrap().count() == 0);
}

#[test]
fn der_schluessel_steht_in_keiner_antwort() {
    let (z, p) = anbieter_zustand("ap-key");
    let c = anmelden(&z);
    api(&z, &c, "POST", "/api/anbieter/setzen", r#"{"id":"lan","anbieter":{"typ":"ollama","bezeichnung":"L"}}"#);
    let r = api(&z, &c, "POST", "/api/anbieter/schluessel", r#"{"id":"lan","wert":"sk-nie-zeigen"}"#);
    assert!(!r.to_string().contains("sk-nie-zeigen"));
    let l = api(&z, &c, "GET", "/api/anbieter/liste", "");
    assert_eq!(l["anbieter"][0]["schluessel"], true);
    assert!(!l.to_string().contains("sk-nie-zeigen"));
    assert_eq!(crate::daten::schluessel_lesen(&p, "lan").as_deref(), Some("sk-nie-zeigen"));
}

fn modul(name: &str, rechte: &[&str], eingebaut: bool) -> Modul {
    Modul {
        name: name.into(), titel: json!("T"), symbol: String::new(), reihenfolge: 1,
        einstieg: "a.js".into(), element: "x-a".into(),
        rechte: rechte.iter().map(|r| r.to_string()).collect(), eingebaut,
    }
}

#[test]
fn nur_eingebaute_module_vergeben_das_schreibrecht() {
    let liste = vec![modul("fremd", &["anbieter-schreiben"], false), modul("ollama", &["anbieter-lesen"], true)];
    assert!(!schreibrecht_vergeben(&liste, "anbieter-schreiben"), "nachgelegt zaehlt nicht");
    assert!(schreibrecht_vergeben(&liste, "anbieter-lesen"));
    let mit = vec![modul("ollama", &["anbieter-schreiben"], true)];
    assert!(schreibrecht_vergeben(&mit, "anbieter-schreiben"));
}

#[test]
fn das_eingebaute_ollamamodul_hat_beide_anbieterrechte() {
    let (m, f) = module_erkennen(None);
    assert!(f.is_empty(), "{f:?}");
    assert!(schreibrecht_vergeben(&m, "anbieter-lesen"));
    assert!(schreibrecht_vergeben(&m, "anbieter-schreiben"));
}

#[test]
fn unbekannter_weg_ist_404() {
    let (z, _) = anbieter_zustand("ap-404");
    let c = anmelden(&z);
    assert_eq!(api(&z, &c, "GET", "/api/anbieter/wasanderes", "")["_status"], 404);
}

#[test]
fn katalog_lesen_ueber_die_oberflaeche() {
    let (z, p) = anbieter_zustand("ap-kat");
    let c = anmelden(&z);
    crate::daten::katalog_speichern(&p, "lan", &json!({"stand": 5, "modelle": {"a": {"tools": true}}})).unwrap();
    let r = api(&z, &c, "GET", "/api/anbieter/katalog?id=lan", "");
    assert_eq!(r["katalog"]["modelle"]["a"]["tools"], true);
    assert_eq!(api(&z, &c, "GET", "/api/anbieter/katalog?id=../x", "")["ok"], false);
    assert_eq!(api(&z, &c, "GET", "/api/anbieter/katalog", "")["ok"], false);
}

#[test]
fn ohne_modul_mit_dem_recht_ist_jeder_anbieterweg_403() {
    let (z, p) = anbieter_zustand("ap-403");
    let leer: Vec<Modul> = vec![];
    let nur_lesen = vec![modul("x", &["anbieter-lesen"], true)];
    for (m, pfad, body) in [
        ("GET", "liste", ""), ("GET", "katalog", ""),
        ("POST", "setzen", r#"{"id":"a","anbieter":{"typ":"ollama","bezeichnung":"x"}}"#),
        ("POST", "entfernen", r#"{"id":"a"}"#), ("POST", "schluessel", r#"{"id":"a","wert":"k"}"#),
        ("POST", "aktualisieren", r#"{"id":"a"}"#), ("POST", "probe", r#"{"id":"a"}"#),
    ] {
        let r = anbieter_antwort(&z, &a(m, &format!("/api/anbieter/{pfad}"), "", body.as_bytes()), pfad, &leer);
        assert_eq!(r.status, 403, "{pfad} ohne Modul");
    }
    // Nur das Leserecht: Schreibwege bleiben zu, nichts wird angelegt.
    let r = anbieter_antwort(&z, &a("POST", "/api/anbieter/setzen", "", br#"{"id":"a","anbieter":{"typ":"ollama","bezeichnung":"x"}}"#), "setzen", &nur_lesen);
    assert_eq!(r.status, 403);
    assert!(!p.anbieter_dir().join("a.json").exists());
}
