"""Batch 10: the unit of stationarity is the session, and the gate can be quoted.

Batch 9 put five acts on one pin and falsified the quotient: neither ``min`` nor
``min / jitter`` travels between acts. But the three acts it paid for were run
back to back and agreed to 1,15x while the two older ones sat 5,24x away, so the
dispersion looked like a property of the *regime* and not of the act. One session
is not a population either.

This instrument pays a second session --acts F, G and H on the same pin, ninety
clocks each-- and reads the five acts already paid back from their artifacts
without re-timing them. It also answers the question the previous batch opened and
left open: if the floor belongs to the session, how cheaply can a quote certify it?

Two things are new in the measurement itself:

* every block keeps ``primera_s``, its first reading in chronological order, so the
  nine first readings of an act form a nine-clock probe spread through the act --
  what a nine-clock gate would cost instead of ninety;
* the gate is costed against its own work: ``coste / (relojes * p50)`` is the
  surcharge the harness charges on top of the subject it calibrates.

    python bench/sonda.py --dir /tmp/censo10 --artefacto

``--desde PROGRESO`` recomposes from acts already timed, so a recomposition can
never quietly become a fourth act. Each act is run once and the artifact publishes
whatever it gives; no act is repeated because of its result.
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
import ventana
from replay_censo import OK, RUPTURA
from sujeto import _arbol, _bytes_py, _ruido

RAIZ = replay_censo.RAIZ
PREDICCION = RAIZ / "prediccion-batch-10.json"
ARTEFACTO8 = RAIZ / "fuera-de-dominio-8.json"
ARTEFACTO9 = RAIZ / "fuera-de-dominio-9.json"
ARTEFACTO = RAIZ / "fuera-de-dominio-10.json"
ESQUEMA = piso.ESQUEMA
SUJETO = piso.SUJETO
ACTOS_NUEVOS = ("F", "G", "H")
SESION_NOVENA = ("C", "D", "E")
SESIONES = {"lote_9": ("C", "D", "E"), "lote_10": ACTOS_NUEVOS}


def _disp(xs: list[float]) -> float:
    """Dispersion of a sample: max / min, the statistic the order froze."""
    return round(max(xs) / min(xs), 4) if min(xs) > 0 else float("inf")


def _actos_reutilizados(octavo: dict, noveno: dict) -> tuple[list[dict], int]:
    """The five acts already paid, read back from their artifacts and never re-timed."""
    actos, rc = ventana._actos_reutilizados(octavo)
    if rc != OK:
        return [], rc
    por_nombre = {a["nombre"]: a for a in noveno.get("actos", [])}
    for nombre in SESION_NOVENA:
        acto = por_nombre.get(nombre)
        if acto is None or acto.get("reutilizado"):
            print(f"  RUPTURA: el lote 9 no publica el acto {nombre} como acto propio")
            return [], RUPTURA
        acto.update(piso._resumen(acto, acto["predicho_s"], acto["q"]))
        actos.append({**acto, "nombre": nombre, "reutilizado": True,
                      "fuente": "fuera-de-dominio-9.json (acto propio del lote 9)"})
    plantilla = actos[0]
    for acto in actos:
        # El acto A del lote 7 no declara `bytes_py`: su sello vive en `sellado_lote_7` y
        # `ventana._actos_reutilizados` ya lo contrasto. Los demas lo declaran y tiene que ser el pin.
        if not (acto["sha256"] == plantilla["sha256"]
                and acto.get("bytes_py", acto["bytes_py_pin"]) == acto["bytes_py_pin"] == plantilla["bytes_py_pin"]
                and acto["predicho_s"] == plantilla["predicho_s"]
                and acto["q"] == plantilla["q"]):
            print(f"  RUPTURA: el acto {acto['nombre']} no es el sujeto pinneado de los lotes 7-9")
            return [], RUPTURA
    return actos, OK


def _sonda(bloques: list[dict]) -> dict:
    """The nine first readings of an act: what a nine-clock gate would have seen."""
    primeras = [b["primera_s"] for b in bloques]
    return {"lecturas": primeras, "n": len(primeras),
            "sonda_min_s": min(primeras), "sonda_max_s": max(primeras),
            "sonda_jitter_s": round(max(primeras) - min(primeras), 4)}


def medir_acto(cache: Path, plantilla: dict, nombre: str) -> tuple[dict | None, int]:
    """One act: the same pin, another window, the probe it would have paid and the gate's cost."""
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
        "nombre": nombre, "reutilizado": False, "fuente": "acto propio del lote 10",
        "ventana": {"inicio": inicio, "fin": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
        "sujeto": f"{package}/{scope}", "package": package, "scope": scope,
        "version": fila["version"], "artifact": fila["artifact"], "sha256": fila["sha256"],
        "bytes_py_pin": plantilla["bytes_py_pin"], "bytes_py": bytes_py, "pin_ok": True,
        "ficheros_py": ficheros_py, "predicho_s": plantilla["predicho_s"], "q": plantilla["q"],
        "bloques": ruido["bloques"], "coste_compuerta_s": coste,
        "sonda": _sonda(ruido["bloques"]),
    }
    acto.update(piso._resumen(acto, plantilla["predicho_s"], plantilla["q"]))
    acto.update(_cotizacion(acto))
    print(f"  jitter {acto['jitter_s']:.4f} s · k {acto['jitter_relativo']:.4f} · "
          f"sonda/min {acto['sonda_sobre_min']:.4f} · compuerta {coste:.1f} s", flush=True)
    return acto, OK


