"""Batch 7: the instrument's jitter, per subject.

Batch 6 compared the band's half-width against the clock's jitter on a single
tree, so ``publicable`` there was a property of one subject. A quote is per
subject, so this measures the clock on the five subjects fixed in
``prediccion-batch-7.json`` -- chosen by *predicted* time, which is a function of
``bytes_py``, never by a clock -- with the same nine-blocks-of-ten protocol.

Nothing is refitted and nothing is re-timed for the model: coefficients, ``q`` and
the twenty clocks are batch 6's. What is new is the noise floor of each subject.

    python bench/ruido.py --dir /tmp/censo7 --artefacto

The subject pins are the prediction's, and a subject whose ``bytes_py`` no longer
matches its pin is not measured: the wheel would be a different object under the
same name.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import time
from pathlib import Path

import replay_censo
from replay_censo import NO_MEDIDO, OK, RUPTURA
from sujeto import _arbol, _bytes_py, _ruido

RAIZ = replay_censo.RAIZ
PREDICCION = RAIZ / "prediccion-batch-7.json"
ARTEFACTO6 = RAIZ / "fuera-de-dominio-6.json"
ARTEFACTO = RAIZ / "fuera-de-dominio-7.json"
ESQUEMA = "fiber-ast-lint/fuera-de-dominio/1"


def _git_blob(ruta: Path) -> str | None:
    p = subprocess.run(["git", "-C", str(RAIZ), "hash-object", str(ruta)],
                       capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None


def _fila(sexto: dict, s: dict) -> dict | None:
    """The batch-6 row that names the wheel for this pinned subject."""
    for r in sexto["rows"]:
        if (r["package"], r["scope"]) == (s["package"], s["scope"]):
            return r
    return None


def medir(cache: Path, progreso: Path) -> tuple[list[dict], int]:
    pred = json.loads(PREDICCION.read_text(encoding="utf-8"))
    sexto = json.loads(ARTEFACTO6.read_text(encoding="utf-8"))
    m = sexto["modelos"]["codigo"]
    q = sexto["banda"]["codigo"]["q"]
    out, peor = [], OK
    for s in pred["subjects"]:
        fila = _fila(sexto, s)
        if fila is None:
            print(f"  RUPTURA: {s['package']}/{s['scope']} no esta en el lote 6")
            peor = RUPTURA
            continue
        arbol, rc = _arbol(cache, fila)
        if rc != OK:
            print(f"  {'NO_MEDIDO' if rc == NO_MEDIDO else 'RUPTURA'}: {s['package']}")
            peor = rc
            continue
        bytes_py, ficheros_py = _bytes_py(arbol)
        if bytes_py != s["bytes_py"]:
            # The pin is the subject: a different byte count is a different object.
            print(f"  RUPTURA: {s['package']}/{s['scope']} pin {s['bytes_py']} != {bytes_py}")
            peor = RUPTURA
            continue
        predicho = round(m["a"] + m["b"] * bytes_py, 4)
        if predicho != s["predicho_s"]:
            print(f"  RUPTURA: {s['package']} predicho {s['predicho_s']} != {predicho}")
            peor = RUPTURA
            continue
        t0 = time.perf_counter()
        ruido = _ruido(arbol, 10, 9)
        jitter = ruido["jitter_s"]
        semianchura = round(predicho * q, 4)
        fila_out = {
            "package": s["package"], "scope": s["scope"], "version": fila["version"],
            "artifact": fila["artifact"], "sha256": fila["sha256"],
            "bytes_py_pin": s["bytes_py"], "bytes_py": bytes_py,
            "ficheros_py": ficheros_py, "pin_ok": True,
            "predicho_s": predicho, "cpu_min_lote6": fila["cpu_min"], "q": q,
            "bloques": ruido["bloques"], "n_bloques": ruido["n_bloques"],
            "relojes": ruido["n_bloques"] * ruido["bloques"][0]["n"],
            "jitter_s": jitter, "jitter_p50_s": ruido["jitter_p50_s"],
            "jitter_min_s": ruido["jitter_min_s"],
            "p50_min_s": ruido["p50_min_s"], "p50_max_s": ruido["p50_max_s"],
            "dispersion": ruido["dispersion"],
            "semianchura_s": semianchura,
            "jitter_relativo": round(jitter / predicho, 4),
            "publicable": semianchura > jitter,
            "minimo_publicable_s": round(jitter / q, 4),
            "en_banda": abs(fila["cpu_min"] - predicho) / predicho <= q,
            "segundos_de_pared": round(time.perf_counter() - t0, 1),
        }
        out.append(fila_out)
        progreso.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  {s['package'] + '/' + s['scope']:<22} jitter {jitter:>7.4f} s · "
              f"rel {fila_out['jitter_relativo']:>6.4f} · semianchura {semianchura:>8.4f} s · "
              f"publicable {'si' if fila_out['publicable'] else 'NO'} "
              f"({fila_out['segundos_de_pared']} s)", flush=True)
    return out, peor


def _veredictos(sujetos: list[dict], pred: dict) -> list[dict]:
    por = {f"{s['package']}/{s['scope']}": s for s in sujetos}
    pequeno = "attrs/attrs"
    grandes = ["setuptools/setuptools", "pygments/pygments"]
    j1 = pred["predictions"][0]
    j2 = pred["predictions"][1]
    j3 = pred["predictions"][2]
    q = sujetos[0]["q"]
    return [
        {"id": "J1", "sujeto": pequeno, "umbral": q,
         "medido": por[pequeno]["jitter_relativo"],
         "sobrevive": por[pequeno]["jitter_relativo"] > q,
         "evalua": j1["claim"]},
        {"id": "J2", "sujetos": grandes, "umbral": j2["umbral"],
         "medido": {g: por[g]["jitter_relativo"] for g in grandes},
         "sobrevive": all(por[g]["jitter_relativo"] < j2["umbral"] for g in grandes),
         "evalua": j2["claim"]},
        {"id": "J3", "umbral": j3["umbral"],
         "medido": {k: s["jitter_p50_s"] for k, s in por.items()},
         "sobrevive": all(j3["umbral"][0] <= s["jitter_p50_s"] <= j3["umbral"][1]
                          for s in sujetos),
         "evalua": j3["claim"]},
    ]


def artefacto(sujetos: list[dict], pred: dict) -> dict:
    doc = {
        "schema": ESQUEMA, "lote": 7, "title": "el ruido del instrumento por sujeto",
        "prediction": {"archivo": PREDICCION.name,
                       "sha256": hashlib.sha256(PREDICCION.read_bytes()).hexdigest(),
                       "git_blob": _git_blob(PREDICCION),
                       "declared_before_computation": pred["declared_before_computation"]},
        "metodo": ("cinco sujetos fijados por tiempo predicho; nueve bloques de diez lecturas "
                   "por sujeto con cotizar._tiempo(arbol, 3); coeficientes y q del lote 6 sin "
                   "reajustar; ningun reloj de estos sujetos intervino en su eleccion"),
        "sujetos": sujetos,
        "escala": {
            "bytes_py": {s["package"]: s["bytes_py"] for s in sujetos},
            "jitter_s": {s["package"]: s["jitter_s"] for s in sujetos},
            "jitter_por_megabyte_s": {s["package"]: round(s["jitter_s"] / (s["bytes_py"] / 1e6), 4)
                                      for s in sujetos},
            "jitter_relativo": {s["package"]: s["jitter_relativo"] for s in sujetos},
            "dispersion_jitter": round(max(s["jitter_s"] for s in sujetos)
                                       / min(s["jitter_s"] for s in sujetos), 4),
            "dispersion_bytes": round(max(s["bytes_py"] for s in sujetos)
                                      / min(s["bytes_py"] for s in sujetos), 1),
            "nota": ("si el jitter fuera una constante de la maquina, `dispersion_jitter` seria "
                     "cercano a 1 mientras `dispersion_bytes` es de tres ordenes: ese es el "
                     "contraste que separa piso fijo de ruido proporcional, y se lee aqui sin "
                     "ajustar nada"),
        },
        "veredictos": _veredictos(sujetos, pred),
        "cost": {"sujetos": len(sujetos),
                 "relojes_por_sujeto": sujetos[0]["relojes"],
                 "relojes_totales": sum(s["relojes"] for s in sujetos),
                 "segundos_de_pared": round(sum(s["segundos_de_pared"] for s in sujetos), 1),
                 "clones_externos": 0, "escrituras_en_platino_labs": 0,
                 "medido_en": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
    }
    v = doc["veredictos"]
    sobre = [x["id"] for x in v if x["sobrevive"]]
    caen = [x["id"] for x in v if not x["sobrevive"]]
    publicables = [s["package"] for s in sujetos if s["publicable"]]
    doc["predictions_summary"] = {
        "sobreviven": sobre, "caen": caen,
        "rama": ("todas_sobreviven" if not caen else
                 "ninguna_sobrevive" if not sobre else "parcial"),
        "publicables": publicables,
        "lo_que_cambio": ("`publicable` deja de ser una cifra del lote y pasa a ser una "
                          "funcion del sujeto: el recibo puede decir, por arbol, si su "
                          "intervalo tiene grados de libertad"
                          if "J1" in sobre else
                          "el jitter no domina ni en el sujeto mas pequeno: la banda manda en "
                          "todo el rango y la comparacion del lote 6 era un caso, no una ley"),
    }
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure the clock's jitter on the pinned subjects.")
    ap.add_argument("--dir", required=True, help="cache directory for the wheels")
    ap.add_argument("--artefacto", action="store_true",
                    help=f"write {ARTEFACTO.name} with the verdicts")
    a = ap.parse_args(argv)
    cache = Path(a.dir)
    cache.mkdir(parents=True, exist_ok=True)
    pred = json.loads(PREDICCION.read_text(encoding="utf-8"))
    print(f"lote 7 · {len(pred['subjects'])} sujetos · "
          f"{pred['cost']['relojes_por_sujeto']} relojes cada uno", flush=True)
    sujetos, peor = medir(cache, cache / "progreso-7.json")
    if len(sujetos) != len(pred["subjects"]):
        print(f"NO_MEDIDO: {len(sujetos)} de {len(pred['subjects'])} sujetos")
        return NO_MEDIDO
    doc = artefacto(sujetos, pred)
    if a.artefacto:
        ARTEFACTO.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"artefacto: {ARTEFACTO.name} · veredictos " +
              " ".join(f"{x['id']}={'si' if x['sobrevive'] else 'NO'}" for x in doc["veredictos"]))
    return peor


if __name__ == "__main__":
    raise SystemExit(main())
