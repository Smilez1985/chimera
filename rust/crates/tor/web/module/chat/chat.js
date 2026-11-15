"use strict";
// Chat-Modul (DESIGN 5m): hängt am selben Strom wie Telegram. Zeigt Text nur
// per textContent an, nie als HTML.
/// Weicht eine Blase dem Gesicht aus? Reine Rechnung ohne DOM, damit
/// `tests/js/chat_umfluss.mjs` sie an der ECHTEN Datei pruefen kann.
///
/// `rechts` sagt, auf welcher Seite des Verlaufs das Gesicht liegt. Eine Blase
/// weicht aus, wenn sie es senkrecht ueberdeckt UND auf seiner Seite bis unter
/// seine Kante reicht -- eine schmale Blase weit links stoert niemanden.
function weichtAus(blase, gesicht, rechts) {
  const senkrecht = blase.unten > gesicht.oben && blase.oben < gesicht.unten;
  if (!senkrecht) return false;
  return rechts ? blase.rechts > gesicht.links : blase.links < gesicht.rechts;
}

/// Kleinste Höhe der Eingabe: zwei Zeilen (die Vorgabe aus `rows="2"`).
const EINGABE_MIN = 42;
/// Gemerkte Höhe je Gerät (Ansichtssache, keine Geräteeinstellung).
const EINGABE_SCHLUESSEL = "chimera.eingabe.hoehe";

/// Wie hoch das Eingabefeld wird. Reine Rechnung, damit
/// `tests/js/chat_eingabe.mjs` sie an der ECHTEN Datei prüfen kann.
///
/// `fest` ist die vom Nutzer gezogene Höhe, `inhalt` was der Text braucht,
/// `hoechst` die Grenze (60 % des Fensters). Es gilt: **nie unter die gezogene
/// Höhe**, nie über die Grenze — und wächst der Text darüber hinaus, wird das
/// Feld größer, statt den Text abzuschneiden.
function eingabeHoehe(fest, inhalt, hoechst) {
  const unten = Number.isFinite(fest) && fest > 0 ? fest : EINGABE_MIN;
  const grenze = Number.isFinite(hoechst) && hoechst > unten ? hoechst : unten;
  const braucht = Number.isFinite(inhalt) && inhalt > 0 ? inhalt : 0;
  return Math.round(Math.min(Math.max(unten, braucht), grenze));
}

/// Höhe beim Ziehen am Griff: nach oben (negatives `dy`) wird höher,
/// begrenzt auf `min`/`max`. Auch das ist eine Rechnung, kein Zustand.
function griffHoehe(start, dy, min, max) {
  const unten = Number.isFinite(min) && min > 0 ? min : EINGABE_MIN;
  const oben = Number.isFinite(max) && max > unten ? max : unten;
  if (!Number.isFinite(start)) return unten;
  // Ein kaputtes `dy` heisst „nicht gezogen", nicht „auf Minimum springen".
  const roh = start - (Number.isFinite(dy) ? dy : 0);
  return Math.round(Math.min(Math.max(roh, unten), oben));
}

