"""Mide dos relojes sobre los mismos sujetos: pared y CPU del hijo.

El lote 3 dejo la R2 como unico aval de un modelo de coste. Una R2 no dice si el
reloj resuelve: dice como se ordenan las filas que ya se midieron. Este lector
mide, para cada sujeto, el minimo y el maximo de N repeticiones de las dos
magnitudes, de modo que el ruido de la maquina quede publicado en vez de
promediado. Los conteos se miden en cada repeticion y se comparan: si cambian,
el defecto es del escaneo y no se disfraza de ruido.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import zipfile
from pathlib import Path

import lote
import replay_censo
from replay_censo import CAMPOS, CUBETAS, FIRMA, NO_MEDIDO, OK, RUPTURA, _get, _medir

RAIZ = replay_censo.RAIZ
ARTEFACTOS = ("fuera-de-dominio.json", "fuera-de-dominio-2.json", "fuera-de-dominio-3.json")
PREDICCION = "prediccion-batch-4.json"
COMPARADOS = CAMPOS + CUBETAS + FIRMA


def _cpu_hijo() -> float:
    u = resource.getrusage(resource.RUSAGE_CHILDREN)
    return u.ru_utime + u.ru_stime


def _medir_n(raiz: Path, repeticiones: int) -> tuple[dict, dict]:
    """N repeticiones: los conteos tienen que ser identicos, los relojes no."""
    paredes, cpus = [], []
    primera: dict | None = None
    for _ in range(repeticiones):
        c0 = _cpu_hijo()
        t0 = time.perf_counter()
        nueva = _medir(raiz)
        paredes.append(time.perf_counter() - t0)
        cpus.append(_cpu_hijo() - c0)
        if primera is None:
            primera = nueva
        elif {k: nueva[k] for k in COMPARADOS} != {k: primera[k] for k in COMPARADOS}:
            raise RuntimeError(f"los conteos cambiaron entre repeticiones en {raiz}: "
                               "es un defecto del escaneo, no ruido del reloj")
    assert primera is not None
    return primera, {"wall_min": round(min(paredes), 4), "wall_max": round(max(paredes), 4),
                     "cpu_min": round(min(cpus), 4), "cpu_max": round(max(cpus), 4),
                     "wall_muestras": [round(p, 4) for p in paredes],
                     "cpu_muestras": [round(c, 4) for c in cpus]}


def _pins() -> list[dict]:
    pins = []
    for fichero in ARTEFACTOS:
        for r in json.loads((RAIZ / fichero).read_text(encoding="utf-8"))["rows"]:
            pins.append({k: r[k] for k in ("package", "version", "artifact", "sha256",
                                           "scope", "bytes", "files")})
    return pins


def _resolver(pin: dict) -> tuple[str, str]:
    """(url, artifact) del sujeto: version fijada si la hay, ultima si no."""
    paquete = urllib.parse.quote(pin["package"])
    if pin.get("version"):
        meta = json.loads(_get(f"https://pypi.org/pypi/{paquete}/{pin['version']}/json"))
        for entrada in meta.get("urls", []):
            if entrada.get("filename") == pin["artifact"]:
                return entrada["url"], pin["artifact"]
        raise LookupError(f"{pin['package']} {pin['version']} ya no publica {pin['artifact']}")
    meta = json.loads(_get(f"https://pypi.org/pypi/{paquete}/json"))
    entrada = lote._wheel_puro(meta)
    if entrada is None:
        raise LookupError(f"{pin['package']} no publica wheel puro")
    return entrada["url"], entrada["filename"]


def _preparar(pin: dict, cache: Path) -> tuple[Path | None, dict, str, int]:
    """Descarga, verifica el sha256 y devuelve (subarbol, pin resuelto, digest, rc)."""
    try:
        url, artifact = _resolver(pin)
        datos = _get(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, LookupError) as exc:
        print(f"  NO_MEDIDO: {pin['package']}: {exc}")
        return None, pin, "", NO_MEDIDO
    destino = cache / artifact
    destino.write_bytes(datos)
    digest = hashlib.sha256(datos).hexdigest()
    if pin.get("sha256") and digest != pin["sha256"]:
        print(f"  RUPTURA: {artifact} ya no es el artefacto fijado ({digest[:12]})")
        return None, pin, digest, RUPTURA
    extraido = cache / artifact.replace(".whl", "")
    with zipfile.ZipFile(destino) as z:
        z.extractall(extraido)
    resuelto = {**pin, "artifact": artifact, "bytes": pin.get("bytes") or len(datos),
                "version": pin.get("version") or _version_de(artifact)}
    if pin.get("scope"):
        raiz = extraido / pin["scope"]
        if not raiz.exists():
            print(f"  RUPTURA: el scope fijado {pin['scope']} no esta en {artifact}")
            return None, resuelto, digest, RUPTURA
    else:
        raiz = lote._subarbol(extraido, pin["package"])
        if raiz is None:
            print(f"  NO_MEDIDO: {artifact} no tiene subarbol de importacion")
            return None, resuelto, digest, NO_MEDIDO
        resuelto["scope"] = raiz.name
    return raiz, resuelto, digest, OK


def _version_de(artifact: str) -> str:
    """`attrs-26.1.0-py3-none-any.whl` -> `26.1.0` (el nombre no lleva guiones)."""
    return artifact.split("-")[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dos relojes sobre los mismos sujetos.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repeticiones", type=int, default=5)
    ap.add_argument("--dir", help="cache (por defecto, temporal y se borra)")
    args = ap.parse_args(argv)

    pred = json.loads((RAIZ / PREDICCION).read_text(encoding="utf-8"))
    sujetos = list(pred["subjects"]["conocidos"])
    sujetos += [{"package": n} for n in pred["subjects"]["nuevos"]]

    cache = Path(args.dir) if args.dir else Path(tempfile.mkdtemp(prefix="reloj4-"))
    cache.mkdir(parents=True, exist_ok=True)
    rc_global = OK
    filas = []
    try:
        vacio = cache / "vacio"
        vacio.mkdir(exist_ok=True)
        _, arranque = _medir_n(vacio, args.repeticiones)
        print(f"  arranque en vacio: cpu_min={arranque['cpu_min']:.4f} "
              f"pared_min={arranque['wall_min']:.4f}")
        for pin in sujetos:
            print(f"  {pin['package']}:", end="", flush=True)
            raiz, resuelto, digest, rc = _preparar(pin, cache)
            if raiz is None:
                rc_global = max(rc_global, rc)
                print(" sin sujeto")
                continue
            celda, relojes = _medir_n(raiz, args.repeticiones)
            claves = celda.pop("claves")
            especie = celda.pop("species")
            fila = {**resuelto, "sha256_medido": digest, **celda, **relojes,
                    "sites": len(claves), "groups": len(set(claves)), "species": especie}
            filas.append(fila)
            print(f" f={fila['files']:<4} cpu={relojes['cpu_min']:.3f} "
                  f"pared={relojes['wall_min']:.3f}")
    finally:
        if not args.dir:
            shutil.rmtree(cache, ignore_errors=True)

    salida = {"schema": "reloj/1", "repeticiones": args.repeticiones,
              "arranque_vacio": arranque, "rows": filas}
    Path(args.out).write_text(json.dumps(salida, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"escrito {args.out}: {len(filas)} filas")
    return rc_global


if __name__ == "__main__":
    sys.exit(main())
