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
      </style>
      <h3>Konten</h3>
      <p class="klein">Guthaben je Anbieter. Jede Zahl nennt ihre Herkunft; ein alter Stand
      steht als alt da, nicht als neu. Der Betrag in der Originalwährung bleibt die Zahl —
      der Euro-Wert steht in Klammern und kommt aus dem Kurs oben.</p>
      <div id="kurse" class="klein"></div>
      <div id="liste"></div>
      <button id="neu">Alle neu holen</button> <span id="stand" class="klein"></span>
      <p id="fehler" class="fehler"></p>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
    this.$("neu").onclick = () => this.laden(true);
    this.laden(false);
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
