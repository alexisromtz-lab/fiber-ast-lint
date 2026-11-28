"""Adjudicating the cause of a locus: decide or abstain, never guess.

``detect`` names a locus -- a destructive write on a visible projection. Naming
the *cause* of a refutation is a different act: "the projection is injective",
"the container is used as a set", "the key is a protocol field". Most of those
statements are not theorems of the syntax, so this module implements exactly the
part that is:

  T1  POSITIONAL ADDRESS.  ``acc[a:b] = v``, ``acc[:, i] = v``: the index
      contains a slice and no call or conditional anywhere. A slice is a
      *location*, not a value read off the row, so no ``K(v)`` exists and there
      is no fiber to collapse. The loss predicate is vacuous by construction,
      and it stays vacuous whatever the payload is.

  T2  LOCALITY.  The file of the locus does not parse. Nothing inside it can be
      adjudicated, and refusing to look is itself a measurement.

Everything else answers ``NO_MEDIDO``. The three largest causes in the lote 22
cohort -- ``proyeccion_inyectiva`` (60), ``uso_como_conjunto`` (9),
``clave_de_protocolo`` (6) -- are statements about the *domain*: "this attribute
is a primary key", "this container is a set of declarations", "this name belongs
to a fixed schema". Deciding them from a syntax tree needs the identity of a
field, which is a naming convention and not a structure; an instrument that
answered them would be borrowing the reader's vocabulary and calling the guess a
measurement. That is the tautology this module exists to refuse.

The law, in one line: an abstention costs coverage and never precision, so
abstention is a result and a conjecture is not.
"""
from __future__ import annotations

import ast

POSICIONAL = "escritura_posicional"
NO_PARSEA = "fichero_no_parsea"
SIN_CAUSA = "NO_MEDIDO"

#: The only causes this instrument is allowed to emit. A value outside this
#: tuple would be a guess, and a guess has no place in a receipt.
CAUSAS_DECIDIBLES = (POSICIONAL, NO_PARSEA)


def objetivos(nodo: ast.AST) -> list[ast.AST]:
    """The assignment targets of ``nodo``, whatever its assignment flavour."""
    if isinstance(nodo, ast.Assign):
        return list(nodo.targets)
    if isinstance(nodo, (ast.AnnAssign, ast.AugAssign)):
        return [nodo.target]
    return []


def indices_de_escritura(nodo: ast.AST) -> list[ast.AST]:
    """The index expressions of ``nodo`` that write into a container by key."""
    return [t.slice for t in objetivos(nodo) if isinstance(t, ast.Subscript)]


def direccion_posicional(indice: ast.AST) -> bool:
    """``indice`` addresses a location instead of computing a key from the row.

    Two conditions, both syntactic: at least one slice (a bare name or a constant
    is a key, not an address) and no call, conditional or lambda inside it (a
    call may compute a projection that fuses two distinct rows into one address).
    """
    nodos = list(ast.walk(indice))
    if not any(isinstance(x, ast.Slice) for x in nodos):
        return False
    return not any(isinstance(x, (ast.Call, ast.IfExp, ast.Lambda)) for x in nodos)


def causa_de_escritura(nodo: ast.AST) -> str:
    """T1. The cause of a keyed write, or ``NO_MEDIDO`` when it is not a theorem.

    Every target that indexes must be positional: one subscript keyed by a value
    is enough to reopen the loss predicate.
    """
    indices = indices_de_escritura(nodo)
    if not indices:
        return SIN_CAUSA
    return POSICIONAL if all(direccion_posicional(i) for i in indices) else SIN_CAUSA


def nodo_de_escritura(arbol: ast.AST, linea: int) -> ast.AST | None:
    """The unique keyed write starting at ``linea``; ambiguity is not resolved.

    ``detect`` reports the line of the statement it walked. Two keyed writes on
    one line mean the coordinate does not identify the node, and picking one
    would be choosing which fact to measure.
    """
    hallados = [
        x for x in ast.walk(arbol)
        if isinstance(x, (ast.Assign, ast.AnnAssign))
        and getattr(x, "lineno", -1) == linea
        and indices_de_escritura(x)
    ]
    return hallados[0] if len(hallados) == 1 else None


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
