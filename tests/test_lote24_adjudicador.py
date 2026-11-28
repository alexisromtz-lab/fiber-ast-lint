"""El adjudicador decide o se abstiene: nunca adivina.

La ley que estos casos fijan es asimetrica a proposito. Una abstencion cuesta
cobertura y no cuesta precision, asi que el error que se persigue aqui es el
falso teorema --una fila que el modulo decide y cuya causa el lector humano
nombro de otra manera-- y no la fila que deja de decidir.
"""
from __future__ import annotations

import ast

import pytest

from fiber_ast_lint.adjudicador_ast import (
    CAUSAS_DECIDIBLES,
    NO_PARSEA,
    POSICIONAL,
    SIN_CAUSA,
    adjudicar,
    causa_de_escritura,
    causa_por_localidad,
    nodo_de_escritura,
)

# El unico locus de la cohorte del lote 22 con familia REBANADA y causa distinta
# de escritura_posicional. Tiene rebanada y por tanto se parece a los otros 25,
# pero la rebanada va envuelta en una condicional sobre una llamada: el indice
# ya no es una direccion, es un calculo, y el teorema no lo cubre.
CASO_FRONTERA = (
    "def juntar(entidades, clave, sufijo, salida):\n"
    "    for entidad in entidades:\n"
    "        salida[clave[: -len(sufijo)] if clave.endswith(sufijo) else clave] = entidad\n"
)


def _arbol(fuente: str) -> ast.Module:
    return ast.parse(fuente)


def _primera_escritura(fuente: str, linea: int | None = None) -> ast.AST | None:
    arbol = _arbol(fuente)
    if linea is not None:
        return nodo_de_escritura(arbol, linea)
    for x in ast.walk(arbol):
        if isinstance(x, (ast.Assign, ast.AnnAssign)):
            return x
    return None


def test_t1_la_rebanada_no_tiene_clave() -> None:
    nodo = _primera_escritura("def f(a, v):\n    a[y0:y1] = v\n")
    assert causa_de_escritura(nodo) == POSICIONAL


def test_t1_la_mascara_por_columnas_tampoco() -> None:
    nodo = _primera_escritura("def f(a, v, i):\n    a[:, i] = v\n")
    assert causa_de_escritura(nodo) == POSICIONAL


def test_t1_un_indice_escalar_es_una_clave_y_no_se_decide() -> None:
    nodo = _primera_escritura("def f(a, v, k):\n    a[k] = v\n")
    assert causa_de_escritura(nodo) == SIN_CAUSA


def test_t1_una_llamada_dentro_del_indice_abre_el_predicado() -> None:
    nodo = _primera_escritura("def f(a, v, k):\n    a[k.strip().lower()] = v\n")
    assert causa_de_escritura(nodo) == SIN_CAUSA


def test_t1_el_caso_frontera_de_la_cohorte_no_se_decide() -> None:
    """Rebanada presente, pero envuelta en condicional: no es direccion."""
    nodo = _primera_escritura(CASO_FRONTERA, 3)
    assert nodo is not None
    assert causa_de_escritura(nodo) == SIN_CAUSA


def test_t1_un_solo_objetivo_indexado_por_clave_reabre_el_predicado() -> None:
    nodo = _primera_escritura("def f(a, b, k, v):\n    a[0:1] = b[k] = v\n")
    assert causa_de_escritura(nodo) == SIN_CAUSA


def test_t2_fichero_que_no_parsea() -> None:
    assert causa_por_localidad("def f(:\n") == NO_PARSEA
    assert causa_por_localidad(b"x = 1\x00\n") == NO_PARSEA


def test_t2_fichero_que_parsea_no_es_causa() -> None:
    assert causa_por_localidad("x = 1\n") == SIN_CAUSA


def test_nodo_de_escritura_ambiguo_se_abstiene() -> None:
    """Dos escrituras indexadas en la misma linea: la coordenada no identifica."""
    fuente = "def f(a, b, v):\n    a[1:2] = v; b[v] = 1\n"
    assert nodo_de_escritura(_arbol(fuente), 2) is None


def test_adjudicar_solo_emite_causas_de_la_lista_cerrada() -> None:
    nodo = _primera_escritura(CASO_FRONTERA, 3)
    for salida in (
        adjudicar(nodo),
        adjudicar(nodo, CASO_FRONTERA),
        adjudicar(None, "no parsea ("),
        adjudicar(None, None),
    ):
        assert salida == SIN_CAUSA or salida in CAUSAS_DECIDIBLES


def test_adjudicar_prefiere_el_teorema_de_la_escritura_a_la_localidad() -> None:
    """Si la escritura se localiza, el fichero que parsea no cambia la respuesta."""
    fuente = "def f(a, v):\n    a[1:] = v\n"
    nodo = _primera_escritura(fuente, 2)
    assert adjudicar(nodo, fuente) == POSICIONAL


@pytest.mark.parametrize("indice", ["a[:]", "a[1:]", "a[: -1]", "a[x:]"])
def test_t1_la_rebanada_pura_se_decide(indice: str) -> None:
    nodo = _primera_escritura(f"def f(a, v, x):\n    {indice} = v\n")
    assert causa_de_escritura(nodo) == POSICIONAL
