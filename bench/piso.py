"""Batch 8: the quote measures its own floor.

Batch 7 timed the clock on five subjects and none of them was quotable, with
``jitter / predicho`` between 0,3418 and 0,8163 against ``q`` = 0,3018. That
quotient does not order by size -- the largest tree gives the tightest one -- so it
is not a property of the subject. If the floor is a reading of the machine taken
during the act, two acts on one subject must disagree; if it is a property of the
subject, they must agree.

This instrument answers that with a single subject and two acts. Act A is the
ninety clocks batch 7 already paid for on ``pyflakes/pyflakes``; they are reused
as they stand, never re-timed, so the comparison is paired. Act B is the same
protocol, the same pin, another window. Nothing is refitted:

    python bench/piso.py --dir /tmp/censo8 --artefacto

``--desde PROGRESO`` recomposes the document from readings already paid: act B is
read back from the file and act A is rebuilt from the sealed batch-7 artifact, so
a recomposition can never quietly become a second act. The act is run once.
Choosing the window after seeing ``k_B`` would turn the disjunction into an
announcement.
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
from replay_censo import OK, RUPTURA
from sujeto import _arbol, _bytes_py, _ruido

RAIZ = replay_censo.RAIZ
PREDICCION = RAIZ / "prediccion-batch-8.json"
ARTEFACTO6 = RAIZ / "fuera-de-dominio-6.json"
ARTEFACTO7 = RAIZ / "fuera-de-dominio-7.json"
ARTEFACTO = RAIZ / "fuera-de-dominio-8.json"
ESQUEMA = "fiber-ast-lint/fuera-de-dominio/1"
SUJETO = ("pyflakes", "pyflakes")


def _git_blob(ruta: Path) -> str | None:
    p = subprocess.run(["git", "-C", str(RAIZ), "hash-object", str(ruta)],
                       capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None


def _lecturas(bloques: list[dict]) -> list[float]:
    return [x for b in bloques for x in b["lecturas"]]


def _resumen(b: dict, predicho: float, q: float) -> dict:
    """Every summary figure recomputed from the ten readings of each block, never inherited."""
    bloques = b["bloques"]
    lecturas = sorted(_lecturas(bloques))
    jit = [x["jitter_s"] for x in bloques]
    jitter = max(jit)
    return {
        "n_bloques": len(bloques), "relojes": len(lecturas),
        "jitter_s": jitter, "jitter_p50_s": round(statistics.median(jit), 4),
        "jitter_min_s": min(jit),
        "p50_min_s": min(x["p50_s"] for x in bloques),
        "p50_max_s": max(x["p50_s"] for x in bloques),
        "dispersion": round(max(x["max_s"] for x in bloques)
                            / min(x["min_s"] for x in bloques), 4),
        "jitter_relativo": round(jitter / predicho, 4),
        "publicable": round(predicho * q, 4) > jitter,
        "minimo_s": round(lecturas[0], 4), "maximo_s": round(lecturas[-1], 4),
        "mediana_s": round(statistics.median(lecturas), 4), "lecturas_n": len(lecturas),
    }


def _acto_a(septimo: dict, package: str, scope: str) -> dict | None:
    """Batch 7's row for this subject, with its ninety readings carried as they were paid."""
    for s in septimo["sujetos"]:
        if (s["package"], s["scope"]) == (package, scope):
            lecturas = sorted(_lecturas(s["bloques"]))
            a = {
                "sujeto": f"{package}/{scope}", "package": package, "scope": scope,
                "version": s["version"], "artifact": s["artifact"], "sha256": s["sha256"],
                "bytes_py_pin": s["bytes_py_pin"], "predicho_s": s["predicho_s"],
                "q": s["q"], "bloques": s["bloques"],
                "lecturas": [round(x, 4) for x in lecturas],
                "sellado_lote_7": {k: s[k] for k in (
                    "n_bloques", "relojes", "jitter_s", "jitter_p50_s", "jitter_min_s",
                    "p50_min_s", "p50_max_s", "dispersion", "semianchura_s",
                    "jitter_relativo", "publicable", "minimo_publicable_s", "en_banda")},
            }
            a.update(_resumen(a, s["predicho_s"], s["q"]))
            a["semianchura_s"] = round(s["predicho_s"] * s["q"], 4)
            a["minimo_publicable_s"] = round(a["jitter_s"] / s["q"], 4)
            # `en_banda` es el control del modelo —el costo del lote 6 dentro de la
            # banda— y no la condicion de ruido, que es `publicable`.
            a["cpu_min_lote6"] = s["cpu_min_lote6"]
            a["en_banda"] = abs(s["cpu_min_lote6"] - s["predicho_s"]) / s["predicho_s"] <= s["q"]
            return a
    return None


