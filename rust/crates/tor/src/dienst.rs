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

use crate::deepseek;
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
        // Die Modellwahl fuer den Chat (14.11.): je Anbieter drei Listen --
        // mit Werkzeugen, Spezialmodelle, unbekannt. `tools: null` ist
        // "nicht gemessen", nicht "ja" (DESIGN 5t).
        "modelle_auswahl" => modelle_auswahl(stand),
        "modelle" => match anfrage.get("anbieter").and_then(Value::as_str) {
            Some(a) => modelle(a, stand),
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
        // Guthaben je Anbieter (ROADMAP, Auftrag 13.11.). `neu: true` ist der
        // Knopf in der Oberflaeche; `Retry-After` bindet auch ihn.
        "quota_lesen" => crate::quota::op_lesen(&stand.daten, anfrage, jetzt_s()),
        // Websuche ist ein Werkzeug des Gateways (DESIGN Regel 5r): der Agent
        // hat kein Netz, hier wird gesucht. Quellen stehen in wahl.json.
        "web_suche" => {
            // Der Schluessel der Suchquelle gehoert dem Gateway und steht in
            // seiner Umgebung (`.env`, nur das Gateway liest sie, 5l).
            let schluessel = std::env::var("OLLAMA_API_KEY").ok();
            crate::suche::op_web_suche(
                anfrage,
                &crate::daten::wahl_laden(&stand.daten).unwrap_or_else(|_| json!({})),
                schluessel.as_deref().filter(|s| !s.trim().is_empty()),
            )
        }
        "netzsuche" => crate::netzsuche::durchgang(stand),
        // Eine Adresse holen -- nur mit Freigabe (DESIGN 5r, Stufe 2 der
        // Regel "Freigabe je Werkzeug auf Zeit"). Die Pruefung sitzt hier,
        // vor dem Verbinden: der Agent fragt nie selbst "darf ich?".
        "web_abruf" => {
            let url = anfrage.get("url").and_then(Value::as_str).unwrap_or("");
            crate::abruf::durchgang(&stand.daten, url, jetzt_s())
        }
        // Freigabe je Werkzeug auf Zeit (DESIGN, Regel "Freigabe je Werkzeug
        // auf Zeit"). Lesen und Setzen gehoeren dem Nutzer; `freigabe_pruefen`
        // ist die Frage des Ausfuehrers vor dem Handeln.
        "freigabe_lesen" => json!({"ok": true, "freigaben": crate::freigaben::laden(&stand.daten)}),
        "freigabe_setzen" => {
            let name = anfrage.get("werkzeug").and_then(Value::as_str).unwrap_or("");
            let wert = anfrage.get("wert").cloned().unwrap_or(Value::Null);
            match crate::freigaben::setzen(&stand.daten, name, &wert, jetzt_s()) {
                Ok(v) => json!({"ok": true, "werkzeug": name, "freigabe": v}),
                Err((code, text)) => zeile::fehlerantwort(code, &text),
            }
        }
        "freigabe_pruefen" => {
            let name = anfrage.get("werkzeug").and_then(Value::as_str).unwrap_or("");
            let ziel = anfrage.get("ziel").and_then(Value::as_str);
            let a = crate::freigaben::pruefen(&stand.daten, name, ziel, jetzt_s());
            json!({"ok": true, "werkzeug": name, "ziel": anfrage.get("ziel").cloned(), "erlaubt": a["erlaubt"], "grund": a["grund"], "bis": a["bis"]})
        }
        // Die Host-Tabelle der Fernausfuehrung (DESIGN, Regel "Jedes
        // Werkzeug bekommt nur seine Rechte"). Der Agent darf **nur**
        // vorschlagen: `ssh_vorschlag` legt an und aendert nie. Lesen, Setzen
        // und Loeschen gehoeren dem Nutzer (Web-Modul).
        "ssh_hosts" => json!({"ok": true, "hosts": crate::ssh::laden(&stand.daten)["hosts"]}),
        // Tailscale: **nur lesen** (LocalAPI, GET). Fehlt der Socket, ist das
        // kein Fehler -- Tailscale ist opt-in (DESIGN, "Tailscale/Headscale").
        // Was das Tailnet **ändert**, hängt an der Freigabe `tailscale` --
        // ein Knopf, der den Netzzugang abschaltet, gehört nicht immer an.
        "tailscale_steuern" => {
            let aktion = anfrage.get("aktion").and_then(Value::as_str).unwrap_or("");
            let frei = crate::freigaben::pruefen(&stand.daten, "tailscale", None, jetzt_s());
            if frei["erlaubt"] != true {
                json!({"ok": false, "fehler": {"code": "tailscale_gesperrt",
                    "text": format!("Das Tailnet zu steuern ist nicht freigegeben: {}",
                        frei["grund"].as_str().unwrap_or("ohne Grund"))}})
            } else {
                match crate::tailscale::steuern(aktion) {
                    Ok(t) => json!({"ok": true, "aktion": aktion, "text": t}),
                    Err(e) => zeile::fehlerantwort("tailscale_fehler", &e),
                }
            }
        }
        "tailscale" => {
            let pfad = std::env::var("CHIMERA_TAILSCALE_SOCKET")
                .unwrap_or_else(|_| crate::tailscale::SOCKET.to_string());
            if !std::path::Path::new(&pfad).exists() {
                json!({"ok": true, "eingerichtet": false,
                       "socket": pfad,
                       "hinweis": "tailscaled laeuft auf diesem Geraet nicht. Tailscale ist eine Zutat, die der Nutzer dazunimmt."})
            } else {
                match crate::tailscale::holen(&pfad) {
                    Ok(z) => json!({"ok": true, "eingerichtet": true, "socket": pfad,
                        "zustand": z.backend, "hostname": z.hostname, "adressen": z.adressen,
                        "peers_gesamt": z.peers_gesamt, "peers_online": z.peers_online}),
                    Err(e) => zeile::fehlerantwort("nicht_lesbar", &format!("Die Tailscale-LocalAPI antwortet nicht: {e}")),
                }
            }
        }
        "ssh_host_setzen" => {
            let name = anfrage.get("host").and_then(Value::as_str).unwrap_or("");
            let wert = anfrage.get("wert").cloned().unwrap_or(Value::Null);
            match crate::ssh::setzen(&stand.daten, name, &wert) {
                Ok(v) => json!({"ok": true, "host": name, "eintrag": v}),
                Err((code, text)) => zeile::fehlerantwort(code, &text),
            }
        }
        "ssh_host_loeschen" => {
            let name = anfrage.get("host").and_then(Value::as_str).unwrap_or("");
            match crate::ssh::loeschen(&stand.daten, name) {
                Ok(weg) => json!({"ok": true, "geloescht": weg}),
                Err((code, text)) => zeile::fehlerantwort(code, &text),
            }
        }
        "ssh_aufnahme" => {
            let host = anfrage.get("host").and_then(Value::as_str).unwrap_or("");
            crate::ssh::op_ssh_aufnahme(&stand.daten, host, jetzt_s())
        }
        // Den Hostschluessel holt **das Gateway** selbst (entschieden smilez,
        // 13.11.): `ssh-keyscan` als Kindprozess mit fester argv, kein eigener
        // SSH-Code. Der Abruf schreibt nichts -- bestaetigt wird im Modul.
        "ssh_schluessel_lesen" => {
            let host = anfrage.get("host").and_then(Value::as_str).unwrap_or("");
            if host.is_empty() {
                zeile::fehlerantwort("wert_ungueltig", "Feld \"host\" fehlt.")
            } else {
                crate::ssh::op_ssh_schluessel_lesen(&stand.daten, host)
            }
        }
        "ssh" => {
            let host = anfrage.get("host").and_then(Value::as_str).unwrap_or("");
            let befehl = anfrage.get("befehl").and_then(Value::as_str).unwrap_or("");
            crate::ssh::op_ssh(&stand.daten, host, befehl, jetzt_s())
        }
        "ssh_vorschlag" => {
            let feld = |k: &str| anfrage.get(k).and_then(Value::as_str).unwrap_or("").to_string();
            match crate::ssh::vorschlag(
                &stand.daten,
                &feld("host"),
                &feld("adresse"),
                &feld("nutzer"),
                anfrage.get("port").and_then(Value::as_u64),
                &feld("notiz"),
            ) {
                Ok(v) => {
                    let mut v = v;
                    if let Some(o) = v.as_object_mut() {
                        o.insert("ok".into(), json!(true));
                    }
                    v
                }
                Err((code, text)) => zeile::fehlerantwort(code, &text),
            }
        }
        "" => zeile::fehlerantwort("op_fehlt", "Die Anfrage braucht ein Feld \"op\"."),
        andere => crate::daten::op(andere, anfrage, &stand.daten).unwrap_or_else(|| {
            zeile::fehlerantwort("op_unbekannt", &format!("Unbekannte Operation: {andere}"))
        }),
    }
}

