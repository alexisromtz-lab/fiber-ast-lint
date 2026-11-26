"""Structural detection of lossy key projections in Python source.

THE LAW THIS MODULE IMPLEMENTS
------------------------------
A dictionary built as ``acc[pi(k)] = v`` where ``pi`` is not injective keeps
only ``|im(pi)|`` of the ``|domain|`` entries it received. The mass
``sum_k (|pi^-1(k)| - 1)`` is destroyed **silently**: no exception, no
warning, no log line. The only static guard that makes the loss visible is an
explicit ``if k not in acc`` (which turns it into a countable bucket), because
a guard drawn from the *codomain* (``pi(k) in ALLOWED``) can never suppress a
kernel: ``ALLOWED`` necessarily contains images of non-trivial fibers.

WHAT IS MEASURED (structural signatures, not names)
---------------------------------------------------
For every ``for`` loop in a function or module:

  1. ``PERDIDA``      the loop reads and writes the same accumulator by index,
                      the written value does not mention the accumulator, and
                      nobody asks ``k in acc`` anywhere in the loop.
  2. ``ACUMULACION``  the written value reads the accumulator
                      (``acc[k] = acc.get(k, 0) + x``): aggregation, not loss.
  3. ``GUARDADA``     the loop asks ``k in acc`` at any point: the loss becomes
                      a visible bucket.
  4. ``POSICIONAL``   the accumulator was born a sequence: ``acc[i] = x``
                      replaces row i and cannot change cardinality.
  5. ``CARDINAL_SIN_MEDIR``  nobody calls ``len(acc)`` in the scope: the loss
                      is invisible even to the program itself.

A locus is only *actionable* when it can change another decision:
the accumulator escapes its function (returned) **and** the function is called
somewhere in the analysed universe. Otherwise the defect is latent and the
report says so instead of spending a reader's time.

The instrument applies its own law: it publishes the census of what it
discarded and refuses to emit (RC 4) when the buckets do not add up.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

RC_OK, RC_CANDIDATO, RC_VACIO, RC_CONSERVACION = 0, 1, 2, 4

# Filtered against the path RELATIVE to the requested root. ``site-packages`` is
# deliberately absent: a user analysing one installed package has it as root,
# and excluding it by absolute path made the instrument report an empty
# universe over hundreds of present modules (measured 2026-11-24).
IGNORADOS = {
    "__pycache__", ".git", ".hg", ".svn", ".venv", "venv", "env",
    "node_modules", "build", "dist", ".tox", ".eggs", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".nox",
}

ESCRITURAS = {"add", "update", "append", "extend", "insert", "setdefault", "appendleft"}

# Pure operators that can fuse two distinct inputs into one key.
OPS = {
    "strip": "ESPACIO", "lstrip": "ESPACIO", "rstrip": "ESPACIO",
    "lower": "CAJA", "upper": "CAJA", "casefold": "CAJA", "title": "CAJA",
    "split": "SEPARADOR", "rsplit": "SEPARADOR", "partition": "SEPARADOR",
    "rpartition": "SEPARADOR", "splitlines": "SEPARADOR",
    "removeprefix": "PREFIJO", "removesuffix": "PREFIJO",
    "basename": "RUTA", "dirname": "RUTA", "stem": "RUTA", "suffix": "RUTA",
    "normpath": "RUTA", "resolve": "RUTA", "absolute": "RUTA",
    "expanduser": "RUTA", "name": "RUTA",
    "group": "REGEX", "groups": "REGEX", "findall": "REGEX", "match": "REGEX",
    "search": "REGEX", "sub": "REGEX", "fullmatch": "REGEX",
    "replace": "NORMALIZA", "translate": "NORMALIZA", "normalize": "NORMALIZA",
    "unidecode": "NORMALIZA",
}
RECORTE = {"strip", "lstrip", "rstrip"}
LETALES = {
    "split", "rsplit", "splitlines", "partition", "rpartition",
    "removeprefix", "removesuffix", "strip", "lstrip", "rstrip",
    "lower", "upper", "casefold", "replace", "translate",
    "stem", "suffix", "name", "resolve", "absolute", "normpath",
    "basename", "dirname", "expanduser", "normalize", "unidecode",
}
PUBLICADORES = {
    "print", "write", "writelines", "debug", "info", "warning", "error",
    "critical", "exception", "dump", "dumps", "format",
}

NACEN_SECUENCIA = {
    "list", "sorted", "range", "tuple", "reversed", "enumerate", "zip",
    "split", "splitlines", "rsplit", "keys", "values", "items",
}
NACEN_DICCIONARIO = {"dict", "defaultdict", "Counter", "OrderedDict"}
TIPOS_SECUENCIA = {"list", "List", "Sequence", "MutableSequence", "tuple", "Tuple"}


# --------------------------------------------------------------------------- #
# Small structural readers
# --------------------------------------------------------------------------- #
def escritos_en(cuerpo: list[ast.stmt]) -> set[str]:
    """Containers the body WRITES (the loop's inner population)."""
    out: set[str] = set()
    for raiz in cuerpo:
        for x in ast.walk(raiz):
            if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute):
                if x.func.attr in ESCRITURAS and isinstance(x.func.value, ast.Name):
                    out.add(x.func.value.id)
            elif isinstance(x, ast.Assign):
                for t in x.targets:
                    if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name):
                        out.add(t.value.id)
                    if isinstance(t, ast.Name) and isinstance(x.value, ast.BinOp) \
                            and isinstance(x.value.op, (ast.BitOr, ast.Add)):
                        out.add(t.id)
            elif isinstance(x, ast.AugAssign) and isinstance(x.target, ast.Name):
                out.add(x.target.id)
    return out


