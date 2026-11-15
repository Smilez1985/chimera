"use strict";
// Anzeige-Modul (DESIGN, Regel „Anzeigespiegel"): zeigt das fertige Bild des
// Renderers. Das Gateway liest die Datei nur und reicht sie durch; hier wird
// sie gedeutet — RGB565 big-endian, wie der Panelspeicher.
//
// Zwei Elemente in einer Datei:
//   <chimera-anzeige>        das Bild selbst (auch im Chat, dann verschiebbar)
//   <chimera-anzeige-seite>  die Modulseite: Bild, Maße und Stand
//
// Der Abruf läuft NUR, solange das Element im Dokument hängt. Der Rahmen
// ersetzt beim Reiterwechsel den Inhalt (`zeigeModul`), damit hält
// `disconnectedCallback` den Zähler an — kein versteckter Reiter fragt weiter.

/// Kopflänge: 4 Kennung + 1 Fassung + 1 Format + 2 Breite + 2 Höhe
/// + 2 Reserve + 8 Zähler, danach 12 Byte Reserve (gesamt 32).
const KOPF = 32;
const KOPF_FELDER = 20;
const MAGIC = [0x43, 0x48, 0x53, 0x50]; // "CHSP"
const FORMAT_RGB565_BE = 1;

/// RGB565 (big-endian) → RGBA in ein Canvas. Reine Rechnung, ohne DOM —
/// damit ein Test sie ohne Browser prüfen kann (tests/js/anzeige_bild.mjs).
function bildMalen(bytes, breite, hoehe, ctx) {
  const anzahl = breite * hoehe;
  const ziel = new Uint8ClampedArray(anzahl * 4);
  const sicht = new DataView(bytes.buffer ? bytes.buffer : bytes,
                             bytes.byteOffset || 0, bytes.byteLength);
  for (let i = 0; i < anzahl; i++) {
    const p = sicht.getUint16(i * 2, false);
    const o = i * 4;
    // 5/6/5 auf 0..255, mit Rundung: 31 → 255, nicht 248.
    ziel[o] = (p >> 11 & 0x1f) * 255 / 31 + 0.5;
    ziel[o + 1] = (p >> 5 & 0x3f) * 255 / 63 + 0.5;
    ziel[o + 2] = (p & 0x1f) * 255 / 31 + 0.5;
    ziel[o + 3] = 255;
  }
  ctx.putImageData(new ImageData(ziel, breite, hoehe), 0, 0);
}

/// Kopf der Antwort deuten. `null` heißt: kein gültiges Bild.
function kopfDeuten(bytes) {
  if (!bytes || bytes.byteLength < KOPF_FELDER) return null;
  const s = new DataView(bytes.buffer ? bytes.buffer : bytes,
                         bytes.byteOffset || 0, bytes.byteLength);
  for (let i = 0; i < 4; i++) if (s.getUint8(i) !== MAGIC[i]) return null;
  if (s.getUint8(4) !== 1) return null;           // Fassung
  const format = s.getUint8(5);
  const breite = s.getUint16(6, false);
  const hoehe = s.getUint16(8, false);
  const zaehler = Number(s.getBigUint64(12, false));
  if (!breite || !hoehe) return null;
  return { format, breite, hoehe, zaehler };
}

const STIL = `
  :host { display:block; }
  /* Schwebend heisst: fest im Chatfeld verankert, nicht im Verlauf. Die
     Lage setzt der Chat (top/left), das Ziehen hier (DESIGN, Regel
     „Anzeigespiegel"). */
  :host([schwebend]) {
    position:absolute; top:var(--oben, 8px); left:var(--links, auto); right:var(--rechts, 8px);
    width:var(--breite, 110px); cursor:grab; touch-action:none;
    user-select:none; z-index:3; margin:0;
  }
  #rahmen {
    position:relative; background:#0b0d12; border:1px solid #2b2f3b;
    border-radius:.6rem; overflow:hidden; line-height:0;
  }
  canvas { width:100%; height:auto; display:block; image-rendering:auto; }
  #grund {
    position:absolute; inset:0; padding:.5rem; margin:0;
    font:0.75rem/1.3 system-ui, sans-serif; color:#8a90a2;
    white-space:pre-wrap; display:flex; align-items:center;
  }
  #grund[hidden] { display:none; }
`;

