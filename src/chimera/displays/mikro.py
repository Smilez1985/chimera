"""Welche Mikrofone einer Anzeige sind brauchbar? Messen statt annehmen.

Anlass (smilez, 11.10.2026): Am chimera-pi klirrt das linke Mikro der
Whisplay. "Nur rechts" fest einzubauen hiesse, einen Defekt dieses einen
Boards jedem aufzuzwingen, der das Repo zieht. Deshalb misst der Installer
(Modul 46) jedes Geraet selbst und entscheidet: ``beide``, ``links``,
``rechts`` oder ``keins``.

Messung: Der eigene Lautsprecher spielt Stufentoene, beide Mikros nehmen
gleichzeitig auf. Je Kanal und Ton werden Grundton und Oberwellen bestimmt.
Am chimera-pi (11.10.2026) trennte das klar: R klirrt 23-33 dB unter dem
Grundton, L 3 dB darueber; L war bis 3 kHz zudem 14-19 dB leiser. Die
Verzerrung stammt nicht vom Lautsprecher -- nach Abzug des Frequenzgangs
erzeugte L 16-24 dB mehr Oberwellen als R (Messskript
``shared/chimera/proben/mikro_analyse.py``).

Entscheidungsregeln (Schwellen als Konstanten, Gruende dabei):

* Kein Ton auf beiden Kanaelen -> ``keins``: Lautsprecher stumm ODER beide
  Mikros tot. Unterscheiden laesst sich das ohne zweite Quelle nicht, also
  wird beides genannt, statt zu raten.
* Ein Kanal ist untauglich, wenn er den Ton nicht hoert (mehr als
  ``STUMM_ABSTAND_DB`` unter dem anderen) oder wenn er klirrt
  (``KLIRR_GRENZE_DB``).
* Zweifel heisst ``beide`` mit Warnung, nie stilles Abschalten: Ein
  abgeschaltetes gutes Mikro faellt keinem auf, ein mitlaufendes schlechtes
  schon.

Die Auswertung (:func:`auswerten`) ist eine reine Funktion ueber Messwerte --
pruefbar ohne Geraet. :func:`messen` spielt und nimmt auf (``aplay``/``arecord``).
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = ["TOENE", "KanalWert", "Befund", "kanal_werte", "auswerten", "messen",
           "alsa_geraet", "main"]

ABTASTRATE = 48000
#: Stufentoene: im Sprachband, wo am chimera-pi der Unterschied lag. 4 kHz
#: und hoeher trennten dort nicht (beide Kanaele gleich).
TOENE: tuple[int, ...] = (1000, 2000, 3000)
TON_DAUER_S = 0.6
TON_PEGEL = 0.3            # Anteil Vollaussteuerung; am chimera-pi kein Clipping

#: Ein Ton, der weniger als 20 dB ueber dem Rauschen liegt, gilt als nicht
#: gehoert. Rauschen = Pegel des Kanals IN DER STILLE BEI DERSELBEN FREQUENZ
#: (gleiche Einzel-DFT wie der Grundton). Ein Breitband-RMS taugt nicht: Er
#: enthaelt Brummen und Lueftergeraeusch und lag am chimera-pi bei -32 dBFS --
#: der hoerbare, aber klirrende linke Kanal (-21 dBFS) galt damit als taub,
#: die Entscheidung stimmte zufaellig, der Grund nicht.
HOERBAR_UEBER_RAUSCHEN_DB = 20.0
#: Klirren: Summe der Oberwellen 2..5 relativ zum Grundton. Unter -10 dB ist
#: fuer Sprache unkritisch; gemessen R -23..-33, L +3 (chimera-pi).
KLIRR_GRENZE_DB = -10.0
#: Ein Kanal, der den Ton mehr als 20 dB leiser hoert als der andere, gilt
#: als stumm/abgedeckt. Gemessen L-R bis -19 dB -- L klirrte zusaetzlich,
#: der Pegel allein haette ihn NICHT ausgesondert. Das ist Absicht: Leiser
#: ist kein Defekt, solange er sauber ist (Verstaerkung gleicht aus).
STUMM_ABSTAND_DB = 20.0

@dataclass
class KanalWert:
    """Ein Kanal bei einem Ton."""
    ton_hz: int
    grundton_db: float          # dBFS
    klirr_db: float             # Oberwellen relativ zum Grundton
    rauschen_db: float          # dBFS in der Stille

    @property
    def gehoert(self) -> bool:
        return self.grundton_db - self.rauschen_db >= HOERBAR_UEBER_RAUSCHEN_DB

@dataclass
class Befund:
    entscheidung: str                       # beide | links | rechts | keins
    kanal: int | None                       # 0 = links, 1 = rechts, None = beide/keins
    gruende: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    werte: dict = field(default_factory=dict)   # {"links": [...], "rechts": [...]}
    zeit: str = ""

    def als_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

# --- reine Auswertung ---------------------------------------------------------

def _db(a: float) -> float:
    return 20 * math.log10(max(a, 1e-9) / 32768.0)

def _amp(seg, f: float) -> float:
    """Amplitude der Frequenz f im Segment (Hann-gefensterte Einzel-DFT)."""
    import numpy as np
    seg = seg - seg.mean()
    w = np.hanning(len(seg))
    z = np.sum(seg * w * np.exp(-2j * np.pi * f * np.arange(len(seg)) / ABTASTRATE))
    return float(2 * abs(z) / np.sum(w))

def kanal_werte(stille, toene: dict[int, object]) -> list[KanalWert]:
    """Messwerte EINES Kanals: ``stille`` = Segment ohne Ton, ``toene`` =
    {Frequenz: Segment}. Liefert je Ton einen :class:`KanalWert`."""
    werte = []
    for f, seg in toene.items():
        g = _amp(seg, f)
        h = [_amp(seg, k * f) for k in range(2, 6) if k * f < ABTASTRATE / 2]
        klirr = 20 * math.log10(max(math.sqrt(sum(v * v for v in h)), 1e-9) / max(g, 1e-9))
        # Rauschen bei derselben Frequenz, gleiche Fensterlaenge wie der Ton.
        st = stille[: len(seg)] if len(stille) >= len(seg) else stille
        rauschen = _db(_amp(st, f)) if len(st) > 16 else -120.0
        werte.append(KanalWert(ton_hz=f, grundton_db=round(_db(g), 1),
                               klirr_db=round(klirr, 1), rauschen_db=round(rauschen, 1)))
    return werte

def _maengel(eigen: list[KanalWert], anderer: list[KanalWert]) -> list[str]:
    """Was gegen einen Kanal spricht (leer = tauglich)."""
    m = []
    taub = [w.ton_hz for w in eigen if not w.gehoert]
    if taub and len(taub) == len(eigen):
        m.append("hoert keinen Testton")
    leise = [w.ton_hz for w, a in zip(eigen, anderer)
             if a.gehoert and a.grundton_db - w.grundton_db > STUMM_ABSTAND_DB]
    if leise and len(leise) == len(eigen):
        m.append(f"mehr als {STUMM_ABSTAND_DB:.0f} dB leiser als der andere Kanal")
    klirrt = [w for w in eigen if w.gehoert and w.klirr_db > KLIRR_GRENZE_DB]
    # Ein einzelner Ton koennte Pech sein (Raumresonanz). Erst die Mehrheit zaehlt.
    if len(klirrt) * 2 > len([w for w in eigen if w.gehoert]) > 0:
        m.append("klirrt (" + ", ".join(f"{w.ton_hz} Hz {w.klirr_db:+.0f} dB" for w in klirrt)
                 + f"; Grenze {KLIRR_GRENZE_DB:.0f} dB)")
    return m

def auswerten(links: list[KanalWert], rechts: list[KanalWert]) -> Befund:
    """Entscheidung aus den Messwerten beider Kanaele (rein, ohne Geraet)."""
    werte = {"links": [asdict(w) | {"gehoert": w.gehoert} for w in links],
             "rechts": [asdict(w) | {"gehoert": w.gehoert} for w in rechts]}
    zeit = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if not any(w.gehoert for w in links + rechts):
        return Befund("keins", None, ["kein Testton gehoert -- Lautsprecher stumm oder "
                                      "beide Mikrofone ohne Signal"], [], werte, zeit)
    ml, mr = _maengel(links, rechts), _maengel(rechts, links)
    if ml and mr:
        return Befund("keins", None, [f"links: {'; '.join(ml)}", f"rechts: {'; '.join(mr)}"],
                      [], werte, zeit)
    if ml:
        return Befund("rechts", 1, [f"links: {'; '.join(ml)}"], [], werte, zeit)
    if mr:
        return Befund("links", 0, [f"rechts: {'; '.join(mr)}"], [], werte, zeit)
    warn = []
    for nm, ws in (("links", links), ("rechts", rechts)):
        grenzfall = [w for w in ws if w.gehoert and w.klirr_db > KLIRR_GRENZE_DB]
        if grenzfall:
            warn.append(f"{nm}: einzelner Ton ueber der Klirrgrenze "
                        f"({', '.join(str(w.ton_hz) for w in grenzfall)} Hz) -- beobachten")
    return Befund("beide", None, ["beide Kanaele hoeren den Ton sauber"], warn, werte, zeit)

# --- Messung am Geraet ----------------------------------------------------------

def _testsignal(pfad: str) -> list[tuple[int, int, int]]:
    """Schreibt Stille + Stufentoene als WAV; liefert (f, start, laenge) in Abtastwerten."""
    import numpy as np
    teile, plan, pos = [np.zeros(int(ABTASTRATE * 1.0))], [], int(ABTASTRATE * 1.0)
    for f in TOENE:
        n = int(ABTASTRATE * TON_DAUER_S)
        t = np.arange(n) / ABTASTRATE
        teile.append(TON_PEGEL * np.sin(2 * np.pi * f * t))
        plan.append((f, pos, n))
        pos += n
        luecke = int(ABTASTRATE * 0.15)
        teile.append(np.zeros(luecke))
        pos += luecke
    teile.append(np.zeros(int(ABTASTRATE * 0.4)))
    sig = np.concatenate(teile)
    with wave.open(pfad, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(ABTASTRATE)
        w.writeframes((np.clip(sig, -1, 1) * 32767).astype("<i2").tobytes())
    return plan

def messen(*, geraet_spiel: str = "default", geraet_auf: str = "default",
           arbeitsordner: str | None = None) -> Befund:
    """Spielt die Testtoene, nimmt beide Kanaele auf und wertet aus.

    Wirft ``RuntimeError`` mit benanntem Grund, wenn Abspielen oder Aufnehmen
    scheitern -- ein gescheiterter Lauf ist KEIN Befund ueber die Mikros.
    """
    import numpy as np
    d = Path(arbeitsordner or tempfile.mkdtemp(prefix="chimera-mikro-"))
    spiel, auf = str(d / "test.wav"), str(d / "auf.wav")
    plan = _testsignal(spiel)
    dauer = int(math.ceil(plan[-1][1] / ABTASTRATE + TON_DAUER_S + 2.0))
    rec = subprocess.Popen(["arecord", "-q", "-D", geraet_auf, "-f", "S16_LE",
                            "-r", str(ABTASTRATE), "-c", "2", "-d", str(dauer), auf],
                           stderr=subprocess.PIPE, text=True)
    time.sleep(0.4)
    sp = subprocess.run(["aplay", "-q", "-D", geraet_spiel, spiel],
                        capture_output=True, text=True, timeout=dauer + 10)
    try:
        _, rec_err = rec.communicate(timeout=dauer + 10)
    except subprocess.TimeoutExpired:
        rec.kill()
        raise RuntimeError("arecord haengt -- Aufnahme abgebrochen") from None
    if sp.returncode != 0:
        raise RuntimeError(f"aplay rc {sp.returncode}: {sp.stderr.strip()[-200:]}")
    if rec.returncode != 0:
        raise RuntimeError(f"arecord rc {rec.returncode}: {(rec_err or '').strip()[-200:]}")
    with wave.open(auf, "rb") as w:
        if w.getnchannels() != 2:
            raise RuntimeError(f"Aufnahme hat {w.getnchannels()} Kanaele, erwartet 2")
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float).reshape(-1, 2)
    # Versatz Wiedergabe->Aufnahme ueber Kreuzkorrelation mit dem Testsignal.
    with wave.open(spiel, "rb") as w:
        ref = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)
    mono = x[:, 0] + x[:, 1]
    n = 1 << int(math.ceil(math.log2(len(mono) + len(ref))))
    cc = np.fft.irfft(np.fft.rfft(mono, n) * np.conj(np.fft.rfft(ref, n)), n)[: len(mono)]
    versatz = int(np.argmax(np.abs(cc)))
    stille_ende = versatz + int(ABTASTRATE * 0.9)
    werte = []
    for k in (0, 1):
        stille = x[max(0, versatz + int(ABTASTRATE * 0.2)):max(1, stille_ende), k]
        toene = {}
        for f, s, ln in plan:
            a, b = versatz + s + int(ln * 0.2), versatz + s + int(ln * 0.8)
            if b > len(x):
                raise RuntimeError("Aufnahme zu kurz fuer die Testtoene")
            toene[f] = x[a:b, k]
        werte.append(kanal_werte(stille, toene))
    return auswerten(werte[0], werte[1])

# --- ALSA-Geraet ----------------------------------------------------------------

def alsa_geraet(befund: Befund, *, quelle: str = "array", name: str = "chimera_mikro") -> str:
    """ALSA-Konfiguration fuer das Aufnahmegeraet des Dienstes.

    ``beide`` -> zwei Kanaele durchgereicht; ``links``/``rechts`` -> ein
    Kanal (mono) aus dem guten Mikro; ``keins`` -> keine Konfiguration (leer).
    ``quelle`` ist das dsnoop-Geraet der Herstellerkonfiguration (mehrere
    Leser gleichzeitig moeglich).
    """
    if befund.entscheidung == "keins":
        return ""
    kopf = (f"# Chimera -- Aufnahmegeraet, vom Installer (Modul 46) aus der Messung\n"
            f"# erzeugt ({befund.zeit}): {befund.entscheidung}.\n"
            f"# {'; '.join(befund.gruende)}\n"
            f"# Von Hand geaendert? Beim naechsten Messlauf wird die Datei ersetzt.\n")
    if befund.entscheidung == "beide":
        return kopf + (f"pcm.{name} {{\n    type plug\n    slave {{ pcm \"{quelle}\" channels 2 }}\n}}\n")
    return kopf + (f"pcm.{name} {{\n    type plug\n    slave {{ pcm \"{quelle}\" channels 2 }}\n"
                   f"    ttable.0.{befund.kanal} 1\n}}\n")

# --- Werkzeug -------------------------------------------------------------------

def main(argv: list[str]) -> int:
    """``python3 -m chimera.displays mikro [--json]`` -- messen und Befund ausgeben.

    rc 0 mindestens ein Mikro brauchbar, 1 keins, 2 Messung gescheitert.
    """
    try:
        b = messen()
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"Messung gescheitert: {exc}", file=sys.stderr)
        return 2
    if "--json" in argv:
        print(b.als_json())
    else:
        print(f"Mikrofone: {b.entscheidung}")
        for g in b.gruende:
            print(f"  {g}")
        for w in b.warnungen:
            print(f"  WARNUNG: {w}")
    return 1 if b.entscheidung == "keins" else 0
