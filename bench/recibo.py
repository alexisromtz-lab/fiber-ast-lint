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

# El interprete de predicados es del contrato v3. Un recibo v1 o v2 se verifica sin el al
# lado: el claim comercial es que un tercero con el recibo, la prediccion y el artefacto
# recomputa el veredicto, y cobrarle un modulo que su contrato no nombra lo rompe en silencio.
_MOD = None


class _Interprete:
    """Carga ``predicado`` desde el directorio de este archivo, la primera vez que se usa."""

    def __getattr__(self, nombre):
        global _MOD
        if _MOD is None:
            aqui = str(Path(__file__).resolve().parent)
            if aqui not in sys.path:
                sys.path.insert(0, aqui)
            import predicado as m

            _MOD = m
        return getattr(_MOD, nombre)


predicado = _Interprete()

RELOJES_SONDA = 9
ZONAS = ("margen_sano", "banda_de_riesgo", "fuera_de_cota")
VOLATILES = ("huella", "medicion_de_si_mismo")

CONTRATO_V1 = "fiber-ast-lint/recibo/1"
CONTRATO_V2 = "fiber-ast-lint/recibo/2"
CONTRATO_V3 = "fiber-ast-lint/recibo/3"

# Causas cerradas de un veredicto NO_MEDIDO. Una causa fuera de este conjunto es un
# defecto del instrumento, no una medida: ausencia declarada, nunca ausencia omitida.
# Las tres del contrato v2 quedan congeladas: su recuento viaja dentro de la huella de los
# cuatro recibos sellados del lote 13, y una causa nueva re-firmaria lo ya publicado.
CAUSAS_V2 = ("sin_evaluador", "metrica_ausente", "fuera_de_la_huella")
CAUSAS = CAUSAS_V2 + ("sin_predicado", "predicado_ilegible", "poblacion_vacia")

# Magnitudes que el recibo publica por acto para que un predicado pueda apuntarlas. Son
# lecturas del sujeto, no juicios: quien juzga es el predicado, y el recibo solo tiene que
# llevar consigo la resolucion suficiente para que un tercero lo haga sin el artefacto.
CAMPOS_HECHO = (
    "minimo_s", "jitter_s", "mediana_s", "p50_min_s", "p50_max_s", "minimo_publicable_s",
    "predicho_s", "q", "relojes", "lecturas_n", "n_bloques", "bytes_py_pin", "dispersion",
    "coste_compuerta_s", "coste_arnes_s", "trabajo_s", "sonda_sobre_min",
    "sonda_jitter_sobre_jitter", "arranque_sobre_sonda", "coste_sobre_trabajo",
)
CAMPOS_BLOQUE = ("min_s", "p50_s", "max_s", "jitter_s", "n")


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


def _leer_predicciones(ruta: Path | None) -> list[dict] | None:
    """Las predicciones completas: el juicio necesita la declaracion, no solo su prosa.

    Devuelve None cuando no hay pre-registro, que no es lo mismo que una lista vacia: el
    recibo tiene que poder distinguir "no se declaro nada" de "se declaro y no se midio".
    """
    if ruta is None or not ruta.exists():
        return None
    return list(json.loads(ruta.read_text()).get("predictions", []))


def _ruta_prediccion(lote: int | None, junto_a: Path,
                     sellado: dict | None = None) -> Path | None:
    """El pre-registro del lote que el recibo cita, si vive junto al recibo.

    El sello declara su pre-registro y esa declaracion vence al default: un recibo puede
    juzgar las predicciones de un lote anterior bajo las reglas de uno nuevo, y adivinar por
    numero de lote lo haria citar un texto que no es el que sus veredictos juzgaron.
    """
    decl = (sellado or {}).get("pre_registro") or {}
    if decl.get("ruta"):
        ruta = junto_a / decl["ruta"]
        if ruta.exists():
            return ruta
    if lote is None:
        return None
    ruta = junto_a / f"prediccion-batch-{lote}.json"
    return ruta if ruta.exists() else None