class ChimeraAnzeige extends HTMLElement {
  constructor() {
    super();
    this.zaehler = 0;
    this.laeuft = false;
    this._fehler = "";
    this._grund = "";
  }

  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `<style>${STIL}</style>
        <div id="rahmen"><canvas width="240" height="280"></canvas><p id="grund" hidden></p></div>`;
      this.canvas = this.shadowRoot.querySelector("canvas");
      this.ctx = this.canvas.getContext("2d", { willReadFrequently: false });
      this.grund = this.shadowRoot.getElementById("grund");
      this._sichtbar = () => { if (!document.hidden) this._weiter(); };
      document.addEventListener("visibilitychange", this._sichtbar);
      if (this.hasAttribute("schwebend")) this._ziehenEinrichten();
    }
    this.laeuft = true;
    this._weiter();
  }

  disconnectedCallback() {
    // Ohne diesen Griff liefe der Abruf in einem Reiter weiter, den niemand
    // ansieht (Reiterwechsel tauscht den Inhalt des Rahmens aus).
    this.laeuft = false;
    clearTimeout(this._takt);
    document.removeEventListener("visibilitychange", this._sichtbar);
  }

  _weiter(ms = 200) {
    clearTimeout(this._takt);
    if (!this.laeuft) return;
    this._takt = setTimeout(() => this._runde(), ms);
  }

  async _runde() {
    if (!this.laeuft || document.hidden) return;
    let pause = 200;
    try {
      const r = await fetch(`/api/anzeige/bild?seit=${this.zaehler}`,
        { headers: { "X-Chimera": "1" }, credentials: "same-origin", cache: "no-store" });
      if (r.status === 401) { this._sagen("nicht angemeldet"); this.laeuft = false; return; }
      if (r.status === 204) { this._sagen(""); return; }        // unverändert
      if (!r.ok) {
        let text = `Anzeige nicht lesbar (${r.status})`;
        try { const j = await r.json(); if (j && j.fehler) text = j.fehler; } catch (_) {}
        this._sagen(text);
        pause = 1000;
        return;
      }
      const puffer = await r.arrayBuffer();
      const kopf = kopfDeuten(puffer);
      if (!kopf) { this._sagen("Bildkopf unverständlich"); pause = 1000; return; }
      // Nur bei geänderter Größe neu anlegen — sonst flackert das Canvas.
      if (this.canvas.width !== kopf.breite || this.canvas.height !== kopf.hoehe) {
        this.canvas.width = kopf.breite;
        this.canvas.height = kopf.hoehe;
      }
      bildMalen(new Uint8Array(puffer, KOPF), kopf.breite, kopf.hoehe, this.ctx);
      this.zaehler = kopf.zaehler;     // nie rückwärts: nur der Kopf zählt
      this._sagen("");
    } catch (_) {
      // Netz weg oder Gateway aus: erneut versuchen, nicht stillstehen.
      this._sagen("Anzeige nicht erreichbar");
      pause = 1000;
    } finally {
      if (this.laeuft) this._weiter(pause);
    }
  }

  _sagen(text) {
    this._fehler = text;
    if (!this.grund) return;
    this.grund.textContent = text;
    this.grund.hidden = !text;
    if (this._melde) this._melde(text);
  }

  /// Ziehen: beide Achsen, innerhalb der Bühne begrenzt, Lage wird gemerkt.
  ///
  /// Gemerkt wird in Pixeln ab der linken oberen Ecke der Bühne. Beim
  /// Wiederherstellen wird gegen die aktuelle Größe begrenzt — ein schmaleres
  /// Fenster darf das Gesicht nicht aus dem Chatfeld schieben.
  _ziehenEinrichten() {
    let start = null;
    this.addEventListener("pointerdown", (e) => {
      const r = this.getBoundingClientRect();
      const b = this.parentElement ? this.parentElement.getBoundingClientRect() : null;
      start = { x: e.clientX, y: e.clientY,
                links: r.left - (b ? b.left : 0), oben: r.top - (b ? b.top : 0) };
      this.setPointerCapture(e.pointerId);
      this.style.cursor = "grabbing";
    });
    this.addEventListener("pointermove", (e) => {
      if (!start) return;
      const b = this.parentElement;
      if (!b) return;
      const grenze = b.getBoundingClientRect();
      const max_x = Math.max(0, grenze.width - this.offsetWidth);
      const max_y = Math.max(0, grenze.height - this.offsetHeight);
      const x = Math.min(max_x, Math.max(0, start.links + (e.clientX - start.x)));
      const y = Math.min(max_y, Math.max(0, start.oben + (e.clientY - start.y)));
      this._setzen(x, y);
    });
    const ende = () => {
      if (!start) return;
      start = null;
      this.style.cursor = "";
      this._merken();
      // Der Chat rechnet seinen Umfluss neu — sonst blieben die Blasen an der
      // alten Stelle schmal, bis der nächste Scroll kommt.
      this.dispatchEvent(new CustomEvent("anzeige-bewegt", { bubbles: true, composed: true }));
    };
    this.addEventListener("pointerup", ende);
    this.addEventListener("pointercancel", ende);
    this._wiederherstellen();
  }

  _setzen(x, y) {
    this.style.setProperty("--links", `${Math.round(x)}px`);
    this.style.setProperty("--rechts", "auto");
    this.style.setProperty("--oben", `${Math.round(y)}px`);
  }

  _merken() {
    try {
      const r = this.getBoundingClientRect();
      const b = this.parentElement ? this.parentElement.getBoundingClientRect() : null;
      localStorage.setItem("chimera.anzeige.pos", JSON.stringify({
        x: Math.round(r.left - (b ? b.left : 0)),
        y: Math.round(r.top - (b ? b.top : 0)),
      }));
    } catch (_) { /* ohne Merker ist es auch in Ordnung */ }
  }

  _wiederherstellen() {
    let pos = null;
    try { pos = JSON.parse(localStorage.getItem("chimera.anzeige.pos") || "null"); } catch (_) {}
    const b = this.parentElement;
    if (!b) return;
    const breite = b.clientWidth || 0;
    const hoehe = b.clientHeight || 0;
    if (!pos || typeof pos.x !== "number") {
      // Vorgabe: oben rechts.
      this.style.setProperty("--rechts", "8px");
      this.style.setProperty("--oben", "8px");
      return;
    }
    const x = Math.min(Math.max(0, breite - this.offsetWidth), Math.max(0, pos.x));
    const y = Math.min(Math.max(0, hoehe - this.offsetHeight), Math.max(0, pos.y));
    this._setzen(x, y);
  }
}