/// Ein Anbieter aus der Anbietertabelle: `(typ, adresse)`. `ollama` ohne
/// eigene Datei ist der Anbieter aus der `.env` (Rueckfall bis zur
/// Umstellung); jede andere Id muss eine Datei haben. `Ok(None)` als Adresse
/// heisst „nicht eingerichtet“ oder „Vorgabe des Typs“ (DeepSeek etwa nimmt
/// dann seine feste Basis) -- die Antwort der Operation sagt das selbst.
///
/// Der Typ entscheidet, **welches Modul** den Anbieter bedient. Kein Weg
/// bedient „irgendeinen“ Typ: ein Eintrag, den kein Modul kennt, wird
/// benannt und nicht geraten.
fn anbieter_finden(id: &str, stand: &Stand) -> Result<(String, Option<String>), Value> {
    if !crate::daten::id_gueltig(id) {
        return Err(zeile::fehlerantwort("anbieter_unbekannt", &format!("Unbekannter Anbieter: {id}")));
    }
    let (liste, _) = crate::daten::anbieter_laden(&stand.daten);
    if let Some((_, a)) = liste.iter().find(|(i, _)| i == id) {
        if a.get("an").and_then(Value::as_bool) == Some(false) {
            return Err(zeile::fehlerantwort("anbieter_aus", &format!("Anbieter {id} ist ausgeschaltet.")));
        }
        let typ = a["typ"].as_str().unwrap_or("").trim().to_string();
        let adresse = a["adresse"].as_str().map(str::trim).filter(|s| !s.is_empty()).map(str::to_string);
        return Ok((typ, adresse));
    }
    if id == "ollama" {
        return Ok(("ollama".to_string(), stand.ollama.clone()));
    }
    Err(zeile::fehlerantwort("anbieter_unbekannt", &format!("Unbekannter Anbieter: {id}")))
}

