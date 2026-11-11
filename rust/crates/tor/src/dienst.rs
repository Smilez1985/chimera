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
            Some(a) => chat(a, anfrage, stand),
            None => zeile::fehlerantwort("anbieter_fehlt", "Der Chat braucht ein Feld \"anbieter\"."),
        },
        "modelle" => match anfrage.get("anbieter").and_then(Value::as_str) {
            Some(a) => match ollama_adresse(a, stand) {
                Ok(adr) => ollama::op_modelle(
                    adr.as_deref(),
                    &katalog_fuer(a, adr.as_deref(), stand),
                ),
                Err(f) => f,
            },
            None => zeile::fehlerantwort("anbieter_fehlt", "Die Abfrage braucht ein Feld \"anbieter\"."),
        },
        // Was das Gateway ueber die Modelle gemessen hat (Werkzeuge, Fenster).
        // Der Dienst hat kein Netz und kann es nicht selbst fragen; ohne diese
        // Operation muesste er das Fenster raten (DESIGN 5a, 11.11.2026).
        "katalog_lesen" => match anfrage.get("id").and_then(Value::as_str) {
            Some(id) if crate::daten::id_gueltig(id) => json!({
                "ok": true,
                "id": id,
                "katalog": crate::daten::katalog_lesen(&stand.daten, id),
            }),
            _ => zeile::fehlerantwort("id_ungueltig", "Die Anfrage braucht eine gueltige \"id\"."),
        },
        "katalog_aktualisieren" => katalog_aktualisieren(anfrage, stand, ollama::KATALOG_BUDGET),
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

/// `op: chat`: nimmt den gespeicherten Katalog mit, damit ohne genanntes
/// Modell nach dem gemessenen `tools` gewaehlt wird (DESIGN 5n, „Das Modell
/// kommt vom Server"). Ist nichts gemessen (frischer Anbieter, Katalog leer),
/// wird **einmal** gemessen und erneut gefragt -- sonst bliebe ein Anbieter,
/// den die Netzsuche nicht auffrischt (`auto: false`), dauerhaft ohne Antwort.
fn chat(id: &str, anfrage: &Value, stand: &Stand) -> Value {
    let adr = match ollama_adresse(id, stand) {
        Ok(Some(a)) => a,
        Ok(None) => return ollama::op_chat(None, anfrage, &json!({})),
        Err(f) => return f,
    };
    let mut katalog = katalog_fuer(id, Some(&adr), stand);
    let a = ollama::op_chat(Some(&adr), anfrage, &katalog);
    let genannt = anfrage.get("modell").and_then(Value::as_str).is_some_and(|m| !m.is_empty());
    if a["fehler"]["code"] == "kein_modell" && !genannt && !katalog_gemessen(&katalog) {
        let r = katalog_aktualisieren(&json!({"id": id}), stand, ollama::KATALOG_BUDGET_SOFORT);
        if r["ok"] == true {
            katalog = crate::daten::katalog_lesen(&stand.daten, id);
            return ollama::op_chat(Some(&adr), anfrage, &katalog);
        }
    }
    a
}

/// Der gespeicherte Katalog zu einem Anbieter.
///
/// Warum nicht einfach `katalog_lesen(id)`: Die Netzsuche vergibt eigene Ids
/// (`ollama-192-168-178-100`), waehrend der Dienst den Anbieter `ollama` mit
/// der Adresse aus der `.env` fragt. Am 11.11. am Geraet gemessen: der
/// Katalog lag unter der gefundenen Id, die Wahl unter `ollama` sah einen
/// leeren Katalog. Gesucht wird deshalb zuerst unter der Id, dann unter der
/// **gleichen Adresse**.
fn katalog_fuer(id: &str, adresse: Option<&str>, stand: &Stand) -> Value {
    let eigen = crate::daten::katalog_lesen(&stand.daten, id);
    let gefuellt = |k: &Value| k["modelle"].as_object().map(|m| !m.is_empty()).unwrap_or(false);
    if gefuellt(&eigen) {
        return eigen;
    }
    let Some(adr) = adresse else { return eigen };
    let (liste, _) = crate::daten::anbieter_laden(&stand.daten);
    for (i, a) in &liste {
        if i == id || a["typ"] != "ollama" {
            continue;
        }
        if ollama::adresse_aus(a["adresse"].as_str()).as_deref() != Some(adr) {
            continue;
        }
        let k = crate::daten::katalog_lesen(&stand.daten, i);
        if gefuellt(&k) {
            return k;
        }
    }
    eigen
}

