"""Combining exit codes is a supremum, not a maximum.

The precedence order over runs is::

    RUPTURA (4)  >  DEFECTO (1)  >  NO_MEDIDO / VACIO (2)  >  LIMPIO (0)

``max`` is the wrong operator for that order: ``max(1, 2) == 2``, so a partition
that measured nothing would report the run as "not measured" and let a proven
defect leave the door as a legitimate-looking code. The two orders disagree
exactly on the pair ``(1, 2)``, which is the pair that matters: blindness must
never cover a measurement.

Properties (tested): commutative, associative, identity element ``0``, and
fail-closed — an unknown code is normalised to ``4``, never to ``0``.
"""
from __future__ import annotations

LIMPIO, DEFECTO, VACIO, RUPTURA = 0, 1, 2, 4

#: Higher precedence wins. A code outside the table is a rupture.
PRECEDENCIA = {LIMPIO: 0, VACIO: 1, DEFECTO: 2, RUPTURA: 3}


def normalizar(rc: int) -> int:
    """Fail-closed: an unknown code is not clean, it is a rupture."""
    return rc if rc in PRECEDENCIA else RUPTURA


def precedencia(rc: int) -> int:
    return PRECEDENCIA[normalizar(rc)]


def combinar_rc(*rcs: int) -> int:
    """Supremum of the run's codes under ``4 > 1 > 2 > 0``; empty run is ``0``."""
    if not rcs:
        return LIMPIO
    return max((normalizar(r) for r in rcs), key=precedencia)
