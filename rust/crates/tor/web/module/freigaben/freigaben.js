"use strict";
// Modul Freigaben (DESIGN, Regel "Freigabe je Werkzeug auf Zeit").
// Je Werkzeug: Positivliste (einzeln fragen) oder offen. **Kein Ablauf mehr**
// (Entscheidung smilez, 13.11.2026): eine Freigabe bleibt offen, bis der
// Nutzer sie schliesst; statt still zuzumachen erinnert ein Ton alle
// `erinnern_alle` Sekunden. Die Negativliste gilt immer. Der Agent kann hier
// nichts; nur der Nutzer ueber diese Seite oder /frei in Telegram -- beide
// schreiben dieselbe Datei.
class ChimeraFreigaben extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:1rem; }
        h3 { margin:.2rem 0 .5rem; }
        .karte { border:1px solid #2b2f3b; border-radius:.6rem; padding:.75rem; margin:.75rem 0; background:#1c1f28; }
        .kopf { display:flex; justify-content:space-between; gap:.5rem; flex-wrap:wrap; align-items:baseline; }
        .klein { color:#8a90a2; font-size:.85rem; }
        .offen { color:#ffd989; } .zu { color:#8a90a2; } .ja { color:#7be0a0; }
        .fehler { color:#ff7a7a; } .meldung { color:#ffd989; }
        label.klein { display:block; margin-top:.4rem; }
        select, input { background:#1c1f28; color:#e6e8ee; border:1px solid #2b2f3b; border-radius:.4rem; padding:.35rem; font:inherit; box-sizing:border-box; }
        input { width:100%; margin:.2rem 0 .4rem; }
        button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem; padding:.35rem .8rem; font:inherit; cursor:pointer; margin:.2rem .2rem 0 0; }
        button.stumm { background:#2b2f3b; color:#e6e8ee; }
        button.gefahr { background:#ff7a7a; }
        ul { margin:.3rem 0 0; padding-left:1.1rem; font-size:.9rem; }
      </style>
      <h3>Freigaben</h3>
      <p class="klein">Je Werkzeug: <strong>einzeln fragen</strong> (nur Ziele auf der Positivliste) oder <strong>offen</strong> — dann geht alles durch, was nicht auf der Negativliste steht. Eine Freigabe <strong>läuft nicht mehr ab</strong>: sie bleibt offen, bis du sie schließt. Ein Ton kann daran erinnern, ist aber <strong>aus, solange du ihn nicht einschaltest</strong>. Die Negativliste gilt immer. Der Agent kann hier nichts ändern.</p>
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

  // Wie lange steht die Freigabe schon offen? Kein "läuft ab in" mehr --
  // eine Frist gibt es nicht.
  seitText(seit, jetzt) {
    if (!seit) return "seit unbekannt";
    const s = Math.max(0, jetzt - seit);
    if (s < 90) return `seit ${s} s`;
    if (s < 5400) return `seit ${Math.round(s / 60)} min`;
    if (s < 172800) return `seit ${Math.round(s / 3600)} h`;
    return `seit ${Math.round(s / 86400)} Tagen`;
  }

  async laden() {
    const liste = this.$("liste");
    const r = await window.chimera.api("/api/freigaben/lesen");
    liste.replaceChildren();
    if (!r.ok) {
      liste.appendChild(this.el("p", "Fehler: " + (r.fehler && r.fehler.text || r.fehler || "nicht erreichbar"), "fehler"));
      return;
    }
    const jetzt = r.jetzt || Math.round(Date.now() / 1000);
    const w = (r.freigaben && r.freigaben.werkzeuge) || {};
    for (const name of r.werkzeuge || []) {
      liste.appendChild(this.karte(name, w[name] || {}, jetzt));
    }
    liste.appendChild(this.el("p", "Jede Entscheidung wird protokolliert (auch das Ja).", "klein"));
  }

  karte(name, e, jetzt) {
    // Offen ist offen: kein Ablauf mehr. Ein `bis` aus dem Altbestand zaehlt
    // nur, solange es nicht vorbei ist (dieselbe Regel wie in Rust).
    const offen = e.modus === "offen" && (!e.bis || e.bis > jetzt);
    const k = this.el("div", undefined, "karte");
    const kopf = this.el("div", undefined, "kopf");
    kopf.append(
      this.el("strong", name),
      this.el("span", offen ? "offen — " + this.seitText(e.seit, jetzt) : "fragt einzeln (Positivliste)", offen ? "offen" : "zu")
    );
    k.append(kopf);

    const positiv = (e.positiv || []).join(", ");
    const negativ = (e.negativ || []).join(", ");

    // Freigeben: keine Dauerwahl, dafür der Abstand der Erinnerung.
    const zeile = this.el("div");
    const auswahl = this.el("select");
    // Der Ton ist **opt-in** (Entscheidung smilez, 13.11.): er gehoert zu
    // offenen Rueckfragen, nicht zu jeder Freigabe. Vorgabe: ohne Ton.
    for (const [wert, text] of [["0", "ohne Ton (Vorgabe)"], ["300", "alle 5 Minuten"], ["600", "alle 10 Minuten"], ["1800", "alle 30 Minuten"]]) {
      const o = this.el("option", text);
      o.value = wert;
      auswahl.appendChild(o);
    }
    auswahl.value = String(e.erinnern_alle == null ? 0 : e.erinnern_alle);
    const frei = this.el("button", "Freigeben");
    const zu = this.el("button", offen ? "Freigabe beenden" : "Einzeln fragen", "stumm");
    const aus = this.el("div", undefined, "klein");
    const schicken = async (wert) => {
      aus.className = "klein";
      aus.textContent = "";
      const a = await this.post("/api/freigaben/setzen", { werkzeug: name, wert });
      if (!a.ok) {
        aus.className = "fehler";
        aus.textContent = (a.fehler && a.fehler.text) || a.fehler || "Fehler";
        return;
      }
      this.laden();
    };
    const listen = () => ({ positiv: e.positiv || [], negativ: e.negativ || [], notiz: e.notiz || "" });
    frei.onclick = () => {
      schicken({ modus: "offen", erinnern_alle: Number(auswahl.value), ...listen() });
    };
    zu.onclick = () => schicken({ modus: "positivliste", ...listen() });
    zeile.append(auswahl, " ", frei, zu, aus);
    k.append(zeile);

    // Listen
    const lp = this.el("input");
    lp.value = positiv;
    lp.placeholder = "erlaubte Ziele, mit Komma getrennt";
    const ln = this.el("input");
    ln.value = negativ;
    ln.placeholder = "immer gesperrte Ziele, mit Komma getrennt";
    const speichern = this.el("button", "Listen speichern", "stumm");
    speichern.onclick = () => {
      const teile = (t) => t.split(",").map((x) => x.trim()).filter((x) => x.length);
      schicken({
        modus: e.modus === "offen" ? "offen" : "positivliste",
        erinnern_alle: e.erinnern_alle == null ? 0 : e.erinnern_alle,
        positiv: teile(lp.value),
        negativ: teile(ln.value),
        notiz: e.notiz || "",
      });
    };
    k.append(this.el("label", "Positivliste (gilt immer für diese Ziele)", "klein"), lp);
    k.append(this.el("label", "Negativliste (gilt immer)", "klein"), ln);
    k.append(speichern);
    if (e.notiz) k.append(this.el("p", e.notiz, "klein"));
    return k;
  }
}
customElements.define("chimera-freigaben", ChimeraFreigaben);
