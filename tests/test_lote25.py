"""El recibo del lote 25 se recalcula, no se lee.

Estos casos no comprueban que el fichero contenga ciertos numeros: los vuelven a
computar desde las tablas del propio recibo y desde los ficheros que el recibo
dice haber usado. Si alguien edita una fila, un sha o un veredicto, el caso que
lo cubre falla aunque el fichero siga siendo JSON valido.

La unica cosa que no se recalcula es la lectura del locus --juicio humano sobre
la columna de contexto--, y por eso lo que se exige de ella no es que valga 1
sino que toda fila decidida la tenga, con su texto y su contexto publicados.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import re

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
RECIBO = RAIZ / "recibo-lote25-20261127.json"
POSICIONAL = "escritura_posicional"
NO_PARSEA = "fichero_no_parsea"
DECIDIBLES = (POSICIONAL, NO_PARSEA)
DESPACHADOR = re.compile(r"\.(loc|iloc|at|iat)\s*\[")
UMBRAL = 0.90
MINIMO_PARA_INTERVALO = 35
Z95 = 1.959963984540054


def _sha(ruta: pathlib.Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def recibo() -> dict:
    return json.loads(RECIBO.read_text(encoding="utf-8"))


def _coordenada(fila: dict) -> tuple:
    return (fila["sujeto"], fila["archivo"], fila["linea"])


def _wilson(aciertos: int, n: int) -> tuple[float, float]:
    p = aciertos / n
    centro = 2 * n * p + Z95 * Z95
    radio = Z95 * math.sqrt(Z95 * Z95 + 4 * n * p * (1 - p))
    return (centro - radio) / (2 * (n + Z95 * Z95)), (centro + radio) / (2 * (n + Z95 * Z95))


def test_el_recibo_cita_el_sello_que_lo_gobierna(recibo: dict) -> None:
    sello = RAIZ / recibo["pre_registro"]["archivo"]
    assert recibo["pre_registro"]["sha256"] == _sha(sello)
    declarado = json.loads(sello.read_text(encoding="utf-8"))
    assert declarado["batch"] == recibo["batch"]
    assert [p["id"] for p in declarado["predictions"]] == [v["id"] for v in recibo["veredictos"]]


def test_el_instrumento_del_recibo_es_el_que_corre(recibo: dict) -> None:
    for clave in ("detect", "adjudicador_v10", "adjudicador_v11", "corredor"):
        artefacto = recibo["instrumento"][clave]
        assert artefacto["sha256"] == _sha(RAIZ / artefacto["archivo"]), clave
    assert recibo["instrumento"]["detect"]["intacto"] is True
    assert recibo["corrida"]["detect_sha256_antes"] == recibo["corrida"]["detect_sha256_despues"]


def test_la_cohorte_nueva_es_la_congelada(recibo: dict) -> None:
    censo = json.loads((RAIZ / recibo["pre_registro"]["cohorte"]).read_text(encoding="utf-8"))
    assert recibo["pre_registro"]["cohorte_sha256"] == _sha(RAIZ / recibo["pre_registro"]["cohorte"])
    congelados = {f["sha"] for f in (censo["filas"] if "filas" in censo else censo["sujetos"])}
    medidos = {s["sha"] for s in recibo["fuera_de_muestra"]["sujetos"]}
    assert medidos == congelados
    assert len(medidos) == 20
    for s in recibo["fuera_de_muestra"]["sujetos"]:
        assert s["purga"] is True and s["reconcilia"] is True, s["repo"]
        assert s["sha"] == s["sha"].lower() and len(s["sha"]) == 40, s["repo"]


def test_la_cohorte_vieja_se_reproduce_sin_sobras_ni_faltas(recibo: dict) -> None:
    reproducidos = recibo["en_muestra"]["reproduccion_de_detect"]
    assert len(reproducidos) == recibo["en_muestra"]["sujetos"] == 20
    for s in reproducidos:
        assert s["ausentes"] == [], s["repo"]
        assert len(s["sobrantes"]) == s["loci_detect"] - s["esperados"], s["repo"]


def test_p1_decide_veinticinco_y_todas_publicadas(recibo: dict) -> None:
    medido = recibo["en_muestra"]
    filas = medido["tabla"]
    decididas = [f for f in filas if f["predicha"] in DECIDIBLES]
    assert len(filas) == 125
    assert len(decididas) == medido["decididas"] == 25
    assert medido["decididas_no_publicadas"] == []
    assert {f["publicada"] for f in decididas} == {POSICIONAL}


def test_p2_cero_contradicciones_sobre_las_adjudicadas(recibo: dict) -> None:
    medido = recibo["en_muestra"]
    adjudicadas = [f for f in medido["tabla"] if f["veredicto"] in ("CONFIRMADO", "REFUTADO")]
    contradicciones = [
        f for f in adjudicadas
        if f["predicha"] in DECIDIBLES and f["predicha"] != f["publicada"]
    ]
    assert len(adjudicadas) == medido["adjudicadas"] == 117
    assert contradicciones == []
    assert medido["contradicciones"] == 0


def test_p3_la_precision_se_recalcula_desde_las_lecturas(recibo: dict) -> None:
    medido = recibo["fuera_de_muestra"]["medicion"]
    filas = recibo["fuera_de_muestra"]["tabla"]
    decididas = [f for f in filas if f["predicha"] in DECIDIBLES]
    assert len(filas) == medido["candidatas"] == 118
    assert len(decididas) == medido["decididas"] == 67
    assert medido["abstenciones"] == len(filas) - len(decididas) == 51

    aciertos = sum(1 for f in decididas if f["lectura"] == "sostiene")
    assert aciertos == medido["aciertos"]
    assert medido["errores"] == len(decididas) - aciertos
    precision = aciertos / len(decididas)
    assert precision >= UMBRAL
    assert medido["precision_puntual"] == pytest.approx(precision)

    bajo, alto = _wilson(aciertos, len(decididas))
    assert medido["wilson_95"] == pytest.approx([bajo, alto])
    assert len(decididas) >= MINIMO_PARA_INTERVALO
    assert bajo >= UMBRAL


def test_p3_toda_fila_decidida_se_publica_con_su_evidencia(recibo: dict) -> None:
    decididas = [
        f for f in recibo["fuera_de_muestra"]["tabla"] if f["predicha"] in DECIDIBLES
    ]
    for f in decididas:
        assert f["lectura"] in ("sostiene", "residuo_declarado"), _coordenada(f)
        assert f["texto"].strip() and f["contexto"], _coordenada(f)
        assert f["nodo"] is True, _coordenada(f)
        assert f["piso"] == f["predicha"], _coordenada(f)


def test_el_residuo_del_despachador_es_cero_y_se_nombra(recibo: dict) -> None:
    decididas = [
        f for f in recibo["fuera_de_muestra"]["tabla"] if f["predicha"] in DECIDIBLES
    ]
    etiquetados = [f for f in decididas if DESPACHADOR.search(f["texto"])]
    declarados = recibo["fuera_de_muestra"]["lectura"]["residuo_declarado"]
    assert len(etiquetados) == len(declarados) == recibo["fuera_de_muestra"]["medicion"]["residuo_despachador"]
    assert [_coordenada(f) for f in etiquetados] == [_coordenada(f) for f in declarados]


def test_p4_la_capa_t1_no_depende_del_piso_del_parser(recibo: dict) -> None:
    for cohorte in ("en_muestra", "fuera_de_muestra"):
        piso = recibo["columnas_por_piso"][cohorte]
        assert piso["t1_igual"] is True, cohorte
        assert {tuple(x) for x in piso["t1_nativo"]} == {tuple(x) for x in piso["t1_piso"]}
        tabla = recibo[cohorte]["tabla"]
        decididas = {_coordenada(f) for f in tabla if f["predicha"] == POSICIONAL}
        assert decididas == {tuple(x) for x in piso["t1_nativo"]}
        assert sum(1 for f in tabla if f["predicha"] == NO_PARSEA) == piso["no_parsea_nativo"]
    assert recibo["columnas_por_piso"]["fuera_de_muestra"]["no_parsea_piso"] == 0
    assert recibo["columnas_por_piso"]["en_muestra"]["no_parsea_piso"] == 5


def test_los_veredictos_no_se_contradicen_con_su_medida(recibo: dict) -> None:
    for v in recibo["veredictos"]:
        assert v["veredicto"] == "SE CUMPLE", v["id"]
        assert v["medido"].strip(), v["id"]
    assert len(recibo["no_se_hizo"]) >= 5
    assert recibo["proximo_acto"]["falsador"].strip()
