"""The five write classes, asserted against the control fixtures.

Every assertion names a fixture that exists only to be classified one way, so a
regression in the classifier shows up as a class change here rather than as a
different number in a report nobody diffs.
"""
from __future__ import annotations

from fiber_ast_lint.detect import analizar


def test_proyeccion_con_perdida_es_candidato(copia):
    a = analizar(copia("espacio_no_transversal.py"))
    cands = a.candidatos
    assert len(cands) == 1
    loc = cands[0]
    assert loc.linea == 31
    assert loc.op == "pierde"
    assert loc.familia == "ESPACIO+NORMALIZA"
    assert loc.forma == "PROYECCION_ARRIBA_CON_PERDIDA"
    assert loc.fn == "construir_reporteros"
    assert loc.escapa is True
    assert loc.llamadas >= 1
    assert loc.severidad == "CANDIDATO"


def test_agregacion_monoidal_no_es_perdida(copia):
    a = analizar(copia("monoidal_conserva.py"))
    assert a.candidatos == []
    assert [x.op for x in a.loci] == ["acumulacion"]
    assert a.acumulacion == 1
    assert a.pierde == 0


def test_pertenencia_previa_es_cubeta_contada(copia):
    a = analizar(copia("guardada_conserva.py"))
    assert a.candidatos == []
    assert a.guardadas == 1
    assert a.sin_len == 0


def test_escritura_posicional_no_cambia_cardinalidad(copia):
    a = analizar(copia("posicional_conserva.py"))
    assert a.candidatos == []
    assert a.posicional == 1
    assert a.pierde == 0


def test_columna_de_la_fila_es_proyeccion_no_identidad(copia):
    """``acc[fila.codigo]`` is a column of the row, not the row.

    The family had to change: ``familia_de`` only sums operators applied to the
    key, so an attribute answers ``IDENTIDAD`` and the projection disappears
    from the report while the loss stays real.
    """
    a = analizar(copia("columna_no_transversal.py"))
    loc = a.loci[0]
    assert loc.forma == "SELECCION_COLUMNA_BUCLE"
    assert loc.familia == "COLUMNA"
    assert loc.op == "pierde"
    assert a.candidatos == [loc]
    assert loc.escapa is True
    assert loc.severidad == "CANDIDATO"


def test_columna_con_guarda_no_es_perdida(copia):
    """A uniqueness check on the same column turns the loss into a bucket."""
    a = analizar(copia("columna_guardada.py"))
    assert a.candidatos == []
    assert a.guardadas == 1
    assert a.pierde == 0


def test_atributo_que_no_es_la_fila_no_finge_columna(copia):
    """``out[cfg.clave]`` is a constant key, not a column: the root is a parameter."""
    a = analizar(copia("seleccion_invariante.py"))
    loc = a.loci[0]
    assert loc.forma == "SELECCION"
    assert loc.familia != "COLUMNA"
    assert a.candidatos == []


def test_sin_acumulador_no_hay_loci(copia):
    a = analizar(copia("limpio.py"))
    assert a.archivos == 1
    assert a.loci == []
    assert a.almacenes == 0
    assert a.reconcilia()


def test_ningun_almacen_se_cuenta_dos_veces(copia):
    """Anchors the double-count regression: each loop and each store, once.

    A walk that descends into a function body from the module scope reports the
    same store twice (once as ``fn=<nombre>``, once as ``fn=<modulo>``) and the
    census still adds up, so only the absolute totals catch it.
    """
    for nombre in ("espacio_no_transversal.py", "grafo_consumidores.py",
                   "monoidal_conserva.py", "guardada_conserva.py",
                   "posicional_conserva.py", "limpio.py",
                   "columna_no_transversal.py", "columna_guardada.py",
                   "seleccion_invariante.py"):
        a = analizar(copia(nombre))
        assert a.for_medidos == len(_lineas_de_for(nombre)), nombre
        assert len(a.loci) <= a.almacenes, nombre


def _lineas_de_for(nombre: str) -> set[int]:
    import ast
    from pathlib import Path
    ruta = Path(__file__).parent / "fixtures" / nombre
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    return {n.lineno for n in ast.walk(arbol) if isinstance(n, (ast.For, ast.AsyncFor))}


def test_reconcilia_sobre_un_universo_conocido():
    """Nine loops and nine stores over the whole battery, buckets disjoint."""
    from conftest import FIXTURES
    a = analizar(FIXTURES)
    assert a.fallas == 0
    assert a.for_medidos == 9
    assert a.almacenes == 9
    assert a.almacenes == (a.pierde + a.guardadas + a.acumulacion
                           + a.posicional + a.sin_len)
    assert a.reconcilia()
    assert (a.pierde, a.guardadas, a.acumulacion, a.posicional) == (0, 2, 1, 1)


def test_universo_vacio_no_es_cero(tmp_path):
    a = analizar(tmp_path)
    assert a.archivos == 0
    assert a.loci == []


def test_la_identidad_sobre_cero_almacenes_no_certifica(copia):
    """0 = 0 cierra por no haber poblacion: cierra, y no certifica nada.

    ``reconcilia`` es aritmetica; ``certifica`` es la firma que un recibo
    publica. Un universo medido sin un solo almacen sostiene la primera y no la
    segunda, y confundirlas es lo que dejo a dos filas del censo firmando una
    conservacion sobre cero unidades.
    """
    a = analizar(copia("limpio.py"))
    assert a.almacenes == 0
    assert a.reconcilia() is True
    assert a.certifica() is False
