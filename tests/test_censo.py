"""The census is a claim about artifacts, not about a machine.

Every row of `censo.json` names a wheel, its SHA-256 and the subtree that was
analysed, so the claim can be re-derived by someone who does not have this
repository. These tests check the two ways that file can lie: a row that is not
pinned, and a README table that drifted away from it.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CENSO = json.loads((RAIZ / "censo.json").read_text(encoding="utf-8"))
README = (RAIZ / "README.md").read_text(encoding="utf-8")

CAMPOS = ("files", "stores", "pierde", "candidates", "admitted", "column_loci")


def _num(texto: str) -> int:
    return int(texto.replace(" ", "").replace("\u00a0", ""))


def _tabla(encabezado: str) -> list[list[str]]:
    lineas = README.splitlines()
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


def _fila(package: str, scope: str) -> dict:
    scope = scope.rstrip("/") or "."
    for r in CENSO["rows"]:
        if r["package"] == package and r["scope"] == scope:
            return r
    raise AssertionError(f"{package} scope={scope} ausente de censo.json")


def test_every_row_is_pinned():
    for r in CENSO["rows"]:
        assert re.fullmatch(r"[0-9a-f]{64}", r["sha256"]), r
        assert r["version"] and r["scope"], r
        assert r["version"] in r["artifact"], r
        assert r["bytes"] > 0, r
        # The flag is not evidence. The row now publishes the buckets, so the
        # equation is recomputed here instead of believed.
        suma = r["pierde"] + r["guardadas"] + r["acumulacion"] + r["posicional"] + r["sin_len"]
        assert suma == r["stores"], (
            f"{r['package']} {r['scope']}: {r['stores']} != {suma} (residuo {r['stores'] - suma})")
        assert r["reconciles"] is True, f"{r['package']}: el censo de descartes no cuadra"


def test_one_artifact_one_digest():
    por_artefacto: dict[str, set[str]] = {}
    for r in CENSO["rows"]:
        por_artefacto.setdefault(r["artifact"], set()).add(r["sha256"])
    duplicados = {k: v for k, v in por_artefacto.items() if len(v) > 1}
    assert not duplicados, duplicados


def test_seven_package_table_matches_censo():
    filas = _tabla("| package | version | scope |")
    assert len(filas) == 8, "la tabla de siete paquetes cambió de forma"
    for package, version, scope, *resto in filas[:-1]:
        r = _fila(package, scope)
        assert version == r["version"], (package, version, r["version"])
        medido = dict(zip(("files", "stores", "pierde", "candidates",
                           "admitted", "column_loci"), (_num(c) for c in resto)))
        real = {k: r[k] for k in medido}
        assert medido == real, f"{package}: README {medido} != censo.json {real}"


def test_seven_package_total_matches_censo():
    total = _tabla("| package | version | scope |")[-1]
    assert total[0] == "total"
    medido = dict(zip(("files", "stores", "pierde", "candidates",
                       "admitted", "column_loci"), (_num(c) for c in total[3:])))
    publicado = {k: CENSO["totals_seven"][k] for k in medido}
    assert medido == publicado, (medido, publicado)
    t = CENSO["totals_seven"]
    suma = t["pierde"] + t["guardadas"] + t["acumulacion"] + t["posicional"] + t["sin_len"]
    assert suma == t["stores"], f"el total de siete no cuadra: {t['stores']} != {suma}"


def test_wide_table_matches_censo():
    filas = _tabla("| package | version | files |")
    assert len(filas) == 3
    claves = {"mypy (whole wheel)": ("mypy", "."),
              "pydantic": ("pydantic", "."),
              "jsonschema": ("jsonschema", ".")}
    for etiqueta, version, files, stores, pierde, loops, cand, adm, col in filas:
        r = _fila(*claves[etiqueta])
        assert version == r["version"]
        assert (_num(files), _num(stores), _num(pierde), _num(loops), _num(cand),
                _num(adm), _num(col)) == (r["files"], r["stores"], r["pierde"],
                                          r["loops"], r["candidates"],
                                          r["admitted"], r["column_loci"]), etiqueta


def test_replay_against_unpacked_wheels():
    """Offline replay: skipped loudly unless the corpora are on disk."""
    base = os.environ.get("FIBER_CENSO_DIR")
    if not base:
        pytest.skip("FIBER_CENSO_DIR no declarada: censo no re-ejecutado (NO_MEDIDO)")
    for r in CENSO["rows"]:
        raiz = Path(base) / f"{r['package']}-{r['version']}" / r["scope"]
        if not raiz.is_dir():
            pytest.skip(f"falta {raiz}: censo no re-ejecutado (NO_MEDIDO)")
        p = subprocess.run([sys.executable, "-m", "fiber_ast_lint", str(raiz), "--json"],
                           capture_output=True, text=True)
        d = json.loads(p.stdout)
        cand = d["candidatos"]
        real = {"files": d["archivos"], "stores": d["almacenes"], "pierde": d["pierde"],
                "candidates": len(cand),
                "admitted": sum(1 for c in cand if c["severidad"] == "CANDIDATO"),
                "column_loci": sum(1 for c in cand
                                   if c["forma"] == "SELECCION_COLUMNA_BUCLE")}
        assert real == {k: r[k] for k in real}, f"{r['package']} {r['scope']}"


def test_instrument_version_is_the_package_version():
    """A pin that names a version which never produced it is a testimony.

    If this fails, the fix is to re-run the census with the new code, never to
    edit the version in `censo.json` to match.
    """
    import fiber_ast_lint

    assert CENSO["instrument_version"] == fiber_ast_lint.__version__