/// Wie die Seite eine Vorschau ankündigt (reine Funktion, ohne DOM —
/// `tests/js/avatar_seite.mjs` prüft sie ohne Browser).
///
/// Die Auskunft muss stimmen, sonst ist sie schlimmer als keine: Ein
/// Dauerzustand bleibt 30 s stehen, ein Ausdruck mit eigener Dauer läuft
/// einmal ganz (und nicht 30 s lang, davon 17 s bewegungslos).
function vorschauText(eintrag) {
  if (!eintrag || !eintrag.name) return "";
  if (eintrag.dauerzustand) {
    const s = Math.round(eintrag.vorschau_s || 0);
    return `${eintrag.name}: ${s} s Vorschau, dann zurück`;
  }
  const d = Math.round(eintrag.dauer_s || 0);
  return d > 0 ? `${eintrag.name}: läuft einmal ganz (${d} s)`
               : `${eintrag.name}: läuft einmal ganz`;
}

/// Beschriftung der Frisuren. Die Kennungen sind die Namen der
/// `draw_hair_<name>`-Methoden im Renderer — eine Liste, eine Stelle
/// (`render/einstellungen.py`), hier nur die Anzeige.
const FRISUREN_TEXT = {
  mochi: "Mochi", peruecke: "Perücke", kurz: "Kurz", strubbel: "Strubbel",
  scheitel: "Scheitel", locken: "Locken", pony: "Pony", punk: "Punk",
  zopf: "Zopf",
};

