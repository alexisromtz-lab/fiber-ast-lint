"""Is a whitelist a transversal of the partition induced by a projection?

A projection ``pi`` loses nothing over a set ``W`` of inputs exactly when ``pi``
restricted to ``pi^-1(W)`` is injective:

    forall y in pi(W):  |W intersect pi^-1(y)| <= 1

If ``W`` is drawn from the *codomain* (``W`` is a set of allowed *outputs*), the
condition can never hold while ``pi`` has a non-trivial fiber inside ``W``: the
whitelist contains two inputs of the same fiber by construction. This is the
reason a guard of the form ``if pi(k) in ALLOWED`` cannot suppress a collision,
and it is checkable without running the program: apply ``pi`` to ``W`` and count.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass
class Fibra:
    """The image of a population under a projection, with its kernel."""
    imagen: dict[str, list[str]] = field(default_factory=dict)

    @property
    def preimagenes(self) -> int:
        return sum(len(v) for v in self.imagen.values())

    @property
    def colisiones(self) -> dict[str, list[str]]:
        return {k: v for k, v in self.imagen.items() if len(v) > 1}

    @property
    def nucleo(self) -> int:
        """Mass destroyed: sum over fibers of (|fiber| - 1)."""
        return sum(len(v) - 1 for v in self.imagen.values())

    def conserva(self) -> bool:
        return self.preimagenes - self.nucleo == len(self.imagen)

    def testigos(self, limite: int = 5) -> list[tuple[str, list[str]]]:
        return sorted(self.colisiones.items())[:limite]


def fibra(entradas: Iterable[str], normalizar: Callable[[str], str]) -> Fibra:
    f = Fibra()
    for e in entradas:
        f.imagen.setdefault(normalizar(e), []).append(e)
    return f


def es_transversal(permitidos: Iterable[str], normalizar: Callable[[str], str]) -> bool:
    """True iff no two allowed inputs share an image under ``normalizar``."""
    return not fibra(permitidos, normalizar).colisiones


def verificar_transversal(permitidos: Iterable[str],
                          normalizar: Callable[[str], str]) -> dict:
    f = fibra(permitidos, normalizar)
    return {
        "transversal": not f.colisiones,
        "permitidos": f.preimagenes,
        "imagenes": len(f.imagen),
        "nucleo": f.nucleo,
        "colisiones": [{"imagen": k, "preimagenes": v} for k, v in f.testigos(limite=100)],
    }


def verificar_conservacion(dominio: int, imagen: int, rechazos: int,
                           colisiones: int) -> dict:
    """The bucket law, with strict positivity.

    ``dominio == imagen + rechazos + colisiones`` with every bucket >= 0. A
    bucket defined by subtraction closes in the integers even when the counts are
    incompatible (``68 + 0 + (-1) = 67``); the positivity check is what refutes
    an inconsistent census.
    """
    cubetas = {"imagen": imagen, "rechazos": rechazos, "colisiones": colisiones}
    negativas = {k: v for k, v in cubetas.items() if v < 0}
    suma = sum(cubetas.values())
    return {
        "conserva": suma == dominio and not negativas,
        "dominio": dominio,
        "suma": suma,
        "descuadre": dominio - suma,
        "cubetas_negativas": negativas,
    }