def leidos_en(cuerpo: list[ast.stmt]) -> set[str]:
    """Names the body READS. An internal accumulator is read and written."""
    out: set[str] = set()
    for raiz in cuerpo:
        for x in ast.walk(raiz):
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load):
                out.add(x.id)
    return out


def objetivo_del_for(n: ast.For) -> set[str]:
    return {x.id for x in ast.walk(n.target) if isinstance(x, ast.Name)}


def rebindeados(cuerpo: list[ast.stmt]) -> set[str]:
    """Names RE-CREATED inside the loop: per-iteration, not accumulators.

    ``fila = {}`` at the top of the body makes ``fila['x'] = y`` write a new
    row, not a repeated entry. Without this exclusion the census fills with
    rows and the instrument loses its reader.
    """
    out: set[str] = set()
    for raiz in cuerpo:
        for x in ast.walk(raiz):
            if isinstance(x, ast.Assign):
                for t in x.targets:
                    if isinstance(t, ast.Name):
                        out.add(t.id)
            elif isinstance(x, (ast.AnnAssign, ast.AugAssign)) \
                    and isinstance(x.target, ast.Name):
                out.add(x.target.id)
            elif isinstance(x, (ast.For, ast.AsyncFor, ast.With, ast.AsyncWith)):
                for t in ast.walk(x):
                    if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store):
                        out.add(t.id)
    return out


def pertenencia_con_continue(h: ast.If) -> bool:
    t = h.test
    if not isinstance(t, ast.Compare) or len(t.ops) != 1:
        return False
    if not isinstance(t.ops[0], (ast.In, ast.NotIn)):
        return False
    return len(h.body) == 1 and isinstance(h.body[0], ast.Continue)


def clase_de_clave(t: ast.Subscript) -> bool:
    """The key is COMPUTED: not a fixed schema field."""
    return not isinstance(t.slice, ast.Constant)


