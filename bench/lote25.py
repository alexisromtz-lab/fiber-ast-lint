"""Run detect 0.5.0 over two frozen cohorts and adjudicate every row with v1.1.

`prediccion-batch-25.json` is the seal; this is the act. Two cohorts, one pass each:

  en muestra      the 125 loci of batch 22 over `censo-22-20261127.json`. No
                  labels are used to decide: the published cause is only compared
                  afterwards, so a contradiction refutes the rule instead of
                  training it. P1 and P2 live here.
  fuera de muestra  the 20 subjects of `censo-25-20261127.json`, which have
                  produced no label ever. detect 0.5.0 emits the candidate rows
                  and v1.1 pronounces on them. P3 lives here, and its reading is
                  done by hand from the `contexto` column this runner publishes
                  -- which is why the context travels in the receipt: the clones
                  are purged, the reading has to survive them.

P4 compares two columns of the same row. `predicha` is the instrument as it is:
native parse, then T1, then T2. `piso` is the same call with the write located in
a `feature_version=(3, 9)` tree, and `fichero_no_parsea` when the floor has no
tree at all -- that is T2's own meaning, not a second rule. Both columns call
`adjudicar`; the only difference is which tree supplies the node.

detect is not touched: the digest is read before the first clone and after the
last one, and a cohort run on any other detect exits without writing.

    python bench/lote25.py --out /tmp/lote25_resultado.json

Exit codes.

    0  every subject cloned and purged, every row adjudicated, detect unchanged
    3  detect is not 0.5.0 -- nothing was measured
    4  a subject's HEAD is not the frozen sha -- nothing below it can be interpreted
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from fiber_ast_lint import analizar  # noqa: E402
from fiber_ast_lint.adjudicador_ast import (  # noqa: E402
    NO_PARSEA,
    POSICIONAL,
    SIN_CAUSA,
    nodo_de_escritura,
)
from fiber_ast_lint.adjudicador_ast_11 import CAUSAS_DECIDIBLES, adjudicar  # noqa: E402

DETECT = REPO / "src/fiber_ast_lint/detect.py"
DETECT_050 = "b03f3ac31a1f843c453a38bb834156328f0f1a073e6fe39b12ad2e75db8bb6d6"
PISO = (3, 9)
CONTEXTO = 3


def _clonar(destino: pathlib.Path, repo: str, sha: str) -> str:
    def git(*a: str) -> str:
        return subprocess.run(
            ["git", *a], cwd=destino, capture_output=True, text=True,
            env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin:/usr/local/bin"},
            check=True,
        ).stdout.strip()

    destino.mkdir(parents=True, exist_ok=True)
    git("init", "-q")
    git("remote", "add", "origin", f"https://github.com/{repo}")
    git("fetch", "-q", "--depth", "1", "origin", sha)
    git("checkout", "-q", "FETCH_HEAD")
    obtenido = git("rev-parse", "HEAD")
    if obtenido != sha:
        raise SystemExit(f"4: {repo}: HEAD {obtenido} != {sha}")
    return obtenido


def _parsear(crudo: bytes, piso: bool) -> ast.Module | None:
    try:
        fuente = crudo.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        if piso:
            return ast.parse(fuente, feature_version=PISO)
        return ast.parse(fuente)
    except (SyntaxError, ValueError):
        return None


def _contexto(crudo: bytes, linea: int) -> list[str]:
    """The write and its neighbourhood, so the hand reading outlives the clone."""
    try:
        lineas = crudo.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return []
    desde = max(1, linea - CONTEXTO)
    return [f"{n}: {lineas[n - 1]}" for n in range(desde, min(len(lineas), linea + CONTEXTO) + 1)]


def _columnas(crudo: bytes, linea: int) -> tuple[str, str, bool, bool]:
    """(predicha, piso, nodo, nodo_piso).

    ``predicha`` is exactly what the instrument does today. ``piso`` answers what
    it would say if the interpreter were 3.9: no tree means T2 has already
    spoken, and a tree means the same call with the node taken from it.
    """
    nativo = _parsear(crudo, piso=False)
    suelo = _parsear(crudo, piso=True)
    nodo = nodo_de_escritura(nativo, linea) if nativo is not None else None
    nodo_piso = nodo_de_escritura(suelo, linea) if suelo is not None else None
    predicha = adjudicar(nodo, crudo)
    piso = NO_PARSEA if suelo is None else adjudicar(nodo_piso, crudo)
    return predicha, piso, nodo is not None, nodo_piso is not None


def _filas_de(destino: pathlib.Path, sujeto: dict, filas: list[dict]) -> list[dict]:
    cache: dict[str, bytes] = {}
    salida = []
    for f in filas:
        clave = f["archivo"]
        if clave not in cache:
            ruta = destino / clave
            cache[clave] = ruta.read_bytes() if ruta.is_file() else b""
        crudo = cache[clave]
        predicha, piso, nodo, nodo_piso = _columnas(crudo, f["linea"])
        salida.append({
            **{k: f[k] for k in ("archivo", "linea", "familia", "forma") if k in f},
            "publicada": f.get("causa", f.get("publicada")),
            "veredicto": f.get("veredicto"),
            "poblacion": f.get("poblacion"),
            "texto": f.get("texto", ""),
            "contexto": _contexto(crudo, f["linea"]),
            "predicha": predicha,
            "piso": piso,
            "nodo": nodo,
            "nodo_piso": nodo_piso,
        })
    return [{"sujeto": sujeto["repo"], "sha": sujeto["sha"], **r} for r in salida]


def _censo(nombre: str) -> list[dict]:
    censo = json.loads((REPO / nombre).read_text(encoding="utf-8"))
    return censo["filas"] if "filas" in censo else censo["sujetos"]


def _en_muestra(base: pathlib.Path) -> dict:
    """Batch 22's 125 rows, decided without looking at their published cause."""
    censo = _censo("censo-22-20261127.json")
    recibo = json.loads((REPO / "recibo-lote22-20261127.json").read_text(encoding="utf-8"))
    por_sujeto: dict[str, list[dict]] = {}
    for f in recibo["loci"]:
        por_sujeto.setdefault(f["sujeto"], []).append(f)

    sujetos, filas = [], []
    for i, s in enumerate(censo, 1):
        destino = base / ("m-" + s["repo"].replace("/", "__"))
        try:
            sha = _clonar(destino, s["repo"], s["sha"])
            analisis = analizar(destino)
            vistos = {(l.rel, l.linea, l.familia, l.forma) for l in analisis.loci}
            esperados = {(f["archivo"], f["linea"], f["familia"], f["forma"])
                         for f in por_sujeto.get(s["repo"], [])
                         if f["causa"] != NO_PARSEA}
            sujetos.append({
                "repo": s["repo"], "sha": sha, "loci_detect": len(analisis.loci),
                "archivos": analisis.archivos, "fallas": analisis.fallas,
                "errores": analisis.errores, "esperados": len(esperados),
                "ausentes": sorted(map(str, esperados - vistos)),
                "sobrantes": sorted(map(str, vistos - esperados)),
            })
            filas.extend(_filas_de(destino, s, por_sujeto.get(s["repo"], [])))
        finally:
            shutil.rmtree(destino, ignore_errors=True)
        if sujetos and sujetos[-1]["repo"] == s["repo"]:
            sujetos[-1]["purga"] = not destino.exists()
        print(f"en muestra [{i}/{len(censo)}] {s['repo']} "
              f"filas={len(por_sujeto.get(s['repo'], []))}", flush=True)

    return _resumen_en_muestra(sujetos, filas)


