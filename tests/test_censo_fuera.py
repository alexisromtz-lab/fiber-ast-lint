"""A sample that was measured before it was predicted may not become a constant.

`fuera-de-dominio.json` publishes five rows from four domains the census does not
contain. It is *exploratory*: no number in it was written down before the artifact
was fetched, so the file may name directions and may not name rates. These tests
hold it to that, and hold the README to the file.

What they can check offline: every row is pinned, every row's buckets close its
store count, and the containment `candidates <= sin_len` holds across both census
files. What they cannot check is the measurement itself -- that needs the wheels,
and `bench/replay_censo.py --censo fuera-de-dominio.json` is the reader for it.
"""
import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FUERA = json.loads((RAIZ / "fuera-de-dominio.json").read_text(encoding="utf-8"))
CENSO = json.loads((RAIZ / "censo.json").read_text(encoding="utf-8"))
README = (RAIZ / "README.md").read_text(encoding="utf-8")

CUBETAS = ("guardadas", "acumulacion", "posicional", "sin_len", "pierde")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _num(texto: str) -> int:
    return int(texto.replace(" ", "").replace("\u00a0", "").replace("**", ""))


SECCION = "### Four domains the census never touches"


def _tabla(encabezado: str) -> list[list[str]]:
    """The table under our own heading: the census table above shares the same header."""
    lineas = README[README.index(SECCION):].splitlines()
    inicio = next(i for i, l in enumerate(lineas) if l.startswith(encabezado))
    filas = []
    for linea in lineas[inicio + 1:]:
        if not linea.startswith("|"):
            break
        celdas = [c.strip().replace("**", "").replace("`", "")
                  for c in linea.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in celdas):
            continue
        filas.append(celdas)
    return filas


def test_cada_fila_esta_pinneada():
    por_artefacto = {}
    for r in FUERA["rows"]:
        assert r["artifact"].endswith(".whl"), r
        assert r["artifact"].startswith(r["package"] + "-"), r["artifact"]
        assert HEX64.match(r["sha256"]), (r["package"], r["sha256"])
        assert r["bytes"] > 0, r["package"]
        assert r["version"] and r["scope"], r["package"]
        # A pin is only worth what its value is worth, and this suite has no wheel
        # to compare it against. It can still refuse a placeholder and two digests
        # for one artifact; the value itself is checked by `bench/replay_censo.py`.
        assert len(set(r["sha256"])) >= 8, f"{r['package']}: digest de baja entropia"
        previo = por_artefacto.setdefault(r["artifact"], r["sha256"])
        assert previo == r["sha256"], f"{r['artifact']} con dos digests distintos"
    assert len(set(por_artefacto.values())) == len(por_artefacto), "dos artefactos con el mismo digest"


def test_las_cubetas_cierran_el_recuento_de_almacenes():
    for r in FUERA["rows"]:
        suma = sum(r[k] for k in CUBETAS)
        assert suma == r["stores"], f"{r['package']} {r['scope']}: {suma} != {r['stores']}"
        assert r["reconciles"] is True, r["package"]


def test_ningun_candidato_nace_fuera_de_sin_len():
    filas = FUERA["rows"] + CENSO["rows"]
    for r in filas:
        assert r["candidates"] <= r["sin_len"], \
            f"{r['package']} {r['scope']}: {r['candidates']} > {r['sin_len']}"
    assert len(filas) == FUERA["invariant"]["rows_checked"], \
        "el invariante declara un recuento de filas que ya no es el medido"


def test_los_totales_son_la_suma_de_las_filas():
    # Los enteros cuadran exacto. Los segundos no: CPython 3.12 metio suma
    # compensada (Neumaier) en sum(), asi que la misma lista da 2.06 en 3.12 y
    # 2.0599999999999996 en 3.11. El total publicado va redondeado a dos
    # decimales, asi que se compara a la precision a la que se publica.
    for k, v in FUERA["totals"].items():
        suma = sum(r[k] for r in FUERA["rows"])
        if isinstance(v, float):
            assert v == pytest.approx(suma, abs=5e-3), (k, v, suma)
        else:
            assert v == suma, k


def test_la_tabla_del_readme_es_el_archivo():
    filas = _tabla("| package | version | scope | files | stores |")
    publicadas = [f for f in filas if not f[0].startswith("added")]
    assert len(publicadas) == len(FUERA["rows"])
    for celda, r in zip(publicadas, FUERA["rows"]):
        assert celda[0] == r["package"], (celda[0], r["package"])
        assert celda[1] == r["version"], (celda[1], r["version"])
        assert celda[2].rstrip("/") == r["scope"], (celda[2], r["scope"])
        assert _num(celda[3]) == r["files"], r["package"]
        assert _num(celda[4]) == r["stores"], r["package"]
        assert _num(celda[5]) == r["sin_len"], r["package"]
        assert _num(celda[6]) == r["candidates"], r["package"]
        assert _num(celda[7]) == r["admitted"], r["package"]
        assert celda[8].startswith("yes") == r["reconciles"], r["package"]


