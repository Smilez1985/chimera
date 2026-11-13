"use strict";
// Modul Fernzugriff (DESIGN, Regel "Jedes Werkzeug bekommt nur seine Rechte",
// Abschnitt "Fernausfuehrung: ssh geht durch das Gateway, und nur so").
//
// Hier steht die Host-Tabelle: Adresse, Nutzer, Port, Schluesselname und die
// Rechte auf dem Ziel. Der Hostschluessel wird beim Anlegen einmal
// aufgenommen -- was hier steht, ist der Blob aus `ssh-keyscan`; den
// Fingerabdruck rechnet das Gateway und zeigt ihn an. Ein Vorschlag des
// Agenten steht als "unbestaetigt" und wirkt nicht, bis der Nutzer ihn hier
// mit Hostschluessel speichert.
class ChimeraSsh extends HTMLElement {
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
        .ja { color:#7be0a0; } .offen { color:#ffd989; }
        .fehler { color:#ff7a7a; }
        label.klein { display:block; margin-top:.4rem; }
        input, select, textarea { background:#1c1f28; color:#e6e8ee; border:1px solid #2b2f3b; border-radius:.4rem; padding:.35rem; font:inherit; box-sizing:border-box; width:100%; margin:.2rem 0 .4rem; }
        textarea { min-height:3.2rem; font-family:ui-monospace, monospace; font-size:.8rem; }
        .reihung { display:grid; grid-template-columns:1fr 1fr; gap:.5rem; }
        button { background:#7aa2ff; color:#0b0d12; border:0; border-radius:.4rem; padding:.35rem .8rem; font:inherit; cursor:pointer; margin:.2rem .2rem 0 0; }
        button.stumm { background:#2b2f3b; color:#e6e8ee; }
        button.gefahr { background:#ff7a7a; }
        code { font-family:ui-monospace, monospace; font-size:.8rem; word-break:break-all; }
      </style>
      <h3>Fernzugriff</h3>
      <p class="klein">Diese Tabelle ist die einzige Wahrheit darüber, welche Hosts es gibt. Die
      Schlüsseldateien liegen beim Ausführer (das Gateway hat Netz und keinen Schlüssel, der
      Ausführer Schlüssel und kein Netz). Ein Host ohne bestätigten Hostschlüssel wirkt nicht —
      auch kein Vorschlag des Agenten.</p>
      <div id="liste"></div>
      <div class="karte">
        <h4>Host eintragen oder ändern</h4>
        <div class="reihung">
          <div><label class="klein">Name (Bezeichner)</label><input id="name" placeholder="radxa"></div>
          <div><label class="klein">Adresse</label><input id="adresse" placeholder="192.0.2.10 oder host.example"></div>
          <div><label class="klein">Nutzer</label><input id="nutzer" placeholder="dietpi"></div>
          <div><label class="klein">Port</label><input id="port" value="22"></div>
          <div><label class="klein">Schlüsselname (im Schlüsselordner des Ausführers)</label><input id="schluessel" placeholder="radxa_ed25519"></div>
          <div><label class="klein">Rechte auf dem Ziel</label>
            <select id="rechte">
              <option value="zaun">zaun — freie Befehle, aber keine Weiterleitung/kein PTY (restrict, Vorgabe)</option>
              <option value="force">force — nur die vorgesehenen Befehle; verlangt ein Skript auf dem Ziel</option>
              <option value="voll">voll — der Schlüssel darf, was der Zielnutzer darf (wie ssh-copy-id)</option>
            </select>
          </div>
        </div>
        <label class="klein"><input type="checkbox" id="aufnahme" style="width:auto;margin-right:.4rem">
          zur Aufnahme anlegen — der Hostschlüssel wird beim ersten Verbinden geholt und hier bestätigt</label>
        <label class="klein">Hostschlüssel — Zeile aus <code>ssh-keyscan -t ed25519 &lt;adresse&gt;</code>
          (nur beim ersten Mal oder wenn Adresse/Port sich ändern; bei „zur Aufnahme" leer lassen)</label>
        <textarea id="hostschluessel" placeholder="host.example ssh-ed25519 AAAAC3NzaC1lZDI1NTE5..."></textarea>
        <label class="klein">Notiz</label><input id="notiz" placeholder="optional">
        <button id="speichern">Speichern</button>
        <p id="meldung" class="fehler"></p>
      </div>`;
    this.$ = (id) => this.shadowRoot.getElementById(id);
    this.$("speichern").onclick = () => this.speichern();
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

  melden(text, fehler) {
    const m = this.$("meldung");
    m.className = fehler ? "fehler" : "klein";
    m.textContent = text || "";
  }

  // "host ssh-ed25519 AAAA..." -> {typ, schluessel}. Auch die Form mit
  // Klammernport ("[host]:2222 ...") wird angenommen.
  zerlegen(text) {
    const teile = (text || "").trim().split(/\s+/).filter((x) => x.length);
    if (teile.length < 3) return null;
    const typ = teile.find((t) => /^(ssh-|ecdsa-sha2-)/.test(t));
    if (!typ) return null;
    const i = teile.indexOf(typ);
    return { typ, schluessel: teile[i + 1] };
  }

  async laden() {
    const liste = this.$("liste");
    const r = await window.chimera.api("/api/ssh/lesen");
    liste.replaceChildren();
    if (!r.ok) {
      liste.appendChild(this.el("p", "Fehler: " + (r.fehler && r.fehler.text || r.fehler || "nicht erreichbar"), "fehler"));
      return;
    }
    const hosts = r.hosts || {};
    const namen = Object.keys(hosts).sort();
    if (!namen.length) {
      liste.appendChild(this.el("p", "Noch kein Host eingetragen.", "klein"));
      return;
    }
    for (const name of namen) liste.appendChild(this.karte(name, hosts[name]));
  }

  karte(name, e) {
    const k = this.el("div", undefined, "karte");
    const kopf = this.el("div", undefined, "kopf");
    kopf.append(
      this.el("strong", name),
      this.el("span", e.brauchbar ? "bestätigt" : "unbestätigt — wirkt nicht", e.brauchbar ? "ja" : "offen")
    );
    k.append(kopf);
    k.append(this.el("p", `${e.nutzer}@${e.adresse}:${e.port} · Schlüssel ${e.schluessel || "—"} · Rechte ${e.rechte}` + (e.herkunft === "vorschlag" ? " · Vorschlag des Agenten" : ""), "klein"));
    if (e.hostschluessel && e.hostschluessel.fingerabdruck) {
      k.append(this.el("p", `Hostschlüssel ${e.hostschluessel.typ} ${e.hostschluessel.fingerabdruck}`, "klein"));
    }
    if (e.notiz) k.append(this.el("p", e.notiz, "klein"));

    // Passwort für die Aufnahme: es geht **nur hier** hinein — nie in den
    // Chat. Angezeigt wird nur, ob eines hinterlegt ist; der Wert kommt
    // nirgends zurück.
    const pwZeile = this.el("div");
    const pwMeldung = this.el("p", "", "klein");
    const zeige = (da) => {
      pwZeile.replaceChildren();
      if (da) {
        pwZeile.append(this.el("span", "Passwort hinterlegt (0600, nur das Gateway). ", "klein"));
        const weg = this.el("button", "Passwort löschen", "stumm");
        weg.onclick = async () => {
          const r = await this.post("/api/ssh/geheim-loeschen", { host: name });
          if (!r.ok) { pwMeldung.className = "fehler"; pwMeldung.textContent = (r.fehler && r.fehler.text) || "Fehler"; return; }
          this.laden();
        };
        pwZeile.append(weg);
      } else {
        const feld = this.el("input");
        feld.type = "password";
        feld.autocomplete = "new-password";
        feld.placeholder = "Passwort für die erste Verbindung (wird nicht angezeigt)";
        const knopf = this.el("button", "Passwort hinterlegen", "stumm");
        knopf.onclick = async () => {
          if (!feld.value) { pwMeldung.className = "fehler"; pwMeldung.textContent = "Das Feld ist leer."; return; }
          const r = await this.post("/api/ssh/geheim", { host: name, passwort: feld.value });
          feld.value = "";
          if (!r.ok) { pwMeldung.className = "fehler"; pwMeldung.textContent = (r.fehler && r.fehler.text) || "Fehler"; return; }
          // Neu laden, nicht nur die Zeile tauschen: der Aufnahme-Knopf
          // haengt an e.geheim und entsteht nur beim Neuaufbau der Karte.
          this.laden();
        };
        pwZeile.append(feld, knopf);
      }
      pwZeile.append(pwMeldung);
    };
    zeige(!!e.geheim);
    k.append(pwZeile);

    // Die Aufnahme: Passwort-Anmeldung, Schluessel erzeugen, **eine** Zeile
    // aufs Ziel. Danach steht der Eintrag noch nicht -- der Fingerabdruck
    // wird hier angezeigt und muss bestaetigt werden.
    if (e.geheim && !e.brauchbar) {
      const auf = this.el("button", "Jetzt aufnehmen");
      const erg = this.el("div", undefined, "klein");
      auf.onclick = async () => {
        auf.disabled = true;
        erg.className = "klein";
        erg.textContent = "läuft … (Passwort-Anmeldung, Schlüssel eintragen)";
        const r = await this.post("/api/ssh/aufnahme", { host: name });
        auf.disabled = false;
        if (!r.ok) {
          erg.className = "fehler";
          erg.textContent = (r.fehler && r.fehler.text) || r.fehler || "Fehler";
          return;
        }
        erg.className = "klein";
        erg.replaceChildren();
        erg.append(
          this.el("p", `Hostschlüssel ${r.hostschluessel.typ} ${r.hostschluessel.fingerabdruck}`, "offen"),
          this.el("p", "Öffentlicher Schlüssel auf dem Ziel: " + r.zeile, "klein"),
          this.el("p", "Stimmt der Fingerabdruck? Dann bestätigen — vorher wirkt der Eintrag nicht.", "klein")
        );
        const ja = this.el("button", "Eintrag bestätigen");
        ja.onclick = async () => {
          const w = { adresse: e.adresse, nutzer: e.nutzer, port: e.port, schluessel: e.schluessel,
                      rechte: e.rechte, hostschluessel: r.hostschluessel };
          const b = await this.post("/api/ssh/setzen", { host: name, wert: w });
          if (!b.ok) { erg.className = "fehler"; erg.textContent = (b.fehler && b.fehler.text) || "Fehler"; return; }
          erg.className = "klein";
          erg.textContent = "Bestätigt.";
          this.laden();
        };
        erg.append(ja);
      };
      k.append(this.el("p", "Passwort liegt vor — Aufnahme möglich.", "klein"));
      k.append(auf, erg);
    } else if (e.geheim && e.brauchbar) {
      k.append(this.el("p", "Passwort liegt noch vor, obwohl der Host bestätigt ist — kannst du löschen.", "klein"));
    }

    const aendern = this.el("button", "In das Formular", "stumm");
    aendern.onclick = () => {
      this.$("name").value = name;
      this.$("adresse").value = e.adresse || "";
      this.$("nutzer").value = e.nutzer || "";
      this.$("port").value = e.port || 22;
      this.$("schluessel").value = e.schluessel || "";
      this.$("rechte").value = e.rechte || "zaun";
      this.$("notiz").value = e.notiz || "";
      this.$("hostschluessel").value = "";
      this.melden(e.brauchbar ? "Zum Ändern: Felder prüfen, dann speichern. Der Hostschlüssel bleibt, solange Adresse und Port gleich bleiben." : "Zum Bestätigen: Hostschlüssel einfügen (ssh-keyscan) und speichern.", false);
    };
    const weg = this.el("button", "Löschen", "gefahr");
    weg.onclick = async () => {
      if (!confirm(`Host "${name}" löschen?`)) return;
      const r = await this.post("/api/ssh/loeschen", { host: name });
      if (!r.ok) { this.melden((r.fehler && r.fehler.text) || r.fehler || "Fehler", true); return; }
      this.melden(`"${name}" gelöscht.`, false);
      this.laden();
    };
    k.append(aendern, weg);
    return k;
  }

  async speichern() {
    const wert = {
      adresse: this.$("adresse").value.trim(),
      nutzer: this.$("nutzer").value.trim(),
      port: Number(this.$("port").value || 22),
      schluessel: this.$("schluessel").value.trim(),
      rechte: this.$("rechte").value,
      notiz: this.$("notiz").value.trim(),
    };
    const aufnahme = this.$("aufnahme").checked;
    if (aufnahme) wert.aufnahme = true;
    const roh = this.$("hostschluessel").value.trim();
    if (roh) {
      const h = this.zerlegen(roh);
      if (!h) { this.melden("Der Hostschlüssel ist keine Zeile aus ssh-keyscan (Typ und Blob fehlen).", true); return; }
      wert.hostschluessel = h;
    }
    const name = this.$("name").value.trim();
    if (!name) { this.melden("Der Host braucht einen Namen.", true); return; }
    this.melden("speichert …", false);
    const r = await this.post("/api/ssh/setzen", { host: name, wert });
    if (!r.ok) { this.melden((r.fehler && r.fehler.text) || r.fehler || "Fehler", true); return; }
    const fp = r.eintrag && r.eintrag.hostschluessel && r.eintrag.hostschluessel.fingerabdruck;
    this.melden(`"${name}" gespeichert${fp ? " · Fingerabdruck " + fp : ""}.`, false);
    this.$("hostschluessel").value = "";
    this.laden();
  }
}
customElements.define("chimera-ssh", ChimeraSsh);