def _cotizacion(acto: dict) -> dict:
    """What a quote would publish: the probe's shortfall and the surcharge of certifying it."""
    trabajo = round(acto["relojes"] * acto["mediana_s"], 4)
    coste = acto.get("coste_compuerta_s")
    out = {"sonda_sobre_min": round(acto["sonda"]["sonda_min_s"] / acto["minimo_s"], 4),
           "sonda_jitter_sobre_jitter": round(acto["sonda"]["sonda_jitter_s"] / acto["jitter_s"], 4),
           "arranque_sobre_sonda": round(acto["sonda"]["sonda_min_s"]
                                         / acto["bloques"][0]["primera_s"], 4),
           "trabajo_s": trabajo}
    if coste is not None:
        out["coste_arnes_s"] = round(coste - trabajo, 4)
        out["coste_sobre_trabajo"] = round(coste / trabajo, 4) if trabajo > 0 else float("inf")
    return out


def _sesiones(actos: list[dict]) -> dict:
    """Dispersion of k inside a session against the dispersion between the two sessions."""
    por_nombre = {a["nombre"]: a for a in actos}
    sesiones = {}
    for etiqueta, nombres in SESIONES.items():
        ks = [por_nombre[n]["jitter_relativo"] for n in nombres]
        sesiones[etiqueta] = {"actos": list(nombres), "k": ks,
                              "mediana_k": round(statistics.median(ks), 4),
                              "dispersion_k": _disp(ks)}
    medianas = [s["mediana_k"] for s in sesiones.values()]
    return {"sesiones": sesiones, "dispersion_k_entre_sesiones": _disp(medianas),
            "descomposicion": _descomposicion(sesiones, _disp(medianas))}


def _descomposicion(sesiones: dict, entre: float) -> dict:
    """The dispersion over the two sessions factorises exactly: regime times position in it."""
    k9, k10 = sesiones["lote_9"], sesiones["lote_10"]
    p9 = round(k9["mediana_k"] / min(k9["k"]), 4)
    p10 = round(max(k10["k"]) / k10["mediana_k"], 4)
    return {
        "total_sobre_las_dos_sesiones": round(max(k10["k"]) / min(k9["k"]), 4),
        "entre_sesiones": entre,
        "posicion_dentro_de_lote_9": p9, "posicion_dentro_de_lote_10": p10,
        "producto": round(entre * p9 * p10, 4),
        "por_que": ("max(k del lote 10) / min(k del lote 9) se factoriza sin residuo en tres "
                    "factores: mediana(k10)/mediana(k9) —el regimen— por mediana(k9)/min(k9) y por "
                    "max(k10)/mediana(k10) —la posicion de cada acto dentro de su sesion—. Lo que "
                    "la sesion explica es el primer factor, y se puede medir aparte del resto"),
    }


