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
import math
import re
import statistics
import sys
from pathlib import Path

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


def _cuadra(suma, publicado):
    """El total de segundos se publica redondeado a dos decimales.

    Los enteros cuadran exacto. Los flotantes no: CPython 3.12 metio suma
    compensada (Neumaier) en sum(), asi que la misma lista da 2,06 en 3.12 y
    2,0599999999999996 en 3.11. Y cuando la suma cae justo en el borde de medio
    centesimo -- 2,745 -- el redondeo depende de la representacion binaria y no
    de la aritmetica, asi que no se compara el redondeo: se admite medio
    centesimo, que es la precision a la que se publica, mas un nano por la
    representacion. Una cifra que difiera en un centesimo entero muere.
    """
    return abs(suma - publicado) <= 5e-3 + 1e-9


def test_los_totales_son_la_suma_de_las_filas():
    for k, v in FUERA["totals"].items():
        suma = sum(r[k] for r in FUERA["rows"])
        if isinstance(v, float):
            assert _cuadra(suma, v), (k, v, suma)
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
            assert _cuadra(suma, v), (k, v, suma)
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


# --- lote 3: el lote que mato su propia unidad de factura --------------------
#
# El lote 2 predijo una tasa y sobrevivio. Este predijo la UNIDAD de la factura
# -- sitios partido por claves -- y al medirla mato la unidad de coste que el
# lote 2 habia dejado en pie. Los tests de este bloque recalculan los veredictos
# desde las filas: un veredicto que solo vive en la prosa envejece en silencio.
TERCERO = json.loads((RAIZ / "fuera-de-dominio-3.json").read_text(encoding="utf-8"))
PREDICCION_3 = RAIZ / "prediccion-batch-3.json"
SECCION_3 = "### A batch that killed its own unit of invoice"


def _ajuste(filas, clave):
    """s = a + b*clave por minimos cuadrados; devuelve (a, b, R2)."""
    n = len(filas)
    xs = [r[clave] for r in filas]
    ys = [r["segundos_min"] for r in filas]
    mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    ss = sum((y - my) ** 2 for y in ys)
    return a, b, 1 - sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / ss


def _quince():
    return FUERA["rows"] + SEGUNDO["rows"] + TERCERO["rows"]


def test_el_pin_de_la_prediccion_del_lote_3_es_el_archivo_que_viaja():
    assert TERCERO["prediction"]["sha256"] == _sha(PREDICCION_3)
    declarado = json.loads(PREDICCION_3.read_text(encoding="utf-8"))
    assert declarado["declared_before_fetch"] is True
    assert list(declarado["population"]["packages"]) == [r["package"] for r in TERCERO["rows"]], \
        "el lote medido no es el lote nombrado en la prediccion"


def test_las_filas_del_lote_3_anaden_campos_sin_perder_ninguno():
    # El esquema crecio: las fibras y la especie son medida nueva. Lo que no puede
    # pasar es que una fila del lote 3 pierda una clave que el lector del lote 2
    # compara, porque entonces el replay leeria None como si fuera un cero.
    faltan = set(SEGUNDO["rows"][0]) - set(TERCERO["rows"][0])
    assert not faltan, faltan
    for r in TERCERO["rows"]:
        assert len(r["sha256"]) == 64 and len(set(r["sha256"])) > 8, r["package"]
        assert sum(r[k] for k in CUBETAS) == r["stores"], r["package"]
        assert r["candidates"] <= r["sin_len"], r["package"]
        assert r["reconciles"] is True, r["package"]
        assert r["sites"] == r["candidates"], r["package"]
        assert r["groups"] <= r["sites"], r["package"]
        assert sum(r["species"].values()) == r["sites"], r["package"]
    assert len({r["sha256"] for r in TERCERO["rows"]}) == len(TERCERO["rows"])


def test_las_fibras_se_recalculan_y_la_frecuencia_sigue_refutando_p2():
    filas = TERCERO["rows"]
    con_sitios = [r for r in filas if r["sites"]]
    con_colision = [r for r in con_sitios if r["groups"] < r["sites"]]
    assert len(con_colision) == 1, [r["package"] for r in con_colision]
    assert con_colision[0]["package"] == "pyparsing"
    agrupado = TERCERO["totals"]["sites"] / TERCERO["totals"]["groups"]
    assert abs(agrupado - TERCERO["sites_vs_groups"]["fiber_pooled"]) < 1e-9
    # La conjuncion de P2 exige >= 3 de 5 filas con colision; el archivo la declara
    # refutada y este recalculo tiene que seguir dandole la razon.
    assert len(con_colision) < 3


def test_los_totales_del_lote_3_son_la_suma_de_sus_filas():
    for k, v in TERCERO["totals"].items():
        suma = sum(r[k] for r in TERCERO["rows"])
        if isinstance(v, float):
            assert _cuadra(suma, v), (k, v, suma)
        else:
            assert v == suma, k


def test_p4_se_recalcula_y_loops_ya_no_gana():
    filas = _quince()
    assert len(filas) == 15
    ajustes = {k: round(_ajuste(filas, k)[2], 4) for k in ("bytes", "files", "loops")}
    publicado = {k: v["r2"] for k, v in TERCERO["cost"]["regresores_sobre_15_filas"].items()}
    assert ajustes == publicado, (ajustes, publicado)
    # P4 exigia bucles - ficheros >= 0.20; el recalculo da negativo: la prediccion
    # murio y el orden de los regresores se invirtio.
    assert ajustes["loops"] - ajustes["files"] < 0.20
    assert ajustes["files"] > ajustes["loops"] > 0
    assert ajustes["bytes"] >= ajustes["files"], "el mejor regresor unico ya no es el tamano"


def test_la_tasa_de_los_tres_lotes_se_recalcula():
    lotes = {"1": FUERA, "2": SEGUNDO, "3": TERCERO}
    publicado = {str(d["lote"]): d for d in TERCERO["rate_is_a_property_of_the_project"]["lotes"]}
    acumulado = [0, 0]
    for clave, doc in lotes.items():
        c, d = doc["totals"]["candidates"], doc["totals"]["sin_len"]
        assert c == publicado[clave]["candidates"] and d == publicado[clave]["sin_len"], clave
        assert abs(c / d - publicado[clave]["ratio"]) < 1e-3, clave
        acumulado = [acumulado[0] + c, acumulado[1] + d]
    total = TERCERO["rate_is_a_property_of_the_project"]["cumulative_out_of_sample"]
    assert [total["candidates"], total["sin_len"]] == acumulado
    assert abs(acumulado[0] / acumulado[1] - total["ratio"]) < 1e-3
    # Un cociente por lote que baja 40, 24, 11 no sostiene ninguna tasa unica.
    assert publicado["1"]["ratio"] > publicado["2"]["ratio"] > publicado["3"]["ratio"]


ORIENTACIONES = ("medido/predicho", "predicho/medido")


def _orientacion(p):
    """La orientacion de un cociente, en cualquiera de sus dos formas admitidas.

    La canonica nombra los dos terminos (`medido/predicho`). El lote 4 estreno dos
    formas mas sin romper la regla: la formula que escribe el cociente entero
    (`error = |medido - predicho| / predicho`, `a_cpu / t0_cpu`) y la que declara
    que no hay cociente (`no_aplica: es una identidad`). Las tres se leen sin
    inferir nada -- lo que sigue sin pasar es una llave ausente o un cociente con un
    lado vacio, porque entonces el lector tiene que adivinar el denominador.
    """
    declarada = (p.get("ratio_orientation") or "").strip()
    if declarada in ORIENTACIONES or declarada.startswith("no_aplica"):
        return declarada
    izquierda, barra, derecha = declarada.partition("/")
    if barra and izquierda.strip() and derecha.strip():
        return declarada
    return None


def test_toda_prediccion_con_cociente_declara_su_orientacion():
    """Un cociente entre medicion y modelo tiene dos lecturas y la llave no lo dice.

    El pre-registro de este lote escribio la banda como medido/predicho y la
    justifico con extremos anotados como predicho/medido. Bajo una letra
    sobrevive y bajo la otra muere, asi que el defecto es del pre-registro. La
    regla vale para todo archivo nuevo; la excepcion se nombra aqui y tiene que
    seguir documentada en el artefacto, o deja de ser una excepcion y pasa a ser
    un agujero.
    """
    exentos = {("prediccion-batch-3.json", "P3")}
    for fichero in sorted(RAIZ.glob("prediccion-batch-*.json")):
        doc = json.loads(fichero.read_text(encoding="utf-8"))
        for p in doc["predictions"]:
            texto = p["claim"].lower()
            if "predicho" not in texto and "modelo" not in texto:
                continue
            if (fichero.name, p["id"]) in exentos:
                continue
            assert _orientacion(p), \
                f"{fichero.name} {p['id']}: un cociente sin orientacion admite dos veredictos"
    defecto = TERCERO["defect_found"]
    assert defecto["where"].startswith("prediccion-batch-3.json")
    assert "P3" in defecto["where"]
    assert "ratio_orientation" in defecto["fix"]
    assert "ratio_orientation" in README, "la regla del esquema se lee en el archivo, no solo en el test"


def test_la_tabla_del_lote_3_es_el_archivo():
    lineas = README[README.index(SECCION_3):]
    inicio = next(i for i, l in enumerate(lineas.splitlines())
                  if l.startswith("| package | version | files | stores |"))
    filas = []
    for linea in lineas.splitlines()[inicio + 1:]:
        if not linea.startswith("|"):
            break
        celdas = [c.strip().replace("**", "").replace("`", "")
                  for c in linea.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in celdas):
            continue
        filas.append(celdas)
    publicadas = [f for f in filas if f[0] != "added"]
    assert len(publicadas) == len(TERCERO["rows"])
    for celda, r in zip(publicadas, TERCERO["rows"]):
        assert celda[0] == r["package"], celda[0]
        assert celda[1] == r["version"], celda[1]
        for celda_i, clave in ((2, "files"), (3, "stores"), (4, "sin_len"),
                               (5, "loops"), (6, "sites"), (7, "groups")):
            assert _num(celda[celda_i]) == r[clave], (r["package"], clave)
        assert float(celda[8]) == r["segundos_min"], (r["package"], celda[8])
    total = [f for f in filas if f[0] == "added"][0]
    for celda_i, clave in ((2, "files"), (3, "stores"), (4, "sin_len"),
                           (5, "loops"), (6, "sites"), (7, "groups")):
        assert _num(total[celda_i]) == TERCERO["totals"][clave], clave
    assert float(total[8]) == TERCERO["totals"]["segundos_min"]


def test_las_cifras_del_readme_del_lote_3_son_las_del_archivo():
    trozo = README[README.index(SECCION_3):]
    plano = trozo.replace("\n", " ")
    for k in ("bytes", "files", "loops"):
        assert str(TERCERO["cost"]["regresores_sobre_15_filas"][k]["r2"]) in trozo, k
    for d in TERCERO["rate_is_a_property_of_the_project"]["lotes"]:
        assert f"{100 * d['ratio']:.1f} %" in trozo, d["lote"]
    total = TERCERO["rate_is_a_property_of_the_project"]["cumulative_out_of_sample"]
    assert f"{100 * total['ratio']:.1f} %" in trozo
    assert "nothing is priced per loop" in plano
    for p in TERCERO["predictions"]:
        assert p["id"] in trozo, p["id"]


# --- lote 4: dos relojes y la unidad de factura ------------------------------
#
# El lote 3 cerro con "termino fijo mas tamano", apoyado en una R2. Este lote
# mide dos relojes sobre los mismos sujetos y encuentra que lo unico que
# reproduce entre sesiones es el conteo. Se recalculan los cinco veredictos: un
# veredicto que solo vive en la prosa envejece en silencio, y este decide que se
# cobra.
CUARTO = json.loads((RAIZ / "fuera-de-dominio-4.json").read_text(encoding="utf-8"))
PREDICCION_4 = RAIZ / "prediccion-batch-4.json"
SECCION_4 = "### The invoice is not denominated in seconds"
# Lo que los cuatro lotes comparten. `sites`/`groups` nacieron en el lote 3 y se
# exigen aparte: comparar contra una clave que la fila vieja no tiene seria comparar
# contra None.
CONTEOS = ("files", "stores", "pierde", "candidates", "admitted", "column_loci", "loops",
           "rc", "rc_certificado", "reconciles", "certifica")
CONTEOS_3 = ("sites", "groups", "species")


def _veredictos(doc):
    return {p["id"]: p for p in doc["predictions"]}


def _modelo(filas, clave, reloj):
    """s = a + b*clave por minimos cuadrados, con el reloj elegido en la y."""
    n = len(filas)
    xs = [r[clave] for r in filas]
    ys = [r[reloj] for r in filas]
    mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    ss = sum((y - my) ** 2 for y in ys)
    return a, b, 1 - sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / ss


def _loo(filas, reloj, clave="bytes"):
    """Error relativo leave-one-out contra el modelo que excluye esa fila."""
    out = []
    for i, r in enumerate(filas):
        a, b, _ = _modelo([x for j, x in enumerate(filas) if j != i], clave, reloj)
        predicho = a + b * r[clave]
        out.append(abs(r[reloj] - predicho) / predicho)
    return sorted(out)


def _conocidos():
    return CUARTO["rows"][:15]


def _por_sujeto(*docs):
    return {(r["package"], r["scope"]): r for d in docs for r in d["rows"]}


def test_el_pin_del_lote_4_es_el_archivo_que_viaja():
    assert CUARTO["prediction"]["sha256"] == _sha(PREDICCION_4)
    declarado = json.loads(PREDICCION_4.read_text(encoding="utf-8"))
    assert declarado["declared_before_fetch"] is True
    # Los quince sujetos conocidos que la prediccion nombra son los que los lotes
    # 1-3 publicaron: si aqui se colara una fila nueva, la comparacion dejaria de
    # ser pareada y la ventaja del reloj de CPU no seria atribuible al reloj.
    publicados = _por_sujeto(FUERA, SEGUNDO, TERCERO)
    for pin in declarado["subjects"]["conocidos"]:
        assert pin["sha256"] == publicados[(pin["package"], pin["scope"])]["sha256"], pin["package"]
    assert len(declarado["subjects"]["conocidos"]) == 15
    assert declarado["subjects"]["total"] == 20 == len(CUARTO["rows"])


def test_p1_los_conteos_replayan_contra_lo_publicado():
    publicados = _por_sujeto(FUERA, SEGUNDO, TERCERO)
    identicos = [r for r in _conocidos()
                 if all(r[k] == publicados[(r["package"], r["scope"])][k] for k in CONTEOS)]
    assert len(identicos) == 15
    assert CUARTO["determinism"]["identicos_contra_lo_publicado"] == "15 de 15"
    assert _veredictos(CUARTO)["P1"]["verdict"] == "SOBREVIVE"
    for r in _conocidos():
        assert r["sha256_medido"] == r["sha256"], r["package"]


def test_p2_la_direccion_sobrevive_y_la_banda_no():
    cpu, pared = _loo(_conocidos(), "cpu_min"), _loo(_conocidos(), "wall_min")
    medido = _veredictos(CUARTO)["P2"]["medido"]
    # El archivo declara refutada porque la banda se paso de optimista. El recobro
    # tiene que dar los mismos numeros Y la misma direccion (cpu mejor que pared).
    assert round(100 * statistics.median(cpu), 1) == medido["cpu_p50_loo"]
    assert round(100 * max(cpu), 1) == medido["cpu_max_loo"]
    assert a_sostiene_refutacion(medido), "P2 ya no estaria refutada"
    assert statistics.median(cpu) < statistics.median(pared)
    assert _veredictos(CUARTO)["P2"]["verdict"] == "REFUTADA"


def a_sostiene_refutacion(medido):
    return medido["cpu_p50_loo"] > 10.0 and medido["cpu_max_loo"] > 25.0


def test_p3_el_ruido_es_del_reloj_de_pared():
    filas = CUARTO["rows"]
    for r in filas:
        assert r["cpu_min"] <= r["cpu_max"] and r["wall_min"] <= r["wall_max"], r["package"]
        assert r["wall_min"] >= r["cpu_min"], r["package"]
    cocientes = sorted(r["wall_max"] / r["wall_min"] / (r["cpu_max"] / r["cpu_min"]) for r in filas)
    mediana = round(statistics.median(cocientes), 2)
    assert mediana == _veredictos(CUARTO)["P3"]["medido"]["cociente_mediano"] == 2.77
    assert mediana >= 2.0
    assert _veredictos(CUARTO)["P3"]["verdict"] == "SOBREVIVE"


