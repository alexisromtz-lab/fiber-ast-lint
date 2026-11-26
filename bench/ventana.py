"""Batch 9: what travels between acts is a quotient.

Batch 8 put the same pinned tree in two acts and the minimum of ninety readings
moved 2,10x without a byte changing: the floor is a reading of the act, not of the
subject. Two acts are not a population, so they cannot say *what* travels. The
candidate is the dimensionless quotient ``min / jitter``, which moved 1,15x while
``min`` moved 2,10x and ``jitter`` 2,42x; the alternative is that nothing travels.

This instrument adds three acts to the two already paid, on the same pin, ninety
clocks each, and it times the gate itself:

    python bench/ventana.py --dir /tmp/censo9 --artefacto

Acts A and B are read back from ``fuera-de-dominio-8.json`` with their ninety
readings each and are never re-timed, so the sample is paired. ``coste_compuerta_s``
is the wall clock the gate burns to certify the floor: a quote that has to measure
its own noise should say what that measurement cost.

``--desde PROGRESO`` recomposes the document from acts already timed, so a
recomposition can never quietly become a fourth act. Each act is run once and the
artifact publishes whatever it gives; no act is repeated because of its result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

import piso
import replay_censo
from replay_censo import OK, RUPTURA
from sujeto import _arbol, _bytes_py, _ruido

RAIZ = replay_censo.RAIZ
PREDICCION = RAIZ / "prediccion-batch-9.json"
ARTEFACTO8 = RAIZ / "fuera-de-dominio-8.json"
ARTEFACTO = RAIZ / "fuera-de-dominio-9.json"
ESQUEMA = piso.ESQUEMA
SUJETO = piso.SUJETO
ACTOS_NUEVOS = ("C", "D", "E")


def _disp(xs: list[float]) -> float:
    """Dispersion of a sample: max / min, the statistic the order froze."""
    return round(max(xs) / min(xs), 4) if min(xs) > 0 else float("inf")


def _actos_reutilizados(octavo: dict) -> tuple[list[dict], int]:
    """Acts A and B of batch 8 as they were paid, every summary recomputed from their blocks."""
    a, b = octavo.get("acto_a"), octavo.get("acto_b")
    if a is None or b is None:
        print("  RUPTURA: el lote 8 no publica los actos A y B")
        return [], RUPTURA
    if a["sha256"] != b["sha256"] or a["bytes_py_pin"] != b["bytes_py_pin"] or b["bytes_py"] != b["bytes_py_pin"]:
        print("  RUPTURA: los actos A y B no son el mismo sujeto pinneado")
        return [], RUPTURA
    if a["predicho_s"] != b["predicho_s"] or a["q"] != b["q"]:
        print("  RUPTURA: la banda o q cambiaron entre los actos A y B")
        return [], RUPTURA
    out = []
    for nombre, acto, fuente in (("A", a, "fuera-de-dominio-8.json (sellado del lote 7)"),
                                 ("B", b, "fuera-de-dominio-8.json (acto propio del lote 8)")):
        acto.update(piso._resumen(acto, acto["predicho_s"], acto["q"]))
        out.append({"nombre": nombre, "reutilizado": True, "fuente": fuente,
                    "ventana": acto.get("ventana"), **acto})
    # El acto A tiene que seguir siendo la fila que el lote 7 sello: si no, el
    # frame pareado se estaria comparando contra otra cosa.
    for campo, valor in out[0]["sellado_lote_7"].items():
        if out[0][campo] != valor:
            print(f"  RUPTURA: el acto A ya no cuadra con el lote 7 en {campo}")
            return [], RUPTURA
    return out, OK


def medir_acto(cache: Path, plantilla: dict, nombre: str) -> tuple[dict | None, int]:
    """One act: the same pin, another window, and the wall clock the gate costs."""
    package, scope = SUJETO
    fila = {k: plantilla[k] for k in ("package", "scope", "version", "artifact", "sha256")}
    arbol, rc = _arbol(cache, fila)
    if rc != OK:
        print(f"  RUPTURA: el arbol del acto {nombre} no se pudo componer")
        return None, rc
    bytes_py, ficheros_py = _bytes_py(arbol)
    if bytes_py != plantilla["bytes_py_pin"]:
        print(f"  RUPTURA: pin {plantilla['bytes_py_pin']} != {bytes_py}; el sujeto seria otro objeto")
        return None, RUPTURA

    print(f"  acto {nombre} · {package}/{scope} · {bytes_py} B · 9 bloques de 10", flush=True)
    inicio = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    t0 = time.perf_counter()
    ruido = _ruido(arbol, 10, 9)
    coste = round(time.perf_counter() - t0, 4)
    acto = {
        "nombre": nombre, "reutilizado": False, "fuente": "acto propio del lote 9",
        "ventana": {"inicio": inicio, "fin": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
        "sujeto": f"{package}/{scope}", "package": package, "scope": scope,
        "version": fila["version"], "artifact": fila["artifact"], "sha256": fila["sha256"],
        "bytes_py_pin": plantilla["bytes_py_pin"], "bytes_py": bytes_py, "pin_ok": True,
        "ficheros_py": ficheros_py, "predicho_s": plantilla["predicho_s"], "q": plantilla["q"],
        "bloques": ruido["bloques"], "coste_compuerta_s": coste,
    }
    acto.update(piso._resumen(acto, plantilla["predicho_s"], plantilla["q"]))
    acto["coste_por_reloj_s"] = round(coste / acto["relojes"], 4)
    print(f"  jitter {acto['jitter_s']:.4f} s · rel {acto['jitter_relativo']:.4f} · "
          f"publicable {'si' if acto['publicable'] else 'NO'} · compuerta {coste:.1f} s", flush=True)
    return acto, OK


def _dentro_de_cada_acto(acto: dict) -> float:
    """Dispersion of the block jitters inside one act: what one block cannot represent."""
    return _disp([b["jitter_s"] for b in acto["bloques"]])


def _comparacion(actos: list[dict]) -> dict:
    mins = [a["minimo_s"] for a in actos]
    jits = [a["jitter_s"] for a in actos]
    coci = [round(a["minimo_s"] / a["jitter_s"], 4) for a in actos]
    ks = [round(a["jitter_s"] / a["predicho_s"], 4) for a in actos]
    dentro = [{"acto": a["nombre"], "dispersion_jitter_de_bloque": _dentro_de_cada_acto(a),
               "max_jitter_sobre_min_bloque": round(
                   a["jitter_s"] / min(b["min_s"] for b in a["bloques"]), 4)} for a in actos]
    return {
        "actos": [a["nombre"] for a in actos],
        "min_s": mins, "jitter_s": jits, "min_sobre_jitter": coci,
        "k": ks, "publicable": [a["publicable"] for a in actos],
        "dispersion": {"min": _disp(mins), "jitter": _disp(jits),
                       "min_sobre_jitter": _disp(coci), "k": _disp(ks)},
        "dentro": dentro,
        # L3 tal como la orden la escribe: la media de max(jitter de bloque) /
        # min(minimo de bloque) sobre los actos, partida por la dispersion de min.
        "l3_claim": round(statistics.fmean(x["max_jitter_sobre_min_bloque"] for x in dentro)
                          / _disp(mins), 4),
        # La generalizacion de lo que la cota numera —dispersion de jitter de un acto
        # partida por la dispersion de min— promediada sobre los cinco actos. No es
        # `l3_cota`: con los dos actos del lote 8 da 1,7043 y no 1,1797, porque el
        # 2,4797 de la cota es la dispersion interna del acto B y no una media.
        "l3_cota_media": round(statistics.fmean(x["dispersion_jitter_de_bloque"] for x in dentro)
                               / _disp(mins), 4),
    }


def _defectos(octavo: dict, comp: dict, pred: dict) -> list[dict]:
    """The order's own arithmetic, checked against the batch-8 numbers it cites."""
    l3 = next(p for p in pred["predictions"] if p["id"] == "L3")
    a8, b8 = octavo["acto_a"], octavo["acto_b"]
    dentro_b8 = round(max(x["jitter_s"] for x in b8["bloques"])
                      / min(x["jitter_s"] for x in b8["bloques"]), 4)
    disp_min_8 = round(max(a8["minimo_s"], b8["minimo_s"]) / min(a8["minimo_s"], b8["minimo_s"]), 4)
    claim_8 = round(((a8["jitter_s"] / min(x["min_s"] for x in a8["bloques"]))
                     + (b8["jitter_s"] / min(x["min_s"] for x in b8["bloques"]))) / 2 / disp_min_8, 4)
    return [{
        "id": "L3",
        "clase": "la orden se contradice a si misma",
        "claim_aplica": l3["claim"],
        "cota_dice": l3["cota_error"],
        "probado_con_el_lote_8": {"claim": claim_8, "cota": round(dentro_b8 / disp_min_8, 4),
                                  "dispersion_jitter_del_acto_B": dentro_b8,
                                  "dispersion_min": disp_min_8},
        "por_que": ("`claim` divide max(jitter) / min(minimo) por acto —dos unidades, cuatro "
                    "digitos— y `cota_error` divide la dispersion de jitter de UN acto por la "
                    "dispersion de min. Con los dos actos del lote 8 dan 0,4464 y 1,1797: no son "
                    "la misma cantidad, y solo la segunda pasa por el rango [0,80; 1,25]."),
        "que_se_hace": ("se evalua L3 con la formula que el `claim` declara, que es la que el "
                        "rango congela, y se publica `l3_cota_media` como cifra descriptiva. El defecto "
                        "no se corrige despues de ver el resultado: se declara"),
        "medido_ahora": {"claim": comp["l3_claim"], "cota_media": comp["l3_cota_media"]},
    }]