def _cita_prediccion(ruta: Path | None) -> dict | None:
    """El pre-registro citado con su huella: el juicio viaja con la prueba de que fue previo."""
    if ruta is None or not ruta.exists():
        return None
    crudo = ruta.read_bytes()
    pred = json.loads(crudo)
    return {
        "ruta": ruta.name,
        "sha256": hashlib.sha256(crudo).hexdigest(),
        "predictions": len(pred.get("predictions", [])),
        "declared_before_computation": bool(pred.get("declared_before_computation")),
    }


def _ev_p1(resumen: dict, por_acto: list[dict]) -> tuple[dict, bool] | None:
    pub = resumen["publicables_como_booleano"]
    riesgo = resumen["en_banda_de_riesgo_n"]
    if not resumen["actos"]:
        return None
    return (
        {"publicables": pub, "en_banda_de_riesgo": riesgo, "actos": resumen["actos"]},
        bool(pub) and 1 <= riesgo and riesgo * 2 <= pub,
    )


def _ev_p4(resumen: dict, por_acto: list[dict]) -> tuple[dict, bool] | None:
    """Sin coste medido no hay veredicto: la ausencia de la metrica no es una caida."""
    cotizados = [a for a in por_acto if a["cotizacion"]]
    if not cotizados:
        return None
    caro = max(cotizados, key=lambda a: a["coste_compuerta_s"])
    usos = caro["cotizacion"]["usos_para_amortizar"]
    return (
        {"acto_mas_caro": caro["nombre"], "usos_para_amortizar": usos,
         "usos_sin_arnes": caro["cotizacion"]["usos_sin_arnes"]},
        bool(20 <= usos <= 40),
    )


EVALUADORES = {"P1": _ev_p1, "P4": _ev_p4}
EVALUA = {
    "P1": "el booleano dice si con el margen ya consumido en al menos un acto y en no mas de la mitad",
    "P4": "la compuerta de noventa relojes solo se amortiza con volumen, entre veinte y cuarenta usos",
}
# Predicciones cuya magnitud se mide, pero fuera de la huella: un veredicto sobre la
# verificacion o sobre la propia huella no puede viajar dentro de la huella que firma.
# El default de la ausencia para lo que no la declara. El contrato v1 la lee siempre desde
# aqui y por eso se queda: su recuento viaja dentro de la huella de los recibos sellados. En
# v3 una regla declarada vence a esta tabla, y la tabla solo responde por lo que calla.
FUERA_DE_LA_HUELLA = {
    "P2": "tests/test_recibo.py::test_verificar_el_recibo_cuesta_menos_de_una_centesima_parte_de_medir_la_compuerta",
    "P3": "tests/test_recibo.py::test_la_huella_se_reproduce_con_jq_y_shasum_sin_python",
}


def _evaluar(pid: str, resumen: dict, por_acto: list[dict]) -> tuple[dict, bool] | None:
    ev = EVALUADORES.get(pid)
    return None if ev is None else ev(resumen, por_acto)


def _veredictos_v2(resumen: dict, por_acto: list[dict], preds: list[dict] | None) -> list[dict]:
    """Un registro por prediccion declarada, y ninguno mas.

    El lector v1 devolvia lista vacia cuando no conocia el identificador, de modo que un
    pre-registro con predicciones y un pre-registro sin ellas producian el mismo recibo.
    Aqui lo que el instrumento no sabe medir se publica NO_MEDIDO con su causa: la
    poblacion juzgada tiene que igualar la poblacion declarada, o el silencio miente.
    """
    out = []
    for p in preds or []:
        pid = p["id"]
        base = {"id": pid, "prediccion": p.get("claim")}
        if pid in FUERA_DE_LA_HUELLA:
            out.append({**base, "estado": "no_medido", "causa": "fuera_de_la_huella",
                        "locus": FUERA_DE_LA_HUELLA[pid]})
            continue
        if pid not in EVALUADORES:
            out.append({**base, "estado": "no_medido", "causa": "sin_evaluador"})
            continue
        r = _evaluar(pid, resumen, por_acto)
        if r is None:
            out.append({**base, "estado": "no_medido", "causa": "metrica_ausente",
                        "evalua": EVALUA[pid]})
            continue
        medido, sobrevive = r
        out.append({**base, "estado": "evaluado", "medido": medido,
                    "sobrevive": sobrevive, "evalua": EVALUA[pid]})
    return out


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