def almacenes(cuerpo: list[ast.stmt], interno: set[str],
              ajenos: set[int]) -> list[tuple[ast.AST, str, str]]:
    """Writes ``acc[key] = ...`` on a loop-internal accumulator.

    ``ajenos`` excludes nodes of nested loops: without it one store is
    attributed to both the outer and the inner ``For`` and the census stops
    reconciling.
    """
    out: list[tuple[ast.AST, str, str]] = []
    for raiz in cuerpo:
        for x in ast.walk(raiz):
            if id(x) in ajenos:
                continue
            if isinstance(x, (ast.Assign, ast.AnnAssign)):
                objetivos = x.targets if isinstance(x, ast.Assign) else [x.target]
                for t in objetivos:
                    if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) \
                            and t.value.id in interno and clase_de_clave(t):
                        out.append((x, t.value.id, ast.unparse(x)))
    return out


def clave_de(nodo: ast.Assign | ast.AnnAssign, acc: str) -> ast.AST | None:
    objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
    for tg in objetivos:
        if isinstance(tg, ast.Subscript) and isinstance(tg.value, ast.Name) \
                and tg.value.id == acc:
            return tg.slice
    return None


def tipo_secuencia(anotacion: ast.AST | None) -> bool:
    if anotacion is None:
        return False
    if isinstance(anotacion, ast.Name):
        return anotacion.id in TIPOS_SECUENCIA
    if isinstance(anotacion, ast.Subscript):
        base = anotacion.value
        return isinstance(base, ast.Name) and base.id in TIPOS_SECUENCIA
    return False


def nombres_de_secuencia(cuerpo: list[ast.stmt]) -> set[str]:
    """Containers that are BORN sequences: they have no key space at all.

    An indexed sequence preserves its cardinality by construction: ``s[i] = x``
    replaces row i, it never removes it. Only a dict or a set can lose mass to a
    key collision, so a missing guard on a sequence is not a defect.
    """
    secuencias: set[str] = set()
    diccionarios: set[str] = set()
    for raiz in cuerpo:
        for x in ast.walk(raiz):
            if isinstance(x, ast.arg) and tipo_secuencia(x.annotation):
                secuencias.add(x.arg)
            if isinstance(x, ast.Assign) and len(x.targets) == 1:
                objetivo = x.targets[0]
            elif isinstance(x, ast.AnnAssign):
                objetivo = x.target
            else:
                continue
            if not isinstance(objetivo, ast.Name):
                continue
            if isinstance(x, ast.AnnAssign) and tipo_secuencia(x.annotation):
                secuencias.add(objetivo.id)
            v = x.value
            if isinstance(v, (ast.List, ast.Tuple, ast.ListComp, ast.SetComp)):
                secuencias.add(objetivo.id)
            elif isinstance(v, (ast.Dict, ast.DictComp)):
                diccionarios.add(objetivo.id)
            elif isinstance(v, ast.Call):
                f = v.func
                nombre = f.id if isinstance(f, ast.Name) else (
                    f.attr if isinstance(f, ast.Attribute) else "")
                if nombre in NACEN_SECUENCIA:
                    secuencias.add(objetivo.id)
                elif nombre in NACEN_DICCIONARIO:
                    diccionarios.add(objetivo.id)
    return secuencias - diccionarios


def nombres_con_len(cuerpo: list[ast.stmt]) -> set[str]:
    """Containers whose cardinality SOMEONE measures again in the same scope.

    An accumulator nobody measures loses no *observable* mass: the overwrite is
    invisible because there is no published magnitude to betray it.
    """
    out: set[str] = set()
    for raiz in cuerpo:
        for x in ast.walk(raiz):
            if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) \
                    and x.func.id == "len" and x.args and isinstance(x.args[0], ast.Name):
                out.add(x.args[0].id)
    return out


def clase_de_escritura(nodo: ast.AST, acc: str) -> str:
    """Classifies ``acc[k] = value``. Only ``pierde`` is a name to review."""
    valor = getattr(nodo, "value", None)
    if valor is None:
        return "pierde"
    for x in ast.walk(valor):
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load) and x.id == acc:
            return "acumulacion"
    # Mentioning the loop variable does NOT preserve the previous tenant of that
    # key: ``acc[k] = x`` loses the earlier iteration even when x is the subject.
    return "pierde"