def test_la_fila_de_totales_del_readme_es_la_suma():
    totales = [f for f in _tabla("| package | version | scope | files | stores |")
               if f[0].startswith("added")]
    assert len(totales) == 1
    t = FUERA["totals"]
    for celda, clave in zip(totales[0][3:8], ("files", "stores", "sin_len", "candidates", "admitted")):
        assert _num(celda) == t[clave], (celda, clave, t[clave])


def test_los_dos_cocientes_publicados_son_los_de_las_dos_poblaciones():
    t, c = FUERA["totals"], FUERA["contrast_censo"]
    esperado = {
        "stores_censo": c["stores"], "stores_fuera": t["stores"],
        "cand_sobre_stores_censo": round(100 * c["candidates"] / c["stores"], 2),
        "cand_sobre_sin_len_censo": round(100 * c["candidates"] / c["sin_len"], 2),
        "cand_sobre_stores_fuera": round(100 * t["candidates"] / t["stores"], 2),
        "cand_sobre_sin_len_fuera": round(100 * t["candidates"] / t["sin_len"], 2),
    }
    assert esperado["stores_censo"] == 308 and esperado["stores_fuera"] == 47
    for valor in (esperado["cand_sobre_stores_censo"], esperado["cand_sobre_sin_len_censo"],
                  esperado["cand_sobre_stores_fuera"], esperado["cand_sobre_sin_len_fuera"]):
        assert f"{valor:.2f} %" in README, f"{valor:.2f} % ausente del README"


def test_los_sitios_no_son_los_grupos():
    s = FUERA["sites_vs_groups"]
    assert s["sites"] == FUERA["totals"]["candidates"]
    assert s["groups"] <= s["sites"]
    assert s["dominant_sites"] == s["sites"] - 3, "las tres de requests son de clave distinta"
    assert len(s["dominant_functions"]) == s["groups"] - 3
    assert f"are **{s['groups']}**, not {s['sites']}" in README


def test_el_estado_exploratorio_no_se_degrada_a_constante():
    assert FUERA["status"]["verdict"] == "EXPLORATORIO"
    assert "exploratory" in README
    assert "no constant" in README
    assert FUERA["sample"]["declared_before_reading_code"] is True


def test_el_replay_del_archivo_esta_declarado():
    assert FUERA["replay"]["command"].endswith("--censo fuera-de-dominio.json")
    assert FUERA["replay"]["line"].startswith("REPLAY IDENTICO")
    assert FUERA["cost"]["seconds_total"] == FUERA["totals"]["segundos_min"]
    assert f"{FUERA['cost']['seconds_total']:.2f} s" in README


# --- lote 2: el mismo esquema, la primera instancia confirmatoria ------------
#
# `fuera-de-dominio.json` se midio antes de predecir y por eso puede nombrar
# direcciones y no tasas. `prediccion-batch-2.json` se commiteo antes de descargar
# nada, y `fuera-de-dominio-2.json` es la medida que llega despues. Los tests de
# este bloque comprueban dos cosas distintas: que el pin de la prediccion es el
# archivo que viaja en el arbol, y que los cuatro veredictos se recalculan desde
# las filas en vez de leerse de la prosa.

SEGUNDO = json.loads((RAIZ / "fuera-de-dominio-2.json").read_text(encoding="utf-8"))
PREDICCION = (RAIZ / "prediccion-batch-2.json")


def _sha(fichero):
    import hashlib
    return hashlib.sha256(fichero.read_bytes()).hexdigest()


def test_el_pin_de_la_prediccion_es_el_archivo_que_viaja():
    # El commit prueba el orden y no se puede probar offline; el digest prueba que
    # el archivo anclado es este y no una version posterior, que si se prueba.
    assert SEGUNDO["prediction"]["sha256"] == _sha(PREDICCION)
    assert SEGUNDO["prediction"]["sha256"] != "0" * 64
    assert len(SEGUNDO["prediction"]["sha256"]) == 64
    declarado = json.loads(PREDICCION.read_text(encoding="utf-8"))
    assert declarado["declared_before_fetch"] is True
    assert list(declarado["population"]["packages"]) == [r["package"] for r in SEGUNDO["rows"]], \
        "el lote medido no es el lote nombrado en la prediccion"


def test_el_segundo_archivo_es_el_mismo_esquema():
    for clave in ("schema", "instrument", "instrument_version", "measured_at",
                  "interpreter", "method", "reproduce", "sample", "status", "rows",
                  "totals", "replay"):
        assert clave in SEGUNDO, clave
        assert clave in FUERA, clave
    assert SEGUNDO["schema"] == FUERA["schema"]
    assert set(SEGUNDO["rows"][0]) == set(FUERA["rows"][0]), "una fila, dos formas"
    assert SEGUNDO["replay"]["line"].startswith("REPLAY IDENTICO")


