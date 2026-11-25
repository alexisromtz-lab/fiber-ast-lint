"""Second pass: which call sites measure the producer's cardinal?

Identity, not name. The local pass (``detect``) only sees a ``len(acc)`` written
in the same scope; when the accumulator is returned or arrives as a parameter,
the reader lives one hop away. This module closes that hop, but only through a
resolved identity: a call is attributed to a producer when the call site binds
to the same ``(module, qualname)`` the producer was defined at, either by a
module-level ``def``/``class``, an ``import``/``from ... import`` binding, or an
attribute form whose receiver is an imported module or a module-level class.

A bare name that does not resolve is **not** an identity. It is published in its
own population (``por_nombre``) so a reader can see the size of the homonymy,
and it never fills ``Locus.consumidor``.

Forms, all measured after the call line:

  DIRECTO    ``len(f(...))``                the consumer is the call itself
  VINCULO    ``x = f(...)`` then ``len(x)`` afterwards in the same scope
  PARAMETRO  ``f(x)`` and later ``len(x)`` in the caller

Declared limits (each returns ``NO_MEDIDO``, never 0): no attribute form of the
measurement (``len(x.keys())``), no aliasing through containers, no propagation
beyond one hop, no rebinding analysis (a name reassigned after its ``def`` is
still read as the ``def``), and no resolution of first-class values passed as
arguments. ``*`` imports are not expanded.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .detect import IGNORADOS, PUBLICADORES, _fuentes

SIN_DESCENSO_FN = (ast.FunctionDef, ast.AsyncFunctionDef)

#: Separator between module and qualname in a producer key.
SEP = "::"


@dataclass
class Consumidor:
    productor: str
    archivo: str
    linea_llamada: int
    linea_consumo: int
    forma: str
    via: str = "EXACTO"

    def __str__(self) -> str:
        return (f"{self.productor}() {self.archivo}:{self.linea_llamada}"
                f" -> len en :{self.linea_consumo} [{self.forma}/{self.via}]")


@dataclass
class Consumos:
    """Two populations that must never be added together."""
    exactos: dict[str, list[Consumidor]] = field(default_factory=dict)
    por_nombre: dict[str, list[Consumidor]] = field(default_factory=dict)
    no_resueltos: int = 0
    sitios_llamada: int = 0

    @property
    def productores_con_sitio(self) -> int:
        return sum(1 for v in self.exactos.values() if v)

    @property
    def sitios_exactos(self) -> int:
        return sum(len(v) for v in self.exactos.values())

    @property
    def sitios_por_nombre(self) -> int:
        return sum(len(v) for v in self.por_nombre.values())

    def de(self, clave: str) -> list[Consumidor]:
        return self.exactos.get(clave) or []


def modulo_de(rel: str) -> str:
    """Dotted module path of a repo-relative file (``__init__.py`` is its dir)."""
    partes = [p for p in rel.replace("\\", "/").split("/") if p]
    if not partes:
        return ""
    if partes[-1] == "__init__.py":
        partes = partes[:-1]
    else:
        partes[-1] = partes[-1][:-3]
    return ".".join(partes)


def clave_de(rel: str, qualname: str) -> str:
    return f"{modulo_de(rel)}{SEP}{qualname}"


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


def _base_de_import(n: ast.ImportFrom, modulo: str, es_paquete: bool) -> str | None:
    """Absolute module a ``from ... import`` reads from (``None`` if unknowable)."""
    if n.level == 0:
        return n.module or None
    paquete = modulo if es_paquete else (modulo.rsplit(".", 1)[0] if "." in modulo else "")
    partes = [p for p in paquete.split(".") if p]
    salto = n.level - 1
    if salto > len(partes):
        return None
    if salto:
        partes = partes[:-salto]
    base = ".".join(partes)
    if n.module:
        base = f"{base}.{n.module}" if base else n.module
    return base or None


def tabla_de_enlaces(arbol: ast.AST, modulo: str, es_paquete: bool) -> dict[str, tuple[str, str]]:
    """Module-level name -> ``(module, qualname)``; ``qualname == ""`` is a module.

    Only module-level statements are read: a binding made inside a function is
    not visible to a call site in another function, and pretending otherwise
    would resolve to the wrong object.
    """
    tabla: dict[str, tuple[str, str]] = {}
    for n in getattr(arbol, "body", []):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            tabla[n.name] = (modulo, n.name)
        elif isinstance(n, ast.Import):
            for al in n.names:
                if al.asname:
                    tabla[al.asname] = (al.name, "")
                else:
                    raiz = al.name.split(".")[0]
                    tabla[raiz] = (raiz, "")
        elif isinstance(n, ast.ImportFrom):
            base = _base_de_import(n, modulo, es_paquete)
            if base is None:
                continue
            for al in n.names:
                if al.name == "*":
                    continue
                tabla[al.asname or al.name] = (base, al.name)
    return tabla


def identidad_de_llamada(n: ast.Call, tabla: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    """``(module, qualname)`` of the callee, or ``None`` when it cannot be resolved."""
    f = n.func
    if isinstance(f, ast.Name):
        return tabla.get(f.id)
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        base = tabla.get(f.value.id)
        if base is None:
            return None
        modulo, cual = base
        return (modulo, f.attr) if cual == "" else (modulo, f"{cual}.{f.attr}")
    return None


def _sitios(n: ast.Call, arbol: ast.AST, padres: dict[int, ast.AST]):
    """Yield ``(linea_llamada, linea_consumo, forma)`` for one call site."""
    padre = padres.get(id(n))
    if _es_len(padre):
        yield n.lineno, padre.lineno, "DIRECTO"
        return
    if isinstance(padre, (ast.Assign, ast.AnnAssign)):
        objetivos = padre.targets if isinstance(padre, ast.Assign) else [padre.target]
        if len(objetivos) == 1 and isinstance(objetivos[0], ast.Name):
            cuerpo = _cuerpo_que_contiene(arbol, padre)
            for ln in _lecturas_de(objetivos[0].id, cuerpo, padre.lineno):
                yield n.lineno, ln, "VINCULO"
        return
    cuerpo = _cuerpo_que_contiene(arbol, n)
    for arg in n.args:
        if isinstance(arg, ast.Name):
            for ln in _lecturas_de(arg.id, cuerpo, n.lineno):
                yield n.lineno, ln, "PARAMETRO"


def _nombre_pelado(n: ast.Call) -> str:
    f = n.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def consumos(raiz: str | Path, productores: set[str]) -> Consumos:
    """Maps each producer key (``modulo::qualname``) to its identity-matched sites."""
    raiz = Path(raiz)
    out = Consumos(exactos={k: [] for k in productores})
    if not productores:
        return out
    colas = {k.rsplit(SEP, 1)[-1] for k in productores}
    base, fuentes = _fuentes(raiz)
    for p in fuentes:
        relp = p.relative_to(base)
        if any(part in IGNORADOS for part in relp.parts):
            continue
        try:
            arbol = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        rel = str(relp)
        modulo = modulo_de(rel)
        tabla = tabla_de_enlaces(arbol, modulo, p.name == "__init__.py")
        padres = _padres(arbol)
        for n in ast.walk(arbol):
            if not isinstance(n, ast.Call):
                continue
            ident = identidad_de_llamada(n, tabla)
            if ident is None:
                pelo = _nombre_pelado(n)
                if pelo in colas:
                    out.no_resueltos += 1
                    out.por_nombre.setdefault(pelo, []).append(
                        Consumidor(f"?{SEP}{pelo}", rel, n.lineno, n.lineno, "SIN_IDENTIDAD", "NOMBRE"))
                continue
            clave = f"{ident[0]}{SEP}{ident[1]}"
            if clave not in productores:
                continue
            out.sitios_llamada += 1
            for linea, consumo, forma in _sitios(n, arbol, padres):
                out.exactos[clave].append(
                    Consumidor(clave, rel, linea, consumo, forma, "EXACTO"))
    return out