def _coordenadas(filas: list[dict]) -> list[list]:
    return sorted([f["sujeto"], f["archivo"], f["linea"]] for f in filas)


def _por_piso(filas: list[dict]) -> dict:
    """P4's two columns. T1 is the set decided ``escritura_posicional``; T2 is the
    set that could not be read at all. They are counted apart because only the
    second one is allowed to move with the parser floor.
    """
    t1_nativo = [f for f in filas if f["predicha"] == POSICIONAL]
    t1_piso = [f for f in filas if f["piso"] == POSICIONAL]
    return {
        "t1_nativo": _coordenadas(t1_nativo),
        "t1_piso": _coordenadas(t1_piso),
        "t1_igual": _coordenadas(t1_nativo) == _coordenadas(t1_piso),
        "no_parsea_nativo": sum(1 for f in filas if f["predicha"] == NO_PARSEA),
        "no_parsea_piso": sum(1 for f in filas if f["piso"] == NO_PARSEA),
        "otras_nativo": sum(1 for f in filas if f["predicha"] == SIN_CAUSA),
        "otras_piso": sum(1 for f in filas if f["piso"] == SIN_CAUSA),
    }


def _resumen_en_muestra(sujetos: list[dict], filas: list[dict]) -> dict:
    decididas = [f for f in filas if f["predicha"] in CAUSAS_DECIDIBLES]
    adjudicadas = [f for f in filas if f["veredicto"] in ("CONFIRMADO", "REFUTADO")]
    return {
        "sujetos": sujetos,
        "filas": filas,
        "decididas": len(decididas),
        "por_causa": _por_causa(decididas),
        "adjudicadas": len(adjudicadas),
        "contradicciones": [
            f for f in adjudicadas
            if f["predicha"] in CAUSAS_DECIDIBLES and f["predicha"] != f["publicada"]
        ],
        "decididas_no_publicadas": [
            f for f in decididas if f["publicada"] != f["predicha"]
        ],
        "por_piso": _por_piso(filas),
    }