/// Der Typ, den dieser Weg nicht bedient -- mit Klartext statt „unbekannt“.

/// Eine Modellliste in die drei Rubriken der Chat-Auswahl zerlegen.
///
/// `katalog` ist der gemessene Stand (`/api/show` -> `capabilities`). Was
/// dort `tools: true` sagt, darf in die Chat-Auswahl; `false` heisst
/// Spezialmodell (mit seiner Art); fehlender Eintrag heisst **unbekannt**
/// und bleibt draussen. Unbekannt als "kann Werkzeuge" zu behandeln waere
/// genau der Fehler, den DESIGN 5t verbietet.
fn auswahl_rubriken(modelle: &[String], katalog: &Value, herkunft: &str) -> (Vec<Value>, Vec<Value>, Vec<Value>) {
    let eintraege = katalog["modelle"].as_object();
    let mut chat = Vec::new();
    let mut spezial = Vec::new();
    let mut unbekannt = Vec::new();
    for m in modelle {
        let e = eintraege
            .and_then(|k| k.get(m))
            .cloned()
            .unwrap_or_else(|| json!({}));
        match e["tools"].as_bool() {
            Some(true) => chat.push(json!({"modell": m, "herkunft": herkunft})),
            Some(false) => spezial.push(json!({
                "modell": m,
                "art": art_aus(&e),
                "herkunft": herkunft,
            })),
            None => unbekannt.push(json!({"modell": m, "herkunft": "nicht gemessen"})),
        }
    }
    (chat, spezial, unbekannt)
}

/// Die Art eines Modells, das keine Werkzeuge kann: was es sonst kann.
fn art_aus(eigenschaften: &Value) -> &'static str {
    let f: Vec<&str> = eigenschaften["faehigkeiten"]
        .as_array()
        .map(|a| a.iter().filter_map(Value::as_str).collect())
        .unwrap_or_default();
    for (name, art) in [
        ("vision", "vision"),
        ("image", "bild"),
        ("audio", "audio"),
        ("embedding", "embedding"),
    ] {
        if f.iter().any(|x| *x == name) {
            return art;
        }
    }
    "ohne Werkzeuge"
}

