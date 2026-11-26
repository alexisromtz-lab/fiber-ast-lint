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
    for k, v in FUERA["totals"].items():
        assert v == sum(r[k] for r in FUERA["rows"]), k


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
