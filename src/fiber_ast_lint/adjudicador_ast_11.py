"""Adjudicating the cause of a locus, v1.1: a bound is not a key.

This is a new artifact, not an edit. ``adjudicador_ast`` v1.0 is frozen by hash
because the batch 24 receipt measures *that* file; correcting it in place would
erase the measurement that refuted it. The helpers that are not the rule are
imported from v1.0 on purpose: ``objetivos``, ``indices_de_escritura`` and
``nodo_de_escritura`` locate a locus, they do not adjudicate it, and duplicating
them would let two copies drift.

The one thing that changes is the shape of the index. v1.0 rejected any index
containing a call, and the batch 24 run found the case that shows the rejection
was too coarse::

    wavs[i, : len(row)] = row          # tests/test_chattts_streaming.py:134

The call sits *inside the bound of a slice*. A bound selects which positions are
addressed; it does not produce a key. Refined, in two pieces:

  T1  POSITIONAL ADDRESS.  Decompose the index into its components -- the
      elements of a tuple, or the index itself. A component that is a ``Slice``
      is a *bound*: a call, conditional or lambda inside it is a length, and the
      address stays a set of positions. Any other component is a *key*: a call
      there may fuse two distinct rows into one address, so it is still refused.
      At least one component must be a bound, else there is no address at all.

  T2  LOCALITY.  The file of the locus does not parse under the interpreter that
      reads it. Nothing inside it can be adjudicated, and refusing to look is
      itself a measurement. ``INTERPRETE`` is published because T2 measures the
      parser's floor, not the subject's state: the same file parses under 3.12
      and not under 3.11 when it uses PEP 695.

The certificate behind T1 is not a domain assumption: ``hash(slice(1, 2))``
raises ``TypeError: unhashable type: 'slice'``, so an index that contains a slice
cannot be a dictionary key and cannot be the fiber of a keyed write. The residue
is declared rather than hidden: a labelled dispatcher (``serie.loc[label, :]``)
has the same syntax tree as a positional one (``serie.iloc[i, :]``), and this
rule does not distinguish them. The receipt counts those rows and publishes the
count.

The law is unchanged from v1.0: an abstention costs coverage and never precision.
"""
from __future__ import annotations

import ast
import sys

from .adjudicador_ast import (  # noqa: F401  (locating a locus is not adjudicating it)
    NO_PARSEA,
    POSICIONAL,
    SIN_CAUSA,
    indices_de_escritura,
    nodo_de_escritura,
    objetivos,
)

__all__ = [
    "CAUSAS_DECIDIBLES",
    "INTERPRETE",
    "adjudicar",
    "causa_de_escritura",
    "causa_por_localidad",
    "componentes",
    "direccion_posicional",
    "indices_de_escritura",
    "nodo_de_escritura",
    "objetivos",
]

#: The only causes this instrument is allowed to emit. A value outside this
#: tuple would be a guess, and a guess has no place in a receipt.
CAUSAS_DECIDIBLES = (POSICIONAL, NO_PARSEA)

#: The interpreter whose parser floor T2 measures. Published, never inferred:
#: a verdict of ``fichero_no_parsea`` is a statement about this parser.
INTERPRETE = sys.version.split()[0]

#: Expressions that can compute a key out of the row. Inside a bound they are
#: lengths and are allowed; as a component of the index they are refused.
COMPUTAN_CLAVE = (ast.Call, ast.IfExp, ast.Lambda)


def componentes(indice: ast.AST) -> list[ast.AST]:
    """The pieces of an index: the elements of a tuple, or the index itself.

    ``acc[a, b]`` indexes with a tuple and ``acc[a:b]`` with a slice; treating
    the tuple as one expression is what made v1.0 unable to tell which piece
    carried the call.
    """
    return list(indice.elts) if isinstance(indice, ast.Tuple) else [indice]


def direccion_posicional(indice: ast.AST) -> bool:
    """``indice`` addresses a set of locations instead of computing a key.

    Two conditions: at least one bound (a bare name or a constant is a key, not
    an address), and no key component that could compute -- a call, conditional
    or lambda as the component itself, not inside a bound.
    """
    piezas = componentes(indice)
    if not any(isinstance(p, ast.Slice) for p in piezas):
        return False
    return not any(
        not isinstance(p, ast.Slice)
        and any(isinstance(x, COMPUTAN_CLAVE) for x in ast.walk(p))
        for p in piezas
    )


def causa_de_escritura(nodo: ast.AST) -> str:
    """T1. The cause of a keyed write, or ``NO_MEDIDO`` when it is not a theorem.

    Every target that indexes must be positional: one subscript keyed by a value
    is enough to reopen the loss predicate.
    """
    indices = indices_de_escritura(nodo)
    if not indices:
        return SIN_CAUSA
    return POSICIONAL if all(direccion_posicional(i) for i in indices) else SIN_CAUSA


def causa_por_localidad(fuente: str | bytes) -> str:
    """T2. ``fichero_no_parsea`` when the source does not parse, else ``NO_MEDIDO``."""
    try:
        ast.parse(fuente)
    except (SyntaxError, ValueError):
        return NO_PARSEA
    return SIN_CAUSA


def adjudicar(nodo: ast.AST | None, fuente: str | bytes | None = None) -> str:
    """The cause the syntax proves about one locus, or ``NO_MEDIDO``.

    T1 is asked first: it speaks about the write, which is the object of the
    locus. T2 speaks about the file and only answers when the write could not be
    located at all.
    """
    if nodo is not None:
        causa = causa_de_escritura(nodo)
        if causa in CAUSAS_DECIDIBLES:
            return causa
    if fuente is not None:
        return causa_por_localidad(fuente)
    return SIN_CAUSA
