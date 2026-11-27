"""Recibo con banda: el veredicto deja de ser un booleano.

El lote 8 cerro con ``publicable = predicho * q > jitter``, que vale lo mismo para un acto
con k = 0,10 que para uno con k = 0,29 cuando q = 0,3018, y que se invirtio cuatro veces
sobre el mismo pin a lo largo del lote 10. Un veredicto binario sobre una magnitud que se
mueve 2,64x entre sesiones no certifica: informa. Lo que certifica es la distancia a la
frontera, la dispersion de la sesion que la produjo y lo que costo comprobarla.

Este instrumento no vuelve a cronometrar nada. Lee un artefacto ``fuera-de-dominio-N.json``
ya sellado y emite, por acto, la banda ``(k, umbral, margen, zona)``, la dispersion de k
dentro de su sesion, el coste de la compuerta y cuantos usos la amortizan. El recibo se
firma con la huella de su serializacion canonica: verificarlo es recomputarlo y comparar
dos numeros, sin ejecutar el escaner ni creer una prosa.

El instrumento no sabe de lotes: recibe un artefacto, deriva de lo que ese artefacto declara
en que sesion se tomo cada lectura, y emite la banda. Ninguna de sus reglas nombra un lote
concreto, de modo que los tres artefactos sellados que comparten actos (lotes 8, 9 y 10)
producen la misma banda para el mismo acto. La ley que se comprueba en el lote 12 es esa:
la banda es funcion del acto, no del artefacto que lo contiene.

Uso::

    python bench/recibo.py --artefacto fuera-de-dominio-10.json --salida R --prediccion P
    python bench/recibo.py --artefacto fuera-de-dominio-10.json --check R
    python bench/recibo.py --artefacto fuera-de-dominio-8.json --salida R

Codigos de salida: 0 recibo escrito o verificado, 2 artefacto ilegible, 4 huella distinta,
20 argumentos.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

RELOJES_SONDA = 9
ZONAS = ("margen_sano", "banda_de_riesgo", "fuera_de_cota")
VOLATILES = ("huella", "medicion_de_si_mismo")


def canonico(obj: dict) -> bytes:
    """Serializacion sin la que dos dicts iguales pueden dar bytes distintos."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def huella(obj: dict) -> str:
    return hashlib.sha256(canonico({k: v for k, v in obj.items() if k not in VOLATILES})).hexdigest()


def _zona(k: float, q: float) -> str:
    if k > q:
        return "fuera_de_cota"
    if k > q / 2:
        return "banda_de_riesgo"
    return "margen_sano"


def _banda(k: float, q: float) -> dict:
    """La distancia a la frontera, no el lado en que se cae."""
    margen = round(q - k, 4)
    return {
        "k": k,
        "umbral": q,
        "mitad_umbral": round(q / 2, 4),
        "margen": margen,
        "margen_relativo": round(margen / q, 4),
        "zona": _zona(k, q),
    }


def _sesion(fuente: str) -> int | None:
    """La sesion sale de la fuente declarada, nunca del orden de la lista."""
    m = re.search(r"lote\s+(\d+)", fuente or "")
    return int(m.group(1)) if m else None


def _sesion_de(acto: dict, lote_artefacto: int | None) -> int | None:
    """Donde se tomaron las lecturas, segun lo que el artefacto declare.

    Tres declaraciones y ninguna rama por lote: la fuente citada, el sello de un lote
    anterior y -- si el acto es propio -- el lote del artefacto que lo publica.
    """
    s = _sesion(acto.get("fuente"))
    if s is not None:
        return s
    for clave in acto:
        m = re.fullmatch(r"sellado_lote_(\d+)", clave)
        if m:
            return int(m.group(1))
    return None if acto.get("reutilizado") else lote_artefacto


