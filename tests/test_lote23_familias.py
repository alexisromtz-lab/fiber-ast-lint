"""El lote 23 mide la precision por familia y descubre que el denominador estaba mal elegido.

El recibo del lote 22 dejo escrito su proximo acto: separar lo confirmado de lo refutado por la
familia que el instrumento declaro, sin releer una sola linea, porque el denominador ya se habia
pagado leyendo. Este fichero custodia lo que un cambio posterior romperia sin hacer ruido: que el
pre-registro se sello antes de cruzar una fila, que la cifra relayada se reprodujo antes de usarla,
que los tres veredictos se sostienen en su aritmetica, y que la compuerta que sale del cruce se
publica como candidata y no como resultado.

Nada aqui se afirma por lectura del recibo: cada aserto recalcula desde las 125 filas del lote 22,
que son el unico sujeto del acto. La razon de verosimilitud se rehace con `Fraction`, de modo que
un recibo que cambie de datos y no de veredicto falle.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PRE_REGISTRO = RAIZ / "prediccion-batch-23.json"
FUENTE = RAIZ / "recibo-lote22-20261127.json"
RECIBO = RAIZ / "recibo-lote23-20261127.json"
DETECT = RAIZ / "src" / "fiber_ast_lint" / "detect.py"

CAUSA_BENIGNA = ("proyeccion_inyectiva", "escritura_posicional")
CAUSA_TAUTOLOGICA = "proyeccion_no_inyectiva_sin_medicion"
VEREDICTOS = {"CONFIRMADO", "REFUTADO", "NO_MEDIDO"}


def _cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _loci() -> list[dict]:
    return _cargar(FUENTE)["loci"]


def _adjudicados() -> list[dict]:
    return [x for x in _loci() if x["veredicto"] in ("CONFIRMADO", "REFUTADO")]


def _benigna(fila: dict) -> bool:
    return fila["causa"] in CAUSA_BENIGNA


def test_el_pre_registro_se_sello_antes_de_cruzar_una_fila() -> None:
    recibo = _cargar(RECIBO)["pre_registro"]
    assert recibo["ruta"] == PRE_REGISTRO.name
    assert recibo["bytes"] == len(PRE_REGISTRO.read_bytes())
    assert recibo["sha256"] == _sha(PRE_REGISTRO)
    assert recibo["verificado_en_este_acto"] == _sha(PRE_REGISTRO)
    assert recibo["declarado_antes"] is True
    assert _cargar(PRE_REGISTRO)["declared_before_computation"] is True


def test_el_sujeto_es_el_recibo_del_lote_22_y_no_se_re_adjudica() -> None:
    recibo = _cargar(RECIBO)
    assert recibo["fuente"]["sha256"] == _sha(FUENTE)
    assert recibo["fuente"]["loci"] == len(_loci()) == 125
    assert "loci" not in recibo, (
        "el acto cuenta filas que ya existen: copiarlas aqui seria una segunda fuente de verdad"
    )
    assert recibo["medicion"]["relojes_nuevos"] == 0
    assert recibo["medicion"]["clones"] == 0


def test_el_instrumento_no_se_movio_y_el_acto_no_lo_ejecuto() -> None:
    instrumento = _cargar(RECIBO)["instrumento"]
    vivo = _sha(DETECT)
    assert instrumento["detect_py_sha256_antes"] == vivo
    assert instrumento["detect_py_sha256_despues"] == vivo
    assert instrumento["congelado"] is True


def test_los_tres_veredictos_reconcilian_y_el_invariante_cierra() -> None:
    loci = _loci()
    cuenta = Counter(x["veredicto"] for x in loci)
    assert set(cuenta) == VEREDICTOS, cuenta
    assert cuenta["CONFIRMADO"] + cuenta["REFUTADO"] + cuenta["NO_MEDIDO"] == len(loci) == 125
    assert len({(x["sujeto"], x["archivo"], x["linea"]) for x in loci}) == len(loci)
    for clave in ("familia", "causa", "veredicto"):
        assert all(x[clave] for x in loci), clave


def test_la_cifra_relayada_se_reprodujo_antes_de_usarla() -> None:
    """Una cifra que llega de fuera se recomputa o se declara creida. Aqui se recomputa."""
    publicado = _cargar(RECIBO)["reproduccion_de_la_cifra_relayada"]
    benignas = [x for x in _loci() if _benigna(x)]
    candidatas = [x for x in _loci() if not _benigna(x)]
    assert publicado["recomputada"]["benignas"] == len(benignas)
    assert publicado["recomputada"]["candidatas"] == len(candidatas)
    assert len(benignas) + len(candidatas) == 125
    assert publicado["coincide"] is True
    assert publicado["reparto_por_veredicto"]["benignas"] == dict(
        Counter(x["veredicto"] for x in benignas)
    )
    assert publicado["reparto_por_veredicto"]["candidatas"] == dict(
        Counter(x["veredicto"] for x in candidatas)
    )


def test_la_tabla_de_familias_se_recomputa() -> None:
    publicado = {f["familia"]: f for f in _cargar(RECIBO)["tabla_familia"]}
    familias = sorted({x["familia"] for x in _loci()})
    assert sorted(publicado) == familias
    for familia in familias:
        filas = [x for x in _loci() if x["familia"] == familia]
        real = {
            "familia": familia,
            "n": len(filas),
            "confirmados": sum(x["veredicto"] == "CONFIRMADO" for x in filas),
            "refutados": sum(x["veredicto"] == "REFUTADO" for x in filas),
            "no_medidos": sum(x["veredicto"] == "NO_MEDIDO" for x in filas),
            "causa_benigna": sum(_benigna(x) for x in filas),
        }
        assert publicado[familia] == real, familia


def test_la_tabla_de_causas_se_recomputa() -> None:
    publicado = {c["causa"]: c for c in _cargar(RECIBO)["tabla_causa"]}
    causas = sorted({x["causa"] for x in _loci()})
    assert sorted(publicado) == causas
    for causa in causas:
        filas = [x for x in _loci() if x["causa"] == causa]
        real = {
            "causa": causa,
            "n": len(filas),
            "confirmados": sum(x["veredicto"] == "CONFIRMADO" for x in filas),
            "refutados": sum(x["veredicto"] == "REFUTADO" for x in filas),
            "no_medidos": sum(x["veredicto"] == "NO_MEDIDO" for x in filas),
            "benigna": causa in CAUSA_BENIGNA,
            "tautologica": causa == CAUSA_TAUTOLOGICA,
        }
        assert publicado[causa] == real, causa


def _razon_de_verosimilitud(familia: str) -> tuple[Fraction, int, int, int, int]:
    adj = _adjudicados()
    confirmados = sum(x["veredicto"] == "CONFIRMADO" for x in adj)
    refutados = sum(x["veredicto"] == "REFUTADO" for x in adj)
    a = sum(x["veredicto"] == "CONFIRMADO" and x["familia"] == familia for x in adj)
    b = sum(x["veredicto"] == "REFUTADO" and x["familia"] == familia for x in adj)
    return Fraction(a, confirmados), a, confirmados, b, refutados


def test_p1_cae_por_denominador_cero_y_la_sensibilidad_se_publica() -> None:
    """El falsador se dispara por la forma que el pre-registro declaro: el denominador es cero.

    Un cero de denominador no es una razon infinita: es un estadistico que no existe sobre esta
    particion. El recibo tiene que decir las dos cosas y ademas publicar con que suavizado el
    predicado se cumpliria, para que el veredicto no dependa de un prior que nadie declaro.
    """
    _razon, a, confirmados, b, refutados = _razon_de_verosimilitud("CAJA+RUTA")
    assert b == 0 and a > 0, (a, confirmados, b, refutados)
    publicado = {v["id"]: v for v in _cargar(RECIBO)["veredictos"]}["P1"]
    assert publicado["veredicto"] == "REFUTADA"
    assert publicado["causa"] == "denominador_cero"
    familias = {x["familia"] for x in _loci()}
    lapace_1 = Fraction(a + 1, confirmados + len(familias)) / Fraction(
        b + 1, refutados + len(familias)
    )
    assert publicado["sensibilidad_declarada_y_publicada"]["laplace_alfa_1"] == float(lapace_1)
    assert lapace_1 > 3, (
        "si el suavizado no salvara el predicado, el veredicto no seria ambiguo y el recibo "
        "estaria publicando una sensibilidad que no explica nada"
    )
    assert "no es una victoria del predicado" in publicado["el_caso_sustantivo_queda_en_no_medido"]


def test_la_particion_es_rala_y_ese_es_el_motivo_de_la_caida() -> None:
    """La razon de verosimilitud por familia exige celdas con denominador; esta tabla no las tiene."""
    conteo = Counter(x["familia"] for x in _loci())
    ralas = sum(1 for n in conteo.values() if n <= 2)
    publicado = {v["id"]: v for v in _cargar(RECIBO)["veredictos"]}["P1"]
    assert f"y {ralas} de ellas no pasan de dos filas" in publicado["por_que_el_predicado_heredado_no_podia_funcionar"]
    assert len(conteo) >= 19 and ralas * 2 > len(conteo), (len(conteo), ralas)


def test_p2_se_confirma_con_la_aritmetica_del_recibo() -> None:
    familias = Counter(x["familia"] for x in _loci() if x["veredicto"] == "CONFIRMADO")
    assert sum(familias.values()) == 10
    assert len(familias) >= 2, familias
    publicado = {v["id"]: v for v in _cargar(RECIBO)["veredictos"]}["P2"]
    assert publicado["veredicto"] == "CONFIRMADA"
    for familia, n in familias.items():
        assert f"{familia} x{n}" in publicado["evidencia"], familia


def _familias_del_acoplamiento() -> tuple[list[str], list[str]]:
    """Las dos mitades de P3: familias benignas sin confirmar, y familias que confirman sin benignas."""
    conteo = {}
    for familia in {x["familia"] for x in _loci()}:
        filas = [x for x in _loci() if x["familia"] == familia]
        conteo[familia] = (
            sum(_benigna(x) for x in filas),
            sum(x["veredicto"] == "CONFIRMADO" for x in filas),
        )
    con_benignas = sorted(f for f, (b, c) in conteo.items() if b >= 10 and c == 0)
    con_confirmados = sorted(f for f, (b, c) in conteo.items() if c > 0 and b == 0)
    return con_benignas, con_confirmados


def test_p3_se_confirma_y_nombra_las_familias_que_lo_sostienen() -> None:
    con_benignas, con_confirmados = _familias_del_acoplamiento()
    assert con_benignas, "ninguna familia acumula diez causas benignas sin un confirmado"
    assert con_confirmados, "ninguna familia confirma sin cargar causas benignas"
    evidencia = {v["id"]: v for v in _cargar(RECIBO)["veredictos"]}["P3"]["evidencia"]
    for familia in con_benignas + con_confirmados:
        assert familia in evidencia, familia


def test_la_supresion_de_superficie_no_pierde_ningun_confirmado() -> None:
    """La compuerta que sale del cruce: dos familias enteras fuera, cero confirmados dentro."""
    con_benignas, _ = _familias_del_acoplamiento()
    publicado = _cargar(RECIBO)["medido_despues_del_pre_registro"][
        "la_supresion_de_superficie_cuesta_cero"
    ]
    assert publicado["familias"] == con_benignas
    dentro = [x for x in _loci() if x["familia"] not in con_benignas]
    fuera = [x for x in _loci() if x["familia"] in con_benignas]
    assert publicado["filas_suprimidas"] == len(fuera)
    assert publicado["confirmados_suprimidos"] == 0
    adj_dentro = [x for x in dentro if x["veredicto"] in ("CONFIRMADO", "REFUTADO")]
    assert publicado["precision_antes"]["denominador"] == len(_adjudicados())
    assert publicado["precision_despues"]["denominador"] == len(adj_dentro)
    assert publicado["factor"] > 1, "una compuerta que no mejora la precision no es una compuerta"


def test_la_compuerta_se_publica_como_candidata_y_no_como_resultado() -> None:
    """Las familias se eligieron mirando las mismas filas: eso es seleccion, y hay que decirlo."""
    publicado = _cargar(RECIBO)["medido_despues_del_pre_registro"][
        "la_supresion_de_superficie_cuesta_cero"
    ]
    assert "seleccion posterior" in publicado["nota"]
    politica = _cargar(RECIBO)["politica"]
    assert politica["supresion_de_superficie"].startswith("se adopta como compuerta candidata")
    assert politica["familia_como_discriminador"].startswith("no se vende")
    assert politica["causa_como_clasificador"].startswith("no se vende")


def test_la_causa_que_separa_perfectamente_es_una_tautologia_declarada() -> None:
    """Reproduce la definicion de CONFIRMADO: se publica para que no se lea como hallazgo."""
    filas = [x for x in _loci() if x["causa"] == CAUSA_TAUTOLOGICA]
    assert filas, "la causa tautologica no aparece en el recibo del lote 22"
    assert [] == [x for x in filas if x["veredicto"] != "CONFIRMADO"]
    confirmados = {x["causa"] for x in _loci() if x["veredicto"] == "CONFIRMADO"}
    assert confirmados == {CAUSA_TAUTOLOGICA}, confirmados
    declarado = _cargar(RECIBO)["medido_despues_del_pre_registro"][
        "la_causa_separa_perfectamente_y_es_una_tautologia"
    ]
    assert f"tiene {len(filas)} filas" in declarado["medido"]
    assert "no informa" in declarado["por_que_no_se_vende"]


def test_toda_cifra_de_la_causa_benigna_cierra_con_las_filas() -> None:
    """Las 85 benignas se reparten en familias y causas sin dejar sumando huerfano."""
    benignas = [x for x in _loci() if _benigna(x)]
    assert all(x["veredicto"] == "REFUTADO" for x in benignas), (
        "una causa benigna confirmada seria una contradiccion en el vocabulario del lote 22"
    )
    por_familia = sum(
        f["causa_benigna"] for f in _cargar(RECIBO)["tabla_familia"]
    )
    por_causa = sum(f["n"] for f in _cargar(RECIBO)["tabla_causa"] if f["benigna"])
    assert por_familia == por_causa == len(benignas) == 85


def test_el_proximo_acto_tiene_falsador_con_sujeto_y_no_amplia_el_denominador() -> None:
    proximo = _cargar(RECIBO)["proximo_acto"]
    assert set(proximo) >= {"nombre", "predicado", "falsador", "requisito", "coste"}
    assert "recibo-lote24-20261127.json" in proximo["falsador"]
    assert "detect.py" in proximo["falsador"]
    assert "clones" in proximo["coste"]
    assert _cargar(RECIBO)["no_se_hizo"]["reportes_abiertos"] == 0
