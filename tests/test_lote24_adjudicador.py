"""El adjudicador decide o se abstiene: nunca adivina.

La ley que estos casos fijan es asimetrica a proposito. Una abstencion cuesta
cobertura y no cuesta precision, asi que el error que se persigue aqui es el
falso teorema --una fila que el modulo decide y cuya causa el lector humano
nombro de otra manera-- y no la fila que deja de decidir.
"""
from __future__ import annotations

import ast

import pytest

from fiber_ast_lint.adjudicador_ast import (
    CAUSAS_DECIDIBLES,
    NO_PARSEA,
    POSICIONAL,
    SIN_CAUSA,
    adjudicar,
    causa_de_escritura,
    causa_por_localidad,
    nodo_de_escritura,
)

# El unico locus de la cohorte del lote 22 con familia REBANADA y causa distinta
# de escritura_posicional. Tiene rebanada y por tanto se parece a los otros 25,
# pero la rebanada va envuelta en una condicional sobre una llamada: el indice
# ya no es una direccion, es un calculo, y el teorema no lo cubre.
CASO_FRONTERA = (
    "def juntar(entidades, clave, sufijo, salida):\n"
    "    for entidad in entidades:\n"
    "        salida[clave[: -len(sufijo)] if clave.endswith(sufijo) else clave] = entidad\n"
)


def _arbol(fuente: str) -> ast.Module:
    return ast.parse(fuente)


def _primera_escritura(fuente: str, linea: int | None = None) -> ast.AST | None:
    arbol = _arbol(fuente)
    if linea is not None:
        return nodo_de_escritura(arbol, linea)
    for x in ast.walk(arbol):
        if isinstance(x, (ast.Assign, ast.AnnAssign)):
            return x
    return None


def test_t1_la_rebanada_no_tiene_clave() -> None:
    nodo = _primera_escritura("def f(a, v):\n    a[y0:y1] = v\n")
    assert causa_de_escritura(nodo) == POSICIONAL


def test_t1_la_mascara_por_columnas_tampoco() -> None:
    nodo = _primera_escritura("def f(a, v, i):\n    a[:, i] = v\n")
    assert causa_de_escritura(nodo) == POSICIONAL


def test_t1_un_indice_escalar_es_una_clave_y_no_se_decide() -> None:
    nodo = _primera_escritura("def f(a, v, k):\n    a[k] = v\n")
    assert causa_de_escritura(nodo) == SIN_CAUSA


def test_t1_una_llamada_dentro_del_indice_abre_el_predicado() -> None:
    nodo = _primera_escritura("def f(a, v, k):\n    a[k.strip().lower()] = v\n")
    assert causa_de_escritura(nodo) == SIN_CAUSA


def test_t1_el_caso_frontera_de_la_cohorte_no_se_decide() -> None:
    """Rebanada presente, pero envuelta en condicional: no es direccion."""
    nodo = _primera_escritura(CASO_FRONTERA, 3)
    assert nodo is not None
    assert causa_de_escritura(nodo) == SIN_CAUSA


def test_t1_un_solo_objetivo_indexado_por_clave_reabre_el_predicado() -> None:
    nodo = _primera_escritura("def f(a, b, k, v):\n    a[0:1] = b[k] = v\n")
    assert causa_de_escritura(nodo) == SIN_CAUSA


def test_t2_fichero_que_no_parsea() -> None:
    assert causa_por_localidad("def f(:\n") == NO_PARSEA
    assert causa_por_localidad(b"x = 1\x00\n") == NO_PARSEA


def test_t2_fichero_que_parsea_no_es_causa() -> None:
    assert causa_por_localidad("x = 1\n") == SIN_CAUSA


def test_nodo_de_escritura_ambiguo_se_abstiene() -> None:
    """Dos escrituras indexadas en la misma linea: la coordenada no identifica."""
    fuente = "def f(a, b, v):\n    a[1:2] = v; b[v] = 1\n"
    assert nodo_de_escritura(_arbol(fuente), 2) is None


def test_adjudicar_solo_emite_causas_de_la_lista_cerrada() -> None:
    nodo = _primera_escritura(CASO_FRONTERA, 3)
    for salida in (
        adjudicar(nodo),
        adjudicar(nodo, CASO_FRONTERA),
        adjudicar(None, "no parsea ("),
        adjudicar(None, None),
    ):
        assert salida == SIN_CAUSA or salida in CAUSAS_DECIDIBLES


def test_adjudicar_prefiere_el_teorema_de_la_escritura_a_la_localidad() -> None:
    """Si la escritura se localiza, el fichero que parsea no cambia la respuesta."""
    fuente = "def f(a, v):\n    a[1:] = v\n"
    nodo = _primera_escritura(fuente, 2)
    assert adjudicar(nodo, fuente) == POSICIONAL


