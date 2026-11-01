//! Der Dienstbetrieb des Gateways: ein Unix-Socket, eine JSON-Zeile hin,
//! eine zurueck (DESIGN Regel 5n, Protokoll aus `gemein::zeile`).
//!
//! Stand Phase 4d Schritt 2 (Geruest): `ping` und `status`. Anbieter,
//! Telegram und Web folgen (docs/ROADMAP.md). Alles Unbekannte wird mit
//! einer Fehlerantwort abgelehnt, nie still verschluckt.
//!
//! Zwei Wege zum Socket:
//! - **systemd-Socket-Aktivierung** (`LISTEN_FDS`): systemd haelt den
//!   Socket, legt Besitzer und Rechte fest und startet das Gateway beim
//!   ersten Aufruf. Stuerzt das Gateway ab, wartet der Aufrufer, statt
//!   „abgelehnt“ zu bekommen.
//! - **selbst binden** (`--socket PFAD`): fuer Tests und den Betrieb ohne
//!   systemd.

use crate::ollama;
use gemein::protokoll::{melden, Stufe};
use gemein::zeile;
use serde_json::{json, Value};
use std::io::BufReader;
use std::os::unix::io::FromRawFd;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

/// Gleichzeitige Verbindungen. Jede kostet einen Thread-Stapel; das
/// Gateway soll unter 10 MB bleiben (Regel 5n).
pub const MAX_VERBINDUNGEN: usize = 8;

/// Wer eine Zeile angefangen hat und nicht fertig schreibt, haelt keinen
/// Platz laenger als das.
const LESEFRIST: Duration = Duration::from_secs(10);

/// Die vom Aufrufer unabhaengige Zaehlung des Gateways.
pub struct Stand {
    start: Instant,
    anfragen: AtomicU64,
    offen: AtomicUsize,
    /// Adresse des Ollama-Servers, einmal beim Start aus der Umgebung.
    ollama: Option<String>,
    /// Die vier Ablagen (Regel 5t).
    pub daten: crate::daten::Pfade,
}

impl Stand {
    pub fn neu() -> Self {
        Self::mit_ollama(ollama::adresse())
    }

    pub fn mit_ollama(ollama: Option<String>) -> Self {
        Self::mit(ollama, crate::daten::Pfade::aus_umgebung())
    }

    pub fn mit(ollama: Option<String>, daten: crate::daten::Pfade) -> Self {
        Stand {
            start: Instant::now(),
            anfragen: AtomicU64::new(0),
            offen: AtomicUsize::new(0),
            ollama,
            daten,
        }
    }
}

/// Beantwortet eine Anfrage. Rein, ohne E/A -- prueft sich allein.
pub fn antworten(anfrage: &Value, stand: &Stand) -> Value {
    let op = anfrage.get("op").and_then(Value::as_str).unwrap_or("");
    match op {
        "ping" => json!({ "ok": true, "programm": "chimera-tor", "version": gemein::version() }),
        "status" => json!({
            "ok": true,
            "programm": "chimera-tor",
            "version": gemein::version(),
            "laufzeit_s": stand.start.elapsed().as_secs(),
            "anfragen": stand.anfragen.load(Ordering::Relaxed),
            "offen": stand.offen.load(Ordering::Relaxed),
            "ollama": stand.ollama.as_deref().map(ollama::host_von),
            "telegram": if crate::telegram::laeuft() { "an" } else { "aus" },
        }),
        "chat" => match anfrage.get("anbieter").and_then(Value::as_str) {
            Some(a) => match ollama_adresse(a, stand) {
                Ok(adr) => ollama::op_chat(adr.as_deref(), anfrage),
                Err(f) => f,
            },
            None => zeile::fehlerantwort("anbieter_fehlt", "Der Chat braucht ein Feld \"anbieter\"."),
        },
        "modelle" => match anfrage.get("anbieter").and_then(Value::as_str) {
            Some(a) => match ollama_adresse(a, stand) {
                Ok(adr) => ollama::op_modelle(adr.as_deref()),
                Err(f) => f,
            },
            None => zeile::fehlerantwort("anbieter_fehlt", "Die Abfrage braucht ein Feld \"anbieter\"."),
        },
        "katalog_aktualisieren" => katalog_aktualisieren(anfrage, stand),
        "netzsuche" => crate::netzsuche::durchgang(stand),
        "" => zeile::fehlerantwort("op_fehlt", "Die Anfrage braucht ein Feld \"op\"."),
        andere => crate::daten::op(andere, anfrage, &stand.daten).unwrap_or_else(|| {
            zeile::fehlerantwort("op_unbekannt", &format!("Unbekannte Operation: {andere}"))
        }),
    }
}

