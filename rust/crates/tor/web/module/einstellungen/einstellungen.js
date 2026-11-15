"use strict";
// Einstellungen-Modul (DESIGN, Regel „Einstellungen am Gerät"): Bildschirm
// (Kontrast, Helligkeit, Nachtfenster), Mikrofon und Tonausgabe samt
// Lautstärke, und das Kennwort der Oberfläche.
//
// **Kein eigener Zustand.** Was hier steht, kommt aus zwei Quellen, die es
// schon gibt: Kontrast und Helligkeit liegen in der Avatar-Ablage des Dienstes
// (`einstellungen/avatar.json`, Op `avatar_setzen`), Mikrofon und Lautsprecher
// im `AudioSchalter` desselben Dienstes (Op `audio_setzen`). Diese Seite ist
// eine zweite Tür zu denselben Werten, keine zweite Wahrheit — sie schreibt
// nichts selbst und merkt sich nichts.
//
// Das Kennwort prüft und schreibt das Gateway allein (es hält den Hash); die
// Vorprüfung hier ist Bequemlichkeit, nicht die Entscheidung.

const STIL = `
  :host { display:block; padding:1rem; max-width:44rem; }
  h3 { margin:.2rem 0 .6rem; font:1rem/1.3 system-ui, sans-serif; }
  .karte { border:1px solid #2b2f3b; border-radius:.6rem; padding:.75rem;
           margin:0 0 .75rem; background:#1c1f28; }
  .karte strong { display:block; margin:0 0 .4rem; }
  .zeile { display:flex; align-items:center; gap:.6rem; flex-wrap:wrap; }
  .zeile .wert { color:#8a90a2; font-size:.85rem; margin-left:auto; }
  label { display:block; font-size:.85rem; color:#8a90a2; margin:.5rem 0 .2rem; }
  input[type=range] { width:100%; }
  input[type=time], input[type=password] {
           width:100%; font:inherit; padding:.4rem; border-radius:.4rem;
           border:1px solid #2b2f3b; background:#12141a; color:#e6e8ee; }
  label.schalter { display:flex; align-items:center; gap:.45rem; color:#e6e8ee;
           font-size:.9rem; margin:.35rem 0 .6rem; }
  label.schalter input { width:1.1rem; height:1.1rem; }
  button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem;
           padding:.4rem .9rem; font:inherit; cursor:pointer; }
  button.zweit { background:#2b2f3b; color:#e6e8ee; }
  button:disabled { opacity:.6; cursor:default; }
  .klein { color:#8a90a2; font-size:.85rem; margin:.35rem 0 0; }
  .fehler { color:#ff7a7a; } .gut { color:#7be0a0; } .meldung { color:#ffd989; }
  .aus { color:#ff9b9b; } .an { color:#7be0a0; }
`;

/// Wie ein Audio-Kanal in Worten aussieht (reine Funktion, ohne DOM —
/// `tests/js/einstellungen_seite.mjs` prüft sie).
///
/// Der Punkt: **Ist der Kanal aus, bleibt die eingestellte Lautstärke
/// sichtbar.** „aus, 0 %" wäre gelogen (der Regler steht auf 80), und ein
/// bloßes „aus" verschweigt, was beim Einschalten kommt.
function audioText(audio, was) {
  if (!audio) return "nicht lesbar";
  const an = was === "mikrofon" ? !!audio.mikrofon_an : !!audio.lautsprecher_an;
  const roh = was === "mikrofon" ? audio.lautstaerke_mikrofon
                                  : audio.lautstaerke_lautsprecher;
  const prozent = (typeof roh === "number" && isFinite(roh)) ? `${roh} %` : "nicht messbar";
  if (an) return `an · ${prozent}`;
  return roh === null || roh === undefined ? "aus" : `aus · ${prozent} gilt beim Einschalten`;
}

/// Was die Seite vor dem Absenden prüft. `null` heißt: abschicken.
///
/// Die Entscheidung fällt im Gateway (Länge, Gleichheit, altes Passwort); was
/// hier steht, ist die billige Vorprüfung, damit ein Tippfehler keine
/// Anfrage kostet. Beide Regeln nennen **denselben** Grund wie der Server —
/// zwei verschiedene Texte für denselben Fehler verwirren nur.
const PASSWORT_MIN = 8;
function passwortFehler(alt, neu, wiederholung) {
  if (!alt) return "Bitte das bisherige Passwort eingeben.";
  if (!neu || neu.length < PASSWORT_MIN) {
    return `Das neue Passwort braucht mindestens ${PASSWORT_MIN} Zeichen.`;
  }
  if (neu !== wiederholung) return "Die beiden neuen Eingaben sind nicht gleich.";
  return null;
}