def pregunta_pertenencia(cuerpo: list[ast.stmt], acc: str) -> bool:
    """Does the loop ask ``... in acc`` / ``... not in acc`` anywhere?"""
    for raiz in cuerpo:
        for x in ast.walk(raiz):
            if isinstance(x, ast.Compare):
                for op, comp in zip(x.ops, x.comparators):
                    if isinstance(op, (ast.In, ast.NotIn)) \
                            and isinstance(comp, ast.Name) and comp.id == acc:
                        return True
    return False


def ops_de(nodo: ast.AST) -> set[str]:
    out: set[str] = set()
    for x in ast.walk(nodo):
        nombre = ""
        if isinstance(x, ast.Call):
            f = x.func
            if isinstance(f, ast.Attribute):
                nombre = f.attr
                if nombre in RECORTE and x.args:
                    out.add("CONJUNTO")
                    continue
            elif isinstance(f, ast.Name):
                nombre = f.id
        elif isinstance(x, ast.Attribute):
            nombre = x.attr
        if nombre in OPS:
            out.add(OPS[nombre])
        if isinstance(x, ast.Slice):
            out.add("REBANADA")
    return out


def familia_de(clave: ast.AST, resuelto: ast.AST | None) -> str:
    """The family is the SET of pure operators in the resolved key.

    Declared invariance: order does not enter. ``strip().lower()`` and
    ``lower().strip()`` have the same kernel. Limit: the resolved function's
    tree drags operators that do not touch the key, so the family is published
    as an upper bound of the kernel, not as the exact kernel.
    """
    ops = ops_de(clave)
    if resuelto is not None:
        ops |= ops_de(resuelto)
    return "+".join(sorted(ops)) if ops else "IDENTIDAD"


def llamadas_de(nodo: ast.AST) -> set[str]:
    out: set[str] = set()
    for x in ast.walk(nodo):
        if isinstance(x, ast.Call):
            f = x.func
            if isinstance(f, ast.Attribute):
                out.add(f.attr)
            elif isinstance(f, ast.Name):
                out.add(f.id)
    return out


def tiene_rebanada(nodo: ast.AST) -> bool:
    return any(isinstance(x, ast.Slice) for x in ast.walk(nodo))


def raiz_de(cadena: ast.AST) -> ast.Name | None:
    """Root ``Name`` of an attribute chain: ``a.b.c`` -> ``a``; else ``None``."""
    while isinstance(cadena, ast.Attribute):
        cadena = cadena.value
    return cadena if isinstance(cadena, ast.Name) else None


def forma_de_clave(clave: ast.AST, objetivo: set[str]) -> str:
    """The ladder, decided only by the syntactic shape of the key."""
    if isinstance(clave, ast.Name):
        return "IDENTIDAD_BUCLE" if clave.id in objetivo else "PROCEDENCIA_OCULTA"
    if isinstance(clave, ast.Attribute) and (
            r := raiz_de(clave)) is not None and r.id in objetivo:
        # ``acc[fila.codigo] = fila``: the key is ONE COLUMN of the row, not the
        # row. Two rows that share the column fuse, so the key space is the
        # column's image, not the domain. ``SELECCION`` alone cannot say this:
        # it also covers ``acc[cfg.key]``, whose root is not the loop variable.
        return "SELECCION_COLUMNA_BUCLE"
    if isinstance(clave, (ast.Subscript, ast.Attribute)):
        return "SELECCION"
    if tiene_rebanada(clave) or (llamadas_de(clave) & LETALES):
        return "PROYECCION_VISIBLE"
    return "EXPRESION"


def perdida_en_cuerpo(fn: ast.AST) -> bool:
    if tiene_rebanada(fn):
        return True
    return bool(llamadas_de(fn) & LETALES)


