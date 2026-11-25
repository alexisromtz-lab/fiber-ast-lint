"""The second pass: does anyone measure the cardinal one hop away?

The local pass says ``SIN_LEN`` when the ``len`` lives in another scope. That is
an honest "not measured here", not a zero; this pass closes the hop through the
call site and declares what it cannot see.
"""
from __future__ import annotations

from pathlib import Path

from fiber_ast_lint.graph import consumidores

FIXTURES = Path(__file__).parent / "fixtures"


def test_las_tres_formas_de_consumo(copia):
    raiz = copia("grafo_consumidores.py")
    out = consumidores(raiz, {"construir", "llenar"})
    assert set(out) == {"construir", "llenar"}
    assert {c.forma for c in out["construir"]} == {"VINCULO", "DIRECTO"}
    assert {c.forma for c in out["llenar"]} == {"PARAMETRO"}
    directo = [c for c in out["construir"] if c.forma == "DIRECTO"][0]
    assert directo.linea_llamada == directo.linea_consumo == 20


def test_un_len_anterior_a_la_llamada_no_es_consumidor(tmp_path):
    (tmp_path / "mod.py").write_text(
        "def productor(items):\n"
        "    acc = {}\n"
        "    for k in items:\n"
        "        acc[k.lower()] = k\n"
        "    return acc\n"
        "\n"
        "def antes(items):\n"
        "    n = len(items)\n"
        "    tabla = productor(items)\n"
        "    return tabla, n\n",
        encoding="utf-8",
    )
    out = consumidores(tmp_path, {"productor"})
    assert out["productor"] == []


def test_llamada_sin_consumo_no_inventa_consumidor(copia):
    raiz = copia("grafo_consumidores.py")
    out = consumidores(raiz, {"consumidor_ausente"})
    assert out == {"consumidor_ausente": []}


def test_sin_productores_no_recorre_nada(copia):
    raiz = copia("grafo_consumidores.py")
    assert consumidores(raiz, set()) == {}


def test_ignora_directorios_de_terceros(tmp_path):
    interno = tmp_path / "__pycache__"
    interno.mkdir()
    (interno / "basura.py").write_text(
        "def productor(x):\n    return x\n\nprint(len(productor(1)))\n",
        encoding="utf-8",
    )
    assert consumidores(tmp_path, {"productor"}) == {"productor": []}


def test_el_consumidor_nombra_archivo_y_lineas(copia):
    raiz = copia("grafo_consumidores.py")
    c = consumidores(raiz, {"llenar"})["llenar"][0]
    assert c.archivo == "grafo_consumidores.py"
    assert (c.linea_llamada, c.linea_consumo) == (25, 26)
    assert "PARAMETRO" in str(c)


def test_ficheros_de_los_fixtures_cuentan_igual():
    """The fixture directory itself is a universe: three producers, four sites."""
    out = consumidores(FIXTURES, {"construir", "llenar"})
    sitios = [c for lista in out.values() for c in lista]
    assert len(sitios) == 3