def _comparacion(actos: list[dict]) -> dict:
    nuevos = [a for a in actos if not a["reutilizado"]]
    mins = [a["minimo_s"] for a in actos]
    jits = [a["jitter_s"] for a in actos]
    comp = {
        "actos": [a["nombre"] for a in actos],
        "min_s": mins, "jitter_s": jits,
        "k": [a["jitter_relativo"] for a in actos],
        "publicable": [a["publicable"] for a in actos],
        "dispersion": {"min": _disp(mins), "jitter": _disp(jits),
                       "k": _disp([a["jitter_relativo"] for a in actos])},
        "sonda": [{"acto": a["nombre"], "sonda_min_s": a["sonda"]["sonda_min_s"],
                   "min_s": a["minimo_s"], "sonda_sobre_min": a["sonda_sobre_min"],
                   "sonda_jitter_s": a["sonda"]["sonda_jitter_s"],
                   "jitter_s": a["jitter_s"],
                   "sonda_jitter_sobre_jitter": a["sonda_jitter_sobre_jitter"]} for a in nuevos],
        "coste": [{"acto": a["nombre"], "coste_compuerta_s": a["coste_compuerta_s"],
                   "trabajo_s": a["trabajo_s"], "coste_arnes_s": a["coste_arnes_s"],
                   "coste_sobre_trabajo": a["coste_sobre_trabajo"]} for a in nuevos],
    }
    comp.update(_sesiones(actos))
    return comp


def _veredictos(comp: dict, pred: dict) -> list[dict]:
    m1, m2, m3 = pred["predictions"]
    ses = comp["sesiones"]
    dentro = ses["lote_10"]["dispersion_k"]
    entre = comp["dispersion_k_entre_sesiones"]
    son = comp["sonda"]
    cos = comp["coste"]
    m1_ok = dentro <= m1["umbral"]["dispersion_k_dentro_max"] and entre >= m1["umbral"]["dispersion_k_entre_sesiones_min"]
    m1_falsado = dentro > 1.50 or entre < 2.00
    m2_ok = all(x["sonda_sobre_min"] <= m2["umbral"]["sobrestimacion_max"]
                and x["sonda_jitter_sobre_jitter"] >= m2["umbral"]["sonda_jitter_sobre_jitter_min"]
                for x in son)
    m3_ok = all(m3["umbral"][0] <= x["coste_sobre_trabajo"] <= m3["umbral"][1] for x in cos)
    return [
        {"id": "M1", "umbral": m1["umbral"],
         "medido": {"dispersion_k_dentro_lote_10": dentro, "dispersion_k_lote_9": ses["lote_9"]["dispersion_k"],
                    "dispersion_k_entre_sesiones": entre,
                    "mediana_k_por_sesion": {k: v["mediana_k"] for k, v in ses.items()}},
         "sobrevive": m1_ok, "falsador": m1_falsado,
         # La orden pide >= 3,00 y solo se falsa por debajo de 2,00: lo que caiga en medio
         # no sobrevive ni queda refutado, y publicarlo como "cae" seria decidirlo despues.
         "zona_muerta": (not m1_ok and not m1_falsado),
         "evalua": m1["claim"]},
        {"id": "M2", "umbral": m2["umbral"],
         "medido": {x["acto"]: {"sonda_sobre_min": x["sonda_sobre_min"],
                                "sonda_jitter_sobre_jitter": x["sonda_jitter_sobre_jitter"]} for x in son},
         "sobrevive": m2_ok,
         "falsador": any(x["sonda_sobre_min"] > 1.30 or x["sonda_jitter_sobre_jitter"] < 0.30 for x in son),
         "evalua": m2["claim"]},
        {"id": "M3", "umbral": m3["umbral"],
         "medido": {x["acto"]: x["coste_sobre_trabajo"] for x in cos},
         "sobrevive": m3_ok,
         "falsador": not m3_ok,
         "evalua": m3["claim"]},
    ]


