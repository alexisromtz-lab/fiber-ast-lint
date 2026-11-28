"""The cause of a candidate, read from the same file a second time.

``detect`` names *where* a write loses rows; *why* it loses them is a different
reading, and it belongs to the adjudicator batch 25 froze (v1.1). It is computed
here and not inside ``detect`` so the detector's blob keeps being the one the
receipts measure: ``detect.py`` at ``b03f3ac3`` still produces the census, and the
cause is an extra column on top of it.

Three states, never two. A candidate the syntax decides carries its cause. One it
does not decide is ``NO_MEDIDO`` -- a measurement of this rule, not a zero. And a
row whose file cannot be read at all is ``fichero_no_parsea``, which measures the
parser named by ``INTERPRETE``, never the subject.
"""
from __future__ import annotations

import ast
import pathlib

from .adjudicador_ast import NO_PARSEA, POSICIONAL, nodo_de_escritura
from .adjudicador_ast_11 import INTERPRETE, adjudicar  # noqa: F401  (published)

ADJUDICADOR = "v1.1"

#: The causes that clear a row. T1 only: a slice is a location, so the loss
#: predicate is vacuous and nothing is left to review. T2 abstains -- a file that
#: does not parse measures ``INTERPRETE``, never the subject -- so a row it
#: touches stays open.
REFUTADAS = (POSICIONAL,)


def _base(raiz) -> pathlib.Path:
    """A directory is analysed as is; an explicit file as its own directory.

    Mirrors ``detect._fuentes``: ``locus.rel`` is relative to that base, so
    joining it to the argument would invent a second notion of root.
    """
    p = pathlib.Path(raiz)
    return p.parent if p.is_file() else p


def causas(raiz, loci) -> dict[tuple[str, int], str]:
    """``{(archivo, linea): causa}`` for every candidate in ``loci``.

    One parse per file that carries a candidate, and none for the files that
    carry none: the second reading is paid only where the first one spoke.
    """
    pendientes: dict[str, list[int]] = {}
    for loc in loci:
        if loc.candidato:
            pendientes.setdefault(loc.rel, []).append(loc.linea)
    base = _base(raiz)
    salida: dict[tuple[str, int], str] = {}
    for rel, lineas in pendientes.items():
        ruta = base / rel
        try:
            crudo = ruta.read_bytes()
            arbol = ast.parse(crudo.decode("utf-8"), filename=str(ruta))
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
            salida.update({(rel, linea): NO_PARSEA for linea in lineas})
            continue
        for linea in lineas:
            salida[(rel, linea)] = adjudicar(nodo_de_escritura(arbol, linea), crudo)
    return salida