def test_p4_el_intercepto_es_el_arranque_y_no_un_parametro_libre():
    a, _, _ = _modelo(_conocidos(), "bytes", "cpu_min")
    ratio = a / CUARTO["arranque_vacio"]["cpu_min"]
    assert 0.5 <= ratio <= 2.0
    assert round(ratio, 2) == _veredictos(CUARTO)["P4"]["medido"]["ratio"] == 0.66
    # Con el reloj de pared el mismo cociente se sale de la banda: la coincidencia
    # es del reloj, no del ajuste.
    a_pared, _, _ = _modelo(_conocidos(), "bytes", "wall_min")
    assert round(a_pared / CUARTO["arranque_vacio"]["wall_min"], 2) == 0.38


def test_p5_docutils_mata_la_extrapolacion():
    a, b, _ = _modelo(_conocidos(), "bytes", "cpu_min")
    errores = {r["package"]: abs(r["cpu_min"] - (a + b * r["bytes"])) / (a + b * r["bytes"])
               for r in CUARTO["rows"][15:]}
    publicado = {n["package"]: n["error_relativo"] for n in _veredictos(CUARTO)["P5"]["medido"]["filas"]}
    assert set(errores) == set(publicado)
    for paquete, error in errores.items():
        assert round(error, 4) == publicado[paquete], paquete
    assert sum(1 for e in errores.values() if e <= 0.25) == 4
    assert errores["docutils"] > 0.25
    assert _veredictos(CUARTO)["P5"]["verdict"] == "REFUTADA"


def test_las_dos_fallas_son_del_regresor_y_no_del_reloj():
    # attrs: un artefacto, dos subarboles, el mismo bytes y cinco veces mas trabajo.
    attrs = [r for r in CUARTO["rows"] if r["package"] == "attrs"]
    assert {r["scope"] for r in attrs} == {"attr", "attrs"}
    assert len({r["bytes"] for r in attrs}) == 1, "bytes no distingue el sujeto escaneado"
    assert len({r["files"] for r in attrs}) == 2
    assert max(r["cpu_min"] for r in attrs) / min(r["cpu_min"] for r in attrs) > 5.0
    # docutils: menos bytes que setuptools y mas CPU -- bytes tampoco mide densidad.
    nuevos = {r["package"]: r for r in CUARTO["rows"][15:]}
    assert nuevos["docutils"]["bytes"] < nuevos["setuptools"]["bytes"]
    assert nuevos["docutils"]["files"] < nuevos["setuptools"]["files"]
    assert nuevos["docutils"]["cpu_min"] > nuevos["setuptools"]["cpu_min"]
    assert {"attrs", "docutils"} <= set(CUARTO["failures_anatomy"])


def test_la_deriva_entre_sesiones_se_recalcula():
    publicados = _por_sujeto(FUERA, SEGUNDO, TERCERO)
    cpu, pared = [], []
    for r in _conocidos():
        previo = publicados[(r["package"], r["scope"])]["segundos_min"]
        cpu.append(r["cpu_min"] / previo)
        pared.append(r["wall_min"] / previo)
    deriva = CUARTO["clock_drift"]
    for clave, valores in (("cpu_sobre_publicado", cpu), ("pared_sobre_publicado", pared)):
        assert round(statistics.median(valores), 2) == deriva[clave]["p50"], clave
        assert round(min(valores), 2) == deriva[clave]["min"], clave
        assert round(max(valores), 2) == deriva[clave]["max"], clave
    # Ningun reloj reproduce: la deriva es un factor que depende de la maquina.
    assert min(cpu) > 1.0 and max(cpu) > 2.0
    assert max(pared) > 3.0


def test_la_seccion_del_lote_4_publica_el_archivo():
    trozo = README[README.index(SECCION_4):]
    for fijo in ("| P1 |", "| P2 |", "| P3 |", "| P4 |", "| P5 |",
                 "15 of 15", "2.77", "0.66", "66.3 %", "16.7 %", "81.5 %",
                 "10.370 s", "16.204 s", "1.23×–2.27×", "1.26×–3.93×", "5.2×"):
        assert fijo in trozo, fijo
    assert "unit of work" in trozo
    # La retirada del lote 3 se anuncia donde el lector la busca: al final del
    # parrafo que la sostuvo, no solo en la seccion nueva.
    anterior = README[README.index(SECCION_3):README.index(SECCION_4)]
    assert "does not survive either" in anterior


def test_cada_prediccion_del_lote_4_declara_su_orientacion():
    # La regla del lote 3, cumplida por las dos formas admitidas: tres predicciones
    # nombran su denominador y dos declaran que no son un cociente.
    declarado = json.loads(PREDICCION_4.read_text(encoding="utf-8"))
    assert len(declarado["predictions"]) == 5
    for p in declarado["predictions"]:
        assert p.get("ratio_orientation"), p["id"]
        assert _orientacion(p), p["id"]


def test_el_lote_4_no_abre_un_esquema_paralelo():
    # El esquema crece (dos relojes) sin perder lo que el lote 3 ya media: una
    # clave perdida la leeria el censo como cero.
    faltan = set(CONTEOS + CONTEOS_3) - set(CUARTO["rows"][0])
    assert not faltan, faltan
    for k in ("wall_min", "wall_max", "cpu_min", "cpu_max", "sha256_medido", "segundos_min_publicado"):
        assert k in CUARTO["rows"][0]
    for r in CUARTO["rows"]:
        assert sum(r[k] for k in CUBETAS) == r["stores"], r["package"]
        assert sum(r["species"].values()) == r["sites"], r["package"]
        assert r["sites"] == r["candidates"], r["package"]
        assert len(r["wall_muestras"]) == len(r["cpu_muestras"]) == 5, r["package"]


# --- Lote 5: la cotizacion que no da un numero -------------------------------
#
# El lote 4 dejo la factura en conteos y el reloj al lado. El paso obvio es
# convertir ese reloj en precio; lo que el lote 5 entrega son conteos, una banda
# con cobertura declarada y una negativa. Estas pruebas separan las tres cosas y
# recomputan cada cifra que la seccion publica.
QUINTO = json.loads((RAIZ / "fuera-de-dominio-5.json").read_text(encoding="utf-8"))
PREDICCION_5 = RAIZ / "prediccion-batch-5.json"
SECCION_5 = "### The quote that refuses to give a number"


def test_el_pin_del_lote_5_es_el_archivo_que_viaja():
    assert QUINTO["prediction"]["sha256"] == _sha(PREDICCION_5)
    declarado = json.loads(PREDICCION_5.read_text(encoding="utf-8"))
    assert declarado["declared_before_computation"] is True
    assert len(declarado["predictions"]) == len(QUINTO["predictions"]) == 5


def test_el_lote_5_repara_lo_que_su_control_encontro():
    # El defecto no lo encontro una lectura: lo encontro correr el control. Cinco
    # filas del lote 4 publicaban la medicion donde el contrato pide el pin.
    defecto = QUINTO["defect_found"]
    nombrados = {"wcwidth", "sqlparse", "pyflakes", "docutils", "setuptools"}
    for paquete in nombrados:
        assert paquete in defecto["where"], paquete
    assert "sha256_medido" in defecto["what"] and defecto["resolved_in"] == "lote 5"
    for r in CUARTO["rows"]:
        # Un lector de terceros compara `sha256`; sin el, la fila es una trascripcion.
        assert HEX64.match(r["sha256"]), r["package"]
        if r["package"] in nombrados:
            assert r["sha256"] == r["sha256_medido"], r["package"]
            assert r["lote"] == 4, r["package"]
    assert QUINTO["control"]["filas_identicas"] == QUINTO["control"]["filas"] == len(CUARTO["rows"])
    assert QUINTO["control"]["rc"] == 0


def test_la_banda_conforme_es_el_cuantil_que_declara():
    residuos = _loo(_conocidos(), "cpu_min")
    indice = math.ceil((len(residuos) + 1) * (1 - QUINTO["banda"]["calibracion"]["alfa"])) - 1
    cal = QUINTO["banda"]["calibracion"]
    assert cal["filas"] == len(residuos) == 15
    assert cal["cuantil_indice"] == indice == 12
    assert cal["q"] == round(residuos[indice], 4)
    assert cal["max_residuo"] == round(residuos[-1], 4)
    assert cal["residuos"] == [round(x, 4) for x in residuos]
    # Lo que hace que la banda sea una banda y no el peor caso: el cuantil no es
    # el maximo, y el maximo es un solo sujeto.
    assert cal["q"] < cal["max_residuo"]
    assert cal["q"] < 0.50


def test_la_cobertura_medida_es_la_que_el_alfa_promete():
    conocidos = _conocidos()
    a, b, _ = _modelo(conocidos, "bytes", "cpu_min")
    q = QUINTO["banda"]["calibracion"]["q"]
    cobertura = QUINTO["banda"]["cobertura_retencion"]
    fuera = []
    for fila in cobertura["filas"]:
        r = next(x for x in CUARTO["rows"] if x["package"] == fila["package"])
        predicho = a + b * r["bytes"]
        error = abs(r["cpu_min"] - predicho) / predicho
        assert fila["bytes"] == r["bytes"], fila["package"]
        assert fila["predicho"] == round(predicho, 4), fila["package"]
        assert fila["error_relativo"] == round(error, 4), fila["package"]
        assert fila["dentro"] is (error <= q), fila["package"]
        if not fila["dentro"]:
            fuera.append(fila["package"])
    assert cobertura["previstos"] == len(cobertura["filas"]) == 5
    assert cobertura["dentro"] == sum(1 for f in cobertura["filas"] if f["dentro"]) == 4
    assert cobertura["dentro"] >= 3
    # La que cae fuera es el sujeto que el lote 4 ya habia nombrado como falla del
    # regresor: la banda vale para sujetos como los de calibracion, y lo dice.
    assert fuera == ["docutils"]


def test_el_lote_5_no_cotiza_tiempo_de_un_arbol_en_disco():
    cot = QUINTO["cotizacion"]
    assert cot["tiempo"]["estado"] == "NO_MEDIDO"
    assert cot["tiempo"]["que_falta"]
    assert cot["precio"]["estado"] == "NO_COTIZADO"
    assert HEX64.match(cot["sujeto"]["manifiesto_sha256"])
    # Los conteos si son del sujeto: cierran entre si, que es lo unico que una
    # cotizacion puede afirmar sin un modelo.
    c = cot["conteos"]
    assert sum(c[k] for k in CUBETAS) == c["stores"]
    assert c["candidates"] == cot["unidades_facturables"]["sitios"]
    assert cot["unidades_facturables"]["claves"] == c["column_loci"]
    assert cot["unidades_facturables"]["ficheros"] == c["files"]
    assert cot["reloj"]["determinista"] is True
    assert cot["reloj"]["cpu_min"] > 0 and cot["reloj"]["wall_min"] > 0


def test_la_aritmetica_de_la_tarifa_de_ejemplo_es_una_suma():
    ejemplo = json.loads((RAIZ / "tarifa.ejemplo.json").read_text(encoding="utf-8"))
    assert ejemplo["firmada"] is False
    aritmetica = QUINTO["tarifa_de_ejemplo"]["aritmetica_comprobada"]
    assert QUINTO["tarifa_de_ejemplo"]["firmada"] is False
    assert aritmetica["estado"] == "COTIZADO"
    assert aritmetica["total"] == sum(x["subtotal"] for x in aritmetica["detalle"])
    for x in aritmetica["detalle"]:
        assert x["subtotal"] == x["conteo"] * x["coeficiente"], x["unidad"]
        assert x["coeficiente"] == ejemplo["coeficientes"][x["unidad"]], x["unidad"]
    # El total del archivo no se teclea: sale de la misma funcion que lo emitiria
    # con una tarifa firmada.
    assert aritmetica["total"] == 4600


def test_las_cinco_predicciones_del_lote_5_se_verifican_contra_la_medicion():
    v = _veredictos(QUINTO)
    q = QUINTO["banda"]["calibracion"]["q"]
    dentro = QUINTO["banda"]["cobertura_retencion"]["dentro"]
    assert v["P1"]["verdict"] == "SOBREVIVE" and v["P1"]["medido"]["filas_identicas"] == "20 de 20"
    # P2 pedia una banda de medio punto; se midio mas estrecha. La prediccion era
    # pesimista, no el instrumento.
    assert v["P2"]["verdict"] == "REFUTADA" and q < v["P2"]["banda"]["q_min"]
    assert v["P3"]["verdict"] == "SOBREVIVE" and dentro >= 3
    assert v["P4"]["verdict"] == "SOBREVIVE"
    assert v["P4"]["medido"]["con_tarifa_firmada"] == "COTIZADO"
    assert v["P4"]["medido"]["total"] == 4600
    assert v["P4"]["medido"]["sin_tarifa"] == "NO_COTIZADO"
    # P5 tenia dos mitades y solo una se puede puntuar.
    assert v["P5"]["verdict"] == "NO_MEDIDO"
    assert QUINTO["predictions_summary"]["sobrevive"] == 3
    assert QUINTO["predictions_summary"]["refutada"] == 1
    assert QUINTO["predictions_summary"]["no_medido"] == 1


def _tabla_5(encabezado):
    lineas = README[README.index(SECCION_5):].splitlines()
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


def test_la_seccion_del_lote_5_publica_el_archivo():
    trozo = README[README.index(SECCION_5):]
    fijos = ("8093a1f2558cf42f", "cpu_min 0,4303 s", "wall_min 0,5071 s",
             "NO_MEDIDO", "NO_COTIZADO", "4600", "firmada: false",
             "20 `identico:` lines", "4 of 5")
    for fijo in fijos:
        assert fijo in trozo, fijo
    # Cada celda de la banda sale del artefacto, no de la prosa que la rodea: un
    # numero publicado dos veces con dos valores es el defecto que este lote mide.
    cal = QUINTO["banda"]["calibracion"]
    banda = {f[0]: f[1] for f in _tabla_5("| | value |")}
    assert banda["q (half-width, relative)"] == f"{cal['q']:.4f}".replace(".", ",")
    assert banda["max LOO residual"] == f"{cal['max_residuo']:.4f}".replace(".", ",")
    assert quilates(banda["residuals, sorted"]) == [f"{x:.2f}".replace(".", ",") for x in cal["residuos"]]


def quilates(celda):
    return [x.strip() for x in celda.split("·")]


def test_la_tabla_de_cobertura_del_lote_5_es_el_archivo():
    filas = {f[0]: f for f in _tabla_5("| package | bytes |")}
    for fila in QUINTO["banda"]["cobertura_retencion"]["filas"]:
        publicada = filas[fila["package"]]
        assert _num(publicada[1]) == fila["bytes"], fila["package"]
        assert publicada[2] == f"{fila['cpu_min']:.4f}".replace(".", ","), fila["package"]
        assert publicada[3] == f"{fila['predicho']:.4f}".replace(".", ","), fila["package"]
        assert publicada[4] == f"{fila['error_relativo']:.4f}".replace(".", ","), fila["package"]
        assert publicada[5] == ("yes" if fila["dentro"] else "no"), fila["package"]


# --- Lote 6: el sujeto del modelo -------------------------------------------
#
# El lote 5 se nego a cotizar un arbol porque su modelo se habia ajustado sobre
# bytes de artefacto. Este lote mueve solo la regresora, y lo hace sobre los
# veinte relojes del lote 4 sin volver a cronometrar: por eso la comparacion es
# pareada y toda diferencia de error es atribuible al cambio de `x`. Lo que estas
# pruebas separan: que el emparejamiento sea real, que ambos ajustes y las dos
# coberturas se recompongan desde las filas, y que el intervalo publicado se
# compare contra el ruido del instrumento y no solo contra el error del modelo.
SEXTO = json.loads((RAIZ / "fuera-de-dominio-6.json").read_text(encoding="utf-8"))
PREDICCION_6 = RAIZ / "prediccion-batch-6.json"
SECCION_6 = "### The model's subject"


def _tabla_6(encabezado):
    lineas = README[README.index(SECCION_6):].splitlines()
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


def _coma(x, n=4):
    return f"{x:.{n}f}".replace(".", ",")


def test_el_pin_del_lote_6_es_el_archivo_que_viaja():
    assert SEXTO["prediction"]["sha256"] == _sha(PREDICCION_6)
    declarado = json.loads(PREDICCION_6.read_text(encoding="utf-8"))
    assert declarado["declared_before_computation"] is True
    assert declarado["batch"] == SEXTO["lote"] == 6
    assert [p["id"] for p in declarado["predictions"]] == [v["id"] for v in SEXTO["veredictos"]]
    # El pin del codigo viaja al lado del sha256: un blob de git es otro objeto.
    assert re.fullmatch(r"[0-9a-f]{40}", SEXTO["prediction"]["git_blob"])