/// `op: modelle_auswahl` -- was im Chat waehlbar ist, je Anbieter.
fn modelle_auswahl(stand: &Stand) -> Value {
    let (liste, meldungen) = crate::daten::anbieter_laden(&stand.daten);
    let mut anbieter = Vec::new();
    let mut meld = Vec::new();
    for (id, a) in &liste {
        if a["an"].as_bool() == Some(false) {
            continue;
        }
        let typ = a["typ"].as_str().unwrap_or("");
        let r = modelle(id, stand);
        if r["ok"] != true {
            meld.push(json!({"anbieter": id, "text": r["fehler"]["text"]}));
            continue;
        }
        let namen: Vec<String> = r["modelle"]
            .as_array()
            .map(|a| a.iter().filter_map(Value::as_str).map(String::from).collect())
            .unwrap_or_default();
        let (chat, spezial, unbekannt, herkunft) = if typ == "deepseek" {
            // Die API liefert keine Eigenschaften; die Doku sagt, dass alle
            // Chat-Modelle Werkzeuge koennen. Das ist eine Herkunft, keine
            // Messung -- und steht deshalb so da.
            (namen.iter().map(|m| json!({"modell": m, "herkunft": "dokumentiert"})).collect(), Vec::new(), Vec::new(), "dokumentiert")
        } else {
            let k = katalog_fuer(id, a["adresse"].as_str(), stand);
            let (c, s, u) = auswahl_rubriken(&namen, &k, "gemessen");
            (c, s, u, "gemessen")
        };
        anbieter.push(json!({
            "id": id,
            "typ": typ,
            "bezeichnung": a["bezeichnung"],
            "host": r["host"],
            "herkunft": herkunft,
            "chat": chat,
            "spezial": spezial,
            "unbekannt": unbekannt,
        }));
    }
    let mut alle_meld = meldungen.iter().map(|m| json!({"quelle": m.quelle, "text": m.text})).collect::<Vec<_>>();
    alle_meld.extend(meld);
    json!({"ok": true, "anbieter": anbieter, "meldungen": alle_meld})
}

fn typ_nicht_bedient(id: &str, typ: &str) -> Value {
    zeile::fehlerantwort(
        "anbieter_unbekannt",
        &format!("Anbieter {id} hat den Typ {typ}, den dieser Weg nicht bedient."),
    )
}

/// Die Adresse eines Ollama-Anbieters, oder der Fehler, dass er keiner ist.
fn ollama_adresse(id: &str, stand: &Stand) -> Result<Option<String>, Value> {
    let (typ, adr) = anbieter_finden(id, stand)?;
    if typ != "ollama" {
        return Err(typ_nicht_bedient(id, &typ));
    }
    Ok(ollama::adresse_aus(adr.as_deref()))
}

/// `op: modelle`: welcher Weg fragt, entscheidet der **Typ** des Anbieters.
fn modelle(id: &str, stand: &Stand) -> Value {
    match anbieter_finden(id, stand) {
        Ok((typ, adr)) if typ == "ollama" => {
            let a = ollama::adresse_aus(adr.as_deref());
            ollama::op_modelle(a.as_deref(), &katalog_fuer(id, a.as_deref(), stand), &bevorzugt(id, stand))
        }
        Ok((typ, adr)) if typ == "deepseek" => deepseek::op_modelle(
            &deepseek::basis_aus(adr.as_deref()),
            schluessel_von(id, stand).as_deref(),
            &bevorzugt(id, stand),
            id,
        ),
        Ok((typ, _)) => typ_nicht_bedient(id, &typ),
        Err(f) => f,
    }
}

/// Der Schluessel eines Anbieters: erst die Ablage, die die Oberflaeche
/// fuellt (`config/geheim/`), dann die Umgebung. Beide sind Eigentum des
/// Gateways; der Agent sieht keinen Wert (DESIGN 5l).
fn schluessel_von(id: &str, stand: &Stand) -> Option<String> {
    crate::daten::schluessel_lesen(&stand.daten, id).or_else(deepseek::schluessel_aus_umgebung)
}

