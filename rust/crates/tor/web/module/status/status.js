"use strict";
// Status-Modul (DESIGN 5m): zeigt Zeilen, die das Gateway liefert -- Gruppe, Titel,
// Text, Balken, Stufe. Neue Messungen kommen allein aus dem Gateway (status.rs,
// `sonden()`); dieses Element kennt keine einzelne Messung. Werte nur per textContent.
class ChimeraStatus extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:1rem; }
        h3 { margin:1rem 0 .25rem; font-size:.8rem; color:#8a90a2; text-transform:uppercase; letter-spacing:.05em; }
        .z { padding:.45rem 0; border-bottom:1px solid #2b2f3b; }
        .k { display:flex; justify-content:space-between; gap:.75rem; }
        .t { color:#8a90a2; } .w { text-align:right; }
        .bahn { height:.35rem; background:#2b2f3b; border-radius:.2rem; margin-top:.3rem; overflow:hidden; }
        .bahn > div { height:100%; background:#7be0a0; }
        .warnung .bahn > div, .warnung .w { background:#ffd989; color:#ffd989; }
        .kritisch .bahn > div, .kritisch .w { background:#ff7a7a; color:#ff7a7a; }
        .unbekannt .w { color:#8a90a2; }
        .ok .w { color:#e6e8ee; }
        .warnung .bahn > div, .kritisch .bahn > div { color:inherit; }
        small { color:#8a90a2; }
      </style>
      <div id="t"></div><p><small id="zeit"></small></p>`;
    this.laden();
    this.takt = setInterval(() => this.laden(), 3000);
  }
  disconnectedCallback() { clearInterval(this.takt); }
  async laden() {
    const r = await window.chimera.api("/api/status/messwerte");
    const t = this.shadowRoot.getElementById("t");
    t.replaceChildren();
    if (!r.ok) {
      const d = document.createElement("div"); d.className = "z kritisch";
      d.textContent = "Fehler: " + (r.fehler || "nicht erreichbar"); t.appendChild(d); return;
    }
    let gruppe = null;
    for (const z of r.zeilen || []) {
      if (z.gruppe !== gruppe) {
        gruppe = z.gruppe;
        const h = document.createElement("h3"); h.textContent = gruppe; t.appendChild(h);
      }
      const d = document.createElement("div"); d.className = "z " + (z.stufe || "unbekannt");
      const k = document.createElement("div"); k.className = "k";
      const a = document.createElement("span"); a.className = "t"; a.textContent = z.titel;
      const b = document.createElement("span"); b.className = "w"; b.textContent = z.text;
      k.append(a, b); d.appendChild(k);
      if (typeof z.anteil === "number") {
        const bahn = document.createElement("div"); bahn.className = "bahn";
        const f = document.createElement("div"); f.style.width = Math.max(0, Math.min(100, z.anteil)) + "%";
        bahn.appendChild(f); d.appendChild(bahn);
      }
      t.appendChild(d);
    }
    this.shadowRoot.getElementById("zeit").textContent = "Stand: " + new Date().toLocaleTimeString();
  }
}
customElements.define("chimera-status", ChimeraStatus);
