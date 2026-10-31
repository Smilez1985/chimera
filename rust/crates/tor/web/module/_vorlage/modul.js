"use strict";
// Modul "{{NAME}}" (Vorlage). Zeigt Text; Werte nur per textContent, nie als HTML.
// Der Rahmen stellt window.chimera.api(pfad, opt) bereit (Anmeldung und Schutzkopf inklusive).
class Chimera{{KLASSE}} extends HTMLElement {
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>:host{display:block;padding:1rem}</style><p id="t"></p>`;
    this.shadowRoot.getElementById("t").textContent = "{{TITEL_DE}}: noch leer.";
  }
}
customElements.define("chimera-{{NAME}}", Chimera{{KLASSE}});