def _fuera_de_muestra(base: pathlib.Path) -> dict:
    """20 subjects that have produced no label; every candidate row is adjudicated."""
    censo = _censo("censo-25-20261127.json")
    sujetos, filas = [], []
    for i, s in enumerate(censo, 1):
        destino = base / ("f-" + s["repo"].replace("/", "__"))
        try:
            sha = _clonar(destino, s["repo"], s["sha"])
            analisis = analizar(destino)
            candidatos = [
                {"archivo": l.rel, "linea": l.linea, "familia": l.familia,
                 "forma": l.forma, "poblacion": l.poblacion, "texto": l.texto}
                for l in analisis.candidatos
            ]
            sujetos.append({
                "repo": s["repo"], "sha": sha, "spdx": s.get("spdx"),
                "archivos": analisis.archivos, "fallas": analisis.fallas,
                "errores": analisis.errores, "almacenes": analisis.almacenes,
                "reconcilia": analisis.reconcilia(),
                "candidatos": len(candidatos),
            })
            filas.extend(_filas_de(destino, s, candidatos))
        finally:
            shutil.rmtree(destino, ignore_errors=True)
        if sujetos and sujetos[-1]["repo"] == s["repo"]:
            sujetos[-1]["purga"] = not destino.exists()
        print(f"fuera de muestra [{i}/{len(censo)}] {s['repo']} "
              f"candidatos={sujetos[-1]['candidatos']}", flush=True)

    return _resumen_fuera(sujetos, filas)


def _resumen_fuera(sujetos: list[dict], filas: list[dict]) -> dict:
    decididas = [f for f in filas if f["predicha"] in CAUSAS_DECIDIBLES]
    return {
        "sujetos": sujetos,
        "filas": filas,
        "candidatas": len(filas),
        "decididas": len(decididas),
        "por_causa": _por_causa(decididas),
        "por_piso": _por_piso(filas),
        "reconcilia": all(s["reconcilia"] for s in sujetos),
    }


def _por_causa(filas: list[dict]) -> dict[str, int]:
    cuenta: dict[str, int] = {}
    for f in filas:
        cuenta[f["predicha"]] = cuenta.get(f["predicha"], 0) + 1
    return dict(sorted(cuenta.items()))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="/tmp/lote25_resultado.json")
    p.add_argument("--dir", default="")
    a = p.parse_args(argv)

    sentinela = hashlib.sha256(DETECT.read_bytes()).hexdigest()
    if sentinela != DETECT_050:
        print(f"3: detect NO es 0.5.0: {sentinela}")
        return 3

    base = pathlib.Path(a.dir) if a.dir else pathlib.Path(tempfile.mkdtemp(prefix="l25-"))
    salida = {"detect_sha256": sentinela, "interprete": sys.version.split()[0],
              "piso": list(PISO), "adjudicador": "v1.1"}
    try:
        salida["en_muestra"] = _en_muestra(base)
        salida["fuera_de_muestra"] = _fuera_de_muestra(base)
    finally:
        if not a.dir:
            shutil.rmtree(base, ignore_errors=True)

    final = hashlib.sha256(DETECT.read_bytes()).hexdigest()
    dentro, fuera = salida["en_muestra"], salida["fuera_de_muestra"]
    salida["detect_sha256_final"] = final
    salida["resumen"] = {
        "decididas_en_muestra": dentro["decididas"],
        "contradicciones": len(dentro["contradicciones"]),
        "candidatas_fuera": fuera["candidatas"],
        "decididas_fuera": fuera["decididas"],
        "p4_t1_igual_por_piso": fuera["por_piso"]["t1_igual"],
        "no_parsea_por_piso": [fuera["por_piso"]["no_parsea_nativo"],
                               fuera["por_piso"]["no_parsea_piso"]],
        "clones_purgados": sum(1 for s in dentro["sujetos"] + fuera["sujetos"] if s["purga"]),
        "sujetos": len(dentro["sujetos"]) + len(fuera["sujetos"]),
        "detect_intacto": final == sentinela,
    }
    pathlib.Path(a.out).write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    print("resumen: " + json.dumps(salida["resumen"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