def _frame(sexto: dict, septimo: dict) -> tuple[dict | None, int]:
    """The paired frame: act A, with the batch-6 model and q re-checked against it."""
    a = _acto_a(septimo, *SUJETO)
    if a is None:
        print(f"  RUPTURA: {SUJETO[0]}/{SUJETO[1]} no esta en el lote 7")
        return None, RUPTURA
    m = sexto["modelos"]["codigo"]
    q = sexto["banda"]["codigo"]["q"]
    if a["q"] != q:
        print(f"  RUPTURA: q del acto A {a['q']} != q del lote 6 {q}")
        return None, RUPTURA
    esperado = round(m["a"] + m["b"] * a["bytes_py_pin"], 4)
    if esperado != a["predicho_s"]:
        print(f"  RUPTURA: predicho del acto A {a['predicho_s']} != {esperado} del lote 6")
        return None, RUPTURA
    return a, OK


def medir(cache: Path, progreso: Path, acto_a: dict) -> tuple[dict | None, int]:
    package, scope = SUJETO
    fila = {k: acto_a[k] for k in ("package", "scope", "version", "artifact", "sha256")}
    arbol, rc = _arbol(cache, fila)
    if rc != OK:
        print("  RUPTURA: el arbol del acto B no se pudo componer")
        return None, rc
    bytes_py, ficheros_py = _bytes_py(arbol)
    if bytes_py != acto_a["bytes_py_pin"]:
        print(f"  RUPTURA: pin {acto_a['bytes_py_pin']} != {bytes_py}; el sujeto seria otro objeto")
        return None, RUPTURA

    print(f"  acto B · {package}/{scope} · {bytes_py} B · 9 bloques de 10", flush=True)
    t0 = time.perf_counter()
    ruido = _ruido(arbol, 10, 9)
    pared = round(time.perf_counter() - t0, 1)
    b = {
        "sujeto": f"{package}/{scope}", "package": package, "scope": scope,
        "version": fila["version"], "artifact": fila["artifact"], "sha256": fila["sha256"],
        "bytes_py_pin": acto_a["bytes_py_pin"], "bytes_py": bytes_py, "pin_ok": True,
        "ficheros_py": ficheros_py, "predicho_s": acto_a["predicho_s"], "q": acto_a["q"],
        "bloques": ruido["bloques"],
    }
    b.update(_resumen(b, acto_a["predicho_s"], acto_a["q"]))
    b["segundos_de_pared"] = pared
    progreso.write_text(json.dumps({"acto_a": acto_a, "acto_b": b}, ensure_ascii=False, indent=1)
                        + "\n", encoding="utf-8")
    print(f"  jitter {b['jitter_s']:.4f} s · rel {b['jitter_relativo']:.4f} · "
          f"publicable {'si' if b['publicable'] else 'NO'} ({pared} s)", flush=True)
    return b, OK


def _k(bloques: list[dict], predicho: float) -> float:
    return round(max(x["jitter_s"] for x in bloques) / predicho, 4)