class ChimeraChat extends HTMLElement {
  connectedCallback() {
    this.seit = 0;
    this.ersterStrom = true;
    this.laeuft = true;
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:flex; flex-direction:column; height:100%; }
        /* Flaeche mit Verlauf und Buehne: das Gesicht liegt FEST ueber dem
           Verlauf und scrollt nicht mit (DESIGN, Regel „Anzeigespiegel"). */
        #flaeche { position:relative; flex:1; min-height:0; }
        #buehne { position:absolute; inset:0; pointer-events:none; }
        #buehne > * { pointer-events:auto; }
        #liste { position:absolute; inset:0; overflow:auto; padding:.75rem; display:block; }
        .m { width:fit-content; max-width:85%; padding:.5rem .75rem; margin:.25rem 0;
             border-radius:.75rem; white-space:pre-wrap; word-break:break-word;
             transition:margin .12s linear; }
        /* Ueberdeckt eine Blase das Gesicht, weicht sie ihm aus: sie wird
           schmaler und bricht um. Das ist die Rechnung hinter „der Text
           fliesst darum herum" -- CSS kann das ohne Float nicht. */
        .m.weicht-rechts { margin-right: var(--frei, 126px); }
        .m.weicht-links { margin-left: var(--frei, 126px); }
        .ich { margin-left:auto; background:#2f4a8a; }
        .sie { margin-right:auto; background:#2b2f3b; }
        .sys { margin:.25rem auto; color:#8a90a2; font-size:.85rem; }
        .tuer { display:block; font-size:.7rem; opacity:.6; }
        /* Griff über der Eingabe (Auftrag smilez, 15.11.: „den prompt Bereich
           manipulierbar, dynamisch nach oben vergrösserbar machen"). Ziehen
           nach oben macht die Eingabe höher, der Verlauf gibt den Platz ab. */
        #griff { height:12px; border-top:1px solid #2b2f3b; cursor:ns-resize;
                 touch-action:none; background:transparent; }
        #griff::after { content:""; display:block; width:3rem; height:3px; margin:4px auto 0;
                        border-radius:2px; background:#3d4354; }
        #griff:hover::after, #griff:active::after { background:#7aa2ff; }
        form { display:flex; gap:.5rem; padding:.5rem; border-top:1px solid #2b2f3b; }
        textarea { flex:1; resize:none; padding:.5rem; border-radius:.5rem; border:1px solid #2b2f3b;
                   background:#1c1f28; color:#e6e8ee; font:inherit; min-height:2.6rem;
                   max-height:60vh; overflow:auto; }
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
        <label title="Gesicht im Chat zeigen (verschiebbar)"><input type="checkbox" id="gesicht"> Gesicht</label>
      </div>
      <div id="flaeche">
        <div id="liste"></div>
        <div id="buehne"></div>
      </div>
      <div id="denkt"></div>
      <div id="griff" title="Ziehen: Eingabe höher"></div>
      <form><textarea id="eingabe" rows="2" placeholder="Nachricht"></textarea><button type="submit">Senden</button></form>`;
    this.liste = this.shadowRoot.getElementById("liste");
    this.buehne = this.shadowRoot.getElementById("buehne");
    this.denkt = this.shadowRoot.getElementById("denkt");
    this.wahl = this.shadowRoot.getElementById("wahl");
    this.aWahl = this.shadowRoot.getElementById("a-wahl");
    this.mWahl = this.shadowRoot.getElementById("m-wahl");
    this.dWahl = this.shadowRoot.getElementById("d-wahl");
    this.auswahlDaten = [];
    this.aWahl.addEventListener("change", () => { this.modelleZeigen(); this.wahlMerken(); });
    this.mWahl.addEventListener("change", () => { this.denkenZeigen(); this.wahlMerken(); });
    this.dWahl.addEventListener("change", () => this.wahlMerken());
    // Gesicht im Chat (DESIGN, Regel „Anzeigespiegel"). Die Wahl ist eine
    // Ansichtseinstellung je Geraet, keine Geraeteeinstellung -- deshalb im
    // Browser gemerkt und nicht in einer Gateway-Ablage.
    this.gesichtWahl = this.shadowRoot.getElementById("gesicht");
    this.gesichtWahl.checked = this.gesichtGemocht();
    this.gesichtWahl.addEventListener("change", () => this.gesichtSetzen(this.gesichtWahl.checked));
    if (this.gesichtWahl.checked) this.gesichtSetzen(true);
    this.shadowRoot.querySelector("form").addEventListener("submit", (e) => { e.preventDefault(); this.senden(); });
    this.shadowRoot.getElementById("eingabe").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this.senden(); }
    });
    this.wahl.addEventListener("change", () => this.sitzungWechseln());
    this.eingabeEinrichten();
    // Beim Hochscrollen rueckwaerts nachladen (Nutzerbefund 14.11.: nach
    // einem Neuladen war der Verlauf weg).
    this.liste.addEventListener("scroll", () => {
      if (this.liste.scrollTop < 80) this.aeterLaden();
      this.umflussSpaeter();
    });
    // Ein Zug am Gesicht aendert, welche Blasen ihm ausweichen muessen.
    this.shadowRoot.addEventListener("anzeige-bewegt", () => this.umflussSpaeter());
    if (window.ResizeObserver) {
      new ResizeObserver(() => this.umflussSpaeter()).observe(this.liste);
    }
    this.sitzungenLaden();
    this.auswahlLaden();
    this.hoeren();
  }
  disconnectedCallback() { this.laeuft = false; }

  /// Ist das Gesicht eingeschaltet? Vorgabe: an -- wer die Oberflaeche
  /// oeffnet, will sehen, was das Geraet gerade zeigt.
  gesichtGemocht() {
    try { return localStorage.getItem("chimera.gesicht") !== "0"; } catch (_) { return true; }
  }

  /// Das Gesicht ein- oder aushaengen.
  ///
  /// Das Element kommt aus dem Modul `anzeige` (eigenes Modul, eigenes Recht).
  /// Ein Reiter, den niemand geoeffnet hat, hat dessen Skript nicht geladen --
  /// der Chat holt es bei Bedarf nach. Ausgehaengt wird ueber `remove`; der
  /// Zaehler im Element endet mit `disconnectedCallback`.
  async gesichtSetzen(an) {
    try { localStorage.setItem("chimera.gesicht", an ? "1" : "0"); } catch (_) {}
    if (!an) {
      if (this.gesicht) { this.gesicht.remove(); this.gesicht = null; }
      return;
    }
    if (!customElements.get("chimera-anzeige")) {
      await new Promise((ok, nein) => {
        const s = document.createElement("script");
        s.src = "/module/anzeige/anzeige.js";
        s.onload = ok;
        s.onerror = () => nein(new Error("Anzeige-Modul nicht ladbar"));
        document.head.appendChild(s);
      }).catch((e) => this.blase("sys", `Gesicht: ${e.message}`));
    }
    if (!customElements.get("chimera-anzeige")) return;
    if (this.gesicht) return;
    const el = document.createElement("chimera-anzeige");
    el.setAttribute("schwebend", "");
    el.style.setProperty("--breite", "110px");
    // In die Buehne, NICHT in den Verlauf: sonst scrollt es mit.
    this.buehne.appendChild(el);
    this.gesicht = el;
    this.umflussSpaeter();
  }

  /// Den Umfluss gebündelt anstoßen (je Anzeigebild, nicht je Ereignis).
  umflussSpaeter() {
    if (this._umflussGeplant) return;
    this._umflussGeplant = true;
    const lauf = () => { this._umflussGeplant = false; this.umfluss(); };
    if (window.requestAnimationFrame) requestAnimationFrame(lauf);
    else setTimeout(lauf, 16);
  }

  /// Welche Blasen muss das Gesicht ausweichen lassen?
  ///
  /// Ein `float` scheidet aus (er scrollt mit), `position: fixed` scheidet
  /// aus (der Text liefe darunter durch). Also wird gemessen: liegt eine
  /// Blase im Rechteck des Gesichts, bekommt sie auf dessen Seite einen Rand
  /// in seiner Breite und bricht um (DESIGN, Regel „Anzeigespiegel").
  umfluss() {
    const g = this.gesicht;
    if (!g) {
      for (const el of this.liste.querySelectorAll(".m")) {
        el.classList.remove("weicht-rechts", "weicht-links");
      }
      return;
    }
    const gr = g.getBoundingClientRect();
    const lr = this.liste.getBoundingClientRect();
    const breite = g.offsetWidth || 110;
    const abstand = 16;                       // Luft zwischen Blase und Gesicht
    this.liste.style.setProperty("--frei", `${breite + abstand}px`);
    // Rechts, wenn die Mitte des Gesichts rechts der Mitte des Verlaufs liegt.
    const rechts = (gr.left + gr.width / 2) > (lr.left + lr.width / 2);
    // Nur das sichtbare Band messen: was ausserhalb liegt, kann nicht
    // ueberdeckt sein, und eine Messung weniger ist eine Messung weniger.
    const oben = lr.top - 40;
    const unten = lr.bottom + 40;
    for (const el of this.liste.children) {
      if (!el.classList || !el.classList.contains("m")) continue;
      const r = el.getBoundingClientRect();
      if (r.bottom < oben || r.top > unten) {
        el.classList.remove("weicht-rechts", "weicht-links");
        continue;
      }
      const ueberlappt = ChimeraChat.weichtAus(
        { oben: r.top, unten: r.bottom, links: r.left, rechts: r.right },
        { oben: gr.top, unten: gr.bottom, links: gr.left, rechts: gr.right },
        rechts);
      el.classList.toggle(rechts ? "weicht-rechts" : "weicht-links", ueberlappt);
      el.classList.remove(rechts ? "weicht-links" : "weicht-rechts");
    }
  }

  blase(klasse, text, tuer) {
    const d = document.createElement("div");
    d.className = "m " + klasse;
    if (tuer) { const t = document.createElement("span"); t.className = "tuer"; t.textContent = tuer; d.appendChild(t); }
    d.appendChild(document.createTextNode(text));
    this.liste.appendChild(d);
    this.liste.scrollTop = this.liste.scrollHeight;
    this.umflussSpaeter();
    return d;
  }

  /// Eingabe ziehbar und mitwachsend (Auftrag smilez, 15.11.2026: „den prompt
  /// Bereich manipulierbar, dynamisch nach oben vergrösserbar machen").
  ///
  /// Zwei Wege, ein Wert: Der Griff über dem Kasten setzt `eingabeFest` per
  /// Ziehen, der Text zieht die Höhe bei Bedarf darüber (`eingabeHoehe`). Der
  /// gemerkte Wert liegt im Browser — das ist eine Ansichtssache dieses
  /// Geräts, keine Geräteeinstellung wie Helligkeit oder Lautstärke.
  eingabeEinrichten() {
    this.eingabe = this.shadowRoot.getElementById("eingabe");
    this.griff = this.shadowRoot.getElementById("griff");
    this.eingabeFest = this.hoeheLesen();
    this.eingabeNachziehen();
    this.eingabe.addEventListener("input", () => this.eingabeNachziehen());
    this.griff.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const start = e.clientY;
      const von = this.eingabe.offsetHeight || EINGABE_MIN;
      try { this.griff.setPointerCapture(e.pointerId); } catch (_) { /* ohne ist es auch bedienbar */ }
      const bewegen = (ev) => {
        this.eingabeFest = griffHoehe(von, ev.clientY - start, EINGABE_MIN, this.eingabeHoechst());
        this.eingabe.style.height = `${this.eingabeFest}px`;
      };
      const ende = () => {
        this.griff.removeEventListener("pointermove", bewegen);
        this.griff.removeEventListener("pointerup", ende);
        this.griff.removeEventListener("pointercancel", ende);
        this.hoeheMerken();
      };
      this.griff.addEventListener("pointermove", bewegen);
      this.griff.addEventListener("pointerup", ende);
      this.griff.addEventListener("pointercancel", ende);
    });
  }

  /// Höchstens 60 % des Fensters: Der Verlauf muss sichtbar bleiben — eine
  /// Eingabe, die alles einnimmt, ist kein Chatfenster mehr.
  eingabeHoechst() {
    return Math.max(EINGABE_MIN, Math.round((window.innerHeight || 600) * 0.6));
  }

  /// Höhe an den Inhalt anpassen, ohne unter die gezogene Höhe zu gehen.
  eingabeNachziehen() {
    if (!this.eingabe) return;
    this.eingabe.style.height = "auto";
    const inhalt = this.eingabe.scrollHeight || 0;
    this.eingabe.style.height = `${eingabeHoehe(this.eingabeFest, inhalt, this.eingabeHoechst())}px`;
  }

  hoeheLesen() {
    try {
      const roh = Number(localStorage.getItem(EINGABE_SCHLUESSEL) || 0);
      // Eine gemerkte Höhe aus einem großen Fenster darf ein kleines nicht
      // sprengen — deshalb gegen die aktuelle Grenze begrenzen.
      return roh > 0 ? griffHoehe(roh, 0, EINGABE_MIN, this.eingabeHoechst()) : EINGABE_MIN;
    } catch (_) {
      return EINGABE_MIN;
    }
  }

  hoeheMerken() {
    try { localStorage.setItem(EINGABE_SCHLUESSEL, String(this.eingabeFest)); } catch (_) { /* egal */ }
  }

  async senden() {
    const feld = this.shadowRoot.getElementById("eingabe");
    const text = feld.value.trim();
    if (!text || this.schreibgeschuetzt) return;
    feld.value = "";
    // Auf die eingestellte Höhe zurück: Ein geleerter Kasten, der 12 Zeilen
    // hoch bleibt, nimmt dem Verlauf den Platz weg (smilez, 15.11.).
    this.eingabeNachziehen();
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
        this.umflussSpaeter();
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
    // Die Wahl gehoert der Sitzung (wahl.json): beim Oeffnen zeigen, was gilt.
    this.wahlZeigen(r.wahl);
  }

  /// Die gespeicherte Wahl in die drei Felder setzen. Rein lesend -- ohne
  /// `wahlMerken`, damit das Laden nichts schreibt.
  wahlZeigen(wahl) {
    if (!wahl) return;
    if (wahl.anbieter && this.auswahlDaten.some((a) => a.id === wahl.anbieter)) {
      this.aWahl.value = wahl.anbieter;
      this.modelleZeigen();
      if (wahl.modell) {
        const da = [...this.mWahl.options].some((o) => o.value === wahl.modell && !o.disabled);
        if (da) { this.mWahl.value = wahl.modell; this.denkenZeigen(); }
      }
      if (wahl.denken) {
        const da = [...this.dWahl.options].some((o) => o.value === wahl.denken);
        if (da) this.dWahl.value = wahl.denken;
      }
    }
  }

  /// Die Wahl der Sitzung sagen. Leer heisst loeschen -- dann entscheidet
  /// wieder die Reihenfolge des Anbieters (5h).
  async wahlMerken() {
    const auftrag = {
      anbieter: this.aWahl.value || "",
      modell: this.mWahl.value || "",
      denken: this.dWahl.value || "",
    };
    const r = await window.chimera.api("/api/chat/wahl", { method: "POST", body: JSON.stringify(auftrag) });
    if (!r.ok) this.blase("sys", `Wahl nicht gespeichert: ${r.fehler || "ohne Grund"}`);
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
    this.gesicht = null;              // wurde mit entfernt
    this.geladen = 0;
    this.seit = 0;
    if (this.gesichtWahl && this.gesichtWahl.checked) this.gesichtSetzen(true);
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
// An der Klasse, damit der Node-Test sie ohne DOM erreicht.
ChimeraChat.weichtAus = weichtAus;
ChimeraChat.eingabeHoehe = eingabeHoehe;
ChimeraChat.griffHoehe = griffHoehe;
ChimeraChat.EINGABE_MIN = EINGABE_MIN;

customElements.define("chimera-chat", ChimeraChat);
