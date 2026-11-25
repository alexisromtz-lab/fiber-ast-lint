"""The README's recomputable claims, checked against the real code (A0.12 blind spot).

A published number with no reader is prose: nothing notices when it diverges
from the instrument. These tests are that reader. They cover only the cells
that can be recomputed inside this repository -- the fixtures census and the
exit-code contract. The larger censuses in the README need corpora that are not
vendored here; they stay dated and sourced, and no test pretends otherwise.
"""
from __future__ import annotations

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