@pytest.mark.parametrize("indice", ["a[:]", "a[1:]", "a[: -1]", "a[x:]"])
def test_t1_la_rebanada_pura_se_decide(indice: str) -> None:
    nodo = _primera_escritura(f"def f(a, v, x):\n    {indice} = v\n")
    assert causa_de_escritura(nodo) == POSICIONAL


# --- el recibo: lo que se afirma se recalcula, no se lee --------------------

import hashlib  # noqa: E402
import json  # noqa: E402
from fractions import Fraction  # noqa: E402
from pathlib import Path  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
PRE_REGISTRO = RAIZ / "prediccion-batch-24.json"
RECIBO = RAIZ / "recibo-lote24-20261127.json"
ADJUDICADOR = RAIZ / "src" / "fiber_ast_lint" / "adjudicador_ast.py"
DETECTOR = RAIZ / "src" / "fiber_ast_lint" / "detect.py"
ECO = "proyeccion_no_inyectiva_sin_medicion"
COMPUERTA = ("COLUMNA", "REBANADA")


def _cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _filas() -> list[dict]:
    return _cargar(RECIBO)["tabla_adjudicacion"]


def _adjudicadas() -> list[dict]:
    return [f for f in _filas() if f["veredicto"] != "NO_MEDIDO"]


def _decididas() -> list[dict]:
    return [f for f in _adjudicadas() if f["predicha"] != SIN_CAUSA]


def test_el_pre_registro_se_sello_antes_de_medir() -> None:
    pre = _cargar(PRE_REGISTRO)
    assert pre["declared_before_computation"] is True
    assert _cargar(RECIBO)["pre_registro"]["sha256"] == _sha(PRE_REGISTRO)


def test_el_detector_no_se_movio() -> None:
    inst = _cargar(RECIBO)["instrumento"]
    assert _sha(DETECTOR) == inst["detector"]["sha256"]
    assert inst["detector"]["sha256"] == (
        "b03f3ac31a1f843c453a38bb834156328f0f1a073e6fe39b12ad2e75db8bb6d6"
    )
    assert inst["detector"]["intacto"] is True
    assert inst["detector"]["modificado"] is False


def test_el_adjudicador_sigue_siendo_el_que_se_sello() -> None:
    """Si alguien edita el modulo, el recibo deja de describirlo."""
    sellado = _cargar(PRE_REGISTRO)["instrumento_antes"]["adjudicador_sha256"]
    assert _sha(ADJUDICADOR) == sellado
    assert _cargar(RECIBO)["instrumento"]["adjudicador"]["sha256"] == sellado


def test_las_decisiones_llevan_la_causa_publicada() -> None:
    decididas = _decididas()
    assert decididas
    assert all(f["predicha"] == f["publicada"] for f in decididas)


def test_la_cobertura_cae_dentro_de_la_banda_sellada() -> None:
    # La banda [22, 27] esta sellada en el enunciado de P2 y se deriva de la
    # tabla del lote 22: 25 filas con causa escritura_posicional, todas REBANADA.
    assert 22 <= len(_decididas()) <= 27


def test_la_capa_teorema_no_toca_ningun_confirmado() -> None:
    """El teorema solo decide del lado negativo: no sube la precision del producto."""
    decididas = _decididas()
    assert not [f for f in decididas if f["veredicto"] == "CONFIRMADO"]
    med = _cargar(RECIBO)["medicion"]["efecto_sobre_la_precision_del_producto"]
    confirmados = sum(1 for f in _adjudicadas() if f["veredicto"] == "CONFIRMADO")
    assert med["antes"]["confirmados"] == med["despues"]["confirmados"] == confirmados
    assert med["despues"]["filas"] == len(_adjudicadas()) - len(decididas)
    assert med["despues"]["precision"] == round(confirmados / med["despues"]["filas"], 4)


def test_las_cifras_del_recibo_se_recalculan() -> None:
    med = _cargar(RECIBO)["medicion"]
    adjudicadas = _adjudicadas()
    decididas = _decididas()
    eco = [f for f in adjudicadas if f["predicha"] != SIN_CAUSA or f["publicada"] == ECO]
    assert med["filas"] == len(_filas())
    assert med["adjudicados"] == len(adjudicadas)
    assert med["decididas"] == len(decididas)
    assert med["aciertos"] == sum(1 for f in decididas if f["predicha"] == f["publicada"])
    assert med["precision_capa_teorema"] == round(
        float(Fraction(med["aciertos"], len(decididas))), 4)
    assert med["acuerdo_estricto"] == round(
        float(Fraction(len(decididas), len(adjudicadas))), 4)
    assert med["acuerdo_con_capa_eco"]["numerador"] == len(eco)
    assert med["acuerdo_con_capa_eco"]["valor"] == round(
        float(Fraction(len(eco), len(adjudicadas))), 4)


