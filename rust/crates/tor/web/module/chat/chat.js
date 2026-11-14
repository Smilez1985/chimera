"use strict";
// Chat-Modul (DESIGN 5m): hängt am selben Strom wie Telegram. Zeigt Text nur
// per textContent an, nie als HTML.
class ChimeraChat extends HTMLElement {
  connectedCallback() {
    this.seit = 0;
    this.ersterStrom = true;
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
        #alt { padding:.25rem .75rem; font-size:.85rem; display:flex; flex-wrap:wrap; gap:.4rem; align-items:center; }
        #alt select { max-width:11rem; }
        select { background:#1c1f28; color:#e6e8ee; border:1px solid #2b2f3b; border-radius:.4rem; }
      </style>
      <div id="alt">
        <label>Sitzung: <select id="wahl"></select></label>
        <label>Anbieter: <select id="a-wahl"></select></label>
        <label>Modell: <select id="m-wahl"></select></label>
        <label>Denken: <select id="d-wahl"></select></label>
      </div>
      <div id="liste"></div>
      <div id="denkt"></div>
      <form><textarea id="eingabe" rows="2" placeholder="Nachricht"></textarea><button type="submit">Senden</button></form>`;
    this.liste = this.shadowRoot.getElementById("liste");
    this.denkt = this.shadowRoot.getElementById("denkt");
    this.wahl = this.shadowRoot.getElementById("wahl");
    this.aWahl = this.shadowRoot.getElementById("a-wahl");
    this.mWahl = this.shadowRoot.getElementById("m-wahl");
    this.dWahl = this.shadowRoot.getElementById("d-wahl");
    this.auswahlDaten = [];
    this.aWahl.addEventListener("change", () => this.modelleZeigen());
    this.mWahl.addEventListener("change", () => this.denkenZeigen());
    this.shadowRoot.querySelector("form").addEventListener("submit", (e) => { e.preventDefault(); this.senden(); });
    this.shadowRoot.getElementById("eingabe").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this.senden(); }
    });
    this.wahl.addEventListener("change", () => this.sitzungWechseln());
    // Beim Hochscrollen rueckwaerts nachladen (Nutzerbefund 14.11.: nach
    // einem Neuladen war der Verlauf weg).
    this.liste.addEventListener("scroll", () => {
      if (this.liste.scrollTop < 80) this.aeterLaden();
    });
    this.sitzungenLaden();
    this.auswahlLaden();
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
    const auftrag = { text };
    // Die Wahl gilt fuer die Sitzung, nicht nur fuer dieses Fenster: sie geht
    // mit jeder Frage mit. Leer heisst "der Anbieter entscheidet" (5h).
    if (this.aWahl.value) auftrag.anbieter = this.aWahl.value;
    if (this.mWahl.value) auftrag.modell = this.mWahl.value;
    if (this.dWahl.value && this.aWahl.value) auftrag.denken = this.dWahl.value;
    const r = await window.chimera.api("/api/chat/senden", { method: "POST", body: JSON.stringify(auftrag) });
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
          for (const e of r.ereignisse) {
            this.seit = Math.max(this.seit, e.nr);
            // Der erste Abruf nach dem Laden holt den Puffer nach -- was
            // schon im Verlauf steht, waere sonst doppelt. Deshalb wird beim
            // ersten Durchgang nur die Marke gesetzt.
            if (!this.ersterStrom) this.ereignis(e);
          }
          this.ersterStrom = false;
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

  /// Die letzten Eintraege einer Sitzung holen und anzeigen. `vor` ist der
  /// Abstand vom Ende -- damit laesst sich stueckweise rueckwaerts laden.
  async verlaufLaden(sid, vor = 0) {
    const pfad = `/api/chat/lesen?sitzung=${encodeURIComponent(sid)}&max=50&vor=${vor}`;
    const r = await window.chimera.api(pfad);
    if (!r.ok) { this.blase("sys", r.fehler || "Verlauf nicht lesbar"); return null; }
    return r;
  }

  /// Aeltere Eintraege vorne anhaengen und die Scrollposition halten --
  /// sonst springt der Text beim Nachladen unter dem Finger weg.
  async aeterLaden() {
    if (this.laedtAlt || !this.gesamt || !this.sid) return;
    const geladen = this.geladen || 0;
    if (geladen >= this.gesamt) return;
    this.laedtAlt = true;
    try {
      const r = await this.verlaufLaden(this.sid, geladen);
      if (r && r.eintraege && r.eintraege.length) {
        const hoehe = this.liste.scrollHeight;
        const vorne = document.createDocumentFragment();
        for (const e of r.eintraege) {
          const knoten = this.blasenKnoten(e);
          if (knoten) vorne.appendChild(knoten);
        }
        this.liste.insertBefore(vorne, this.liste.firstChild);
        this.geladen = geladen + r.eintraege.length;
        this.liste.scrollTop = this.liste.scrollHeight - hoehe;
      } else {
        this.geladen = this.gesamt;   // nichts mehr da
      }
    } finally {
      this.laedtAlt = false;
    }
  }

  /// Eine Blase bauen, ohne sie anzuhaengen (fuer das Nachladen oben).
  blasenKnoten(e) {
    const d = document.createElement("div");
    if (!e || e.art === "verdichtet") {
      d.className = "m sys";
      d.textContent = "— verdichtet —";
      return d;
    }
    if (e.art !== "nachricht") return null;
    d.className = "m " + (e.rolle === "user" ? "ich" : "sie");
    d.appendChild(document.createTextNode(e.inhalt || ""));
    return d;
  }

  /// Was zur Wahl steht (nur gemessene Werkzeug-Modelle, Spezialmodelle
  /// getrennt und nicht waehlbar). DESIGN: "Die Modellwahl im Chat".
  async auswahlLaden() {
    const r = await window.chimera.api("/api/chat/auswahl");
    if (!r.ok) { this.aWahl.replaceChildren(this.option("", "Auswahl nicht abrufbar")); return; }
    this.auswahlDaten = r.anbieter || [];
    this.aWahl.replaceChildren(this.option("", "automatisch"));
    for (const a of this.auswahlDaten) {
      this.aWahl.appendChild(this.option(a.id, a.bezeichnung || a.id));
    }
    this.modelleZeigen();
  }

  option(wert, text, gesperrt) {
    const o = document.createElement("option");
    o.value = wert;
    o.textContent = text;
    if (gesperrt) o.disabled = true;
    return o;
  }

  anbieterDaten() {
    return this.auswahlDaten.find((a) => a.id === this.aWahl.value) || null;
  }

  /// Modelle des gewaehlten Anbieters. Spezialmodelle stehen **da**, sind
  /// aber nicht waehlbar -- sonst raetselt jemand, wo sein Modell bleibt.
  modelleZeigen() {
    const a = this.anbieterDaten();
    this.mWahl.replaceChildren();
    this.dWahl.replaceChildren(this.option("", "—"));
    if (!a) { this.mWahl.appendChild(this.option("", "automatisch")); this.dWahl.disabled = true; return; }
    const chat = a.chat || [];
    if (!chat.length) {
      this.mWahl.appendChild(this.option("", "kein Modell mit Werkzeugen"));
    } else {
      for (const m of chat) {
        this.mWahl.appendChild(this.option(m.modell, m.modell));
      }
    }
    if ((a.spezial || []).length) {
      const g = document.createElement("optgroup");
      g.label = "Spezialmodelle (nicht für den Chat)";
      for (const m of a.spezial) g.appendChild(this.option(m.modell, `${m.modell} — ${m.art}`, true));
      this.mWahl.appendChild(g);
    }
    if ((a.unbekannt || []).length) {
      const g = document.createElement("optgroup");
      g.label = "Werkzeuge nicht gemessen";
      for (const m of a.unbekannt) g.appendChild(this.option(m.modell, m.modell, true));
      this.mWahl.appendChild(g);
    }
    this.denkenZeigen();
  }

  /// Nur die Denkstufen, die dieses Modell wirklich kann.
  denkenZeigen() {
    const a = this.anbieterDaten();
    const m = a && (a.chat || []).find((x) => x.modell === this.mWahl.value);
    const stufen = (m && m.denkstufen) || [];
    this.dWahl.replaceChildren();
    if (!stufen.length) {
      this.dWahl.appendChild(this.option("", "keine"));
      this.dWahl.disabled = true;
      return;
    }
    this.dWahl.disabled = false;
    this.dWahl.appendChild(this.option("", "Vorgabe"));
    for (const st of stufen) this.dWahl.appendChild(this.option(st, st));
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
    // Der Verlauf kommt beim Oeffnen der Seite -- nicht erst beim Umschalten.
    this.sid = r.haupt;
    this.wahl.value = r.haupt;
    await this.verlaufZeigen();
  }

  async sitzungWechseln() {
    this.sid = this.wahl.value;
    this.schreibgeschuetzt = this.sid !== this.haupt;
    this.liste.replaceChildren();
    this.geladen = 0;
    this.seit = 0;
    await this.verlaufZeigen();
  }

  /// Den Verlauf der gewaehlten Sitzung anzeigen -- beim Laden UND beim
  /// Wechseln derselbe Weg, damit nach einem Neuladen nichts fehlt.
  async verlaufZeigen() {
    if (!this.sid) return;
    const r = await this.verlaufLaden(this.sid, 0);
    if (!r) return;
    this.gesamt = r.gesamt || 0;
    this.geladen = (r.eintraege || []).length;
    for (const e of r.eintraege || []) {
      const k = this.blasenKnoten(e);
      if (k) this.liste.appendChild(k);
    }
    this.liste.scrollTop = this.liste.scrollHeight;
  }
}
customElements.define("chimera-chat", ChimeraChat);
