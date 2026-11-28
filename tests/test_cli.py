"""The exit code is the contract: 0 clean, 1 candidates, 2 empty, 4 broken.

A tool that reports an empty universe or an unreconciled census as success is
worse than no tool, so each of those paths is asserted here.
"""
from __future__ import annotations

import json
import sys

from fiber_ast_lint.adjudicador_ast import POSICIONAL, SIN_CAUSA
from fiber_ast_lint.causa import ADJUDICADOR, INTERPRETE
from fiber_ast_lint.cli import construir, main

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


def test_el_escaneo_y_la_certificacion_publican_codigos_distintos(copia, capsys):
    """Un linter callado sobre un fichero sin bucles sigue siendo un 0.

    El acta, en cambio, no puede firmar ``certifica`` sobre cero almacenes: el
    payload publica los dos codigos con nombre para que el recibo no tenga que
    adivinar cual esta leyendo.
    """
    main([str(copia("limpio.py")), "--json"])
    salida = json.loads(capsys.readouterr().out)
    assert salida["rc"] == 0
    assert salida["certifica"] is False
    assert salida["rc_certificado"] == 2


def test_con_almacenes_los_dos_codigos_son_el_mismo(copia, capsys):
    main([str(copia("espacio_no_transversal.py")), "--json"])
    salida = json.loads(capsys.readouterr().out)
    assert salida["almacenes"] > 0
    assert salida["certifica"] is True
    assert salida["rc_certificado"] == salida["rc"] == 1


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


def test_el_payload_publica_de_donde_salio_cada_identidad(capsys):
    """A reader must be able to tell the two resolution rules apart."""
    rc = main([FIXTURES, "--json"])
    salida = json.loads(capsys.readouterr().out)
    assert rc == 1
    for clave in ("consumidores_por_self", "llamadas_self_ajenas", "consumidores_por_nombre"):
        assert isinstance(salida[clave], int), clave
    assert salida["consumidores_por_self"] >= 0
    assert salida["llamadas_self_ajenas"] >= 0


def test_el_payload_nombra_el_binario_que_lo_escribio(capsys):
    """Un recibo sin autor no se puede fechar: se confunde con uno editado."""
    import fiber_ast_lint

    rc = main([FIXTURES, "--json"])
    salida = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert salida["instrument"] == "fiber-ast-lint"
    assert salida["instrument_version"] == fiber_ast_lint.__version__

# --------------------------------------------------------------------------- #
# The cause column: the adjudicator's verdict, published next to the row.
# --------------------------------------------------------------------------- #
REBANADA = '''\
def tapar(largos):
    mascara = crear_tensor(len(largos), 8)
    for i, n in enumerate(largos):
        mascara[i, :n] = 1
    return mascara


def resumen(largos):
    return tapar(largos)
'''

CLAVE = '''\
def por_codigo(entries):
    indice = {}
    for entry in entries:
        indice[entry.code] = entry
    return indice


def resumen(entries):
    return por_codigo(entries)
'''


def _construir(tmp_path, nombre, fuente):
    (tmp_path / f"{nombre}.py").write_text(fuente, encoding="utf-8")
    return construir(str(tmp_path))


def test_la_fila_lleva_la_causa_que_el_arbol_decide(tmp_path):
    """``mascara[i, :n]`` direcciona posiciones: ese indice no puede ser clave."""
    d = _construir(tmp_path, "rebanada", REBANADA)
    (c,) = d["candidatos"]
    assert c["causa"] == POSICIONAL
    assert d["causas"][(c["archivo"], c["linea"])] == POSICIONAL


def test_un_candidato_que_el_arbol_no_decide_no_es_un_cero(tmp_path):
    """Una clave calculada no se decide: se publica ``NO_MEDIDO``, no una causa."""
    d = _construir(tmp_path, "clave", CLAVE)
    (c,) = d["candidatos"]
    assert c["causa"] == SIN_CAUSA


def test_el_payload_nombra_el_adjudicador_y_el_interprete(tmp_path, capsys):
    """T2 mide el piso del parser: sin el interprete, ``fichero_no_parsea`` no tiene sujeto."""
    _construir(tmp_path, "rebanada", REBANADA)
    assert main([str(tmp_path), "--json"]) == 1
    salida = json.loads(capsys.readouterr().out)
    assert salida["adjudicador"] == ADJUDICADOR
    assert salida["interprete"] == INTERPRETE == sys.version.split()[0]


def test_la_causa_no_mueve_el_contrato_de_codigos(tmp_path):
    """Es una columna, no un veredicto: el censo y el codigo de salida no se mueven."""
    d = _construir(tmp_path, "clave", CLAVE)
    assert d["reconcilia"] is True
    assert (d["archivos"], d["almacenes"], len(d["candidatos"])) == (1, 1, 1)