def resolver_arriba(clave: ast.Name, foro: ast.For, ambito: list[ast.stmt],
                    locales: dict[str, ast.AST]) -> tuple[str, str, ast.AST | None]:
    """Follows a ``Name`` to its visible assignment and checks whether it projects."""
    candidatas: list[ast.stmt] = [s for s in ast.walk(foro) if isinstance(s, ast.Assign)]
    candidatas += [s for s in ast.walk(ast.Module(body=list(ambito), type_ignores=[]))
                   if isinstance(s, ast.Assign)]
    elegida: ast.Assign | None = None
    for s in candidatas:
        if s.lineno > clave.lineno:
            continue
        for t in s.targets:
            if isinstance(t, ast.Name) and t.id == clave.id:
                if elegida is None or s.lineno >= elegida.lineno:
                    elegida = s
    if elegida is None or not isinstance(elegida.value, ast.Call):
        return "PROCEDENCIA_OCULTA", "sin asignacion visible", None
    f = elegida.value.func
    nombre = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
    if nombre in LETALES:
        return ("PROYECCION_ARRIBA_CON_PERDIDA",
                f"{nombre}() en linea {elegida.lineno}", elegida.value)
    fn = locales.get(nombre)
    if fn is None:
        return "PROCEDENCIA_OCULTA", f"{nombre}() no es local", None
    if perdida_en_cuerpo(fn):
        return ("PROYECCION_ARRIBA_CON_PERDIDA",
                f"{nombre}() linea {elegida.lineno} proyecta", fn)
    return "PROYECCION_ARRIBA_SIN_PERDIDA", f"{nombre}() linea {elegida.lineno}", fn


def escapa(fn: ast.AST | None, acc: str) -> bool:
    """A module-level accumulator is visible from the whole file; a local one
    escapes only when someone returns it."""
    if fn is None:
        return True
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and n.value is not None:
            if any(isinstance(x, ast.Name) and x.id == acc for x in ast.walk(n.value)):
                return True
    return False


def publica_nodo(n: ast.AST) -> bool:
    """Contexts where a value leaves the program or becomes a ratio."""
    if isinstance(n, (ast.Return, ast.JoinedStr)):
        return True
    if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Div, ast.Mod)):
        return True
    if isinstance(n, ast.Call):
        f = n.func
        nombre = f.attr if isinstance(f, ast.Attribute) else (
            f.id if isinstance(f, ast.Name) else "")
        return nombre in PUBLICADORES
    return False


SIN_DESCENSO = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
# A class body is not a scope for this census: its statements belong to the
# enclosing frame (its methods are analysed by their own pass), so the walk
# descends into it and stops only at callables.
SIN_DESCENSO_DE_AMBITO = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def publicacion(cuerpo: list[ast.stmt], acc: str) -> str:
    """Does the measured cardinal of ``acc`` reach an output of the program?

    A ``print(f"{len(acc)}")``, a ``return len(acc)`` or a ratio with it publish
    ``|im(pi)|`` as if it were the domain; an internal ``len()`` (loop bound,
    comparison) publishes nothing. Limit: no alias tracking
    (``x = len(acc); print(x)``), no attribute form (``len(acc.keys())``), no
    interprocedural step: those return ``NO_MEDIDO``, never 0.
    """
    visto = {"SI": False, "NO": False}

    def baja(n: ast.AST, ctx: bool) -> None:
        ctx = ctx or publica_nodo(n)
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "len" and len(n.args) == 1
                and isinstance(n.args[0], ast.Name) and n.args[0].id == acc):
            visto["SI" if ctx else "NO"] = True
        if isinstance(n, SIN_DESCENSO):
            return
        for h in ast.iter_child_nodes(n):
            baja(h, ctx)

    for raiz in cuerpo:
        baja(raiz, False)
    if visto["SI"]:
        return "SI"
    if visto["NO"]:
        return "NO"
    return "NO_MEDIDO"