def test_el_lote_6_es_pareado_sobre_los_veinte_relojes_del_lote_4():
    assert len(SEXTO["rows"]) == len(CUARTO["rows"]) == 20
    for nuevo, viejo in zip(SEXTO["rows"], CUARTO["rows"]):
        assert (nuevo["package"], nuevo["scope"]) == (viejo["package"], viejo["scope"])
        assert nuevo["sha256"] == viejo["sha256"]
        # Si un solo reloj se hubiera vuelto a medir, la comparacion dejaria de
        # ser pareada y la mejora no seria atribuible a la regresora.
        assert nuevo["cpu_min"] == viejo["cpu_min"], nuevo["package"]
        assert nuevo["wall_min"] == viejo["wall_min"], nuevo["package"]
        assert nuevo["bytes"] == viejo["bytes"], nuevo["package"]


def test_los_dos_ajustes_se_recomponen_desde_las_filas():
    filas = SEXTO["rows"]
    for nombre, clave in (("artefacto", "bytes"), ("codigo", "bytes_py")):
        m = SEXTO["modelos"][nombre]
        assert m["clave"] == clave, nombre
        a, b, r2 = _modelo(filas[:15], clave, "cpu_min")
        assert abs(a - m["a"]) / m["a"] < 1e-4, nombre
        assert abs(b - m["b"]) / m["b"] < 1e-4, nombre
        assert abs(r2 - m["r2"]) < 5e-4, nombre
        residuos = _loo(filas[:15], "cpu_min", clave)
        assert m["residuos"] == [round(x, 4) for x in residuos], nombre
        assert m["loo_max"] == round(residuos[-1], 4), nombre
        assert m["loo_p50"] == round(statistics.median(residuos), 4), nombre
        # La mediana no es el maximo: si coincidieran, el lote seria un solo sujeto.
        assert m["loo_p50"] < m["loo_max"], nombre


def test_el_lote_6_reproduce_el_lote_5_antes_de_mejorarlo():
    # La primera fila de la tabla es una reproduccion, no una afirmacion nueva:
    # el ajuste sobre bytes de artefacto devuelve el q y el max del lote 5.
    cal = QUINTO["banda"]["calibracion"]
    artefacto = SEXTO["modelos"]["artefacto"]
    assert SEXTO["banda"]["artefacto"]["q"] == cal["q"] == 0.4258
    assert artefacto["loo_max"] == cal["max_residuo"] == 0.8147
    assert artefacto["residuos"][12] == cal["q"], "el cuantil del lote 5 y el de aqui no son el mismo"


def test_la_banda_del_lote_6_recompone_q_indice_y_frontera():
    q = SEXTO["banda"]["codigo"]["q"]
    assert q == SEXTO["modelos"]["codigo"]["residuos"][12]
    assert q < SEXTO["modelos"]["codigo"]["loo_max"]
    # La frontera se declara, no se redondea: wcwidth cae fuera por 9 partes en
    # un millon y el archivo la nombra en vez de contarla como acierto o fallo.
    assert SEXTO["banda"]["codigo"]["frontera"] == ["wcwidth"]
    fila = next(f for f in SEXTO["banda"]["codigo"]["filas"] if f["package"] == "wcwidth")
    assert fila["frontera"] is True and fila["dentro"] is False
    assert fila["residuo"] > q
    assert fila["residuo"] - q < 1e-4


def test_la_cobertura_del_lote_6_se_recompone_fila_a_fila():
    m = SEXTO["modelos"]["codigo"]
    q = SEXTO["banda"]["codigo"]["q"]
    retenidos = SEXTO["rows"][15:]
    filas = SEXTO["banda"]["codigo"]["filas"]
    assert len(filas) == len(retenidos) == 5
    for publicada, r in zip(filas, retenidos):
        assert publicada["package"] == r["package"]
        predicho = m["a"] + m["b"] * r["bytes_py"]
        assert abs(publicada["predicho_s"] - predicho) < 1e-3, r["package"]
        error = abs(r["cpu_min"] - predicho) / predicho
        assert abs(publicada["residuo"] - error) < 1e-4, r["package"]
        assert publicada["dentro"] == (publicada["residuo"] <= q), r["package"]
    assert SEXTO["banda"]["codigo"]["dentro"] == sum(1 for f in filas if f["dentro"]) == 2
    assert SEXTO["banda"]["codigo"]["total"] == 5
    # La cobertura baja al cambiar la regresora; que baje no es un defecto del
    # lote, es el resultado, y por eso el archivo publica las dos.
    assert SEXTO["banda"]["artefacto"]["dentro"] > SEXTO["banda"]["codigo"]["dentro"]


def test_attrs_se_ordena_con_bytes_py_y_no_con_bytes_de_artefacto():
    at = SEXTO["attrs"]
    assert at["bytes"][0] == at["bytes"][1], "sin el defecto no hay nada que curar"
    assert at["bytes_py"][0] > at["bytes_py"][1] * 100
    assert at["medido_s"][0] > at["medido_s"][1]
    assert at["artefacto"]["ordena"] is False
    assert at["artefacto"]["razon"] == 1.0
    assert at["codigo"]["ordena"] is True
    m = SEXTO["modelos"]["codigo"]
    predichos = [m["a"] + m["b"] * x for x in at["bytes_py"]]
    assert at["codigo"]["razon"] == round(predichos[0] / predichos[1], 3)
    assert at["codigo"]["razon"] > 2.0
    # Y el sujeto de attrs es la fila 0 y 1 del lote, no otra pareja.
    assert at["medido_s"] == [SEXTO["rows"][0]["cpu_min"], SEXTO["rows"][1]["cpu_min"]]


def test_cada_fila_declara_bytes_py_positivos_y_acotados():
    for r in SEXTO["rows"]:
        assert r["bytes_py"] > 0, r["package"]
        assert r["ficheros_py"] >= 1, r["package"]
        assert r["bytes_py"] <= 5.3 * r["bytes"], r["package"]
    minimo = min(r["bytes_py"] / r["bytes"] for r in SEXTO["rows"])
    maximo = max(r["bytes_py"] / r["bytes"] for r in SEXTO["rows"])
    assert SEXTO["covarianza"]["py_sobre_wheel_min"] == round(minimo, 4)
    assert SEXTO["covarianza"]["py_sobre_wheel_max"] == round(maximo, 4)
    assert maximo / minimo > 100, "si el cociente no varia, la regresora no cambia de sujeto"


def test_los_dos_instrumentos_cuentan_el_mismo_universo():
    # El conteo del escaner y un glob de .py son dos instrumentos: que coincidan
    # fila a fila dice que miden el mismo universo, no que compartan calculo.
    assert all(r["files"] == r["ficheros_py"] for r in SEXTO["rows"])
    assert SEXTO["coherencia"]["files_igual_ficheros_py"] == SEXTO["coherencia"]["filas"] == 20


def test_la_cotizacion_del_arbol_local_es_medida_y_cae_en_su_intervalo():
    t = SEXTO["cotizacion"]["tiempo"]
    assert t["estado"] == "MEDIDO"
    assert t["modelo"]["clave"] == "bytes_py"
    m = SEXTO["modelos"]["codigo"]
    predicho = m["a"] + m["b"] * t["bytes_py"]
    assert t["predicho_s"] == round(predicho, 4)
    q = SEXTO["banda"]["codigo"]["q"]
    # Las cotas se comprueban como ancho y no como digitos: el artefacto las
    # calcula con el ajuste sin redondear, y exigir el mismo redondeo aqui seria
    # medir el redondeo, no la banda.
    assert t["semicerco_relativo"] == q
    assert abs((t["intervalo_s"][1] - t["intervalo_s"][0]) - 2 * t["predicho_s"] * q) < 1e-3
    assert t["intervalo_s"][0] < t["predicho_s"] < t["intervalo_s"][1]
    medido = SEXTO["cotizacion"]["reloj"]["cpu_min"]
    assert t["intervalo_s"][0] <= medido <= t["intervalo_s"][1]
    assert SEXTO["cotizacion"]["reloj"]["determinista"] is True
    # El sujeto del arbol no se recompone aqui: la suite no tiene el arbol de esa
    # hora y un digest recalculado sobre el de hoy seria una medicion de otro
    # objeto. Lo que si se comprueba es que el intervalo sale del modelo publicado.
    assert HEX64.match(SEXTO["cotizacion"]["arbol"]["manifiesto_sha256"])
    assert SEXTO["cotizacion"]["arbol"]["bytes_py"] == t["bytes_py"] > 0
    assert SEXTO["cotizacion"]["precio"]["estado"] == "NO_COTIZADO"


def test_el_reloj_del_instrumento_se_mide_en_el_mismo_acto_que_la_banda():
    r = SEXTO["reloj_del_instrumento"]
    assert r["n_bloques"] == len(r["bloques"]) == 9
    assert all(len(b["lecturas"]) == b["n"] == 10 for b in r["bloques"])
    for b in r["bloques"]:
        assert b["min_s"] == min(b["lecturas"])
        assert b["max_s"] == max(b["lecturas"])
        assert b["jitter_s"] == round(b["max_s"] - b["min_s"], 4)
    assert r["jitter_por_bloque_s"] == [b["jitter_s"] for b in r["bloques"]]
    assert r["jitter_s"] == max(r["jitter_por_bloque_s"])
    assert r["jitter_min_s"] == min(r["jitter_por_bloque_s"])
    assert r["jitter_p50_s"] == round(statistics.median(r["jitter_por_bloque_s"]), 4)
    assert r["p50_min_s"] == min(b["p50_s"] for b in r["bloques"])
    assert r["p50_max_s"] == max(b["p50_s"] for b in r["bloques"])
    todos = [x for b in r["bloques"] for x in b["lecturas"]]
    assert r["dispersion"] == round(max(todos) / min(todos), 4)
    # El intervalo no hereda la banda sin mirar la maquina: se compara la
    # semianchura contra el jitter del mismo acto, y el juicio es esa comparacion.
    q = SEXTO["banda"]["codigo"]["q"]
    assert r["semianchura_s"] == round(r["predicho_s"] * q, 4)
    assert r["publicable"] == (r["semianchura_s"] > r["jitter_s"])
    assert r["minimo_publicable_s"] == round(r["jitter_s"] / q, 4)
    assert "dos poblaciones" in r["dos_poblaciones"]


def test_la_sensibilidad_del_arbol_es_la_que_publica_el_archivo():
    s = SEXTO["sensibilidad"]
    assert s["dispersion"] == round(max(l["reloj_s"] for l in s["lecturas"])
                                    / min(l["reloj_s"] for l in s["lecturas"]), 4)
    assert s["dispersion"] > 1.5, "si el reloj fuera estable entre sesiones no habria nada que declarar"
    # La lectura del lote 5, aplicada a la banda de hoy, queda fuera: es la prueba
    # de que el reloj de un arbol no se puede trasladar de una sesion a otra.
    assert s["residuo_con_reloj_lote5"] == round(
        abs(s["reloj_lote5_s"] - SEXTO["cotizacion"]["tiempo"]["predicho_s"])
        / SEXTO["cotizacion"]["tiempo"]["predicho_s"], 4)
    assert s["dentro_con_reloj_lote5"] == (s["residuo_con_reloj_lote5"] <= SEXTO["banda"]["codigo"]["q"])


def test_los_veredictos_del_lote_6_se_recomponen_desde_los_umbrales():
    v = {p["id"]: p for p in SEXTO["veredictos"]}
    codigo = SEXTO["modelos"]["codigo"]
    assert set(v) == {"P1", "P2", "P3", "P4", "P5"}
    assert v["P1"]["sobrevive"] == (codigo["loo_max"] < v["P1"]["umbral"])
    assert v["P1"]["medido"] == codigo["loo_max"]
    assert v["P2"]["sobrevive"] == (codigo["loo_p50"] < v["P2"]["umbral"])
    docutils = next(f for f in SEXTO["banda"]["codigo"]["filas"] if f["package"] == "docutils")
    assert v["P3"]["medido"] == docutils["residuo"]
    assert v["P3"]["sobrevive"] == (docutils["residuo"] <= SEXTO["banda"]["codigo"]["q"])
    assert v["P3"]["sobrevive"] is False
    assert v["P4"]["medido"] == SEXTO["attrs"]["codigo"]["razon"]
    assert v["P4"]["sobrevive"] == (SEXTO["attrs"]["codigo"]["razon"] > v["P4"]["umbral"])
    t = SEXTO["cotizacion"]["tiempo"]
    medido = SEXTO["cotizacion"]["reloj"]["cpu_min"]
    assert v["P5"]["umbral"] == t["intervalo_s"]
    assert v["P5"]["medido"] == medido
    assert v["P5"]["sobrevive"] == (t["intervalo_s"][0] <= medido <= t["intervalo_s"][1])
    resumen = SEXTO["predictions_summary"]
    assert resumen["sobreviven"] == sorted(k for k, p in v.items() if p["sobrevive"])
    assert resumen["caen"] == sorted(k for k, p in v.items() if not p["sobrevive"])
    # Una prediccion que enumera ramas y no incluye la observada no es una
    # particion: P3 cae sola y la taxonomia no la nombraba.
    assert resumen["rama"] == "P3_cae_FUERA_DE_TAXONOMIA"
    assert "P3" in resumen["hueco_de_la_taxonomia"]


def test_la_seccion_del_lote_6_publica_el_archivo():
    trozo = README[README.index(SECCION_6):]
    fijos = ("fuera-de-dominio-6.json", "bench/sujeto.py", "0,301809",
             "NO_COTIZADO", "0,1471", "jitter per block")
    for fijo in fijos:
        assert fijo in trozo, fijo
    filas = {f[0]: f for f in _tabla_6("| regressor |")}
    assert set(filas) == {"artifact bytes", "scanned .py bytes"}
    for nombre, doc in (("artifact bytes", "artefacto"), ("scanned .py bytes", "codigo")):
        celda, m = filas[nombre], SEXTO["modelos"][doc]
        assert celda[1] == _coma(m["a"], 5), nombre
        assert celda[2] == f"{m['b']:.6e}", nombre
        assert celda[3] == _coma(m["r2"]), nombre
        assert celda[4] == _coma(m["loo_p50"]), nombre
        assert celda[5] == _coma(m["loo_max"]), nombre
        assert celda[6] == _coma(SEXTO["banda"][doc]["q"]), nombre
        assert celda[7] == f"{SEXTO['banda'][doc]['dentro']}/{SEXTO['banda'][doc]['total']}", nombre


def test_la_tabla_de_cobertura_del_lote_6_es_el_archivo():
    filas = {f[0]: f for f in _tabla_6("| package | scanned bytes |")}
    publicadas = SEXTO["banda"]["codigo"]["filas"]
    assert set(filas) == {f["package"] for f in publicadas}
    for f in publicadas:
        celda = filas[f["package"]]
        r = next(x for x in SEXTO["rows"] if x["package"] == f["package"])
        assert _num(celda[1]) == r["bytes_py"], f["package"]
        assert celda[2] == _coma(r["cpu_min"]), f["package"]
        assert celda[3] == _coma(f["predicho_s"]), f["package"]
        assert celda[4] == _coma(f["residuo"], 6 if f["frontera"] else 4), f["package"]
        dentro = "yes" if f["dentro"] else ("no (boundary)" if f["frontera"] else "no")
        assert celda[5] == dentro, f["package"]


# --- Lote 7: lo que ya esta predicho -----------------------------------------
#
# El lote 6 comparo banda y jitter sobre un solo arbol. Una afirmacion de
# publicabilidad es por sujeto, asi que el lote 7 la lleva a cinco. Estas pruebas
# no miden nada: sostienen que el orden exista antes de la medida y que los cinco
# sujetos se eligieran por la regresora y no por el reloj.
SEPTIMO = json.loads((RAIZ / "prediccion-batch-7.json").read_text(encoding="utf-8"))


def test_la_prediccion_del_lote_7_tiene_falsador_y_es_anterior():
    assert SEPTIMO["declared_before_computation"] is True
    assert SEPTIMO["batch"] == 7
    assert len(SEPTIMO["predictions"]) == 3
    for p in SEPTIMO["predictions"]:
        assert p["falsifier"].strip(), p["id"]
        assert p["cota_error"].strip(), p["id"]
        if p["kind"] == "cuantitativa":
            assert p.get("umbral") is not None, p["id"]
        else:
            assert "ratio_orientation" in p, p["id"]
    assert SEPTIMO["cost"]["escrituras_en_platino_labs"] == 0
    assert SEPTIMO["cost"]["clones_externos"] == 0
    assert SEPTIMO["cost"]["relojes_por_sujeto"] == len([]) + 90


