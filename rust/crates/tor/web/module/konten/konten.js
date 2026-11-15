"use strict";
// Modul „Konten": das Guthaben je Anbieter (ROADMAP „Guthaben und Kosten je
// Anbieter", Auftrag 13.11.).
//
// Grundsätze, die hier sichtbar werden müssen, nicht nur im Code:
//  * Je Währung ein eigener Betrag; der €-Wert steht in Klammern (15.11.:
//    Auftrag smilez -- mit Kurs oben, Summe je Anbieter).
//  * Herkunft steht an jeder Zahl (Quelle, Belegtheit, Endpunkt).
//  * Ein alter Stand wird gezeigt und als alt beschriftet, nicht versteckt.
//  * Wo es keine Zahl gibt, steht der Grund.
class ChimeraKonten extends HTMLElement {
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
        .ja { color:#7be0a0; } .nein { color:#ff7a7a; } .alt { color:#ffd989; }
        .fehler { color:#ff7a7a; }
        table { width:100%; border-collapse:collapse; margin-top:.4rem; font-size:.9rem; }
        td, th { text-align:left; padding:.25rem .4rem; border-bottom:1px solid #2b2f3b; }
        th { color:#8a90a2; font-weight:normal; }
        .betrag { font-variant-numeric:tabular-nums; }
        button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem; padding:.35rem .8rem; font:inherit; cursor:pointer; margin:.5rem .2rem 0 0; }
        button.stumm { background:#2b2f3b; color:#e6e8ee; }
        code { font-family:ui-monospace, monospace; font-size:.8rem; word-break:break-all; }
        .reiter { display:flex; gap:.4rem; margin:.4rem 0 .6rem; }
        .reiter button { background:#2b2f3b; color:#e6e8ee; }
        .reiter button.an { background:#7aa2ff; color:#0b0d12; }
        .balken { background:#2b2f3b; border-radius:.3rem; height:.6rem; width:6rem; overflow:hidden; }
        .balken-fuellung { background:#7aa2ff; height:100%; }
      </style>
      <h3>Konten</h3>
      <p class="klein">Guthaben je Anbieter. Jede Zahl nennt ihre Herkunft; ein alter Stand
      steht als alt da, nicht als neu. Der Betrag in der Originalwährung bleibt die Zahl —
      der Euro-Wert steht in Klammern und kommt aus dem Kurs oben.</p>
      <div id="kurse" class="klein"></div>
      <div class="reiter">
        <button id="r-guthaben" class="an">Guthaben</button>
        <button id="r-verbrauch">Verbrauch</button>
      </div>
      <div id="bereich-guthaben">
        <div id="liste"></div>
        <button id="neu">Alle neu holen</button> <span id="stand" class="klein"></span>
      </div>
      <div id="bereich-verbrauch" hidden>
        <p class="klein">Oben, was Chimera selbst mitzählt (Token je Aufruf, aus der
        Antwort des Anbieters). Darunter die Abrechnung laut Anbieter — die
        Kontostand-Abnahme. Beides mit Herkunft; umgerechnet wird nichts.</p>
        <div id="verbrauchsliste"></div>
      </div>
      <p id="fehler" class="fehler"></p>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
    this.$("neu").onclick = () => this.laden(true);
    this.$("r-guthaben").onclick = () => this.reiter("guthaben");
    this.$("r-verbrauch").onclick = () => this.verbrauchZeigen();
    this.laden(false);
  }

  /** Zwischen Guthaben und Verbrauch umschalten. */
  reiter(was) {
    this.$("bereich-guthaben").hidden = was !== "guthaben";
    this.$("bereich-verbrauch").hidden = was !== "verbrauch";
    this.$("r-guthaben").className = was === "guthaben" ? "an" : "";
    this.$("r-verbrauch").className = was === "verbrauch" ? "an" : "";
  }

  /** Zahl mit Tausenderpunkten -- Tokens werden schnell gross. */
  zahl(n) {
    const v = Number(n);
    if (!Number.isFinite(v)) return "—";
    return v.toLocaleString("de-DE");
  }

  /** Der Verbrauchsreiter: eigene Zaehlung und Abrechnung nebeneinander. */
  async verbrauchZeigen() {
    this.reiter("verbrauch");
    const ziel = this.$("verbrauchsliste");
    ziel.replaceChildren(this.el("p", "Lade ...", "klein"));
    let r;
    try {
      r = await window.chimera.api("/api/verbrauch?tage=7");
    } catch (e) {
      ziel.replaceChildren(this.el("p", "Nicht abrufbar: " + e, "fehler"));
      return;
    }
    ziel.replaceChildren();
    if (!r || r.ok !== true) {
      ziel.appendChild(this.el("p", "Nicht abrufbar: " +
        ((r && r.fehler && r.fehler.text) || "unbekannter Grund"), "fehler"));
      return;
    }
    const tage = r.tag || [];
    if (!tage.length) {
      ziel.appendChild(this.el("p", "Noch kein Verbrauch gezaehlt.", "klein"));
    } else {
      // Die groesste Tagesmenge bestimmt den Balken -- reine CSS-Breite,
      // keine Bibliothek (Auftrag: ohne Grafana).
      const groesste = Math.max(...tage.map((x) => Number(x.eingabe || 0) + Number(x.ausgabe || 0)), 1);
      const t = document.createElement("table");
      const kopf = document.createElement("tr");
      for (const h of ["Tag", "Aufrufe", "Eingabe", "Ausgabe", ""]) kopf.appendChild(this.el("th", h));
      t.appendChild(kopf);
      for (const x of tage) {
        const tr = document.createElement("tr");
        tr.appendChild(this.el("td", x.tag || "?"));
        tr.appendChild(this.el("td", this.zahl(x.aufrufe), "betrag"));
        tr.appendChild(this.el("td", this.zahl(x.eingabe), "betrag"));
        tr.appendChild(this.el("td", this.zahl(x.ausgabe), "betrag"));
        const balken = this.el("div", "", "balken");
        const f = this.el("div", "", "balken-fuellung");
        const menge = Number(x.eingabe || 0) + Number(x.ausgabe || 0);
        f.style.width = Math.max(2, Math.round((menge / groesste) * 100)) + "%";
        balken.appendChild(f);
        const zelle = document.createElement("td");
        zelle.appendChild(balken);
        tr.appendChild(zelle);
        t.appendChild(tr);
      }
      ziel.appendChild(t);
      const s = r.summe || {};
      ziel.appendChild(this.el("p", "Summe: " + this.zahl(s.aufrufe) + " Aufrufe, " +
        this.zahl(s.eingabe) + " Eingabe, " + this.zahl(s.ausgabe) + " Ausgabe-Token.",
        "klein"));
      ziel.appendChild(this.el("p", r.quelle || "", "klein"));
    }
    ziel.appendChild(this.abrechnungTeil(r.abrechnung));
  }

  /** Die Abrechnungsseite: Kontostand-Abnahme je Anbieter. */
  abrechnungTeil(a) {
    const box = document.createElement("div");
    box.appendChild(this.el("h4", "Abrechnung laut Anbieter"));
    if (!a || !(a.anbieter || []).length) {
      box.appendChild(this.el("p", "Kein Anbieter mit abrufbarem Guthaben.", "klein"));
      return box;
    }
    for (const x of a.anbieter) {
      const k = this.el("div", undefined, "karte");
      k.appendChild(this.el("h4", x.bezeichnung || x.id));
      const v = x.veraenderung || {};
      const waehrungen = Object.keys(v).sort();
      if (waehrungen.length) {
        const teile = waehrungen.map((w) => {
          const n = Number(v[w]);
          const zeichen = n > 0 ? "+" : "";
          return zeichen + n.toFixed(2).replace(".", ",") + " " + w;
        });
        k.appendChild(this.el("p", "Veränderung im Zeitraum: " + teile.join(" · "), "betrag"));
      } else {
        k.appendChild(this.el("p", x.hinweis || "Noch keine Vergleichsbasis.", "klein"));
      }
      k.appendChild(this.el("p", this.zahl(x.anzahl) + " Kontostände mitgeschrieben.", "klein"));
      box.appendChild(k);
    }
    if (a.hinweis) box.appendChild(this.el("p", a.hinweis, "klein"));
    return box;
  }

  /** "12.34 ≈ 11,17 €" -- Original bleibt vorn, Euro in Klammern. */
  mitEuro(betrag, euro) {
    const roh = (betrag === null || betrag === undefined || betrag === "") ? "—" : String(betrag);
    if (roh === "—") return roh;
    const e = this.euro(euro);
    return e === "—" ? roh : roh + " (" + e + ")";
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

  /** Euro-Betrag fuer die Anzeige: "≈ 1,23 €"; ohne Zahl ein Strich. */
  euro(wert) {
    const n = Number(wert);
    if (wert === null || wert === undefined || !Number.isFinite(n)) return "—";
    return "≈ " + n.toFixed(2).replace(".", ",") + " €";
  }

  /** Die Kurszeile ueber den Karten: je Waehrung ein Kurs, mit Datum. */
  kurseZeigen(k) {
    const ziel = this.$("kurse");
    ziel.replaceChildren();
    const tabelle = (k && k.kurse) || null;
    if (!tabelle) {
      const grund = (k && k.fehler) || "kein Kurs geholt";
      ziel.textContent = "Kurse: keine (" + grund + "). Betraege stehen ohne Euro-Wert da.";
      return;
    }
    const teile = Object.keys(tabelle).sort().map((w) => {
      // Ein Kurs von 1 EUR in W ist der Preis; angezeigt wird lieber, wie
      // viel 1 W in EUR ist -- das ist die Zahl, mit der man rechnet.
      return "1 " + w + " = " + this.euro(tabelle[w]).replace("≈ ", "").replace(" €", "") + " €";
    });
    const datum = k.datum ? " · Kurs vom " + k.datum : "";
    const alt = k.veraltet ? " (aelter, wird nachgeladen)" : "";
    ziel.textContent = "Kurse: " + teile.join(" · ") + datum + alt;
    if (k.fehler) ziel.textContent += " · Abruf: " + k.fehler;
  }

  /** Alter in Worten -- kurz, damit es in eine Zeile passt. */
  alter(s) {
    const n = Number(s);
    if (!Number.isFinite(n) || n < 90) return "gerade eben";
    const m = Math.floor(n / 60);
    if (m < 60) return `vor ${m} Minuten`;
    const h = Math.floor(m / 60);
    if (h < 24) return h === 1 ? "vor 1 Stunde" : `vor ${h} Stunden`;
    const t = Math.floor(h / 24);
    return t === 1 ? "vor 1 Tag" : `vor ${t} Tagen`;
  }

  async laden(neu) {
    this.$("fehler").textContent = "";
    let r;
    if (neu) {
      r = await this.post("/api/quota/erneuern", {});
    } else {
      r = await window.chimera.api("/api/quota/lesen");
    }
    const liste = this.$("liste");
    liste.replaceChildren();
    if (!r.ok || r.ok === undefined) {
      this.$("fehler").textContent = "Nicht abrufbar: " +
        ((r.fehler && r.fehler.text) || r.fehler || "unbekannter Grund");
      return;
    }
    const anbieter = r.anbieter || [];
    if (!anbieter.length) {
      liste.appendChild(this.el("p", "Es ist kein Anbieter eingetragen.", "klein"));
      return;
    }
    this.$("stand").textContent = `Frische: ${Math.round((r.frische_s || 600) / 60)} Minuten.`;
    this.kurseZeigen(r.kurse);
    for (const a of anbieter) liste.appendChild(this.karte(a));
  }

  karte(a) {
    const k = this.el("div", undefined, "karte");
    const kopf = this.el("div", undefined, "kopf");
    kopf.appendChild(this.el("h4", a.bezeichnung || a.id));
    const zustand = a.zustand || "unbekannt";
    const marke = this.el("span", "", "klein");
    if (zustand === "gut") {
      marke.textContent = a.veraltet
        ? `veraltet, Stand ${this.alter(a.alter_s)}`
        : `Stand ${this.alter(a.alter_s)}`;
      marke.className = a.veraltet ? "alt" : "klein";
    } else if (zustand === "kein_guthaben_noetig") {
      marke.textContent = "kein Guthaben nötig";
      marke.className = "ja";
    } else if (zustand === "nicht_abrufbar" || zustand === "abruf_gescheitert") {
      marke.textContent = "nicht abrufbar";
      marke.className = "nein";
    } else {
      marke.textContent = "unbekannt";
    }
    kopf.appendChild(marke);
    k.appendChild(kopf);
    k.appendChild(this.el("p", a.typ ? `Typ: ${a.typ}` : "", "klein"));

    const pools = a.pools || [];
    if (pools.length) {
      const t = document.createElement("table");
      const kopfZeile = document.createElement("tr");
      for (const h of ["Währung", "Gesamt", "Aufgeladen", "Geschenkt"]) {
        kopfZeile.appendChild(this.el("th", h));
      }
      t.appendChild(kopfZeile);
      for (const p of pools) {
        const tr = document.createElement("tr");
        tr.appendChild(this.el("td", p.waehrung || "?"));
        tr.appendChild(this.el("td", this.mitEuro(p.gesamt, p.euro), "betrag"));
        tr.appendChild(this.el("td", this.mitEuro(p.aufgeladen, p.euro_aufgeladen), "betrag"));
        tr.appendChild(this.el("td", this.mitEuro(p.geschenkt, p.euro_geschenkt), "betrag"));
        t.appendChild(tr);
      }
      k.appendChild(t);
      // Summe nur innerhalb dieses Anbieters: beide Waehrungen zahlen
      // dasselbe Konto (smilez, 15.11.). Ueber Anbieter wird nicht summiert.
      if (a.summe_euro !== undefined && a.summe_euro !== null) {
        const w = (a.summe_waehrungen || []).join(" + ");
        k.appendChild(this.el("p", "Gesamt: " + w + " " + this.euro(a.summe_euro), "betrag"));
      } else if ((a.summe_waehrungen || []).length) {
        k.appendChild(this.el("p", "Gesamt: kein Euro-Wert, weil fuer " +
          a.summe_waehrungen.join("/") + " kein Kurs vorliegt.", "alt"));
      }
      // Ein Hinweis, der nicht als Zahl taugt, wird nicht verschluckt.
      if (a.verfuegbar === false) {
        k.appendChild(this.el("p", "Der Anbieter meldet: zur Zeit nicht verfügbar.", "alt"));
      }
    }

    const h = a.hinweis || (a.fehler && a.fehler.text) || "";
    if (h) k.appendChild(this.el("p", h, zustand === "gut" ? "klein" : "alt"));

    const herkunft = a.herkunft || {};
    if (herkunft.quelle) {
      const zeile = this.el("p", `Quelle: ${herkunft.quelle} · ${herkunft.belegtheit || "?"}`, "klein");
      if (herkunft.endpunkt) {
        zeile.appendChild(document.createTextNode(" · "));
        zeile.appendChild(this.el("code", herkunft.endpunkt));
      }
      k.appendChild(zeile);
    }
    if (zustand === "gut" || zustand === "abruf_gescheitert") {
      const knopf = this.el("button", "Neu holen", "stumm");
      knopf.onclick = async () => {
        knopf.disabled = true;
        const r = await this.post("/api/quota/erneuern", { id: a.id });
        if (!r.ok) {
          this.$("fehler").textContent = "Erneuern gescheitert: " +
            ((r.fehler && r.fehler.text) || r.fehler || "unbekannter Grund");
        }
        await this.laden(false);
      };
      k.appendChild(knopf);
    }
    return k;
  }
}
customElements.define("chimera-konten", ChimeraKonten);
