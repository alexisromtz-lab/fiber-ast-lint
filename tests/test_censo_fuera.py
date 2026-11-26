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