/// Die Adresse eines Ollama-Anbieters. `ollama` ohne eigene Datei ist der
/// Anbieter aus der `.env` (Rueckfall bis zur Umstellung); jede andere Id muss
/// eine Anbieterdatei vom Typ `ollama` haben. `Ok(None)` heisst „nicht
/// eingerichtet“ (die Antwort der Operation sagt das selbst).
fn ollama_adresse(id: &str, stand: &Stand) -> Result<Option<String>, Value> {
    if !crate::daten::id_gueltig(id) {
        return Err(zeile::fehlerantwort("anbieter_unbekannt", &format!("Unbekannter Anbieter: {id}")));
    }
    let (liste, _) = crate::daten::anbieter_laden(&stand.daten);
    if let Some((_, a)) = liste.iter().find(|(i, _)| i == id) {
        if a["typ"] != "ollama" {
            return Err(zeile::fehlerantwort(
                "anbieter_unbekannt",
                &format!("Anbieter {id} hat den Typ {}, den dieser Weg nicht bedient.", a["typ"]),
            ));
        }
        if a.get("an").and_then(Value::as_bool) == Some(false) {
            return Err(zeile::fehlerantwort("anbieter_aus", &format!("Anbieter {id} ist ausgeschaltet.")));
        }
        return Ok(ollama::adresse_aus(a["adresse"].as_str()));
    }
    if id == "ollama" {
        return Ok(stand.ollama.clone());
    }
    Err(zeile::fehlerantwort("anbieter_unbekannt", &format!("Unbekannter Anbieter: {id}")))
}

/// `op: katalog_aktualisieren` mit `id`: Server fragen, Katalog abgleichen
/// (Frist statt Loeschen) und schreiben. Ein nicht erreichbarer Server
/// laesst den alten Katalog unberuehrt.
fn katalog_aktualisieren(anfrage: &Value, stand: &Stand) -> Value {
    let id = match anfrage.get("id").and_then(Value::as_str) {
        Some(i) if crate::daten::id_gueltig(i) => i,
        _ => return zeile::fehlerantwort("id_ungueltig", "Die Anfrage braucht eine gueltige \"id\"."),
    };
    let adr = match ollama_adresse(id, stand) {
        Ok(Some(a)) => a,
        Ok(None) => return zeile::fehlerantwort("nicht_eingerichtet", "Der Anbieter hat keine Adresse."),
        Err(f) => return f,
    };
    let neu = match ollama::katalog_von(&adr, ollama::KATALOG_BUDGET) {
        Ok(k) => k,
        Err(f) => return f,
    };
    let jetzt = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let alt = crate::daten::katalog_lesen(&stand.daten, id);
    let katalog = crate::daten::katalog_abgleichen(&alt, &neu, jetzt);
    if let Err(e) = crate::daten::katalog_speichern(&stand.daten, id, &katalog) {
        return zeile::fehlerantwort("katalog_nicht_gespeichert", &e);
    }
    json!({"ok": true, "id": id, "modelle": katalog["modelle"].as_object().map(|m| m.len()), "host": ollama::host_von(&adr)})
}

/// Eine Verbindung bedienen: Zeilen lesen, antworten, bis das Gegenueber geht.
fn bedienen(strom: UnixStream, stand: &Stand) {
    let _ = strom.set_read_timeout(Some(LESEFRIST));
    let mut schreiber = match strom.try_clone() {
        Ok(s) => s,
        Err(e) => {
            melden(Stufe::Warnung, &format!("Verbindung nicht doppelbar: {e}"));
            return;
        }
    };
    let mut leser = BufReader::new(strom);
    loop {
        match zeile::lesen(&mut leser, zeile::MAX_BYTES) {
            Ok(anfrage) => {
                stand.anfragen.fetch_add(1, Ordering::Relaxed);
                if zeile::schreiben(&mut schreiber, &antworten(&anfrage, stand)).is_err() {
                    return;
                }
            }
            Err(zeile::Fehler::Ende) => return,
            Err(f @ (zeile::Fehler::KeinObjekt(_) | zeile::Fehler::ZuLang(_))) => {
                // Das Gegenueber hat Unsinn geschickt: sagen, was war, und
                // die Verbindung beenden -- die Zeilengrenze ist unsicher.
                let _ = zeile::schreiben(
                    &mut schreiber,
                    &zeile::fehlerantwort("anfrage_ungueltig", &f.to_string()),
                );
                return;
            }
            Err(f) => {
                melden(Stufe::Info, &format!("Verbindung beendet: {f}"));
                return;
            }
        }
    }
}

