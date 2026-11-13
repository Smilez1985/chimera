// Prüft die Anzeige des Freigaben-Moduls ohne Browser.
//
// Warum ohne Browser: `freigaben.js` ist eine Web-Komponente, aber die
// Rechnung "seit wann offen" und "wie viel Zeit ist das" ist reine
// Arithmetik. Sie wird hier aus der ECHTEN Datei geladen (nicht nachgebaut) —
// ein Test, der die Formel wiederholt, besteht auch mit der kaputten Anzeige.
//
// **Kein Ablauf mehr (13.11.2026):** Geprüft wird nicht mehr "läuft ab in …",
// sondern "seit wann offen" plus der Erinnerungsabstand. Eine Frist gibt es
// nicht; ein `bis` aus dem Altbestand darf nur nicht auf einmal aufgehen.
//
// Aufruf: node tests/js/freigaben_anzeige.mjs   (rc 0 = alles gut)

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
if (typeof probe.seitText !== "function") {
  console.log("  FAIL  seitText fehlt (umbenannt?)");
  process.exit(1);
}
if (typeof probe.dauerText === "function") {
  console.log("  FAIL  dauerText gibt es noch -- eine Frist darf es im Modul nicht mehr geben");
  process.exit(1);
}

let pass = 0;
let fail = 0;

function check(name, seit, jetzt, soll) {
  const ist = probe.seitText(seit, jetzt);
  if (ist === soll) {
    pass += 1;
    console.log(`  ok    ${name} -> ${ist}`);
  } else {
    fail += 1;
    console.log(`  FAIL  ${name} -- erwartet "${soll}", bekam "${ist}"`);
  }
}

const J = 1_700_000_000;

// Ohne Zeitpunkt: nicht "abgelaufen", sondern ehrlich "unbekannt".
check("ohne seit", null, J, "seit unbekannt");
check("seit 0 gilt als unbekannt", 0, J, "seit unbekannt");

// Gerade geöffnet.
check("gerade geöffnet", J, J, "seit 0 s");
// Eine Uhr, die dem Server nachläuft, erfindet keine negative Zeit.
check("seit liegt in der Zukunft", J + 5, J, "seit 0 s");

// Sekunden unter 90 -- wer gerade freigegeben hat, soll die Sekunden sehen.
check("1 s offen", J - 1, J, "seit 1 s");
check("89 s offen", J - 89, J, "seit 89 s");
// Ab 90 s in Minuten (gerundet).
check("90 s offen", J - 90, J, "seit 2 min");
check("60 s offen bleibt in Sekunden", J - 60, J, "seit 60 s");
check("5399 s offen", J - 5399, J, "seit 90 min");

// Ab 5400 s (1,5 h) in Stunden; darunter bleibt Minuten die genauere Auskunft.
check("5400 s offen", J - 5400, J, "seit 2 h");
check("1 h offen bleibt in Minuten", J - 3600, J, "seit 60 min");
check("172799 s offen", J - 172799, J, "seit 48 h");

// Ab 172800 s (2 Tage) in Tagen.
check("2 Tage offen", J - 172800, J, "seit 2 Tagen");
check("7 Tage offen", J - 604800, J, "seit 7 Tagen");

// --- Anzeige, nicht nur Rechnung ------------------------------------------
// Wer `seitText` prueft, aber nicht, dass `karte` ihn benutzt, merkt nicht,
// wenn die Karte die Dauer gar nicht mehr zeigt.
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

function karteOhne(name, eintrag, jetzt, verboten) {
  const texte = sammleText(probe.karte("ssh", eintrag, jetzt), []);
  const treffer = texte.find((t) => t.includes(verboten));
  if (!treffer) {
    pass += 1;
    console.log(`  ok    ${name} -> kein "${verboten}"`);
  } else {
    fail += 1;
    console.log(`  FAIL  ${name} -- "${verboten}" steht noch in der Karte: "${treffer}"`);
  }
}

// Offen: Zustand und "seit wann" stehen zusammen im Kopf.
kartePruefen("Karte zeigt seit wann", { modus: "offen", seit: J - 3600 }, J, "offen — seit 60 min");
// Ohne `seit` (Altbestand): lesbar, ohne erfundene Zeit.
kartePruefen("Karte ohne seit sagt unbekannt", { modus: "offen" }, J, "seit unbekannt");
// Positivliste: keine Dauer, sondern der Modus.
kartePruefen("Karte ohne Freigabe fragt einzeln", { modus: "positivliste" }, J, "fragt einzeln");
// Ein `bis` aus dem Altbestand in der Vergangenheit gilt nicht mehr als offen.
kartePruefen("Altbestand mit alter Frist fragt einzeln", { modus: "offen", bis: J - 5 }, J, "fragt einzeln");
// Und eine Frist in der Zukunft (Altbestand, noch nicht vorbei) schon.
kartePruefen("Altbestand mit laufender Frist ist offen", { modus: "offen", bis: J + 600 }, J, "offen — seit unbekannt");

// Keine Frist mehr im Text: weder "läuft ab" noch eine Dauerwahl.
karteOhne("Karte nennt keinen Ablauf", { modus: "offen", seit: J - 60 }, J, "läuft ab");
karteOhne("Karte bietet keine Dauer mehr an", { modus: "offen", seit: J - 60 }, J, "für immer");

console.log(`\nErgebnis: ${pass} ok, ${fail} FAIL`);
process.exit(fail === 0 ? 0 : 1);
