"use strict";
// Anbietermodul Ollama (DESIGN 5t): Vorlage fuer alle weiteren Anbieter.
// Zeigt die eingerichteten Ollama-Server, legt neue an, holt deren Modelle
// (Katalog) und testet ein Modell. Alles Gesendete geht durch /api/anbieter/*;
// das Gateway prueft dort Recht und Eingabe. Werte nur per textContent.
class ChimeraOllama extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:1rem; }
        h3 { margin:.2rem 0 .5rem; }
        .karte { border:1px solid #2b2f3b; border-radius:.6rem; padding:.75rem; margin:.75rem 0; background:#1c1f28; }
        .kopf { display:flex; justify-content:space-between; gap:.5rem; flex-wrap:wrap; align-items:baseline; }
        .klein { color:#8a90a2; font-size:.85rem; }
        table { width:100%; border-collapse:collapse; margin-top:.5rem; font-size:.9rem; }
        td, th { text-align:left; padding:.25rem .4rem; border-bottom:1px solid #2b2f3b; }
        button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem; padding:.35rem .8rem; font:inherit; cursor:pointer; margin:.2rem .2rem 0 0; }
        button.stumm { background:#2b2f3b; color:#e6e8ee; }
        button.gefahr { background:#ff7a7a; }
        input { background:#1c1f28; color:#e6e8ee; border:1px solid #2b2f3b; border-radius:.4rem; padding:.4rem; font:inherit; width:100%; box-sizing:border-box; margin:.2rem 0 .5rem; }
        .ja { color:#7be0a0; } .nein { color:#ff7a7a; } .unbekannt { color:#8a90a2; }
        .fehler { color:#ff7a7a; } .meldung { color:#ffd989; }
        #antwort { white-space:pre-wrap; margin-top:.4rem; }
      </style>
      <h3>Ollama</h3>
      <p class="klein" id="hinweis"></p>
      <div id="liste"></div>
      <div class="karte">
        <strong>Ollama-Server hinzufuegen</strong>
        <label class="klein">Kennung (a-z, 0-9, -)<input id="n-id" placeholder="ollama-lan"></label>
        <label class="klein">Bezeichnung<input id="n-bez" placeholder="Ollama im LAN"></label>
        <label class="klein">Adresse<input id="n-adr" placeholder="http://adresse-des-servers:11434"></label>
        <button id="n-ok">Anlegen</button> <span id="n-fehler" class="fehler"></span>
      </div>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
    this.$("n-ok").onclick = () => this.anlegen();
    this.laden();
  }

  el(tag, text, klasse) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (klasse) e.className = klasse;
    return e;
  }

  post(pfad, body) {
    return window.chimera.api(pfad, { method: "POST", body: JSON.stringify(body) });
  }

  async laden() {
    const r = await window.chimera.api("/api/anbieter/liste");
    const liste = this.$("liste");
    liste.replaceChildren();
    if (!r.ok) {
      liste.appendChild(this.el("p", "Fehler: " + (r.fehler && r.fehler.text || r.fehler || "nicht erreichbar"), "fehler"));
      return;
    }
    const meine = (r.anbieter || []).filter((a) => a.typ === "ollama");
    this.$("hinweis").textContent = meine.length ? "" : "Noch kein Ollama-Server eingerichtet.";
    for (const m of r.meldungen || []) {
      liste.appendChild(this.el("p", m.quelle + ": " + m.text, "meldung"));
    }
    for (const a of meine) liste.appendChild(await this.karte(a));
  }

  async karte(a) {
    const k = this.el("div", undefined, "karte");
    const kopf = this.el("div", undefined, "kopf");
    kopf.append(this.el("strong", a.bezeichnung), this.el("span", a.id + (a.an === false ? " (aus)" : ""), "klein"));
    k.append(kopf, this.el("div", a.adresse || "keine Adresse", "klein"));

    const kat = await window.chimera.api("/api/anbieter/katalog?id=" + encodeURIComponent(a.id));
    const modelle = (kat.katalog && kat.katalog.modelle) || {};
    const namen = Object.keys(modelle).sort();
    if (kat.katalog && kat.katalog.stand) {
      k.appendChild(this.el("div", namen.length + " Modelle, Stand " + new Date(kat.katalog.stand * 1000).toLocaleString(), "klein"));
    } else {
      k.appendChild(this.el("div", "Noch kein Katalog. „Modelle holen“ fragt den Server.", "klein"));
    }
    if (namen.length) {
      const t = this.el("table");
      const kopfz = this.el("tr");
      for (const h of ["Modell", "Groesse", "Kontext", "Tools", ""]) kopfz.appendChild(this.el("th", h));
      t.appendChild(kopfz);
      for (const n of namen) {
        const e = modelle[n];
        const z = this.el("tr");
        z.appendChild(this.el("td", n + (e.fehlt_seit ? " (fehlt seit " + new Date(e.fehlt_seit * 1000).toLocaleDateString() + ")" : "")));
        z.appendChild(this.el("td", e.groesse || "-"));
        z.appendChild(this.el("td", e.kontext ? String(e.kontext) : "-"));
        const tools = e.tools === true ? ["ja", "ja"] : e.tools === false ? ["nein", "nein"] : ["?", "unbekannt"];
        z.appendChild(this.el("td", tools[0], tools[1]));
        const td = this.el("td");
        const b = this.el("button", "Testen", "stumm");
        b.onclick = () => this.testen(a.id, n, ausgabe);
        td.appendChild(b);
        z.appendChild(td);
        t.appendChild(z);
      }
      k.appendChild(t);
    }
    const ausgabe = this.el("div", undefined, "klein");
    ausgabe.id = "antwort";

    const holen = this.el("button", "Modelle holen");
    holen.onclick = async () => {
      holen.disabled = true; holen.textContent = "frage ...";
      const r = await this.post("/api/anbieter/aktualisieren", { id: a.id });
      if (r.ok) this.laden();
      else { holen.disabled = false; holen.textContent = "Modelle holen"; ausgabe.className = "fehler"; ausgabe.textContent = (r.fehler && r.fehler.text) || r.fehler || "Fehler"; }
    };
    const aus = this.el("button", a.an === false ? "Einschalten" : "Ausschalten", "stumm");
    aus.onclick = async () => {
      const neu = { ...a }; delete neu.id; delete neu.schluessel;
      neu.an = a.an === false;
      await this.post("/api/anbieter/setzen", { id: a.id, anbieter: neu });
      this.laden();
    };
    const weg = this.el("button", "Entfernen", "gefahr");
    weg.onclick = async () => {
      if (!window.confirm(a.bezeichnung + " entfernen? Katalog und Wahl bleiben liegen.")) return;
      await this.post("/api/anbieter/entfernen", { id: a.id });
      this.laden();
    };
    k.append(holen, aus, weg, ausgabe);
    return k;
  }

  async testen(id, modell, ausgabe) {
    ausgabe.className = "klein";
    ausgabe.textContent = "Frage " + modell + " (ein kaltes Modell braucht bis zu zwei Minuten) ...";
    const r = await this.post("/api/anbieter/probe", { id, modell });
    if (r.ok) { ausgabe.className = "ja"; ausgabe.textContent = modell + ": " + r.text; }
    else { ausgabe.className = "fehler"; ausgabe.textContent = (r.fehler && r.fehler.text) || r.fehler || "Fehler"; }
  }

  async anlegen() {
    const id = this.$("n-id").value.trim();
    const bez = this.$("n-bez").value.trim();
    const adr = this.$("n-adr").value.trim();
    const f = this.$("n-fehler");
    f.textContent = "";
    const r = await this.post("/api/anbieter/setzen", { id, anbieter: { typ: "ollama", bezeichnung: bez, adresse: adr, an: true } });
    if (!r.ok) { f.textContent = (r.fehler && r.fehler.text) || r.fehler || "Fehler"; return; }
    this.$("n-id").value = this.$("n-bez").value = this.$("n-adr").value = "";
    this.laden();
  }
}
customElements.define("chimera-ollama", ChimeraOllama);
