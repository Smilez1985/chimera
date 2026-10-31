"use strict";
// Status-Modul (DESIGN 5m): zeigt Dienste, Speicher, Temperatur, Last, Platte.
// Werte nur per textContent; fehlt ein Wert, steht "nicht lesbar", nie 0.
class ChimeraStatus extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:1rem; }
        table { border-collapse:collapse; width:100%; max-width:34rem; }
        td { padding:.4rem .5rem; border-bottom:1px solid #2b2f3b; }
        td:first-child { color:#8a90a2; width:45%; }
        .aus { color:#ff7a7a; } .ein { color:#7be0a0; }
        small { color:#8a90a2; }
      </style>
      <table id="t"></table><p><small id="zeit"></small></p>`;
    this.laden();
    this.takt = setInterval(() => this.laden(), 5000);
  }
  disconnectedCallback() { clearInterval(this.takt); }
  zeile(name, wert, klasse) {
    const tr = document.createElement("tr");
    const a = document.createElement("td"), b = document.createElement("td");
    a.textContent = name; b.textContent = wert;
    if (klasse) b.className = klasse;
    tr.append(a, b);
    return tr;
  }
  async laden() {
    const r = await window.chimera.api("/api/status/messwerte");
    const t = this.shadowRoot.getElementById("t");
    t.replaceChildren();
    if (!r.ok) { t.appendChild(this.zeile("Fehler", r.fehler || "nicht erreichbar", "aus")); return; }
    const nl = "nicht lesbar";
    const gb = (m) => (m / 1024).toFixed(1) + " GB";
    t.appendChild(this.zeile("Temperatur", r.temperatur_c == null ? nl : r.temperatur_c.toFixed(1) + " °C"));
    t.appendChild(this.zeile("Arbeitsspeicher", r.speicher_mib ? `${r.speicher_mib.verfuegbar} von ${r.speicher_mib.gesamt} MiB frei` : nl));
    t.appendChild(this.zeile("Last (1/5/15 min)", r.last ? r.last.join(" / ") : nl));
    t.appendChild(this.zeile("Laufzeit", r.laufzeit_s == null ? nl : Math.floor(r.laufzeit_s / 3600) + " h"));
    t.appendChild(this.zeile("Platte", r.platte_mib ? `${gb(r.platte_mib.belegt)} von ${gb(r.platte_mib.gesamt)} belegt` : nl));
    for (const d of r.dienste || []) t.appendChild(this.zeile(d.name, d.zustand, d.zustand === "aktiv" ? "ein" : "aus"));
    this.shadowRoot.getElementById("zeit").textContent = "Stand: " + new Date().toLocaleTimeString();
  }
}
customElements.define("chimera-status", ChimeraStatus);
