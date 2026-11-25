"""The kill matrix: does the classifier fire when a defect is planted?

`H_out_of_sample` measures *precision* on three populations nobody had read, and
it does it on three candidates -- which is far too few to say anything about
whether a real defect of a given class is caught. This file measures the other
direction on truth I construct, which is weaker than the wild and stronger than
nothing: one instance of each losing form, planted inside a real module, and one
instance of each guarded form planted beside it.

The discriminating triplet is the point. `plantado`, `guardado` and `acumulado`
below share one key expression -- ``entry.code`` -- and differ only in what the
body does with it. A classifier that reacted to the *shape* of the key would
return the same verdict three times; the matrix proves it reacts to whether a
lost row can reach a consumer.

Measured on the pinned `flake8` 7.5.0 tree before being written down here: the
five plants took `stores` from 3 to 8, produced `guardadas=1` and
`acumulacion=1`, and left the pre-existing row at `finder.py:327` untouched.
"""
from __future__ import annotations

from pathlib import Path

from fiber_ast_lint.cli import construir

PLANTADO = '''\
def por_codigo(entries):
    indice = {}
    for entry in entries:
        indice[entry.code] = entry
    return indice


def resumen(entries):
    return por_codigo(entries)
'''

GUARDADO = '''\
def por_codigo(entries):
    indice = {}
    for entry in entries:
        if entry.code not in indice:
            indice[entry.code] = entry
    return indice


def resumen(entries):
    return por_codigo(entries)
'''

ACUMULADO = '''\
def por_codigo(entries):
    cuenta = {}
    for entry in entries:
        cuenta[entry.code] = cuenta.get(entry.code, 0) + 1
    return cuenta


def resumen(entries):
    return por_codigo(entries)
'''

ARRIBA = '''\
def por_linea_limpia(lineas):
    indice = {}
    for linea in lineas:
        clave = linea.strip()
        indice[clave] = linea
    return indice


def resumen(lineas):
    return por_linea_limpia(lineas)
'''

VISIBLE = '''\
def por_linea_minuscula(lineas):
    indice = {}
    for linea in lineas:
        indice[linea.lower()] = linea
    return indice


def resumen(lineas):
    return por_linea_minuscula(lineas)
'''


def _analizar(tmp_path: Path, nombre: str, fuente: str) -> dict:
    ruta = tmp_path / f"{nombre}.py"
    ruta.write_text(fuente, encoding="utf-8")
    return construir(str(ruta))


def test_cada_forma_que_pierde_dispara_cuando_se_planta(tmp_path):
    esperado = {
        "plantado": "SELECCION_COLUMNA_BUCLE",
        "arriba": "PROYECCION_ARRIBA_CON_PERDIDA",
        "visible": "PROYECCION_VISIBLE",
    }
    fuentes = {"plantado": PLANTADO, "arriba": ARRIBA, "visible": VISIBLE}
    for nombre, forma in esperado.items():
        d = _analizar(tmp_path, nombre, fuentes[nombre])
        assert d["reconcilia"] is True, nombre
        assert len(d["candidatos"]) == 1, nombre
        c = d["candidatos"][0]
        assert c["forma"] == forma, (nombre, c["forma"])
        assert c["severidad"] == "CANDIDATO", nombre
        assert c["escapa"] is True and c["llamadas"] == 1, nombre


def test_las_dos_guardas_callan_y_no_son_un_cero_ausente(tmp_path):
    for nombre, fuente, cubo in (("guardado", GUARDADO, "guardadas"),
                                 ("acumulado", ACUMULADO, "acumulacion")):
        d = _analizar(tmp_path, nombre, fuente)
        assert d["almacenes"] == 1, nombre
        assert d[cubo] == 1, (nombre, cubo)
        assert d["candidatos"] == [], nombre
        assert d["reconcilia"] is True, nombre


def test_la_misma_clave_da_tres_veredictos(tmp_path):
    """`entry.code` tres veces: perder, guardar, acumular."""
    perder = _analizar(tmp_path, "t_perder", PLANTADO)
    guardar = _analizar(tmp_path, "t_guardar", GUARDADO)
    acumular = _analizar(tmp_path, "t_acumular", ACUMULADO)

    claves = {d["candidatos"][0]["clave"] if d["candidatos"] else None
              for d in (perder, guardar, acumular)}
    assert claves == {"entry.code", None}

    assert (perder["almacenes"], guardar["almacenes"], acumular["almacenes"]) == (1, 1, 1)
    assert perder["acumulacion"] + perder["guardadas"] == 0
    assert guardar["guardadas"] == 1
    assert acumular["acumulacion"] == 1
    assert all(d["reconcilia"] is True for d in (perder, guardar, acumular))
