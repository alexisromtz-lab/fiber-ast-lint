"""Measure a batch of wheels that were named before they were fetched.

`replay_censo.py` starts from a file that already names an artifact; it can prove a
pin but it cannot name one. A batch whose packages were chosen before any data
existed needs the other half: go to PyPI, pick the pure wheel, verify the digest
against PyPI's own, unpack it, scan the import subtree, and write the rows.

The row shape is not redefined here. `replay_censo._medir` is the only definition
of what a row is, so a measured row and a replayed row cannot drift apart.

    python bench/lote.py --paquetes tomli,colorama --out lote.json

Exit codes stay on the ladder the package already uses.

    0  every package measured
    2  NO_MEDIDO -- PyPI unreachable or no pure wheel, nothing was measured
    4  the premise broke -- the wheel on PyPI is not the one whose digest was just
       read, so nothing below it can be interpreted
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
import urllib.error
import urllib.parse
import zipfile
from pathlib import Path

import replay_censo
from replay_censo import NO_MEDIDO, OK, RUPTURA, _get, _medir

RAIZ = replay_censo.RAIZ


def _wheel_puro(meta: dict) -> dict | None:
    """The pure-Python wheel of the newest release, or None.

    A platform wheel carries a compiled core, and the scanner measures Python:
    a batch that silently scanned the thin Python wrapper of a C extension would
    be quoting the wrong subject.
    """
    for entrada in meta.get("urls", []):
        nombre = entrada.get("filename", "")
        if nombre.endswith("-py3-none-any.whl") or nombre.endswith("-py2.py3-none-any.whl"):
            return entrada
    return None


def _subarbol(extraido: Path, paquete: str) -> Path | None:
    """The import subtree: `<name>/` if it is a package, `<name>.py` if a module."""
    normal = paquete.replace("-", "_").lower()
    for candidato in (extraido / normal, extraido / f"{normal}.py"):
        if candidato.exists():
            return candidato
    # Pygments ships `pygments/`, charset-normalizer `charset_normalizer/`; both
    # are covered above. Anything else is a wheel whose layout this script has
    # not seen, and guessing is worse than reporting NO_MEDIDO.
    for candidato in sorted(extraido.iterdir()):
        if candidato.is_dir() and candidato.name.endswith(".dist-info"):
            continue
        if candidato.is_dir() or candidato.suffix == ".py":
            return candidato
    return None


def _medir_n(raiz: Path, repeticiones: int) -> tuple[dict, float]:
    """Measure once, then re-measure for the clock only: the counts are deterministic."""
    celda: dict = {}
    segundos = float("inf")
    for i in range(repeticiones):
        t0 = time.perf_counter()
        celda = _medir(raiz)
        segundos = min(segundos, time.perf_counter() - t0)
    return celda, round(segundos, 3)


def medir_lote(paquetes: list[str], dir_cache: Path, repeticiones: int = 3) -> tuple[list[dict], int]:
    filas: list[dict] = []
    rc = OK
    for paquete in paquetes:
        try:
            meta = json.loads(_get(f"https://pypi.org/pypi/{urllib.parse.quote(paquete)}/json"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  NO_MEDIDO: PyPI sin respuesta para {paquete}: {exc}")
            rc = max(rc, NO_MEDIDO)
            continue
        entrada = _wheel_puro(meta)
        if entrada is None:
            print(f"  NO_MEDIDO: {paquete} {meta['info']['version']} no publica wheel puro")
            rc = max(rc, NO_MEDIDO)
            continue
        destino = dir_cache / entrada["filename"]
        try:
            datos = _get(entrada["url"])
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  NO_MEDIDO: descarga de {entrada['filename']}: {exc}")
            rc = max(rc, NO_MEDIDO)
            continue
        destino.write_bytes(datos)
        digest = hashlib.sha256(datos).hexdigest()
        declarado = entrada.get("digests", {}).get("sha256", "")
        if declarado and digest != declarado:
            print(f"  RUPTURA: {entrada['filename']} no es el que PyPI declara")
            rc = max(rc, RUPTURA)
            continue
        extraido = dir_cache / paquete
        with zipfile.ZipFile(destino) as z:
            z.extractall(extraido)
        raiz = _subarbol(extraido, paquete)
        if raiz is None:
            print(f"  NO_MEDIDO: {entrada['filename']} no tiene subarbol de importacion")
            rc = max(rc, NO_MEDIDO)
            continue
        celda, segundos = _medir_n(raiz, repeticiones)
        claves = celda.pop("claves")
        # `groups` is the fiber count: one adjudication closes every site that
        # shares a key. `species` is the mechanism histogram, which is how a
        # batch says which defect it probably contains.
        fila = {"package": paquete, "version": meta["info"]["version"],
                "artifact": entrada["filename"], "sha256": digest,
                "bytes": len(datos), "scope": raiz.name,
                **celda, "segundos_min": segundos,
                "sites": len(claves),
                "groups": len(set(claves)),
                "sites_per_group": round(len(claves) / len(set(claves)), 4) if claves else None}
        filas.append(fila)
        print(f"  {paquete:<20} f={fila['files']:<4} bucles={fila.get('loops', 0):<6} "
              f"sitios={len(claves):<3} claves={fila['groups']:<3} {segundos:.3f}s")
    return filas, rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure a batch of wheels named in advance.")
    ap.add_argument("--paquetes", required=True, help="comma-separated package names")
    ap.add_argument("--out", required=True, help="where to write the rows")
    ap.add_argument("--dir", help="cache directory (default: a temporary one)")
    ap.add_argument("--keep", action="store_true", help="do not delete the cache")
    ap.add_argument("--repeticiones", type=int, default=3,
                    help="runs per package; the clock keeps the minimum")
    a = ap.parse_args(argv)

    paquetes = [p.strip() for p in a.paquetes.split(",") if p.strip()]
    dir_cache = Path(a.dir) if a.dir else Path(tempfile.mkdtemp(prefix="fiber-lote-"))
    dir_cache.mkdir(parents=True, exist_ok=True)
    try:
        filas, rc = medir_lote(paquetes, dir_cache, a.repeticiones)
        if filas:
            Path(a.out).write_text(json.dumps(filas, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
            print(f"  {len(filas)} filas -> {a.out}")
        else:
            print("NO_MEDIDO: no se midio ninguna fila")
    finally:
        if not a.keep and not a.dir:
            import shutil

            shutil.rmtree(dir_cache, ignore_errors=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