def _veredictos(comp: dict, pred: dict) -> list[dict]:
    l1, l2, l3 = pred["predictions"]
    d = comp["dispersion"]
    return [
        {"id": "L1", "umbral": l1["umbral"],
         "medido": {"dispersion_min_sobre_jitter": d["min_sobre_jitter"], "dispersion_min": d["min"]},
         "sobrevive": (d["min_sobre_jitter"] <= l1["umbral"]["dispersion_min_sobre_jitter_max"]
                       and d["min"] >= l1["umbral"]["dispersion_min_min"]),
         "falsador": (d["min_sobre_jitter"] > 1.50 or d["min"] < 1.50),
         "evalua": l1["claim"]},
        {"id": "L2", "umbral": l2["umbral"],
         "medido": {"min_sobre_jitter": comp["min_sobre_jitter"]},
         "sobrevive": all(l2["umbral"][0] <= x <= l2["umbral"][1] for x in comp["min_sobre_jitter"]),
         "falsador": (not all(l2["umbral"][0] <= x <= l2["umbral"][1] for x in comp["min_sobre_jitter"])),
         "evalua": l2["claim"]},
        {"id": "L3", "umbral": l3["umbral"],
         "medido": {"claim": comp["l3_claim"], "cota_media": comp["l3_cota_media"]},
         "sobrevive": l3["umbral"][0] <= comp["l3_claim"] <= l3["umbral"][1],
         "falsador": (not l3["umbral"][0] <= comp["l3_claim"] <= l3["umbral"][1]),
         "evalua": l3["claim"]},
    ]


