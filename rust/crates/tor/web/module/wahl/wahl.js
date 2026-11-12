"use strict";
// Modul Wahl (DESIGN 5h, 5r): zeigt, was das Gateway benutzt -- Modellkette,
// Teilstuecke, Suchquellen. Aenderbar ist hier nur der Strom-Schalter; alles
// Gesendete geht durch /api/wahl/*, das Gateway prueft Recht und Eingabe.
// Eine Eigenschaft des Gateways, nicht dieses Browsers: der Schalter gilt
// gleichzeitig fuer Telegram und die Kommandozeile.
class ChimeraWahl extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:1rem; }
        h3 { margin:.2rem 0 .5rem; }
        .karte { border:1px solid #2b2f3b; border-radius:.6rem; padding:.75rem; margin:.75rem 0; background:#1c1f28; }
        .kopf { display:flex; justify-content:space-between; gap:.5rem; flex-wrap:wrap; align-items:baseline; }
        .klein { color:#8a90a2; font-size:.85rem; }
        ul { margin:.3rem 0 0; padding-left:1.1rem; font-size:.9rem; }
        button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem; padding:.35rem .8rem; font:inherit; cursor:pointer; }
        button.stumm { background:#2b2f3b; color:#e6e8ee; }
        .ja { color:#7be0a0; } .nein { color:#8a90a2; }
        .fehler { color:#ff7a7a; } .meldung { color:#ffd989; }
      </style>
      <h3>Wahl des Gateways</h3>
      <p class="klein">Diese Einstellungen gelten fuer alle Tueren: Chat, Telegram und Kommandozeile.</p>
      <div id="liste"></div>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
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
    const liste = this.$("liste");
    const r = await window.chimera.api("/api/wahl/lesen");
    liste.replaceChildren();
    if (!r.ok) {
      liste.appendChild(this.el("p", "Fehler: " + (r.fehler && r.fehler.text || r.fehler || "nicht erreichbar"), "fehler"));
      return;
    }
    const w = r.wahl || {};

    // Teilstuecke (Strom)
    const strom = this.el("div", undefined, "karte");
    const kopf = this.el("div", undefined, "kopf");
    kopf.append(this.el("strong", "Teilstuecke (Strom)"), this.el("span", r.strom ? "an" : "aus", r.strom ? "ja" : "nein"));
    strom.append(kopf, this.el("p", "An: Ollama schickt die Antwort in Stuecken, das Gateway setzt sie zusammen. Aus: eine Antwort am Stueck.", "klein"));
    const b = this.el("button", r.strom ? "Ausschalten" : "Einschalten", "stumm");
    const aus = this.el("div", undefined, "klein");
    b.onclick = async () => {
      b.disabled = true;
      const a = await this.post("/api/wahl/strom", { an: !r.strom });
      if (a.ok) { this.laden(); return; }
      b.disabled = false;
      aus.className = "fehler";
      aus.textContent = (a.fehler && a.fehler.text) || a.fehler || "Fehler";
    };
    strom.append(b, aus);
    liste.appendChild(strom);

    // Modellkette
    const reihe = this.el("div", undefined, "karte");
    reihe.appendChild(this.el("strong", "Modellkette"));
    const rl = (w.reihenfolge || []).filter((x) => typeof x === "string");
    if (rl.length) {
      const ul = this.el("ul");
      for (const x of rl) ul.appendChild(this.el("li", x));
      reihe.appendChild(ul);
    } else {
      reihe.appendChild(this.el("p", "Keine Vorgabe: es gilt das erste Modell, das Werkzeuge kann.", "klein"));
    }
    reihe.appendChild(this.el("p", "Reihenfolge und Modelle pflegst du im Modul Ollama; /model im Telegram schreibt in dieselbe Datei.", "klein"));
    liste.appendChild(reihe);

    // Suchquellen
    const quellen = (w.suche && w.suche.quellen) || [];
    const suche = this.el("div", undefined, "karte");
    suche.appendChild(this.el("strong", "Suchquellen"));
    if (quellen.length) {
      const ul = this.el("ul");
      for (const x of quellen) ul.appendChild(this.el("li", x === "ollama" ? "ollama (Schluessel aus der Umgebung)" : x));
      suche.appendChild(ul);
    } else {
      suche.appendChild(this.el("p", "Keine Quelle eingetragen: die Websuche meldet dann \"keine_quelle\".", "klein"));
    }
    suche.appendChild(this.el("p", "In wahl.json unter suche.quellen. Reihenfolge gilt; ddg ist kostenlos und ohne Schluessel (Opt-in).", "klein"));
    liste.appendChild(suche);

    for (const m of r.meldungen || []) {
      liste.appendChild(this.el("p", m.quelle + ": " + m.text, "meldung"));
    }
  }
}
customElements.define("chimera-wahl", ChimeraWahl);