def recibo_v2(arte: dict, fuente: str, lote: int | None = None,
              pred_ruta: Path | None = None) -> dict:
    """El recibo del contrato recibo/2: la poblacion juzgada iguala la declarada.

    No reescribe nada del cuerpo: parte del mismo recibo y le cambia el juicio. El contrato
    v1 sigue vivo al lado, congelado, porque verificar un recibo publicado exige el lector
    del contrato que ese recibo declara y no el que este codigo prefiera.
    """
    rec = recibo(arte, fuente, lote)
    preds = _leer_predicciones(pred_ruta)
    rec["schema"] = CONTRATO_V2
    rec["pre_registro"] = _cita_prediccion(pred_ruta)
    rec["veredictos"] = _veredictos_v2(rec["resumen"], rec["actos"], preds)
    rec["resumen"]["veredictos"] = {
        "declaradas": None if preds is None else len(preds),
        "emitidas": len(rec["veredictos"]),
        "evaluadas": sum(1 for v in rec["veredictos"] if v["estado"] == "evaluado"),
        "no_medidas": sum(1 for v in rec["veredictos"] if v["estado"] == "no_medido"),
        "causas": {c: sum(1 for v in rec["veredictos"] if v.get("causa") == c) for c in CAUSAS_V2},
    }
    rec["huella"] = huella(rec)
    return rec


def _hechos(acto: dict) -> dict:
    """Las magnitudes del acto, en la resolucion que un predicado necesita.

    Se publican tal como el artefacto las declaro, sin reinterpretar: los derivados que se
    anaden son cocientes entre dos campos ya presentes, y ninguno decide nada. Los bloques
    van sin sus lecturas crudas -- esas viven en el artefacto, que el recibo cita por hash --
    pero con su minimo, su maximo y su jitter, que es lo que una prediccion sobre mitades
    necesita y no puede reconstruir desde el agregado del acto.
    """
    out = {}
    for c in CAMPOS_HECHO:
        v = acto.get(c)
        if isinstance(v, bool) or v is None:
            continue
        out[c] = round(v, 6) if isinstance(v, float) else v
    mn, jt = acto.get("minimo_s"), acto.get("jitter_s")
    if isinstance(mn, (int, float)) and isinstance(jt, (int, float)) and jt:
        out["ratio_min_jitter"] = round(mn / jt, 6)
    coste, relojes, mediana = (acto.get("coste_compuerta_s"), acto.get("relojes"),
                               acto.get("mediana_s"))
    if "coste_sobre_trabajo" not in out and None not in (coste, relojes, mediana) and relojes * mediana:
        out["coste_sobre_trabajo"] = round(coste / (relojes * mediana), 6)
    bloques = acto.get("bloques")
    if isinstance(bloques, list) and bloques and all(isinstance(b, dict) for b in bloques):
        out["bloques"] = [{k: (round(b[k], 6) if isinstance(b.get(k), float) else b.get(k))
                           for k in CAMPOS_BLOQUE if k in b} for b in bloques]
    return out


def _resolucion(rec: dict) -> dict:
    """La vista sobre la que un predicado resuelve: las secciones, no la firma."""
    return {k: rec[k] for k in ("lote", "sujeto", "actos", "resumen",
                                "dispersiones_por_sesion") if k in rec}


def _ausencia(pid: str, ausencias: dict) -> dict:
    """El registro de una prediccion que no se traduce: la causa es una propiedad declarada.

    Antes de este lote la unica fuente era ``FUERA_DE_LA_HUELLA``, una tabla indexada por
    identificador: el juicio negativo seguia dependiendo del nombre aunque el positivo ya no.
    Ahora manda la declaracion de la traduccion y la tabla queda como default para lo que no
    declara nada. El ``por_que`` del fichero no viaja al veredicto: documenta la ausencia sin
    mover la huella de un recibo que solo cambia de procedencia.
    """
    a = ausencias.get(pid) or {}
    motivo = a.get("motivo")
    if not motivo:
        if pid in FUERA_DE_LA_HUELLA:
            return {"estado": "no_medido", "causa": "fuera_de_la_huella",
                    "locus": FUERA_DE_LA_HUELLA[pid]}
        return {"estado": "no_medido", "causa": "sin_predicado"}
    if motivo not in CAUSAS:
        motivo = "sin_predicado"
    fuera = {"estado": "no_medido", "causa": motivo}
    if a.get("locus"):
        fuera["locus"] = a["locus"]
    return fuera