const STIL_SEITE = `
  :host { display:block; padding:1rem; }
  h3 { margin:.2rem 0 .5rem; font:1rem/1.3 system-ui, sans-serif; }
  .spalte { display:flex; gap:1rem; align-items:flex-start; flex-wrap:wrap; }
  /* Das Gesicht links, die Einstellungen daneben — auf schmalen Fenstern
     rutschen sie untereinander (kein eigener Reiter, keine zweite Seite). */
  .bild { flex:0 0 auto; width:min(240px, 46vw); }
  .einst { flex:1 1 260px; min-width:220px; }
  .karte { border:1px solid #2b2f3b; border-radius:.6rem; padding:.75rem;
           margin:0 0 .75rem; background:#1c1f28; }
  .karte strong { display:block; margin:0 0 .4rem; }
  label { display:block; font-size:.85rem; color:#8a90a2; margin:.5rem 0 .2rem; }
  select, input[type=color] { width:100%; font:inherit; padding:.35rem;
           border-radius:.4rem; border:1px solid #2b2f3b; background:#12141a; color:#e6e8ee; }
  input[type=color] { height:2.6rem; padding:.15rem; cursor:pointer; }
  input[type=range] { width:100%; }
  button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem;
           padding:.4rem .9rem; font:inherit; cursor:pointer; }
  button:disabled { opacity:.6; cursor:default; }
  .klein { color:#8a90a2; font-size:.85rem; margin:.35rem 0 0; }
  .fehler { color:#ff7a7a; } .gut { color:#7be0a0; } .meldung { color:#ffd989; }
`;

