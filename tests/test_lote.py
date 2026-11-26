"""El lector de un lote no puede tener su propia idea de que es una fila.

`bench/lote.py` nombra un lote (descarga, verifica sha256, escanea) y
`bench/replay_censo.py` lo re-mide. Si cada uno definiera la forma de la fila,
un campo medido por uno y comparado por el otro podria faltar sin que nada
fallara: el replay leeria `None` y lo trataria como un cero. Estos tests fijan
que hay una sola definicion y que el selector de wheel no mide el sujeto
equivocado.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "bench"))

import lote  # noqa: E402
import replay_censo  # noqa: E402


def _meta(*nombres):
    return {"urls": [{"filename": n, "url": f"https://example.invalid/{n}"} for n in nombres]}


def test_solo_se_acepta_un_wheel_puro():
    # Un wheel de plataforma trae un nucleo compilado: escanearlo mediria el
    # envoltorio de Python de una extension en C, que es otro sujeto.
    assert lote._wheel_puro(_meta("pkg-1.0-cp312-cp312-macosx_11_0_arm64.whl")) is None
    assert lote._wheel_puro(_meta("pkg-1.0.tar.gz")) is None
    assert lote._wheel_puro({"urls": []}) is None


def test_el_wheel_puro_se_elige_aunque_no_sea_el_primero():
    entradas = _meta("pkg-1.0-cp312-cp312-win_amd64.whl", "pkg-1.0-py3-none-any.whl")
    elegido = lote._wheel_puro(entradas)
    assert elegido is not None
    assert elegido["filename"] == "pkg-1.0-py3-none-any.whl"
    # py2.py3 tambien es puro y es el que publican los proyectos viejos.
    elegido = lote._wheel_puro(_meta("pkg-1.0-py2.py3-none-any.whl"))
    assert elegido["filename"].endswith("-py2.py3-none-any.whl")


def test_el_subarbol_distingue_paquete_de_modulo(tmp_path):
    (tmp_path / "paquete_x").mkdir()
    (tmp_path / "paquete_x" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "modulo_y.py").write_text("X = 1\n", encoding="utf-8")

    assert lote._subarbol(tmp_path, "paquete-x") == tmp_path / "paquete_x"
    assert lote._subarbol(tmp_path, "modulo_y") == tmp_path / "modulo_y.py"


def test_el_subarbol_no_devuelve_metadatos(tmp_path):
    # La caida a "lo que haya" no puede elegir el .dist-info: escanear la
    # metadata de un paquete da cero almacenes y certificaria un vacio falso.
    (tmp_path / "otro-1.0.dist-info").mkdir()
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "m.py").write_text("X = 1\n", encoding="utf-8")
    assert lote._subarbol(tmp_path, "nombre-que-no-casa") == tmp_path / "real"


def test_la_fila_del_lote_y_la_del_replay_son_la_misma_funcion():
    assert lote._medir is replay_censo._medir
    assert lote.NO_MEDIDO == replay_censo.NO_MEDIDO
    assert lote.RUPTURA == replay_censo.RUPTURA


def test_la_medicion_expone_las_fibras_y_la_especie(tmp_path):
    src = tmp_path / "solo.py"
    src.write_text("def f(filas, acumulador):\n"
                   "    for fila in filas:\n"
                   "        if fila:\n"
                   "            acumulador.append(len(fila))\n"
                   "    return acumulador\n", encoding="utf-8")
    medido = replay_censo._medir(src)
    assert isinstance(medido["claves"], list) and len(medido["claves"]) == medido["candidates"]
    assert sum(medido["species"].values()) == medido["candidates"]
    assert medido["loops"] >= 1, "el unico bucle del fichero tiene que contarse"
    for k in replay_censo.CAMPOS:
        assert k in medido, k