def nodos_sin_funciones(raiz: ast.AST):
    """Walks a subtree without descending into nested scopes.

    A function definition found here is never descended into, *including* when
    it is the root itself: every ``FunctionDef`` in a module is analysed by its
    own pass, so descending here would count the same store twice (once as
    ``fn=<nombre>`` and once as ``fn=<modulo>``) and silently inflate the census.
    """
    pila = [raiz]
    while pila:
        n = pila.pop()
        yield n
        if isinstance(n, SIN_DESCENSO_DE_AMBITO):
            continue
        pila.extend(ast.iter_child_nodes(n))


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #
@dataclass
class Locus:
    rel: str
    linea: int
    texto: str
    poblacion: str          # "pierde" | "cardinal_sin_medir"
    op: str                 # "pierde" | "acumulacion"
    forma: str
    familia: str
    fn: str
    escapa: bool
    llamadas: int
    publica: str
    clave: str
    nota: str = ""
    qn: str = ""            # qualified name inside the module (``C.m``)
    consumidor: str = ""    # filled by graph.consumos

    @property
    def candidato(self) -> bool:
        """Actionable: destructive write on a visible projection."""
        return self.op == "pierde" and self.forma in (
            "PROYECCION_VISIBLE", "PROYECCION_ARRIBA_CON_PERDIDA",
            "SELECCION_COLUMNA_BUCLE")

    @property
    def admitido(self) -> bool:
        """A fiber only changes a decision if the accumulator leaves its
        function and someone calls that function."""
        return self.candidato and self.escapa and self.llamadas > 0

    @property
    def severidad(self) -> str:
        if not self.candidato:
            return "INFO"
        if self.admitido:
            return "CANDIDATO"
        return "LATENTE"


@dataclass
class Analisis:
    raiz: str
    archivos: int = 0
    fallas: int = 0
    for_medidos: int = 0
    almacenes: int = 0
    pierde: int = 0
    guardadas: int = 0
    acumulacion: int = 0
    posicional: int = 0
    sin_len: int = 0
    loci: list[Locus] = field(default_factory=list)
    llamadas: dict[str, int] = field(default_factory=dict)
    errores: list[str] = field(default_factory=list)

    def reconcilia(self) -> bool:
        return self.almacenes == (self.pierde + self.guardadas + self.acumulacion
                                  + self.posicional + self.sin_len)

    def certifica(self) -> bool:
        """La identidad sola no certifica: 0 = 0 cierra por no haber poblacion."""
        return self.almacenes > 0 and self.reconcilia()

    @property
    def admitidos(self) -> list[Locus]:
        return [x for x in self.loci if x.admitido]

    @property
    def candidatos(self) -> list[Locus]:
        return [x for x in self.loci if x.candidato]


def _ambito(cuerpo: list[ast.stmt], rel: str, locales: dict[str, ast.AST],
            a: Analisis, firma: list[ast.arg] = (), fn: ast.AST | None = None,
            qn: str = "") -> None:
    medido = nombres_con_len(cuerpo)
    secuencias = nombres_de_secuencia(cuerpo)
    # ast.arg nodes hang off the FunctionDef, not off its body: without this a
    # parameter ``lineas: list[str]`` never reaches the classifier and its store
    # is counted as ``pierde`` instead of ``posicional``.
    secuencias |= {x.arg for x in firma if tipo_secuencia(x.annotation)}
    for raiz in cuerpo:
        for n in nodos_sin_funciones(raiz):
            if not isinstance(n, ast.For):
                continue
            a.for_medidos += 1
            objetivo = objetivo_del_for(n)
            escritos = escritos_en(n.body)
            interno = (escritos & leidos_en(n.body)) - objetivo - rebindeados(n.body)
            ajenos: set[int] = set()
            for sub in ast.walk(n):
                if sub is not n and isinstance(sub, (ast.For, ast.AsyncFor)):
                    ajenos.update(id(x) for x in ast.walk(sub))
            for nodo, acc, txt in almacenes(n.body, interno, ajenos):
                a.almacenes += 1
                clave = clave_de(nodo, acc)
                if clave is None:
                    continue
                if acc in secuencias:
                    a.posicional += 1
                    continue
                if pregunta_pertenencia(n.body, acc):
                    a.guardadas += 1
                    continue
                poblacion = "pierde" if acc in medido else "cardinal_sin_medir"
                clase = clase_de_escritura(nodo, acc)
                # Aggregation is never a loss, whoever measures the cardinal: the
                # bucket answers "what kind of write is this", not "did anyone
                # look". Bucketing it under ``cardinal_sin_medir`` would file a
                # monoid with the unreported losses.
                if clase == "acumulacion":
                    a.acumulacion += 1
                elif poblacion == "pierde":
                    a.pierde += 1
                else:
                    a.sin_len += 1
                forma = forma_de_clave(clave, objetivo)
                resuelto = None
                nota = ""
                if forma == "PROCEDENCIA_OCULTA" and isinstance(clave, ast.Name):
                    forma, nota, resuelto = resolver_arriba(clave, n, cuerpo, locales)
                # A column of the row is not an operator applied to the key, so
                # ``familia_de`` would answer IDENTIDAD and hide the projection.
                familia = ("COLUMNA" if forma == "SELECCION_COLUMNA_BUCLE"
                           else familia_de(clave, resuelto))
                loc = Locus(
                    rel=rel, linea=nodo.lineno, texto=txt, poblacion=poblacion,
                    op=clase, forma=forma, familia=familia,
                    fn=getattr(fn, "name", ""), escapa=escapa(fn, acc),
                    llamadas=0, qn=qn,
                    publica=(publicacion(cuerpo, acc) if poblacion == "pierde" else "SIN_LEN"),
                    clave=ast.unparse(clave), nota=nota,
                )
                a.loci.append(loc)


