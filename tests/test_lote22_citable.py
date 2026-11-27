"""El lote 22 paga el denominador y publica el primer locus externo que sobrevive a la lectura.

El recibo del lote 21 dejo escrito el siguiente acto: leer los loci que el instrumento publica
hasta encontrar uno citable. Este fichero custodia lo que un cambio posterior romperia sin
hacer ruido: que el pre-registro no se reescribio despues de medir, que el instrumento no se
movio entre la prediccion y la corrida, que los tres veredictos reconcilian con las filas que
los sostienen, y que el NO_MEDIDO no se lee como cero.

Nada aqui se afirma por lectura del recibo: cada aserto recalcula desde las filas o desde el
arbol. La aritmetica de P2 se rehace con los numeros del propio recibo, de modo que un recibo
que cambie de datos y no de veredicto falle.

El unico confirmado con ``poblacion == "pierde"`` no se custodia clonando su sujeto (una red y
un sujeto movible por tres lineas) ni metiendo un fichero mas en ``tests/fixtures``, cuyo censo
publica el README: se custodia con una reduccion escrita aqui, que el instrumento debe seguir
clasificando igual y que, ejecutada, debe perder masa.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

from fiber_ast_lint.detect import analizar

RAIZ = Path(__file__).resolve().parents[1]
PRE_REGISTRO = RAIZ / "prediccion-batch-22.json"
CENSO = RAIZ / "censo-22-20261127.json"
RECIBO = RAIZ / "recibo-lote22-20261127.json"
DETECT = RAIZ / "src" / "fiber_ast_lint" / "detect.py"

OSI = {"MIT", "Apache-2.0", "BSD-3-Clause"}
VEREDICTOS = {"CONFIRMADO", "REFUTADO", "NO_MEDIDO"}
CAUSAS_NO_MEDIDO = {"fichero_no_parsea", "invariante_externo_no_declarado"}


def _cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_el_pre_registro_no_se_reescribio_despues_de_medir() -> None:
    recibo = _cargar(RECIBO)
    vivo = _sha(PRE_REGISTRO)
    assert recibo["pre_registro"]["sha256"] == vivo
    assert recibo["pre_registro"]["verificado_en_este_acto"] == vivo
    assert recibo["pre_registro"]["declarado_antes"] is True


def test_el_instrumento_no_se_movio_entre_la_prediccion_y_la_corrida() -> None:
    instrumento = _cargar(RECIBO)["instrumento"]
    vivo = _sha(DETECT)
    assert instrumento["detect_py_sha256_antes"] == vivo
    assert instrumento["detect_py_sha256_despues"] == vivo
    assert instrumento["congelado"] is True


def test_la_cohorte_es_un_denominador_declarado_y_anterior() -> None:
    censo = _cargar(CENSO)
    recibo = _cargar(RECIBO)["cohorte"]
    filas = censo["filas"]
    assert recibo["sha256"] == _sha(CENSO)
    assert len(filas) == censo["total_filas"] == recibo["sujetos"]
    assert {f["spdx"] for f in filas} <= OSI
    assert Counter(f["spdx"] for f in filas) == Counter(recibo["por_spdx"])
    assert all(len(f["sha"]) == 40 and f["sha"] == f["sha"].lower() for f in filas)


def test_los_tres_veredictos_reconcilian_con_las_filas() -> None:
    recibo = _cargar(RECIBO)
    loci = recibo["loci"]
    cuenta = Counter(x["veredicto"] for x in loci)
    assert set(cuenta) == VEREDICTOS
    assert sum(cuenta.values()) == len(loci) == recibo["corrida"]["agregado"]["loci"]
    assert cuenta["CONFIRMADO"] == len(recibo["confirmados"])
    assert cuenta["NO_MEDIDO"] == len(recibo["no_medidos"])
    assert len({(x["sujeto"], x["archivo"], x["linea"]) for x in loci}) == len(loci)


def test_toda_causa_esta_en_el_vocabulario_declarado_antes_de_leer() -> None:
    recibo = _cargar(RECIBO)
    admitidas = {
        causa
        for cuerpo in recibo["lectura"]["vocabulario"].values()
        for causa in ([cuerpo.split(":", 1)[0]] if isinstance(cuerpo, str) else cuerpo)
    }
    causas = {x["causa"] for x in recibo["loci"]}
    assert causas <= set(admitidas)
    assert Counter(x["causa"] for x in recibo["loci"]) == Counter(recibo["lectura"]["por_causa"])


def test_p2_se_refuta_con_la_aritmetica_del_propio_recibo() -> None:
    recibo = _cargar(RECIBO)
    loci = recibo["loci"]
    confirmados = sum(1 for x in loci if x["veredicto"] == "CONFIRMADO")
    no_medidos = sum(1 for x in loci if x["veredicto"] == "NO_MEDIDO")
    umbral = Fraction(1, 6)
    assert Fraction(confirmados, len(loci)) <= umbral
    assert Fraction(confirmados, len(loci) - no_medidos) <= umbral
    p2 = next(v for v in recibo["veredictos"] if v["id"] == "P2")
    assert p2["veredicto"] == "REFUTADA"
    assert f"{confirmados}/{len(loci)}" in p2["evidencia"]


def test_ningun_no_medido_se_lee_como_cero_ni_se_cuenta_como_refutado() -> None:
    recibo = _cargar(RECIBO)
    no_medidos = [x for x in recibo["loci"] if x["veredicto"] == "NO_MEDIDO"]
    assert no_medidos and {x["causa"] for x in no_medidos} <= CAUSAS_NO_MEDIDO
    # El sujeto cuyo instrumento declaro ruptura es el mismo que aporta los ficheros que no
    # parsean: la ceguera del lector y el codigo tipado del instrumento apuntan al mismo sujeto.
    ruptura = {s["repo"] for s in recibo["corrida"]["por_sujeto"] if s["rc"] == 4}
    assert ruptura
    assert {x["sujeto"] for x in no_medidos if x["causa"] == "fichero_no_parsea"} == ruptura
    assert all(s["fallas"] > 0 for s in recibo["corrida"]["por_sujeto"] if s["rc"] == 4)


def test_el_locus_citable_esta_dentro_de_la_superficie_publicada() -> None:
    recibo = _cargar(RECIBO)
    filas = {(x["sujeto"], x["archivo"], x["linea"]): x for x in recibo["loci"]}
    citable = [c for c in recibo["confirmados"] if c["poblacion"] == "pierde"]
    assert len(citable) == 1
    fila = filas[(citable[0]["sujeto"], citable[0]["archivo"], citable[0]["linea"])]
    assert fila["veredicto"] == "CONFIRMADO"
    assert fila["licencia"] in OSI


ANCLA = '''"""Seis claves dentro, tres identificadores fuera: el saneador es la proyeccion.

