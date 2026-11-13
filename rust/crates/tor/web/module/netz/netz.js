"use strict";
// Modul Netz (DESIGN, Regel "Tailscale -- gelesen, nicht gesteuert").
//
// Zeigt den Zustand des Tailnets und schaltet es an oder aus. Was hier
// sichtbar ist, kommt allein vom Gateway (`op: tailscale`); geschaltet wird
// ueber `tailscale_steuern`, und das haengt an der Freigabe `tailscale` --
// die Antwort nennt den Grund, wenn sie fehlt. Werte nur per textContent.
class ChimeraNetz extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:1rem; }
        h3 { margin:.2rem 0 .5rem; }
        .karte { border:1px solid #2b2f3b; border-radius:.6rem; padding:.75rem; margin:.75rem 0; background:#1c1f28; }
        .klein { color:#8a90a2; font-size:.85rem; }
        .ja { color:#7be0a0; } .warn { color:#ffd989; } .fehler { color:#ff7a7a; }
        button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem; padding:.4rem .9rem; font:inherit; cursor:pointer; margin:.3rem .3rem 0 0; }
        button.stumm { background:#2b2f3b; color:#e6e8ee; }
        button:disabled { opacity:.5; cursor:default; }
        code { font-family:ui-monospace, monospace; font-size:.8rem; }
      </style>
      <h3>Netz</h3>
      <div id="tailnet" class="karte"></div>`;
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
    const k = this.$("tailnet");
    const r = await window.chimera.api("/api/netz/tailscale");
    k.replaceChildren();
    k.append(this.el("strong", "Tailnet"));

    if (!r.ok) {
      k.append(this.el("p", "Fehler: " + ((r.fehler && r.fehler.text) || r.fehler || "nicht erreichbar"), "fehler"));
      return;
    }
    if (!r.eingerichtet) {
      k.append(this.el("p", "nicht eingerichtet (tailscaled läuft hier nicht)", "klein"));
      k.append(this.el("p", "Tailscale ist eine Zutat, die der Nutzer dazunimmt — Chimera startet es nicht.", "klein"));
      return;
    }

    const laeuft = r.zustand === "Running";
    k.append(this.el("p", `${r.zustand}${r.hostname ? " · " + r.hostname : ""}${(r.adressen && r.adressen[0]) ? " " + r.adressen[0] : ""}`, laeuft ? "ja" : "warn"));
    if (typeof r.peers_gesamt === "number") {
      k.append(this.el("p", `${r.peers_online} von ${r.peers_gesamt} Peers online`, "klein"));
    }

    const meldung = this.el("p", "", "klein");
    const schalte = async (aktion, knopf) => {
      knopf.disabled = true;
      meldung.className = "klein";
      meldung.textContent = "läuft …";
      const b = await this.post("/api/netz/steuern", { aktion });
      knopf.disabled = false;
      if (!b.ok) {
        meldung.className = "fehler";
        meldung.textContent = (b.fehler && b.fehler.text) || b.fehler || "Fehler";
        return;
      }
      this.laden();
    };

    const an = this.el("button", laeuft ? "Tailnet ausschalten" : "Tailnet einschalten");
    if (laeuft) an.className = "stumm";
    an.onclick = () => schalte(laeuft ? "aus" : "an", an);
    const neu = this.el("button", "Neu lesen", "stumm");
    neu.onclick = () => this.laden();
    k.append(an, neu, meldung);
    k.append(this.el("p", "Schalten hängt an der Freigabe „tailscale“ — ohne sie sagt die Antwort warum.", "klein"));
  }
}
customElements.define("chimera-netz", ChimeraNetz);
