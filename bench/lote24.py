"""Run detect 0.5.0 over a frozen cohort and adjudicate every published row.

The receipt of batch 24 named a command, and a command that lives in `/tmp` is not
a measurement: `recibo-lote24-20261127.json` can be re-checked by its reader, but it
could not be re-run. This is the runner that produced it, with the only change that
matters -- it takes the repository root from its own location instead of hardcoding
one, so a cold clone can repeat the act.

detect is not touched and not importable from here by accident: the digest is read
before the first clone and again after the last one, and a cohort run on any other
detect exits without writing.

    python bench/lote24.py --out /tmp/lote24_resultado.json

Exit codes.

    0  every subject cloned, every row adjudicated, detect unchanged
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
from fiber_ast_lint.adjudicador_ast import SIN_CAUSA, adjudicar, nodo_de_escritura  # noqa: E402

DETECT = REPO / "src/fiber_ast_lint/detect.py"
DETECT_050 = "b03f3ac31a1f843c453a38bb834156328f0f1a073e6fe39b12ad2e75db8bb6d6"


def _clonar(destino: pathlib.Path, repo: str, sha: str) -> None:
    def git(*a: str) -> str:
        return subprocess.run(
            ["git", *a], cwd=destino, capture_output=True, text=True,
            env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin:/usr/local/bin"},
            check=True,
        ).stdout.strip()

    git("init", "-q")
    git("remote", "add", "origin", f"https://github.com/{repo}")
    git("fetch", "-q", "--depth", "1", "origin", sha)
    git("checkout", "-q", "FETCH_HEAD")
    obtenido = git("rev-parse", "HEAD")
    if obtenido != sha:
        raise SystemExit(f"4: {repo}: HEAD {obtenido} != {sha}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="/tmp/lote24_resultado.json")
    p.add_argument("--dir", default="")
    a = p.parse_args(argv)

    sentinela = hashlib.sha256(DETECT.read_bytes()).hexdigest()
    if sentinela != DETECT_050:
        print(f"3: detect NO es 0.5.0: {sentinela}")
        return 3

    censo = json.loads((REPO / "censo-22-20261127.json").read_text(encoding="utf-8"))
    recibo = json.loads((REPO / "recibo-lote22-20261127.json").read_text(encoding="utf-8"))
    filas = recibo["loci"]
    por_sujeto: dict[str, list[dict]] = {}
    for f in filas:
        por_sujeto.setdefault(f["sujeto"], []).append(f)

    base = pathlib.Path(a.dir) if a.dir else pathlib.Path(tempfile.mkdtemp(prefix="l24-"))
    sujetos = censo["filas"] if "filas" in censo else censo["sujetos"]
    print(f"cohorte: {len(sujetos)} sujetos · {len(filas)} filas", flush=True)
    salida = {"detect_sha256": sentinela, "interprete": sys.version.split()[0],
              "sujetos": [], "reproducibilidad": [], "filas": []}

    try:
        for i, s in enumerate(sujetos, 1):
            repo, sha = s["repo"], s["sha"]
            destino = base / repo.replace("/", "__")
            if destino.exists():
                shutil.rmtree(destino)
            destino.mkdir(parents=True)
            _clonar(destino, repo, sha)

            analisis = analizar(destino)
            vistos = {(l.rel, l.linea, l.familia, l.forma) for l in analisis.loci}
            esperados = {(f["archivo"], f["linea"], f["familia"], f["forma"])
                         for f in por_sujeto.get(repo, []) if f["causa"] != "fichero_no_parsea"}
            salida["reproducibilidad"].append({
                "repo": repo, "sha": sha,
                "loci_detect": len(analisis.loci), "archivos": analisis.archivos,
                "fallas": analisis.fallas, "errores": analisis.errores,
                "esperados": len(esperados),
                "ausentes": sorted(map(str, esperados - vistos)),
                "sobrantes": sorted(map(str, vistos - esperados)),
            })

            cache: dict[str, tuple[ast.Module | None, bytes]] = {}
            for f in por_sujeto.get(repo, []):
                clave = f["archivo"]
                if clave not in cache:
                    ruta = destino / clave
                    crudo = ruta.read_bytes() if ruta.is_file() else b""
                    try:
                        arbol = ast.parse(crudo.decode("utf-8"), filename=clave)
                    except (SyntaxError, UnicodeDecodeError, ValueError):
                        arbol = None
                    cache[clave] = (arbol, crudo)
                arbol, crudo = cache[clave]
                nodo = nodo_de_escritura(arbol, f["linea"]) if arbol is not None else None
                salida["filas"].append({
                    "sujeto": repo, "sha": sha, "archivo": f["archivo"], "linea": f["linea"],
                    "familia": f["familia"], "forma": f["forma"],
                    "publicada": f["causa"], "veredicto": f["veredicto"],
                    "predicha": adjudicar(nodo, crudo), "nodo": nodo is not None,
                })
            print(f"[{i}/{len(sujetos)}] {repo} loci={len(analisis.loci)} "
                  f"filas={len(por_sujeto.get(repo, []))}", flush=True)
            shutil.rmtree(destino)
    finally:
        if not a.dir:
            shutil.rmtree(base, ignore_errors=True)

    final = hashlib.sha256(DETECT.read_bytes()).hexdigest()
    salida["detect_sha256_final"] = final
    salida["decididas"] = sum(1 for f in salida["filas"] if f["predicha"] != SIN_CAUSA)
    pathlib.Path(a.out).write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    print(f"OK · filas={len(salida['filas'])} · decididas={salida['decididas']} · "
          f"detect intacto={final == sentinela}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