def test_la_compuerta_del_lote_23_se_cruza_sin_leer_el_veredicto() -> None:
    cruce = _cargar(RECIBO)["cruce_con_la_compuerta_del_lote_23"]
    gate = [f for f in _adjudicadas() if f["familia"] in COMPUERTA]
    sostenidas = [f for f in gate if f["predicha"] == POSICIONAL]
    assert cruce["filas_suprimidas"] == len(gate)
    assert cruce["sostenidas_por_el_teorema"] == len(sostenidas)
    assert cruce["no_sostenidas"] == len(gate) - len(sostenidas)
    assert cruce["confirmados_suprimidos"] == 0
    assert cruce["no_sostenidas"] >= 45


def test_el_borde_es_una_sola_fila_y_explica_toda_desviacion() -> None:
    """La unica causa publicada `escritura_posicional` que el modulo no decide."""
    borde = _cargar(RECIBO)["borde_no_decidido"]
    sobrantes = [f for f in _adjudicadas()
                 if f["publicada"] == POSICIONAL and f["predicha"] == SIN_CAUSA]
    assert len(sobrantes) == 1
    fila = sobrantes[0]
    assert (fila["sujeto"], fila["archivo"], fila["linea"]) == (
        borde["sujeto"], borde["archivo"], borde["linea"])
    # y la razon estructural: la rebanada esta, pero su cota lleva una llamada.
    arbol = ast.parse(f"def f(wavs, i, row):\n    {borde['texto']}\n")
    nodo = _primera_escritura(f"def f(wavs, i, row):\n    {borde['texto']}\n", 2)
    assert nodo is not None
    indices = [n.slice for n in ast.walk(nodo) if isinstance(n, ast.Subscript)]  # type: ignore[attr-defined]
    hojas = [x for i in indices for x in ast.walk(i)]
    assert any(isinstance(x, ast.Slice) for x in hojas)
    assert any(isinstance(x, ast.Call) for x in hojas)


def test_los_veredictos_del_recibo_son_los_cinco_sellados() -> None:
    pre = _cargar(PRE_REGISTRO)
    veredictos = _cargar(RECIBO)["veredictos"]
    assert [v["id"] for v in veredictos] == [p["id"] for p in pre["predictions"]]
    assert {v["veredicto"] for v in veredictos} <= {"CUMPLIDA", "REFUTADA", "NO_MEDIDO"}


def test_los_cocientes_del_sello_declaran_su_denominador() -> None:
    """El guardian del esquema se cumple aqui tambien, y su cumplimiento se declara."""
    sello = _cargar(RECIBO)["sello"]
    assert sello["completado_despues_de_medir"] is True
    assert sello["sha256_vigente"] == _sha(PRE_REGISTRO)
    for p in _cargar(PRE_REGISTRO)["predictions"]:
        if p["id"] in ("P2", "P3", "P4"):
            assert "/" in p["ratio_orientation"]


def test_el_comando_que_el_recibo_cita_existe_y_congela_el_detector() -> None:
    """Una corrida que solo se puede repetir desde /tmp no es una medicion."""
    comando = _cargar(RECIBO)["corrida"]["comando"]
    citado = next(t for t in comando.split() if t.startswith("bench/"))
    corredor = RAIZ / citado
    assert corredor.is_file()
    fuente = corredor.read_text(encoding="utf-8")
    assert _sha(DETECTOR) in fuente


def test_las_dos_corridas_difieren_solo_en_lo_que_no_es_del_sujeto() -> None:
    """T2 mide el piso del parser, no un estado del sujeto: la cuenta se declara."""
    bloque = _cargar(RECIBO)["corrida_por_interprete"]
    corridas = {c["interprete"]: c for c in bloque["corridas"]}
    assert all(c["filas"] == len(_filas()) for c in corridas.values())
    diferencia = corridas["3.9.6"]["decididas"] - corridas["3.12"]["decididas"]
    assert diferencia == bloque["filas_que_cambian_de_dictamen"]
    # las que se mueven son exactamente las de causa T2, y ninguna de ellas esta entre los 117
    t2 = [f for f in _filas() if f["publicada"] == bloque["causa_de_las_5"]]
    assert len(t2) == diferencia
    assert all(f["veredicto"] == "NO_MEDIDO" for f in t2)
    adjudicadas = [f for f in _filas() if f["veredicto"] != "NO_MEDIDO"]
    assert len(adjudicadas) == 117
    assert all(f["predicha"] != bloque["causa_de_las_5"] for f in adjudicadas)
    assert _cargar(RECIBO)["corrida"]["interprete"] in corridas