def _actos(arte: dict) -> list[dict]:
    """Los actos del artefacto: la lista ``actos`` o el par ``acto_a``/``acto_b`` del lote 8."""
    actos = arte.get("actos")
    if actos is None:
        actos = [arte[k] for k in ("acto_a", "acto_b") if k in arte]
    return [dict(a, nombre=a.get("nombre") or chr(ord("A") + i)) for i, a in enumerate(actos)]


def _dispersiones(actos: list[dict], lote: int | None = None) -> dict[int, dict]:
    """Dispersion de k por sesion; con un solo acto no hay dispersion, hay NO_MEDIDO."""
    por_sesion: dict[int, list[float]] = {}
    for a in actos:
        s = _sesion_de(a, lote)
        if s is not None:
            por_sesion.setdefault(s, []).append(a["jitter_relativo"])
    out = {}
    for s, ks in por_sesion.items():
        out[s] = {
            "n": len(ks),
            "k_min": round(min(ks), 4),
            "k_max": round(max(ks), 4),
            "dispersion": round(max(ks) / min(ks), 4) if len(ks) > 1 else None,
        }
    return out


def _cotizacion(acto: dict) -> dict | None:
    """Cuanto cuesta re-certificar con una sonda, y cuantos usos amortizan el acto."""
    coste = acto.get("coste_compuerta_s")
    arnes = acto.get("coste_arnes_s")
    mediana = acto.get("mediana_s")
    if coste is None or arnes is None or mediana is None:
        return None
    sonda = round(RELOJES_SONDA * mediana, 4)
    uso = round(arnes + sonda, 4)
    return {
        "relojes_sonda": RELOJES_SONDA,
        "sonda_s": sonda,
        "coste_uso_s": uso,
        "usos_para_amortizar": math.ceil(coste / uso),
        "usos_sin_arnes": math.ceil(coste / sonda),
    }


def _sujeto(actos: list[dict]) -> dict:
    pins = {a.get("sha256") for a in actos}
    bytes_ = {a.get("bytes_py_pin") for a in actos}
    return {
        "sha256": pins.pop() if len(pins) == 1 else None,
        "bytes_py_pin": bytes_.pop() if len(bytes_) == 1 else None,
        "actos": len(actos),
        "relojes": sum(a.get("relojes", 0) for a in actos),
    }


def _veredictos(resumen: dict, por_acto: list[dict], pred: dict | None) -> list[dict]:
    """Evalua P1 y P4 del pre-registro; P2 y P3 se miden fuera de la huella.

    Un veredicto solo existe si un pre-registro lo declara: los lotes 8 y 9 no conocian
    P1 ni P4, y emitir su juicio desde aqui seria inventarle un pre-registro al sujeto.
    """
    if pred is None:
        return []
    out = []
    if "P1" in pred:
        pub = resumen["publicables_como_booleano"]
        riesgo = resumen["en_banda_de_riesgo_n"]
        out.append({
            "id": "P1",
            "prediccion": pred.get("P1"),
            "medido": {"publicables": pub, "en_banda_de_riesgo": riesgo, "actos": resumen["actos"]},
            "sobrevive": 1 <= riesgo and riesgo * 2 <= pub if pub else False,
            "evalua": "el booleano dice si con el margen ya consumido en al menos un acto y en no mas de la mitad",
        })
    if "P4" in pred:
        cotizados = [a for a in por_acto if a["cotizacion"]]
        caro = max(cotizados, key=lambda a: a["coste_compuerta_s"]) if cotizados else None
        usos = caro["cotizacion"]["usos_para_amortizar"] if caro else None
        out.append({
            "id": "P4",
            "prediccion": pred.get("P4"),
            "medido": {"acto_mas_caro": caro["nombre"] if caro else None, "usos_para_amortizar": usos,
                       "usos_sin_arnes": caro["cotizacion"]["usos_sin_arnes"] if caro else None},
            "sobrevive": bool(usos is not None and 20 <= usos <= 40),
            "evalua": "la compuerta de noventa relojes solo se amortiza con volumen, entre veinte y cuarenta usos",
        })
    return out


