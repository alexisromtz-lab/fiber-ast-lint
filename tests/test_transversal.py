"""The whitelist theorem, exercised on the six-key space of the mypy fixture.

A guard of the form ``if pi(k) in ALLOWED`` constrains the codomain; it can only
suppress a collision when the *inputs* it lets through form a transversal of the
partition induced by ``pi``. The fixture is the shape measured in
``mypy/config_parser.py`` (six ini keys, four reporter names, two collisions).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from fiber_ast_lint.transversal import (
    es_transversal,
    fibra,
    verificar_conservacion,
    verificar_transversal,
)

FIXTURE = Path(__file__).parent / "fixtures" / "espacio_no_transversal.py"


def _fixture():
    spec = importlib.util.spec_from_file_location("_espacio", FIXTURE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seis_entradas_cuatro_imagenes():
    m = _fixture()
    f = fibra(m.INIFILE_KEYS, m.nombre_de_reporter)
    assert f.preimagenes == 6
    assert len(f.imagen) == 4
    assert f.nucleo == 2
    assert f.conserva()
    testigos = dict(f.testigos())
    assert testigos["any-exprs"] == ["any-exprs", "any_exprs"]
    assert testigos["xslt-html"] == ["xslt-html", "xslt_html"]


def test_lista_blanca_de_codominio_no_es_transversal():
    """Every key passes the guard and the kernel is untouched."""
    m = _fixture()
    pasantes = [k for k in m.INIFILE_KEYS if m.nombre_de_reporter(k) in m.REPORTER_NAMES]
    assert len(pasantes) == 6
    assert es_transversal(pasantes, m.nombre_de_reporter) is False
    r = verificar_transversal(pasantes, m.nombre_de_reporter)
    assert r["transversal"] is False
    assert r["nucleo"] == 2
    assert r["imagenes"] == 4


def test_transversal_exacta_no_pierde():
    m = _fixture()
    permitidos = ["any-exprs", "xslt-html", "line-count", "misc"]
    r = verificar_transversal(permitidos, m.nombre_de_reporter)
    assert r["transversal"] is True
    assert r["nucleo"] == 0
    assert r["permitidos"] == r["imagenes"] == 4


def test_conservacion_exige_positividad():
    """A bucket defined by subtraction closes in Z even when counts disagree."""
    roto = verificar_conservacion(dominio=67, imagen=68, rechazos=0, colisiones=-1)
    assert roto["suma"] == 67
    assert roto["descuadre"] == 0
    assert roto["conserva"] is False
    assert roto["cubetas_negativas"] == {"colisiones": -1}


def test_conservacion_cuadra():
    ok = verificar_conservacion(dominio=6, imagen=4, rechazos=0, colisiones=2)
    assert ok["conserva"] is True
    assert ok["descuadre"] == 0
    assert ok["cubetas_negativas"] == {}


def test_conservacion_reporta_el_descuadre():
    falta = verificar_conservacion(dominio=10, imagen=4, rechazos=0, colisiones=2)
    assert falta["conserva"] is False
    assert falta["descuadre"] == 4
