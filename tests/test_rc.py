"""Combining run codes: the supremum of ``4 > 1 > 2 > 0``, never ``max``.

``max(1, 2) == 2``, so a partition that measured nothing would report the run as
"not measured" and let a proven defect leave as a legitimate-looking code.
"""
from __future__ import annotations

import itertools

import pytest

from fiber_ast_lint.rc import combinar_rc, normalizar, precedencia

CODIGOS = (0, 1, 2, 4)


def test_el_par_que_discrepa_de_max():
    assert combinar_rc(1, 2) == 1
    assert combinar_rc(2, 1) == 1
    assert combinar_rc(2, 0) == 2
    assert combinar_rc(4, 1) == 4


def test_conmutativa():
    for a, b in itertools.product(CODIGOS, repeat=2):
        assert combinar_rc(a, b) == combinar_rc(b, a)


def test_asociativa():
    for a, b, c in itertools.product(CODIGOS, repeat=3):
        assert combinar_rc(combinar_rc(a, b), c) == combinar_rc(a, combinar_rc(b, c))


def test_neutro_es_cero():
    for a in CODIGOS:
        assert combinar_rc(a, 0) == a
        assert combinar_rc(0, a) == a
    assert combinar_rc() == 0


def test_idempotente():
    for a in CODIGOS:
        assert combinar_rc(a, a) == a


def test_orden_de_precedencia():
    assert precedencia(4) > precedencia(1) > precedencia(2) > precedencia(0)


@pytest.mark.parametrize("ajeno", [3, 9, -1, 127])
def test_codigo_desconocido_es_ruptura_no_limpieza(ajeno):
    assert normalizar(ajeno) == 4
    assert combinar_rc(ajeno) == 4
    assert combinar_rc(0, ajeno) == 4
