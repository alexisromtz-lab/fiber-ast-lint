"""Interprete de predicados: el juicio depende de la forma de la declaracion.

El contrato ``recibo/2`` hizo que la poblacion juzgada igualase la declarada, pero el juez
seguia siendo una tabla: ``EVALUADORES`` mapea dos identificadores a dos funciones escritas
a mano y las demas predicciones salen ``sin_evaluador``. Con esa forma, cada prediccion
historica cuesta una rama de codigo nueva, y el conjunto de lo juzgable lo decide quien
programa, no quien pre-registra.

Aqui la declaracion dice *donde mirar*, *como colapsar lo que se ve* y *contra que se
compara*::

    {"expr": {"de": "/actos/B/banda/k", "agrega": "valor"}, "rel": "lt", "valor": 0.1509}

y el instrumento resuelve. Ninguna regla de este modulo nombra una prediccion concreta: la
expresion K1 y una prediccion de otro arbol con la misma forma comparten camino.

Tres reglas que no son de estilo:

* **La ausencia se propaga, no se lee como cero.** Un puntero que no alcanza ningun valor
  devuelve ``None``, y ninguna comparacion con ``None`` produce veredicto: produce
  ``metrica_ausente``. Un cero de indice es estado del calculo, no estado del sujeto.
* **La poblacion vacia no es vacua.** Una conjuncion sobre cero elementos es cierta por
  vacuidad; publicarla como ``sobrevive`` seria el falso verde mas barato de escribir. Se
  publica ``poblacion_vacia``.
* **Lo ilegible no es falso.** Un operador desconocido o un puntero mal formado levantan
  ``Ilegible`` y el recibo publica ``predicado_ilegible``. Un predicado que el instrumento
  no entiende no es evidencia contra el sujeto.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

CONTRATO = "fiber-ast-lint/predicado/1"

RELACIONES = {
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "igual": lambda a, b: a == b,
    "entre": lambda a, b: b[0] <= a <= b[1],
    "fuera_de": lambda a, b: not (b[0] <= a <= b[1]),
}

AGREGADOS = ("valor", "max", "min", "media", "dispersion")
CUANTIFICADORES = ("todos", "alguno", "ninguno")
OPERADORES = ("razon", "diferencia", "abs_diferencia")


class Ilegible(Exception):
    """El predicado no es interpretable: ni verdadero ni falso, ilegible."""


class _Ausente(Exception):
    """La magnitud no esta en el objeto: se propaga como NO_MEDIDO, nunca como cero."""


class _PoblacionVacia(_Ausente):
    """La coleccion existe y ningun elemento declara la magnitud.

    No es lo mismo que una metrica ausente: aqui la poblacion se midio y tiene tamano cero,
    y cero elementos no es evidencia de nada. Se publica ``poblacion_vacia``, nunca ``true``.
    """


def _etiqueta(lista: list, paso: str) -> int | None:
    """El indice del elemento de ``lista`` que responde a ``paso``, o ``None`` si ninguno.

    Se admite el indice (``/actos/1``) y el nombre declarado (``/actos/B``). Devuelve -1
    cuando el paso tiene forma de seleccion pero no selecciona nada: eso no es un error, es
    un tramo ausente, y quien llama decide si la ausencia es una causa o un cero.
    """
    try:
        i = int(paso)
    except ValueError:
        i = None
    if i is not None and 0 <= i < len(lista):
        return i
    for j, e in enumerate(lista):
        if isinstance(e, dict) and str(e.get("nombre")) == paso:
            return j
    return -1 if (i is not None or any(isinstance(e, dict) and "nombre" in e for e in lista)) else None


def resolver(doc, puntero: str) -> list:
    """Los nodos que el puntero alcanza, en orden.

    ``*`` recorre una lista o, si el nodo es un mapa, sus claves ordenadas: la resolucion no
    puede depender del orden en que el JSON se escribio. ``[:n]`` y ``[n:]`` parten una lista
    por mitades, que es lo que una prediccion declara cuando habla del principio y del final.
    Un tramo que no existe no es un error: el nodo simplemente no aporta.
    """
    if not isinstance(puntero, str) or not puntero.startswith("/"):
        raise Ilegible(f"puntero mal formado: {puntero!r}")
    nodos = [doc]
    for paso in puntero[1:].split("/"):
        nuevos: list = []
        for n in nodos:
            if paso == "*":
                if isinstance(n, list):
                    nuevos.extend(n)
                elif isinstance(n, dict):
                    nuevos.extend(n[k] for k in sorted(n))
                else:
                    raise Ilegible(f"'*' sobre {type(n).__name__} en {puntero!r}")
            elif paso.startswith("[") and paso.endswith("]"):
                if not isinstance(n, list):
                    raise Ilegible(f"corte de lista sobre {type(n).__name__} en {puntero!r}")
                cuerpo = paso[1:-1]
                try:
                    if cuerpo.startswith(":"):
                        nuevos.extend(n[: int(cuerpo[1:])])
                    elif cuerpo.endswith(":"):
                        nuevos.extend(n[int(cuerpo[:-1]) :])
                    else:
                        nuevos.append(n[int(cuerpo)])
                except ValueError as e:
                    raise Ilegible(f"corte {paso!r} en {puntero!r}: {e}") from e
            elif isinstance(n, dict) and paso in n:
                nuevos.append(n[paso])
            elif isinstance(n, list) and _etiqueta(n, paso) is not None:
                # Un acto se nombra en la resolucion, no se cuenta: '/actos/B' tiene que
                # seguir diciendo lo mismo aunque el artefacto reordene sus actos.
                i = _etiqueta(n, paso)
                if i >= 0:
                    nuevos.append(n[i])
        nodos = nuevos
    return nodos


def _numeros(nodos: list, puntero: str) -> list[float]:
    out = []
    for n in nodos:
        if n is None:
            # Un campo declarado sin valor (una dispersion de un solo acto) no es un cero:
            # es una magnitud que el sujeto no tiene.
            raise _Ausente(puntero)
        if isinstance(n, bool) or not isinstance(n, (int, float)):
            raise Ilegible(f"{puntero!r} alcanzo un {type(n).__name__}, no un numero")
        out.append(float(n))
    return out


def _colapsa(nodos: list, agrega: str, puntero: str) -> float:
    if agrega not in AGREGADOS:
        raise Ilegible(f"agregado desconocido: {agrega!r}")
    if not nodos:
        raise _Ausente(puntero)
    xs = _numeros(nodos, puntero)
    if agrega == "valor":
        if len(xs) != 1:
            raise Ilegible(f"'valor' sobre {len(xs)} nodos en {puntero!r}")
        return xs[0]
    if agrega == "max":
        return max(xs)
    if agrega == "min":
        return min(xs)
    if agrega == "media":
        return sum(xs) / len(xs)
    if len(xs) < 2 or min(xs) == 0:
        raise _Ausente(f"dispersion de {puntero!r}")
    return max(xs) / min(xs)


def escalar(expr: dict, doc, ruta: str = "") -> float:
    """El valor de una expresion, o ``_Ausente`` si la magnitud no esta en el objeto."""
    if not isinstance(expr, dict):
        raise Ilegible(f"expresion no es un objeto en {ruta or '<raiz>'}")
    op = expr.get("op")
    if op is None:
        if "de" not in expr:
            raise Ilegible(f"expresion sin 'de' ni 'op' en {ruta or '<raiz>'}")
        return _colapsa(resolver(doc, expr["de"]), expr.get("agrega", "valor"), expr["de"])
    if op not in OPERADORES:
        raise Ilegible(f"operador desconocido: {op!r}")
    a = escalar(expr.get("a"), doc, f"{ruta}/{op}/a")
    b = escalar(expr.get("b"), doc, f"{ruta}/{op}/b")
    if op == "razon":
        if b == 0:
            raise _Ausente(f"razon con denominador cero en {ruta or '<raiz>'}")
        return a / b
    if op == "diferencia":
        return a - b
    return abs(a - b)


def _compara(rel: str, valor, contra) -> bool:
    if rel not in RELACIONES:
        raise Ilegible(f"relacion desconocida: {rel!r}")
    if rel in ("entre", "fuera_de"):
        if not isinstance(contra, list) or len(contra) != 2:
            raise Ilegible(f"{rel!r} exige una cota de dos numeros, no {contra!r}")
    return RELACIONES[rel](valor, contra)


def _poblacion(puntero: str, doc) -> list:
    nodos = resolver(doc, puntero)
    if nodos:
        return nodos
    # El puntero tiene dos formas de no dar nada, y no son la misma cosa: si la coleccion
    # existe pero ningun elemento declara la magnitud, la poblacion es de tamano cero; si
    # no hay ni coleccion, el puntero no resolvio contra este documento.
    if "*" in puntero and resolver(doc, puntero.rsplit("/", 1)[0]):
        raise _PoblacionVacia(puntero)
    raise _Ausente(puntero)


def evaluar(pred: dict, doc) -> dict:
    """El veredicto de un predicado sobre un recibo.

    Devuelve siempre un registro con ``estado``: ``evaluado`` con ``sobrevive`` y ``medido``,
    o ``no_medido`` con la causa exacta. Un predicado mal formado no lanza: se publica.
    """
    try:
        sobrevive, medido = _pred(pred, doc, "")
    except _PoblacionVacia as e:
        return {"estado": "no_medido", "causa": "poblacion_vacia", "magnitud": str(e)}
    except _Ausente as e:
        return {"estado": "no_medido", "causa": "metrica_ausente", "magnitud": str(e)}
    except Ilegible as e:
        return {"estado": "no_medido", "causa": "predicado_ilegible", "detalle": str(e)}
    except (KeyError, TypeError, ValueError) as e:
        return {"estado": "no_medido", "causa": "predicado_ilegible",
                "detalle": f"{type(e).__name__}: {e}"}
    return {"estado": "evaluado", "sobrevive": sobrevive, "medido": medido}


def _pred(pred: dict, doc, ruta: str) -> tuple[bool, dict]:
    if not isinstance(pred, dict):
        raise Ilegible(f"predicado no es un objeto en {ruta or '<raiz>'}")
    if "y" in pred:
        if not pred["y"]:
            raise _Ausente("conjuncion sin terminos")
        partes = [_pred(p, doc, f"{ruta}/y/{i}") for i, p in enumerate(pred["y"])]
        return all(s for s, _ in partes), {"y": [m for _, m in partes]}
    if "o" in pred:
        if not pred["o"]:
            raise _Ausente("disyuncion sin terminos")
        partes = [_pred(p, doc, f"{ruta}/o/{i}") for i, p in enumerate(pred["o"])]
        return any(s for s, _ in partes), {"o": [m for _, m in partes]}
    if "no" in pred:
        s, m = _pred(pred["no"], doc, f"{ruta}/no")
        return (not s), {"no": m}
    for cuant in CUANTIFICADORES:
        if cuant in pred:
            return _cuantifica(cuant, pred, doc, ruta)
    if "expr" in pred:
        valor = escalar(pred["expr"], doc, ruta)
        rel, contra = pred.get("rel"), pred.get("valor")
        if rel is None or "valor" not in pred:
            raise Ilegible(f"comparacion sin 'rel' o sin 'valor' en {ruta or '<raiz>'}")
        return _compara(rel, valor, contra), {"expr": round(valor, 6), "rel": rel, "valor": contra}
    raise Ilegible(f"predicado sin forma reconocible en {ruta or '<raiz>'}")


def _cuantifica(cuant: str, pred: dict, doc, ruta: str) -> tuple[bool, dict]:
    """Un cuantificador sobre una poblacion de punteros.

    Los elementos que no declaran la magnitud no entran en la poblacion: un acto que no
    corrio la sonda no vota sobre la sonda. Pero si no queda nadie, no hay verdad vacuidad:
    hay NO_MEDIDO, porque cero elementos no es evidencia de nada.
    """
    puntero = pred["de"]
    criterio = pred[cuant]
    if not isinstance(criterio, dict):
        raise Ilegible(f"{cuant!r} exige un criterio con 'rel' y 'valor' en {ruta or '<raiz>'}")
    rel, contra = criterio.get("rel"), criterio.get("valor")
    if rel is None or "valor" not in criterio:
        raise Ilegible(f"criterio de {cuant!r} incompleto en {ruta or '<raiz>'}")
    poblacion = _poblacion(puntero, doc)
    xs = _numeros(poblacion, puntero)
    cumplen = [x for x in xs if _compara(rel, x, contra)]
    fallan = [round(x, 6) for x in xs if not _compara(rel, x, contra)]
    medido = {"poblacion": len(xs), "cumplen": len(cumplen), "rel": rel,
              "valor": contra, "fallan": fallan}
    if cuant == "todos":
        return len(cumplen) == len(xs), medido
    if cuant == "alguno":
        return bool(cumplen), medido
    return not cumplen, medido


def leer(ruta: Path | None, junto_a: Path | None = None) -> tuple[dict, dict | None]:
    """Los predicados de un lote, atados al pre-registro que traducen.

    La traduccion declara el sha256 del texto que traduce. Si el texto cambia, el predicado
    deja de valer: no se puede traducir un pre-registro que ya no es el que se leyo.
    """
    if ruta is None or not ruta.exists():
        return {}, None
    crudo = ruta.read_bytes()
    doc = json.loads(crudo)
    cita = doc.get("cita_pre_registro") or {}
    if not cita.get("ruta") or not cita.get("sha256"):
        raise Ilegible(f"{ruta.name} no cita el pre-registro que traduce")
    base = junto_a if junto_a is not None else ruta.parent
    objetivo = base / cita["ruta"]
    if not objetivo.exists():
        raise Ilegible(f"{ruta.name} cita un pre-registro que no esta: {cita['ruta']}")
    real = hashlib.sha256(objetivo.read_bytes()).hexdigest()
    if real != cita["sha256"]:
        raise Ilegible(f"{ruta.name} cita {cita['sha256']} y el texto es {real}")
    mapa = {}
    for p in doc.get("predicados", []):
        if "id" not in p or "evalua" not in p:
            raise Ilegible(f"predicado sin 'id' o sin 'evalua' en {ruta.name}")
        mapa[p["id"]] = p
    return mapa, {
        "ruta": ruta.name,
        "sha256": hashlib.sha256(crudo).hexdigest(),
        "predicados": len(mapa),
        "cita_pre_registro": dict(cita),
    }
