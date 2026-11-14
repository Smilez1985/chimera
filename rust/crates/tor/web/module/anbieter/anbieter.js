"use strict";
// Modul „Anbieter": eintragen, ändern, Schlüssel hinterlegen.
//
// Das ist der Ort für Copy&Paste: Der Schlüssel wird **einmal** hier
// eingefügt, geht über /api/anbieter/schluessel an das Gateway und wird dort
// in config/geheim/<id> (0600) abgelegt. Er kommt **nie** zurück -- die
// Liste sagt nur, OB einer da ist. Ein Feld, das den Wert anzeigt, gibt es
// deshalb nicht.
class ChimeraAnbieter extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:1rem; }
        h3 { margin:.2rem 0 .5rem; }
        h4 { margin:0 0 .4rem; font-size:.95rem; }
        .karte { border:1px solid #2b2f3b; border-radius:.6rem; padding:.75rem; margin:.75rem 0; background:#1c1f28; }
        .kopf { display:flex; justify-content:space-between; gap:.5rem; flex-wrap:wrap; align-items:baseline; }
        .klein { color:#8a90a2; font-size:.85rem; }
        .ja { color:#7be0a0; } .nein { color:#ff7a7a; } .meldung { color:#ffd989; }
        .fehler { color:#ff7a7a; }
        table { width:100%; border-collapse:collapse; margin-top:.4rem; font-size:.9rem; }
        td, th { text-align:left; padding:.25rem .4rem; border-bottom:1px solid #2b2f3b; vertical-align:middle; }
        input, select { background:#1c1f28; color:#e6e8ee; border:1px solid #2b2f3b; border-radius:.4rem; padding:.35rem; font:inherit; box-sizing:border-box; width:100%; margin:.2rem 0 .4rem; }
        label.klein { display:block; margin-top:.4rem; }
        button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem; padding:.35rem .8rem; font:inherit; cursor:pointer; margin:.2rem .2rem 0 0; }
        button.stumm { background:#2b2f3b; color:#e6e8ee; }
        button.gefahr { background:#ff7a7a; }
        code { font-family:ui-monospace, monospace; font-size:.8rem; word-break:break-all; }
        .feld { display:grid; grid-template-columns:1fr 1fr; gap:.5rem; }
        /* Die Kennung ist ein interner Name, kein Feld fuer den Nutzer: sie wird
           aus der Bezeichnung gebildet und nur gedaempft angezeigt. Wer sie
           anfasst, bekommt sie normal -- dann gilt der eigene Wert. */
        input.auto { color:#8a90a2; background:#15171e; }
      </style>
      <h3>Anbieter</h3>
      <p class="klein">Jeder Eintrag hier ist ein Sprachmodell-Anbieter. Der Schlüssel wird beim
      Anlegen oder später hinterlegt — er geht nur an das Gateway, wird dort mit Modus 0600
      abgelegt und kommt in keiner Antwort zurück. Ein Schlüssel bleibt im Feld „Schlüssel"
      leer, wenn schon einer hinterlegt ist.</p>
      <div id="liste"></div>
      <p id="fehler" class="fehler"></p>

      <div class="karte">
        <h4>Anbieter anlegen oder ändern</h4>
        <div class="feld">
          <label class="klein">Bezeichnung<input id="n-bez" placeholder="DeepSeek"></label>
          <label class="klein">Typ
            <select id="n-typ">
              <option value="deepseek">deepseek (Cloud, OpenAI-kompatibel)</option>
              <option value="ollama">ollama (eigenes Netz)</option>
              <option value="anthropic">anthropic</option>
            </select>
          </label>
        </div>
        <label class="klein">Kennung (intern, aus der Bezeichnung gebildet)
          <input id="n-id" class="auto" placeholder="deepseek"></label>
        <label class="klein">Adresse (leer = Vorgabe des Typs)
          <input id="n-adr" placeholder="https://api.deepseek.com"></label>
        <button id="n-ok">Speichern</button> <span id="n-fehler" class="fehler"></span>
      </div>

      <div class="karte">
        <h4>Schlüssel hinterlegen</h4>
        <p class="klein">Hier einfügen (Strg+V / lange drücken → Einfügen). Der Wert wird
        nicht zurückgegeben und steht danach nirgends in der Oberfläche.</p>
        <label class="klein">Anbieter
          <select id="k-id"></select></label>
        <label class="klein">Schlüssel
          <input id="k-wert" type="password" autocomplete="off" spellcheck="false"
                 placeholder="sk-…"></label>
        <button id="k-ok">Schlüssel setzen</button> <span id="k-fehler" class="fehler"></span>
        <p id="k-erfolg" class="ja"></p>
      </div>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
    this.$("n-ok").onclick = () => this.speichern();
    this.$("k-ok").onclick = () => this.schluessel();
    // Die Kennung ist ein interner Name (`config/geheim/<kennung>`, `config/
    // anbieter/<kennung>.json`). Der Nutzer soll sie nicht erfinden muessen:
    // sie folgt der Bezeichnung, solange er sie nicht selbst angefasst hat.
    this.idVonHand = false;
    this.$("n-bez").oninput = () => {
      if (this.idVonHand) return;
      this.$("n-id").value = ChimeraAnbieter.kennungAus(this.$("n-bez").value)
        || this.$("n-typ").value;
    };
    this.$("n-typ").onchange = () => {
      if (this.idVonHand) return;
      if (!this.$("n-bez").value.trim()) this.$("n-id").value = this.$("n-typ").value;
    };
    this.$("n-id").oninput = () => {
      this.idVonHand = true;
      this.$("n-id").classList.remove("auto");
    };
    this.laden();
  }

  /// Die Kennung aus einer Bezeichnung bilden: „DeepSeek" → `deepseek`,
  /// „Mein Anbieter" → `mein-anbieter`. Erlaubt ist, was `daten::id_gueltig`
  /// durchlaesst (a-z, 0-9, `-`, hoechstens 32 Zeichen, kein `-` vorn).
  /// Umlaute werden ausgeschrieben, damit „Änderung" nicht zu „nderung" wird.
  static kennungAus(text) {
    let s = String(text == null ? "" : text).toLowerCase()
      .replace(/ä/g, "ae").replace(/ö/g, "oe")
      .replace(/ü/g, "ue").replace(/ß/g, "ss")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+/, "");
    if (s.length > 32) s = s.slice(0, 32);
    // Ein Trenner am Ende ist bei `daten::id_gueltig` erlaubt, aber haesslich
    // und macht zwei Kennungen aus einem Namen ("Test" / "Test ").
    return s.replace(/-+$/, "");
  }

  el(tag, text, klasse) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (klasse) e.className = klasse;
    return e;
  }

  post(pfad, body) {
    return window.chimera.api(pfad, { method: "POST", body: JSON.stringify(body || {}) });
  }

  grund(r) {
    return (r.fehler && r.fehler.text) || r.fehler || "unbekannter Grund";
  }

  async laden() {
    const r = await window.chimera.api("/api/anbieter/liste");
    const liste = this.$("liste");
    liste.replaceChildren();
    if (!r.ok) {
      this.$("fehler").textContent = "Nicht abrufbar: " + this.grund(r);
      return;
    }
    const alle = r.anbieter || [];
    if (!alle.length) {
      liste.appendChild(this.el("p", "Noch kein Anbieter eingetragen.", "klein"));
    } else {
      const t = document.createElement("table");
      const kopf = document.createElement("tr");
      for (const h of ["Kennung", "Typ", "Bezeichnung", "Adresse", "Schlüssel", ""]) {
        kopf.appendChild(this.el("th", h));
      }
      t.appendChild(kopf);
      for (const a of alle) {
        const tr = document.createElement("tr");
        tr.appendChild(this.el("td", a.id));
        tr.appendChild(this.el("td", a.typ || "?"));
        tr.appendChild(this.el("td", a.bezeichnung || ""));
        tr.appendChild(this.el("td", a.adresse || "—", "klein"));
        tr.appendChild(this.el("td", a.schluessel ? "hinterlegt" : "keiner",
          a.schluessel ? "ja" : "nein"));
        const td = document.createElement("td");
        const dran = this.el("button", "bearbeiten", "stumm");
        dran.onclick = () => this.fuelle(a);
        const weg = this.el("button", "entfernen", "gefahr");
        weg.onclick = () => this.entfernen(a.id);
        td.appendChild(dran);
        td.appendChild(weg);
        tr.appendChild(td);
        t.appendChild(tr);
      }
      liste.appendChild(t);
    }
    for (const m of r.meldungen || []) {
      liste.appendChild(this.el("p", `${m.quelle}: ${m.text}`, "meldung"));
    }
    // Auswahl im Schluessel-Bereich: nur vorhandene Anbieter, damit ein
    // Schluessel nicht an eine erfundene Kennung geht.
    const sel = this.$("k-id");
    const vorher = sel.value;
    sel.replaceChildren();
    const leer = document.createElement("option");
    leer.value = "";
    leer.textContent = alle.length ? "— bitte wählen —" : "— zuerst oben anlegen —";
    sel.appendChild(leer);
    for (const a of alle) {
      const o = document.createElement("option");
      o.value = a.id;
      o.textContent = a.id;
      sel.appendChild(o);
    }
    sel.value = alle.some((a) => a.id === vorher) ? vorher : (alle[0] ? alle[0].id : "");
  }

  fuelle(a) {
    this.$("n-id").value = a.id || "";
    this.$("n-typ").value = a.typ || "deepseek";
    this.$("n-bez").value = a.bezeichnung || "";
    this.$("n-adr").value = a.adresse || "";
    this.$("k-id").value = a.id || "";
    this.idVonHand = true;
    this.$("n-id").classList.remove("auto");
    this.$("n-fehler").textContent = "";
    this.$("k-fehler").textContent = "";
  }

  async speichern() {
    const id = this.$("n-id").value.trim();
    const eintrag = {
      typ: this.$("n-typ").value,
      bezeichnung: this.$("n-bez").value.trim() || id,
      an: true,
    };
    const adr = this.$("n-adr").value.trim();
    if (adr) eintrag.adresse = adr;
    if (!id) {
      this.$("n-fehler").textContent = "Die Kennung fehlt.";
      return;
    }
    const r = await this.post("/api/anbieter/setzen", { id, anbieter: eintrag });
    if (!r.ok) {
      this.$("n-fehler").textContent = "Nicht gespeichert: " + this.grund(r);
      return;
    }
    this.$("n-fehler").textContent = "";
    await this.laden();
    this.$("k-id").value = id;
  }

  async schluessel() {
    const id = this.$("k-id").value.trim();
    const wert = this.$("k-wert").value.trim();
    this.$("k-erfolg").textContent = "";
    if (!id) {
      this.$("k-fehler").textContent = "Bitte oben einen Anbieter anlegen.";
      return;
    }
    if (!wert) {
      this.$("k-fehler").textContent = "Der Schlüssel ist leer.";
      return;
    }
    const r = await this.post("/api/anbieter/schluessel", { id, wert });
    if (!r.ok) {
      this.$("k-fehler").textContent = "Nicht abgelegt: " + this.grund(r);
      return;
    }
    this.$("k-fehler").textContent = "";
    // Das Feld wird geleert: der Wert soll nicht im Browser stehen bleiben.
    this.$("k-wert").value = "";
    this.$("k-erfolg").textContent = `Schlüssel für "${id}" abgelegt (wird nie angezeigt).`;
    await this.laden();
  }

  async entfernen(id) {
    if (!window.confirm(`Anbieter "${id}" wirklich entfernen? Der Schlüssel bleibt liegen.`)) return;
    const r = await this.post("/api/anbieter/entfernen", { id });
    if (!r.ok) {
      this.$("fehler").textContent = "Nicht entfernt: " + this.grund(r);
      return;
    }
    await this.laden();
  }
}
customElements.define("chimera-anbieter", ChimeraAnbieter);
