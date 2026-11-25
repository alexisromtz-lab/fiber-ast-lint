"""The exit code is the contract: 0 clean, 1 candidates, 2 empty, 4 broken.

A tool that reports an empty universe or an unreconciled census as success is
worse than no tool, so each of those paths is asserted here.
"""
from __future__ import annotations

import json

from fiber_ast_lint.cli import main

FIXTURES = "tests/fixtures"


def test_json_salida_completa(copia, capsys):
    raiz = str(copia("espacio_no_transversal.py"))
    rc = main([raiz, "--json"])
    salida = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert salida["reconcilia"] is True
    assert salida["archivos"] == 1
    assert [c["funcion"] for c in salida["candidatos"]] == ["construir_reporteros"]
    assert salida["consumidores"]["construir_reporteros"]


def test_sin_candidatos_sale_cero(copia):
    rc = main([str(copia("limpio.py")), "-q"])
    assert rc == 0


def test_universo_vacio_no_sale_cero(tmp_path):
    assert main([str(tmp_path), "-q"]) == 2


def test_error_de_sintaxis_no_degrada_a_cero(tmp_path):
    (tmp_path / "roto.py").write_text("def f(:\n", encoding="utf-8")
    assert main([str(tmp_path), "-q"]) == 4


def test_fixtures_como_universo(capsys):
    rc = main([FIXTURES, "--json", "--sin-interproc"])
    salida = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert salida["for_medidos"] == 6
    assert salida["almacenes"] == 6
    assert salida["consumidores"] == {}
    assert len(salida["candidatos"]) == 3
