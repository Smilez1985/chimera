"""Anzeigetreiber -- eigenständig, ohne Abhängigkeit vom übrigen Chimera.

Importiert nur Standardbibliothek, Pillow und (für Tempo) numpy. Der Ordner
lässt sich unverändert in ein eigenes Repo heben (smilez, 11.10.2026).
"""

from .base import NullPanel, Panel, Profil, to_rgb565  # noqa: F401
from .registry import oeffne, profil, profile, typen  # noqa: F401