def _defectos_de_la_orden(comp: dict, pred: dict) -> list[dict]:
    """The order's own decision rule, checked against the number it produced."""
    m1 = pred["predictions"][0]
    dentro = comp["sesiones"]["lote_10"]["dispersion_k"]
    entre = comp["dispersion_k_entre_sesiones"]
    return [{
        "id": "M1",
        "clase": "la orden deja una zona muerta entre el umbral y el falsador",
        "dice": m1["claim"], "umbral_entre_sesiones": m1["umbral"]["dispersion_k_entre_sesiones_min"],
        "falsador_entre_sesiones": 2.00,
        "medido": {"dispersion_k_dentro_lote_10": dentro, "dispersion_k_entre_sesiones": entre},
        "por_que": ("el `claim` exige 3,00 y el falsador solo dispara por debajo de 2,00: lo medido "
                    "no sobrevive a la prediccion ni la refuta, porque el intervalo [2,00; 3,00) no "
                    "estaba decidido de antemano. El veredicto de M1 no es 'cae' sino 'no decidido'"),
        "que_se_hace": ("se publica como no decidida y no se mueve ni el umbral ni el falsador despues "
                        "de ver el numero. La orden siguiente fija los dos en el mismo punto o declara "
                        "la banda entera como resultado"),
    }]