/// Nimmt Verbindungen an, bis der Prozess beendet wird.
pub fn lauschen(listener: UnixListener) -> ! {
    let stand = Arc::new(Stand::neu());
    for verbindung in listener.incoming() {
        let strom = match verbindung {
            Ok(s) => s,
            Err(e) => {
                melden(Stufe::Warnung, &format!("accept: {e}"));
                continue;
            }
        };
        // Platz reservieren, bevor der Thread entsteht -- sonst liesse
        // sich die Grenze mit einem Schwung Verbindungen ueberrennen.
        if stand.offen.fetch_add(1, Ordering::SeqCst) >= MAX_VERBINDUNGEN {
            stand.offen.fetch_sub(1, Ordering::SeqCst);
            let mut s = strom;
            let _ = zeile::schreiben(&mut s, &zeile::fehlerantwort("ausgelastet", "Zu viele Verbindungen."));
            continue;
        }
        let stand2 = Arc::clone(&stand);
        let r = std::thread::Builder::new()
            .name("verbindung".into())
            .stack_size(512 * 1024)
            .spawn(move || {
                bedienen(strom, &stand2);
                stand2.offen.fetch_sub(1, Ordering::SeqCst);
            });
        if let Err(e) = r {
            stand.offen.fetch_sub(1, Ordering::SeqCst);
            melden(Stufe::Fehler, &format!("Thread nicht startbar: {e}"));
        }
    }
    unreachable!("incoming() endet nicht")
}

/// Den von systemd uebergebenen Socket holen (`LISTEN_FDS`, Handle 3).
/// `None`, wenn der Prozess nicht per Socket-Aktivierung gestartet wurde.
pub fn von_systemd() -> Option<UnixListener> {
    let pid: u32 = std::env::var("LISTEN_PID").ok()?.parse().ok()?;
    if pid != std::process::id() {
        return None;
    }
    let n: u32 = std::env::var("LISTEN_FDS").ok()?.parse().ok()?;
    if n != 1 {
        melden(Stufe::Fehler, &format!("LISTEN_FDS={n}, erwartet 1."));
        return None;
    }
    // SAFETY: systemd uebergibt Handle 3 genau dann, wenn LISTEN_PID und
    // LISTEN_FDS gesetzt sind (sd_listen_fds(3)); niemand sonst besitzt es.
    Some(unsafe { UnixListener::from_raw_fd(3) })
}

/// Selbst an einen Pfad binden. Eine alte Socket-Datei, hinter der niemand
/// mehr lauscht, wird ersetzt; antwortet dort noch jemand, ist es ein
/// Fehler (zwei Gateways nebeneinander waeren einer zu viel).
pub fn binden(pfad: &Path) -> Result<UnixListener, String> {
    if pfad.exists() {
        if UnixStream::connect(pfad).is_ok() {
            return Err(format!("{} wird schon bedient", pfad.display()));
        }
        std::fs::remove_file(pfad).map_err(|e| format!("alter Socket nicht entfernbar: {e}"))?;
    }
    let l = UnixListener::bind(pfad).map_err(|e| format!("bind {}: {e}", pfad.display()))?;
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(pfad, std::fs::Permissions::from_mode(0o660))
        .map_err(|e| format!("Rechte auf {}: {e}", pfad.display()))?;
    Ok(l)
}