def test_las_filas_del_lote_2_estan_pinneadas_y_cuadran():
    for r in SEGUNDO["rows"]:
        assert len(r["sha256"]) == 64 and len(set(r["sha256"])) > 8, r["package"]
        assert r["guardadas"] + r["pierde"] + r["acumulacion"] + r["posicional"] \
            + r["sin_len"] == r["stores"], r["package"]
        assert r["candidates"] <= r["sin_len"], r["package"]
        assert r["reconciles"] is True, r["package"]
    assert len({r["sha256"] for r in SEGUNDO["rows"]}) == len(SEGUNDO["rows"])


def test_los_totales_del_lote_2_son_la_suma_de_sus_filas():
    for k, v in SEGUNDO["totals"].items():
        suma = sum(r[k] for r in SEGUNDO["rows"])
        if isinstance(v, float):
            assert v == pytest.approx(suma, abs=5e-3), k
        else:
            assert v == suma, k


def test_los_cuatro_veredictos_se_recalculan_desde_las_filas():
    filas = SEGUNDO["rows"]
    con_sin_len = [r for r in filas if r["sin_len"] > 0]
    agrupado = SEGUNDO["totals"]["candidates"] / SEGUNDO["totals"]["sin_len"]
    ficheros = SEGUNDO["totals"]["files"]
    bajo, alto = 0.0238 * ficheros, 0.055 * ficheros
    calculado = {
        "P1": all(r["candidates"] <= r["sin_len"] for r in filas),
        "P2": all(r["candidates"] / r["sin_len"] <= 0.50 for r in con_sin_len),
        "P3": 0.10 <= agrupado <= 0.45,
        "P4": bajo <= SEGUNDO["totals"]["segundos_min"] <= alto,
    }
    declarado = {p["id"]: p["verdict"] == "PASA" for p in SEGUNDO["predictions"]}
    assert calculado == declarado, (calculado, declarado)
    assert all(declarado.values()), "un veredicto declarado ya no pasa al recalcularlo"
    assert abs(SEGUNDO["predictions"][2]["observed"] - round(agrupado, 2)) < 0.005


def test_confirmatorio_no_se_lee_como_exploratorio():
    assert SEGUNDO["status"]["verdict"] == "CONFIRMATORIO"
    assert "limit" in SEGUNDO["status"], \
        "una confirmacion sin su limite declarado se lee como una tasa de la poblacion"
    assert FUERA["status"]["verdict"] == "EXPLORATORIO", \
        "el archivo anterior no cambia de estado porque llegue uno nuevo"


SECCION_2 = "### A batch named before it was fetched"


def _tabla_2(encabezado):
    lineas = README[README.index(SECCION_2):].splitlines()
    inicio = next(i for i, l in enumerate(lineas) if l.startswith(encabezado))
    filas = []
    for linea in lineas[inicio + 1:]:
        if not linea.startswith("|"):
            break
        celdas = [c.strip().replace("**", "").replace("`", "")
                  for c in linea.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in celdas):
            continue
        filas.append(celdas)
    return filas


def test_la_tabla_del_lote_2_es_el_archivo():
    filas = _tabla_2("| package | version | files | stores |")
    publicadas = [f for f in filas if f[0] != "added"]
    assert len(publicadas) == len(SEGUNDO["rows"])
    for celda, r in zip(publicadas, SEGUNDO["rows"]):
        assert celda[0] == r["package"], celda[0]
        assert celda[1] == r["version"], celda[1]
        for celda_i, clave in ((2, "files"), (3, "stores"), (4, "sin_len"), (5, "candidates")):
            assert _num(celda[celda_i]) == r[clave], (r["package"], clave)
    total = [f for f in filas if f[0] == "added"][0]
    for celda_i, clave in ((2, "files"), (3, "stores"), (4, "sin_len"), (5, "candidates")):
        assert _num(total[celda_i]) == SEGUNDO["totals"][clave], clave


def test_los_veredictos_y_el_cociente_del_readme_son_los_del_archivo():
    agrupado = SEGUNDO["totals"]["candidates"] / SEGUNDO["totals"]["sin_len"]
    assert f"{100 * agrupado:.1f} %" in README[README.index(SECCION_2):]
    for p in SEGUNDO["predictions"]:
        assert p["id"] in README[README.index(SECCION_2):], p["id"]
    # Las dos cifras del modelo de coste se publican y no pueden envejecer solas.
    for forma in ("files", "loops"):
        r2 = SEGUNDO["cost"]["regressors_fitted_on_10_out_of_sample_rows"][forma]["r2"]
        assert f"`R² = {r2}`" in README, (forma, r2)
    # El sitio no es el grupo, tampoco en este lote.
    s = SEGUNDO["sites_vs_groups"]
    assert s["sites"] == SEGUNDO["totals"]["candidates"]
    assert s["groups"] == len(s["detail"])
    assert "3 decisions" in README
