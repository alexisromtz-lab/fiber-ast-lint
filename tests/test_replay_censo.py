"""The replay reader has to be able to say four different things.

A replay that can only print "identical" is a mirror. These tests drive the four
verdicts offline with a toy corpus and a census written by hand: identical (0),
divergent (1), not measured (2) and ruptured pin (4). They also check that the
ladder is a supremum, not a first-error-wins.

    python bench/replay_censo.py --desde DIR --censo FILE
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "bench" / "replay_censo.py"

TOY = """\
def junta(partes):
    acc = {}
    for p in partes:
        acc[p.nombre] = p
    return acc
"""


def _correr(desde: Path, censo: Path) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(SCRIPT), "--desde", str(desde),
                        "--censo", str(censo)], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def _censo(tmp: Path, medido: dict) -> Path:
    fila = {"package": "toypkg", "version": "0.0.1", "artifact": "toypkg-0.0.1-py3-none-any.whl",
            "sha256": "0" * 64, "bytes": 1, "scope": ".",
            "files": medido["files"], "stores": medido["stores"], "pierde": medido["pierde"],
            "candidates": medido["candidates"], "admitted": medido["admitted"],
            "column_loci": medido["column_loci"], "reconciles": True, "rc": 1}
    ruta = tmp / "censo.json"
    ruta.write_text(json.dumps({"instrument_version": "0.4.1", "rows": [fila],
                                "totals_seven": {}}, indent=2), encoding="utf-8")
    return ruta


def _medido(desde: Path) -> dict:
    p = subprocess.run([sys.executable, "-m", "fiber_ast_lint",
                        str(desde / "toypkg-0.0.1"), "--json"],
                       capture_output=True, text=True, cwd=RAIZ)
    d = json.loads(p.stdout)
    cand = d["candidatos"]
    return {"files": d["archivos"], "stores": d["almacenes"], "pierde": d["pierde"],
            "candidates": len(cand),
            "admitted": sum(1 for c in cand if c["severidad"] == "CANDIDATO"),
            "column_loci": sum(1 for c in cand if c["forma"] == "SELECCION_COLUMNA_BUCLE")}


def test_identical_divergent_and_unmeasured(tmp_path: Path) -> None:
    desde = tmp_path / "corpus"
    (desde / "toypkg-0.0.1").mkdir(parents=True)
    (desde / "toypkg-0.0.1" / "toy.py").write_text(TOY, encoding="utf-8")
    medido = _medido(desde)

    censo = _censo(tmp_path, medido)
    rc, salida = _correr(desde, censo)
    assert rc == 0, salida
    assert "REPLAY IDENTICO" in salida

    fila = json.loads(censo.read_text())["rows"][0]
    fila["files"] = medido["files"] + 1
    censo.write_text(json.dumps({"instrument_version": "0.4.1", "rows": [fila],
                                 "totals_seven": {}}, indent=2), encoding="utf-8")
    rc, salida = _correr(desde, censo)
    assert rc == 1, salida
    assert "DIVERGE" in salida

    p = subprocess.run([sys.executable, str(SCRIPT), "--desde", str(tmp_path / "nada"),
                        "--censo", str(censo)], capture_output=True, text=True)
    assert p.returncode == 2, p.stdout + p.stderr
    assert "NO_MEDIDO" in p.stdout + p.stderr


def test_an_unmeasured_corpus_does_not_mask_a_divergence(tmp_path: Path) -> None:
    """4 > 1 > 2 > 0: the worst verdict wins, and `NO_MEDIDO` is the mildest.

    A missing corpus must not hide a cell that has already been proven wrong,
    which is the same ordering failure the ingest guard was built to refuse.
    """
    desde = tmp_path / "corpus"
    (desde / "toypkg-0.0.1").mkdir(parents=True)
    (desde / "toypkg-0.0.1" / "toy.py").write_text(TOY, encoding="utf-8")
    medido = _medido(desde)
    censo = _censo(tmp_path, medido)
    datos = json.loads(censo.read_text())
    datos["rows"][0]["files"] = medido["files"] + 1
    datos["rows"].append({"package": "otro", "version": "1", "artifact": "otro-1.whl",
                          "scope": ".", "files": 9})
    censo.write_text(json.dumps(datos, indent=2), encoding="utf-8")
    rc, salida = _correr(desde, censo)
    assert "DIVERGE" in salida and "NO_MEDIDO" in salida, salida
    assert rc == 1, salida
