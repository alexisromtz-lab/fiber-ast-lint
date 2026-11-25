"""Second pass: who measures the cardinal outside the producing function?

The local pass (``detect``) can only see a ``len(acc)`` written in the same
scope. When the accumulator is returned, or when it arrives as a parameter, the
reader lives one hop away and the local pass honestly says ``SIN_LEN``. This
module walks the call sites and closes that hop:

  DIRECTO    ``len(f(...))``                the consumer is the call itself
  VINCULO    ``x = f(...)`` then ``len(x)`` afterwards in the same scope
  PARAMETRO  ``f(x)`` and later ``len(x)`` in the caller

Declared limits (all of them return ``NO_MEDIDO``, never 0): no attribute form
(``len(x.keys())``), no aliasing through containers, no propagation beyond one
hop, and no cross-module resolution beyond a name match in the analysed
universe. A name match is a *candidate* consumer: it is evidence that a reader
exists, not that the two functions are the same object.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .detect import IGNORADOS, PUBLICADORES

SIN_DESCENSO_FN = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass
class Consumidor:
    productor: str
    archivo: str
    linea_llamada: int
    linea_consumo: int
    forma: str

    def __str__(self) -> str:
        return (f"{self.productor}() {self.archivo}:{self.linea_llamada}"
                f" -> len en :{self.linea_consumo} [{self.forma}]")


def _padres(arbol: ast.AST) -> dict[int, ast.AST]:
    out: dict[int, ast.AST] = {}
    for n in ast.walk(arbol):
        for h in ast.iter_child_nodes(n):
            out[id(h)] = n
    return out


def _es_len(n: ast.AST | None) -> bool:
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "len" and len(n.args) == 1)


def _es_publicador(n: ast.AST | None) -> bool:
    if not isinstance(n, ast.Call):
        return False
    f = n.func
    nombre = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
    return nombre in PUBLICADORES


def _cuerpo_que_contiene(arbol: ast.AST, objetivo: ast.AST) -> list[ast.stmt]:
    """Innermost function/module body that contains ``objetivo``."""
    mejor: list[ast.stmt] = getattr(arbol, "body", [])
    for n in ast.walk(arbol):
        if isinstance(n, SIN_DESCENSO_FN) and \
                any(x is objetivo for x in ast.walk(n)):
            mejor = n.body
    return mejor


def _lecturas_de(nombre: str, cuerpo: list[ast.stmt], desde: int) -> list[int]:
    """Lines where ``nombre``'s cardinal is measured or published, after ``desde``."""
    lineas: list[int] = []
    for raiz in cuerpo:
        for n in ast.walk(raiz):
            if getattr(n, "lineno", 0) <= desde:
                continue
            if _es_len(n) and isinstance(n.args[0], ast.Name) and n.args[0].id == nombre:
                lineas.append(n.lineno)
            elif _es_publicador(n):
                for x in ast.walk(n):
                    if isinstance(x, ast.Name) and x.id == nombre:
                        lineas.append(n.lineno)
                        break
    return sorted(set(lineas))


def consumidores(raiz: str | Path, productores: set[str]) -> dict[str, list[Consumidor]]:
    """Maps each producer name to the call sites that measure its cardinal."""
    raiz = Path(raiz)
    out: dict[str, list[Consumidor]] = {k: [] for k in productores}
    if not productores or not raiz.is_dir():
        return out
    for p in sorted(raiz.rglob("*.py")):
        relp = p.relative_to(raiz)
        if any(part in IGNORADOS for part in relp.parts):
            continue
        try:
            arbol = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        padres = _padres(arbol)
        for n in ast.walk(arbol):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
                continue
            nombre = n.func.id
            if nombre not in productores:
                continue
            padre = padres.get(id(n))
            if _es_len(padre):
                out[nombre].append(Consumidor(nombre, str(relp), n.lineno,
                                              padre.lineno, "DIRECTO"))
                continue
            if isinstance(padre, (ast.Assign, ast.AnnAssign)):
                objetivos = padre.targets if isinstance(padre, ast.Assign) else [padre.target]
                if len(objetivos) == 1 and isinstance(objetivos[0], ast.Name):
                    cuerpo = _cuerpo_que_contiene(arbol, padre)
                    for ln in _lecturas_de(objetivos[0].id, cuerpo, padre.lineno):
                        out[nombre].append(Consumidor(nombre, str(relp), n.lineno,
                                                      ln, "VINCULO"))
                continue
            cuerpo = _cuerpo_que_contiene(arbol, n)
            for arg in n.args:
                if isinstance(arg, ast.Name):
                    for ln in _lecturas_de(arg.id, cuerpo, n.lineno):
                        out[nombre].append(Consumidor(nombre, str(relp), n.lineno,
                                                      ln, "PARAMETRO"))
    return out