def _leer_prediccion(ruta: Path | None) -> dict | None:
    if ruta is None or not ruta.exists():
        return None
    pred = json.loads(ruta.read_text())
    return {p["id"]: p["claim"] for p in pred.get("predictions", [])}


def recibo(arte: dict, fuente: str, lote: int | None = None) -> dict:
    """El recibo completo, con huella. Medir su coste es cosa de quien lo llama."""
    actos = _actos(arte)
    if lote is None:
        lote = arte.get("lote")
    disp = _dispersiones(actos, lote)
    por_acto = []
    for a in actos:
        s = _sesion_de(a, lote)
        b = _banda(a["jitter_relativo"], a["q"])
        b.update({
            "nombre": a["nombre"],
            "sesion": s,
            "sesion_n": disp.get(s, {}).get("n"),
            "dispersion_dentro": disp.get(s, {}).get("dispersion"),
            "publicable_como_booleano": bool(a.get("publicable")),
            "coste_compuerta_s": a.get("coste_compuerta_s"),
            "trabajo_s": a.get("trabajo_s"),
            "cotizacion": _cotizacion(a),
        })
        por_acto.append(b)

    publicables = [b["nombre"] for b in por_acto if b["publicable_como_booleano"]]
    margenes = [b["margen_relativo"] for b in por_acto]
    resumen = {
        "actos": len(por_acto),
        "publicables_como_booleano": len(publicables),
        "publicables": publicables,
        "en_banda_de_riesgo": [b["nombre"] for b in por_acto if b["zona"] == "banda_de_riesgo"],
        "en_banda_de_riesgo_n": sum(1 for b in por_acto if b["zona"] == "banda_de_riesgo"),
        "por_zona": {z: [b["nombre"] for b in por_acto if b["zona"] == z] for z in ZONAS},
        "margen_relativo_min": round(min(margenes), 4),
        "margen_relativo_max": round(max(margenes), 4),
        "dispersiones_por_sesion": {str(k): v for k, v in sorted(disp.items())},
    }
    out = {
        "schema": "fiber-ast-lint/recibo/1",
        "lote": lote,
        "sujeto": _sujeto(actos),
        # el nombre, no la ruta: la huella no puede depender de donde se invoco el instrumento
        "fuente_artefacto": {"ruta": Path(fuente).name,
                             "sha256": hashlib.sha256(Path(fuente).read_bytes()).hexdigest()},
        "actos": por_acto,
        "resumen": resumen,
        "veredictos": [],
    }
    out["veredictos"] = _veredictos(resumen, por_acto, None)
    out["huella"] = huella(out)
    return out


def _reanclar_veredictos(rec: dict, pred: dict | None) -> dict:
    """Re-evalua los veredictos con el pre-registro dentro y re-firma sin mover el juicio."""
    rec = dict(rec)
    rec["veredictos"] = _veredictos(rec["resumen"], rec["actos"], pred)
    rec["huella"] = huella(rec)
    return rec


def _resumen_legible(rec: dict) -> str:
    r = rec["resumen"]
    lineas = [
        f"sujeto {(rec['sujeto']['sha256'] or 'NO_MEDIDO')[:8]} · {rec['sujeto']['bytes_py_pin']} B"
        f" · {r['actos']} actos · {rec['sujeto']['relojes']} relojes",
        f"huella {rec['huella']}",
        "",
        f"{'acto':<5}{'ses':>5}{'k':>9}{'q/2':>9}{'umbral':>9}{'margen':>10}{'margen%':>9}"
        f"{'zona':>18}{'booleano':>10}{'usos':>6}",
    ]
    for a in rec["actos"]:
        usos = a["cotizacion"]["usos_para_amortizar"] if a["cotizacion"] else "-"
        lineas.append(
            f"{a['nombre']:<5}{a['sesion'] if a['sesion'] else '-':>5}{a['k']:>9.4f}"
            f"{a['mitad_umbral']:>9.4f}{a['umbral']:>9.4f}{a['margen']:>10.4f}"
            f"{100 * a['margen_relativo']:>8.2f}%{a['zona']:>18}"
            f"{'si' if a['publicable_como_booleano'] else 'NO':>10}{usos:>6}"
        )
    lineas += [
        "",
        f"zona: margen_sano={len(r['por_zona']['margen_sano'])}"
        f" banda_de_riesgo={len(r['por_zona']['banda_de_riesgo'])}"
        f" fuera_de_cota={len(r['por_zona']['fuera_de_cota'])}",
        f"el booleano dice si en {r['publicables_como_booleano']} actos, y de esos"
        f" {r['en_banda_de_riesgo_n']} estan en banda de riesgo",
    ]
    for v in rec["veredictos"]:
        lineas.append(f"{v['id']}: {'sobrevive' if v['sobrevive'] else 'CAE'} · {v['medido']}")
    return "\n".join(lineas)