def _comparacion(a: dict, b: dict) -> dict:
    predicho = a["predicho_s"]
    k_a = round(a["jitter_s"] / predicho, 4)
    k_b = round(b["jitter_s"] / predicho, 4)
    k1 = _k(b["bloques"][:4], predicho)
    k2 = _k(b["bloques"][5:], predicho)
    return {
        "predicho_s": predicho, "q": a["q"], "umbral_q_2": round(a["q"] / 2, 4),
        "jitter_A_s": a["jitter_s"], "jitter_B_s": b["jitter_s"],
        "k_A": k_a, "k_B": k_b, "k_primera_mitad": k1, "k_ultima_mitad": k2,
        "delta_mitades": round(abs(k1 - k2), 4),
        "min_A_s": a["minimo_s"], "min_B_s": b["minimo_s"],
        "ratio_min_B_A": round(b["minimo_s"] / a["minimo_s"], 4),
        "ratio_min_A_B": round(a["minimo_s"] / b["minimo_s"], 4),
        "ratio_jitter_A_B": round(a["jitter_s"] / b["jitter_s"], 4),
        "ratio_k_A_B": round(k_a / k_b, 4) if k_b else None,
        "min_sobre_jitter_A": round(a["minimo_s"] / a["jitter_s"], 4),
        "min_sobre_jitter_B": round(b["minimo_s"] / b["jitter_s"], 4),
        "ratio_min_sobre_jitter_A_B": round((a["minimo_s"] / a["jitter_s"])
                                            / (b["minimo_s"] / b["jitter_s"]), 4),
        "dispersion_bloques_B": round(max(x["jitter_s"] for x in b["bloques"])
                                      / min(x["jitter_s"] for x in b["bloques"]), 4),
        "nota": ("`ratio_jitter_A_B` y `dispersion_bloques_B` son descriptivos: la misma "
                 "cantidad medida entre actos y dentro de un acto. K3 no los usa; su "
                 "falsador es la razon de minimos y queda como se pre-registro"),
    }


def _veredictos(comp: dict, pred: dict) -> list[dict]:
    c = comp["comparacion"]
    k1, k2, k3 = pred["predictions"]
    return [
        {"id": "K1", "umbral": k1["umbral"], "medido": {"k_A": c["k_A"], "k_B": c["k_B"]},
         "sobrevive": c["k_B"] < k1["umbral"], "evalua": k1["claim"]},
        {"id": "K2", "umbral": k2["umbral"],
         "medido": {"k_primera_mitad": c["k_primera_mitad"],
                    "k_ultima_mitad": c["k_ultima_mitad"],
                    "delta_mitades": c["delta_mitades"]},
         "sobrevive": c["delta_mitades"] < k2["umbral"], "evalua": k2["claim"]},
        {"id": "K3", "umbral": k3["umbral"],
         "medido": {"min_A_s": c["min_A_s"], "min_B_s": c["min_B_s"],
                    "ratio_min_B_A": c["ratio_min_B_A"]},
         "sobrevive": k3["umbral"][0] <= c["ratio_min_B_A"] <= k3["umbral"][1],
         "evalua": k3["claim"]},
    ]