def test_los_cinco_sujetos_del_lote_7_se_eligen_por_la_regresora():
    m = SEXTO["modelos"]["codigo"]
    predichos = sorted((round(m["a"] + m["b"] * r["bytes_py"], 4), r["package"], r["scope"])
                       for r in SEXTO["rows"])
    nombres = [(s["package"], s["scope"]) for s in SEPTIMO["subjects"]]
    esperados = [predichos[0][1:], predichos[1][1:], predichos[9][1:],
                 predichos[-2][1:], predichos[-1][1:]]
    assert nombres == esperados
    por_sujeto = {(r["package"], r["scope"]): r for r in SEXTO["rows"]}
    for s in SEPTIMO["subjects"]:
        r = por_sujeto[(s["package"], s["scope"])]
        # El pin es lo que impide que el lote 7 mida otros cinco sujetos.
        assert s["sha256"] == r["sha256"], s["package"]
        assert s["bytes_py"] == r["bytes_py"], s["package"]
        assert s["predicho_s"] == round(m["a"] + m["b"] * r["bytes_py"], 4), s["package"]


# --- Lote 7: el piso de ruido no es una constante, es una proporcion ---------
#
# El lote 6 dejo la publicabilidad calibrada sobre un arbol, y un bloque de esa
# misma sesion ya la habia vencido. El lote 7 la midio en cinco sujetos con el
# mismo protocolo. Estas pruebas no cronometran nada: recomponen de las 450
# lecturas el jitter de cada bloque y de cada sujeto, la semianchura, la
# condicion `publicable` y el minimo publicable, y sostienen por separado que el
# ruido crece 75 veces mientras los bytes crecen 2 940.
SEPTIMO_ARTE = json.loads((RAIZ / "fuera-de-dominio-7.json").read_text(encoding="utf-8"))
OCTAVO = RAIZ / "prediccion-batch-8.json"
SECCION_7 = "### The instrument's noise floor, per subject"
Q7 = SEXTO["banda"]["codigo"]["q"]


def _tabla_7(encabezado):
    lineas = README[README.index(SECCION_7):].splitlines()
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


def _bloques_7(sujeto):
    """El jitter de un bloque es su peor lectura menos la mejor: no se promedia."""
    fuera = []
    for i, b in enumerate(sujeto["bloques"], start=1):
        lecturas = b["lecturas"]
        assert len(lecturas) == 10, (sujeto["package"], i)
        fuera.append({
            "bloque": i,
            "min_s": min(lecturas),
            "p50_s": round(statistics.median(lecturas), 4),
            "max_s": max(lecturas),
            "jitter_s": round(max(lecturas) - min(lecturas), 4),
        })
    return fuera


def _todas_7(sujeto):
    return [x for b in sujeto["bloques"] for x in b["lecturas"]]


def test_el_pin_del_lote_7_es_la_orden_que_viaja():
    assert SEPTIMO_ARTE["lote"] == 7
    assert SEPTIMO_ARTE["prediction"]["archivo"] == "prediccion-batch-7.json"
    assert SEPTIMO_ARTE["prediction"]["sha256"] == _sha(RAIZ / "prediccion-batch-7.json")
    assert re.fullmatch(r"[0-9a-f]{40}", SEPTIMO_ARTE["prediction"]["git_blob"])
    assert SEPTIMO_ARTE["schema"] == "fiber-ast-lint/fuera-de-dominio/1"
    assert SEPTIMO_ARTE["prediction"]["declared_before_computation"] is True


def test_las_lecturas_del_lote_7_recomponen_su_jitter_y_su_banda():
    assert len(SEPTIMO_ARTE["sujetos"]) == 5
    for s in SEPTIMO_ARTE["sujetos"]:
        bloques = _bloques_7(s)
        assert [b["jitter_s"] for b in bloques] == [b["jitter_s"] for b in s["bloques"]], s["package"]
        assert [b["min_s"] for b in bloques] == [b["min_s"] for b in s["bloques"]], s["package"]
        assert [b["p50_s"] for b in bloques] == [b["p50_s"] for b in s["bloques"]], s["package"]
        assert [b["max_s"] for b in bloques] == [b["max_s"] for b in s["bloques"]], s["package"]

        jitters = [b["jitter_s"] for b in bloques]
        assert s["jitter_s"] == max(jitters), s["package"]
        assert s["jitter_min_s"] == min(jitters), s["package"]
        assert s["jitter_p50_s"] == round(statistics.median(jitters), 4), s["package"]
        assert s["p50_min_s"] == min(b["p50_s"] for b in bloques), s["package"]
        assert s["p50_max_s"] == max(b["p50_s"] for b in bloques), s["package"]
        assert s["dispersion"] == round(max(b["max_s"] for b in bloques)
                                        / min(b["min_s"] for b in bloques), 4), s["package"]

        # La regla del lote 7, recompuesta: la semianchura relativa se compara
        # contra el peor jitter del sujeto, y eso decide `publicable`.
        assert s["q"] == Q7, s["package"]
        assert s["semianchura_s"] == round(s["predicho_s"] * Q7, 4), s["package"]
        assert s["jitter_relativo"] == round(s["jitter_s"] / s["predicho_s"], 4), s["package"]
        assert s["publicable"] is (s["semianchura_s"] > s["jitter_s"]), s["package"]
        assert s["minimo_publicable_s"] == round(s["jitter_s"] / Q7, 4), s["package"]
        assert s["n_bloques"] * 10 == s["relojes"] == len(_todas_7(s)), s["package"]


def test_ningun_sujeto_del_lote_7_es_publicable():
    """El titular del lote: cero de cinco, y por que cero y no casi."""
    assert SEPTIMO_ARTE["predictions_summary"]["publicables"] == []
    assert SEPTIMO_ARTE["predictions_summary"]["sobreviven"] == ["J1"]
    assert sorted(SEPTIMO_ARTE["predictions_summary"]["caen"]) == ["J2", "J3"]
    for s in SEPTIMO_ARTE["sujetos"]:
        assert s["publicable"] is False, s["package"]
        assert s["jitter_relativo"] > Q7, s["package"]
        assert s["semianchura_s"] < s["jitter_s"], s["package"]
    # La negativa mas estrecha es el sujeto mayor, no el menor: el ruido no
    # escala con los bytes.
    estrecho = min(SEPTIMO_ARTE["sujetos"], key=lambda s: s["jitter_relativo"])
    ancho = max(SEPTIMO_ARTE["sujetos"], key=lambda s: s["jitter_relativo"])
    assert estrecho["package"] != ancho["package"]
    assert estrecho["bytes_py"] > ancho["bytes_py"]


def test_los_veredictos_del_lote_7_se_recomponen_de_las_lecturas():
    sujetos = SEPTIMO_ARTE["sujetos"]
    menor = min(sujetos, key=lambda s: s["bytes_py"])
    veredictos = {v["id"]: v for v in SEPTIMO_ARTE["veredictos"]}
    assert veredictos["J1"]["sujeto"] == f"{menor['package']}/{menor['scope']}"
    assert veredictos["J1"]["medido"] == menor["jitter_relativo"]
    assert veredictos["J1"]["sobrevive"] is (menor["jitter_relativo"] > Q7)
    j2 = [s for s in sujetos if f"{s['package']}/{s['scope']}" in veredictos["J2"]["sujetos"]]
    assert len(j2) == 2
    assert veredictos["J2"]["medido"] == {f"{s['package']}/{s['scope']}": s["jitter_relativo"] for s in j2}
    assert veredictos["J2"]["sobrevive"] is all(s["jitter_relativo"] < 0.05 for s in j2)
    j3 = veredictos["J3"]["medido"]
    assert j3 == {f"{s['package']}/{s['scope']}": s["jitter_p50_s"] for s in sujetos}
    dentro = [0.003 <= s["jitter_p50_s"] <= 0.05 for s in sujetos]
    assert veredictos["J3"]["sobrevive"] is all(dentro)
    assert [v["id"] for v in SEPTIMO_ARTE["veredictos"]] == [p["id"] for p in SEPTIMO["predictions"]]


def test_la_escala_del_lote_7_separa_el_piso_de_la_proporcion():
    sujetos = SEPTIMO_ARTE["sujetos"]
    escala = SEPTIMO_ARTE["escala"]
    jitters = [s["jitter_s"] for s in sujetos]
    bytes_ = [s["bytes_py"] for s in sujetos]
    assert escala["dispersion_jitter"] == round(max(jitters) / min(jitters), 4)
    assert escala["dispersion_bytes"] == round(max(bytes_) / min(bytes_), 1)
    # El argumento entero vive en este cociente: si el ruido fuera proporcion al
    # tamano, valdria 1.
    assert round(escala["dispersion_bytes"] / escala["dispersion_jitter"], 1) == 39.0
    por_mb = {}
    for s in sujetos:
        assert escala["jitter_por_megabyte_s"][s["package"]] == round(s["jitter_s"] / (s["bytes_py"] / 1e6), 4)
        assert escala["jitter_relativo"][s["package"]] == s["jitter_relativo"]
        por_mb[s["package"]] = escala["jitter_por_megabyte_s"][s["package"]]
    assert round(max(por_mb.values()) / min(por_mb.values()), 1) == 53.8


def test_el_costo_del_lote_7_se_suma_de_sus_partes():
    sujetos = SEPTIMO_ARTE["sujetos"]
    cost = SEPTIMO_ARTE["cost"]
    assert cost["clones_externos"] == 0
    assert cost["escrituras_en_platino_labs"] == 0
    assert cost["sujetos"] == len(sujetos) == 5
    assert cost["relojes_por_sujeto"] == 90
    assert cost["relojes_totales"] == sum(len(_todas_7(s)) for s in sujetos) == 450
    assert cost["segundos_de_pared"] == round(sum(s["segundos_de_pared"] for s in sujetos), 1)


def test_la_tabla_del_lote_7_es_el_artefacto_celda_a_celda():
    filas = _tabla_7("| package | scanned bytes |")
    assert len(filas) == 5
    por_nombre = {s["package"]: s for s in SEPTIMO_ARTE["sujetos"]}
    for fila in filas:
        s = por_nombre[fila[0]]
        assert _num(fila[1]) == s["bytes_py"], fila[0]
        assert _coma(s["predicho_s"]) == fila[2], fila[0]
        assert _coma(s["jitter_s"]) == fila[3], fila[0]
        assert _coma(s["semianchura_s"]) == fila[4], fila[0]
        assert _coma(s["jitter_relativo"]) == fila[5], fila[0]
        assert fila[6] == ("yes" if s["publicable"] else "no"), fila[0]


def test_la_tabla_de_las_lecturas_del_lote_7_es_el_artefacto():
    filas = _tabla_7("| package | best of 90 |")
    assert len(filas) == 5
    por_nombre = {s["package"]: s for s in SEPTIMO_ARTE["sujetos"]}
    for fila in filas:
        s = por_nombre[fila[0]]
        todas = _todas_7(s)
        mejor = min(todas)
        assert _coma(mejor) == fila[1], fila[0]
        assert _coma(statistics.median(todas)) == fila[2], fila[0]
        assert _coma(max(todas)) == fila[3], fila[0]
        assert _coma(max(todas) / mejor) == fila[4], fila[0]
        minimos = [min(b["lecturas"]) for b in s["bloques"]]
        assert _coma(max(minimos) / min(minimos)) == fila[5], fila[0]
        assert _num(fila[6].split("/")[0]) == sum(1 for x in todas if x > 2 * mejor), fila[0]


def test_el_lote_7_publica_el_cociente_y_no_un_promedio_de_ventaja():
    """La cifra que cierra el argumento: el minimo publicable del lote 6 era su
    propio jitter dividido por q, no una propiedad del escaner."""
    jitter6 = SEXTO["reloj_del_instrumento"]["jitter_s"]
    predicho6 = SEXTO["cotizacion"]["tiempo"]["predicho_s"]
    condicion6 = round(jitter6 / predicho6, 4)
    assert condicion6 == 0.1520
    assert abs(condicion6 - Q7 / 2) < 0.002
    assert SEXTO["reloj_del_instrumento"]["minimo_publicable_s"] == round(jitter6 / Q7, 4)
    media = round(sum(s["jitter_relativo"] for s in SEPTIMO_ARTE["sujetos"]) / 5, 4)
    assert media == 0.5736
    assert round(media / condicion6, 2) == 3.77


def test_la_orden_del_lote_8_esta_escrita_antes_de_su_acto():
    octavo = json.loads(OCTAVO.read_text(encoding="utf-8"))
    assert octavo["declared_before_computation"] is True
    assert octavo["batch"] == 8
    assert len(octavo["predictions"]) == 3
    for p in octavo["predictions"]:
        assert p["falsifier"].strip(), p["id"]
        assert p["cota_error"].strip(), p["id"]
    assert octavo["cost"]["escrituras_en_platino_labs"] == 0
    assert octavo["cost"]["clones_externos"] == 0
    assert octavo["cost"]["sujetos"] == 1 and octavo["cost"]["actos"] == 2
    assert octavo["cost"]["relojes_nuevos"] == 90
    # El acto A es el que el lote 7 ya midio sobre pyflakes: mismo sujeto, mismo
    # jitter, sin volver a cronometrar. Si el pin cambia, cambia el sujeto.
    pyflakes = next(s for s in SEPTIMO_ARTE["sujetos"] if s["package"] == "pyflakes")
    assert f"{pyflakes['jitter_s']:.4f}".replace(".", ",") in octavo["method"]["acto_a"]
    assert f"{pyflakes['predicho_s']:.4f}".replace(".", ",") in octavo["method"]["acto_a"]
    assert f"{pyflakes['jitter_relativo']:.4f}".replace(".", ",") in octavo["method"]["sujeto"]


def test_los_multiplos_que_publica_el_texto_se_recomponen():
    """Cada 'veces' de la prosa del lote 7 es un cociente del artefacto."""
    sujetos = {s["package"]: s for s in SEPTIMO_ARTE["sujetos"]}
    rel = {k: v["jitter_relativo"] for k, v in sujetos.items()}
    assert round(max(rel.values()) / min(rel.values()), 2) == 2.39          # dispersion de jitter/predicho
    assert round(rel["setuptools"] / Q7, 2) == 2.70                        # la mas ancha, sobre q
    assert round(rel["pygments"] / Q7, 2) == 1.13                          # la mas estrecha, sobre q
    assert round(rel["setuptools"] / 0.05, 1) == 16.3                      # J2 contra su umbral
    assert round(rel["pygments"] / 0.05, 1) == 6.8
    sobre_techo = sorted(round(s["jitter_p50_s"] / 0.05, 1)
                         for s in SEPTIMO_ARTE["sujetos"] if s["jitter_p50_s"] > 0.05)
    assert sobre_techo == [1.4, 2.6, 7.1, 21.7]                                 # J3 contra su techo
    assert round(max(rel.values()) / (Q7 / 2), 2) == 5.41                  # media sobre q/2, sin promedio


# --- lote 8: el piso es una lectura del acto, no una propiedad del sujeto ----
# El lote 8 mide el MISMO sujeto pinneado en dos actos. Estas pruebas no
# cronometran nada: recomponen de las 180 lecturas selladas el minimo, la
# mediana, el jitter y la dispersion de cada acto, sostienen los tres veredictos
# contra la orden congelada, y prueban por aritmetica que `q` es el semicerco
# relativo y no su doble, que es el defecto que hacia caer K1.
OCTAVO_ARTE = json.loads((RAIZ / "fuera-de-dominio-8.json").read_text(encoding="utf-8"))
SECCION_8 = "### The floor is a reading of the act"
NOVENO = RAIZ / "prediccion-batch-9.json"


def _seccion_8():
    return README[README.index(SECCION_8):README.index(SECCION_9)]


def _prosa_8():
    """La prosa va envuelta a 100 columnas: se compara sin saltos, no se reescribe."""
    return " ".join(_seccion_8().split())


def _tabla_8(encabezado):
    lineas = _seccion_8().splitlines()
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


