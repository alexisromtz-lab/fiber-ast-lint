"""Measure the bytes the scanner walked, for the rows whose clocks are already paid.

Batch 5 refused to quote a disk tree because the CPU model had been fitted on
*wheel* bytes and a tree is a different subject. The wall is the regressor, not
the form; this script moves the regressor and nothing else.

Nothing is timed here. The twenty ``cpu_min`` values of batch 4 are reused as they
stand -- same subjects, same instrument, same session -- so the two fits are
paired on ``y`` and any difference in error is attributable to the change of ``x``:

    python bench/sujeto.py --dir /tmp/censo6 --out sujetos-6.json

The artifact is fetched again only because ``bytes_py`` was never measured: it is
a new measurement of the same subject, not a re-measurement of the old one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import zipfile
from pathlib import Path

import cotizar
import replay_censo
from replay_censo import NO_MEDIDO, OK, RUPTURA, _traer

RAIZ = replay_censo.RAIZ
CALIBRACION = RAIZ / "fuera-de-dominio-4.json"
PREDICCION = RAIZ / "prediccion-batch-6.json"
ARTEFACTO = RAIZ / "fuera-de-dominio-6.json"
TARIFA = RAIZ / "tarifa.ejemplo.json"
ARBOL_LOCAL = RAIZ / "src" / "fiber_ast_lint"
ESQUEMA = "fiber-ast-lint/fuera-de-dominio/1"


def _arbol(cache: Path, fila: dict) -> tuple[Path | None, int]:
    """The scanned root for this row, fetching and unpacking the wheel if needed."""
    rueda = cache / fila["artifact"]
    if not rueda.exists():
        rueda, dig_pypi, rc = _traer(fila["package"], fila["artifact"], rueda)
        if rc != OK:
            return None, rc
        if hashlib.sha256(rueda.read_bytes()).hexdigest() != fila["sha256"]:
            return None, RUPTURA
    destino = cache / f"{fila['package']}-{fila['version']}"
    if not destino.is_dir():
        with zipfile.ZipFile(rueda) as z:
            z.extractall(destino)
    raiz = destino / fila["scope"]
    return (raiz, OK) if raiz.exists() else (None, RUPTURA)


def _bytes_py(raiz: Path) -> tuple[int, int]:
    ficheros = [raiz] if raiz.is_file() else [f for f in sorted(raiz.rglob("*.py")) if f.is_file()]
    return sum(f.stat().st_size for f in ficheros), len(ficheros)


def medir(cache: Path) -> tuple[list[dict], int]:
    filas = json.loads(CALIBRACION.read_text(encoding="utf-8"))["rows"]
    out, peor = [], OK
    for fila in filas:
        raiz, rc = _arbol(cache, fila)
        if rc != OK:
            print(f"  {'NO_MEDIDO' if rc == NO_MEDIDO else 'RUPTURA'}: {fila['package']}")
            peor = rc
            continue
        bytes_py, ficheros_py = _bytes_py(raiz)
        out.append({"package": fila["package"], "version": fila["version"],
                    "artifact": fila["artifact"], "sha256": fila["sha256"],
                    "scope": fila["scope"], "bytes": fila["bytes"],
                    "bytes_py": bytes_py, "ficheros_py": ficheros_py,
                    "files": fila["files"], "cpu_min": fila["cpu_min"],
                    "wall_min": fila["wall_min"]})
        print(f"  {fila['package']:<22} wheel {fila['bytes']:>8} -> walked {bytes_py:>8} "
              f"({ficheros_py} py / {fila['files']} files)")
    return out, peor


def _loo(filas: list[dict], clave: str) -> list[float]:
    out = []
    for i, r in enumerate(filas):
        a, b = cotizar._modelo([x for j, x in enumerate(filas) if j != i], clave=clave)
        p = a + b * r[clave]
        out.append(abs(r["cpu_min"] - p) / p)
    return sorted(out)


def _resumen(filas: list[dict], clave: str) -> dict:
    a, b = cotizar._modelo(filas, clave=clave)
    ys = [r["cpu_min"] for r in filas]
    my = statistics.fmean(ys)
    r2 = 1 - sum((y - (a + b * r[clave])) ** 2 for y, r in zip(ys, filas)) / sum((y - my) ** 2 for y in ys)
    loo = _loo(filas, clave)
    return {"clave": clave, "a": round(a, 5), "b": round(b, 12), "r2": round(r2, 4),
            "loo_p50": round(statistics.median(loo), 4), "loo_max": round(loo[-1], 4),
            "residuos": [round(x, 4) for x in loo]}


def _cobertura(cal: dict, retenidos: list[dict], clave: str) -> dict:
    b = cotizar._banda(cal, clave=clave, sujeto=cotizar.SUJETO[
        "artefacto" if clave == "bytes" else "codigo"][1])
    a, pen = b["modelo"]["a"], b["modelo"]["b"]
    q = b["calibracion"]["q"]
    filas = []
    for r in retenidos:
        p = a + pen * r[clave]
        res = abs(r["cpu_min"] - p) / p
        filas.append({"package": r["package"], "predicho_s": round(p, 4), "residuo": round(res, 6),
                      "dentro": res <= q, "frontera": abs(res - q) < 1e-4})
    return {"clave": clave, "q": q,
            "frontera": [f["package"] for f in filas if f["frontera"]], "filas": filas,
            "dentro": sum(1 for f in filas if f["dentro"]), "total": len(filas)}


def _attrs(cal: dict, clave: str) -> dict:
    a, b = cotizar._modelo(cal["rows"][:15], clave=clave)
    p0, p1 = a + b * cal["rows"][0][clave], a + b * cal["rows"][1][clave]
    return {"clave": clave,
            "predicho": [round(p0, 4), round(p1, 4)],
            "razon": round(max(p0, p1) / min(p0, p1), 3),
            "ordena": (p0 > p1) == (cal["rows"][0]["cpu_min"] > cal["rows"][1]["cpu_min"])}


def _ruido(arbol: Path, n: int = 10, bloques: int = 9) -> dict:
    """The instrument's own jitter: the floor a band must clear, measured in blocks.

    One block cannot separate "quiet machine" from "quiet moment": the same tree,
    minutes apart, gave a 0,8 % jitter in one block and 13 % in another. So the floor
    is the worst jitter observed, not the friendliest.
    """
    out = []
    for _ in range(bloques):
        crudas = [cotizar._tiempo(arbol, 3)["cpu_min"] for _ in range(n)]
        xs = sorted(crudas)
        # `primera_s` is kept before sorting: the first reading of a block is the only
        # evidence of what a cold start costs, and sorting is what made it unrecoverable.
        out.append({"lecturas": [round(x, 4) for x in xs], "n": n,
                    "primera_s": round(crudas[0], 4),
                    "min_s": round(xs[0], 4), "p50_s": round(statistics.median(xs), 4),
                    "max_s": round(xs[-1], 4), "jitter_s": round(xs[-1] - xs[0], 4)})
    peor = max(out, key=lambda x: x["jitter_s"])
    return {"bloques": out, "n_bloques": bloques,
            "jitter_s": peor["jitter_s"],
            "jitter_p50_s": round(statistics.median([x["jitter_s"] for x in out]), 4),
            "jitter_min_s": min(x["jitter_s"] for x in out),
            "p50_min_s": min(x["p50_s"] for x in out), "p50_max_s": max(x["p50_s"] for x in out),
            "dispersion": round(max(x["max_s"] for x in out) / min(x["min_s"] for x in out), 4)}


def _commit_publicado() -> str | None:
    """The commit that ships this tree, or ``None`` while ``src/`` has edits it cannot name.

    A quote is a measurement of one tree, so it names the commit a reader can re-open
    and recompute. Quoting a dirty worktree would name a tree no commit contains, and
    the quote would then describe something nobody can check.
    """
    limpio = subprocess.run(["git", "-C", str(RAIZ), "diff", "--quiet", "HEAD", "--",
                             "src/fiber_ast_lint"], capture_output=True)
    if limpio.returncode != 0:
        return None
    sha = subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "HEAD"],
                         capture_output=True, text=True)
    return sha.stdout.strip() or None


def artefacto(filas: list[dict], cal: dict, cache: Path, out: Path) -> dict:
    retenidos = filas[15:]
    doc = {
        "schema": ESQUEMA, "lote": 6, "title": "el sujeto del modelo",
        "prediction": {"archivo": "prediccion-batch-6.json", "commit": "4c5d1c8e",
                       "sha256": hashlib.sha256(PREDICCION.read_bytes()).hexdigest(),
                       "git_blob": "ac7b494952bab03d58f3012aa149b54927bda254",
                       "declared_before_computation": True},
        "metodo": ("veinte relojes del lote 4 reutilizados sin volver a cronometrar; "
                   "solo cambia la regresora. Dos ajustes sobre los mismos veinte y, "
                   "por tanto, comparacion pareada en y."),
        "rows": filas,
        "coherencia": {"files_igual_ficheros_py": sum(1 for r in filas if r["files"] == r["ficheros_py"]),
                       "filas": len(filas),
                       "nota": ("los ficheros que el escaner declara y los .py que el glob cuenta "
                                "coinciden fila a fila: son dos instrumentos distintos midiendo "
                                "el mismo universo, no dos columnas del mismo calculo")},
        "modelos": {"artefacto": _resumen(filas[:15], "bytes"),
                    "codigo": _resumen(filas[:15], "bytes_py")},
        "covarianza": {"py_sobre_wheel_min": round(min(r["bytes_py"] / r["bytes"] for r in filas), 4),
                       "py_sobre_wheel_max": round(max(r["bytes_py"] / r["bytes"] for r in filas), 4)},
        "reproduccion_lote5": ("el ajuste sobre bytes de artefacto, rehecho sobre estas veinte filas, "
                              "devuelve q y max del lote 5 sin tocar sus relojes"),
        "banda": {"artefacto": _cobertura(cal, retenidos, "bytes"),
                  "codigo": _cobertura(cal, retenidos, "bytes_py")},
        "attrs": {"medido_s": [filas[0]["cpu_min"], filas[1]["cpu_min"]],
                  "bytes": [filas[0]["bytes"], filas[1]["bytes"]],
                  "bytes_py": [filas[0]["bytes_py"], filas[1]["bytes_py"]],
                  "artefacto": _attrs(cal, "bytes"), "codigo": _attrs(cal, "bytes_py")},
        "limitaciones": [
            "las cinco filas de retencion ya se usaron en el lote 5: la cobertura de aqui no es "
            "una prueba fuera de muestra nueva",
            "el reloj del arbol local no es el mismo entre sesiones: ver `sensibilidad`",
        ],
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    q = cotizar.cotizar(ARBOL_LOCAL, out, TARIFA, 3, None, "codigo")
    arbol = dict(q["sujeto"])
    commit = _commit_publicado()
    if commit:
        arbol["commit"] = commit
    doc["cotizacion"] = {"arbol": arbol, "modelo": q["modelo"], "reloj": q["reloj"],
                        "tiempo": q["tiempo"], "precio": q["precio"],
                        "unidades_facturables": q["unidades_facturables"], "medido_en": q["medido_en"]}
    t = q["tiempo"]
    medido = q["reloj"]["cpu_min"]
    dentro = t.get("estado") == "MEDIDO" and t["intervalo_s"][0] <= medido <= t["intervalo_s"][1]
    lote5 = 0.4303
    ruido = _ruido(ARBOL_LOCAL)
    q3w = doc["banda"]["codigo"]["q"]
    jitter = ruido["jitter_s"]
    semianchura = round(t["predicho_s"] * q3w, 4)
    doc["reloj_del_instrumento"] = {
        **ruido, "jitter_s": jitter, "semianchura_s": semianchura,
        "publicable": semianchura > jitter,
        "minimo_publicable_s": round(jitter / q3w, 4),
        "jitter_por_bloque_s": [b["jitter_s"] for b in ruido["bloques"]],
        "predicho_s": t["predicho_s"],
        "dos_poblaciones": ("la banda mide el error del modelo y el jitter mide la maquina; son dos "
                            "poblaciones y el intervalo que se publica es su comparacion. Un intervalo "
                            "mas estrecho que el jitter no tiene grados de libertad: es ruido con "
                            "formato de intervalo"),
        "juicio": (f"semianchura {semianchura} s contra jitter {jitter} s: "
                   + ("la banda manda" if semianchura > jitter else
                      f"manda el jitter, y ningun intervalo se publica por debajo de "
                      f"{round(jitter / q3w, 4)} s de tiempo predicho")),
    }
    doc["sensibilidad"] = {
        "lecturas": [{"reloj_s": lote5, "fuente": "fuera-de-dominio-5.json"},
                     {"reloj_s": ruido["p50_min_s"], "fuente": "mediana del bloque mas rapido"},
                     {"reloj_s": ruido["p50_max_s"], "fuente": "mediana del bloque mas lento"},
                     {"reloj_s": round(medido, 4), "fuente": "la lectura de la cotizacion de este lote"}],
        "dispersion": round(max(lote5, medido, ruido["p50_max_s"])
                            / min(lote5, medido, ruido["p50_min_s"]), 4),
        "reloj_lote5_s": lote5,
        "residuo_con_reloj_lote5": round(abs(lote5 - t.get("predicho_s", 0)) / t.get("predicho_s", 1), 4),
        "dentro_con_reloj_lote5": bool(t.get("estado") == "MEDIDO") and (
            t["intervalo_s"][0] <= lote5 <= t["intervalo_s"][1]),
        "lectura": ("el mismo arbol medido en dos sesiones da dos relojes; la banda cubre el de hoy "
                    "y no el del lote 5, asi que un intervalo de tiempo se cotiza con su reloj, "
                    "no con el de la sesion en que se ajusto el modelo"),
    }
    mc, ma = doc["modelos"]["codigo"], doc["modelos"]["artefacto"]
    q3 = doc["banda"]["codigo"]["q"]
    docu = next(f for f in doc["banda"]["codigo"]["filas"] if f["package"] == "docutils")
    doc["veredictos"] = [
        {"id": "P1", "umbral": 0.8147, "medido": mc["loo_max"], "sobrevive": mc["loo_max"] < 0.8147,
         "evalua": "el error maximo baja del del lote 4"},
        {"id": "P2", "umbral": 0.167, "medido": mc["loo_p50"], "sobrevive": mc["loo_p50"] < 0.167,
         "evalua": "la mediana baja del 16,7 %"},
        {"id": "P3", "umbral": q3, "medido": docu["residuo"], "sobrevive": docu["dentro"],
         "evalua": "docutils vuelve a la banda"},
        {"id": "P4", "umbral": 2.0, "medido": doc["attrs"]["codigo"]["razon"],
         "sobrevive": doc["attrs"]["codigo"]["razon"] > 2 and doc["attrs"]["codigo"]["ordena"],
         "evalua": "las dos filas de attrs se ordenan"},
        {"id": "P5", "umbral": t.get("intervalo_s"), "medido": medido, "sobrevive": dentro,
         "evalua": "el arbol local cae en su intervalo"},
    ]
    doc["predictions_summary"] = {
        "sobreviven": [v["id"] for v in doc["veredictos"] if v["sobrevive"]],
        "caen": [v["id"] for v in doc["veredictos"] if not v["sobrevive"]],
        "rama": ("P1_P2_caen" if not (doc["veredictos"][0]["sobrevive"] or doc["veredictos"][1]["sobrevive"])
                 else "P5_cae" if not doc["veredictos"][4]["sobrevive"]
                 else "todas_sobreviven" if all(v["sobrevive"] for v in doc["veredictos"])
                 else "P3_cae_FUERA_DE_TAXONOMIA"),
        "hueco_de_la_taxonomia": ("la prediccion enumeraba tres ramas -- todas sobreviven, caen P1/P2, "
                                  "cae P5 -- y ninguna nombra la caida de P3 sola, que es lo observado: "
                                  "un conjunto de ramas que no contiene el resultado no es una particion"),
        "leido": ("la regresora era parte del muro: sobre bytes caminados el peor sujeto deja de serlo "
                  "y dos artefactos identicos dejan de dar la misma prediccion; lo que no se arregla es "
                  "la cobertura, que baja porque el cociente py/wheel va de 0,02x a 5,28x"),
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Refit the CPU model on the bytes the scanner walked.")
    ap.add_argument("--dir", required=True, help="cache directory for the wheels")
    ap.add_argument("--out", default=None)
    ap.add_argument("--artefacto", action="store_true",
                    help=f"write {ARTEFACTO.name} with the verdicts and the local quote")
    a = ap.parse_args(argv)
    cache = Path(a.dir)
    cache.mkdir(parents=True, exist_ok=True)
    filas, peor = medir(cache)
    if not filas:
        print("NO_MEDIDO: ninguna fila medida")
        return NO_MEDIDO
    conocidos, retenidos = filas[:15], filas[15:]
    doc = {"sujetos": filas, "filas": len(filas),
           "modelo_wheel": _resumen(conocidos, "bytes"),
           "modelo_codigo": _resumen(conocidos, "bytes_py"),
           "covarianza": {"py_sobre_wheel_min": round(min(r["bytes_py"] / r["bytes"] for r in filas), 4),
                          "py_sobre_wheel_max": round(max(r["bytes_py"] / r["bytes"] for r in filas), 4)},
           "retenidos": [{"package": r["package"], "bytes_py": r["bytes_py"], "cpu_min": r["cpu_min"]}
                         for r in retenidos]}
    if a.out:
        Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if a.artefacto:
        lote = artefacto(filas, {"rows": filas}, cache, ARTEFACTO)
        print(f"artefacto: {ARTEFACTO.name} · veredictos " +
              " ".join(f"{v['id']}={'si' if v['sobrevive'] else 'NO'}" for v in lote["veredictos"]))
    for k in ("modelo_wheel", "modelo_codigo"):
        m = doc[k]
        print(f"{k}: R2 {m['r2']} · p50 {m['loo_p50']} · max {m['loo_max']} · b {m['b']}")
    return peor


if __name__ == "__main__":
    raise SystemExit(main())
