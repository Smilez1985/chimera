#!/usr/bin/env python3
"""Avatar-Renderer.

Herkunft: Dieser Renderer stammt aus **Noisy** (Smilez1985/Noisy, MIT) und
ist dort erprobt. Er wird nicht nachgebaut, sondern übernommen — was rollt,
muss nicht neu erfunden werden.

Angepasst wurde nur, was Chimera anders macht:

* **Keine feste Bildgröße.** Noisy rechnet gegen 240×240 aus der
  Konfiguration; hier kommen Breite und Höhe aus dem Panel
  (Architekturregel 6). Die Gesichtsgeometrie hing ohnehin fast überall an
  den Radien ``r_w``/``r_h``, nicht an Absolutwerten — betroffen waren
  vor allem die Bildschirm-Überlagerungen.
* **Keine Bindung an ein Panel.** Noisy öffnet ``st7789`` selbst. Hier
  nimmt der Renderer ein beliebiges ``Panel`` entgegen
  (:mod:`chimera.display.panel`), damit er ohne Gerät läuft.
* **Keine Bindung an einen Orchestrator.** Statt ``self.orch`` gibt es
  einen schlanken Zustand, den jeder füllen kann.
* **Freie Formen.** Was das Sprachmodell erfindet, wird zusätzlich
  gezeichnet (:mod:`chimera.mood.draw`, Architekturregel 1a).

Der Aufbau des Bildes bleibt Noisys: Schein, Körper, Frisur, Accessoires,
Augen, Mund, Partikel — in dieser Reihenfolge, weil eine Sonnenbrille
hinter den Augen keine wäre.
"""

import time
import math
import random
from datetime import datetime
from PIL import Image, ImageDraw, ImageEnhance

try:
    import numpy as np
except ImportError:          # nur fuer die Helligkeitsanpassung gebraucht
    np = None

from ..mood.draw import validate_shapes  # noqa: F401  (Formen zeichnen, s.u.)

# Farben, die der Renderer selbst braucht. In Noisy kamen sie aus moods/.
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GOLD = (255, 215, 0)
EYE_COLOR = (20, 20, 35)

DEFAULT_BODY = {"color": (30, 180, 220), "glow": (15, 90, 110)}

# Noisy kennt Moods ueber Nummern und vergleicht damit (mood_id == ROCK).
# Chimera vergibt Nummern zur Laufzeit, also wird ueber den NAMEN
# verglichen. Diese beiden Sonderfaelle bleiben, weil der Renderer fuer
# sie eigene Darstellungen hat.
MOOD_SAD = "SAD"
MOOD_ROCK = "ROCK"

# Messing fuer das Saxophon. Drei Toene, weil ein einfarbiges Instrument
# flach aussieht - hell fuer die Kante zum Licht, dunkel fuer den Hals.
# Accessoires, die VOR Augen und Mund gehoeren. Eine Sonnenbrille hinter
# den Augen waere keine, und das Notenblatt soll die Noten verdecken, die
# dahinter aufsteigen.
ACCESSOIRES_VORN = frozenset({
    "sunglasses", "sheet_music", "drink", "devil_sign", "saxophone",
    "jackhammer",
})

# Wie weit die Frisur dem Kopf hoechstens nachhaengen darf (px)
HAIR_MAX_LAG = 7

BRASS = (214, 158, 46)
BRASS_LIGHT = (255, 214, 130)
BRASS_DARK = (150, 106, 28)

# Glaettung der Audio-Kopplung (0 = eingefroren, 1 = ungefiltert).
# 0.18 bei 15 FPS entspricht rund einer Drittelsekunde Nachlauf.
AUDIO_SMOOTHING = 0.18


class State:
    """Was der Renderer von aussen braucht.

    In Noisy war das der Orchestrator mit sechzehn Feldern. Hier ist es ein
    schlichter Behaelter: Wer ihn fuellt -- Agent, Sprachausgabe, Umgebungs-
    hoeren --, ist dem Renderer gleich. Das ist derselbe Gedanke wie beim
    Panel: Der Renderer soll ohne die halbe Anwendung laufen.
    """

    def __init__(self):
        self.mood_name = "IDLE"      # Name statt Nummer (Nummern sind dynamisch)
        self.mood = None             # das Mood-Dict selbst
        self.intensity = 0.0         # 0..255, Lautstaerke -> Mundform (SS4.1)
        self.beat = 0.0
        self.morph_speed = 1.0
        self.personality = None
        self.is_muted = False
        self.is_debug = False
        self.is_social = False
        self.show_identity = False
        self.night_annoyed = False
        self.favorite_playing = False
        self.cube_mode = False
        self.speaking = False        # neu: spricht gerade (SS4.1)

def lift_color(farbe, staerke, ziel=245):
    """
    Hebt eine Farbe Richtung `ziel`, ohne den Farbton zu verschieben.

    Alle drei Kanaele werden mit demselben Faktor skaliert - der Blob
    bleibt also blau, gruen oder rot wie definiert, er wird nur heller.
    Der Faktor richtet sich nach dem hellsten Kanal: eine fast schwarze
    Farbe gewinnt viel, eine ohnehin leuchtende kaum etwas. Damit bleibt
    die Abstufung zwischen ruhigen und lauten Moods erhalten, waehrend
    beide gegen Raumlicht ankommen.

    staerke 0.0 = unveraendert, 1.0 = hellster Kanal geht auf `ziel`.
    """
    if staerke <= 0.0:
        return farbe
    hellster = max(farbe)
    if hellster <= 0 or hellster >= ziel:
        return farbe
    soll = hellster + (ziel - hellster) * staerke
    faktor = soll / float(hellster)
    return tuple(min(255, int(k * faktor)) for k in farbe)


# Kontur fuer dunkle Koerper.
#
# Der Hintergrund ist schwarz, und die Nacht-/Idle-Moods sind bewusst
# gedaempft - in Kombination mit der Nachtabsenkung wird daraus Dunkel auf
# Dunkel. Liegt der hellste Farbkanal unter der Schwelle, zieht der
# Renderer eine duenne aufgehellte Kontur um den Blob. So bleibt sichtbar,
# was der Mochi treibt, ohne dass ein ruhiger Mood grell wird.
BODY_OUTLINE_THRESHOLD = 165      # hellster Kanal, ab dem keine Kontur noetig ist
BODY_OUTLINE_TARGET = 235         # Zielhelligkeit der Kontur

# Zug-Zyklus fuer JOINT und BONG: einatmen, halten, ausatmen, Pause.
# Laengen in Frames. Bei rund 8 FPS ergibt das etwa neun Sekunden pro
# Zug - langsam genug, dass man es als Handlung liest und nicht als
# Zappeln.
# ============================================================
# Zug-Zyklus (Joint, Bong und alles Weitere mit physics.toke)
#
# Eine einzige Phase 0..1 treibt BEIDES: wo das Rauchwerk gerade ist und
# was der Mochi damit macht. Vorher waren das zwei unabhaengige Dinge -
# der Joint lag starr im Bild, waehrend irgendwo ein Atemzyklus lief.
# Aneinander vorbei, per Konstruktion.
#
# Die Phase waechst ausschliesslich im gezeichneten Bild und nur um die
# gemessene, gedeckelte Bildzeit. Damit gilt beides:
#   - sie haengt nicht an der Bildrate (frueher fuer 15 FPS ausgelegt,
#     das Geraet schafft 8 - jeder Zug dauerte fast doppelt so lange),
#   - und sie laeuft nicht davon, wenn die CPU haengt. Wer nichts
#     zeichnet, zieht auch nicht.
TOKE_PERIOD = 13.0          # Sekunden fuer einen ganzen Zug

# Marken innerhalb der Phase (Anteile, muessen aufsteigend sein)
TOKE_P_ANLEGEN = 0.13       # Rauchwerk wandert an den Mund
TOKE_P_ZIEHEN = 0.44        # am Mund: Glut hell, Mochi blaeht sich auf
TOKE_P_ABSETZEN = 0.55      # Rauchwerk wandert weg, Luft wird gehalten
TOKE_P_AUSATMEN = 0.75      # Rauch raus, Mochi schrumpft zurueck
#                    danach: high - die Wirkung setzt ein

TOKE_INFLATE = 0.18         # wie stark er sich aufblaeht (Anteil des Radius)
TOKE_MAX_SCHRITT = 0.25     # groesster Phasenschritt pro Bild, in Sekunden

# Rueckfallwert der Kontrast-Anhebung, falls die RuntimeConfig ihn nicht
# kennt (siehe RuntimeConfig.get_contrast).
DEFAULT_CONTRAST_BOOST = 0.45

# Untergrenze der Nachtabsenkung. Ganz herunterregeln darf man am Regler,
# aber die automatische Absenkung soll den Blob nie unsichtbar machen.
NIGHT_DIM_FLOOR = 0.45

# ============================================================
# Farb-Interpolation
# ============================================================
def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


# ============================================================
# Partikel-System (NumPy-vektorisiert)
# ============================================================
class ParticleSystem:
    """Vektorisiertes Partikel-System mit NumPy Arrays."""

    def __init__(self, max_particles=30):
        self.max = max_particles
        # Spalten: x, y, vx, vy, life, type_id
        # type_id: 0=note, 1=zzz, 2=exclamation, 3=heart, 4=star,
        #          5=smoke, 6=sweat, 7=stink, 8=puff, 9=drop
        self.data = np.zeros((0, 6), dtype=np.float32)
        self.colors = []

    def spawn(self, x, y, p_type, color):
        """Spawnt ein einzelnes Partikel."""
        if len(self.data) >= self.max:
            return

        type_map = {"note": 0, "zzz": 1, "exclamation": 2, "heart": 3,
                     "star": 4, "smoke": 5, "sweat": 6, "stink": 7,
                     "puff": 8, "drop": 9}
        tid = type_map.get(p_type, 0)

        if tid == 1:  # zzz
            vx = random.uniform(0.5, 1.5)
            vy = random.uniform(-1.5, -0.5)
            life = random.randint(40, 80)
        elif tid == 2:  # exclamation
            vx = random.uniform(-3, 3)
            vy = random.uniform(-3, 3)
            life = random.randint(10, 25)
        elif tid == 5:  # smoke
            vx = random.uniform(-0.5, 0.5)
            vy = random.uniform(-1.5, -0.5)
            life = random.randint(20, 50)
        elif tid == 7:  # stink
            vx = random.uniform(-1, 1)
            vy = random.uniform(-0.5, 0.5)
            life = random.randint(15, 35)
        elif tid == 8:  # puff - ausgeblasener Rauch
            # Nach links vom Mund weg und langsam aufsteigend. Anders als
            # das duenne "smoke"-Kringelchen ist das eine sichtbare Wolke,
            # die beim Aufsteigen groesser und blasser wird.
            vx = random.uniform(-2.6, -1.2)
            vy = random.uniform(-0.9, -0.2)
            life = random.randint(38, 58)
        elif tid == 9:  # drop - verschuetteter Tropfen
            # Fliegt seitlich weg und faellt dann (Schwerkraft in update).
            # Kurzes Leben: er soll spritzen, nicht schweben.
            vx = random.uniform(-2.2, 2.2)
            vy = random.uniform(-2.0, -0.6)
            life = random.randint(16, 30)
        else:  # note, heart, star, sweat
            vx = random.uniform(-1.5, 1.5)
            vy = random.uniform(-2.5, -1)
            life = random.randint(30, 60)

        new = np.array([[x, y, vx, vy, life, tid]], dtype=np.float32)
        self.data = np.vstack([self.data, new]) if len(self.data) > 0 else new
        self.colors.append(color)

    def update(self):
        """Update alle Partikel (vektorisiert)."""
        if len(self.data) == 0:
            return
        # Schwerkraft - nur fuer Tropfen. Alles andere steigt auf oder
        # treibt; ein verschuetteter Schluck faellt.
        faellt = self.data[:, 5] == 9
        if faellt.any():
            self.data[faellt, 3] += 0.35

        # Position updaten
        self.data[:, 0] += self.data[:, 2]  # x += vx
        self.data[:, 1] += self.data[:, 3]  # y += vy
        self.data[:, 4] -= 1                 # life -= 1
        # Tote entfernen
        alive = self.data[:, 4] > 0
        self.data = self.data[alive]
        self.colors = [c for c, a in zip(self.colors, alive) if a]

    def draw(self, draw_ctx):
        """Zeichnet alle Partikel."""
        symbols = {0: None, 1: "z", 2: "!", 3: "<3", 4: "*", 5: "~", 6: ".", 7: "~"}
        for i in range(len(self.data)):
            x, y, _, _, life, tid = self.data[i]
            alpha = max(0.2, life / 60.0)
            c = self.colors[i] if i < len(self.colors) else WHITE
            ix, iy = int(x), int(y)
            tid = int(tid)

            if tid == 9:
                # Tropfen: kleiner heller Klecks, der beim Fallen
                # laenglich wird - das liest sich als Fluessigkeit
                gestreckt = 1.0 + max(0.0, self.data[i][3]) * 0.5
                draw_ctx.ellipse([ix - 2, iy - 2 * gestreckt,
                                  ix + 2, iy + 2 * gestreckt], fill=c)
                continue

            if tid == 8:
                # Rauchwolke: waechst beim Aufsteigen und wird blasser
                alter = 1.0 - min(1.0, life / 70.0)
                radius = 3 + alter * 7
                # Nicht ins Schwarze ausblenden - auf dem hellen Koerper
                # sahen die alten Wolken sonst aus wie dunkle Flecken.
                # Sie treiben ohnehin vom Koerper herunter und
                # verschwinden dort gegen den schwarzen Hintergrund.
                blass = max(0.42, 0.85 - alter * 0.45)
                cc = (int(c[0] * blass), int(c[1] * blass), int(c[2] * blass))
                draw_ctx.ellipse([ix - radius, iy - radius,
                                  ix + radius, iy + radius], fill=cc)
                continue

            c = (int(c[0] * alpha), int(c[1] * alpha), int(c[2] * alpha))
            sym = symbols.get(tid)
            if sym:
                draw_ctx.text((ix, iy), sym, fill=c)
            else:
                # Note
                draw_ctx.ellipse([ix, iy, ix + 5, iy + 4], fill=c)
                draw_ctx.line([ix + 4, iy + 2, ix + 4, iy - 8], fill=c, width=2)