def _prediccion_del_lote(lote: int | None, junto_a: Path) -> dict | None:
    """El pre-registro del lote que el recibo declara, si vive junto al recibo."""
    if lote is None:
        return None
    return _leer_prediccion(junto_a / f"prediccion-batch-{lote}.json")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Recibo con banda sobre un artefacto sellado.")
    ap.add_argument("--artefacto", required=True, type=Path)
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--check", type=Path, help="recomputa y compara la huella con este recibo")
    ap.add_argument("--lote", type=int, help="lote de la emision; por defecto, el del artefacto")
    ap.add_argument("--prediccion", type=Path,
                    help="pre-registro que declara P1 y P4; sin el, el recibo no emite veredictos")
    args = ap.parse_args(argv)
    if not args.salida and not args.check:
        ap.error("hace falta --salida o --check")

    try:
        arte = json.loads(args.artefacto.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"artefacto ilegible: {args.artefacto} ({e})", file=sys.stderr)
        return 2

    sellado = None
    if args.check:
        try:
            sellado = json.loads(args.check.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"recibo ilegible: {args.check} ({e})", file=sys.stderr)
            return 2

    # El lote de emision es lo unico que el recibo sellado declara y no se puede recomputar
    # desde el artefacto: se honra su declaracion, y la huella cubre todo lo demas.
    lote = args.lote if args.lote is not None else (sellado.get("lote") if sellado else None)
    if args.prediccion:
        pred = _leer_prediccion(args.prediccion)
    elif sellado and sellado.get("veredictos"):
        pred = _prediccion_del_lote(lote, args.check.parent)
    else:
        pred = None

    t0 = time.perf_counter()
    rec = recibo(arte, str(args.artefacto), lote)
    rec = _reanclar_veredictos(rec, pred)
    coste = round(time.perf_counter() - t0, 6)
    total = sum(a.get("coste_compuerta_s") or 0.0 for a in _actos(arte))
    rec["medicion_de_si_mismo"] = {
        "coste_verificacion_s": coste,
        "coste_compuerta_total_s": round(total, 4),
        "ratio_sobre_compuerta": round(coste / total, 9) if total else None,
    }
    rec["medicion_de_si_mismo"]["P2_sobrevive"] = bool(
        total and rec["medicion_de_si_mismo"]["ratio_sobre_compuerta"] <= 0.01
    )
    rec["medicion_de_si_mismo"]["reproducible"] = True

    if args.check:
        if sellado.get("huella") == rec["huella"]:
            print(f"RECIBO VERIFICADO: {rec['huella']} · {args.check}")
            return 0
        print(f"HUELLA DISTINTA: sellada {sellado.get('huella')} · recomputada {rec['huella']}", file=sys.stderr)
        return 4

    args.salida.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
    print(_resumen_legible(rec))
    print(f"\ncoste de emitir el recibo: {coste} s"
          f" · {rec['medicion_de_si_mismo']['ratio_sobre_compuerta']} de la compuerta")
    print(f"escrito: {args.salida} · huella {rec['huella']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
