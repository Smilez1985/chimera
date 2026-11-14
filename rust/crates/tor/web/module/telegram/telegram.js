"use strict";
// Modul "Telegram" (14.11.2026, Auftrag smilez: "im Dashboard fehlt die
// Moeglichkeit, den Bot-Token einzutragen").
//
// **So wenig tippen wie moeglich:** Der Nutzer gibt nur den Token von
// @BotFather ein. Alles andere holt das Gateway:
//   * den Bot-Namen ueber `getMe` (gleich beim Speichern, und der Token wird
//     nur abgelegt, wenn Telegram ihn annimmt),
//   * die Chat-Kennungen ueber `getUpdates` -- als Liste zum Ankreuzen,
//     nicht als Zahlenfeld.
// Die Server-Adresse (`api.telegram.org`) steht fest im Gateway; sie ist
// keine Einstellung, die ein Mensch falsch machen koennte.
//
// Der Token kommt **nie** zurueck: Das Modul zeigt "gesetzt" und den
// Bot-Namen, nicht den Wert. Ein neuer Token ersetzt den alten.
class ChimeraTelegram extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:1rem; }
        h3 { margin:.2rem 0 .5rem; }
        h4 { margin:0 0 .4rem; font-size:.95rem; }
        .karte { border:1px solid #2b2f3b; border-radius:.6rem; padding:.75rem; margin:.75rem 0; background:#1c1f28; }
        .klein { color:#8a90a2; font-size:.85rem; }
        .ja { color:#7be0a0; } .offen { color:#ffd989; } .fehler { color:#ff7a7a; }
        label.klein { display:block; margin-top:.4rem; }
        input { background:#1c1f28; color:#e6e8ee; border:1px solid #2b2f3b; border-radius:.4rem; padding:.35rem; font:inherit; box-sizing:border-box; width:100%; margin:.2rem 0 .4rem; }
        button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem; padding:.35rem .8rem; font:inherit; cursor:pointer; margin:.2rem .2rem 0 0; }
        button.stumm { background:#2b2f3b; color:#e6e8ee; }
        button.gefahr { background:#ff7a7a; }
        ul { list-style:none; padding:0; margin:.3rem 0; }
        li { padding:.25rem 0; border-bottom:1px solid #232733; }
        code { font-family:ui-monospace, monospace; font-size:.8rem; }
      </style>
      <h3>Telegram</h3>
      <p class="klein">Die Tür ins Gerät, wenn du nicht davorstehst. Ein Token von @BotFather
      genügt — Bot-Name und Chat-Kennungen holt das Gateway selbst von Telegram.
      Ohne angekreuzte Kennung bleibt die Tür zu (ein Agent mit Werkzeugen hinter einem
      offenen Chat wäre ein Fernzugang für jeden, der die Bot-Adresse kennt).</p>
      <div class="karte" id="stand"><span class="klein">Lade …</span></div>
      <div class="karte">
        <h4 id="titel">Bot-Token von @BotFather</h4>
        <p class="klein" id="hinweis">In Telegram: @BotFather → /newbot (oder /token bei einem bestehenden Bot).
        Der Token sieht so aus: <code>123456789:ABCdef…</code></p>
        <label class="klein">Token (wird geprüft und erst dann gespeichert)</label>
        <input id="token" type="password" autocomplete="off" spellcheck="false" placeholder="123456789:ABCdef…">
        <button id="speichern">Prüfen und speichern</button>
        <button id="weg" class="gefahr stumm">Eintrag löschen</button>
        <p class="klein" id="meldung"></p>
      </div>
      <div class="karte">
        <h4>Wer darf schreiben?</h4>
        <p class="klein">Schreib dem Bot in Telegram eine Nachricht („hallo" genügt), dann
        aktualisiere hier — das Gateway liest die Absender bei Telegram und du kreuzt an.</p>
        <button id="holen" class="stumm">Absender von Telegram holen</button>
        <ul id="absender"></ul>
        <button id="erlaubt">Auswahl speichern</button>
        <p class="klein" id="meldung2"></p>
      </div>`;
    this.api = (window.chimera && window.chimera.api) ? window.chimera.api.bind(window.chimera) : null;
    this.shadowRoot.getElementById("speichern").addEventListener("click", () => this._token());
    this.shadowRoot.getElementById("weg").addEventListener("click", () => this._loeschen());
    this.shadowRoot.getElementById("holen").addEventListener("click", () => this._absender());
    this.shadowRoot.getElementById("erlaubt").addEventListener("click", () => this._erlaubt());
    this._laden();
  }

  async post(pfad, koerper) {
    if (!this.api) throw new Error("keine Verbindung zum Gateway");
    return this.api(pfad, { method: "POST", koerper: koerper || {} });
  }

  async _laden() {
    const ziel = this.shadowRoot.getElementById("stand");
    try {
      const r = await this.api("/api/telegram/stand");
      const s = (r && r.stand) || {};
      const bot = s.bot || {};
      const gesetzt = s.token_gesetzt;
      const quelle = s.quelle === "ablage" ? "im Gerät abgelegt"
                   : s.quelle === "umgebung" ? "aus der .env (Altinstallation)"
                   : "kein Token";
      const liste = (s.erlaubt || []).join(", ") || "keine";
      ziel.innerHTML = `
        <div class="kopf"><strong>${gesetzt ? "eingerichtet" : "nicht eingerichtet"}</strong>
          <span class="klein">${quelle}</span></div>
        <p class="klein">Server: <code>${(s.server || "").replace(/^https?:\/\//, "")}</code>
        · erlaubt: <code>${liste}</code>${bot.username ? " · Bot: @" + bot.username : ""}</p>
        ${s.fehler ? `<p class="fehler">${s.fehler}</p>` : ""}`;
      if (!gesetzt) {
        ziel.querySelector(".kopf strong").className = "offen";
      }
    } catch (e) {
      ziel.innerHTML = `<p class="fehler">Nicht lesbar: ${e.message || e}</p>`;
    }
  }

  async _token() {
    const m = this.shadowRoot.getElementById("meldung");
    const feld = this.shadowRoot.getElementById("token");
    const token = (feld.value || "").trim();
    if (!token) { m.className = "klein fehler"; m.textContent = "Bitte den Token einfügen."; return; }
    m.className = "klein"; m.textContent = "Prüfe bei Telegram …";
    try {
      const r = await this.post("/api/telegram/token", { token });
      feld.value = "";
      const b = r.bot || {};
      m.className = "klein ja";
      m.textContent = `Angenommen: @${b.username || "?"}${b.name ? " (" + b.name + ")" : ""}.`
        + (r.neustart_noetig ? " Das Gateway startet die Tür beim nächsten Start — bis dahin bleibt sie zu." : "");
      this._laden();
    } catch (e) {
      m.className = "klein fehler";
      m.textContent = (e && e.message) || String(e);
    }
  }

  async _loeschen() {
    const m = this.shadowRoot.getElementById("meldung");
    try {
      await this.post("/api/telegram/loeschen", {});
      m.className = "klein offen";
      m.textContent = "Eintrag gelöscht. Die Tür ist beim nächsten Start zu.";
      this._laden();
    } catch (e) {
      m.className = "klein fehler";
      m.textContent = (e && e.message) || String(e);
    }
  }

  async _absender() {
    const m = this.shadowRoot.getElementById("meldung2");
    const liste = this.shadowRoot.getElementById("absender");
    m.className = "klein"; m.textContent = "Frage Telegram …";
    try {
      const r = await this.post("/api/telegram/absender", {});
      const leute = (r && r.absender) || [];
      liste.innerHTML = "";
      if (!leute.length) {
        m.className = "klein offen";
        m.textContent = "Keine Absender gefunden — schreib dem Bot zuerst in Telegram eine Nachricht.";
        return;
      }
      for (const e of leute) {
        const li = document.createElement("li");
        li.innerHTML = `<label><input type="checkbox" value="${e.id}"> `
          + `${e.name || "?"}${e.benutzer ? " (@" + e.benutzer + ")" : ""}`
          + ` <code>${e.id}</code> <span class="klein">${e.art}</span>`
          + `${e.text ? ` <span class="klein">„${e.text}"</span>` : ""}</label>`;
        liste.appendChild(li);
      }
      m.className = "klein";
      m.textContent = `${leute.length} Absender gefunden.`;
    } catch (e) {
      m.className = "klein fehler";
      m.textContent = (e && e.message) || String(e);
    }
  }

  async _erlaubt() {
    const m = this.shadowRoot.getElementById("meldung2");
    const ids = [...this.shadowRoot.querySelectorAll("#absender input:checked")]
      .map((x) => Number(x.value));
    if (!ids.length) {
      m.className = "klein offen";
      m.textContent = "Nichts ausgewählt — die Tür bliebe zu.";
      return;
    }
    try {
      const r = await this.post("/api/telegram/erlaubt", { ids });
      m.className = "klein ja";
      m.textContent = `Gespeichert: ${(r.erlaubt || []).join(", ")}.`
        + (r.neustart_noetig ? " Wirkt beim nächsten Start des Gateways." : "");
      this._laden();
    } catch (e) {
      m.className = "klein fehler";
      m.textContent = (e && e.message) || String(e);
    }
  }
}
customElements.define("chimera-telegram", ChimeraTelegram);