# ============================================================
# Renderer
# ============================================================
class NoisyRenderer:
    def __init__(self, state=None, panel=None, *, width=None, height=None,
                 target_fps=15):
        """Renderer aufsetzen.

        ``panel`` ist ein beliebiges Panel aus :mod:`chimera.display.panel`;
        fehlt es, wird eines ohne Anzeige benutzt. Die Bildgroesse kommt vom
        Panel, nicht aus einer Konstanten.
        """
        from ..display.panel import NullPanel

        self.state = state if state is not None else State()
        self.panel = panel if panel is not None else NullPanel()

        self.WIDTH = int(width or getattr(self.panel, "width", 240))
        self.HEIGHT = int(height or getattr(self.panel, "height", 280))
        self.TARGET_FPS = target_fps
        self.FRAME_TIME = 1.0 / target_fps if target_fps else 0.0

        # Bezugsgroesse fuer alles Geometrische. Noisy rechnete gegen eine
        # quadratische Flaeche; auf 240x280 ist die kurze Seite der
        # richtige Massstab, sonst wird das Gesicht mitgedehnt.
        self.BASE = min(self.WIDTH, self.HEIGHT)

        # Sitz und Groesse des Gesichts, als Anteil der Flaeche. Auf 240x280
        # bleibt unten Platz fuer die Statuszeile -- deshalb sitzt das
        # Gesicht etwas hoeher als die geometrische Mitte.
        self.FACE_CY = 0.44
        self.FACE_R = 0.23

        # Diese beiden standen in Noisy im Konstruktor, den Chimera
        # ersetzt hat -- sie gehoeren zum Zustand und werden hier gesetzt.
        self.frame = 0.0
        self.particles = ParticleSystem(max_particles=30)

        self._init_zustand()

    def _mood(self):
        """Der aktuelle Mood als Dict.

        Noisy fragte eine globale Registry nach der Nummer. Chimera vergibt
        Nummern zur Laufzeit, also traegt der Zustand das Dict gleich selbst
        -- ein Umweg weniger und keine versteckte Abhaengigkeit.
        """
        m = self.state.mood
        if m:
            return m
        from ..mood.schema import defaults
        d = defaults()
        d["name"] = self.state.mood_name or "IDLE"
        return d

    def _init_zustand(self):
        """Alles, was unabhaengig vom Ausgabeweg initialisiert wird."""
        # Blink-Engine
        self.blink_timer = 0
        self.blink_duration = 0
        self.is_blinking = False
        self.next_blink = random.randint(50, 150)

        # Smooth Color Morphing
        self.current_body_color = DEFAULT_BODY["color"]
        self.current_glow_color = DEFAULT_BODY["glow"]
        self.morph_speed = 0.08

        # Thermal
        self.cpu_temp = 45.0
        self.temp_read_counter = 0

        # SAD Traene
        self.tear_y = 0

        # Accessoires duerfen sagen, woher die Partikel kommen sollen.
        # Bei Jazz stroemen die Noten aus dem Trichter statt aus dem
        # Kopf - sonst sieht es aus, als saenge der Mochi neben dem
        # Instrument her.
        self.particle_origin = None

        # Geglaettete Audio-Kopplung (0.0-1.0)
        # Die Rohwerte aus der Audio-Engine springen im Sekundentakt.
        # Ungeglaettet wuerde der Blob bei jedem neuen Messwert zucken,
        # deshalb laeuft alles ueber einen exponentiellen Mittelwert.
        self.toke_inflate = 0.0
        self.toke_ember = 0.0
        self.toke_exhaling = False
        self.toke_anlegen = 0.0      # 0 = abgesetzt, 1 = am Mund
        self.toke_high = 0.0         # 0..1 wie stark die Wirkung gerade ist
        self.toke_phase = 0.0
        self.toke_mood = None
        self.toke_letzte_zeit = None

        self.smooth_loud = 0.0
        self.smooth_beat = 0.0
        self.beat_phase = 0.0

    # ----------------------------------------------------------
    # Thermal
    # ----------------------------------------------------------
    def toke_cycle(self, mood_id, zieht, speed=1.0):
        """
        Zug-Zyklus - gemeinsames Verhalten aller Rauch-Moods.

        Joint und Bong teilen sich diese Mechanik; ein Mood meldet sich
        ueber `physics.toke` dafuer an, statt dass hier eine Liste von
        Mood-IDs gepflegt wird. Wer einen weiteren Rauch-Mood baut,
        bekommt Anlegen, Ziehen, Ausatmen und die Wirkung geschenkt.

        Der Ablauf:
            anlegen   Joint/Bong wandert an den Mund
            ziehen    am Mund - Glut hell, Mochi blaeht sich auf
            absetzen  wandert weg, die Luft wird angehalten
            ausatmen  Rauch raus, Mochi schrumpft zurueck
            high      die Wirkung: Schwindelaugen und traeges Treiben

        Setzt die Felder toke_anlegen, toke_inflate, toke_ember,
        toke_exhaling und toke_high. Alles aus derselben Phase, damit
        das Rauchwerk und der Atem nicht auseinanderlaufen koennen.
        """
        if not zieht:
            self.toke_mood = None
            self.toke_letzte_zeit = None
            self.toke_phase = 0.0
            self.toke_anlegen = 0.0
            self.toke_high = 0.0
            return 0.0, 0.0, False

        jetzt = time.monotonic()
        if self.toke_mood != mood_id:
            # Neuer Zug faengt von vorn an. Frueher lief der Zaehler frei
            # durch - beim Umschalten landete man an beliebiger Stelle,
            # oft mitten in der Pause, und sah gar nichts.
            self.toke_mood = mood_id
            self.toke_phase = 0.0
            self.toke_letzte_zeit = jetzt

        # Gedeckelte Bildzeit: haengt die CPU zwei Sekunden, springt der
        # Zug trotzdem nur um einen Bruchteil weiter statt eine Phase zu
        # ueberspringen.
        dt = min(TOKE_MAX_SCHRITT, max(0.0, jetzt - self.toke_letzte_zeit))
        self.toke_letzte_zeit = jetzt
        self.toke_phase = (self.toke_phase
                           + dt * max(0.1, speed) / TOKE_PERIOD) % 1.0

        p = self.toke_phase

        def weich(x):
            """Sanft anfahren und ausrollen statt linear zu rucken."""
            return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, x)))

        def anteil(von, bis):
            return (p - von) / float(bis - von)

        if p < TOKE_P_ANLEGEN:                       # anlegen
            self.toke_anlegen = weich(anteil(0.0, TOKE_P_ANLEGEN))
            self.toke_high = 0.0
            return 0.0, 0.3, False

        if p < TOKE_P_ZIEHEN:                        # ziehen
            fortschritt = weich(anteil(TOKE_P_ANLEGEN, TOKE_P_ZIEHEN))
            self.toke_anlegen = 1.0
            self.toke_high = 0.0
            return fortschritt, 0.35 + 0.65 * fortschritt, False

        if p < TOKE_P_ABSETZEN:                      # absetzen, Luft halten
            self.toke_anlegen = 1.0 - weich(anteil(TOKE_P_ZIEHEN,
                                                   TOKE_P_ABSETZEN))
            self.toke_high = 0.0
            return 1.0, 0.4, False

        if p < TOKE_P_AUSATMEN:                      # ausatmen
            rest = anteil(TOKE_P_ABSETZEN, TOKE_P_AUSATMEN)
            self.toke_anlegen = 0.0
            self.toke_high = 0.0
            return weich(1.0 - rest), 0.3, True

        # high - Wirkung, klingt zum Ende hin wieder ab
        wirkung = anteil(TOKE_P_AUSATMEN, 1.0)
        self.toke_anlegen = 0.0
        self.toke_high = weich(min(1.0, wirkung * 3)) * (1.0 - wirkung * 0.35)
        return 0.0, 0.3, False

    def toke_versatz(self, typ):
        """
        Wie weit Joint oder Bong gerade vom Mund entfernt liegt.

        Gibt (dx, dy) zurueck: bei toke_anlegen == 1 ist beides 0, also
        am Mund. Abgesetzt liegt der Joint tiefer und weiter aussen, die
        Bong steht auf dem Boden.
        """
        weg = 1.0 - self.toke_anlegen
        if typ == "bong":
            # Die Bong wird abgestellt, nicht weggeschwenkt: sie sinkt
            # nach unten und rueckt vom Gesicht weg.
            return weg * 16, weg * 12
        return weg * 20, weg * 22

    def read_temperature(self):
        self.temp_read_counter += 1
        if self.temp_read_counter % 30 == 0:
            try:
                with open(THERMAL_PATH, "r") as f:
                    self.cpu_temp = int(f.read()) / 1000.0
            except Exception:
                self.cpu_temp = 45.0

    # ----------------------------------------------------------
    # Brightness / Night-Window (Web-UI Live-Parameter)
    # ----------------------------------------------------------
    def _is_night(self, disp):
        """True wenn die aktuelle Uhrzeit im Nacht-Fenster liegt."""
        now = datetime.now().strftime("%H:%M")
        start = disp.get("night_mode_start", "22:00")
        end = disp.get("night_mode_end", "06:00")
        if start <= end:
            return start <= now < end
        # Fenster ueber Mitternacht (z.B. 22:00 - 06:00)
        return now >= start or now < end

    def _apply_brightness(self, img):
        """Software-Dimming: skaliert das Bild nach Tag-/Nacht-Helligkeit."""
        rt = getattr(self.state, 'rt', None)
        if rt is None:
            return img
        disp = rt.get_display()
        if disp.get("auto_dim", True) and self._is_night(disp):
            brightness = disp.get("brightness_night", 80)
        else:
            brightness = disp.get("brightness_day", 255)
        factor = max(0.0, min(1.0, brightness / 255.0))

        # Bei automatischer Absenkung nicht unter die Sichtbarkeitsgrenze
        # gehen. Wer bewusst am Regler ganz herunterzieht, bekommt das
        # auch - die Automatik soll den Mochi aber nicht ausknipsen.
        if disp.get("auto_dim", True) and self._is_night(disp):
            factor = max(factor, NIGHT_DIM_FLOOR)

        if factor >= 0.999:
            return img
        return ImageEnhance.Brightness(img).enhance(factor)

    # ----------------------------------------------------------
    # Glow
    # ----------------------------------------------------------
    def draw_glow(self, draw, cx, cy, r_w, r_h, color, mood_id,
                  beat_pulse=0.0, beat_strength=0.0):
        """
        Der Schein um den Blob. Liegt ein Takt an, pulsiert er mit -
        je staerker der gemessene Beat, desto deutlicher.
        """
        pulse = 1.0
        if mood_id == MOOD_ROCK:
            pulse = 0.65 + 0.35 * math.sin(self.frame * 0.45)
        if beat_strength > 0.05:
            pulse *= (1.0 - 0.45 * beat_strength) + 0.45 * beat_strength * beat_pulse * 2.0
        for i in range(5, 0, -1):
            gw = r_w + i * 10
            gh = r_h + i * 10
            f = (6 - i) * 0.25 * pulse
            g = (int(color[0] * f), int(color[1] * f), int(color[2] * f))
            draw.ellipse([cx - gw, cy - gh * 0.85, cx + gw, cy + gh * 0.95], fill=g)

    # ----------------------------------------------------------
    # Body
    # ----------------------------------------------------------
    def draw_body(self, draw, cx, cy, r_w, r_h, color):
        """
        Der Koerper. Dunkle Moods bekommen eine duenne helle Kontur.

        Ohne sie verschwinden die Nacht- und Idle-Stimmungen gegen den
        schwarzen Hintergrund - besonders, wenn die Nachtabsenkung das
        Bild zusaetzlich daempft. Die Kontur kostet einen Zeichenaufruf
        und haelt die Silhouette lesbar, ohne den Mood aufzuhellen.
        """
        kasten = [cx - r_w, cy - r_h * 0.85, cx + r_w, cy + r_h * 0.95]
        draw.ellipse(kasten, fill=color)

        helligkeit = max(color)
        if helligkeit < BODY_OUTLINE_THRESHOLD:
            # Je dunkler der Koerper, desto deutlicher die Kontur
            staerke = 1.0 - helligkeit / float(BODY_OUTLINE_THRESHOLD)
            kontur = tuple(
                min(255, int(k + (BODY_OUTLINE_TARGET - k) * (0.35 + 0.45 * staerke)))
                for k in color
            )
            draw.ellipse(kasten, outline=kontur, width=2)

    # ----------------------------------------------------------
    # Kopfhoerer
    # ----------------------------------------------------------
    def draw_headphones(self, draw, cx, cy, r_w, r_h, before_body=True):
        if before_body:
            draw.arc([cx - r_w - 8, cy - r_h - 18, cx + r_w + 8, cy + 3],
                     180, 0, fill=WHITE, width=10)
            draw.arc([cx - r_w - 6, cy - r_h - 16, cx + r_w + 6, cy + 1],
                     180, 0, fill=(35, 35, 45), width=8)
        else:
            draw.ellipse([cx - r_w - 13, cy - 16, cx - r_w + 9, cy + 26],
                         fill=(35, 35, 45), outline=WHITE, width=2)
            draw.ellipse([cx + r_w - 9, cy - 16, cx + r_w + 13, cy + 26],
                         fill=(35, 35, 45), outline=WHITE, width=2)

    # ----------------------------------------------------------
    # Frisur (immer sichtbar, wippt bei Musik)
    # ----------------------------------------------------------
    # ----------------------------------------------------------
    # Frisuren
    #
    # Der Ausgangszustand war ein Kackhaufen-Emoji: drei gestapelte
    # Ellipsen mit einer Spitze rechts, leicht schraeggedrueckt, damit es
    # wie ein Toupet wirkt. Als Running Gag charmant, als einzige Option
    # unbefriedigend - deshalb gibt es jetzt mehrere Stile, und Farbe wie
    # Stil sind im Dashboard einstellbar.
    #
    # Jeder Stil ist eine Methode draw_hair_<name>(draw, hx, hy, cx, r_w,
    # color, dark, light). hx/hy ist der Ansatzpunkt oben am Kopf,
    # bereits um Wobble und Wind verschoben.
    # ----------------------------------------------------------
    @staticmethod
    def _schattierungen(color):
        """
        Leitet Schatten- und Glanzton aus der Grundfarbe ab. So muss im
        Dashboard nur eine Farbe gewaehlt werden, nicht drei.
        """
        dark = tuple(max(0, int(k * 0.72)) for k in color)
        light = tuple(min(255, int(k + (255 - k) * 0.22)) for k in color)
        return dark, light

    def nachwipp(self, physics, hair_data):
        """
        Wie weit die Frisur der Kopfbewegung hinterherhaengt (ox, oy).

        `physics` sind die WIRKSAMEN Werte, also bereits mit Lautstaerke
        und Takt skaliert. Vorher kamen hier die rohen Mood-Werte an:
        die Frisur wippte in voller Amplitude weiter, waehrend der Kopf
        bei leiser Musik kaum noch bangte - sie sah aus, als haenge sie
        gar nicht am Kopf.

        Der Ausschlag ist gedeckelt. Traegheit ja, Abloesung nein: bei
        grosser Amplitude riss der Nachwipp die Frisur sichtbar vom
        Kopf.
        """
        if not hair_data.get("wobble", False):
            return 0.0, 0.0

        hs = physics.get("headbang_speed", 0)
        ha = physics.get("headbang_amp", 0)
        bs = physics.get("bounce_speed", 0)
        ba = physics.get("bounce_amp", 0)

        if hs > 0 and ha > 0.5:
            koerper = math.sin(self.frame * hs) * ha
            haare = math.sin(self.frame * hs - 0.6) * ha * 1.08
            ho_y = max(-HAIR_MAX_LAG, min(HAIR_MAX_LAG, haare - koerper))
            ho_x = math.sin(self.frame * hs - 0.4) * min(6, ha * 0.24)
            return ho_x, ho_y

        if bs > 0 and ba > 0.5:
            return (math.sin(self.frame * bs - 0.3) * min(3, ba * 0.15),
                    math.sin(self.frame * bs - 0.5) * min(5, ba * 0.25))

        return 0.0, 0.0

    def draw_hair(self, draw, cx, cy, r_w, physics, hair_data):
        if not hair_data.get("visible", True):
            return

        # "blown": die Frisur wird zur Seite gedrueckt, als wehe Wind
        if hair_data.get("blown"):
            cx = cx + 7 + int(3 * math.sin(self.frame * 0.16))

        color = hair_data.get("color", (139, 90, 43))
        auto_dark, auto_light = self._schattierungen(color)
        dark = hair_data.get("color_dark", auto_dark)
        light = hair_data.get("color_light", auto_light)

        # Wobble bei Musik (Traegheits-Nachwipp)
        ho_x, ho_y = self.nachwipp(physics, hair_data)

        hx = cx + ho_x
        hy = cy - r_w * 0.95 + ho_y

        stil = hair_data.get("style") or self.hair_style
        zeichner = getattr(self, 'draw_hair_' + stil, None)
        if zeichner is None:
            zeichner = self.draw_hair_mochi
        zeichner(draw, hx, hy, cx, r_w, color, dark, light, ho_x, ho_y)

    # ----------------------------------------------------------
    def draw_hair_mochi(self, draw, hx, hy, cx, r_w, color, dark, light, ox, oy):
        """Der Klassiker. Ja, das ist ein Kackhaufen. Er bleibt."""
        hx = hx + 10
        draw.ellipse([cx - r_w - 2, hy + 6, cx + r_w + 2, hy + 24], fill=color)
        draw.ellipse([hx - 30, hy - 10, hx + 34, hy + 12], fill=color)
        draw.ellipse([hx - 8, hy - 26, hx + 24, hy - 2], fill=color)
        tip_x = hx + 24 + ox * 0.6
        tip_y = hy - 30 + oy * 0.3
        draw.ellipse([tip_x - 9, tip_y - 7, tip_x + 9, tip_y + 7], fill=color)
        draw.arc([cx - r_w - 2, hy + 6, cx - 10, hy + 24], 90, 270, fill=dark, width=3)
        draw.arc([hx - 30, hy - 10, hx - 6, hy + 12], 90, 270, fill=dark, width=3)
        draw.arc([hx + 10, hy - 22, hx + 22, hy - 6], 270, 90, fill=light, width=2)

    # ----------------------------------------------------------
    def _kappe(self, draw, cx, hy, r_w, color, tiefe=1.0):
        """
        Die Grundform aller Frisuren ausser mochi: eine Haube, die der
        Kopfkuppel folgt und bis knapp ueber die Augen reicht.

        Der erste Anlauf zeichnete duenne Baender quer ueber den Kopf -
        das sah nach Stirnband aus, nicht nach Haaren. Entscheidend ist,
        dass die Form den Kopf UMSCHLIESST: etwas breiter als der Kopf
        und tief genug heruntergezogen.
        """
        # Hoeher ansetzen und flacher enden. Vorher reichten die
        # Schlaefen bis cy-14, die Augenoberkante liegt aber bei cy-17.6 -
        # jede Frisur hing also in den Augen und wirkte gequetscht. Nach
        # oben ist Platz, also faengt die Haube weiter oben an und behaelt
        # trotzdem ihr Volumen.
        breite = r_w + 3
        hoehe = 44 * tiefe
        unten = hy - 10 + hoehe
        draw.chord([cx - breite, hy - 6, cx + breite, hy - 6 + hoehe * 2],
                   180, 360, fill=color)

        # Die Haarlinie darf nicht schnurgerade quer laufen - so sieht es
        # nach aufgesetzter Peruecke aus. An den Schlaefen zieht sie
        # tiefer, in der Mitte hoeher: das ist die Form, an der man Haare
        # erkennt, ohne sie einzeln zeichnen zu muessen.
        for seite in (-1, 1):
            tx = cx + seite * breite * 0.68
            draw.ellipse([tx - breite * 0.34, unten - 14,
                          tx + breite * 0.34, unten + 4], fill=color)
        # Sanfte Woelbung dazwischen
        draw.chord([cx - breite * 0.46, unten - 16,
                    cx + breite * 0.46, unten + 2], 0, 180, fill=color)
        return unten

    # ----------------------------------------------------------
    def draw_hair_peruecke(self, draw, hx, hy, cx, r_w, color, dark, light,
                           ox, oy):
        """
        Die weisse Peruecke fuer CLASSIC.

        Kein Stil, den man im Dashboard waehlen kann - sie gehoert dem
        Mood, so wie der Rasta-Hut dem Reggae gehoert. Ein Mood darf die
        Frisur ueberschreiben, weil sie in dem Moment ein Kostuem ist
        und keine Frisur.

        Was sie erkennbar macht, sind die Rollen ueber den Ohren: drei
        gestapelte Wuelste je Seite, die deutlich ueber den Kopf
        hinausstehen. Ohne sie waere es nur helles Haar.
        """
        unten = self._kappe(draw, cx, hy, r_w, color, tiefe=0.78)

        # Volumen oben - die Peruecke sitzt hoch
        draw.ellipse([cx - r_w * 0.72, hy - 18, cx + r_w * 0.72, hy + 18],
                     fill=color)

        # Seitliche Rollen
        for seite in (-1, 1):
            rx = cx + seite * (r_w + 6)
            for i in range(3):
                # Etwas hoeher angesetzt: die unterste Rolle reichte bis
                # auf 2 px an die Augen heran und wirkte gequetscht.
                ry = unten - 24 + i * 12
                rr = 13 - i * 1.5
                draw.ellipse([rx - rr - 3, ry - rr, rx + rr + 3, ry + rr],
                             fill=color)
                # Schattenkante unten, sonst verschmelzen die Rollen
                draw.arc([rx - rr - 3, ry - rr, rx + rr + 3, ry + rr],
                         0, 180, fill=dark, width=2)

        # Ein paar Glanzstriche oben, damit es nicht wie Watte wirkt
        for i in (-1, 0, 1):
            gx = cx + i * 18
            draw.arc([gx - 12, hy - 14, gx + 12, hy + 8],
                     200, 340, fill=light, width=2)

    # ----------------------------------------------------------
    def draw_hair_kurz(self, draw, hx, hy, cx, r_w, color, dark, light, ox, oy):
        """Kurzhaarschnitt: knappe Haube, die der Kopfform folgt."""
        unten = self._kappe(draw, cx, hy, r_w, color, tiefe=0.72)
        # Straehnen, die nach vorn zeigen
        for i in range(-3, 4):
            sx = cx + i * (r_w * 0.26) + ox * 0.3
            draw.line([sx, hy + 4, sx + 5, unten - 8], fill=dark, width=2)
        draw.arc([cx - r_w + 4, hy - 2, cx + 4, unten - 4], 195, 300,
                 fill=light, width=3)

    # ----------------------------------------------------------
    def draw_hair_strubbel(self, draw, hx, hy, cx, r_w, color, dark, light, ox, oy):
        """Strubbelkopf: unregelmaessige Zacken, wirkt lebendig."""
        unten = self._kappe(draw, cx, hy, r_w, color, tiefe=0.70)
        zacken = ((-0.88, 15, 8), (-0.55, 25, 10), (-0.2, 19, 9),
                  (0.15, 27, 10), (0.5, 17, 8), (0.85, 22, 9))
        for rel, hoehe, breite in zacken:
            zx = cx + rel * r_w + ox * 0.4
            zy = hy + 2
            draw.polygon([
                (zx - breite, zy + 8), (zx + breite, zy + 8),
                (zx + breite * 0.3, zy - hoehe + oy * 0.2),
            ], fill=color)
        draw.arc([cx - r_w + 2, hy, cx - 2, unten - 6], 190, 300, fill=dark, width=3)

    # ----------------------------------------------------------
    def draw_hair_scheitel(self, draw, hx, hy, cx, r_w, color, dark, light, ox, oy):
        """Seitenscheitel: glatt gelegt, mit Volumen ueber dem Scheitel."""
        self._kappe(draw, cx, hy, r_w, color, tiefe=0.78)
        sx = cx - r_w * 0.34
        # Die gelegte Partie: nach rechts geschwungen, mit Volumen
        draw.chord([sx - 6, hy - 16, cx + r_w + 6, hy + 42], 180, 360, fill=color)
        draw.rectangle([sx - 6, hy + 10, cx + r_w + 6, hy + 16], fill=color)
        # Der Scheitel selbst
        draw.line([sx, hy - 8, sx - 5, hy + 22], fill=dark, width=3)
        draw.arc([sx + 10, hy - 12, cx + r_w - 4, hy + 30], 200, 320,
                 fill=light, width=3)

    # ----------------------------------------------------------
    def draw_hair_locken(self, draw, hx, hy, cx, r_w, color, dark, light, ox, oy):
        """Lockenkopf: runde Locken ueber der ganzen Kuppel."""
        self._kappe(draw, cx, hy, r_w, color, tiefe=0.68)
        reihen = (
            ((-0.92, -0.6, -0.25, 0.1, 0.45, 0.8), hy + 2, 12),
            ((-0.68, -0.3, 0.08, 0.45, 0.8), hy - 10, 11),
            ((-0.4, 0.0, 0.4), hy - 20, 10),
        )
        for spalten, ly, radius in reihen:
            for rel in spalten:
                lx = cx + rel * r_w + ox * 0.3
                y = ly + oy * 0.2
                draw.ellipse([lx - radius, y - radius, lx + radius, y + radius],
                             fill=color)
                draw.arc([lx - radius + 3, y - radius + 3,
                          lx + radius - 3, y + radius - 3],
                         170, 330, fill=light, width=2)

    # ----------------------------------------------------------
    def draw_hair_pony(self, draw, hx, hy, cx, r_w, color, dark, light, ox, oy):
        """Pony: Haube mit gerader Fransenreihe ueber der Stirn."""
        unten = self._kappe(draw, cx, hy, r_w, color, tiefe=0.62)
        for i in range(8):
            fx = cx - r_w + 2 + i * (r_w * 2 - 4) / 7.0 + ox * 0.25
            laenge = 8 if i % 2 == 0 else 12
            draw.polygon([
                (fx - 7, unten - 6), (fx + 7, unten - 6),
                (fx + 4, unten + laenge), (fx - 4, unten + laenge),
            ], fill=color)
        draw.arc([cx - r_w + 4, hy - 2, cx + 6, unten - 10], 195, 305,
                 fill=light, width=3)

    # ----------------------------------------------------------
    def draw_hair_punk(self, draw, hx, hy, cx, r_w, color, dark, light, ox, oy):
        """Irokese: mittige Spitzen, Seiten kurz rasiert."""
        # Seiten rasiert: nur ein schmaler dunkler Saum, keine Haube
        draw.chord([cx - r_w - 3, hy + 2, cx + r_w + 3, hy + 58],
                   180, 360, fill=dark)
        # Der Kamm in der Mitte
        draw.chord([cx - r_w * 0.34, hy - 4, cx + r_w * 0.34, hy + 50],
                   180, 360, fill=color)
        spitzen = ((-0.30, 20), (-0.15, 30), (0.0, 36), (0.15, 30), (0.30, 20))
        for rel, hoehe in spitzen:
            px = cx + rel * r_w + ox * 0.5
            draw.polygon([
                (px - 9, hy + 12), (px + 9, hy + 12),
                (px + 2 + ox * 0.3, hy + 8 - hoehe + oy * 0.3),
            ], fill=color)
        draw.line([cx - r_w * 0.32, hy + 10, cx + r_w * 0.32, hy + 10],
                  fill=light, width=2)

    # ----------------------------------------------------------
    def draw_hair_zopf(self, draw, hx, hy, cx, r_w, color, dark, light, ox, oy):
        """Zopf: glatte Haube mit gebundenem Schwanz, der mitschwingt."""
        unten = self._kappe(draw, cx, hy, r_w, color, tiefe=0.74)
        zx = cx + r_w - 4 + ox * 0.6
        zy = hy + 20
        for i in range(4):
            gy = zy + i * 14
            gx = zx + 10 + int(5 * math.sin(self.frame * 0.09 + i * 0.7)) + ox * 0.3
            radius = 10 - i
            draw.ellipse([gx - radius, gy - radius, gx + radius, gy + radius],
                         fill=color)
        draw.rectangle([zx + 3, zy - 2, zx + 17, zy + 4], fill=light)
        draw.arc([cx - r_w + 4, hy - 2, cx + 4, unten - 6], 195, 300,
                 fill=light, width=3)

    # ----------------------------------------------------------
    # Augen (Default + Overrides)
    # ----------------------------------------------------------
    def draw_swirl_eyes(self, draw, cx, cy, r):
        """
        Wirbel statt Pupillen - der klassische "mir schwirrt der Kopf".
        Wird nur vom Chaos-Mood benutzt und ist bewusst albern.
        """
        eye_y = cy - r * 0.12
        abstand = r * 0.38
        for s_ in (-1, 1):
            ex = cx + s_ * abstand
            draw.ellipse([ex - 11, eye_y - 11, ex + 11, eye_y + 11], fill=WHITE)
            # Spirale aus drei Boegen, dreht sich
            phase = self.frame * 6 * s_
            for k, rad in enumerate((9, 6, 3)):
                start = (phase + k * 120) % 360
                draw.arc([ex - rad, eye_y - rad, ex + rad, eye_y + rad],
                         start, start + 250, fill=EYE_COLOR, width=2)

    def draw_eyes(self, draw, cx, cy, r, blink_progress, eye_data):
        eye_y = cy - r * 0.12
        spacing = r * 0.38
        ew = r * 0.13 * eye_data.get("scale_w", 1.0)
        eh = r * 0.16 * eye_data.get("scale_h", 1.0)
        look_offset = eye_data.get("look_offset", 0)

        if eye_data.get("droopy", False):
            eh *= 0.18

        if blink_progress > 0:
            eh *= max(0.05, 1.0 - blink_progress)

        for s in [-1, 1]:
            ex = cx + s * spacing + look_offset
            draw.ellipse([ex - ew, eye_y - eh, ex + ew, eye_y + eh], fill=EYE_COLOR)
            if eh > r * 0.08 and blink_progress < 0.3:
                gr = ew * 0.35
                gx = ex - ew * 0.3
                gy = eye_y - eh * 0.3
                draw.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=WHITE)

    # ----------------------------------------------------------
    # Mund (Default + Overrides)
    # ----------------------------------------------------------
    def draw_mouth(self, draw, cx, cy, r, mouth_data, mood_id):
        my = cy + r * 0.22
        style = mouth_data.get("style", "smile")
        w = mouth_data.get("width", 1.0)
        mw = r * 0.15 * w

        if style == "grin":
            draw.chord([cx - 18, my - 5, cx + 18, my + 22], 0, 180, fill=EYE_COLOR)
        elif style == "open_round":
            draw.ellipse([cx - 8, my + 2, cx + 8, my + 18], fill=EYE_COLOR)
        elif style == "frown":
            draw.arc([cx - 12, my + 5, cx + 12, my + 20], 180, 360, fill=EYE_COLOR, width=4)
        elif style == "line":
            draw.line([cx - 8, my + 8, cx + 8, my + 8], fill=EYE_COLOR, width=3)
        elif style == "smirk":
            draw.arc([cx - 10, my, cx + 10, my + 12], 0, 180, fill=EYE_COLOR, width=3)
            draw.line([cx + 12, my + 4, cx + 18, my + 2], fill=(255, 100, 200), width=2)
        elif style == "yawn":
            draw.ellipse([cx - 12, my, cx + 12, my + 28], fill=EYE_COLOR)
        elif style == "tongue":
            draw.arc([cx - 15, my, cx + 15, my + 20], 0, 180, fill=EYE_COLOR, width=4)
            draw.ellipse([cx - 6, my + 12, cx + 6, my + 24], fill=(220, 80, 80))
        elif style == "squiggle":
            # Zickzack-Mund: ueberfordert, "was passiert hier gerade"
            punkte = []
            for i in range(7):
                px = cx - 12 + i * 4
                py = my + 6 + (4 if i % 2 else -2)
                punkte.append((px, py))
            draw.line(punkte, fill=EYE_COLOR, width=3, joint="curve")

        elif style == "sip":
            sz = 3 + int(math.sin(self.frame * 0.2) * 2)
            draw.ellipse([cx - sz, my + 5, cx + sz, my + 5 + sz * 2], fill=EYE_COLOR)
        elif style == "chewing":
            phase = math.sin(self.frame * 0.4)
            mh = int(6 + phase * 4)
            draw.ellipse([cx - 8, my + 2, cx + 8, my + 2 + mh], fill=EYE_COLOR)
        elif style == "focused":
            draw.line([cx - 10, my + 8, cx + 10, my + 8], fill=EYE_COLOR, width=3)
            draw.line([cx - 6, my + 5, cx - 6, my + 11], fill=EYE_COLOR, width=2)
        elif style == "concerned":
            draw.arc([cx - 10, my + 3, cx + 10, my + 18], 200, 340, fill=EYE_COLOR, width=3)
        elif style == "neutral":
            draw.line([cx - 8, my + 8, cx + 8, my + 8], fill=EYE_COLOR, width=2)
        else:  # smile (default)
            draw.arc([cx - mw, my - mw * 0.4, cx + mw, my + mw * 0.4],
                     0, 180, fill=EYE_COLOR, width=4)

    # ----------------------------------------------------------
    # Accessoires
    # ----------------------------------------------------------
    def draw_accessory(self, draw, cx, cy, r_w, r_h, acc_type, mood_id):
        if acc_type is None:
            return

        if acc_type == "rasta_hat":
            r = r_w
            draw.ellipse([cx - r - 16, cy - r - 42, cx + r + 16, cy - r + 12],
                         fill=(255, 0, 0))
            draw.rectangle([cx - r - 9, cy - r - 26, cx + r + 9, cy - r - 11],
                           fill=(255, 255, 0))
            draw.rectangle([cx - r - 9, cy - r - 11, cx + r + 9, cy - r + 6],
                           fill=(0, 180, 0))
            for i in range(-3, 4):
                dx = cx + i * 22
                sway = math.sin(self.frame * 0.1) * 13
                draw.line([dx, cy - r + 6, dx + sway, cy + r + 12],
                          fill=(50, 40, 30), width=9)

        elif acc_type == "gold_chain":
            swing = math.sin(self.frame * 0.4) * 18
            draw.arc([cx - r_w - 5, cy + 12, cx + r_w + 5, cy + r_w + 22],
                     0, 180, fill=GOLD, width=4)
            mx = cx + swing
            my = cy + r_w + 16
            draw.ellipse([mx - 10, my - 10, mx + 10, my + 10], fill=GOLD, outline=WHITE)
            draw.text((mx - 4, my - 7), "$", fill=BLACK)

        elif acc_type == "saxophone":
            # Was ein Saxophon ausmacht, ist die Silhouette: vom Mund ein
            # duenner Hals nach rechts unten, ein dickerer Korpus, unten
            # der U-Bogen und daraus der weit geoeffnete Trichter nach
            # rechts oben. Genau in dieser Reihenfolge gezeichnet, sonst
            # liest es sich als Krummstab.
            #
            # Die Klappen laufen als Lichtpunkte den Korpus hinunter -
            # das ist die Bewegung, die "gespielt" bedeutet; ein
            # stillstehendes Instrument sieht aus wie ein Requisit.
            mx, my = cx + 6, cy + r_h * 0.24
            takt = math.sin(self.frame * 0.12)

            hals_ende = (cx + 30, cy + r_h * 0.42)
            korpus_ende = (cx + 40, cy + r_h * 0.92)
            bogen_ende = (cx + 52, cy + r_h * 0.86)

            # Mundstueck am Mund
            draw.line([mx, my, mx + 9, my + 5], fill=(40, 38, 42), width=7)
            # Hals
            draw.line([mx + 8, my + 4, hals_ende[0], hals_ende[1]],
                      fill=BRASS_DARK, width=7)
            # Korpus
            draw.line([hals_ende[0], hals_ende[1],
                       korpus_ende[0], korpus_ende[1]],
                      fill=BRASS, width=11)
            # U-Bogen nach rechts
            draw.arc([korpus_ende[0] - 12, korpus_ende[1] - 16,
                      bogen_ende[0] + 4, korpus_ende[1] + 12],
                     0, 180, fill=BRASS, width=11)

            # Trichter: als Polygon, damit die Oeffnung wirklich breit
            # wird. Eine dicke Linie bliebe ein Rohr.
            tx, ty = bogen_ende
            draw.polygon([(tx - 6, ty + 7), (tx + 6, ty + 9),
                          (tx + 30, ty - 29), (tx + 4, ty - 34)],
                         fill=BRASS)
            draw.line([(tx + 4, ty - 34), (tx + 30, ty - 29)],
                      fill=BRASS_LIGHT, width=3)

            # Klappen
            for i in range(4):
                kx = hals_ende[0] + (korpus_ende[0] - hals_ende[0]) * i / 3.5
                ky = hals_ende[1] + (korpus_ende[1] - hals_ende[1]) * i / 3.5
                hell = (int(self.frame * 0.25) + i) % 4 == 0
                farbe = BRASS_LIGHT if hell else BRASS_DARK
                draw.ellipse([kx - 3, ky - 3, kx + 3, ky + 3], fill=farbe)

            # Die Noten kommen aus dem Trichter, nicht aus dem Kopf
            self.particle_origin = (tx + 20 + takt * 3, ty - 30)

        elif acc_type == "drink":
            # Ein Becher in der Hand, der beim Tanzen kippt und ueberschwappt.
            # Der Witz ist die Neigung: ein senkrechtes Glas sieht aus wie
            # ein Moebelstueck, ein schraeges gehoert zu jemandem, der sich
            # bewegt.
            kipp = math.sin(self.frame * 0.30)
            bx = cx + r_w * 0.86
            by = cy + r_h * 0.12
            bh, bw = 38, 15
            # Kraeftig genug, dass die Neigung auch im Standbild auffaellt
            versatz = kipp * 14         # Wie weit der obere Rand auswandert

            oben_l = (bx - bw + versatz, by - bh / 2)
            oben_r = (bx + bw + versatz, by - bh / 2)
            unten_r = (bx + bw * 0.72, by + bh / 2)
            unten_l = (bx - bw * 0.72, by + bh / 2)

            draw.polygon([oben_l, oben_r, unten_r, unten_l], fill=(228, 232, 240))
            # Inhalt: bis knapp unter den Rand, in Bernstein
            fuell = 0.72
            il = (oben_l[0] + (unten_l[0] - oben_l[0]) * (1 - fuell),
                  oben_l[1] + bh * (1 - fuell))
            ir = (oben_r[0] + (unten_r[0] - oben_r[0]) * (1 - fuell),
                  oben_r[1] + bh * (1 - fuell))
            draw.polygon([il, ir, unten_r, unten_l], fill=(236, 168, 40))
            # Schaumkrone
            draw.ellipse([il[0] - 2, il[1] - 7, ir[0] + 2, il[1] + 3],
                         fill=(252, 250, 244))
            # Henkel
            draw.arc([oben_r[0] - 4, oben_r[1] + 6, oben_r[0] + 14,
                      oben_r[1] + 26], 270, 90, fill=(228, 232, 240), width=3)

            # Ueberschwappen, wenn es wirklich schwingt
            if abs(kipp) > 0.6 and random.random() < 0.6:
                seite = 1 if kipp > 0 else -1
                self.particles.spawn(
                    (oben_r[0] if seite > 0 else oben_l[0]) + seite * 2,
                    oben_l[1] + random.randint(-2, 4),
                    "drop", (236, 168, 40))

        elif acc_type == "ear_muffs":
            # Gehoerschutz, nicht Kopfhoerer. Der Unterschied muss man
            # sehen: dickere Kapseln, Signalfarbe, und der Buegel liegt
            # obenauf statt dahinter.
            kapsel = (245, 180, 30)
            kante = (170, 110, 10)
            polster = (60, 58, 62)
            by = cy - r_h * 0.06

            # Der Buegel liegt der Kopfkuppel auf, er schwebt nicht
            # darueber
            draw.arc([cx - r_w - 3, cy - r_h - 14, cx + r_w + 3, cy - r_h + 40],
                     180, 360, fill=kapsel, width=10)
            draw.arc([cx - r_w - 3, cy - r_h - 14, cx + r_w + 3, cy - r_h + 40],
                     190, 260, fill=kante, width=3)
            for seite in (-1, 1):
                kx = cx + seite * (r_w + 2)
                draw.rounded_rectangle([kx - 13, by - 20, kx + 13, by + 20],
                                       radius=8, fill=kapsel, outline=kante,
                                       width=2)
                draw.rounded_rectangle([kx - 7, by - 13, kx + 7, by + 13],
                                       radius=5, fill=polster)

        elif acc_type == "jackhammer":
            # Der Presslufthammer steht auf dem Boden und schlaegt zu.
            # Er zittert im eigenen Takt - schneller als der Koerper, der
            # ueber shake_x/shake_y mitgeht.
            takt = math.sin(self.frame * 1.7)
            schlag = takt > 0.4
            # Weit genug nach aussen: mittig verdeckte er das rechte
            # Auge, und ein Werkzeug vor dem Gesicht nimmt dem Mochi
            # den Ausdruck.
            zx = cx + r_w * 0.92 + takt * 2
            oben = cy - r_h * 0.30
            unten = cy + r_h + 22

            rot = (214, 44, 38)          # Signalrot, wie am Bau ueblich
            rot_dunkel = (150, 24, 20)
            stahl = (188, 192, 198)
            stahl_dunkel = (120, 124, 132)

            # Meissel bis auf den Boden
            draw.rectangle([zx - 4, unten - 34, zx + 4, unten],
                           fill=stahl, outline=stahl_dunkel)
            # Korpus
            draw.rounded_rectangle([zx - 13, oben + 16, zx + 13, unten - 30],
                                   radius=5, fill=rot, outline=rot_dunkel,
                                   width=2)
            draw.line([zx - 7, oben + 24, zx - 7, unten - 38],
                      fill=(255, 120, 110), width=2)
            # Griffe
            draw.rounded_rectangle([zx - 18, oben + 6, zx + 18, oben + 17],
                                   radius=5, fill=(45, 44, 48))
            draw.rounded_rectangle([zx - 6, oben, zx + 6, oben + 10],
                                   radius=3, fill=rot_dunkel)
            # Druckluftschlauch
            for i in range(4):
                sx = zx + 14 + i * 6
                sy = oben + 22 + math.sin(self.frame * 0.2 + i) * 3 + i * 5
                draw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3],
                             fill=(70, 70, 78))

            # Aufschlag: heller Blitz und Staub am Meissel
            if schlag:
                draw.line([zx - 12, unten, zx + 12, unten],
                          fill=(255, 240, 190), width=3)
                for seite in (-1, 1):
                    draw.line([zx + seite * 5, unten - 2,
                               zx + seite * 15, unten - 9],
                              fill=(255, 225, 160), width=2)

            # Die Brocken fliegen vom Meissel weg, nicht vom Kopf
            self.particle_origin = (zx, unten - 6)

        elif acc_type == "sunglasses":
            # Zwei dunkle Glaeser mit Steg, dazu ein Glanzstrich - ohne
            # den sieht die Brille aus wie zwei Loecher im Gesicht.
            ay = cy - r_h * 0.06
            gb, gh = 22, 17          # Glasbreite, Glashoehe
            versatz = 21
            for seite in (-1, 1):
                gx = cx + seite * versatz
                draw.rounded_rectangle(
                    [gx - gb / 2, ay - gh / 2, gx + gb / 2, ay + gh / 2],
                    radius=5, fill=(18, 18, 26), outline=(60, 62, 78), width=2)
                draw.line([gx - gb / 2 + 4, ay + 3, gx - 1, ay - gh / 2 + 4],
                          fill=(120, 170, 210), width=2)
            draw.line([cx - versatz + gb / 2, ay - 2,
                       cx + versatz - gb / 2, ay - 2],
                      fill=(30, 30, 40), width=3)
            # Buegel nach aussen
            for seite in (-1, 1):
                draw.line([cx + seite * (versatz + gb / 2), ay - 3,
                           cx + seite * (r_w - 2), ay - 6],
                          fill=(30, 30, 40), width=3)

        elif acc_type == "frost":
            # Vereiste Adern auf dem Koerper und ein paar Zapfen an der
            # Unterkante. Kein Speiseeis - der Mochi ist cool, nicht am
            # Naschen. Die Adern verzweigen sich zufaellig, aber mit
            # festem Startwert, damit sie nicht jeden Frame neu zucken.
            eis = (196, 238, 255)
            eis_hell = (238, 250, 255)
            zufall = random.Random(mood_id * 977)
            atmen = 0.85 + 0.15 * math.sin(self.frame * 0.05)

            # Die Adern bleiben im Aussenbereich und meiden das Gesicht.
            # Quer ueber Augen und Mund sahen sie nach Sprung in der
            # Scheibe aus, nicht nach Frost auf einem Koerper.
            for _ in range(6):
                winkel = zufall.uniform(0, math.tau)
                if -2.4 < winkel < -0.7:          # oberer Gesichtsbereich
                    winkel += math.pi
                ax = cx + math.cos(winkel) * r_w * zufall.uniform(0.58, 0.82)
                ay = cy + math.sin(winkel) * r_h * zufall.uniform(0.55, 0.8)
                richtung = zufall.uniform(0, math.tau)
                laenge = zufall.uniform(9, 16) * atmen
                for tiefe in range(3):
                    bx = ax + math.cos(richtung) * laenge
                    by = ay + math.sin(richtung) * laenge
                    draw.line([ax, ay, bx, by], fill=eis,
                              width=max(1, 3 - tiefe))
                    if tiefe == 1:      # kleine Verzweigung
                        sx = ax + math.cos(richtung + 0.9) * laenge * 0.6
                        sy = ay + math.sin(richtung + 0.9) * laenge * 0.6
                        draw.line([ax, ay, sx, sy], fill=eis, width=1)
                    ax, ay = bx, by
                    richtung += zufall.uniform(-0.6, 0.6)
                    laenge *= 0.7

            # Zapfen an der Unterkante. Sie muessen wirklich AM Rand
            # haengen - weiter innen sahen sie aus wie Zaehne unter dem
            # Mund. Deshalb sitzen sie exakt auf der Koerperellipse und
            # ragen darueber hinaus.
            for i, anteil in enumerate((-0.82, -0.48, -0.12, 0.3, 0.66)):
                zx = cx + anteil * r_w
                zy = cy + math.sqrt(max(0.0, 1 - anteil * anteil)) * r_h - 2
                lang = (8 + (i % 3) * 6) * atmen
                breit = 3.5 - (i % 2) * 0.8
                draw.polygon([(zx - breit, zy - 4), (zx + breit, zy - 4),
                              (zx, zy + lang)], fill=eis)
                draw.line([(zx - 1, zy - 2), (zx, zy + lang * 0.6)],
                          fill=eis_hell, width=1)

        elif acc_type == "devil_sign":
            # Zeigefinger und kleiner Finger hoch, die mittleren beiden
            # vom Daumen gehalten. Bei 240x240 zaehlt nur die Silhouette:
            # zwei klar getrennte Spitzen ueber einer Faust.
            hand = (255, 214, 170)
            kontur = (168, 120, 78)
            # Neben den Kopf, nicht hinein: im ersten Anlauf lag die Hand
            # ueber Haaren und Kopfhoererbuegel und war nicht zu erkennen.
            # Sie braucht Abstand zum Koerperrand.
            hx = cx + r_w + 22
            hy = cy - r_h * 0.02 - abs(math.sin(self.frame * 0.42)) * 7

            # Faust
            draw.rounded_rectangle([hx - 15, hy, hx + 15, hy + 26],
                                   radius=8, fill=hand, outline=kontur, width=2)
            # Zeigefinger und kleiner Finger
            # Kuerzer als im ersten Anlauf: mit 26 px standen die Finger
            # laenger vom Bild ab als die Faust hoch war - das sah nach
            # Krallen aus.
            for seite in (-1, 1):
                fx = hx + seite * 10
                draw.rounded_rectangle([fx - 5, hy - 15, fx + 5, hy + 6],
                                       radius=5, fill=hand, outline=kontur,
                                       width=2)
            # Daumen quer ueber die eingeklappten Finger. Kurz gab es die
            # Variante mit abgespreiztem Daumen - das ist eine andere
            # Geste. Hier sind es die reinen Hoerner.
            draw.rounded_rectangle([hx - 7, hy + 8, hx + 14, hy + 18],
                                   radius=5, fill=hand, outline=kontur, width=2)

        elif acc_type == "sheet_music":
            # Ein Notenblatt vor dem Mochi. Das Klavier bleibt unsichtbar -
            # es liegt unterhalb des Bildrands, und genau deshalb steigen
            # die Noten hinter dem Blatt auf: man denkt es sich dazu.
            # Tief genug, dass Augen UND Mund frei bleiben - ein Blatt
            # vor dem Gesicht nimmt dem Mochi den Ausdruck.
            bw, bh = 78, 38
            bx = cx
            by = cy + r_h * 1.02
            wiegen = math.sin(self.frame * 0.06) * 2

            draw.polygon([(bx - bw / 2 + wiegen, by - bh / 2),
                          (bx + bw / 2 + wiegen, by - bh / 2),
                          (bx + bw / 2, by + bh / 2),
                          (bx - bw / 2, by + bh / 2)],
                         fill=(248, 246, 238), outline=(190, 186, 172))
            # Notenlinien
            for i in range(5):
                ly = by - bh / 2 + 9 + i * 6
                anteil = (ly - (by - bh / 2)) / bh
                lx = wiegen * (1 - anteil)
                draw.line([bx - bw / 2 + 6 + lx, ly, bx + bw / 2 - 6 + lx, ly],
                          fill=(120, 118, 110), width=1)
            # Ein paar Notenkoepfe, die im Takt wandern
            for i in range(4):
                nx = bx - bw / 2 + 14 + i * 15 + wiegen * 0.5
                ny = by - bh / 2 + 12 + ((int(self.frame * 0.1) + i) % 4) * 6
                draw.ellipse([nx - 3, ny - 2, nx + 3, ny + 2], fill=(40, 40, 48))
                draw.line([nx + 3, ny - 1, nx + 3, ny - 10],
                          fill=(40, 40, 48), width=1)

            # Die aufsteigenden Noten kommen hinter dem Blatt hervor
            self.particle_origin = (bx + random.randint(-26, 26), by - bh / 2 - 2)

        elif acc_type == "keyboard":
            for i in range(4):
                kx = cx - 45 + i * 28
                ky = cy + 42
                pressed = (int(self.frame) + i * 4) % 16 < 5
                yoff = 3 if pressed else 0
                draw.rectangle([kx, ky + yoff, kx + 22, ky + 10 + yoff],
                               outline=WHITE, width=2)

        elif acc_type == "joint":
            # Vorher: ein weisser Balken mit rotem Punkt - das las sich als
            # Strohhalm. Was einen Joint ausmacht, ist die konische Form
            # (hinten duenn gedreht, vorne dicker), die Papiernaht und
            # die gluehende Spitze mit hellem Kern.
            # Position folgt dem Zug: am Mund, wenn gezogen wird,
            # sonst tiefer und weiter aussen abgelegt.
            vx, vy = self.toke_versatz("joint")
            jx, jy = cx + 4 + vx, cy + 6 + vy
            laenge = 34

            # Papier, leicht konisch: hinten 6 px, vorne 10 px hoch
            draw.polygon([
                (jx, jy + 2), (jx + laenge, jy - 1),
                (jx + laenge, jy + 10), (jx, jy + 8),
            ], fill=(245, 243, 235))
            # Schattenkante unten, damit es rund wirkt
            draw.line([jx, jy + 8, jx + laenge, jy + 10], fill=(190, 188, 180), width=1)
            # Gedrehtes Ende
            draw.line([jx, jy + 2, jx - 5, jy + 6], fill=(235, 233, 225), width=2)
            draw.line([jx, jy + 8, jx - 5, jy + 6], fill=(215, 213, 205), width=2)
            # Papiernaht
            draw.line([jx + 8, jy + 3, jx + 8, jy + 9], fill=(205, 200, 185), width=1)

            # Asche vor der Glut
            draw.polygon([
                (jx + laenge, jy - 1), (jx + laenge + 5, jy),
                (jx + laenge + 5, jy + 10), (jx + laenge, jy + 10),
            ], fill=(120, 118, 115))

            # Glut folgt dem Zug: beim Ziehen deutlich heller
            glut = 0.45 + 0.55 * self.toke_ember
            ex = jx + laenge + 5
            draw.ellipse([ex, jy, ex + 8, jy + 10],
                         fill=(int(200 * glut), int(60 * glut), 0))
            draw.ellipse([ex + 2, jy + 3, ex + 6, jy + 7],
                         fill=(255, int(170 * glut), int(60 * glut)))

        elif acc_type == "bong":
            # Was hier zu loesen war, ist eng: Auf 240x240 ist der Blob rund
            # 110 px breit, und zwischen Mund und Koerperunterkante liegen
            # etwa 35 px. Eine Bong braucht aber ueber 50. Entweder sie
            # verdeckt das Gesicht, oder das Mundstueck erreicht den Mund
            # nicht - beides gleichzeitig geht nicht.
            #
            # Vier Versuche und was sie zeigten:
            #   1. senkrechtes Roehrchen mit Kugel unten -> Thermometer
            #   2. runder Boden, duenner Hals            -> Laborkolben
            #   3. Becherbong, Kopf links                -> las sich gut,
            #      aber Noisy zog dort, wo es brennt
            #   4. stark geneigt / geknickt              -> Silhouette weg
            #
            # Der Kompromiss: aufrechter Becherbong (die Form, die man
            # erkennt), Kopf konsequent nach AUSSEN vom Gesicht weg, und
            # das Mundstueck leicht zum Mund geneigt. Damit stimmt die
            # Leserichtung - er zieht oben, es brennt aussen unten.
            glas = (215, 232, 242)
            glanz = (250, 253, 255)
            wasser = (95, 170, 200)
            innen = (26, 48, 58)

            # Position folgt dem Zug: das Mundstueck wandert an den Mund
            # und die Bong wird danach wieder abgestellt.
            vx, vy = self.toke_versatz("bong")
            fx, boden = cx + 13 + vx, cy + 62 + vy
            hals_o = cy + 10 + vy

            # --- Becherboden ---
            b_u, b_o, b_h = 18, 11, 22
            draw.polygon([
                (fx - b_u, boden), (fx + b_u, boden),
                (fx + b_o, boden - b_h), (fx - b_o, boden - b_h),
            ], fill=innen)
            w_y = boden - 11
            draw.polygon([
                (fx - b_u + 2, boden - 2), (fx + b_u - 2, boden - 2),
                (fx + 13, w_y), (fx - 13, w_y),
            ], fill=wasser)
            draw.line([fx - 13, w_y, fx + 13, w_y], fill=glanz, width=2)
            draw.line([fx - b_u, boden, fx - b_o, boden - b_h], fill=glas, width=3)
            draw.line([fx + b_u, boden, fx + b_o, boden - b_h], fill=glas, width=3)
            draw.line([fx - b_u, boden, fx + b_u, boden], fill=glas, width=3)

            # --- Rohr, oben leicht zum Mund geneigt ---
            neig = 7                      # px Versatz nach links oben
            r_u, r_o = 7, 6
            ox = fx - neig
            draw.polygon([
                (fx - r_u, boden - b_h), (fx + r_u, boden - b_h),
                (ox + r_o, hals_o), (ox - r_o, hals_o),
            ], fill=innen)
            draw.line([fx - r_u, boden - b_h, ox - r_o, hals_o], fill=glas, width=3)
            draw.line([fx + r_u, boden - b_h, ox + r_o, hals_o], fill=glas, width=3)
            for ky in (boden - b_h - 7, boden - b_h - 14):
                t = (boden - b_h - ky) / float(b_h + 2)
                mxk = fx - neig * t
                draw.line([mxk - r_o - 2, ky, mxk - 2, ky + 3], fill=glas, width=2)
                draw.line([mxk + r_o + 2, ky, mxk + 2, ky + 3], fill=glas, width=2)

            # --- Mundstueck: ausgestellt, zeigt zum Gesicht ---
            draw.polygon([
                (ox - r_o, hals_o), (ox + r_o, hals_o),
                (ox + r_o + 3, hals_o - 6), (ox - r_o - 5, hals_o - 6),
            ], fill=innen)
            draw.line([ox - r_o - 5, hals_o - 6, ox + r_o + 3, hals_o - 6],
                      fill=glanz, width=3)

            # --- Downstem + Kegelkopf: nach AUSSEN, weg vom Gesicht ---
            dx1, dy1 = fx + 7, boden - b_h + 4
            dx2, dy2 = fx + 25, boden - b_h - 6
            draw.line([dx1, dy1, dx2, dy2], fill=glas, width=4)
            draw.polygon([
                (dx2 - 8, dy2 - 7), (dx2 + 9, dy2 - 7),
                (dx2 + 4, dy2 + 3), (dx2 - 3, dy2 + 3),
            ], fill=(74, 96, 108), outline=glas)
            draw.line([dx2 - 8, dy2 - 7, dx2 + 9, dy2 - 7], fill=glanz, width=2)
            # Glut folgt dem Zug: beim Ziehen deutlich heller
            glut = 0.4 + 0.6 * self.toke_ember
            draw.ellipse([dx2 - 4, dy2 - 6, dx2 + 5, dy2 - 1],
                         fill=(255, int(70 + 130 * glut), int(20 + 40 * glut)))

            # --- Blasen ---
            for i in range(4):
                phase = (self.frame * 0.14 + i * 1.7) % 5.0
                by = boden - 3 - phase * 2.2
                if by > w_y:
                    bxx = fx - 7 + i * 5
                    r = 2 if i % 2 == 0 else 1
                    draw.ellipse([bxx - r, by - r, bxx + r, by + r], fill=glanz)

        elif acc_type == "coffee":
            # Tasse tiefer gesetzt: der Dampf stand vorher mitten im Auge
            # und sah aus wie ein Fleck im Gesicht.
            tx, ty = cx + 24, cy + 16
            draw.rectangle([tx, ty, tx + 24, ty + 22],
                           fill=(240, 240, 240), outline=WHITE)
            draw.arc([tx + 22, ty + 4, tx + 34, ty + 16], -90, 90, fill=WHITE, width=2)
            # Kaffeespiegel
            draw.rectangle([tx + 3, ty + 3, tx + 21, ty + 7], fill=(90, 55, 30))
            # Dampf steigt ueber der Tasse, zwei versetzte Faehnchen
            for i, versatz in enumerate((4, 13)):
                if int(self.frame + i * 6) % 20 < 12:
                    dy = ty - 6 - ((int(self.frame) + i * 6) % 20) // 4
                    draw.text((tx + versatz, dy), "~", fill=(210, 210, 210))

        elif acc_type == "watch":
            draw.line([cx + 28, cy + 22, cx + 48, cy + 8], fill=WHITE, width=3)
            draw.ellipse([cx + 42, cy + 2, cx + 56, cy + 16], fill=WHITE)
            draw.line([cx + 49, cy + 9, cx + 49, cy + 4], fill=BLACK, width=1)
            draw.line([cx + 49, cy + 9, cx + 53, cy + 9], fill=BLACK, width=1)

        elif acc_type == "remote":
            # Fernbedienung: Noisy schaut mit. Leicht schraeg gehalten,
            # mit blinkender Sende-LED, damit man sie als solche erkennt.
            rx, ry = cx + 26, cy + 16
            draw.rounded_rectangle([rx, ry, rx + 16, ry + 40], radius=4,
                                   fill=(45, 45, 55), outline=(190, 190, 200), width=2)
            # Tastenfeld
            for reihe in range(3):
                for spalte in range(2):
                    tx = rx + 4 + spalte * 6
                    ty = ry + 14 + reihe * 8
                    draw.rectangle([tx, ty, tx + 3, ty + 4], fill=(150, 150, 160))
            # Ein/Aus-Taste
            draw.ellipse([rx + 5, ry + 4, rx + 11, ry + 10], fill=(200, 60, 60))
            # Sende-LED, blinkt
            if int(self.frame) % 20 < 4:
                draw.ellipse([rx + 6, ry + 42, rx + 10, ry + 46], fill=(255, 220, 120))

        elif acc_type == "big_ear":
            # Ein grosses Ohr, der Stimme zugewandt. Zuckt gelegentlich,
            # wie ein Tier, das aufmerksam wird.
            zuck = 2 if int(self.frame) % 70 < 6 else 0
            ex = cx + r_w - 4
            ey = cy - 6 - zuck
            haut = (240, 205, 180)
            innen = (205, 150, 135)
            # Aussenkontur
            draw.polygon([
                (ex, ey + 18), (ex + 6, ey - 14 - zuck),
                (ex + 26, ey - 20 - zuck), (ex + 34, ey - 2),
                (ex + 26, ey + 20), (ex + 8, ey + 24),
            ], fill=haut, outline=(200, 165, 145))
            # Ohrmuschel
            draw.polygon([
                (ex + 10, ey + 12), (ex + 13, ey - 8 - zuck),
                (ex + 24, ey - 12 - zuck), (ex + 27, ey + 2),
                (ex + 20, ey + 14),
            ], fill=innen)
            # Gehoergang
            draw.ellipse([ex + 13, ey + 2, ex + 20, ey + 12], fill=(150, 100, 92))
            # Schallwellen, die hineinlaufen
            for i in range(3):
                phase = (int(self.frame) + i * 9) % 27
                if phase < 18:
                    rad = 6 + phase
                    draw.arc([ex + 30 - rad, ey - rad, ex + 30 + rad, ey + rad],
                             300, 60, fill=(215, 240, 225), width=2)

        elif acc_type == "popcorn":
            # Gestreifte Tuete mit Puffmais. Dazu kaut er (mouth
            # "chewing") - jemand erzaehlt eine Geschichte, er lehnt sich
            # zurueck und greift zu.
            bx, by = cx + 20, cy + 14
            bb, bh = 30, 30
            # Tuete: nach unten schmaler
            draw.polygon([
                (bx, by), (bx + bb, by),
                (bx + bb - 5, by + bh), (bx + 5, by + bh),
            ], fill=(240, 240, 245), outline=(210, 210, 215))
            # Rote Streifen
            for i in range(3):
                sx = bx + 4 + i * 9
                draw.polygon([
                    (sx, by), (sx + 4, by),
                    (sx + 3, by + bh), (sx + 1, by + bh),
                ], fill=(205, 60, 60))
            # Puffmais quillt oben heraus
            kerne = ((0, -4, 6), (9, -8, 7), (19, -6, 6), (25, -2, 5), (5, -10, 5))
            for kx, ky, kr in kerne:
                draw.ellipse([bx + kx, by + ky - kr, bx + kx + kr * 2, by + ky + kr],
                             fill=(255, 240, 200))
                draw.ellipse([bx + kx + 2, by + ky - kr + 2,
                              bx + kx + kr, by + ky],
                             fill=(255, 252, 235))
            # Ab und zu fliegt einer hoch
            flug = int(self.frame) % 80
            if flug < 18:
                fy = by - 12 - flug * 1.6
                draw.ellipse([bx + 12, fy - 5, bx + 22, fy + 5],
                             fill=(255, 245, 215))

        elif acc_type == "breeze":
            # Drei Windstriche, die von links ueber den Blob ziehen und
            # die Richtung zeigen, aus der geblasen wird. Einen Ventilator
            # zu zeichnen waere albern - der stuende ja nicht auf Noisys
            # Schoss.
            for i in range(3):
                phase = (self.frame * 2.2 + i * 34) % 130
                lx = int(cx - 70 + phase)
                ly = int(cy - 24 + i * 20)
                if lx > cx + 46:
                    continue
                laenge = 16 + (i % 2) * 8
                h = 150 + int(70 * math.sin(phase * 0.05))
                farbe = (h, min(255, h + 25), min(255, h + 35))
                draw.line([lx, ly, lx + laenge, ly - 2], fill=farbe, width=2)
                if i == 1:
                    draw.arc([lx + laenge - 5, ly - 8, lx + laenge + 5, ly + 2],
                             270, 90, fill=farbe, width=2)

        elif acc_type == "gamepad":
            draw.rectangle([cx - 20, cy + 35, cx + 20, cy + 50],
                           fill=(50, 50, 60), outline=WHITE, width=2)
            draw.ellipse([cx - 12, cy + 38, cx - 6, cy + 44], fill=(200, 50, 50))
            draw.ellipse([cx + 6, cy + 38, cx + 12, cy + 44], fill=(50, 50, 200))

    # ----------------------------------------------------------
    # SAD Traene
    # ----------------------------------------------------------
    def draw_free_shapes(self, draw, shapes, layer, cx, cy, base_r):
        """Vom Sprachmodell erfundene Formen zeichnen (Regel 1a).

        Koordinaten kommen relativ (0..1) und werden hier auf die Flaeche
        gelegt. Damit ist Erfundenes von der Bildgroesse unabhaengig.
        """
        if not shapes:
            return
        W, H = self.WIDTH, self.HEIGHT
        t_now = self.frame / max(1, self.TARGET_FPS)

        for sh in shapes:
            if sh.get("layer", "front") != layer:
                continue

            ox = oy = 0.0
            scale = 1.0
            motion = sh.get("motion")
            if motion:
                amp = sh.get("amp", 0.02)
                spd = sh.get("speed", 1.0)
                ph = sh.get("phase", 0.0)
                w = math.sin(t_now * spd * 6.283 + ph)
                if motion == "bob":
                    oy = w * amp * H
                elif motion == "sway":
                    ox = w * amp * W
                elif motion == "pulse":
                    scale = 1.0 + w * amp * 2
                elif motion == "audio":
                    # Folgt der eigenen Sprachausgabe (SS4.1).
                    scale = 1.0 + self.smooth_loud * amp * 4

            col = tuple(sh.get("color", WHITE))
            outline = sh.get("outline")
            outline = tuple(outline) if outline else None
            filled = sh.get("fill", True)
            fill = col if filled else None
            line = outline or (None if filled else col)
            lw = max(1, int(sh.get("width", 0.004) * self.BASE))

            k = sh["kind"]
            try:
                if k in ("line", "polygon", "point"):
                    pts = [(sh_x * W + ox, sh_y * H + oy) for sh_x, sh_y in sh["points"]]
                    if k == "line":
                        draw.line(pts, fill=col, width=lw,
                                  joint=sh.get("joint"))
                    elif k == "polygon":
                        draw.polygon(pts, fill=fill, outline=line)
                    else:
                        for pt in pts:
                            draw.point(pt, fill=col)
                    continue

                x = sh.get("x", 0.5) * W + ox
                y = sh.get("y", 0.5) * H + oy

                if k == "circle":
                    r = sh.get("r", 0.05) * self.BASE * scale
                    draw.ellipse([x - r, y - r, x + r, y + r],
                                 fill=fill, outline=line, width=lw)
                elif k == "ngon":
                    r = sh.get("r", 0.05) * self.BASE * scale
                    draw.regular_polygon((x, y, r), int(sh.get("sides", 5)),
                                         rotation=sh.get("rotation", 0),
                                         fill=fill, outline=line)
                elif k == "text":
                    draw.text((x, y), sh.get("text", ""), fill=col,
                              anchor=sh.get("anchor"))
                else:
                    w2 = sh.get("w", 0.1) * W * scale / 2
                    h2 = sh.get("h", 0.1) * H * scale / 2
                    box = [x - w2, y - h2, x + w2, y + h2]
                    if k == "ellipse":
                        draw.ellipse(box, fill=fill, outline=line, width=lw)
                    elif k == "rect":
                        rad = int(sh.get("radius", 0) * self.BASE)
                        if rad:
                            draw.rounded_rectangle(box, radius=rad,
                                                   fill=fill, outline=line, width=lw)
                        else:
                            draw.rectangle(box, fill=fill, outline=line, width=lw)
                    elif k == "arc":
                        draw.arc(box, sh.get("start", 0), sh.get("end", 180),
                                 fill=col, width=lw)
                    elif k == "chord":
                        draw.chord(box, sh.get("start", 0), sh.get("end", 180),
                                   fill=fill, outline=line)
                    elif k == "pieslice":
                        draw.pieslice(box, sh.get("start", 0), sh.get("end", 90),
                                      fill=fill, outline=line)
            except Exception as exc:
                # Eine kaputte Form darf nicht das ganze Bild kosten.
                # Gemeldet wird sie trotzdem -- stilles Verschlucken waere
                # wieder die Fehlerklasse aus Regel 8a.
                self._shape_errors = getattr(self, "_shape_errors", 0) + 1
                if self._shape_errors <= 3:
                    print(f"[render] Form '{k}' nicht zeichenbar: {exc}")

    def draw_sad_tear(self, draw, cx, cy, r):
        self.tear_y = (self.tear_y + 1) % 35
        tear_x = cx - r * 0.38 - 5
        tear_start_y = cy - r * 0.05
        ty = tear_start_y + self.tear_y
        draw.ellipse([tear_x, ty, tear_x + 6, ty + 8], fill=(100, 200, 255))

    # ----------------------------------------------------------
    # Identity HUD Overlay (Taste Y)
    # ----------------------------------------------------------
    def draw_identity_overlay(self, draw):
        """
        Semi-transparentes Overlay ueber Noisy.
        Zeigt AEI-Werte, Mood, Alter, Interaktionen.
        240x240px, Lesbarkeit first.
        """
        # Hintergrund (dunkel, semi-transparent simuliert)
        draw.rectangle([10, 10, 230, 230], fill=(0, 0, 0))
        draw.rectangle([12, 12, 228, 228], outline=GOLD, width=2)

        # Header
        draw.text((20, 18), "IDENTITY: NOISY", fill=GOLD)

        # AEI-Balken
        personality = self.state.personality
        bars = [
            ("E", personality.energy, (255, 100, 50)),     # Orange
            ("C", personality.cheerful, (255, 220, 50)),   # Gelb
            ("S", personality.shy, (100, 150, 255)),       # Blau
            ("A", personality.affection, (255, 100, 180)), # Rosa
        ]

        y_start = 50
        bar_height = 18
        bar_spacing = 28
        bar_left = 35
        bar_right = 215
        bar_width = bar_right - bar_left

        for i, (label, value, color) in enumerate(bars):
            by = y_start + i * bar_spacing

            # Label
            draw.text((18, by + 2), label, fill=WHITE)

            # Rahmen
            draw.rectangle([bar_left, by, bar_right, by + bar_height],
                           outline=(80, 80, 80), width=1)

            # Fuell-Balken
            fill_w = int(bar_width * value)
            if fill_w > 0:
                draw.rectangle([bar_left, by, bar_left + fill_w, by + bar_height],
                               fill=color)

            # Wert rechts
            draw.text((bar_right - 32, by + 2), "%.0f%%" % (value * 100), fill=WHITE)

        # Mood + Info
        info_y = y_start + 4 * bar_spacing + 8
        mood_name = self._mood().get('name', 'IDLE')
        draw.text((20, info_y), "VIBE:", fill=(150, 150, 150))
        draw.text((60, info_y), mood_name, fill=GOLD)

        # Alter
        age_days = personality.get_age_days()
        draw.text((20, info_y + 22), "AGE:", fill=(150, 150, 150))
        if age_days < 1:
            age_str = "%.0f Std" % (age_days * 24)
        else:
            age_str = "%.1f Tage" % age_days
        draw.text((60, info_y + 22), age_str, fill=WHITE)

        # Interaktionen
        draw.text((20, info_y + 44), "INT:", fill=(150, 150, 150))
        draw.text((60, info_y + 44), "%d" % personality.total_interactions, fill=WHITE)

        # Dominant Trait
        trait = personality.get_dominant_trait()
        draw.text((20, info_y + 66), "TRAIT:", fill=(150, 150, 150))
        draw.text((72, info_y + 66), trait.upper(), fill=GOLD)

        # Mute-Status
        if self.state.is_muted:
            draw.text((140, info_y + 66), "[MUTED]", fill=(255, 50, 50))

    # ----------------------------------------------------------
    # Night Gesture (Psst! nachts genervt aufgewacht)
    # ----------------------------------------------------------
    def draw_night_gesture(self, draw, cx, cy, r):
        """
        Zeichnet Nacht-Geste: Psst-Finger, genervte Augen-Balken,
        kleine Uhr (zeigt auf die Uhrzeit).
        """
        # Psst-Finger (vertikaler Strich vor dem Mund)
        fx = cx + 2
        fy = cy + r * 0.18
        # Finger (hautfarben)
        draw.rectangle([fx - 3, fy - 12, fx + 3, fy + 8], fill=(220, 180, 150))
        # Fingerspitze (rund)
        draw.ellipse([fx - 4, fy - 16, fx + 4, fy - 10], fill=(220, 180, 150))

        # "Shh" Text (pulsierend)
        if int(self.frame) % 20 < 14:
            draw.text((cx + 18, fy - 8), "shh!", fill=(200, 200, 255))

        # Genervte Augenbrauen (schraeg nach innen)
        eye_y = cy - r * 0.12
        spacing = r * 0.38
        for s in [-1, 1]:
            ex = cx + s * spacing
            # Augenbraue: aussen hoch, innen runter (genervt)
            brow_outer_y = eye_y - 14
            brow_inner_y = eye_y - 8
            if s == -1:
                draw.line([ex - 10, brow_outer_y, ex + 8, brow_inner_y],
                          fill=EYE_COLOR, width=3)
            else:
                draw.line([ex - 8, brow_inner_y, ex + 10, brow_outer_y],
                          fill=EYE_COLOR, width=3)

        # Kleine Uhr (rechts oben, Noisy zeigt auf die Zeit)
        clock_x = cx + r + 20
        clock_y = cy - r - 5
        clock_r = 12
        draw.ellipse([clock_x - clock_r, clock_y - clock_r,
                      clock_x + clock_r, clock_y + clock_r],
                     outline=WHITE, width=2)
        # Zeiger
        draw.line([clock_x, clock_y, clock_x, clock_y - 8], fill=WHITE, width=2)
        draw.line([clock_x, clock_y, clock_x + 6, clock_y], fill=WHITE, width=1)
        # "Zzz" daneben
        draw.text((clock_x + 14, clock_y - 6), "z", fill=(150, 150, 200))

    # ----------------------------------------------------------
    # RENDER
    # ----------------------------------------------------------
    def render(self):
        self.read_temperature()

        # Laufzeit-Parameter (Speed) vom Orchestrator
        rt = getattr(self.state, 'rt', None)
        speed = rt.get_speed() if rt is not None else 1.0

        # Mood-Daten aus dem Zustand. Der Helfer liefert immer ein
        # vollstaendiges Dict -- auch wenn noch nichts gesetzt wurde.
        rd = self._mood()
        mood_id = rd.get("name", "IDLE")

        # --- AUDIO-KOPPLUNG: Lautstaerke + Beat ---
        # Beide Werte kamen bisher hier an und wurden nie benutzt; der
        # Blob reagierte ausschliesslich auf den Mood. Jetzt bestimmen sie
        # Tempo und Ausschlag der Bewegung.
        target_loud = min(1.0, self.state.intensity / 200.0)
        target_beat = min(1.0, self.state.beat / 90.0)
        self.smooth_loud += (target_loud - self.smooth_loud) * AUDIO_SMOOTHING
        self.smooth_beat += (target_beat - self.smooth_beat) * AUDIO_SMOOTHING
        loud = self.smooth_loud
        beat = self.smooth_beat

        # Der Takt bedeutet nur etwas, wenn wirklich Musik laeuft. Ausserhalb
        # der Musik-Moods wird er auf null gesetzt - sonst pulsiert der Blob
        # auch im Schlaf, weil render_beat nie ganz auf null geht. Mit 0,6
        # bis 1,1 Sekunden Periode sah das bei 8 FPS nicht nach Atmen aus,
        # sondern nach Flackern.
        # Noisy fragte hier nach der Mood-Gruppe "musik". Chimera hat keine
        # festen Gruppen mehr (die Zuordnung macht das Sprachmodell), also
        # entscheidet die gemessene Lautstaerke: Ohne Pegel kein Takt.
        ist_musik = loud > 0.15
        if not ist_musik:
            beat = 0.0

        # Taktphase laeuft mit dem gemessenen Puls weiter - dadurch bleibt
        # die Bewegung auch dann rund, wenn sich das Tempo aendert.
        # Deutlich langsamer als frueher: der Blob soll mitwippen, nicht
        # zittern.
        self.beat_phase += (0.10 + beat * 0.45) * speed
        beat_pulse = (math.sin(self.beat_phase) + 1.0) * 0.5      # 0..1

        # Ausschlag- und Tempofaktoren
        amp_scale = 0.55 + loud * 1.05          # leise = zurueckhaltend
        speed_scale = 0.60 + beat * 1.30        # langsamer Takt = ruhiger

        body = rd["body"]
        eyes = rd["eyes"]
        mouth = rd["mouth"]
        hair = rd["hair"]
        physics = rd["physics"]
        particles = rd["particles"]
        accessory = rd["accessory"]

        # --- BLINK ENGINE ---
        blink_progress = 0.0
        if self.is_blinking:
            self.blink_timer += 1
            half = self.blink_duration / 2
            if self.blink_timer <= half:
                blink_progress = self.blink_timer / half
            else:
                blink_progress = 1.0 - (self.blink_timer - half) / half
            if self.blink_timer >= self.blink_duration:
                self.is_blinking = False
                self.next_blink = random.randint(45, 130)
        else:
            self.next_blink -= 1
            if self.next_blink <= 0:
                self.is_blinking = True
                self.blink_timer = 0
                self.blink_duration = random.randint(3, 7)

        # --- THERMAL VISUALS ---
        thermal_droopy = 0.0
        self.thermal_sweat = False
        if self.cpu_temp > 70:
            thermal_droopy = min(0.5, (self.cpu_temp - 70) / 20.0)
            self.thermal_sweat = True
        elif self.cpu_temp > 60:
            thermal_droopy = min(0.2, (self.cpu_temp - 60) / 50.0)
        self.thermal_droopy = thermal_droopy

        # --- KONTRAST FUER HELLE RAEUME ---
        # Eine Stelle fuer alle 35 Moods: die Mood-Definitionen behalten
        # ihre Farben, der Renderer hebt sie nur gemeinsam an. Live ueber
        # das Dashboard regelbar, weil es keinen Lichtsensor gibt.
        # Nachsichtig lesen: der Renderer laeuft auch mit einer aelteren
        # RuntimeConfig weiter, die den Regler noch nicht kennt.
        holen = getattr(rt, 'get_contrast', None) if rt is not None else None
        boost = (holen() / 100.0) if holen else DEFAULT_CONTRAST_BOOST

        # Frisur und Haarfarbe kommen aus der Laufzeit-Config, damit sie
        # im Dashboard einstellbar sind. Ein Mood darf sie weiterhin
        # ueberschreiben (hair.style / hair.color) - der Rasta-Hut braucht
        # nun mal andere Haare als der Kurzhaarschnitt.
        self.hair_style = 'mochi'
        if rt is not None and hasattr(rt, 'get_hair_style'):
            self.hair_style = rt.get_hair_style()
            # Vorsicht: get_render_data() hat die Standard-Haarfarbe schon
            # eingemischt, ein setdefault() liefe also immer ins Leere.
            # Massgeblich ist, ob der MOOD selbst eine Farbe setzt - dann
            # behaelt er sie (der Rasta-Hut braucht andere Haare als der
            # Kurzhaarschnitt). Sonst gilt die Einstellung aus dem
            # Dashboard.
            roh = self._mood()
            if 'color' not in roh.get('hair', {}):
                hair = dict(hair)
                farbe = rt.get_hair_color()
                hair['color'] = farbe
                hair.pop('color_dark', None)
                hair.pop('color_light', None)

        # --- SMOOTH COLOR MORPHING ---
        # morph_speed kommt vom Orchestrator (Transition-Geschwindigkeit)
        morph = self.state.morph_speed
        target_body = lift_color(body.get("color", DEFAULT_BODY["color"]), boost)
        # Der Glow deckt den groessten Teil der Flaeche ab und ist damit
        # das wirksamste Mittel gegen Umgebungslicht - er wird staerker
        # angehoben als der Koerper.
        target_glow = lift_color(body.get("glow", DEFAULT_BODY["glow"]),
                                 min(1.0, boost * 1.35), ziel=200)
        self.current_body_color = lerp_color(self.current_body_color, target_body, morph)
        self.current_glow_color = lerp_color(self.current_glow_color, target_glow, morph)

        # --- CANVAS ---
        img = Image.new('RGB', (self.WIDTH, self.HEIGHT), BLACK)
        draw = ImageDraw.Draw(img)

        # Die einzigen echten Absolutwerte des Gesichts in Noisy waren
        # (120, 118) und Radius 55 -- gerechnet gegen 240x240. Relativ
        # ausgedrueckt: Mitte waagerecht, leicht oberhalb der Mitte
        # senkrecht, Radius knapp ein Viertel der kurzen Seite. Damit
        # sitzt das Gesicht auf jeder Flaeche gleich (Regel 6).
        cx = self.WIDTH // 2
        cy = int(self.FACE_CY * self.HEIGHT)
        base_r = int(self.FACE_R * self.BASE)

        # --- BREATHING & SWAY ---
        # Ruhige Grundatmung, unabhaengig von der Lautstaerke: rund zehn
        # Sekunden pro Zug, gut zwei Pixel Ausschlag. Sie soll man kaum
        # bemerken. Das sichtbare Ein- und Ausatmen ist Joint und Bong
        # vorbehalten - sonst erzaehlt es nichts mehr.
        breath = math.sin(self.frame * 0.08) * 2.0
        sway_speed = physics.get("sway_speed", 0.05)
        sway_amp = physics.get("sway_amp", 2.2) * (0.75 + loud * 0.6)
        cx += math.sin(self.frame * sway_speed) * sway_amp
        r_w = base_r + breath
        r_h = base_r + breath

        # Kein Pumpen der Koerpergroesse mehr. Der Takt zeigt sich in den
        # Physics der Musik-Moods (Headbang, Bounce) und im Glow - dort
        # gehoert er hin. Als Groessenaenderung war er von der Atmung und
        # vom Zug an Joint und Bong nicht zu unterscheiden.

        # --- ZUG-ZYKLUS (JOINT / BONG) ---
        # Beim Ziehen blaeht er sich auf, beim Ausatmen schrumpft er
        # zurueck und blaest den Rauch aus.
        zieht = bool(physics.get("toke"))
        self.toke_inflate, self.toke_ember, self.toke_exhaling = \
            self.toke_cycle(mood_id, zieht, speed)
        if zieht:
            # Waehrend des Zuges die normale Atmung herausnehmen - sonst
            # ueberlagern sich zwei Rhythmen und es sieht aus, als wuerde
            # er dreimal hintereinander pumpen statt einmal zu ziehen.
            r_w -= breath
            r_h -= breath
            r_w *= 1.0 + TOKE_INFLATE * self.toke_inflate
            r_h *= 1.0 + TOKE_INFLATE * self.toke_inflate * 0.85

        # --- PHYSICS (mit Lautstaerke/Beat skaliert) ---
        headbang_speed = physics.get("headbang_speed", 0) * speed_scale
        headbang_amp = physics.get("headbang_amp", 0) * amp_scale
        bounce_speed = physics.get("bounce_speed", 0) * speed_scale
        bounce_amp = physics.get("bounce_amp", 0) * amp_scale
        shake_x = int(physics.get("shake_x", 0) * amp_scale)
        shake_y = int(physics.get("shake_y", 0) * amp_scale)

        # Was der Koerper tatsaechlich tut - inklusive Lautstaerke- und
        # Taktskalierung. Die Frisur muss hieran haengen, nicht an den
        # rohen Mood-Werten: sonst schwingt sie in voller Amplitude
        # weiter, waehrend der Mochi bei leiser Musik schon still steht.
        wirksame_physik = dict(physics)
        wirksame_physik["headbang_speed"] = headbang_speed
        wirksame_physik["headbang_amp"] = headbang_amp
        wirksame_physik["bounce_speed"] = bounce_speed
        wirksame_physik["bounce_amp"] = bounce_amp

        if headbang_speed > 0:
            cy += math.sin(self.frame * headbang_speed) * headbang_amp
        if bounce_speed > 0:
            cy -= abs(math.sin(self.frame * bounce_speed) * bounce_amp)
        if shake_x > 0:
            cx += random.randint(-shake_x, shake_x)
        if shake_y > 0:
            cy += random.randint(-shake_y, shake_y)

        # Wirkung nach dem Zug: traeges Treiben. Langsam und weich, damit
        # es nach Schwerelosigkeit aussieht und nicht nach Wackeln.
        if self.toke_high > 0.01:
            cx += math.sin(self.frame * 0.045) * 7 * self.toke_high
            cy += math.sin(self.frame * 0.031 + 1.1) * 5 * self.toke_high

        # Stretch (Idle)
        r_w += physics.get("stretch_w", 0)
        r_h += physics.get("stretch_h", 0)

        # =======================================================
        # DRAWING LAYERS
        # =======================================================

        # Layer 1: Glow
        self.draw_glow(draw, cx, cy, r_w, r_h, self.current_glow_color, mood_id,
                       beat_pulse=beat_pulse, beat_strength=beat)

        # Layer 2: Kopfhoerer-Buegel (nur bei headphones Accessoire)
        #
        # "type" darf ein einzelner Name oder eine Liste sein. Rock traegt
        # Kopfhoerer UND macht die Pommesgabel; ein Mood auf ein Requisit
        # zu beschraenken hiess, sich zwischen beidem zu entscheiden.
        acc_types = accessory.get("type")
        if isinstance(acc_types, str):
            acc_types = [acc_types]
        acc_types = [a for a in (acc_types or []) if a]
        has_headphones = "headphones" in acc_types
        if has_headphones:
            self.draw_headphones(draw, cx, cy, r_w, r_h, before_body=True)

        # Layer 3: Body
        self.draw_body(draw, cx, cy, r_w, r_h, self.current_body_color)

        # Layer 4: Kopfhoerer-Muscheln
        if has_headphones:
            self.draw_headphones(draw, cx, cy, r_w, r_h, before_body=False)

        # Layer 5: Frisur
        self.draw_hair(draw, cx, cy, r_w, wirksame_physik, hair)

        # Layer 6: Accessoires hinter Augen und Mund
        # (headphones sind als Layer 2/4 schon gezeichnet)
        for typ in acc_types:
            if typ != "headphones" and typ not in ACCESSOIRES_VORN:
                self.draw_accessory(draw, cx, cy, r_w, r_h, typ, mood_id)

        # Layer 7: Augen (mit Thermal-Droopy)
        if self.thermal_droopy > 0:
            eyes = dict(eyes)
            eyes["scale_h"] = eyes.get("scale_h", 1.0) * (1.0 - self.thermal_droopy)
        # Die Wirkung setzt nach dem Ausatmen ein: die Augen drehen sich.
        # Dieselben Schwindelaugen, die es schon gibt - eine Geste mehr
        # zu erfinden haette nur eine zweite Sprache eingefuehrt.
        if eyes.get("swirl") or self.toke_high > 0.35:
            self.draw_swirl_eyes(draw, cx, cy, base_r)
        else:
            self.draw_eyes(draw, cx, cy, base_r, blink_progress, eyes)

        # Layer 8: Mund
        # Waehrend am Mundstueck gezogen wird, saugt er - ein Laecheln
        # waere da die falsche Miene.
        if self.toke_anlegen > 0.6:
            mouth = dict(mouth, style="open_round")
        self.draw_mouth(draw, cx, cy, base_r, mouth, mood_id)

        # Layer 8b: Accessoires vor Augen und Mund
        for typ in acc_types:
            if typ in ACCESSOIRES_VORN:
                self.draw_accessory(draw, cx, cy, r_w, r_h, typ, mood_id)

        # Layer 9: SAD Traene
        if mood_id == MOOD_SAD:
            self.draw_sad_tear(draw, cx, cy, base_r)

        # Layer 10: Partikel
        p_type = particles.get("type")
        # Lauter = mehr los. Der Faktor bleibt bewusst unter 2, damit das
        # Partikel-Limit (30) nicht dauernd anschlaegt.
        p_rate = particles.get("rate", 0) * (0.65 + loud * 1.1)
        p_color = particles.get("color") or self.current_body_color
        if p_type and random.random() < p_rate:
            if self.particle_origin:
                ox, oy = self.particle_origin
                px = ox + random.randint(-5, 5)
                py = oy + random.randint(-5, 5)
            else:
                px = cx + random.randint(-45, 45)
                py = cy - 40
            self.particles.spawn(px, py, p_type, p_color)
        self.particle_origin = None

        # Beim Ausatmen kommt der Rauch aus dem Mund, nicht von ueberall.
        # Eigener Partikeltyp: eine sichtbare Wolke statt der duennen
        # Kringel, die im Hintergrund untergehen.
        if self.toke_exhaling:
            self.particles.spawn(cx - 14 + random.randint(-4, 4),
                                 cy + 12 + random.randint(-5, 5),
                                 "puff", (225, 228, 235))

        # Thermal-Schweiss (bei >70°C, unabhaengig vom Mood)
        if self.thermal_sweat and int(self.frame) % 15 == 0:
            sx = cx + random.randint(-25, 25)
            self.particles.spawn(sx, cy - 35, "sweat", (100, 200, 255))

        # Lieblingsgenre: Herz-Partikel + Augen-Funkeln
        if self.state.favorite_playing and int(self.frame) % 10 == 0:
            hx = cx + random.randint(-35, 35)
            self.particles.spawn(hx, cy - 45, "heart", (255, 100, 180))

        self.particles.update()
        self.particles.draw(draw)

        # Lieblingsgenre: Augen-Funkeln (kleine Sterne in den Augen)
        if self.state.favorite_playing:
            eye_y = cy - base_r * 0.12
            spacing = base_r * 0.38
            sparkle = int(200 + 55 * math.sin(self.frame * 0.5))
            for s in [-1, 1]:
                sx = cx + s * spacing - 3
                sy = eye_y - 5
                draw.text((int(sx), int(sy)), "*", fill=(sparkle, sparkle, 100))

        # Layer 11: Night Gesture (Psst! Finger + Uhr, genervte Augen)
        if self.state.night_annoyed:
            self.draw_night_gesture(draw, cx, cy, base_r)

        # Layer 12: Identity HUD Overlay (Taste Y Toggle)
        if self.state.show_identity:
            self.draw_identity_overlay(draw)

        # Layer 13: DEBUG-Rahmen (rot pulsierend, auffaellig!)
        if self.state.is_debug:
            pulse = int(180 + 75 * math.sin(self.frame * 0.3))
            for i in range(6):
                draw.rectangle([i, i, self.WIDTH - 1 - i, self.HEIGHT - 1 - i],
                               outline=(pulse, 0, 0))
            draw.text((self.WIDTH // 2 - 20, 5), "DEBUG", fill=(255, 50, 50))

        # Layer 14: MUTE-Rahmen (grau) + Korken in den Ohren
        if self.state.is_muted:
            for i in range(6):
                draw.rectangle([i, i, self.WIDTH - 1 - i, self.HEIGHT - 1 - i],
                               outline=(100, 100, 100))
            draw.text((self.WIDTH // 2 - 18, 5), "MUTE", fill=(150, 150, 150))
            # Korken in beiden Ohren
            ear_y = cy - base_r * 0.1
            for s in [-1, 1]:
                ex = cx + s * (r_w + 6)
                # Korken (kleiner brauner Zylinder)
                draw.rectangle([ex - 5, ear_y - 4, ex + 5, ear_y + 8],
                               fill=(180, 130, 60))
                draw.rectangle([ex - 6, ear_y - 5, ex + 6, ear_y - 2],
                               fill=(200, 150, 80))
                # Kleiner Schatten
                draw.line([ex - 3, ear_y + 1, ex + 3, ear_y + 1],
                          fill=(140, 100, 40), width=1)

        # Layer 15: SOCIAL-Rahmen (gruen pulsierend, BLE Beacon aktiv)
        if self.state.is_social:
            pulse = int(140 + 115 * math.sin(self.frame * 0.3))
            for i in range(6):
                draw.rectangle([i, i, self.WIDTH - 1 - i, self.HEIGHT - 1 - i],
                               outline=(0, pulse, 0))
            draw.text((self.WIDTH // 2 - 12, 5), "BLE", fill=(0, 255, 0))

        # Layer 16: PASSWORT-RESET - Bestaetigung am Geraet
        #
        # Der Reset laeuft NICHT von allein durch: waehrend des Countdowns
        # muss der Konami-Code eingegeben werden. Das Display zeigt die
        # Sequenz und den Fortschritt, damit man nichts nachschlagen muss.
        # (Noisys Reset-Ueberlagerung entfernt: Chimera wird ueber
        # Telegram und Sprache bedient, nicht ueber eine Tastenfolge.)

        # --- BRIGHTNESS / NIGHT-DIMMING ---
        img = self._apply_brightness(img)

        # --- AUSGABE ---
        if self.state.cube_mode:
            # Prisma: 180-Grad-Drehung (Faltoptik)
            img = img.transpose(Image.ROTATE_180)

        self.frame += speed

        # Zeichnen und Ausgeben sind getrennt: render() liefert das Bild,
        # show() schiebt es aufs Panel. So laesst sich das Ergebnis
        # pruefen und messen, ohne ein Geraet zu haben.
        return img



    # ----------------------------------------------------------
    # RUN (als Thread)
    # ----------------------------------------------------------
    def show(self, img=None):
        """Ein Bild ausgeben; ohne Argument wird neu gezeichnet."""
        if img is None:
            img = self.render()
        if img is not None:
            self.panel.show(img)
        return img

    def run(self):
        print("Noisy Renderer gestartet (Komponentenbasiert)")
        print(f"Target FPS: {TARGET_FPS}")

        fps_counter = 0
        fps_timer = time.time()

        try:
            while True:
                t_start = time.time()
                self.render()

                fps_counter += 1
                if time.time() - fps_timer >= 10.0:
                    actual_fps = fps_counter / (time.time() - fps_timer)
                    mood_name = self._mood().get('name', 'IDLE')
                    print(f"FPS: {actual_fps:.1f} | Frame: {int(self.frame)} | "
                          f"Temp: {self.cpu_temp:.0f}C | Mood: {mood_name}")
                    fps_counter = 0
                    fps_timer = time.time()

                elapsed = time.time() - t_start
                sleep_time = FRAME_TIME - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except Exception as e:
            print(f"Renderer Fehler: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.panel.show(Image.new('RGB', (self.WIDTH, self.HEIGHT), BLACK))
            print("Renderer beendet.")
