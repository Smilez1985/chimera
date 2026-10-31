"use strict";
// Chat-Modul (DESIGN 5m): hängt am selben Strom wie Telegram. Zeigt Text nur
// per textContent an, nie als HTML.
class ChimeraChat extends HTMLElement {
  connectedCallback() {
    this.seit = 0;
    this.laeuft = true;
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:flex; flex-direction:column; height:100%; }
        #liste { flex:1; overflow:auto; padding:.75rem; display:flex; flex-direction:column; gap:.5rem; }
        .m { max-width:85%; padding:.5rem .75rem; border-radius:.75rem; white-space:pre-wrap; word-break:break-word; }
        .ich { align-self:flex-end; background:#2f4a8a; }
        .sie { align-self:flex-start; background:#2b2f3b; }
        .sys { align-self:center; color:#8a90a2; font-size:.85rem; }
        .tuer { display:block; font-size:.7rem; opacity:.6; }
        form { display:flex; gap:.5rem; padding:.5rem; border-top:1px solid #2b2f3b; }
        textarea { flex:1; resize:none; padding:.5rem; border-radius:.5rem; border:1px solid #2b2f3b;
                   background:#1c1f28; color:#e6e8ee; font:inherit; }
        button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.5rem; padding:.5rem 1rem; font:inherit; }
        #denkt { color:#8a90a2; padding:0 .75rem; min-height:1.2em; font-size:.85rem; }
        #alt { padding:.25rem .75rem; font-size:.85rem; }
        select { background:#1c1f28; color:#e6e8ee; border:1px solid #2b2f3b; border-radius:.4rem; }
      </style>
      <div id="alt"><label>Sitzung: <select id="wahl"></select></label></div>
      <div id="liste"></div>
      <div id="denkt"></div>
      <form><textarea id="eingabe" rows="2" placeholder="Nachricht"></textarea><button type="submit">Senden</button></form>`;
    this.liste = this.shadowRoot.getElementById("liste");
    this.denkt = this.shadowRoot.getElementById("denkt");
    this.wahl = this.shadowRoot.getElementById("wahl");
    this.shadowRoot.querySelector("form").addEventListener("submit", (e) => { e.preventDefault(); this.senden(); });
    this.shadowRoot.getElementById("eingabe").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this.senden(); }
    });
    this.wahl.addEventListener("change", () => this.sitzungWechseln());
    this.sitzungenLaden();
    this.hoeren();
  }
  disconnectedCallback() { this.laeuft = false; }

  blase(klasse, text, tuer) {
    const d = document.createElement("div");
    d.className = "m " + klasse;
    if (tuer) { const t = document.createElement("span"); t.className = "tuer"; t.textContent = tuer; d.appendChild(t); }
    d.appendChild(document.createTextNode(text));
    this.liste.appendChild(d);
    this.liste.scrollTop = this.liste.scrollHeight;
  }

  async senden() {
    const feld = this.shadowRoot.getElementById("eingabe");
    const text = feld.value.trim();
    if (!text || this.schreibgeschuetzt) return;
    feld.value = "";
    const r = await window.chimera.api("/api/chat/senden", { method: "POST", body: JSON.stringify({ text }) });
    if (!r.ok) this.blase("sys", r.fehler || "Senden fehlgeschlagen");
  }

  async hoeren() {
    let pause = 1000;
    while (this.laeuft) {
      try {
        const r = await window.chimera.api(`/api/chat/strom?seit=${this.seit}`);
        if (r.status === 401) { location.reload(); return; }
        if (r.ok) {
          pause = 1000;
          for (const e of r.ereignisse) { this.seit = Math.max(this.seit, e.nr); this.ereignis(e); }
          continue;
        }
      } catch (_) { /* Netz weg: neu versuchen */ }
      await new Promise((ok) => setTimeout(ok, pause));
      pause = Math.min(pause * 2, 15000);
    }
  }

  ereignis(e) {
    if (this.schreibgeschuetzt) return;
    if (e.art === "eingabe") this.blase("ich", e.text, e.tuer);
    else if (e.art === "antwort" || e.art === "fehler") { this.denkt.textContent = ""; this.blase("sie", e.text); }
    else if (e.art === "zustand") this.denkt.textContent = e.text;
    else if (e.art === "umgeleitet" || e.art === "wechsel" || e.art === "neu") this.blase("sys", e.text);
  }

  async sitzungenLaden() {
    const r = await window.chimera.api("/api/chat/sitzungen");
    if (!r.ok) return;
    this.haupt = r.haupt;
    this.wahl.replaceChildren();
    const o = (wert, text) => { const x = document.createElement("option"); x.value = wert; x.textContent = text; this.wahl.appendChild(x); };
    o(r.haupt, "Aktuelle (Haupt)");
    if (r.alt) o(r.alt, "Vorherige (nur lesbar)");
    for (const a of r.archiv || []) o(a, `Archiv ${a} (nur lesbar)`);
  }

  async sitzungWechseln() {
    const sid = this.wahl.value;
    if (sid === this.haupt) { this.schreibgeschuetzt = false; this.liste.replaceChildren(); this.seit = 0; return; }
    this.schreibgeschuetzt = true;
    const r = await window.chimera.api(`/api/chat/lesen?sitzung=${encodeURIComponent(sid)}`);
    this.liste.replaceChildren();
    if (!r.ok) { this.blase("sys", r.fehler || "Nicht lesbar"); return; }
    for (const e of r.eintraege) {
      if (e.art === "nachricht") this.blase(e.rolle === "user" ? "ich" : "sie", e.inhalt);
      else if (e.art === "verdichtet") this.blase("sys", "— verdichtet —");
    }
  }
}
customElements.define("chimera-chat", ChimeraChat);