def _resumen_8(acto):
    """Recompone de las lecturas crudas todo resumen del acto, sin heredarlo."""
    lecturas = sorted(x for b in acto["bloques"] for x in b["lecturas"])
    jit = [round(max(b["lecturas"]) - min(b["lecturas"]), 4) for b in acto["bloques"]]
    return {
        "n_bloques": len(acto["bloques"]),
        "relojes": len(lecturas),
        "jitter_s": max(jit),
        "jitter_p50_s": round(statistics.median(jit), 4),
        "jitter_min_s": min(jit),
        "p50_min_s": min(round(statistics.median(b["lecturas"]), 4) for b in acto["bloques"]),
        "p50_max_s": max(round(statistics.median(b["lecturas"]), 4) for b in acto["bloques"]),
        "dispersion": round(max(max(b["lecturas"]) for b in acto["bloques"])
                            / min(min(b["lecturas"]) for b in acto["bloques"]), 4),
        "minimo_s": round(lecturas[0], 4),
        "maximo_s": round(lecturas[-1], 4),
        "mediana_s": round(statistics.median(lecturas), 4),
    }


def test_el_lote_8_es_un_sujeto_y_dos_actos_sobre_el_mismo_pin():
    a, b = OCTAVO_ARTE["acto_a"], OCTAVO_ARTE["acto_b"]
    assert OCTAVO_ARTE["lote"] == 8
    assert OCTAVO_ARTE["prediction"]["sha256"] == _sha(OCTAVO)
    assert OCTAVO_ARTE["prediction"]["declared_before_computation"] is True
    assert OCTAVO_ARTE["cost"]["relojes_nuevos"] == 90
    assert OCTAVO_ARTE["cost"]["relojes_reutilizados"] == 90
    assert OCTAVO_ARTE["cost"]["relojes_totales"] == 180
    assert OCTAVO_ARTE["cost"]["segundos_de_pared"] > 0
    assert OCTAVO_ARTE["cost"]["escrituras_en_platino_labs"] == 0
    assert OCTAVO_ARTE["cost"]["clones_externos"] == 0
    # Dos controles independientes del sujeto: el pin de bytes y el sha256 de la
    # rueda. Tendrian que discrepar los dos para que el acto no fuera el mismo.
    assert a["bytes_py_pin"] == b["bytes_py_pin"] == b["bytes_py"]
    assert a["sha256"] == b["sha256"]
    assert b["pin_ok"] is True
    assert a["sujeto"] == b["sujeto"] == "pyflakes/pyflakes"
    # Y el acto A es, literalmente, la fila que el lote 7 ya pago.
    septimo = next(s for s in SEPTIMO_ARTE["sujetos"] if s["package"] == "pyflakes")
    assert a["sha256"] == septimo["sha256"]
    assert a["jitter_s"] == septimo["jitter_s"]
    assert [x for bl in a["bloques"] for x in bl["lecturas"]] == _todas_7(septimo)


def test_el_acto_a_recompuesto_cuadra_con_lo_que_el_lote_7_sello():
    """El acto A se relee del lote 7 y se recompone aqui: los dos tienen que dar lo mismo."""
    a = OCTAVO_ARTE["acto_a"]
    for campo, valor in a["sellado_lote_7"].items():
        assert a[campo] == valor, (campo, a[campo], valor)
    # `en_banda` no es la condicion de ruido: es el control del modelo del lote 6.
    assert a["en_banda"] is True
    assert a["publicable"] is False
    assert abs(a["cpu_min_lote6"] - a["predicho_s"]) / a["predicho_s"] <= a["q"]


def test_los_dos_actos_se_recomponen_de_sus_ciento_ochenta_lecturas():
    for nombre in ("acto_a", "acto_b"):
        acto = OCTAVO_ARTE[nombre]
        assert len(acto["bloques"]) == 9, nombre
        for i, bl in enumerate(acto["bloques"], start=1):
            assert len(bl["lecturas"]) == 10, (nombre, i)
            assert bl["jitter_s"] == round(max(bl["lecturas"]) - min(bl["lecturas"]), 4)
        for campo, valor in _resumen_8(acto).items():
            assert acto[campo] == valor, (nombre, campo, acto[campo], valor)


def test_los_veredictos_del_lote_8_son_los_que_la_orden_congelo():
    octavo = json.loads(OCTAVO.read_text(encoding="utf-8"))
    c = OCTAVO_ARTE["comparacion"]
    congelado = {p["id"]: p for p in octavo["predictions"]}
    veredicto = {v["id"]: v for v in OCTAVO_ARTE["veredictos"]}
    # K1: k_B < q/2. Cae, y cae por 0,10: el acto esta por encima del umbral.
    assert c["k_B"] >= congelado["K1"]["umbral"]
    assert veredicto["K1"]["sobrevive"] is False
    # K2: las dos mitades del acto, bloques 1-4 contra 6-9, sin compartir el 5.
    primera = max(x["jitter_s"] for x in OCTAVO_ARTE["acto_b"]["bloques"][:4])
    ultima = max(x["jitter_s"] for x in OCTAVO_ARTE["acto_b"]["bloques"][5:])
    assert (c["k_primera_mitad"], c["k_ultima_mitad"]) == (
        round(primera / c["predicho_s"], 4), round(ultima / c["predicho_s"], 4))
    assert c["delta_mitades"] == round(c["k_ultima_mitad"] - c["k_primera_mitad"], 4)
    assert c["delta_mitades"] < congelado["K2"]["umbral"]
    assert veredicto["K2"]["sobrevive"] is True
    # K3: el minimo no viaja. Cae por 2,10x.
    assert c["ratio_min_B_A"] == round(c["min_B_s"] / c["min_A_s"], 4)
    assert not congelado["K3"]["umbral"][0] <= c["ratio_min_B_A"] <= congelado["K3"]["umbral"][1]
    assert veredicto["K3"]["sobrevive"] is False
    assert c["k_A"] == round(c["jitter_A_s"] / c["predicho_s"], 4)
    assert c["k_B"] == round(c["jitter_B_s"] / c["predicho_s"], 4)


def test_q_es_el_semicerco_relativo_y_no_su_mitad():
    """El defecto del lote 8, probado por aritmetica y no por lectura."""
    t = SEXTO["cotizacion"]["tiempo"]
    q = SEXTO["banda"]["codigo"]["q"]
    assert t["semicerco_relativo"] == q == Q7
    # Si q fuera el semicerco, el intervalo publicado tiene que salir de el.
    assert abs(t["predicho_s"] * (1 - q) - t["intervalo_s"][0]) < 0.0001
    assert abs(t["predicho_s"] * (1 + q) - t["intervalo_s"][1]) < 0.0001
    # Y entonces el umbral que la orden congelo es la mitad del que la seccion
    # del lote 7 aplica en palabras: dos documentos, veredictos opuestos.
    c = OCTAVO_ARTE["comparacion"]
    assert c["umbral_q_2"] == round(q / 2, 4)
    assert c["umbral_q_2"] < c["k_B"] < q
    octavo = json.loads(OCTAVO.read_text(encoding="utf-8"))
    k1 = next(p for p in octavo["predictions"] if p["id"] == "K1")
    assert k1["umbral"] == c["umbral_q_2"]
    assert f"stays under {q}".replace(".", ",") in README
    # `publicable` con la regla del lote 7 da lo contrario que K1 sobre el acto.
    assert OCTAVO_ARTE["acto_b"]["publicable"] is True
    assert OCTAVO_ARTE["acto_b"]["jitter_relativo"] < q


def test_las_dos_tablas_del_lote_8_son_las_de_las_lecturas():
    a, b = OCTAVO_ARTE["acto_a"], OCTAVO_ARTE["acto_b"]
    c = OCTAVO_ARTE["comparacion"]
    filas = _tabla_8("| statistic |")
    assert [f[0] for f in filas] == [
        "minimum of 90 readings", "median", "maximum", "worst block jitter",
        "median block jitter", "jitter / predicted", "min / jitter"]
    esperado = [
        [a["minimo_s"], b["minimo_s"], a["minimo_s"] / b["minimo_s"]],
        [a["mediana_s"], b["mediana_s"], a["mediana_s"] / b["mediana_s"]],
        [a["maximo_s"], b["maximo_s"], a["maximo_s"] / b["maximo_s"]],
        [a["jitter_s"], b["jitter_s"], c["ratio_jitter_A_B"]],
        [a["jitter_p50_s"], b["jitter_p50_s"], a["jitter_p50_s"] / b["jitter_p50_s"]],
        [c["k_A"], c["k_B"], c["ratio_k_A_B"]],
        [c["min_A_s"] / a["jitter_s"], c["min_B_s"] / b["jitter_s"],
         (c["min_B_s"] / b["jitter_s"]) / (c["min_A_s"] / a["jitter_s"])],
    ]
    for fila, (izq, der, razon) in zip(filas, esperado):
        assert fila[1] == _coma(izq) and fila[2] == _coma(der), fila
        assert fila[3] == _coma(razon, 2), fila
    bloques = _tabla_8("| block |")
    assert [f[0] for f in bloques] == [str(i) for i in range(1, 10)]
    for fila, bl in zip(bloques, b["bloques"]):
        assert fila[1:] == [_coma(bl["min_s"]), _coma(bl["p50_s"]),
                            _coma(bl["max_s"]), _coma(bl["jitter_s"])], fila
    veredictos = _tabla_8("| id |")
    assert [f[0] for f in veredictos] == ["K1", "K2", "K3"]
    assert [f[3] for f in veredictos] == ["falls", "survives", "falls"]


def test_los_multiplos_de_la_prosa_del_lote_8_se_recomponen():
    """Cada 'veces' de la prosa del lote 8 es un cociente del artefacto, y se ancla
    en su frase: la tabla ya publica los mismos digitos y sola no distingue la prosa."""
    a, b = OCTAVO_ARTE["acto_a"], OCTAVO_ARTE["acto_b"]
    c = OCTAVO_ARTE["comparacion"]
    texto = _prosa_8()
    mj_A, mj_B = c["min_A_s"] / a["jitter_s"], c["min_B_s"] / b["jitter_s"]
    r_min = a["minimo_s"] / b["minimo_s"]
    r_med = a["mediana_s"] / b["mediana_s"]
    r_max = a["maximo_s"] / b["maximo_s"]
    r_jit = c["ratio_jitter_A_B"]
    r_mj = mj_B / mj_A
    for frase in (
            f"it moved by **{_coma(r_min, 2)}×**",                       # 2,10x
            f"minimum {_coma(r_min, 2)}, median {_coma(r_med, 2)}",      # 2,10 y 2,12
            f"the maximum by {_coma(r_max, 2)}",                         # 1,83
            f"moved by {_coma(r_max, 2)} to {_coma(r_jit, 2)} times",    # 1,83 a 2,42
            f"`min / jitter`, {_coma(mj_A)} → {_coma(mj_B)}",
            f"factor of **{_coma(r_mj, 2)}×**",                          # 1,15x
    ):
        assert frase in texto, frase
    # Las dos dispersiones relativas son jitter / mediana, no un promedio.
    assert f"from {_coma(a['jitter_s'] / a['mediana_s'])} to {_coma(b['jitter_s'] / b['mediana_s'])}" in texto
    # La razon de mitades y la dispersion dentro del acto, en su frase.
    assert f"a ratio of {_coma(c['k_ultima_mitad'] / c['k_primera_mitad'], 2)}" in texto
    assert f"is {_coma(c['dispersion_bloques_B'], 2)}× between its mildest" in texto
    assert f"the {_coma(r_jit, 2)}× between acts" in texto
    # Dentro del acto hay la misma dispersion que entre actos: el cociente.
    assert 0.95 <= c["dispersion_bloques_B"] / r_jit <= 1.05
    # Y lo que casi no se mueve es el adimensional, no el segundo.
    assert round(r_mj, 2) < round(c["ratio_min_A_B"], 2) < round(r_jit, 2)


def test_cada_cifra_de_la_prosa_del_lote_8_tiene_lector():
    """Ninguna cifra narrada puede quedar sin lector: se recompone y se busca."""
    a, b, c = OCTAVO_ARTE["acto_a"], OCTAVO_ARTE["acto_b"], OCTAVO_ARTE["comparacion"]
    texto = _prosa_8()
    for cifra in (f"{b['bytes_py']:,}".replace(",", " "),          # los bytes escaneados
                  _coma(b["segundos_de_pared"], 1),                # el reloj de pared
                  str(b["relojes"]),                               # los relojes nuevos
                  _coma(c["k_B"]), _coma(c["k_A"]),                # los dos cocientes
                  _coma(c["umbral_q_2"]), _coma(Q7),               # los dos umbrales
                  _coma(c["ratio_min_B_A"]),                       # K3
                  _coma(c["delta_mitades"]),                       # K2
                  _coma(c["k_primera_mitad"]), _coma(c["k_ultima_mitad"]),
                  _coma(c["min_A_s"] / a["jitter_s"]), _coma(c["min_B_s"] / b["jitter_s"])):
        assert cifra in texto, cifra
    # La aritmetica del defecto se publica con las cifras del lote 6, no con
    # las del lote 8: el intervalo y su semicerco son los del artefacto sellado.
    t = SEXTO["cotizacion"]["tiempo"]
    for cifra in (_coma(t["predicho_s"]), _coma(t["semicerco_relativo"]),
                  _coma(t["intervalo_s"][1])):
        assert cifra in texto, cifra
    assert f"{t['intervalo_s'][0]:.3f}".replace(".", ",") in texto


def test_la_orden_del_lote_9_esta_escrita_antes_de_su_acto():
    noveno = json.loads(NOVENO.read_text(encoding="utf-8"))
    assert noveno["declared_before_computation"] is True
    assert noveno["batch"] == 9
    assert len(noveno["predictions"]) == 3
    for p in noveno["predictions"]:
        assert p["falsifier"].strip() and p["cota_error"].strip(), p["id"]
    assert noveno["cost"]["relojes_nuevos"] == 270
    assert noveno["cost"]["relojes_reutilizados"] == 180
    assert noveno["cost"]["actos"] == 5 and noveno["cost"]["actos_nuevos"] == 3
    assert noveno["cost"]["escrituras_en_platino_labs"] == 0
    assert noveno["cost"]["clones_externos"] == 0
    # El umbral del lote 9 se decide antes de medir: q, no q/2. Y la razon que
    # da es la aritmetica del lote 6, no una preferencia.
    q = SEXTO["banda"]["codigo"]["q"]
    assert _coma(q) in noveno["threshold_decision"]
    assert _coma(round(q / 2, 4)) in noveno["threshold_decision"]
    assert "semicerco relativo" in noveno["threshold_decision"]
    # L1 se declara contra las dos dispersiones del lote 8 y con su falsador.
    l1 = next(p for p in noveno["predictions"] if p["id"] == "L1")
    c = OCTAVO_ARTE["comparacion"]
    assert c["ratio_min_A_B"] >= l1["umbral"]["dispersion_min_min"]      # 2,10 >= 1,80
    assert round(c["min_B_s"] / b"" if False else (c["min_B_s"] / OCTAVO_ARTE["acto_b"]["jitter_s"]) /
               (c["min_A_s"] / OCTAVO_ARTE["acto_a"]["jitter_s"]), 2) <= 1.30


# ---------------------------------------------------------------------------
# Lote 9. Las tres predicciones congeladas en `prediccion-batch-9.json` cayeron:
# el cociente que el lote 8 habia nominado como lo que viaja es lo que peor viaja
# (3,01x contra 2,10x del propio minimo), la ventana tranquila rompe el techo de
# L2 por tres veces, y L3 no se puede decidir con la formula que su `claim`
# declara. Estos tests recomponen los cinco actos desde sus 450 lecturas, sostienen
# los tres veredictos contra la orden, prueban el defecto de L3 por aritmetica con
# los actos del lote 8, y pinean cada celda de las cuatro tablas y cada cifra de
# la prosa. El lote 10 queda pre-registrado en el mismo acto.
NOVENO_ARTE = json.loads((RAIZ / "fuera-de-dominio-9.json").read_text(encoding="utf-8"))
SECCION_9 = "### Nothing travels but the counts"
DECIMO = RAIZ / "prediccion-batch-10.json"


def _seccion_9():
    return README[README.index(SECCION_9):README.index(SECCION_10)]


def _prosa_9():
    return " ".join(_seccion_9().split())


def _tabla_9(encabezado):
    lineas = _seccion_9().splitlines()
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


def _acto_9(nombre):
    return next(a for a in NOVENO_ARTE["actos"] if a["nombre"] == nombre)