def artefacto(comp: dict, pred: dict) -> dict:
    a, b = comp["acto_a"], comp["acto_b"]
    veredictos = _veredictos(comp, pred)
    sobre = [x["id"] for x in veredictos if x["sobrevive"]]
    caen = [x["id"] for x in veredictos if not x["sobrevive"]]
    c = comp["comparacion"]
    doc = {
        "schema": ESQUEMA, "lote": 8, "title": "la cotizacion mide su propio piso",
        "prediction": {"archivo": PREDICCION.name,
                       "sha256": hashlib.sha256(PREDICCION.read_bytes()).hexdigest(),
                       "git_blob": _git_blob(PREDICCION),
                       "declared_before_computation": pred["declared_before_computation"]},
        "metodo": ("un sujeto, dos actos pareados: el acto A son los noventa relojes del lote 7 "
                   "reutilizados sin volver a cronometrar y el acto B son noventa relojes nuevos "
                   "sobre el mismo pin, mismo protocolo y otra ventana; q y coeficientes del "
                   "lote 6 sin reajustar; el acto B se corrio una vez y se publica lo que salio"),
        "acto_a": a, "acto_b": b,
        "comparacion": c,
        "veredictos": veredictos,
        "cost": {"sujetos": 1, "actos": 2,
                 "relojes_nuevos": b["relojes"], "relojes_reutilizados": a["relojes"],
                 "relojes_totales": b["relojes"] + a["relojes"],
                 "segundos_de_pared": b["segundos_de_pared"],
                 "clones_externos": 0, "escrituras_en_platino_labs": 0,
                 "medido_en": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
    }
    if "K1" in sobre and "K2" in sobre:
        rama = ("publicable se decide en el acto que cotiza: el piso se mide ahi mismo y la "
                "compuerta cuesta la misma ventana que la cotizacion")
    elif "K1" not in sobre:
        rama = ("K1 cae: su umbral q/2 no es el que el lote 6 define; con q el mismo acto seria "
                "publicable. El piso se movio 2,42x sobre un sujeto sin cambios, asi que la "
                "disyuntiva la decide la razon min_B/min_A y no el umbral")
    else:
        rama = ("una ventana no basta: el piso deriva dentro del acto y hay que medirlo "
                "intercalado con la cotizacion")
    if "K3" not in sobre:
        rama += ("; y el minimo no viaja entre actos, asi que ningun segundo se publica sin "
                 "medirse en el acto que cotiza")
    doc["predictions_summary"] = {
        "sobreviven": sobre, "caen": caen,
        "rama": ("todas_sobreviven" if not caen else
                 "ninguna_sobrevive" if not sobre else "parcial"),
        "publicable_acto_a": a["publicable"], "publicable_acto_b": b["publicable"],
        "lo_que_cambio": rama,
    }
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Paired acts on one subject: is the floor the act?")
    ap.add_argument("--dir", required=True, help="cache directory for the wheel")
    ap.add_argument("--artefacto", action="store_true",
                    help=f"write {ARTEFACTO.name} with the verdicts")
    ap.add_argument("--desde", metavar="PROGRESO",
                    help="recompose from readings already paid, never re-timing")
    a = ap.parse_args(argv)
    cache = Path(a.dir)
    cache.mkdir(parents=True, exist_ok=True)
    pred = json.loads(PREDICCION.read_text(encoding="utf-8"))
    sexto = json.loads(ARTEFACTO6.read_text(encoding="utf-8"))
    septimo = json.loads(ARTEFACTO7.read_text(encoding="utf-8"))
    acto_a, peor = _frame(sexto, septimo)
    if acto_a is None:
        return peor

    if a.desde:
        crudo = json.loads(Path(a.desde).read_text(encoding="utf-8"))
        acto_b = crudo.get("acto_b", crudo)
        mismo = (acto_b["sha256"] == acto_a["sha256"]
                 and acto_b["bytes_py"] == acto_b["bytes_py_pin"] == acto_a["bytes_py_pin"])
        if not mismo:
            print("  RUPTURA: el acto B del progreso no es el sujeto del acto A")
            return RUPTURA
        acto_b.update(_resumen(acto_b, acto_a["predicho_s"], acto_a["q"]))
        print(f"recompuesto desde {a.desde} · acto A releido del lote 7 · sin volver a cronometrar",
              flush=True)
    else:
        print(f"lote 8 · {pred['method']['acto_b']}", flush=True)
        acto_b, peor = medir(cache, cache / "progreso-8.json", acto_a)
        if acto_b is None:
            print("NO_MEDIDO: el acto B no se compuso")
            return peor

    comp = {"acto_a": acto_a, "acto_b": acto_b,
            "comparacion": _comparacion(acto_a, acto_b)}
    doc = artefacto(comp, pred)
    if a.artefacto:
        ARTEFACTO.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"artefacto: {ARTEFACTO.name} · veredictos " +
              " ".join(f"{x['id']}={'si' if x['sobrevive'] else 'NO'}" for x in doc["veredictos"]))
    return peor


if __name__ == "__main__":
    raise SystemExit(main())