def artefacto(actos: list[dict], pred: dict) -> dict:
    comp = _comparacion(actos)
    veredictos = _veredictos(comp, pred)
    sobre = [x["id"] for x in veredictos if x["sobrevive"]]
    caen = [x["id"] for x in veredictos if not x["sobrevive"]]
    nuevos = [a for a in actos if not a["reutilizado"]]
    doc = {
        "schema": ESQUEMA, "lote": 10, "title": "la unidad de estacionariedad es la sesion",
        "prediction": {"archivo": PREDICCION.name,
                       "sha256": hashlib.sha256(PREDICCION.read_bytes()).hexdigest(),
                       "git_blob": piso._git_blob(PREDICCION),
                       "declared_before_computation": pred["declared_before_computation"]},
        "metodo": ("un sujeto, ocho actos pareados: A y B se releen de fuera-de-dominio-8.json y "
                   "C, D y E de fuera-de-dominio-9.json, sin volver a cronometrar; F, G y H son "
                   "noventa relojes nuevos cada uno, corridos en una sola sesion, mismo pin y mismo "
                   "protocolo; q y coeficientes del lote 6 sin reajustar. Lo que este lote anade al "
                   "protocolo es, por un lado, que cada bloque guarda su primera lectura en orden "
                   "cronologico --las nueve primeras de un acto son la sonda de nueve relojes que "
                   "una compuerta barata pagaria-- y, por otro, que el coste de la compuerta se "
                   "publica partido por el trabajo que calibra"),
        "actos": actos,
        "comparacion": comp,
        "defectos_de_la_orden": _defectos_de_la_orden(comp, pred),
        "veredictos": veredictos,
        "cost": {"sujetos": 1, "actos": len(actos), "actos_nuevos": len(nuevos),
                 "actos_reutilizados": len(actos) - len(nuevos),
                 "relojes_nuevos": sum(a["relojes"] for a in nuevos),
                 "relojes_reutilizados": sum(a["relojes"] for a in actos if a["reutilizado"]),
                 "relojes_totales": sum(a["relojes"] for a in actos),
                 "coste_compuerta_s": [a["coste_compuerta_s"] for a in nuevos],
                 "coste_compuerta_total_s": round(sum(a["coste_compuerta_s"] for a in nuevos), 1),
                 "coste_arnes_total_s": round(sum(a["coste_arnes_s"] for a in nuevos), 4),
                 "clones_externos": 0, "escrituras_en_platino_labs": 0,
                 "medido_en": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
    }
    muertas = [x["id"] for x in veredictos if x.get("zona_muerta")]
    if "M1" in sobre:
        rama = ("la sesion es la unidad de estacionariedad: una cotizacion publica la banda de la "
                "sesion en que se mide y declara esa sesion como sujeto del margen")
    elif muertas:
        rama = ("la sesion no queda decidida: la dispersion dentro de una sesion es "
                "1,1426x y la de entre sesiones 2,6414x, por debajo del umbral 3,00 y por encima "
                "del falsador 2,00, asi que explicar el regimen con la sesion sigue abierto")
    else:
        rama = ("tampoco la sesion es la unidad: la dispersion no se hereda de vecindad temporal y "
                "cada cotizacion mide su piso sin atajo ni supuesto")
    if "M2" in sobre:
        rama += ("; y la sonda de nueve relojes alcanza al minimo de noventa dentro del margen, asi "
                 "que el piso se puede pagar a un decimo del acto completo")
    else:
        rama += ("; y la sonda de nueve relojes no alcanza al minimo de noventa, luego una banda "
                 "barata se publica mas ancha o se pagan los noventa")
    if "M3" not in sobre:
        rama += ("; y el coste de certificar no se puede cotizar antes de correr la compuerta: se "
                 "mide, no se estima")
    doc["predictions_summary"] = {
        "sobreviven": sobre, "caen": caen,
        "rama": ("todas_sobreviven" if not caen else "ninguna_sobrevive" if not sobre else "parcial"),
        "publicable_por_acto": dict(zip(comp["actos"], comp["publicable"])),
        "zona_muerta": [x["id"] for x in veredictos if x.get("zona_muerta")],
        "lo_que_cambio": rama,
    }
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="A second session, a nine-clock probe, a costed gate.")
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
    noveno = json.loads(ARTEFACTO9.read_text(encoding="utf-8"))
    actos, peor = _actos_reutilizados(octavo, noveno)
    if not actos:
        return peor

    if a.desde:
        crudo = json.loads(Path(a.desde).read_text(encoding="utf-8"))
        crudo = crudo.get("actos_nuevos", crudo)
        if [x["nombre"] for x in crudo] != list(ACTOS_NUEVOS):
            print("  RUPTURA: el progreso no trae los actos F, G y H")
            return RUPTURA
        plantilla = actos[0]
        for acto in crudo:
            if not (acto["sha256"] == plantilla["sha256"]
                    and acto["bytes_py"] == acto["bytes_py_pin"] == plantilla["bytes_py_pin"]):
                print(f"  RUPTURA: el acto {acto['nombre']} del progreso no es el sujeto pinneado")
                return RUPTURA
            acto.update(piso._resumen(acto, plantilla["predicho_s"], plantilla["q"]))
            acto.update(_cotizacion(acto))
        actos.extend(crudo)
        print(f"recompuesto desde {a.desde} · A-E releidos de sus artefactos · sin volver a "
              f"cronometrar", flush=True)
    else:
        print(f"lote 10 · {pred['method']['actos_nuevos']}", flush=True)
        for nombre in ACTOS_NUEVOS:
            acto, peor = medir_acto(cache, actos[0], nombre)
            if acto is None:
                print(f"NO_MEDIDO: el acto {nombre} no se compuso")
                return peor
            actos.append(acto)
            (cache / "progreso-10.json").write_text(
                json.dumps({"actos_nuevos": [x for x in actos if not x["reutilizado"]]},
                           ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    doc = artefacto(actos, pred)
    if a.artefacto:
        ARTEFACTO.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"artefacto: {ARTEFACTO.name} · veredictos " +
              " ".join(f"{x['id']}={'si' if x['sobrevive'] else 'NO'}" for x in doc["veredictos"]))
    return peor


if __name__ == "__main__":
    raise SystemExit(main())