La forma esta tomada del unico locus del lote 22 que sobrevivio a la lectura con
``poblacion == "pierde"``: ``tempus2016/z2m-device-tracker@c5f13b8d``,
``custom_components/z2m_tracker/const.py:66`` (MIT). Reducida a una funcion pura para que el
positivo se pueda afirmar sin clonar al sujeto.

``key.lower()`` y ``re.sub(r"[^a-z0-9_]+", "_", ...)`` funden ``Sensor.Battery``,
``sensor_battery`` y ``sensor battery`` en un mismo id de reparacion, y el guardia pregunta al
*dominio* (``key not in keys``), que no puede suprimir un nucleo: toda imagen de una colision
sigue estando en ``keys``.
"""
import re

KEYS = [
    "Sensor.Battery",
    "sensor_battery",
    "sensor battery",
    "Link.Quality",
    "link quality",
    "Battery",
]

# Una lista blanca de ids de reparacion: contiene la imagen de las dos fibras no triviales.
REPAIRS = {"sensor_battery", "link_quality", "battery"}


def reparaciones_pedidas(keys):
    wanted = {}
    for key in sorted(keys):
        if key not in keys:
            continue
        wanted["issue_" + re.sub(r"[^a-z0-9_]+", "_", key.lower())] = key
    return wanted


def tarjeta_de_reparaciones(keys):
    """Un llamante, para que el acumulador escape *y* alguien llame a la funcion."""
    return reparaciones_pedidas(keys)
'''


def test_el_locus_citable_tiene_ancla_en_el_arbol(tmp_path) -> None:
    """El positivo que sobrevivio a la lectura conserva un control que no depende del sujeto.

    La forma que el instrumento debe seguir emitiendo no se escribe en el test: se lee de la
    fila que el recibo confirmo. Asi un cambio de particion que borre este positivo falla aqui
    y no en la siguiente cohorte, y el dia que la fila cambie el test nombra cual de las dos se
    movio.
    """
    citable = [c for c in _cargar(RECIBO)["confirmados"] if c["poblacion"] == "pierde"][0]
    ruta = tmp_path / "reparacion_por_regex.py"
    ruta.write_text(ANCLA, encoding="utf-8")
    a = analizar(tmp_path)
    assert a.certifica()
    # Un testigo dibujado sobre el dominio no cuenta como cubeta: ``key not in keys`` contiene
    # la imagen de toda colision y por eso no suprime ninguna.
    assert a.guardadas == 0
    assert len(a.candidatos) == 1
    loc = a.candidatos[0]
    assert (loc.familia, loc.forma, loc.severidad) == (
        citable["familia"],
        citable["forma"],
        citable["severidad"],
    )
    assert loc.op == "pierde"
    assert loc.escapa is True and loc.llamadas >= 1
    # La perdida es del sujeto y no del clasificador: ejecutada, la funcion pierde masa.
    spec = importlib.util.spec_from_file_location("ancla_reparacion", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    assert len(modulo.reparaciones_pedidas(modulo.KEYS)) < len(modulo.KEYS)


def test_todo_confirmado_tiene_fila_y_licencia() -> None:
    recibo = _cargar(RECIBO)
    filas = {(x["sujeto"], x["archivo"], x["linea"]): x for x in recibo["loci"]}
    for confirmado in recibo["confirmados"]:
        clave = (confirmado["sujeto"], confirmado["archivo"], confirmado["linea"])
        assert clave in filas, clave
        assert filas[clave]["veredicto"] == "CONFIRMADO"
        assert filas[clave]["licencia"] in OSI


def test_ninguna_fila_se_publica_sin_la_linea_que_se_adjudico() -> None:
    """La frase de `lectura.reproducibilidad` dice donde vive la linea; aqui se cuenta.

    Una fila sin la linea adjudicada no se puede volver a leer, y el recibo afirma que las 125
    se pueden. Las refutadas y las no medidas la llevan en `texto`; las confirmadas la llevan
    abriendo `evidencia`, cuyo resto es la razon. Nadie lleva las dos y nadie lleva ninguna.
    """
    loci = _cargar(RECIBO)["loci"]
    con_linea = [x for x in loci if x.get("texto")]
    con_evidencia = [x for x in loci if x.get("evidencia")]
    assert not [x for x in loci if not x.get("texto") and not x.get("evidencia")]
    assert not [x for x in loci if x.get("texto") and x.get("evidencia")]
    assert {x["veredicto"] for x in con_linea} == {"REFUTADO", "NO_MEDIDO"}
    assert {x["veredicto"] for x in con_evidencia} == {"CONFIRMADO"}


def test_el_agregado_reconcilia_y_no_deja_sumando_huerfano() -> None:
    agregado = _cargar(RECIBO)["corrida"]["agregado"]
    partes = ["pierde", "guardadas", "acumulacion", "posicional", "sin_len"]
    assert agregado["almacenes"] == sum(agregado[k] for k in partes)
    assert _cargar(RECIBO)["corrida"]["reconciliacion"] is True
    assert agregado["filas"] == agregado["loci"]
