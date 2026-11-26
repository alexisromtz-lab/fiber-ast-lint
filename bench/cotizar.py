"""Turn a tree into a quote whose counts are exact and whose clock is declared.

Batch 4 established that the count reproduces between sessions and the clock does
not. A quote built on that result cannot be a single number, so this instrument
publishes three things and never mixes them:

* **counts** -- what the invoice is denominated in: sites closed by their key,
  files, stores, and the buckets that make the store count checkable. They come
  from the same ``_medir`` the census replay uses, so a quoted row and a replayed
  row cannot drift apart.
* **subject** -- a digest over the scanned tree (relative path, file digest,
  sorted). The client can recompute it with ``shasum``; it fixes which tree the
  counts belong to, which is the half ``bytes`` never fixed (batch 4, attrs).
* **clock** -- the run's own elapsed and child-CPU time, measured here, on this
  machine, now. It is a *measurement of this subject*, not a prediction. A model
  forecast is offered only when the caller supplies the artifact bytes the model
  was fitted on; for any other subject the forecast is NO_MEDIDO with the reason
  written next to it, because a model applied outside its subject is a second
  subject under one key.

And the price: without a signed tariff there is no price. The instrument does not
invent coefficients -- it publishes ``NO_COTIZADO``. With a tariff it multiplies
counts by coefficients and nothing else.

    python bench/cotizar.py --arbol src/fiber_ast_lint --out /tmp/cotizacion.json

Exit codes are the package ladder (``4 > 1 > 2 > 0``): a quote whose price is not
quoted is not a clean run, it is ``NO_MEDIDO``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import statistics
import sys
import time
from pathlib import Path

import replay_censo
from replay_censo import NO_MEDIDO, OK, RUPTURA, _medir

RAIZ = replay_censo.RAIZ
ESQUEMA = "fiber-ast-lint/cotizacion/1"
CALIBRACION = RAIZ / "fuera-de-dominio-4.json"
ALFA = 0.2


def _manifiesto(raiz: Path) -> tuple[str, int, int]:
    """Digest of the scanned tree, plus its Python bytes and file count.

    The pair (digest, bytes) is what a client re-computes without our code:
    ``shasum -a 256`` per file, paths sorted, and a sum of sizes. Two subjects
    never share a digest, even when they share a byte count.
    """
    entradas, bytes_py = [], 0
    for fichero in sorted(raiz.rglob("*.py")):
        if not fichero.is_file():
            continue
        datos = fichero.read_bytes()
        bytes_py += len(datos)
        entradas.append(f"{fichero.relative_to(raiz).as_posix()}\0"
                        f"{hashlib.sha256(datos).hexdigest()}\n")
    h = hashlib.sha256("".join(entradas).encode("utf-8")).hexdigest()
    return h, bytes_py, len(entradas)


def _cpu_hijo() -> float:
    uso = resource.getrusage(resource.RUSAGE_CHILDREN)
    return uso.ru_utime + uso.ru_stime


def _tiempo(raiz: Path, repeticiones: int) -> dict:
    """The subject's own clock, and the counts it must not disturb.

    A quote whose counts move between repetitions is not a quote: it is two
    quotes, and the instrument refuses rather than average them.
    """
    paredes, cpus, conteos = [], [], []
    for _ in range(repeticiones):
        c0 = _cpu_hijo()
        t0 = time.perf_counter()
        celda = _medir(raiz)
        paredes.append(time.perf_counter() - t0)
        cpus.append(_cpu_hijo() - c0)
        conteos.append(json.dumps(celda, sort_keys=True))
    if len(set(conteos)) != 1:
        raise RuntimeError("los conteos cambian entre repeticiones: no hay cotizacion")
    return {"celda": celda, "wall_min": round(min(paredes), 4),
            "cpu_min": round(min(cpus), 4), "repeticiones": repeticiones,
            "wall_muestras": [round(x, 4) for x in paredes],
            "cpu_muestras": [round(x, 4) for x in cpus],
            "determinista": True}


def _modelo(filas: list[dict], reloj: str = "cpu_min") -> tuple[float, float]:
    n = len(filas)
    xs = [r["bytes"] for r in filas]
    ys = [r[reloj] for r in filas]
    mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return my - b * mx, b


def _banda(calibracion: dict, bytes_artefacto: int | None, alfa: float = ALFA) -> dict:
    """Split-conformal interval on the CPU model, or NO_MEDIDO with the reason.

    The conformity score is the leave-one-out relative residual of the 15
    calibration rows -- each row scored by a model fitted without it, so a row
    never calibrates its own error. The quantile sits at ``ceil((n+1)(1-alfa))``,
    which is the guarantee: the band is valid for a subject drawn like the
    calibration set, and says nothing about a subject that is not.
    """
    conocidos = calibracion["rows"][:15]
    residuos = sorted(abs(r["cpu_min"] - (_modelo([x for j, x in enumerate(conocidos) if j != i])[0]
                                          + _modelo([x for j, x in enumerate(conocidos) if j != i])[1]
                                          * r["bytes"]))
                      / (_modelo([x for j, x in enumerate(conocidos) if j != i])[0]
                         + _modelo([x for j, x in enumerate(conocidos) if j != i])[1] * r["bytes"])
                      for i, r in enumerate(conocidos))
    n = len(residuos)
    indice = math.ceil((n + 1) * (1 - alfa)) - 1
    q = residuos[indice]
    a, b = _modelo(conocidos)
    base = {"metodo": "conforme partido sobre residuos leave-one-out",
            "calibracion": {"filas": n, "alfa": alfa, "cuantil_indice": indice,
                            "q": round(q, 4), "max_residuo": round(residuos[-1], 4)},
            "modelo": {"a": round(a, 5), "b": round(b, 10), "reloj": "cpu_min",
                       "sujeto": "artifact bytes (wheel)"}}
    if bytes_artefacto is None:
        return {**base, "estado": "NO_MEDIDO",
                "motivo": "el modelo se ajusto sobre bytes de artefacto (wheel); un arbol "
                          "en disco no es ese sujeto. Aplicarlo aqui seria un segundo sujeto "
                          "bajo la misma llave (lote 4: attrs, dos subarboles, un bytes).",
                "que_falta": "ajustar el mismo modelo sobre bytes de codigo escaneado y "
                             "pre-registrar su error antes de cotizar arboles en disco"}
    predicho = a + b * bytes_artefacto
    return {**base, "estado": "MEDIDO", "bytes_artefacto": bytes_artefacto,
            "predicho_s": round(predicho, 4),
            "intervalo_s": [round(predicho * (1 - q), 4), round(predicho * (1 + q), 4)],
            "semicerco_relativo": round(q, 4)}


def _precio(tarifa: dict | None, unidades: dict) -> dict:
    """Counts times coefficients. No coefficient, no price -- there is no default."""
    if tarifa is None:
        return {"estado": "NO_COTIZADO",
                "motivo": "no hay tarifa firmada: el instrumento no inventa coeficientes",
                "unidades_facturables": unidades}
    if tarifa.get("firmada") is not True:
        # Un ejemplo y una tarifa se parecen demasiado: la unica diferencia
        # legible por una maquina es la palabra, asi que la palabra manda.
        return {"estado": "NO_COTIZADO",
                "motivo": "la tarifa no esta firmada (firmada != true): un ejemplo no cotiza",
                "unidades_facturables": unidades}
    faltan = [u for u in unidades if u not in tarifa.get("coeficientes", {})]
    if faltan:
        return {"estado": "NO_COTIZADO", "motivo": f"la tarifa no cubre {faltan}",
                "unidades_facturables": unidades}
    total = sum(unidades[u] * tarifa["coeficientes"][u] for u in unidades)
    return {"estado": "COTIZADO", "moneda": tarifa.get("moneda", "MXN"),
            "tarifa_digest": hashlib.sha256(
                json.dumps(tarifa, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
            "detalle": [{"unidad": u, "conteo": unidades[u],
                         "coeficiente": tarifa["coeficientes"][u],
                         "subtotal": unidades[u] * tarifa["coeficientes"][u]} for u in unidades],
            "total": total}


def cotizar(arbol: Path, calibracion: Path | None = CALIBRACION, tarifa: Path | None = None,
            repeticiones: int = 3, bytes_artefacto: int | None = None) -> dict:
    if not arbol.exists():
        raise FileNotFoundError(arbol)
    digest, bytes_py, ficheros = _manifiesto(arbol)
    medido = _tiempo(arbol, repeticiones)
    celda = medido["celda"]
    unidades = {"sitios": celda["sites"] if "sites" in celda else celda["candidates"],
                "claves": len(celda["claves"]), "ficheros": celda["files"]}
    cal = json.loads(calibracion.read_text(encoding="utf-8")) if calibracion else None
    tar = json.loads(tarifa.read_text(encoding="utf-8")) if tarifa else None
    return {"schema": ESQUEMA,
            "sujeto": {"arbol": str(arbol), "manifiesto_sha256": digest,
                       "bytes_py": bytes_py, "ficheros": ficheros},
            "conteos": {k: celda[k] for k in
                        ("files", "stores", "pierde", "candidates", "admitted", "column_loci",
                         "guardadas", "acumulacion", "posicional", "sin_len", "loops",
                         "rc", "rc_certificado", "reconciles", "certifica")},
            "unidades_facturables": unidades,
            "reloj": {k: medido[k] for k in ("wall_min", "cpu_min", "repeticiones",
                                             "wall_muestras", "cpu_muestras", "determinista")},
            "tiempo": _banda(cal, bytes_artefacto) if cal else
                      {"estado": "NO_MEDIDO", "motivo": "sin archivo de calibracion"},
            "precio": _precio(tar, unidades),
            "medido_en": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def _rc(cotizacion: dict) -> int:
    """The price ladder, not the scan's: a quote nobody can invoice is not clean."""
    if cotizacion["precio"]["estado"] == "COTIZADO":
        return OK
    return NO_MEDIDO


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Quote a tree in the unit that reproduces.")
    ap.add_argument("--arbol", required=True, help="tree to scan")
    ap.add_argument("--out", help="write the quote here (default: stdout)")
    ap.add_argument("--tarifa", help="signed coefficients; without it the price is NO_COTIZADO")
    ap.add_argument("--calibracion", default=str(CALIBRACION))
    ap.add_argument("--bytes-artefacto", type=int, default=None,
                    help="artifact bytes when the subject is a wheel; enables the forecast")
    ap.add_argument("--repeticiones", type=int, default=3)
    a = ap.parse_args(argv)
    try:
        q = cotizar(Path(a.arbol), Path(a.calibracion), Path(a.tarifa) if a.tarifa else None,
                    a.repeticiones, a.bytes_artefacto)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"RUPTURA: {exc}")
        return RUPTURA
    texto = json.dumps(q, ensure_ascii=False, indent=1, sort_keys=True)
    if a.out:
        Path(a.out).write_text(texto + "\n", encoding="utf-8")
    else:
        print(texto)
    rc = _rc(q)
    print(f"precio: {q['precio']['estado']} · tiempo: {q['tiempo']['estado']} · "
          f"conteos: {q['conteos']['files']} ficheros, {q['unidades_facturables']['sitios']} sitios",
          file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