class ChimeraEinstellungen extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${STIL}</style>
      <h3>Einstellungen</h3>

      <div class="karte">
        <strong>Bildschirm</strong>
        <label for="kontrast">Kontrast: <span id="kwert">45</span> %</label>
        <input type="range" id="kontrast" min="0" max="100" step="5" value="45">
        <p class="klein">Hebt alle Farben gemeinsam an — für helle Räume (kein
        Lichtsensor am Gerät).</p>
        <label class="schalter"><input type="checkbox" id="nacht_dimmen">
        Nachts von selbst dunkler</label>
        <label for="nacht_von">Dunkel ab</label>
        <input type="time" id="nacht_von" value="22:00">
        <label for="nacht_bis">Wieder hell ab</label>
        <input type="time" id="nacht_bis" value="06:00">
        <label for="helligkeit_tag">Helligkeit tags: <span id="twert">255</span> von 255</label>
        <input type="range" id="helligkeit_tag" min="20" max="255" step="5" value="255">
        <label for="helligkeit_nacht">Helligkeit nachts: <span id="nwert">80</span> von 255</label>
        <input type="range" id="helligkeit_nacht" min="20" max="255" step="5" value="80">
      </div>

      <div class="karte">
        <strong>Mikrofon</strong>
        <div class="zeile">
          <button id="mikrofon">aus</button>
          <span class="wert" id="mikrofon_wert">—</span>
        </div>
        <label for="mikrofon_pegel">Lautstärke: <span id="mwert">—</span> %</label>
        <input type="range" id="mikrofon_pegel" min="0" max="100" step="5" value="80">
        <p class="klein">Grundstellung ist <em>aus</em>: Das Gerät hört nicht
        zu, solange es nichts damit anfängt. Im Aus bleibt die eingestellte
        Lautstärke gemerkt.</p>
      </div>

      <div class="karte">
        <strong>Tonausgabe</strong>
        <div class="zeile">
          <button id="lautsprecher">aus</button>
          <span class="wert" id="lautsprecher_wert">—</span>
        </div>
        <label for="lautsprecher_pegel">Lautstärke: <span id="lwert">—</span> %</label>
        <input type="range" id="lautsprecher_pegel" min="0" max="100" step="5" value="80">
        <p class="klein">Der Freigabeton schaltet die Wiedergabe selbst an und
        danach wieder aus.</p>
      </div>

      <div class="karte">
        <strong>Kennwort ändern</strong>
        <label for="alt">Bisheriges Kennwort</label>
        <input type="password" id="alt" autocomplete="current-password">
        <label for="neu">Neues Kennwort</label>
        <input type="password" id="neu" autocomplete="new-password">
        <label for="wiederholung">Neues Kennwort wiederholen</label>
        <input type="password" id="wiederholung" autocomplete="new-password">
        <p class="klein">Mindestens ${PASSWORT_MIN} Zeichen. Andere offene
        Anmeldungen werden dabei abgemeldet.</p>
        <p><button id="pw_aendern">Kennwort ändern</button></p>
      </div>

      <p id="meldung" class="klein"></p>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
    this._binden();
    this.laden();
  }

  _melden(text, art = "") {
    const m = this.$("meldung");
    if (!m) return;
    m.textContent = text;
    m.className = "klein " + art;
  }

  _binden() {
    // Bildschirm: alle sechs Werte gehen über denselben Weg
    // (`/api/einstellungen/display` → Op `avatar_setzen`). Nur beim Loslassen
    // senden — jede Zwischenstufe zu schreiben hieße, je Pixel eine Datei zu
    // ersetzen.
    const regler = [
      ["kontrast", "kontrast", "kwert", Number],
      ["helligkeit_tag", "helligkeit_tag", "twert", Number],
      ["helligkeit_nacht", "helligkeit_nacht", "nwert", Number],
    ];
    for (const [id, feld, anzeige, deuten] of regler) {
      const e = this.$(id);
      e.oninput = () => { this.$(anzeige).textContent = e.value; };
      e.onchange = () => this.setzenDisplay(feld, deuten(e.value));
    }
    const dimmen = this.$("nacht_dimmen");
    dimmen.onchange = () => this.setzenDisplay("nacht_dimmen", dimmen.checked);
    const von = this.$("nacht_von");
    von.onchange = () => this.setzenDisplay("nacht_von", von.value);
    const bis = this.$("nacht_bis");
    bis.onchange = () => this.setzenDisplay("nacht_bis", bis.value);

    // Audio: der Knopf schaltet, der Regler stellt ein.
    this.$("mikrofon").onclick = () => this.schalten("mikrofon");
    this.$("lautsprecher").onclick = () => this.schalten("lautsprecher");
    for (const [id, was] of [["mikrofon_pegel", "mikrofon"],
                             ["lautsprecher_pegel", "lautsprecher"]]) {
      const e = this.$(id);
      e.onchange = () => this.pegelSetzen(was, Number(e.value));
    }

    this.$("pw_aendern").onclick = () => this.kennwortAendern();
  }

  async laden() {
    const r = await window.chimera.api("/api/einstellungen/stand");
    if (!r.ok) { this._melden("Nicht lesbar: " + text(r), "fehler"); return; }
    if (r.display) this._displayFuellen(r.display);
    if (r.audio) this._audioFuellen(r.audio);
    else this._melden("Audio nicht verfügbar: " + (r.audio_fehler || "kein Gerät"), "meldung");
  }

  _displayFuellen(w) {
    const k = this.$("kontrast");
    k.max = String(w.kontrast_max || 100);
    k.value = String(w.kontrast ?? 45);
    this.$("kwert").textContent = k.value;
    const t = this.$("helligkeit_tag");
    t.value = String(w.helligkeit_tag ?? 255);
    this.$("twert").textContent = t.value;
    const n = this.$("helligkeit_nacht");
    n.value = String(w.helligkeit_nacht ?? 80);
    this.$("nwert").textContent = n.value;
    this.$("nacht_dimmen").checked = !!w.nacht_dimmen;
    this.$("nacht_von").value = w.nacht_von || "22:00";
    this.$("nacht_bis").value = w.nacht_bis || "06:00";
    for (const h of w.hinweise || []) this._melden(h, "meldung");
  }

  _audioFuellen(a) {
    this.audio = a;
    this.$("mikrofon_wert").textContent = audioText(a, "mikrofon");
    this.$("lautsprecher_wert").textContent = audioText(a, "lautsprecher");
    for (const [id, was, knopf] of [["mikrofon_pegel", "mikrofon", "mikrofon"],
                                    ["lautsprecher_pegel", "lautsprecher", "lautsprecher"]]) {
      const roh = was === "mikrofon" ? a.lautstaerke_mikrofon : a.lautstaerke_lautsprecher;
      const e = this.$(id);
      const anzeige = this.$(was === "mikrofon" ? "mwert" : "lwert");
      if (typeof roh === "number") {
        e.value = String(roh);
        anzeige.textContent = String(roh);
      } else {
        anzeige.textContent = "nicht messbar";
      }
      e.oninput = () => { anzeige.textContent = e.value; };
      const b = this.$(knopf);
      const an = was === "mikrofon" ? !!a.mikrofon_an : !!a.lautsprecher_an;
      b.textContent = an ? "an — ausschalten" : "aus — einschalten";
      b.className = an ? "an" : "aus";
    }
  }

  async setzenDisplay(feld, wert) {
    this._melden("…");
    const r = await window.chimera.api("/api/einstellungen/display",
      { method: "POST", body: JSON.stringify({ feld, wert }) });
    if (!r.ok) { this._melden("Nicht gesetzt: " + text(r), "fehler"); return; }
    if (r.display) this._displayFuellen(r.display);
    this._melden(r.meldung || "gesetzt", "gut");
  }

  async schalten(was) {
    const zustand = this.audio || {};
    const an = was === "mikrofon" ? !!zustand.mikrofon_an : !!zustand.lautsprecher_an;
    const r = await window.chimera.api("/api/einstellungen/audio",
      { method: "POST", body: JSON.stringify({ feld: was, wert: !an }) });
    if (!r.ok) { this._melden("Nicht geschaltet: " + text(r), "fehler"); return; }
    if (r.audio) this._audioFuellen(r.audio);
    this._melden(r.meldung || "geschaltet", "gut");
  }

  async pegelSetzen(was, prozent) {
    const r = await window.chimera.api("/api/einstellungen/audio",
      { method: "POST", body: JSON.stringify({ feld: "lautstaerke", was, wert: prozent }) });
    if (!r.ok) { this._melden("Nicht gesetzt: " + text(r), "fehler"); return; }
    if (r.audio) this._audioFuellen(r.audio);
    this._melden(r.meldung || "gesetzt", "gut");
  }

  async kennwortAendern() {
    const alt = this.$("alt").value;
    const neu = this.$("neu").value;
    const wiederholung = this.$("wiederholung").value;
    const grund = passwortFehler(alt, neu, wiederholung);
    if (grund) { this._melden(grund, "fehler"); return; }
    const knopf = this.$("pw_aendern");
    knopf.disabled = true;
    const r = await window.chimera.api("/api/einstellungen/passwort",
      { method: "POST", body: JSON.stringify({ alt, neu, wiederholung }) });
    knopf.disabled = false;
    if (!r.ok) { this._melden("Nicht geändert: " + text(r), "fehler"); return; }
    this.$("alt").value = this.$("neu").value = this.$("wiederholung").value = "";
    this._melden(r.meldung || "Kennwort geändert", "gut");
  }
}

/// Was das Gateway als Fehler geschickt hat, als Satz. Drei Formen, weil die
/// Routen unterschiedlich antworten — ein „[object Object]" hilft niemandem.
function text(antwort) {
  const f = antwort && antwort.fehler;
  if (typeof f === "string") return f;
  if (f && typeof f.text === "string") return f.text;
  return "unbekannter Fehler (" + (antwort && antwort.status) + ")";
}

// Die beiden Rechnungen hängen an der Klasse, damit
// `tests/js/einstellungen_seite.mjs` die ECHTE Datei prüfen kann (kein
// Nachbau der Formel) — ein klassisches Skript kennt kein `export`.
ChimeraEinstellungen.audioText = audioText;
ChimeraEinstellungen.passwortFehler = passwortFehler;

if (!customElements.get("chimera-einstellungen")) {
  customElements.define("chimera-einstellungen", ChimeraEinstellungen);
}
