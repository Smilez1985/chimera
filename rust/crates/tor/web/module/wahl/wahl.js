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
        ul.kette { padding-left:0; list-style:none; }
        ul.kette li { display:flex; align-items:center; gap:.3rem; padding:.15rem 0; }
        ul.kette .verweis { flex:1; word-break:break-all; }
        button.klein-knopf { padding:.1rem .4rem; font-size:.85rem; }
        button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem; padding:.35rem .8rem; font:inherit; cursor:pointer; }
        button.stumm { background:#2b2f3b; color:#e6e8ee; }
        .ja { color:#7be0a0; } .nein { color:#8a90a2; }
        .fehler { color:#ff7a7a; } .meldung { color:#ffd989; }
      </style>
      <h3>Wahl des Gateways</h3>
      <p class="klein">Diese Einstellungen gelten fuer alle Tueren: Chat, Telegram und Kommandozeile.</p>
      <div id="liste"></div>
      <p id="meldung" class="fehler"></p>`;
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
    this.ketteListe = (w.reihenfolge || []).filter((x) => typeof x === "string");

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

    // Modellkette: sortieren und kuerzen. Gesendet wird immer die ganze Liste
    // -- eine Stelle, die den Wert prueft (daten::feld_wert_pruefen).
    const reihe = this.el("div", undefined, "karte");
    reihe.appendChild(this.el("strong", "Modellkette"));
    const rl = (w.reihenfolge || []).filter((x) => typeof x === "string");
    const kettenAusgabe = this.el("div", undefined, "klein");
    if (rl.length) {
      const ul = this.el("ul");
      ul.className = "kette";
      rl.forEach((x, i) => {
        const li = this.el("li");
        li.appendChild(this.el("span", x, "verweis"));
        const hoch = this.el("button", "▲", "stumm klein-knopf");
        hoch.title = "nach oben";
        hoch.disabled = i === 0;
        hoch.onclick = () => this.kette(i, i - 1);
        const runter = this.el("button", "▼", "stumm klein-knopf");
        runter.title = "nach unten";
        runter.disabled = i === rl.length - 1;
        runter.onclick = () => this.kette(i, i + 1);
        const weg = this.el("button", "✕", "gefahr klein-knopf");
        weg.title = "aus der Kette nehmen";
        weg.onclick = () => this.kette(i, -1);
        li.append(hoch, runter, weg);
        ul.appendChild(li);
      });
      reihe.appendChild(ul);
    } else {
      reihe.appendChild(this.el("p", "Keine Vorgabe: es gilt das erstes Modell, das Werkzeuge kann.", "klein"));
    }
    reihe.appendChild(kettenAusgabe);
    reihe.appendChild(this.el("p", "Die Reihenfolge bestimmt, welches Modell zuerst gefragt wird. Ein Modell ohne Werkzeuge wird bei Aufgaben mit Werkzeugen übersprungen.", "klein"));
    reihe.appendChild(this.el("p", "Angelegte Modelle pflegst du im Modul Ollama; /model im Telegram schreibt in dieselbe Datei.", "klein"));
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

  // Sortieren und Kuerzen der Kette. Eine Handlung = eine ganze Liste:
  // so gibt es keine Teilzustaende und nur eine Pruefung im Dienst.
  async kette(von, nach) {
    const liste = (this.ketteListe || []).slice();
    if (von < 0 || von >= liste.length) return;
    if (nach < 0) liste.splice(von, 1);
    else if (nach < liste.length) [liste[von], liste[nach]] = [liste[nach], liste[von]];
    else return;
    const meldung = this.$("meldung");
    meldung.textContent = "";
    const r = await this.post("/api/wahl/reihenfolge", { reihenfolge: liste });
    if (!r.ok) {
      meldung.textContent = (r.fehler && r.fehler.text) || r.fehler || "Fehler";
      return;
    }
    this.laden();
  }
}
customElements.define("chimera-wahl", ChimeraWahl);
