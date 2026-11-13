// Prüft die Restzeit-Anzeige des Freigaben-Moduls ohne Browser.
//
// Warum ohne Browser: `freigaben.js` ist eine Web-Komponente, aber die
// Rechnung "läuft ab in …" ist reine Arithmetik. Sie wird hier aus der
// ECHTEN Datei geladen (nicht nachgebaut) — ein Test, der die Formel
// wiederholt, besteht auch mit der kaputten Anzeige.
//
// Aufruf: node tests/js/freigaben_restzeit.mjs   (rc 0 = alles gut)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const hier = path.dirname(fileURLToPath(import.meta.url));
// CHIMERA_FREIGABEN_JS laesst die Gegenprobe eine veraenderte Kopie pruefen,
// ohne die echte Datei anzufassen.
const quelle = process.env.CHIMERA_FREIGABEN_JS
  || path.resolve(hier, "../../rust/crates/tor/web/module/freigaben/freigaben.js");

let klasse = null;
globalThis.HTMLElement = class {
  attachShadow() {}
};
globalThis.customElements = {
  define: (name, k) => {
    if (klasse) throw new Error("mehr als eine Komponente definiert: " + name);
    klasse = k;
  },
};
// Minimaler Element-Ersatz: nur, was `el()`/`karte()` anfassen. Damit laesst
// sich auch pruefen, ob der Text wirklich IN DER KARTE landet -- die Rechnung
// allein zu pruefen waere zu wenig ("Anzeige").
function element(tag) {
  return {
    tagName: tag,
    className: "",
    textContent: "",
    value: "",
    placeholder: "",
    children: [],
    append(...teile) {
      for (const t of teile) this.children.push(typeof t === "string" ? { textContent: t } : t);
    },
    appendChild(t) {
      this.children.push(t);
      return t;
    },
  };
}
globalThis.document = { createElement: element };

new Function(fs.readFileSync(quelle, "utf8"))();

if (!klasse) {
  console.log("  FAIL  das Modul definiert keine Komponente");
  process.exit(1);
}
const probe = Object.create(klasse.prototype);
if (typeof probe.dauerText !== "function") {
  console.log("  FAIL  dauerText fehlt (umbenannt?)");
  process.exit(1);
}

let pass = 0;
let fail = 0;

function check(name, bis, jetzt, soll) {
  const ist = probe.dauerText(bis, jetzt);
  if (ist === soll) {
    pass += 1;
    console.log(`  ok    ${name} -> ${ist}`);
  } else {
    fail += 1;
    console.log(`  FAIL  ${name} -- erwartet "${soll}", bekam "${ist}"`);
  }
}

const J = 1_700_000_000;

// Unbefristet: kein Ende gesetzt (modus "offen" ohne bis).
check("ohne Ende", null, J, "unbefristet");
check("Ende 0 gilt als unbefristet", 0, J, "unbefristet");

// Abgelaufen: alles bei oder hinter jetzt.
check("genau jetzt", J, J, "abgelaufen");
check("eine Sekunde zu spät", J - 1, J, "abgelaufen");

// Sekunden unter 90 -- die Anzeige soll nicht auf Minuten runden, wenn
// jemand gerade "15 Minuten" freigegeben hat und zusieht.
check("1 s übrig", J + 1, J, "läuft ab in 1 s");
check("89 s übrig", J + 89, J, "läuft ab in 89 s");

// Ab 90 s in Minuten (gerundet). Die Grenze liegt bewusst bei 90 s: Wer eine
// Freigabe von zwei Minuten gibt, soll die Sekunden laufen sehen.
check("90 s übrig", J + 90, J, "läuft ab in 2 min");
check("60 s übrig bleibt in Sekunden", J + 60, J, "läuft ab in 60 s");
check("5399 s übrig", J + 5399, J, "läuft ab in 90 min");

// Ab 5400 s (1,5 h) in Stunden.
check("5400 s übrig", J + 5400, J, "läuft ab in 2 h");
// Bis 1,5 h bleibt es in Minuten -- "60 min" statt "1 h" ist gewollt:
// unter einer Stunde ist die Minutenangabe die genauere Auskunft.
check("3600 s übrig bleibt in Minuten", J + 3600, J, "läuft ab in 60 min");
check("172799 s übrig", J + 172799, J, "läuft ab in 48 h");

// Ab 172800 s (2 Tage) in Tagen.
check("2 Tage übrig", J + 172800, J, "läuft ab in 2 Tagen");
check("7 Tage übrig", J + 604800, J, "läuft ab in 7 Tagen");

// Die angebotenen Dauern müssen auch so angezeigt werden, wie sie dastehen:
// 15 min, 1 h, 4 h, 1 Tag, 7 Tage (aus der Auswahlliste im Modul).
check("Dauer 15 min", J + 900, J, "läuft ab in 15 min");
check("Dauer 1 h zeigt Minuten", J + 3600, J, "läuft ab in 60 min");
check("Dauer 4 h", J + 14400, J, "läuft ab in 4 h");
check("Dauer 1 Tag", J + 86400, J, "läuft ab in 24 h");
check("Dauer 7 Tage", J + 604800, J, "läuft ab in 7 Tagen");

// --- Anzeige, nicht nur Rechnung ------------------------------------------
// Wer `dauerText` prueft, aber nicht, dass `karte` ihn benutzt, merkt nicht,
// wenn die Karte die Restzeit gar nicht mehr zeigt.
function sammleText(knoten, ziel) {
  if (!knoten || typeof knoten !== "object") return ziel;
  if (typeof knoten.textContent === "string" && knoten.textContent) ziel.push(knoten.textContent);
  for (const k of knoten.children || []) sammleText(k, ziel);
  return ziel;
}

function kartePruefen(name, eintrag, jetzt, soll) {
  const karte = probe.karte("ssh", eintrag, jetzt);
  const texte = sammleText(karte, []);
  const treffer = texte.find((t) => t.includes(soll));
  if (treffer) {
    pass += 1;
    console.log(`  ok    ${name} -> "${treffer}"`);
  } else {
    fail += 1;
    console.log(`  FAIL  ${name} -- erwartet "${soll}", Karte zeigt ${JSON.stringify(texte.slice(0, 4))}`);
  }
}

// „offen" mit Ende: Zustand und Restzeit stehen zusammen im Kopf.
kartePruefen("Karte zeigt die Restzeit", { modus: "offen", bis: J + 3600 }, J, "läuft ab in 60 min");
// Ohne Ende: unbefristet.
kartePruefen("Karte nennt unbefristet", { modus: "offen", bis: null }, J, "unbefristet");
// Positivliste: keine Restzeit, sondern der Modus.
kartePruefen("Karte ohne Freigabe fragt einzeln", { modus: "positivliste" }, J, "fragt einzeln");
// Eine abgelaufene Freigabe wirkt nicht mehr offen. Die Karte zeigt dann
// wieder "fragt einzeln" -- sie sagt NICHT, dass etwas abgelaufen ist. Das ist
// die offene Entscheidung aus der ROADMAP (Ablauf melden oder still
// zurueckfallen); der Test haelt den heutigen Zustand fest, damit eine
// Aenderung daran auffaellt.
kartePruefen("abgelaufene Freigabe zeigt den Rueckfall", { modus: "offen", bis: J - 5 }, J, "fragt einzeln");

console.log(`\nErgebnis: ${pass} ok, ${fail} FAIL`);
process.exit(fail === 0 ? 0 : 1);
