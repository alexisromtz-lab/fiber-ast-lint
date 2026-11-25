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
    assert salida["consumidores"]["espacio_no_transversal::construir_reporteros"]


def test_sin_candidatos_sale_cero(copia):
    rc = main([str(copia("limpio.py")), "-q"])
    assert rc == 0


def test_un_fichero_es_un_universo(copia, capsys):
    """A linter is called with a single file from an editor or a pre-commit hook."""
    fichero = copia("espacio_no_transversal.py") / "espacio_no_transversal.py"
    assert main([str(fichero), "--json"]) == 1
    salida = json.loads(capsys.readouterr().out)
    assert salida["archivos"] == 1
    assert [c["funcion"] for c in salida["candidatos"]] == ["construir_reporteros"]
    assert salida["consumidores"]["espacio_no_transversal::construir_reporteros"]


def test_fichero_ajeno_no_finge_universo(tmp_path):
    otro = tmp_path / "notas.txt"
    otro.write_text("hola", encoding="utf-8")
    assert main([str(otro), "-q"]) == 2


def test_universo_vacio_no_sale_cero(tmp_path):
    assert main([str(tmp_path), "-q"]) == 2


def test_error_de_sintaxis_no_degrada_a_cero(tmp_path):
    (tmp_path / "roto.py").write_text("def f(:\n", encoding="utf-8")
    assert main([str(tmp_path), "-q"]) == 4


def test_fixtures_como_universo(capsys):
    rc = main([FIXTURES, "--json", "--sin-interproc"])
    salida = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert salida["for_medidos"] == 9
    assert salida["almacenes"] == 9
    assert salida["consumidores"] == {}
    assert salida["llamadas_sin_identidad"] == 0
    assert len(salida["candidatos"]) == 4


def test_varios_universos_gana_el_supremo(tmp_path, copia):
    """An empty path must not hide a candidate found in another path."""
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    assert main([str(vacio), str(copia("espacio_no_transversal.py")), "-q"]) == 1


def test_varios_universos_ruptura_manda(tmp_path, copia):
    roto = tmp_path / "roto"
    roto.mkdir()
    (roto / "x.py").write_text("def f(:\n", encoding="utf-8")
    assert main([str(copia("limpio.py")), str(roto), "-q"]) == 4


def test_universo_vacio_solo_sigue_siendo_dos(tmp_path):
    assert main([str(tmp_path), str(tmp_path), "-q"]) == 2


def test_json_de_varios_universos_es_lista(copia, capsys):
    rc = main([FIXTURES, str(copia("limpio.py")), "--json", "--sin-interproc"])
    salida = json.loads(capsys.readouterr().out)
    assert isinstance(salida, list) and len(salida) == 2
    assert [d["rc"] for d in salida] == [1, 0]
    assert rc == 1
