"""v1.1 decides the bound and keeps refusing the key.

The tests below are the rule, not the implementation: a bound is a
location, a key is a value, and only the second one can fuse two rows. The last
two hold the artifact's own terms -- v1.0 stays frozen, and no value outside the
closed set can leave the instrument.
"""
import ast
import hashlib
import re
import sys
from pathlib import Path

from fiber_ast_lint import adjudicador_ast, adjudicador_ast_11
from fiber_ast_lint.adjudicador_ast_11 import (
    CAUSAS_DECIDIBLES,
    INTERPRETE,
    NO_PARSEA,
    POSICIONAL,
    SIN_CAUSA,
    adjudicar,
    componentes,
    direccion_posicional,
    nodo_de_escritura,
)

RAIZ = Path(__file__).resolve().parents[1]
V10 = RAIZ / "src/fiber_ast_lint/adjudicador_ast.py"
V10_SHA256 = "02ab4e4d6750bd8ab0779b74ceebff542ad9523f1e55c3fbddfd6886a6180b16"


def _causa(fuente: str) -> str:
    """The cause v1.1 decides for the keyed write on line 1 of ``fuente``."""
    return adjudicar(nodo_de_escritura(ast.parse(fuente), 1), fuente)


def _causa_v10(fuente: str) -> str:
    return adjudicador_ast.adjudicar(adjudicador_ast.nodo_de_escritura(ast.parse(fuente), 1), fuente)


def test_el_borde_que_motivo_la_regla_se_decide():
    """The real locus of batch 24's undecided edge, verbatim."""
    assert _causa("wavs[i, : len(row)] = row\n") == POSICIONAL


def test_una_llamada_en_la_direccion_sigue_absteniendose():
    assert _causa("acc[fila(x), :] = v\n") == SIN_CAUSA
    assert _causa("acc[clave(x)] = v\n") == SIN_CAUSA
    # A call in one component is enough to reopen the predicate for the target.
    assert _causa("acc[:, clave(x)] = v\n") == SIN_CAUSA


def test_una_cota_con_llamada_junto_a_una_clave_simple_se_decide():
    assert _causa("acc[x, : len(y)] = v\n") == POSICIONAL
    assert _causa("acc[0, k(x):] = v\n") == POSICIONAL


def test_la_condicional_en_la_cota_es_una_cota():
    """Both branches select positions; neither computes an address."""
    assert _causa("acc[: (n if c else m)] = v\n") == POSICIONAL
    assert _causa("acc[(n if c else m)] = v\n") == SIN_CAUSA


def test_sin_rebanada_no_hay_direccion():
    # v1.0 and v1.1 agree here: a bare tuple of names is a key, not an address.
    assert _causa("acc[i, j] = v\n") == SIN_CAUSA
    indice = ast.parse("acc[i, j]").body[0].value.slice
    assert len(componentes(indice)) == 2
    assert direccion_posicional(indice) is False


def test_v10_se_abstiene_en_el_borde_y_eso_es_la_diferencia():
    """Not a rename: the two artifacts disagree on exactly this shape."""
    fuente = "wavs[i, : len(row)] = row\n"
    assert _causa_v10(fuente) == SIN_CAUSA
    assert _causa(fuente) == POSICIONAL


def test_las_que_v10_decidia_siguen_decididas_igual():
    """The refinement may only add. Any row v1.0 decided, v1.1 decides alike."""
    casos = [
        "acc[a:b] = v\n",
        "acc[i, :] = v\n",
        "acc[0, :] = v\n",
        "acc[:, i] = v\n",
        "acc[:] = v\n",
        "acc[a:b:c] = v\n",
        "acc[i][:] = v\n",
    ]
    for fuente in casos:
        assert _causa_v10(fuente) == _causa(fuente) == POSICIONAL, fuente


def test_el_digesto_del_artefacto_anterior_no_se_movio():
    assert hashlib.sha256(V10.read_bytes()).hexdigest() == V10_SHA256


def test_ningun_valor_fuera_del_conjunto_cerrado():
    fuentes = [
        "acc[a:b] = v\n", "acc[f(x)] = v\n", "acc[i, : len(r)] = v\n",
        "acc[:, clave(x)] = v\n", "acc[i, j] = v\n", "acc[...] = v\n",
        "acc[(1, 2)] = v\n", "acc[:] += 1\n", "for k in y:\n    acc[k] = v\n",
    ]
    for fuente in fuentes:
        assert _causa(fuente) in set(CAUSAS_DECIDIBLES) | {SIN_CAUSA}, fuente


def test_t2_declara_el_interprete_que_mide():
    """A ``fichero_no_parsea`` is a statement about a parser, so it names one."""
    assert re.fullmatch(r"\d+\.\d+\.\d+\S*", INTERPRETE), INTERPRETE
    assert INTERPRETE == sys.version.split()[0]
    # The verdict is a statement about THIS parser and moves with it: the pin is
    # what makes the receipt's denominator auditable on any interpreter.
    fuente = "type X = int\n"
    try:
        ast.parse(fuente)
        parsea = True
    except SyntaxError:
        parsea = False
    assert adjudicar(None, fuente) == (SIN_CAUSA if parsea else NO_PARSEA)