def test_el_lote_9_es_un_sujeto_y_cinco_actos_sobre_el_mismo_pin():
    assert NOVENO_ARTE["lote"] == 9
    assert NOVENO_ARTE["prediction"]["sha256"] == _sha(NOVENO)
    assert NOVENO_ARTE["prediction"]["declared_before_computation"] is True
    assert re.fullmatch(r"[0-9a-f]{40}", NOVENO_ARTE["prediction"]["git_blob"])
    assert NOVENO_ARTE["cost"]["relojes_nuevos"] == 270
    assert NOVENO_ARTE["cost"]["relojes_reutilizados"] == 180
    assert NOVENO_ARTE["cost"]["relojes_totales"] == 450
    assert NOVENO_ARTE["cost"]["escrituras_en_platino_labs"] == 0
    assert NOVENO_ARTE["cost"]["clones_externos"] == 0
    actos = NOVENO_ARTE["actos"]
    assert [a["nombre"] for a in actos] == ["A", "B", "C", "D", "E"]
    # El mismo pin en los cinco: el sujeto no se movio mientras se median ventanas.
    assert len({a["sha256"] for a in actos}) == 1
    assert len({a["bytes_py_pin"] for a in actos}) == 1
    assert len({a["predicho_s"] for a in actos}) == 1
    assert len({a["q"] for a in actos}) == 1
    for acto in actos[2:]:
        assert acto["reutilizado"] is False
        assert acto["pin_ok"] is True
        assert acto["bytes_py"] == acto["bytes_py_pin"]
        assert acto["lecturas_n"] == 90
    # A y B no se volvieron a cronometrar: son, lectura a lectura, los del lote 8.
    for nombre, clave in (("A", "acto_a"), ("B", "acto_b")):
        assert _acto_9(nombre)["reutilizado"] is True
        assert [x for b in _acto_9(nombre)["bloques"] for x in b["lecturas"]] == \
               [x for b in OCTAVO_ARTE[clave]["bloques"] for x in b["lecturas"]]
    assert _acto_9("A")["sellado_lote_7"] == OCTAVO_ARTE["acto_a"]["sellado_lote_7"]


def test_los_cinco_actos_del_lote_9_se_recomponen_de_sus_lecturas():
    for acto in NOVENO_ARTE["actos"]:
        assert len(acto["bloques"]) == 9, acto["nombre"]
        assert all(len(b["lecturas"]) == 10 for b in acto["bloques"]), acto["nombre"]
        recomputado = _resumen_8(acto)
        for campo, valor in recomputado.items():
            assert acto[campo] == valor, (acto["nombre"], campo, acto[campo], valor)
        assert acto["relojes"] == acto["lecturas_n"] == 90


def test_los_veredictos_del_lote_9_son_los_que_la_orden_congelo():
    orden = json.loads(NOVENO.read_text(encoding="utf-8"))
    assert [p["id"] for p in orden["predictions"]] == \
           [v["id"] for v in NOVENO_ARTE["veredictos"]] == ["L1", "L2", "L3"]
    c = NOVENO_ARTE["comparacion"]
    # Las dispersiones se rehacen desde los resumenes de los actos, no se heredan.
    minimos = [a["minimo_s"] for a in NOVENO_ARTE["actos"]]
    jitters = [a["jitter_s"] for a in NOVENO_ARTE["actos"]]
    cocientes = [round(a["minimo_s"] / a["jitter_s"], 4) for a in NOVENO_ARTE["actos"]]
    assert c["min_s"] == minimos and c["jitter_s"] == jitters
    assert c["min_sobre_jitter"] == cocientes
    assert c["dispersion"]["min"] == round(max(minimos) / min(minimos), 4) == 2.1019
    assert c["dispersion"]["jitter"] == round(max(jitters) / min(jitters), 4) == 5.2404
    assert c["dispersion"]["min_sobre_jitter"] == round(max(cocientes) / min(cocientes), 4)
    assert c["dispersion"]["k"] == round(max(c["k"]) / min(c["k"]), 4)
    # L1 cae y ademas dispara su propio falsador: la dispersion del cociente pasa
    # de 1,50 cuando la orden pedia 1,30, y el minimo se mueve mas que el umbral.
    l1, l2, l3 = NOVENO_ARTE["veredictos"]
    assert l1["umbral"] == orden["predictions"][0]["umbral"]
    assert c["dispersion"]["min_sobre_jitter"] > 1.30
    assert c["dispersion"]["min"] >= 1.80
    assert l1["sobrevive"] is False and l1["falsador"] is True
    # L2 cae por tres veces su techo: la ventana tranquila no tiene techo.
    assert l2["umbral"] == orden["predictions"][1]["umbral"] == [0.9, 1.4]
    assert all(x > 2.5 for x in cocientes[2:]), cocientes
    assert not all(0.90 <= x <= 1.40 for x in cocientes)
    assert l2["sobrevive"] is False and l2["falsador"] is True
    # L3 se evalua con la formula que su `claim` declara, y cae.
    assert l3["umbral"] == orden["predictions"][2]["umbral"] == [0.8, 1.25]
    assert l3["medido"]["claim"] == c["l3_claim"] == 0.2766
    assert not 0.80 <= c["l3_claim"] <= 1.25
    assert l3["sobrevive"] is False and l3["falsador"] is True
    assert NOVENO_ARTE["predictions_summary"]["caen"] == ["L1", "L2", "L3"]
    assert NOVENO_ARTE["predictions_summary"]["sobreviven"] == []


def test_el_defecto_de_l3_se_prueba_con_la_aritmetica_del_lote_8():
    """`claim` y `cota_error` no evaluan la misma cantidad, y eso se prueba, no se afirma."""
    defecto = NOVENO_ARTE["defectos_de_la_orden"][0]
    assert defecto["id"] == "L3" and defecto["clase"] == "la orden se contradice a si misma"
    # La dispersion interna de jitter del acto B del lote 8, recompuesta de sus bloques.
    jit_b = [round(max(b["lecturas"]) - min(b["lecturas"]), 4)
             for b in OCTAVO_ARTE["acto_b"]["bloques"]]
    disp_jitter_b = round(max(jit_b) / min(jit_b), 4)
    assert disp_jitter_b == defecto["probado_con_el_lote_8"]["dispersion_jitter_del_acto_B"]
    disp_min_8 = round(max(OCTAVO_ARTE["acto_a"]["minimo_s"], OCTAVO_ARTE["acto_b"]["minimo_s"])
                       / min(OCTAVO_ARTE["acto_a"]["minimo_s"],
                             OCTAVO_ARTE["acto_b"]["minimo_s"]), 4)
    assert disp_min_8 == round(defecto["probado_con_el_lote_8"]["dispersion_min"], 4)
    # La `cota_error` es esta razon, y pasa por el rango congelado.
    cota = round(disp_jitter_b / disp_min_8, 4)
    assert cota == defecto["probado_con_el_lote_8"]["cota"] == 1.1797
    assert 0.80 <= cota <= 1.25
    # El `claim`, en cambio, promedia max(jitter de bloque) / min(minimo de bloque)
    # por acto, y no pasa.
    actos_8 = (OCTAVO_ARTE["acto_a"], OCTAVO_ARTE["acto_b"])
    por_acto = [max(max(b["lecturas"]) - min(b["lecturas"]) for b in a["bloques"])
                / min(min(b["lecturas"]) for b in a["bloques"]) for a in actos_8]
    assert [round(x, 4) for x in por_acto] == [1.005, 0.8716]
    claim_8 = round(statistics.mean(por_acto) / disp_min_8, 4)
    assert claim_8 == defecto["probado_con_el_lote_8"]["claim"] == 0.4464
    assert not 0.80 <= claim_8 <= 1.25
    # Dos numeros distintos para la misma prediccion: la orden se contradice a si misma.
    assert abs(cota - claim_8) > 0.70
    # Y el lote 9 se evalua con el `claim`, que es lo que el rango congela; el otro
    # numero se publica como cifra descriptiva y no como veredicto.
    assert NOVENO_ARTE["comparacion"]["l3_claim"] == defecto["medido_ahora"]["claim"]
    assert NOVENO_ARTE["comparacion"]["l3_cota_media"] == defecto["medido_ahora"]["cota_media"]
    dentro = NOVENO_ARTE["comparacion"]["dentro"]
    media_dentro = statistics.mean(d["dispersion_jitter_de_bloque"] for d in dentro)
    assert round(media_dentro / NOVENO_ARTE["comparacion"]["dispersion"]["min"], 4) == 1.6992
    assert NOVENO_ARTE["veredictos"][2]["medido"]["cota_media"] == 1.6992
    assert "se declara" in defecto["que_se_hace"]


def test_las_cuatro_tablas_del_lote_9_son_las_de_las_lecturas():
    actos = NOVENO_ARTE["actos"]
    c = NOVENO_ARTE["comparacion"]
    filas = _tabla_9("| act | minimum |")
    assert len(filas) == 5
    for i, (fila, acto) in enumerate(zip(filas, actos)):
        assert fila == [
            acto["nombre"],
            _coma(acto["minimo_s"]), _coma(acto["mediana_s"]), _coma(acto["jitter_s"]),
            _coma(c["min_sobre_jitter"][i]), _coma(c["k"][i]),
            "yes" if acto["publicable"] else "no",
        ], (acto["nombre"], fila)

    disp = c["dispersion"]
    filas = _tabla_9("| quantity |")
    assert filas == [
        ["minimum", _coma(disp["min"], 2)],
        ["worst block jitter", _coma(disp["jitter"], 2)],
        ["min / jitter", _coma(disp["min_sobre_jitter"], 2)],
        ["k", _coma(disp["k"], 2)],
    ]

    filas = _tabla_9("| id |")
    assert filas == [
        ["L1", "min / jitter dispersion \u2264 1,30 and min dispersion \u2265 1,80",
         f"{_coma(disp['min_sobre_jitter'], 2)} and {_coma(disp['min'], 2)}", "falls"],
        ["L2", "min / jitter in [0,90; 1,40] in all five acts",
         f"{_coma(min(c['min_sobre_jitter']))} to {_coma(max(c['min_sobre_jitter']))}", "falls"],
        ["L3", "within-act over between-act ratio in [0,80; 1,25]",
         _coma(c["l3_claim"]), "falls"],
    ]

    costes = NOVENO_ARTE["cost"]["coste_compuerta_s"]
    filas = _tabla_9("| act | gate wall |")
    assert len(filas) == len(costes) == 3
    for fila, acto, coste in zip(filas, actos[2:], costes):
        assert fila == [
            acto["nombre"],
            f"{_coma(coste, 1)} s",
            f"{_coma(coste / 90, 1)} s",
            str(round(coste / acto["minimo_s"])),
        ], (acto["nombre"], fila)


def test_el_coste_de_la_compuerta_se_mide_y_se_publica():
    """El punto ciego de A0.12: el corpus medía el ruido del entorno, no lo que cuesta medirlo."""
    from datetime import datetime

    cost = NOVENO_ARTE["cost"]
    costes = cost["coste_compuerta_s"]
    assert len(costes) == 3 and all(x > 0 for x in costes)
    # El mismo numero viaja dos veces: el resumen y el acto que lo pago. Dos copias
    # de una cifra divergen si nadie las compara, y aqui las compara un lector.
    assert costes == [a["coste_compuerta_s"] for a in NOVENO_ARTE["actos"][2:]]
    for acto, coste in zip(NOVENO_ARTE["actos"][2:], costes):
        desde = datetime.fromisoformat(acto["ventana"]["inicio"])
        hasta = datetime.fromisoformat(acto["ventana"]["fin"])
        # La ventana declarada y el reloj de pared de la compuerta son la misma cosa.
        assert abs((hasta - desde).total_seconds() - coste) < 1.0, (acto["nombre"], coste)
    assert cost["coste_compuerta_total_s"] == round(sum(costes), 1) == 451.3
    assert cost["coste_por_reloj_s"] == round(sum(costes) / 270, 4) == 1.6714
    # La compuerta cuesta cientos de los escaneos mas baratos que calibra, y ese
    # precio tambien es lectura del acto: cae 1,91x dentro de una sola sesion.
    for acto, coste in zip(NOVENO_ARTE["actos"][2:], costes):
        razon = coste / acto["minimo_s"]
        assert 380 <= round(razon) <= 698, (acto["nombre"], razon)
    assert round(max(costes) / min(costes), 4) == round(209.5298 / 109.6219, 4)
    assert round((costes[0] / 90) / (costes[2] / 90), 2) == 1.91
    assert cost["medido_en"] == _acto_9("E")["ventana"]["fin"]
    # L3 moriria tambien con la otra formula: la dispersion dentro del acto no es
    # del tamano de la de entre actos, la mide o no la mide.
    assert NOVENO_ARTE["metodo"].count("coste_compuerta_s") == 1


def test_cada_cifra_de_la_prosa_del_lote_9_tiene_lector():
    prosa = _prosa_9()
    actos = NOVENO_ARTE["actos"]
    c = NOVENO_ARTE["comparacion"]
    a, b = actos[0], actos[1]
    cociente_8 = (b["minimo_s"] / b["jitter_s"]) / (a["minimo_s"] / a["jitter_s"])
    costes = NOVENO_ARTE["cost"]["coste_compuerta_s"]
    razones = [round(coste / acto["minimo_s"]) for coste, acto in zip(costes, actos[2:])]
    dentro_k = [x for x in c["k"][2:]]
    anclas = [
        # El cociente del lote 8, que es lo que este lote falsa.
        f"{_coma(cociente_8, 2)}\u00d7 against {_coma(c['dispersion']['min'], 2)}\u00d7 "
        f"for the minimum",
        # L1: cayo contra su propio falsador, por el doble.
        f"It measured {_coma(c['dispersion']['min_sobre_jitter'], 2)} \u2014 twice the falsifier "
        f"\u2014 while the minimum moved {_coma(c['dispersion']['min'], 2)}",
        # El jitter solo se mueve 5,24x, y el cociente hereda ese movimiento.
        f"`jitter` alone moves {_coma(c['dispersion']['jitter'], 2)}\u00d7",
        f"{_coma(a['jitter_s'], 4)} to {_coma(min(x['jitter_s'] for x in actos), 4)} is "
        f"{_coma(c['dispersion']['jitter'], 2)}\u00d7",
        f"the minimum only falls {_coma(c['dispersion']['min'], 2)}\u00d7",
        # L2: la ventana tranquila rompe el techo por tres veces.
        f"{_coma(actos[2]['minimo_s'] / actos[2]['jitter_s'], 4)}, "
        f"{_coma(actos[3]['minimo_s'] / actos[3]['jitter_s'], 4)} and "
        f"{_coma(actos[4]['minimo_s'] / actos[4]['jitter_s'], 4)} against a ceiling of 1,40",
        # La sesion: 1,15x dentro, 5,24x entre, y 4,54x de diferencia.
        f"`k` at {_coma(dentro_k[0], 4)}, {_coma(dentro_k[1], 4)} and {_coma(dentro_k[2], 4)}",
        f"a dispersion of {_coma(max(dentro_k) / min(dentro_k), 2)}\u00d7 between the three "
        f"against {_coma(c['dispersion']['k'], 2)}\u00d7 across the five",
        f"the quotient moves {_coma(c['dispersion']['k'] / (max(dentro_k) / min(dentro_k)), 1)}\u00d7 less",
        # El booleano sobrevive y esconde 2,16x de diferencia en el piso.
        f"{_coma(b['jitter_s'], 4)} s in act B against "
        f"{_coma(actos[4]['jitter_s'], 4)} s in act E",
        f"hides a {_coma(b['jitter_s'] / actos[4]['jitter_s'], 2)}\u00d7 change",
        # Coste de la compuerta.
        f"{_coma(NOVENO_ARTE['cost']['coste_compuerta_total_s'], 1)} s of wall bought the 270 new clocks",
        f"between {min(razones)} and {max(razones)} of the cheapest scans",
        f"from {_coma(costes[0] / 90, 1)} s to {_coma(costes[2] / 90, 1)} s across one session, "
        f"{_coma(costes[0] / costes[2], 2)}\u00d7 on a constant workload",
        f"{round(min(costes))} to {round(max(costes))} s for the certificate",
        # El defecto de L3, con sus dos numeros.
        f"gives {_coma(0.4464)} and the second {_coma(1.1797)}",
        f"{_coma(2.4797)} / {_coma(2.1019)}",
        f"freezes: {_coma(c['l3_claim'])}",
        f"`l3_cota_media`, {_coma(c['l3_cota_media'])}",
        # Y lo que si viaja: conteos.
        "Counts travel",
    ]
    for ancla in anclas:
        assert ancla in prosa, ancla
    # El bloque de comando y el nombre del artefacto tienen que estar en la seccion.
    assert "bench/ventana.py --dir /tmp/censo9 --artefacto" in prosa
    assert "fuera-de-dominio-9.json" in prosa
    assert "prediccion-batch-10.json" in prosa