/// Eine Anfrage an ein laufendes Gateway (fuer `--ping` und den Installer).
pub fn anfragen(pfad: &Path, anfrage: &Value) -> Result<Value, String> {
    let mut s = UnixStream::connect(pfad).map_err(|e| format!("{}: {e}", pfad.display()))?;
    s.set_read_timeout(Some(Duration::from_secs(10))).map_err(|e| e.to_string())?;
    zeile::schreiben(&mut s, anfrage).map_err(|e| e.to_string())?;
    zeile::lesen(&mut BufReader::new(s), zeile::MAX_BYTES).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};

    fn tmp(name: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("chimera-tor-test-{}-{name}", std::process::id()));
        let _ = std::fs::remove_file(&d);
        d
    }

    fn starten(pfad: &Path) {
        let l = binden(pfad).expect("binden");
        std::thread::spawn(move || lauschen(l));
    }

    #[test]
    fn ping_nennt_die_version() {
        let a = antworten(&json!({"op": "ping"}), &Stand::neu());
        assert_eq!(a["ok"], true);
        assert_eq!(a["version"], gemein::version());
    }

    #[test]
    fn unbekannte_und_fehlende_op_werden_abgelehnt() {
        let s = Stand::neu();
        let a = antworten(&json!({"op": "loeschen"}), &s);
        assert_eq!(a["ok"], false);
        assert_eq!(a["fehler"]["code"], "op_unbekannt");
        let b = antworten(&json!({}), &s);
        assert_eq!(b["fehler"]["code"], "op_fehlt");
    }

    #[test]
    fn ueber_den_socket_ping_und_zaehler() {
        let p = tmp("ping");
        starten(&p);
        assert_eq!(anfragen(&p, &json!({"op": "ping"})).unwrap()["ok"], true);
        let st = anfragen(&p, &json!({"op": "status"})).unwrap();
        // Der Zaehler zaehlt die Anfrage, die ihn abfragt, schon mit.
        assert!(st["anfragen"].as_u64().unwrap() >= 1);
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn muell_bekommt_eine_fehlerantwort_und_das_gateway_lebt_weiter() {
        let p = tmp("muell");
        starten(&p);
        let mut s = UnixStream::connect(&p).unwrap();
        s.write_all(b"das ist kein json\n").unwrap();
        let mut aus = String::new();
        s.read_to_string(&mut aus).unwrap();
        assert!(aus.contains("anfrage_ungueltig"), "{aus}");
        // Danach antwortet es dem Naechsten.
        assert_eq!(anfragen(&p, &json!({"op": "ping"})).unwrap()["ok"], true);
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn socket_hat_nur_besitzer_und_gruppe() {
        use std::os::unix::fs::PermissionsExt;
        let p = tmp("modus");
        let _l = binden(&p).unwrap();
        let m = std::fs::metadata(&p).unwrap().permissions().mode() & 0o777;
        assert_eq!(m, 0o660);
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn zweites_binden_auf_einen_lebenden_socket_scheitert() {
        let p = tmp("doppelt");
        starten(&p);
        assert!(binden(&p).unwrap_err().contains("schon bedient"));
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn verwaister_socket_wird_ersetzt() {
        let p = tmp("verwaist");
        drop(UnixListener::bind(&p).unwrap()); // Datei bleibt, niemand lauscht
        assert!(p.exists());
        assert!(binden(&p).is_ok());
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn ohne_systemd_umgebung_gibt_es_keinen_uebergebenen_socket() {
        // LISTEN_PID zeigt auf einen fremden Prozess: nicht uebernehmen.
        std::env::set_var("LISTEN_PID", "1");
        std::env::set_var("LISTEN_FDS", "1");
        assert!(von_systemd().is_none());
        std::env::remove_var("LISTEN_PID");
        std::env::remove_var("LISTEN_FDS");
    }
}

#[cfg(test)]
mod tests_anbieter {
    use super::*;

    #[test]
    fn chat_ohne_anbieter_wird_abgelehnt() {
        let a = antworten(&json!({"op": "chat", "prompt": "x"}), &Stand::mit_ollama(None));
        assert_eq!(a["fehler"]["code"], "anbieter_fehlt");
    }

    #[test]
    fn unbekannter_anbieter_wird_benannt_nicht_geraten() {
        let a = antworten(&json!({"op": "chat", "anbieter": "irgendwer"}), &Stand::mit_ollama(None));
        assert_eq!(a["fehler"]["code"], "anbieter_unbekannt");
    }

    #[test]
    fn ollama_ohne_adresse_ist_nicht_eingerichtet() {
        let a = antworten(&json!({"op": "chat", "anbieter": "ollama"}), &Stand::mit_ollama(None));
        assert_eq!(a["fehler"]["code"], "nicht_eingerichtet");
        let b = antworten(&json!({"op": "modelle", "anbieter": "ollama"}), &Stand::mit_ollama(None));
        assert_eq!(b["fehler"]["code"], "nicht_eingerichtet");
    }

    #[test]
    fn status_zeigt_nur_den_host_nie_die_ganze_adresse() {
        let s = Stand::mit_ollama(Some("http://ollama.example:11434".into()));
        assert_eq!(antworten(&json!({"op": "status"}), &s)["ollama"], "ollama.example:11434");
    }

    fn stand_mit_daten(n: &str, ollama: Option<String>) -> (Stand, crate::daten::Pfade) {
        let d = std::env::temp_dir().join(format!("chimera-dienst-{n}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let p = crate::daten::Pfade::neu(d.join("config"), d.join("state"));
        (Stand::mit(ollama, p.clone()), p)
    }

    #[test]
    fn katalog_aktualisieren_schreibt_den_katalog_des_anbieters() {
        let (b, h) = ollama::tests::server(vec![
            (200, r#"{"models":[{"name":"a"}]}"#.into()),
            (200, r#"{"capabilities":["tools"]}"#.into()),
        ]);
        let (s, p) = stand_mit_daten("kat", None);
        crate::daten::anbieter_speichern(&p, "lan", &json!({"typ": "ollama", "bezeichnung": "L", "adresse": b})).unwrap();
        let r = antworten(&json!({"op": "katalog_aktualisieren", "id": "lan"}), &s);
        assert_eq!(r["ok"], true, "{r}");
        assert_eq!(crate::daten::katalog_lesen(&p, "lan")["modelle"]["a"]["tools"], true);
        h.join().unwrap();
    }

    #[test]
    fn nicht_erreichbarer_server_laesst_den_alten_katalog_stehen() {
        let (s, p) = stand_mit_daten("alt", None);
        crate::daten::anbieter_speichern(&p, "lan", &json!({"typ": "ollama", "bezeichnung": "L", "adresse": "http://127.0.0.1:1"})).unwrap();
        let alt = json!({"stand": 1, "modelle": {"a": {"tools": true}}});
        crate::daten::katalog_speichern(&p, "lan", &alt).unwrap();
        let r = antworten(&json!({"op": "katalog_aktualisieren", "id": "lan"}), &s);
        assert_eq!(r["fehler"]["code"], "nicht_erreichbar", "{r}");
        assert_eq!(crate::daten::katalog_lesen(&p, "lan"), alt);
    }

    #[test]
    fn anbieter_aus_der_datenschicht_wird_fuer_chat_benutzt_ausgeschaltete_nicht() {
        let (b, h) = ollama::tests::server(vec![(200, r#"{"models":[{"name":"m"}]}"#.into())]);
        let (s, p) = stand_mit_daten("chat", None);
        crate::daten::anbieter_speichern(&p, "lan", &json!({"typ": "ollama", "bezeichnung": "L", "adresse": b})).unwrap();
        assert_eq!(antworten(&json!({"op": "modelle", "anbieter": "lan"}), &s)["modelle"], json!(["m"]));
        h.join().unwrap();
        crate::daten::anbieter_speichern(&p, "aus", &json!({"typ": "ollama", "bezeichnung": "A", "adresse": "http://x:1", "an": false})).unwrap();
        assert_eq!(antworten(&json!({"op": "modelle", "anbieter": "aus"}), &s)["fehler"]["code"], "anbieter_aus");
    }

    #[test]
    fn id_ohne_datei_ist_unbekannt_nur_ollama_faellt_auf_die_env_zurueck() {
        let (s, _) = stand_mit_daten("env", Some("http://127.0.0.1:1".into()));
        assert_eq!(antworten(&json!({"op": "modelle", "anbieter": "irgendwer"}), &s)["fehler"]["code"], "anbieter_unbekannt");
        assert_eq!(antworten(&json!({"op": "modelle", "anbieter": "../x"}), &s)["fehler"]["code"], "anbieter_unbekannt");
        assert_eq!(antworten(&json!({"op": "modelle", "anbieter": "ollama"}), &s)["fehler"]["code"], "nicht_erreichbar");
    }

    #[test]
    fn anbieter_anderen_typs_wird_nicht_als_ollama_bedient() {
        let (s, p) = stand_mit_daten("typ", None);
        crate::daten::anbieter_speichern(&p, "cloud", &json!({"typ": "anthropic", "bezeichnung": "C"})).unwrap();
        assert_eq!(antworten(&json!({"op": "chat", "anbieter": "cloud"}), &s)["fehler"]["code"], "anbieter_unbekannt");
    }
}