def _veredictos_v3(rec: dict, preds: list[dict] | None, mapa: dict,
                   ausencias: dict | None = None) -> list[dict]:
    """Un registro por prediccion declarada, juzgado por su predicado y no por su nombre.

    Ninguna rama de esta funcion consulta el identificador para decidir el juicio: el
    identificador solo sirve para buscar la traduccion y para etiquetar el registro. Lo que
    el pre-registro no traduce se publica con la causa que la traduccion declare, y lo que el
    interprete no entiende se publica ``predicado_ilegible``; las dos son causas, ninguna es
    una caida.

    El defecto de gramatica se decide con ``predicado.validar`` **antes** de leer un valor: es
    deuda del lenguaje, y confundirla con la deuda del dato es lo que hacia que las dos se
    contaran como la misma cifra.
    """
    doc = _resolucion(rec)
    out = []
    for p in preds or []:
        pid = p["id"]
        base = {"id": pid, "prediccion": p.get("claim")}
        traducido = mapa.get(pid)
        if traducido is None:
            out.append({**base, **_ausencia(pid, ausencias or {})})
            continue
        defectos = predicado.validar(traducido["evalua"])
        if defectos:
            out.append({**base, "estado": "no_medido", "causa": "predicado_ilegible",
                        "detalle": "; ".join(defectos),
                        "evalua": traducido.get("expresa", "")})
            continue
        r = predicado.evaluar(traducido["evalua"], doc)
        if r["estado"] == "no_medido":
            out.append({**base, **{k: v for k, v in r.items() if k != "estado"},
                        "estado": "no_medido",
                        "evalua": traducido.get("expresa", "")})
            continue
        out.append({**base, "estado": "evaluado", "sobrevive": r["sobrevive"],
                    "medido": r["medido"], "evalua": traducido.get("expresa", ""),
                    "via": "predicado"})
    return out