/// Der Strom ist ein Schalter des Nutzers (`wahl.json`); ein ausdruecklicher
/// Wert im Auftrag gilt vorher.
fn mit_stromwahl(anfrage: &Value, stand: &Stand) -> Value {
    let mut a = anfrage.clone();
    if a.get("stream").is_none() {
        a["stream"] = json!(stream_aus_wahl(stand));
    }
    a
}

/// `op: chat`: welcher Weg spricht, entscheidet der **Typ** des Anbieters.
fn chat(id: &str, anfrage: &Value, stand: &Stand) -> Value {
    match anbieter_finden(id, stand) {
        Ok((typ, adr)) if typ == "ollama" => {
            chat_ollama(id, ollama::adresse_aus(adr.as_deref()), anfrage, stand)
        }
        Ok((typ, adr)) if typ == "deepseek" => {
            let a = mit_stromwahl(anfrage, stand);
            deepseek::op_chat(
                id,
                adr.as_deref(),
                schluessel_von(id, stand).as_deref(),
                &a,
                &bevorzugt(id, stand),
            )
        }
        Ok((typ, _)) => typ_nicht_bedient(id, &typ),
        Err(f) => f,
    }
}

/// `op: chat` mit einem Anbieter vom Typ `ollama`: nimmt den gespeicherten
/// Katalog mit, damit ohne genanntes Modell nach dem gemessenen `tools`
/// gewaehlt wird (DESIGN 5n, „Das Modell kommt vom Server"). Ist nichts
/// gemessen (frischer Anbieter, Katalog leer), wird **einmal** gemessen und
/// erneut gefragt -- sonst bliebe ein Anbieter, den die Netzsuche nicht
/// auffrischt (`auto: false`), dauerhaft ohne Antwort.
fn chat_ollama(id: &str, adr: Option<String>, anfrage: &Value, stand: &Stand) -> Value {
    let adr = match adr {
        Some(a) => a,
        None => return ollama::op_chat(None, anfrage, &json!({}), &[]),
    };
    let mut katalog = katalog_fuer(id, Some(&adr), stand);
    // Der Schalter gehoert dem Nutzer (wahl.json); ein ausdruecklicher Wert im
    // Auftrag gilt vor (Tests, spaetere Oberflaechen).
    let anfrage = &mit_stromwahl(anfrage, stand);
    let a = ollama::op_chat(Some(&adr), anfrage, &katalog, &bevorzugt(id, stand));
    let genannt = anfrage.get("modell").and_then(Value::as_str).is_some_and(|m| !m.is_empty());
    if a["fehler"]["code"] == "kein_modell" && !genannt && !katalog_gemessen(&katalog) {
        let r = katalog_aktualisieren(&json!({"id": id}), stand, ollama::KATALOG_BUDGET_SOFORT);
        if r["ok"] == true {
            katalog = crate::daten::katalog_lesen(&stand.daten, id);
            return ollama::op_chat(Some(&adr), anfrage, &katalog, &bevorzugt(id, stand));
        }
    }
    a
}

/// Die Reihenfolge, die der Nutzer in `wahl.json` fuer diesen Anbieter
/// vorgegeben hat (5h). Fehlt die Datei oder ist sie unlesbar, ist die Liste
/// leer -- dann gilt die Reihenfolge des Servers (kein stiller Ausfall).
/// Ist der Strom eingeschaltet? Steht in `wahl.json` (Vorgabe: aus).
fn stream_aus_wahl(stand: &Stand) -> bool {
    crate::daten::wahl_laden(&stand.daten)
        .ok()
        .and_then(|w| w["stream"].as_bool())
        .unwrap_or(false)
}