def _qualnames(arbol: ast.AST) -> dict[int, str]:
    """id(FunctionDef) -> dotted name inside its module, with enclosing classes."""
    padres: dict[int, ast.AST] = {}
    for n in ast.walk(arbol):
        for h in ast.iter_child_nodes(n):
            padres[id(h)] = n
    out: dict[int, str] = {}
    for n in ast.walk(arbol):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        partes = [n.name]
        p = padres.get(id(n))
        while p is not None:
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                partes.append(p.name)
            p = padres.get(id(p))
        out[id(n)] = ".".join(reversed(partes))
    return out


def _fuentes(raiz: Path) -> tuple[Path, list[Path]]:
    """``(base, files)``: a directory is searched, an explicit ``.py`` is taken as is.

    Accepting a file matters for a linter: ``fiber-ast-lint src/app.py`` is how
    the tool gets called from an editor or a pre-commit hook, and answering
    "empty universe" there was a wrong zero, not a small one.
    """
    if raiz.is_file():
        return raiz.parent, [raiz] if raiz.suffix == ".py" else []
    if raiz.is_dir():
        return raiz, sorted(raiz.rglob("*.py"))
    return raiz, []


def analizar(raiz: str | Path) -> Analisis:
    """Analyses every ``*.py`` under ``raiz`` and returns the census."""
    raiz = Path(raiz)
    a = Analisis(raiz=str(raiz))
    base, fuentes = _fuentes(raiz)
    for p in fuentes:
        relp = p.relative_to(base)
        if any(part in IGNORADOS for part in relp.parts):
            continue
        try:
            arbol = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except (SyntaxError, UnicodeDecodeError, OSError) as e:
            a.fallas += 1
            a.errores.append(f"{relp}: {type(e).__name__}: {e}")
            continue
        a.archivos += 1
        rel = str(relp)
        for n in ast.walk(arbol):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                a.llamadas[n.func.id] = a.llamadas.get(n.func.id, 0) + 1
        locales = {n.name: n for n in ast.walk(arbol)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        qns = _qualnames(arbol)
        for fn in [n for n in ast.walk(arbol)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            _ambito(fn.body, rel, locales, a,
                    [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs], fn,
                    qns.get(id(fn), fn.name))
        _ambito(arbol.body, rel, locales, a)
    # The consumer count is taken over the already-walked universe: "called"
    # means nothing before this pass. Kept here so importers never get silent
    # zeros.
    for loc in a.loci:
        loc.llamadas = a.llamadas.get(loc.fn, 0) if loc.fn else 1
    return a
