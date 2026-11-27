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