class ChimeraAnzeigeSeite extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${STIL}${STIL_SEITE}</style>
      <h3>Avatar</h3>
      <div class="spalte">
        <div class="bild">
          <chimera-anzeige></chimera-anzeige>
          <p class="klein" id="kopf">Bild wird geladen …</p>
        </div>
        <div class="einst">
          <div class="karte">
            <strong>Haare</strong>
            <label for="frisur">Frisur</label>
            <select id="frisur"></select>
            <label for="farbe">Haarfarbe</label>
            <input type="color" id="farbe" value="#8B5A2B">
            <p class="klein">Schatten und Glanz leitet der Renderer aus der
            Grundfarbe ab — eine Farbe genügt.</p>
            <label for="kontrast">Kontrast für helle Räume: <span id="kwert">0</span> %</label>
            <input type="range" id="kontrast" min="0" max="100" step="5" value="0">
          </div>
          <div class="karte">
            <strong>Vorschau</strong>
            <label for="ausdruck">Ausdruck</label>
            <select id="ausdruck"></select>
            <p class="klein" id="was">—</p>
            <button id="zeigen">Vorschau zeigen</button>
          </div>
          <p id="meldung" class="klein"></p>
        </div>
      </div>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
    const b = this.shadowRoot.querySelector("chimera-anzeige");
    b._melde = (text) => {
      this.$("kopf").textContent = text ? `Anzeige: ${text}`
        : `Anzeige: läuft, Bild ${b.zaehler}, ${b.canvas.width}×${b.canvas.height}`;
    };
    this.laden();
  }

  _melden(text, art = "") {
    const m = this.$("meldung");
    if (!m) return;
    m.textContent = text;
    m.className = "klein " + art;
  }

  async laden() {
    const r = await window.chimera.api("/api/anzeige/einstellung");
    if (!r.ok) {
      this._melden("Einstellungen nicht lesbar: " + text(r), "fehler");
    } else if (r.avatar) {
      this.werte = r.avatar;
      this._fuellen(r.avatar);
    }
    const a = await window.chimera.api("/api/anzeige/ausdruecke");
    if (!a.ok) {
      this._melden("Ausdrücke nicht lesbar: " + text(a), "fehler");
      return;
    }
    this.ausdruecke = a.ausdruecke || [];
    this._ausdrueckeFuellen();
  }

  _fuellen(w) {
    const frisur = this.$("frisur");
    frisur.replaceChildren();
    for (const name of w.frisuren || []) {
      const o = document.createElement("option");
      o.value = name;
      o.textContent = FRISUREN_TEXT[name] || name;
      if (name === w.frisur) o.selected = true;
      frisur.appendChild(o);
    }
    frisur.onchange = () => this.setzen("frisur", frisur.value);
    const farbe = this.$("farbe");
    farbe.value = w.farbe || "#8B5A2B";
    farbe.onchange = () => this.setzen("farbe", farbe.value);
    const kontrast = this.$("kontrast");
    kontrast.max = String(w.kontrast_max || 100);
    kontrast.value = String(w.kontrast || 0);
    this.$("kwert").textContent = String(w.kontrast || 0);
    kontrast.oninput = () => { this.$("kwert").textContent = kontrast.value; };
    // Erst beim Loslassen senden: jede Zwischenstufe zu schreiben hieße,
    // bei jedem Pixel eine Datei zu ersetzen.
    kontrast.onchange = () => this.setzen("kontrast", Number(kontrast.value));
    for (const h of w.hinweise || []) this._melden(h, "meldung");
  }

  _ausdrueckeFuellen() {
    const sel = this.$("ausdruck");
    sel.replaceChildren();
    for (const e of this.ausdruecke) {
      const o = document.createElement("option");
      o.value = e.name;
      o.textContent = e.name;
      sel.appendChild(o);
    }
    const zeigen = () => {
      const e = this.ausdruecke.find((x) => x.name === sel.value);
      this.$("was").textContent = vorschauText(e) || "—";
    };
    sel.onchange = zeigen;
    zeigen();
    this.$("zeigen").onclick = async () => {
      const knopf = this.$("zeigen");
      if (!sel.value) return;
      knopf.disabled = true;
      const r = await window.chimera.api("/api/anzeige/vorschau",
        { method: "POST", body: JSON.stringify({ name: sel.value }) });
      knopf.disabled = false;
      if (!r.ok) { this._melden("Vorschau nicht möglich: " + text(r), "fehler"); return; }
      this._melden(`${r.gesetzt}: ${r.grund}`, "gut");
    };
  }

  async setzen(feld, wert) {
    this._melden("…", "");
    const r = await window.chimera.api("/api/anzeige/einstellung",
      { method: "POST", body: JSON.stringify({ feld, wert }) });
    if (!r.ok) { this._melden("Nicht gesetzt: " + text(r), "fehler"); return; }
    if (r.avatar) { this.werte = r.avatar; this._fuellen(r.avatar); }
    this._melden(r.meldung || "gesetzt", "gut");
  }
}

/// Was das Gateway als Fehler geschickt hat, als Satz. Drei Formen, weil
/// die Routen unterschiedlich antworten — ein „[object Object]" hilft
/// niemandem.
function text(antwort) {
  const f = antwort && antwort.fehler;
  if (typeof f === "string") return f;
  if (f && typeof f.text === "string") return f.text;
  return "unbekannter Fehler (" + (antwort && antwort.status) + ")";
}

ChimeraAnzeigeSeite.vorschauText = vorschauText;

// Die beiden Rechnungen haengen an der Klasse, damit `tests/js/anzeige_bild.mjs`
// die ECHTE Datei pruefen kann (kein Nachbau der Formel) — ein klassisches
// Skript kennt kein `export`.
ChimeraAnzeige.bildMalen = bildMalen;
ChimeraAnzeige.kopfDeuten = kopfDeuten;

if (!customElements.get("chimera-anzeige")) customElements.define("chimera-anzeige", ChimeraAnzeige);
if (!customElements.get("chimera-anzeige-seite")) customElements.define("chimera-anzeige-seite", ChimeraAnzeigeSeite);