def recibo_v3(arte: dict, fuente: str, lote: int | None = None,
              pred_ruta: Path | None = None, predc_ruta: Path | None = None) -> dict:
    """El contrato recibo/3: el juicio es funcion del predicado, no del identificador.

    Parte del recibo v2 y le anade lo que un interprete necesita para juzgar sin el
    artefacto: los hechos por acto, las dispersiones con su mediana, y la cita del fichero
    de predicados que traduce el pre-registro. El pre-registro no se toca: la traduccion lo
    cita por sha256, y si el texto cambia el predicado deja de valer.
    """
    rec = recibo_v2(arte, fuente, lote, pred_ruta)
    crudos = {a["nombre"]: a for a in _actos(arte)}
    for a in rec["actos"]:
        a["hechos"] = _hechos(crudos.get(a["nombre"], {}))
    por_sesion: dict[int, list[float]] = {}
    for a in rec["actos"]:
        if a["sesion"] is not None:
            por_sesion.setdefault(a["sesion"], []).append(a["k"])
    rec["dispersiones_por_sesion"] = {}
    for s, ks in sorted(por_sesion.items()):
        orden = sorted(ks)
        n = len(orden)
        mediana = orden[n // 2] if n % 2 else round((orden[n // 2 - 1] + orden[n // 2]) / 2, 6)
        rec["dispersiones_por_sesion"][str(s)] = {
            "n": n,
            "k_min": round(min(ks), 6),
            "k_max": round(max(ks), 6),
            "k_mediana": mediana,
            "dispersion": round(max(ks) / min(ks), 6) if n > 1 else None,
        }
    mapa, cita, ausencias = predicado.leer(predc_ruta,
                                           junto_a=predc_ruta.parent if predc_ruta else None)
    preds = _leer_predicciones(pred_ruta)
    if cita is not None and rec.get("pre_registro") is not None:
        if cita["cita_pre_registro"]["sha256"] != rec["pre_registro"]["sha256"]:
            raise predicado.Ilegible(
                f"el predicado traduce {cita['cita_pre_registro']['ruta']}"
                f" {cita['cita_pre_registro']['sha256']} y el recibo cita"
                f" {rec['pre_registro']['sha256']}")
    rec["schema"] = CONTRATO_V3
    rec["predicados"] = cita
    rec["veredictos"] = _veredictos_v3(rec, preds, mapa, ausencias)
    rec["resumen"]["veredictos"] = {
        "declaradas": None if preds is None else len(preds),
        "emitidas": len(rec["veredictos"]),
        "evaluadas": sum(1 for v in rec["veredictos"] if v["estado"] == "evaluado"),
        "no_medidas": sum(1 for v in rec["veredictos"] if v["estado"] == "no_medido"),
        "causas": {c: sum(1 for v in rec["veredictos"] if v.get("causa") == c) for c in CAUSAS},
    }
    rec["huella"] = huella(rec)
    return rec


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
        via = f" [{v['via']}]" if v.get("via") else ""
        if v.get("estado") == "evaluado":
            lineas.append(f"{v['id']}: {'sobrevive' if v['sobrevive'] else 'CAE'}{via} · {v['medido']}")
        elif v.get("estado") == "no_medido":
            lineas.append(f"{v['id']}: NO_MEDIDO · {v['causa']}")
        else:
            lineas.append(f"{v['id']}: {'sobrevive' if v['sobrevive'] else 'CAE'} · {v['medido']}")
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Recibo con banda sobre un artefacto sellado.")
    ap.add_argument("--artefacto", required=True, type=Path)
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--check", type=Path, help="recomputa y compara la huella con este recibo")
    ap.add_argument("--lote", type=int, help="lote de la emision; por defecto, el del artefacto")
    ap.add_argument("--prediccion", type=Path,
                    help="pre-registro que el recibo cita; sin el, el recibo no emite veredictos")
    ap.add_argument("--predicados", type=Path,
                    help="traduccion del pre-registro a expresiones evaluables (contrato recibo/3)")
    ap.add_argument("--contrato", choices=(CONTRATO_V1, CONTRATO_V2, CONTRATO_V3),
                    default=CONTRATO_V3,
                    help="contrato que se emite; al verificar manda el que el fichero declara")
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
    # El contrato tambien: verificar un recibo publicado usa el lector del contrato que el
    # recibo declara, no el que este codigo prefiera, o la evolucion reescribe lo firmado.
    contrato = (sellado or {}).get("schema") or args.contrato
    lote = args.lote if args.lote is not None else (sellado.get("lote") if sellado else None)
    if args.prediccion:
        pred_ruta = args.prediccion
    elif sellado and (sellado.get("veredictos") or sellado.get("pre_registro")):
        pred_ruta = _ruta_prediccion(lote, args.check.parent, sellado)
    else:
        pred_ruta = None
    # La traduccion tampoco se adivina: la declara el recibo sellado, o el argumento.
    if args.predicados:
        predc_ruta = args.predicados
    elif sellado and sellado.get("predicados"):
        predc_ruta = args.check.parent / sellado["predicados"]["ruta"]
    elif contrato == CONTRATO_V3 and lote is not None:
        candidato = Path(__file__).resolve().parent.parent / f"predicado-batch-{lote}.json"
        predc_ruta = candidato if candidato.exists() else None
    else:
        predc_ruta = None

    # Un v3 sin interprete al lado no se verifica: se declara, no se degrada a verde.
    if contrato == CONTRATO_V3:
        try:
            fallo_predicado = (predicado.Ilegible,)
        except ModuleNotFoundError as e:
            print(f"el contrato v3 necesita predicado.py junto al recibo: {e}", file=sys.stderr)
            return 5
    else:
        fallo_predicado = ()

    t0 = time.perf_counter()
    try:
        if contrato == CONTRATO_V1:
            rec = _reanclar_veredictos(recibo(arte, str(args.artefacto), lote),
                                       _leer_prediccion(pred_ruta))
        elif contrato == CONTRATO_V2:
            rec = recibo_v2(arte, str(args.artefacto), lote, pred_ruta)
        else:
            rec = recibo_v3(arte, str(args.artefacto), lote, pred_ruta, predc_ruta)
    except fallo_predicado as e:
        print(f"predicado ilegible: {e}", file=sys.stderr)
        return 5
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
