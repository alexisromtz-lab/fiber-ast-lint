"""The README's recomputable claims, checked against the real code (A0.12 blind spot).

A published number with no reader is prose: nothing notices when it diverges
from the instrument. These tests are that reader. They cover only the cells
that can be recomputed inside this repository -- the fixtures census and the
exit-code contract. The larger censuses in the README need corpora that are not
vendored here; they stay dated and sourced, and no test pretends otherwise.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from fiber_ast_lint.cli import construir
from fiber_ast_lint.detect import RC_CANDIDATO, RC_CONSERVACION, RC_OK, RC_VACIO

RAIZ = Path(__file__).resolve().parents[1]
README = (RAIZ / "README.md").read_text(encoding="utf-8")

COLUMNAS = [
    "files", "stores", "lose", "guarded", "aggregate", "positional",
    "unmeasured", "candidates",
]


def _fila_fixtures() -> list[int]:
    for linea in README.splitlines():
        if linea.startswith("| `tests/fixtures`"):
            celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
            return [int(c) for c in celdas[1:]]
    raise AssertionError("README no publica la fila `tests/fixtures`")


def test_fixtures_census_matches_readme() -> None:
    d = construir(str(RAIZ / "tests" / "fixtures"), interproc=False)
    real = [
        d["archivos"], d["almacenes"], d["pierde"], d["guardadas"],
        d["acumulacion"], d["posicional"], d["sin_len"], len(d["candidatos"]),
    ]
    publicado = _fila_fixtures()
    discrepan = {
        col: (pub, real_)
        for col, pub, real_ in zip(COLUMNAS, publicado, real)
        if pub != real_
    }
    assert not discrepan, f"README.desactualizado: {discrepan}"


def test_fixtures_census_reconciles() -> None:
    d = construir(str(RAIZ / "tests" / "fixtures"), interproc=False)
    suma = d["pierde"] + d["guardadas"] + d["acumulacion"] + d["posicional"] + d["sin_len"]
    assert suma == d["almacenes"], f"cubetas no cierran: {suma} != {d['almacenes']}"


def test_exit_codes_table_matches_contract() -> None:
    codigos: set[int] = set()
    dentro = False
    for linea in README.splitlines():
        if linea.startswith("## Exit codes"):
            dentro = True
            continue
        if dentro and linea.startswith("## "):
            break
        if dentro:
            m = re.match(r"\|\s*`(\d)`\s*\|", linea)
            if m:
                codigos.add(int(m.group(1)))
    contrato = {RC_OK, RC_CANDIDATO, RC_VACIO, RC_CONSERVACION}
    assert codigos == contrato, f"README declara {sorted(codigos)}, el codigo {sorted(contrato)}"


# --- The install line is a claim about a name, and a name resolves or it does not ---------------
#
# Measured 2026-11-27: `uvx fiber-ast-lint` answers `unsatisfiable requirements`, so every console
# line that asks the registry for the bare name teaches a command that cannot run. On 2026-11-27 a
# commit landed on `main` that put that line back as the documented install, and the whole suite
# stayed green: nothing read the block. This is that reader.

NOMBRE_RESUELVE_EN_PYPI = False
NOMBRE = "fiber-ast-lint"
PROGRAMAS = ("uvx", "pip", "pip3", "pipx")


def _comandos() -> list[str]:
    """Every line the README prints as a command, with the `$ ` prompt removed.

    Fences are not tracked on purpose: this README carries an odd number of them (a pre-existing
    orphan), so pairing fences would mis-scope every block after it. A line counts as a command if
    it carries the prompt or if it opens with a program this README could plausibly invoke.
    """
    comandos: list[str] = []
    for linea in README.splitlines():
        limpia = linea.strip()
        if limpia.startswith("$ "):
            limpia = limpia[2:].strip()
        elif not limpia.startswith(PROGRAMAS):
            continue
        if limpia:
            comandos.append(limpia)
    return comandos


def _pide_el_nombre_al_registro(comando: str) -> bool:
    """True when the command asks a registry for the name with no `git+`/`gh:` source."""
    piezas = comando.split()
    if not piezas or piezas[0] not in PROGRAMAS:
        return False
    if NOMBRE not in piezas:
        return False
    return not any(p.startswith(("git+", "gh:")) for p in piezas)


def test_el_readme_no_ensena_un_nombre_que_no_resuelve() -> None:
    if NOMBRE_RESUELVE_EN_PYPI:
        return
    culpables = [c for c in _comandos() if _pide_el_nombre_al_registro(c)]
    assert not culpables, (
        f"README enseña `{NOMBRE}` sin fuente `git+` y ese nombre no resuelve: {culpables}"
    )


def test_la_guarda_ve_comandos_y_discrimina() -> None:
    assert _comandos(), "el lector no encontro ningun comando: la guarda seria un verde vacio"
    assert _pide_el_nombre_al_registro("uvx fiber-ast-lint [ruta]")
    assert _pide_el_nombre_al_registro("pip install fiber-ast-lint       # or: pipx install")
    assert not _pide_el_nombre_al_registro(
        "uvx --from git+https://github.com/alexisromtz-lab/fiber-ast-lint fiber-ast-lint x.py"
    )
    assert not _pide_el_nombre_al_registro(
        "pip install git+https://github.com/alexisromtz-lab/fiber-ast-lint@v0.4.6"
    )


# --- The batch-14 tablas: a verdict published in prose must agree with the receipt ---------------
#
# The batch-14 section publishes thirteen verdicts and a four-row count. Both are recomputable from
# the seals sitting next to the README, so a reader that recomputes them costs one test and removes
# the only number in that section that could drift without anyone noticing.

SECCION_14 = "## The verdict is a function of the predicate"


def _seccion_14() -> list[str]:
    dentro = False
    salida: list[str] = []
    for linea in README.splitlines():
        if linea.startswith(SECCION_14):
            dentro = True
            continue
        if dentro and linea.startswith("## "):
            break
        if dentro:
            salida.append(linea)
    assert salida, f"el README no publica la seccion `{SECCION_14}`"
    return salida


def _celdas(linea: str) -> list[str]:
    return [c.strip() for c in linea.strip().strip("|").split("|")]


def _veredictos_publicados() -> dict[str, str]:
    publicados: dict[str, str] = {}
    for linea in _seccion_14():
        if not linea.startswith("| `"):
            continue
        celdas = _celdas(linea)
        if len(celdas) != 3:
            continue
        m = re.fullmatch(r"`([KLMNP]\d)`", celdas[0])
        if m:
            publicados[m.group(1)] = celdas[2].replace("*", "").replace("`", "")
    return publicados


def _veredictos_reales() -> dict[str, str]:
    reales: dict[str, str] = {}
    for fichero in sorted(RAIZ.glob("recibo-banda-14-lote*.json")):
        rec = json.loads(fichero.read_text(encoding="utf-8"))
        assert rec["schema"] == "fiber-ast-lint/recibo/3", fichero.name
        for v in rec["veredictos"]:
            assert v["id"] not in reales, f"{v['id']} aparece en dos recibos del lote 14"
            if v["estado"] == "evaluado":
                reales[v["id"]] = "survives" if v["sobrevive"] else "falls"
            else:
                reales[v["id"]] = f"NO_MEDIDO · {v['causa']}"
    return reales


def test_la_tabla_de_veredictos_del_lote_14_se_recomputa() -> None:
    publicados = _veredictos_publicados()
    reales = _veredictos_reales()
    assert reales, "no hay recibos del lote 14: el lector seria un verde vacio"
    assert set(publicados) == set(reales), (
        f"el README publica {sorted(publicados)}, los recibos declaran {sorted(reales)}"
    )
    for pid, celda in publicados.items():
        assert celda.startswith(reales[pid]), f"{pid}: README dice `{celda}`, el recibo `{reales[pid]}`"


def _recuento_publicado() -> dict[str, tuple[int, int, int]]:
    filas: dict[str, tuple[int, int, int]] = {}
    for linea in _seccion_14():
        if not linea.startswith("| `fuera-de-dominio-"):
            continue
        celdas = _celdas(linea)
        assert len(celdas) == 7, linea
        filas[celdas[1].strip("`")] = tuple(int(c) for c in celdas[2:])
    return filas


def test_el_recuento_del_lote_14_se_recomputa() -> None:
    """Declaradas, juzgadas y no medidas: la tabla que dice que nada quedo en silencio."""
    publicadas = _recuento_publicado()
    reales: dict[str, tuple[int, int, int]] = {}
    for fichero in sorted(RAIZ.glob("recibo-banda-14-lote*.json")):
        rec = json.loads(fichero.read_text(encoding="utf-8"))
        vs = rec["veredictos"]
        juzgadas = sum(1 for v in vs if v["estado"] == "evaluado")
        reales[rec["pre_registro"]["ruta"]] = (
            rec["resumen"]["actos"], sum(b["n"] for a in rec["actos"] for b in a["hechos"]["bloques"]),
            len(vs), juzgadas, len(vs) - juzgadas,
        )
    assert set(publicadas) == set(reales), (
        f"el README publica {sorted(publicadas)}, los recibos {sorted(reales)}"
    )
    for nombre, celdas in publicadas.items():
        assert celdas == reales[nombre], f"{nombre}: README {celdas}, recibo {reales[nombre]}"


def test_los_sellos_del_lote_14_publicados_son_los_de_los_recibos() -> None:
    """Las cuatro huellas del README existen en los cuatro ficheros, por prefijo."""
    texto = "\n".join(_seccion_14())
    publicadas = re.findall(r"`([0-9a-f]{8})…`", texto)
    reales = {
        json.loads(f.read_text(encoding="utf-8"))["huella"][:8]
        for f in RAIZ.glob("recibo-banda-14-lote*.json")
    }
    faltan = reales - set(publicadas)
    assert not faltan, f"el README no publica el sello de {sorted(faltan)}"
    assert len(publicadas) == 11, (
        f"el README cita {len(publicadas)} sellos; son cuatro del lote 14 y siete anteriores"
    )


SECCION_15 = "## One degree of composition, and an absence that declares itself"


def _seccion_15() -> list[str]:
    dentro = False
    salida: list[str] = []
    for linea in README.splitlines():
        if linea.startswith(SECCION_15):
            dentro = True
            continue
        if dentro and linea.startswith("## "):
            break
        if dentro:
            salida.append(linea)
    assert salida, f"el README no publica la seccion `{SECCION_15}`"
    return salida


def test_la_tabla_de_sellos_del_lote_15_se_recomputa() -> None:
    """Cada celda de la tabla del lote 15 se compara contra el fichero que nombra."""
    filas = [
        [c.strip() for c in l.strip().strip("|").split("|")]
        for l in _seccion_15()
        if l.startswith("| `recibo-banda-15-")
    ]
    assert len(filas) == 2, filas
    texto = "\n".join(_seccion_15())
    for fichero, artefacto, pre_registro, recuento in filas:
        real = json.loads((RAIZ / fichero.strip("`")).read_text(encoding="utf-8"))
        assert real["fuente_artefacto"]["ruta"] == artefacto.strip("`"), artefacto
        assert (RAIZ / artefacto.strip("`")).exists(), artefacto
        assert real["pre_registro"]["ruta"] == pre_registro.strip("`"), pre_registro
        assert real["pre_registro"]["sha256"] == hashlib.sha256(
            (RAIZ / pre_registro.strip("`")).read_bytes()).hexdigest(), pre_registro
        assert f"`{real['huella'][:8]}…`" in texto, f"el README no publica {real['huella'][:8]}"
        v = real["resumen"]["veredictos"]
        assert f"{v['evaluadas']} evaluated" in recuento, recuento
        assert re.search(rf"{v['no_medidas']} (not measured|out of the footprint)", recuento), recuento


def test_el_readme_del_lote_15_publica_las_dos_lecturas_medidas() -> None:
    """Las dos cifras del README son las del recibo, y la banda es reciproca de si misma."""
    texto = "\n".join(_seccion_15())
    l3 = json.loads((RAIZ / "recibo-banda-15-lote9.json").read_text())["veredictos"][0]
    cifras = [c["expr"] for c in l3["medido"]["y"]]
    for c in cifras:
        assert f"{c:.6f}" in texto, f"el README no publica {c:.6f}"
    bajo, alto = l3["medido"]["y"][0]["valor"]
    assert round(1 / alto, 10) == bajo, (bajo, alto)
    assert "its own reciprocal" in texto


def test_el_readme_del_lote_15_declara_el_techo_que_el_interprete_aplica() -> None:
    """Un techo citado en prosa y otro aplicado en codigo es una segunda fuente de verdad."""
    from bench import predicado as p11

    texto = "\n".join(_seccion_15())
    assert f"PROFUNDIDAD_MAXIMA={p11.PROFUNDIDAD_MAXIMA}" in texto, texto[:400]
    assert f"profundidad {p11.PROFUNDIDAD_MAXIMA + 1} supera" in texto