def test_la_seccion_del_lote_9_va_despues_de_la_del_lote_8_y_antes_del_censo():
    assert README.index(SECCION_8) < README.index(SECCION_9)
    assert README.index(SECCION_9) < README.index("## Fixtures census, recomputed")


def test_la_orden_del_lote_10_esta_escrita_antes_de_su_acto():
    orden = json.loads(DECIMO.read_text(encoding="utf-8"))
    assert orden["batch"] == 10
    assert orden["declared_before_computation"] is True
    assert [p["id"] for p in orden["predictions"]] == ["M1", "M2", "M3"]
    for p in orden["predictions"]:
        assert p["falsifier"] and p["cota_error"] and p["claim"]
    # M1 nombra las dos dispersiones que el lote 9 dejo medidas y no concluidas:
    # dentro de la sesion C-D-E, y entre los cinco actos.
    dentro = [a["jitter_s"] / a["predicho_s"] for a in NOVENO_ARTE["actos"][2:]]
    m1 = orden["predictions"][0]
    assert m1["umbral"]["dispersion_k_dentro_max"] == 1.30
    assert max(dentro) / min(dentro) <= m1["umbral"]["dispersion_k_dentro_max"]
    assert m1["umbral"]["dispersion_k_entre_sesiones_min"] == 3.00
    assert NOVENO_ARTE["comparacion"]["dispersion"]["k"] >= 3.00
    # M2 se mide con una sonda anidada: nueve relojes repartidos no cuestan relojes
    # nuevos en el papel, pero si exigen que cada bloque guarde su primera lectura.
    m2 = orden["predictions"][1]
    assert m2["umbral"]["sobrestimacion_max"] == 1.15
    assert "primera lectura en orden" in orden["method"]["actos_nuevos"]
    # M3 cotiza la compuerta desde el acto; el lote 9 da el rango que la orden usa.
    m3 = orden["predictions"][2]
    p50 = [statistics.median(x for b in a["bloques"] for x in b["lecturas"]) for a in NOVENO_ARTE["actos"][2:]]
    razones = [costes / 90 / mediana
               for costes, mediana in zip(NOVENO_ARTE["cost"]["coste_compuerta_s"], p50)]
    assert m3["umbral"] == [3.0, 6.5]
    assert all(m3["umbral"][0] <= r <= m3["umbral"][1] for r in razones), razones
    assert orden["cost"]["relojes_nuevos"] == 270
    assert orden["cost"]["relojes_reutilizados"] == 450
    assert orden["cost"]["escrituras_en_platino_labs"] == 0


# ---------------------------------------------------------------------------
# Lote 10. La orden congelada en `prediccion-batch-10.json` pidio tres cosas y el
# lote devolvio una que no estaba decidida: M1 cae entre su umbral (3,00) y su
# falsador (2,00), asi que se publica como no decidida y el hueco queda declarado.
# M2 y M3 sobreviven. Estos tests recomponen los ocho actos desde sus 720 lecturas,
# sostienen cada veredicto contra la orden, prueban que los cinco actos reutilizados
# no se vuelven a cronometrar, comprueban la factorizacion exacta de la dispersion y
# pinean cada celda de las cuatro tablas y cada cifra de la prosa.
DECIMO_ARTE = json.loads((RAIZ / "fuera-de-dominio-10.json").read_text(encoding="utf-8"))
SECCION_10 = "### The session is the regime"
PIN_10 = "b2e05e6bac8e49b67be2a6ffa63422c60f7193fc72e8180255907b41ec997dc1"


def _seccion_10():
    return README[README.index(SECCION_10):README.index("## Fixtures census, recomputed")]


def _prosa_10():
    return " ".join(_seccion_10().split())


def _tabla_10(encabezado):
    lineas = _seccion_10().splitlines()
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


def _acto_10(nombre):
    return next(a for a in DECIMO_ARTE["actos"] if a["nombre"] == nombre)


def _k_por_sesion():
    return ([a["jitter_relativo"] for a in DECIMO_ARTE["actos"][2:5]],
            [a["jitter_relativo"] for a in DECIMO_ARTE["actos"][5:]])


def test_el_lote_10_es_un_sujeto_y_ocho_actos_sobre_el_mismo_pin():
    assert DECIMO_ARTE["lote"] == 10
    assert DECIMO_ARTE["prediction"]["archivo"] == "prediccion-batch-10.json"
    assert DECIMO_ARTE["prediction"]["sha256"] == _sha(DECIMO)
    assert DECIMO_ARTE["prediction"]["declared_before_computation"] is True
    assert re.fullmatch(r"[0-9a-f]{40}", DECIMO_ARTE["prediction"]["git_blob"])
    assert [a["nombre"] for a in DECIMO_ARTE["actos"]] == list("ABCDEFGH")
    assert {a["sha256"] for a in DECIMO_ARTE["actos"]} == {PIN_10}
    assert {a["bytes_py_pin"] for a in DECIMO_ARTE["actos"]} == {296870}
    assert {a["relojes"] for a in DECIMO_ARTE["actos"]} == {90}
    assert all(len(a["bloques"]) == 9 for a in DECIMO_ARTE["actos"])
    cost = DECIMO_ARTE["cost"]
    assert cost["sujetos"] == 1 and cost["actos"] == 8
    assert cost["actos_nuevos"] == 3 and cost["actos_reutilizados"] == 5
    assert cost["relojes_nuevos"] == 270
    assert cost["relojes_reutilizados"] == 450
    assert cost["relojes_totales"] == 720
    assert cost["escrituras_en_platino_labs"] == 0
    assert cost["clones_externos"] == 0


def test_los_tres_actos_nuevos_son_una_sola_sesion_encadenada():
    f, g, h = (_acto_10(n) for n in "FGH")
    assert f["ventana"]["fin"] == g["ventana"]["inicio"]
    assert g["ventana"]["fin"] == h["ventana"]["inicio"]
    assert f["ventana"]["fin"] < DECIMO_ARTE["cost"]["medido_en"]
    # Los reutilizados conservan la ventana de su artefacto de origen; A y B no la declaran.
    for nombre in "CDE":
        assert _acto_10(nombre)["ventana"]["fin"] < f["ventana"]["inicio"]
    assert _acto_10("A")["ventana"] is None and _acto_10("B")["ventana"] is None


def test_los_cinco_actos_reutilizados_se_releen_sin_volver_a_cronometrar():
    octavo = json.loads((RAIZ / "fuera-de-dominio-8.json").read_text(encoding="utf-8"))
    origen = {"A": octavo["acto_a"], "B": octavo["acto_b"],
              "C": NOVENO_ARTE["actos"][2], "D": NOVENO_ARTE["actos"][3],
              "E": NOVENO_ARTE["actos"][4]}
    for nombre, fuente in origen.items():
        acto = _acto_10(nombre)
        assert acto["reutilizado"] is True
        assert acto["fuente"] != "acto propio del lote 10"
        assert [b["lecturas"] for b in acto["bloques"]] == [b["lecturas"] for b in fuente["bloques"]]
        assert acto["ventana"] == fuente.get("ventana")
    for nombre in "FGH":
        acto = _acto_10(nombre)
        assert acto["reutilizado"] is False
        assert acto["fuente"] == "acto propio del lote 10"
    # Los reutilizados no traen coste de compuerta propio del lote 10: no se re-cronometraron.
    assert DECIMO_ARTE["cost"]["coste_compuerta_s"] == [
        _acto_10(n)["coste_compuerta_s"] for n in "FGH"]


def test_cada_bloque_nuevo_guarda_su_primera_lectura_en_orden_cronologico():
    for nombre in "FGH":
        bloques = _acto_10(nombre)["bloques"]
        assert sum(b["n"] for b in bloques) == 90
        for bloque in bloques:
            assert bloque["primera_s"] in bloque["lecturas"]
            assert bloque["min_s"] <= bloque["primera_s"] <= bloque["max_s"]
        # Una lectura por bloque, nueve en total: eso es la sonda de nueve relojes.
        assert len({b["primera_s"] for b in bloques}) == 9
    # Los artefactos viejos no se reescriben: sus bloques no llevan primera_s.
    for nombre in "ABCDE":
        assert not any("primera_s" in b for b in _acto_10(nombre)["bloques"])


def test_la_sonda_de_nueve_relojes_se_recompone_desde_los_bloques():
    for nombre in "FGH":
        acto = _acto_10(nombre)
        primeras = [b["primera_s"] for b in acto["bloques"]]
        assert acto["sonda"]["lecturas"] == primeras
        assert acto["sonda"]["n"] == 9
        assert acto["sonda"]["sonda_min_s"] == min(primeras)
        assert acto["sonda"]["sonda_max_s"] == max(primeras)
        assert round(max(primeras) - min(primeras), 4) == acto["sonda"]["sonda_jitter_s"]
        # La sonda es un subconjunto de las noventa: solo puede sobrestimar el minimo.
        assert acto["minimo_s"] <= acto["sonda"]["sonda_min_s"]
        assert round(acto["sonda"]["sonda_min_s"] / acto["minimo_s"], 4) == acto["sonda_sobre_min"]
        # Y el arranque en frio se lee aparte: el piso de la sonda contra la primera lectura del
        # acto. Por debajo de 1, esa primera lectura fue mas lenta que el piso.
        assert round(min(primeras) / primeras[0], 4) == acto["arranque_sobre_sonda"]


def test_m2_sobrevive_en_los_tres_actos_nuevos():
    son = {x["acto"]: x for x in DECIMO_ARTE["comparacion"]["sonda"]}
    m2 = DECIMO_ARTE["veredictos"][1]
    assert m2["id"] == "M2"
    assert m2["umbral"]["sobrestimacion_max"] == 1.15
    assert m2["umbral"]["sonda_jitter_sobre_jitter_min"] == 0.50
    assert [son[n]["sonda_sobre_min"] for n in "FGH"] == [1.0268, 1.0507, 1.0]
    assert [son[n]["sonda_jitter_sobre_jitter"] for n in "FGH"] == [0.6266, 1.5071, 0.7518]
    assert all(x["sonda_sobre_min"] <= 1.15 for x in son.values())
    assert all(x["sonda_jitter_sobre_jitter"] >= 0.50 for x in son.values())
    assert m2["sobrevive"] is True and m2["falsador"] is False
    # Acierta el piso y no la banda: en F la sonda ve menos jitter que el acto, en G mas.
    assert son["F"]["sonda_jitter_sobre_jitter"] < 1.0 < son["G"]["sonda_jitter_sobre_jitter"]


def test_m3_cotiza_la_compuerta_y_separa_el_arnes_del_sujeto():
    cos = {x["acto"]: x for x in DECIMO_ARTE["comparacion"]["coste"]}
    m3 = DECIMO_ARTE["veredictos"][2]
    assert m3["id"] == "M3" and m3["umbral"] == [3.0, 6.5]
    assert [cos[n]["coste_sobre_trabajo"] for n in "FGH"] == [3.8493, 4.1044, 3.474]
    for nombre in "FGH":
        fila = cos[nombre]
        assert m3["umbral"][0] <= fila["coste_sobre_trabajo"] <= m3["umbral"][1]
        assert fila["trabajo_s"] == round(90 * _acto_10(nombre)["mediana_s"], 3)
        assert fila["coste_arnes_s"] == round(fila["coste_compuerta_s"] - fila["trabajo_s"], 4)
        assert fila["coste_compuerta_s"] == _acto_10(nombre)["coste_compuerta_s"]
        # Entre 71 % y 76 % de la compuerta es arnes: el recargo es del instrumento.
        assert round(fila["coste_arnes_s"] / fila["coste_compuerta_s"], 2) in (0.74, 0.76, 0.71)
    assert m3["sobrevive"] is True and m3["falsador"] is False
    cost = DECIMO_ARTE["cost"]
    assert cost["coste_compuerta_total_s"] == 468.1
    assert cost["coste_arnes_total_s"] == 345.9601
    assert round(sum(cos[n]["trabajo_s"] for n in "FGH"), 3) == 122.157


def test_m1_no_sobrevive_ni_dispara_su_falsador_y_el_hueco_se_declara():
    m1 = DECIMO_ARTE["veredictos"][0]
    assert m1["id"] == "M1"
    assert m1["umbral"]["dispersion_k_dentro_max"] == 1.30
    assert m1["umbral"]["dispersion_k_entre_sesiones_min"] == 3.00
    medido = m1["medido"]
    assert medido["dispersion_k_lote_9"] == 1.1532
    assert medido["dispersion_k_dentro_lote_10"] == 1.1426
    assert medido["dispersion_k_entre_sesiones"] == 2.6414
    assert m1["sobrevive"] is False
    assert m1["falsador"] is False
    assert m1["zona_muerta"] is True
    # 2,6414 cae dentro del intervalo que la orden no decidio: ni 3,00 ni 2,00.
    assert 2.00 < medido["dispersion_k_entre_sesiones"] < 3.00
    resumen = DECIMO_ARTE["predictions_summary"]
    assert resumen["caen"] == ["M1"]
    assert resumen["sobreviven"] == ["M2", "M3"]
    assert resumen["zona_muerta"] == ["M1"]
    defecto = DECIMO_ARTE["defectos_de_la_orden"][0]
    assert defecto["id"] == "M1"
    assert defecto["umbral_entre_sesiones"] == 3.00
    assert defecto["falsador_entre_sesiones"] == 2.00
    assert defecto["medido"]["dispersion_k_entre_sesiones"] == 2.6414
    # Las dos sesiones coinciden a 1,01x: la dispersion interna no es del dia.
    assert round(medido["dispersion_k_lote_9"] / medido["dispersion_k_dentro_lote_10"], 2) == 1.01


def test_la_dispersion_se_factoriza_sin_residuo_y_el_factor_grande_es_la_sesion():
    k9, k10 = _k_por_sesion()
    ses = DECIMO_ARTE["comparacion"]["sesiones"]
    des = DECIMO_ARTE["comparacion"]["descomposicion"]
    assert round(max(k10) / min(k9), 4) == des["total_sobre_las_dos_sesiones"] == 3.2545
    assert des["producto"] == 3.2545
    assert round(des["entre_sesiones"] * des["posicion_dentro_de_lote_9"]
                 * des["posicion_dentro_de_lote_10"], 4) == 3.2545
    # Cada factor sale de los actos, no de una constante copiada.
    assert round(ses["lote_10"]["mediana_k"] / ses["lote_9"]["mediana_k"], 4) == des["entre_sesiones"]
    assert round(ses["lote_9"]["mediana_k"] / min(k9), 4) == des["posicion_dentro_de_lote_9"]
    assert round(max(k10) / ses["lote_10"]["mediana_k"], 4) == des["posicion_dentro_de_lote_10"]
    assert round(max(k9) / min(k9), 4) == ses["lote_9"]["dispersion_k"] == 1.1532
    assert round(max(k10) / min(k10), 4) == ses["lote_10"]["dispersion_k"] == 1.1426
    # Lo que la sesion explica es el factor grande; la posicion dentro de la sesion, el chico.
    assert round(des["posicion_dentro_de_lote_9"] * des["posicion_dentro_de_lote_10"], 4) == 1.2321
    assert des["entre_sesiones"] > des["posicion_dentro_de_lote_9"] * des["posicion_dentro_de_lote_10"]


def test_publicable_se_invierte_con_la_sesion_y_no_con_el_sujeto():
    p = DECIMO_ARTE["predictions_summary"]["publicable_por_acto"]
    assert p == {"A": False, "B": True, "C": True, "D": True,
                 "E": True, "F": False, "G": False, "H": False}
    assert sum(p.values()) == 4
    for acto in DECIMO_ARTE["actos"]:
        assert acto["publicable"] == (acto["jitter_s"] < acto["predicho_s"] * acto["q"])
        assert acto["q"] == 0.3018
    # Mismo pin, mismo protocolo: el booleano no distingue el sujeto, distingue la ventana.
    assert {a["sha256"] for a in DECIMO_ARTE["actos"]} == {PIN_10}
    assert {p["A"], p["B"], p["C"], p["D"], p["E"], p["F"], p["G"], p["H"]} == {True, False}


