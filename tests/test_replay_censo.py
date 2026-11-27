"""The replay reader has to be able to say four different things.

A replay that can only print "identical" is a mirror. These tests drive the four
verdicts offline with a toy corpus and a census written by hand: identical (0),
divergent (1), not measured (2) and ruptured pin (4). They also check that the
ladder is a supremum, not a first-error-wins.

    python bench/replay_censo.py --desde DIR --censo FILE
"""
from __future__ import annotations

import importlib.util
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
            "column_loci": medido["column_loci"], "reconciles": medido["reconciles"],
            "rc": medido["rc"], "rc_certificado": medido["rc_certificado"],
            "certifica": medido["certifica"]}
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
            "column_loci": sum(1 for c in cand if c["forma"] == "SELECCION_COLUMNA_BUCLE"),
            "rc": d["rc"], "rc_certificado": d["rc_certificado"],
            "reconciles": d["reconcilia"], "certifica": d["certifica"]}


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


def _modulo():
    spec = importlib.util.spec_from_file_location("replay_censo", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _meta(ficheros: dict[str, str]) -> dict:
    return {"info": {"version": "9.9.9"},
            "urls": [{"filename": n, "url": f"https://files.example/{n}",
                      "digests": {"sha256": d}} for n, d in ficheros.items()]}


def test_el_pin_se_pregunta_a_su_release_y_no_al_ultimo(monkeypatch, tmp_path, capsys):
    """Un release de mas aguas arriba no puede romper un pin que sigue publicado.

    PyPI publica en `urls` del proyecto solo los ficheros de la ultima version. Preguntando
    al proyecto, `platformdirs 4.14.8` desaparecio el 2026-11-27 porque salio 4.14.9, y la
    corrida imprimio PIN ROTO sobre un arbol que nadie habia tocado. Aqui se simula ese
    estado exacto: el proyecto solo ofrece 9.9.9 y la version fijada sigue teniendo su rueda.
    """
    modulo = _modulo()
    pedidas: list[str] = []

    def falso_get(url: str) -> bytes:
        pedidas.append(url)
        if url == "https://pypi.org/pypi/pkg/1.2.3/json":
            return json.dumps(_meta({"pkg-1.2.3-py3-none-any.whl": "a" * 64})).encode()
        if url == "https://pypi.org/pypi/pkg/json":
            return json.dumps(_meta({"pkg-9.9.9-py3-none-any.whl": "b" * 64})).encode()
        return b"rueda"

    monkeypatch.setattr(modulo, "_get", falso_get)
    ruta, dig, rc = modulo._traer("pkg", "pkg-1.2.3-py3-none-any.whl",
                                  tmp_path / "pkg.whl", "1.2.3")
    assert rc == modulo.OK, capsys.readouterr().out
    assert dig == "a" * 64
    assert pedidas == ["https://pypi.org/pypi/pkg/1.2.3/json",
                       "https://files.example/pkg-1.2.3-py3-none-any.whl"]


def test_un_artefacto_que_su_release_no_publica_sigue_siendo_ruptura(monkeypatch, tmp_path, capsys):
    """El arreglo de arriba no puede volver blando el codigo 4: sin rueda, premisa rota."""
    modulo = _modulo()
    monkeypatch.setattr(modulo, "_get",
                        lambda url: json.dumps(_meta({"pkg-1.2.4-py3-none-any.whl": "c" * 64})).encode())
    ruta, dig, rc = modulo._traer("pkg", "pkg-1.2.3-py3-none-any.whl",
                                  tmp_path / "pkg.whl", "1.2.3")
    assert rc == modulo.RUPTURA
    assert ruta is None and dig == ""
    assert "pkg 1.2.3 no publica pkg-1.2.3-py3-none-any.whl" in capsys.readouterr().out