def artefacto(actos: list[dict], pred: dict, octavo: dict) -> dict:
    comp = _comparacion(actos)
    veredictos = _veredictos(comp, pred)
    sobre = [x["id"] for x in veredictos if x["sobrevive"]]
    caen = [x["id"] for x in veredictos if not x["sobrevive"]]
    nuevos = [a for a in actos if not a["reutilizado"]]
    costes = [a["coste_compuerta_s"] for a in nuevos]
    doc = {
        "schema": ESQUEMA, "lote": 9, "title": "lo que viaja entre actos es un cociente",
        "prediction": {"archivo": PREDICCION.name,
                       "sha256": hashlib.sha256(PREDICCION.read_bytes()).hexdigest(),
                       "git_blob": piso._git_blob(PREDICCION),
                       "declared_before_computation": pred["declared_before_computation"]},
        "metodo": ("un sujeto, cinco actos pareados: A y B se releen de fuera-de-dominio-8.json "
                   "sin volver a cronometrar y C, D y E son noventa relojes nuevos cada uno, "
                   "mismo pin, mismo protocolo, ventana distinta; q y coeficientes del lote 6 sin "
                   "reajustar; cada acto se corre una vez y se publica lo que salio. Lo unico que "
                   "este lote anade al protocolo es cronometrar la compuerta: coste_compuerta_s es "
                   "el reloj de pared de los noventa relojes que miden el piso"),
        "actos": actos,
        "comparacion": comp,
        "defectos_de_la_orden": _defectos(octavo, comp, pred),
        "veredictos": veredictos,
        "cost": {"sujetos": 1, "actos": len(actos), "actos_nuevos": len(nuevos),
                 "actos_reutilizados": len(actos) - len(nuevos),
                 "relojes_nuevos": sum(a["relojes"] for a in nuevos),
                 "relojes_reutilizados": sum(a["relojes"] for a in actos if a["reutilizado"]),
                 "relojes_totales": sum(a["relojes"] for a in actos),
                 "coste_compuerta_s": costes, "coste_compuerta_total_s": round(sum(costes), 1),
                 "coste_por_reloj_s": round(statistics.fmean(a["coste_por_reloj_s"] for a in nuevos), 4),
                 "clones_externos": 0, "escrituras_en_platino_labs": 0,
                 "medido_en": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
    }
    if "L1" in sobre and "L2" in sobre:
        rama = ("una cotizacion se publica como su minimo medido mas una banda adimensional: el "
                "reloj entra al recibo como cociente y no como segundo heredado")
    elif "L1" not in sobre:
        rama = ("ni el cociente viaja: no hay magnitud temporal publicable entre actos y la "
                "cotizacion se queda en conteos de bytes y de nodos")
    else:
        rama = ("el cociente tiene colas abiertas: la banda solo se publica midiendo el piso en "
                "el acto del cliente, al coste de una ventana por cotizacion")
    if "L3" not in sobre:
        rama += ("; y L3 no se decide con la formula que su claim declara, asi que la dispersion "
                 "de dentro del acto se sigue midiendo en vez de suponiendose")
    doc["predictions_summary"] = {
        "sobreviven": sobre, "caen": caen,
        "rama": ("todas_sobreviven" if not caen else "ninguna_sobrevive" if not sobre else "parcial"),
        "publicable_por_acto": dict(zip(comp["actos"], comp["publicable"])),
        "lo_que_cambio": rama,
    }
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Three more acts on one pin: does the quotient travel?")
    ap.add_argument("--dir", required=True, help="cache directory for the wheel")
    ap.add_argument("--artefacto", action="store_true",
                    help=f"write {ARTEFACTO.name} with the verdicts")
    ap.add_argument("--desde", metavar="PROGRESO",
                    help="recompose from acts already timed, never re-timing")
    a = ap.parse_args(argv)
    cache = Path(a.dir)
    cache.mkdir(parents=True, exist_ok=True)
    pred = json.loads(PREDICCION.read_text(encoding="utf-8"))
    octavo = json.loads(ARTEFACTO8.read_text(encoding="utf-8"))
    actos, peor = _actos_reutilizados(octavo)
    if not actos:
        return peor

    if a.desde:
        crudo = json.loads(Path(a.desde).read_text(encoding="utf-8"))
        crudo = crudo.get("actos_nuevos", crudo)
        if [x["nombre"] for x in crudo] != list(ACTOS_NUEVOS):
            print("  RUPTURA: el progreso no trae los actos C, D y E")
            return RUPTURA
        plantilla = actos[0]
        for acto in crudo:
            if not (acto["sha256"] == plantilla["sha256"]
                    and acto["bytes_py"] == acto["bytes_py_pin"] == plantilla["bytes_py_pin"]):
                print(f"  RUPTURA: el acto {acto['nombre']} del progreso no es el sujeto pinneado")
                return RUPTURA
            acto.update(piso._resumen(acto, plantilla["predicho_s"], plantilla["q"]))
        actos.extend(crudo)
        print(f"recompuesto desde {a.desde} · actos A y B releidos del lote 8 · sin volver a "
              f"cronometrar", flush=True)
    else:
        print(f"lote 9 · {pred['method']['actos_nuevos']}", flush=True)
        for nombre in ACTOS_NUEVOS:
            acto, peor = medir_acto(cache, actos[0], nombre)
            if acto is None:
                print(f"NO_MEDIDO: el acto {nombre} no se compuso")
                return peor
            actos.append(acto)
            (cache / "progreso-9.json").write_text(
                json.dumps({"actos_nuevos": [x for x in actos if not x["reutilizado"]]},
                           ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    doc = artefacto(actos, pred, octavo)
    if a.artefacto:
        ARTEFACTO.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"artefacto: {ARTEFACTO.name} · veredictos " +
              " ".join(f"{x['id']}={'si' if x['sobrevive'] else 'NO'}" for x in doc["veredictos"]))
    return peor


if __name__ == "__main__":
    raise SystemExit(main())