fn bevorzugt(id: &str, stand: &Stand) -> Vec<String> {
    match crate::daten::wahl_laden(&stand.daten) {
        Ok(w) => crate::daten::bevorzugt(&w, id),
        Err(_) => Vec::new(),
    }
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

/// Sekunden seit der Epoche. Der Dienst rechnet mit derselben Uhr wie die
/// Freigaben -- eine Quelle, damit "abgelaufen" ueberall dasselbe heisst.
fn jetzt_s() -> u64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
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

    /// Der JSON-Koerper einer aufgezeichneten Anfrage (nicht die Kopfzeilen).
    fn koerper_von(roh: &str) -> Value {
        let i = roh.find("\r\n\r\n").expect("Kopfzeilen fehlen");
        serde_json::from_str(&roh[i + 4..]).expect("Koerper ist kein JSON")
    }

    #[test]
    fn der_strom_schalter_aus_wahl_json_gilt_fuer_den_chat() {
        // Aus: kein "stream" im Koerper. An: "stream": true -- und dann muss
        // die Antwort trotzdem als fertige Zeile ankommen (Teilstuecke).
        let (b, h) = ollama::tests::server(vec![
            (200, r#"{"message":{"content":"ok"}}"#.into()),
        ]);
        let (s, p) = stand_mit_daten("strom-aus", None);
        crate::daten::anbieter_speichern(&p, "lan", &json!({"typ": "ollama", "bezeichnung": "L", "adresse": b.clone()})).unwrap();
        let a = antworten(&json!({"op": "chat", "anbieter": "lan", "modell": "m", "prompt": "x"}), &s);
        assert_eq!(a["ok"], true, "{a}");
        let gesehen = h.join().unwrap();
        let koerper = koerper_von(&gesehen[0]);
        assert_eq!(koerper["stream"], false, "aus heisst aus");

        let antwort = r#"{"message":{"content":"Hallo"},"done":false}
{"message":{"content":" Welt"},"done":true,"eval_count":2}"#;
        let (b2, h2) = ollama::tests::server(vec![(200, antwort.into())]);
        let (s2, p2) = stand_mit_daten("strom-an", None);
        crate::daten::anbieter_speichern(&p2, "lan", &json!({"typ": "ollama", "bezeichnung": "L", "adresse": b2})).unwrap();
        crate::daten::wahl_speichern(&p2, &json!({"stream": true})).unwrap();
        let a2 = antworten(&json!({"op": "chat", "anbieter": "lan", "modell": "m", "prompt": "x"}), &s2);
        assert_eq!(a2["text"], "Hallo Welt", "Teilstuecke zusammengesetzt: {a2}");
        let g2 = h2.join().unwrap();
        assert_eq!(koerper_von(&g2[0])["stream"], true, "an heisst an");
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

#[cfg(test)]
mod tests_deepseek {
    use super::*;

    fn stand_mit_daten(n: &str) -> (Stand, crate::daten::Pfade) {
        let d = std::env::temp_dir().join(format!("chimera-ds-{n}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let p = crate::daten::Pfade::neu(d.join("config"), d.join("state"));
        (Stand::mit(None, p.clone()), p)
    }

    #[test]
    fn anbieter_vom_typ_deepseek_wird_ueber_sein_modul_bedient() {
        let (b, h) = ollama::tests::server(vec![(
            200,
            r#"{"choices":[{"message":{"content":"Hallo"}}],"usage":{"prompt_tokens":3,"completion_tokens":1}}"#
                .into(),
        )]);
        let (s, p) = stand_mit_daten("chat");
        crate::daten::anbieter_speichern(
            &p,
            "ds",
            &json!({"typ": "deepseek", "bezeichnung": "DeepSeek", "adresse": b}),
        )
        .unwrap();
        // Der Schlüssel liegt in der Ablage, nicht in der Umgebung: dieselbe
        // Stelle, die die Oberfläche füllt.
        crate::daten::schluessel_setzen(&p, "ds", "sk-aus-der-ablage").unwrap();
        let a = antworten(&json!({"op": "chat", "anbieter": "ds", "modell": "deepseek-flash", "prompt": "x"}), &s);
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["text"], "Hallo");
        assert_eq!(a["anbieter"], "ds");
        let anfragen = h.join().unwrap();
        assert!(anfragen[0].starts_with("POST /chat/completions"), "{}", anfragen[0]);
        assert!(anfragen[0].to_lowercase().contains("authorization: bearer sk-aus-der-ablage"));
    }

    #[test]
    fn modelle_gehen_fuer_deepseek_an_das_deepseek_modul() {
        let (b, h) = ollama::tests::server(vec![(
            200,
            r#"{"data":[{"id":"deepseek-flash"},{"id":"deepseek-v4-pro"}]}"#.into(),
        )]);
        let (s, p) = stand_mit_daten("modelle");
        crate::daten::anbieter_speichern(
            &p,
            "ds",
            &json!({"typ": "deepseek", "bezeichnung": "DeepSeek", "adresse": b}),
        )
        .unwrap();
        crate::daten::schluessel_setzen(&p, "ds", "k").unwrap();
        let a = antworten(&json!({"op": "modelle", "anbieter": "ds"}), &s);
        assert_eq!(a["ok"], true, "{a}");
        assert_eq!(a["modelle"], json!(["deepseek-flash", "deepseek-v4-pro"]));
        assert_eq!(a["wahl"], "deepseek-flash");
        h.join().unwrap();
    }

    #[test]
    fn ein_ausgeschalteter_deepseek_anbieter_wird_nicht_gefragt() {
        let (s, p) = stand_mit_daten("aus");
        crate::daten::anbieter_speichern(
            &p,
            "ds",
            &json!({"typ": "deepseek", "bezeichnung": "D", "adresse": "http://127.0.0.1:1", "an": false}),
        )
        .unwrap();
        let a = antworten(&json!({"op": "chat", "anbieter": "ds", "prompt": "x"}), &s);
        assert_eq!(a["fehler"]["code"], "anbieter_aus", "{a}");
    }

    #[test]
    fn ein_typ_ohne_modul_wird_benannt() {
        let (s, p) = stand_mit_daten("typ");
        crate::daten::anbieter_speichern(&p, "cloud", &json!({"typ": "litellm", "bezeichnung": "C"})).unwrap();
        let a = antworten(&json!({"op": "chat", "anbieter": "cloud", "prompt": "x"}), &s);
        assert_eq!(a["fehler"]["code"], "anbieter_unbekannt");
        assert!(a["fehler"]["text"].as_str().unwrap().contains("litellm"), "{a}");
    }
}

#[cfg(test)]
mod tests_auswahl {
    use super::*;

    fn namen(v: &[Value]) -> Vec<String> {
        v.iter().map(|e| e["modell"].as_str().unwrap_or("").to_string()).collect()
    }

    // Die Chat-Auswahl zeigt nur, was Werkzeuge kann. `false` ist ein
    // Spezialmodell, **fehlend** ist unbekannt -- und unbekannt ist nicht
    // "kann Werkzeuge" (DESIGN 5t, Nutzerauftrag 14.11.).
    #[test]
    fn nur_gemessene_werkzeuge_stehen_zur_wahl() {
        let modelle: Vec<String> = ["tools-an", "tools-aus", "unbekannt", "leer"]
            .iter().map(|s| s.to_string()).collect();
        let katalog = json!({"modelle": {
            "tools-an": {"tools": true, "faehigkeiten": ["completion", "tools"]},
            "tools-aus": {"tools": false, "faehigkeiten": ["completion", "vision"]},
            "unbekannt": {"tools": null},
            "leer": {}
        }});
        let (chat, spezial, unbekannt) = auswahl_rubriken(&modelle, &katalog, "gemessen");
        assert_eq!(namen(&chat), ["tools-an"]);
        assert_eq!(namen(&spezial), ["tools-aus"]);
        assert_eq!(namen(&unbekannt), ["unbekannt", "leer"]);
        // Die Art des Spezialmodells kommt aus seinen Faehigkeiten.
        assert_eq!(spezial[0]["art"], "vision");
        // Die Herkunft steht dabei -- eine Messung wird nicht als Doku verkauft.
        assert_eq!(chat[0]["herkunft"], "gemessen");
    }

    #[test]
    fn spezialarten_werden_benannt() {
        for (faehigkeiten, art) in [
            (json!(["completion", "vision"]), "vision"),
            (json!(["completion", "image"]), "bild"),
            (json!(["completion", "audio"]), "audio"),
            (json!(["embedding"]), "embedding"),
            (json!(["completion"]), "ohne Werkzeuge"),
        ] {
            let e = json!({"tools": false, "faehigkeiten": faehigkeiten});
            assert_eq!(art_aus(&e), art, "{e}");
        }
    }

    // Ohne Katalog ist alles unbekannt -- und damit nicht waehlbar. Das ist
    // die Haelfte der Zusage: lieber nichts anbieten als ein Modell, das
    // Werkzeuge nur zu versprechen scheint.
    #[test]
    fn ohne_katalog_ist_nichts_waehlbar() {
        let m: Vec<String> = vec!["a".into(), "b".into()];
        let (chat, spezial, unbekannt) = auswahl_rubriken(&m, &json!({}), "gemessen");
        assert!(chat.is_empty() && spezial.is_empty());
        assert_eq!(namen(&unbekannt), ["a", "b"]);
    }
}