def test_las_cuatro_tablas_del_lote_10_cuentan_lo_que_el_artefacto_mide():
    filas = _tabla_10("| act | session |")
    assert [f[0] for f in filas] == list("ABCDEFGH")
    assert [f[1] for f in filas] == ["own", "own", "1", "1", "1", "2", "2", "2"]
    for fila in filas:
        acto = _acto_10(fila[0])
        assert fila[2] == _coma(acto["jitter_relativo"])
        assert fila[3] == ("yes" if acto["publicable"] else "no")

    filas = _tabla_10("| id | pre-registered threshold |")
    assert [f[0] for f in filas] == ["M1", "M2", "M3"]
    assert [f[3] for f in filas] == ["not decided", "holds", "holds"]
    assert "1,1426 and 2,6414" in filas[0][2]
    assert "1,0000 to 1,0507" in filas[1][2] and "0,6266 to 1,5071" in filas[1][2]
    assert "3,4740 to 4,1044" in filas[2][2]

    son = {x["acto"]: x for x in DECIMO_ARTE["comparacion"]["sonda"]}
    filas = _tabla_10("| act | nine-clock minimum |")
    assert [f[0] for f in filas] == ["F", "G", "H"]
    for fila in filas:
        x = son[fila[0]]
        assert fila[1] == _coma(x["sonda_min_s"])
        assert fila[2] == _coma(x["min_s"])
        assert fila[3] == _coma(x["sonda_sobre_min"])
        assert fila[4] == _coma(x["sonda_jitter_s"])
        assert fila[5] == _coma(x["jitter_s"])
        assert fila[6] == _coma(x["sonda_jitter_sobre_jitter"])

    cos = {x["acto"]: x for x in DECIMO_ARTE["comparacion"]["coste"]}
    filas = _tabla_10("| act | gate wall |")
    assert [f[0] for f in filas] == ["F", "G", "H"]
    for fila in filas:
        x = cos[fila[0]]
        assert fila[1] == f"{_coma(x['coste_compuerta_s'], 1)} s"
        assert fila[2] == f"{_coma(x['trabajo_s'], 1)} s"
        assert fila[3] == f"{_coma(x['coste_arnes_s'], 1)} s"
        assert fila[4] == _coma(x["coste_sobre_trabajo"])


def test_cada_cifra_de_la_prosa_del_lote_10_tiene_lector():
    prosa = _prosa_10()
    actos = DECIMO_ARTE["actos"]
    c = DECIMO_ARTE["comparacion"]
    k9, k10 = _k_por_sesion()
    son = {x["acto"]: x for x in c["sonda"]}
    cos = {x["acto"]: x for x in c["coste"]}
    cost = DECIMO_ARTE["cost"]
    minimo_nuevos = [a["minimo_s"] for a in actos[5:]]
    jitter_nuevos = [a["jitter_s"] for a in actos[5:]]
    anclas = [
        # El booleano se invierte con la misma madera: cuatro si, cuatro no.
        "**The same tree, the same hash, the same protocol: four acts are publishable and four are not.**",
        f"Acts C, D and E sit at `k` {_coma(k9[0])}, {_coma(k9[1])} and {_coma(k9[2])} against "
        f"`q` = {_coma(actos[2]['q'])}; acts F, G and H sit at {_coma(k10[0])}, {_coma(k10[1])} "
        f"and {_coma(k10[2])}",
        # Dentro de la sesion el acto apenas se mueve; entre sesiones si el regimen.
        f"the minimum moves {_coma(max(minimo_nuevos) / min(minimo_nuevos), 2)}\u00d7 and the worst "
        f"block jitter {_coma(max(jitter_nuevos) / min(jitter_nuevos), 2)}\u00d7",
        f"moves {_coma(c['dispersion_k_entre_sesiones'], 4)}\u00d7, and the two within-session "
        f"dispersions \u2014 {_coma(c['sesiones']['lote_9']['dispersion_k'])} in session 1 and "
        f"{_coma(c['sesiones']['lote_10']['dispersion_k'])} in session 2 \u2014 agree with each "
        f"other to {_coma(c['sesiones']['lote_9']['dispersion_k'] / c['sesiones']['lote_10']['dispersion_k'], 2)}\u00d7",
        # La factorizacion, escrita como se lee.
        f"{_coma(c['descomposicion']['total_sobre_las_dos_sesiones'])} = "
        f"{_coma(c['descomposicion']['entre_sesiones'])} \u00d7 "
        f"{_coma(c['descomposicion']['posicion_dentro_de_lote_9'])} \u00d7 "
        f"{_coma(c['descomposicion']['posicion_dentro_de_lote_10'])}",
        f"session medians is {_coma(c['descomposicion']['entre_sesiones'])}\u00d7 and the position of an "
        f"act inside its own session adds {_coma(c['descomposicion']['posicion_dentro_de_lote_9'] * c['descomposicion']['posicion_dentro_de_lote_10'])}",
        # M1: la zona muerta, con los dos bordes.
        f"It measured {_coma(c['dispersion_k_entre_sesiones'])} \u2014 below the threshold and above "
        f"the falsifier",
        # La palabra del veredicto sale de la zona muerta del artefacto, no del teclado.
        f"M1 is published as **{'not decided' if DECIMO_ARTE['predictions_summary']['zona_muerta'] else 'decided'}**",
        # Y el "a lo sumo" de la prosa es el mayor de los tres porcentajes de la tabla.
        f"was how much, and the answer is at most "
        f"{_coma(max((son[k]['sonda_sobre_min'] - 1) * 100 for k in 'FGH'), 2)} %",
        # El arranque en frio: la primera lectura de H contra el piso que dan las nueve.
        f"the first clock of act H took {_coma(_acto_10('H')['bloques'][0]['primera_s'])} s, "
        f"{_coma(_acto_10('H')['bloques'][0]['primera_s'] / _acto_10('H')['sonda']['sonda_min_s'], 2)}\u00d7 "
        f"the floor the nine later ones found",
        # M2: cuanto sobrestima y cuanto se le escapa la banda.
        f"overstates the minimum of ninety by "
        f"{_coma((son['F']['sonda_sobre_min'] - 1) * 100, 2)} %, "
        f"{_coma((son['G']['sonda_sobre_min'] - 1) * 100, 2)} % and "
        f"{_coma((son['H']['sonda_sobre_min'] - 1) * 100, 2)} %",
        f"Its jitter is a different story: {_coma(son['F']['sonda_jitter_sobre_jitter'], 2)}\u00d7, "
        f"{_coma(son['G']['sonda_jitter_sobre_jitter'], 2)}\u00d7 and "
        f"{_coma(son['H']['sonda_jitter_sobre_jitter'], 2)}\u00d7 of the act's worst block",
        # El precio de la sonda, que es aritmetica y no medida.
        f"ninety clocks took {_coma(cos['F']['coste_compuerta_s'] / 90, 2)} s per clock in F, "
        f"{_coma(cos['G']['coste_compuerta_s'] / 90, 2)} s in G and "
        f"{_coma(cos['H']['coste_compuerta_s'] / 90, 2)} s in H",
        f"so nine should cost {round(9 * cos['F']['coste_compuerta_s'] / 90)} to "
        f"{round(9 * cos['G']['coste_compuerta_s'] / 90)} s instead of "
        f"{round(cos['H']['coste_compuerta_s'])} to {round(cos['G']['coste_compuerta_s'])}",
        # M3: el arnes es la mayor parte de la compuerta.
        f"{_coma(min(x['coste_arnes_s'] / x['coste_compuerta_s'] for x in cos.values()) * 100, 1)} % to "
        f"{_coma(max(x['coste_arnes_s'] / x['coste_compuerta_s'] for x in cos.values()) * 100, 1)} % "
        f"of a gate is the harness",
        f"the split is {_coma(cost['coste_arnes_total_s'], 1)} s of harness against "
        f"{_coma(sum(x['trabajo_s'] for x in cos.values()), 1)} s of work",
        f"the certificate costs {_coma(min(x['coste_sobre_trabajo'] for x in cos.values()), 1)}\u00d7 "
        f"to {_coma(max(x['coste_sobre_trabajo'] for x in cos.values()), 1)}\u00d7 the work",
        # El contrato que el lote propone, con sus cuatro campos.
        "`(k, threshold, within-session dispersion, cost)`",
    ]
    for ancla in anclas:
        assert ancla in prosa, ancla
    assert "bench/sonda.py --dir /tmp/censo10 --artefacto" in prosa
    assert "fuera-de-dominio-10.json" in prosa
    assert "prediccion-batch-11.json" in prosa


def test_la_seccion_del_lote_10_va_despues_de_la_del_9_y_antes_del_censo():
    assert README.index(SECCION_9) < README.index(SECCION_10)
    assert README.index(SECCION_10) < README.index("## Fixtures census, recomputed")
    # Y la seccion del lote 9 ya no se lleva por delante el texto del lote 10.
    assert "fuera-de-dominio-10.json" not in _seccion_9()
    assert SECCION_10 not in _seccion_9()


# ---------------------------------------------------------------------------
# El instrumento, ejercitado con bloques sinteticos.
#
# Hasta el lote 9 la suite solo leia artefactos: un mutante de `bench/*.py` era
# equivalente para el banco porque ningun test importaba el codigo que produce las
# cifras. Estos cuatro tests cargan `bench/sonda.py` y lo falsan con entradas que no
# salen del artefacto, asi que un mutante del instrumento muere aqui.
sys.path.insert(0, str(RAIZ / "bench"))
import sonda  # noqa: E402


def test_la_sonda_toma_la_primera_lectura_de_cada_bloque_y_solo_esa():
    bloques = [{"lecturas": [9.0, 1.0, 2.0], "primera_s": 9.0},
               {"lecturas": [3.0, 0.5, 4.0], "primera_s": 3.0},
               {"lecturas": [0.1, 7.0], "primera_s": 7.0}]
    s = sonda._sonda(bloques)
    assert s["lecturas"] == [9.0, 3.0, 7.0]
    assert s["n"] == 3
    # 0,1 y 0,5 estan en las crudas pero no son la primera lectura de su bloque:
    # la sonda no las ve, y por eso solo puede sobrestimar el minimo.
    assert s["sonda_min_s"] == 3.0
    assert s["sonda_max_s"] == 9.0
    assert s["sonda_jitter_s"] == 6.0


def test_la_cotizacion_resta_el_trabajo_del_coste_y_no_al_reves():
    acto = {"relojes": 90, "mediana_s": 0.5, "minimo_s": 0.4, "jitter_s": 0.2,
            "sonda": {"sonda_min_s": 0.42, "sonda_jitter_s": 0.1},
            "bloques": [{"primera_s": 0.6}, {"primera_s": 0.42}],
            "coste_compuerta_s": 200.0}
    c = sonda._cotizacion(acto)
    assert c["trabajo_s"] == 45.0
    assert c["coste_arnes_s"] == 155.0
    assert c["coste_sobre_trabajo"] == round(200 / 45, 4)
    assert c["sonda_sobre_min"] == 1.05
    assert c["sonda_jitter_sobre_jitter"] == 0.5
    # El arranque se lee contra la primera lectura del acto, no contra la del ultimo bloque.
    assert c["arranque_sobre_sonda"] == round(0.42 / 0.6, 4)
    # Sin coste medido no se inventa arnes: el campo no existe.
    sin = sonda._cotizacion({**acto, "coste_compuerta_s": None})
    assert "coste_arnes_s" not in sin and "coste_sobre_trabajo" not in sin


def test_los_veredictos_distinguen_zona_muerta_de_falsador():
    pred = {"predictions": [
        {"claim": "m1", "umbral": {"dispersion_k_dentro_max": 1.30,
                                   "dispersion_k_entre_sesiones_min": 3.00}},
        {"claim": "m2", "umbral": {"sobrestimacion_max": 1.15,
                                   "sonda_jitter_sobre_jitter_min": 0.50}},
        {"claim": "m3", "umbral": [3.0, 6.5]}]}
    def comp(entre, dentro):
        return {"sesiones": {"lote_9": {"dispersion_k": 1.15, "mediana_k": 0.12},
                             "lote_10": {"dispersion_k": dentro, "mediana_k": 0.33}},
                "dispersion_k_entre_sesiones": entre,
                "sonda": [{"acto": "X", "sonda_sobre_min": 1.05,
                           "sonda_jitter_sobre_jitter": 0.60}],
                "coste": [{"acto": "X", "coste_sobre_trabajo": 4.0}]}
    # En medio: no sobrevive y el falsador no dispara. Eso es zona muerta, no caida.
    m1 = sonda._veredictos(comp(2.64, 1.14), pred)[0]
    assert (m1["sobrevive"], m1["falsador"], m1["zona_muerta"]) == (False, False, True)
    # Por encima del umbral: sobrevive.
    assert sonda._veredictos(comp(3.20, 1.20), pred)[0]["sobrevive"] is True
    # Por debajo del falsador: cae, y entonces no hay zona muerta.
    m1 = sonda._veredictos(comp(1.90, 1.20), pred)[0]
    assert (m1["sobrevive"], m1["falsador"], m1["zona_muerta"]) == (False, True, False)
    # Y la dispersion interna sola, con `entre` sano, no basta para sobrevivir.
    assert sonda._veredictos(comp(3.20, 1.50), pred)[0]["sobrevive"] is False
    assert sonda._veredictos(comp(3.20, 1.14), pred)[1]["sobrevive"] is True
    assert sonda._veredictos(comp(3.20, 1.14), pred)[2]["sobrevive"] is True
    malo = comp(3.20, 1.14)
    malo["sonda"] = [{"acto": "X", "sonda_sobre_min": 1.31,
                      "sonda_jitter_sobre_jitter": 0.60}]
    assert sonda._veredictos(malo, pred)[1]["falsador"] is True
    malo["sonda"] = [{"acto": "X", "sonda_sobre_min": 1.05,
                      "sonda_jitter_sobre_jitter": 0.29}]
    assert sonda._veredictos(malo, pred)[1]["falsador"] is True
    malo = comp(3.20, 1.14)
    malo["coste"] = [{"acto": "X", "coste_sobre_trabajo": 6.6}]
    assert sonda._veredictos(malo, pred)[2]["sobrevive"] is False


def test_la_factorizacion_sale_de_la_funcion_y_no_de_una_constante():
    k9 = [0.25, 0.20, 0.10]
    k10 = [0.50, 0.40, 0.80]
    actos = [{"nombre": n, "jitter_relativo": k}
             for n, k in zip("ABCDEFGH", [0.9, 0.9] + k9 + k10)]
    out = sonda._sesiones(actos)
    assert out["sesiones"]["lote_9"]["k"] == k9
    assert out["sesiones"]["lote_10"]["k"] == k10
    assert out["sesiones"]["lote_9"]["dispersion_k"] == 2.5
    assert out["sesiones"]["lote_10"]["dispersion_k"] == 2.0
    assert out["dispersion_k_entre_sesiones"] == 2.5
    d = out["descomposicion"]
    assert d["total_sobre_las_dos_sesiones"] == 8.0
    assert (d["entre_sesiones"], d["posicion_dentro_de_lote_9"],
            d["posicion_dentro_de_lote_10"]) == (2.5, 2.0, 1.6)
    assert d["producto"] == d["total_sobre_las_dos_sesiones"]
    # `dispersion_k` es el cociente de extremos; `posicion_dentro_de_*` divide la
    # mediana de la sesion entre su minimo. Dos cuentas distintas sobre la misma lista.
    assert out["sesiones"]["lote_10"]["mediana_k"] == 0.5
    assert out["sesiones"]["lote_9"]["dispersion_k"] == round(max(k9) / min(k9), 4)
    # Y los actos fuera de las dos sesiones no entran en la cuenta.
    assert out["sesiones"]["lote_9"]["actos"] == ["C", "D", "E"]
    assert 0.9 not in out["sesiones"]["lote_9"]["k"]


def test_la_rama_del_resumen_se_deriva_de_los_veredictos_y_no_se_elige():
    veredictos = DECIMO_ARTE["veredictos"]
    resumen = DECIMO_ARTE["predictions_summary"]
    sobre = [x["id"] for x in veredictos if x["sobrevive"]]
    caen = [x["id"] for x in veredictos if not x["sobrevive"]]
    assert resumen["sobreviven"] == sobre
    assert resumen["caen"] == caen
    # Tres ramas y ninguna cuarta: o todas sobreviven, o ninguna, o queda partida.
    # Una `rama` que no salga de aqui es una etiqueta elegida, no una medida.
    esperado = ("todas_sobreviven" if not caen
                else "ninguna_sobrevive" if not sobre else "parcial")
    assert resumen["rama"] == esperado
    assert resumen["zona_muerta"] == [x["id"] for x in veredictos if x.get("zona_muerta")]