/// Hat der Katalog mindestens eine echte Messung? `tools: null` ist keine.
fn katalog_gemessen(katalog: &Value) -> bool {
    katalog["modelle"]
        .as_object()
        .map(|m| m.values().any(|e| !e["tools"].is_null()))
        .unwrap_or(false)
}

/// `op: katalog_aktualisieren` mit `id`: Server fragen, Katalog abgleichen
/// (Frist statt Loeschen) und schreiben. Ein nicht erreichbarer Server
/// laesst den alten Katalog unberuehrt.
fn katalog_aktualisieren(anfrage: &Value, stand: &Stand, budget: Duration) -> Value {
    let id = match anfrage.get("id").and_then(Value::as_str) {
        Some(i) if crate::daten::id_gueltig(i) => i,
        _ => return zeile::fehlerantwort("id_ungueltig", "Die Anfrage braucht eine gueltige \"id\"."),
    };
    let adr = match ollama_adresse(id, stand) {
        Ok(Some(a)) => a,
        Ok(None) => return zeile::fehlerantwort("nicht_eingerichtet", "Der Anbieter hat keine Adresse."),
        Err(f) => return f,
    };
    let neu = match ollama::katalog_von(&adr, budget) {
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

/// Eine Anfrage an ein laufendes Gateway (fuer `--ping` und den Installer).
pub fn anfragen(pfad: &Path, anfrage: &Value) -> Result<Value, String> {
    let mut s = UnixStream::connect(pfad).map_err(|e| format!("{}: {e}", pfad.display()))?;
    s.set_read_timeout(Some(Duration::from_secs(10))).map_err(|e| e.to_string())?;
    zeile::schreiben(&mut s, anfrage).map_err(|e| e.to_string())?;
    zeile::lesen(&mut BufReader::new(s), zeile::MAX_BYTES).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    // Der Dienst hat kein Netz: Ohne diese Operation muesste er das Fenster
    // raten (DESIGN 5a).
    #[test]
    fn katalog_lesen_ueber_den_socket() {
        let s = Stand::mit_ollama(None);
        let a = antworten(&json!({"op": "katalog_lesen", "id": "ollama"}), &s);
        assert_eq!(a["ok"], true);
        assert_eq!(a["id"], "ollama");
        assert!(a.get("katalog").is_some(), "katalog fehlt: {a}");
        let falsch = antworten(&json!({"op": "katalog_lesen", "id": "../etc"}), &s);
        assert_eq!(falsch["fehler"]["code"], "id_ungueltig");
    }

    use super::*;
    use std::io::{Read, Write};

    fn tmp(name: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("chimera-tor-test-{}-{name}", std::process::id()));
        let _ = std::fs::remove_file(&d);
        d
    }

    fn starten(pfad: &Path) {
        let l = gemein::socket::binden(pfad).expect("binden");
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
        let _l = gemein::socket::binden(&p).unwrap();
        let m = std::fs::metadata(&p).unwrap().permissions().mode() & 0o777;
        assert_eq!(m, 0o660);
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn zweites_binden_auf_einen_lebenden_socket_scheitert() {
        let p = tmp("doppelt");
        starten(&p);
        assert!(gemein::socket::binden(&p).unwrap_err().contains("schon bedient"));
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn verwaister_socket_wird_ersetzt() {
        let p = tmp("verwaist");
        drop(UnixListener::bind(&p).unwrap()); // Datei bleibt, niemand lauscht
        assert!(p.exists());
        assert!(gemein::socket::binden(&p).is_ok());
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn ohne_systemd_umgebung_gibt_es_keinen_uebergebenen_socket() {
        // LISTEN_PID zeigt auf einen fremden Prozess: nicht uebernehmen.
        std::env::set_var("LISTEN_PID", "1");
        std::env::set_var("LISTEN_FDS", "1");
        assert!(gemein::socket::von_systemd().is_none());
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

    #[test]
    fn chat_ohne_modell_nimmt_das_gemessene_aus_dem_gespeicherten_katalog() {
        // Nur Modellliste und Chat: der gespeicherte Katalog reicht, es wird
        // nichts nachgemessen (sonst kaeme ein dritter Aufruf, den der Server
        // nicht beantwortet und der Test haengt).
        let (b, h) = ollama::tests::server(vec![
            (200, r#"{"models":[{"name":"blind:7b"},{"name":"klug"}]}"#.into()),
            (200, r#"{"message":{"content":"ok"}}"#.into()),
        ]);
        let (s, p) = stand_mit_daten("wahl", None);
        crate::daten::anbieter_speichern(&p, "lan", &json!({"typ": "ollama", "bezeichnung": "L", "adresse": b})).unwrap();
        let katalog = json!({"stand": 7, "modelle": {
            "blind:7b": {"tools": false}, "klug": {"tools": true},
        }});
        crate::daten::katalog_speichern(&p, "lan", &katalog).unwrap();
        let a = antworten(&json!({"op": "chat", "anbieter": "lan", "prompt": "x"}), &s);
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["modell"], "klug", "die Zahl im Namen darf nicht entscheiden: {a}");
        h.join().unwrap();
    }

    #[test]
    fn der_katalog_der_netzsuche_gilt_auch_fuer_den_namen_ollama() {
        // Am Geraet gemessen (11.11.): Die Netzsuche legt den Anbieter als
        // `ollama-192-168-178-100` an, der Dienst fragt `ollama` ueber die
        // Adresse aus der `.env`. Ohne Adressabgleich sah die Wahl einen
        // leeren Katalog und haette kein Modell genannt.
        let (b, h) = ollama::tests::server(vec![
            (200, r#"{"models":[{"name":"blind:7b"},{"name":"klug"}]}"#.into()), // op: modelle
            (200, r#"{"models":[{"name":"blind:7b"},{"name":"klug"}]}"#.into()), // chat: modellliste
            (200, r#"{"message":{"content":"ok"}}"#.into()),                     // chat
        ]);
        let (s, p) = stand_mit_daten("adressabgleich", Some(b.clone()));
        crate::daten::anbieter_speichern(
            &p,
            "ollama-192-0-2-1",
            &json!({"typ": "ollama", "bezeichnung": "L", "adresse": b, "auto": true}),
        )
        .unwrap();
        crate::daten::katalog_speichern(
            &p,
            "ollama-192-0-2-1",
            &json!({"stand": 7, "modelle": {"blind:7b": {"tools": false}, "klug": {"tools": true}}}),
        )
        .unwrap();
        let m = antworten(&json!({"op": "modelle", "anbieter": "ollama"}), &s);
        assert_eq!(m["wahl"], "klug", "Wahl ueber die Adresse: {m}");
        let a = antworten(&json!({"op": "chat", "anbieter": "ollama", "prompt": "x"}), &s);
        assert_eq!(a["modell"], "klug", "{a}");
        h.join().unwrap();
    }

    #[test]
    fn chat_ohne_gemessenen_katalog_misst_einmal_und_fragt_dann_erneut() {
        let (b, h) = ollama::tests::server(vec![
            (200, r#"{"models":[{"name":"a"},{"name":"b"}]}"#.into()),   // chat: Modellliste
            (200, r#"{"models":[{"name":"a"},{"name":"b"}]}"#.into()),   // katalog: tags
            (200, r#"{"capabilities":["completion"]}"#.into()),          // show a
            (200, r#"{"capabilities":["tools"]}"#.into()),               // show b
            (200, r#"{"models":[{"name":"a"},{"name":"b"}]}"#.into()),   // chat: Modellliste erneut
            (200, r#"{"message":{"content":"ok"}}"#.into()),             // chat
        ]);
        let (s, p) = stand_mit_daten("nachmessen", None);
        crate::daten::anbieter_speichern(&p, "lan", &json!({"typ": "ollama", "bezeichnung": "L", "adresse": b})).unwrap();
        let a = antworten(&json!({"op": "chat", "anbieter": "lan", "prompt": "x"}), &s);
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["modell"], "b", "{a}");
        assert_eq!(crate::daten::katalog_lesen(&p, "lan")["modelle"]["b"]["tools"], true);
        h.join().unwrap();
    }

    #[test]
    fn ein_genanntes_modell_loest_keine_messung_aus() {
        let (b, h) = ollama::tests::server(vec![(200, r#"{"message":{"content":"ok"}}"#.into())]);
        let (s, p) = stand_mit_daten("genannt", None);
        crate::daten::anbieter_speichern(&p, "lan", &json!({"typ": "ollama", "bezeichnung": "L", "adresse": b})).unwrap();
        let a = antworten(&json!({"op": "chat", "anbieter": "lan", "modell": "a", "prompt": "x"}), &s);
        assert_eq!(a["ok"], true, "{a}");
        h.join().unwrap();
    }
}
