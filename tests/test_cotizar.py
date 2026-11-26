"""A quote has three parts and only one of them is a number.

Batch 4 established that counts reproduce between sessions and clocks do not. The
instrument in ``bench/cotizar.py`` turns that into an artifact with three separate
compartments -- counts, subject digest, own clock -- plus a price that is
``NO_COTIZADO`` unless someone signed coefficients. These tests hold the
compartments apart offline: no wheel is fetched, so nothing here checks a
measurement, only that the instrument refuses the substitutions that would make a
measurement look like something it is not.

The one substitution worth naming: the CPU model was fitted on *artifact* bytes.
Handing it a disk tree and returning a number is the ``attrs`` defect of batch 4 --
two subjects under one key -- so ``_banda`` answers ``NO_MEDIDO`` and says what is
missing instead.
"""
import json
import math
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "bench"))

import cotizar  # noqa: E402
import replay_censo  # noqa: E402

UNIDADES = {"sitios": 3, "claves": 5, "ficheros": 7}


def _arbol(base: Path, cuerpo: str) -> Path:
    (base / "pkg").mkdir(parents=True)
    (base / "pkg" / "__init__.py").write_text(cuerpo, encoding="utf-8")
    return base


def _tarifa(**extra) -> dict:
    return {"firmada": True, "moneda": "MXN",
            "coeficientes": {"sitios": 1500, "claves": 800, "ficheros": 0}, **extra}


def test_la_cotizacion_y_el_replay_comparten_la_definicion_de_fila():
    # Una fila cotizada y una fila replicada no pueden divergir: es la misma funcion,
    # no una copia parecida.
    assert cotizar._medir is replay_censo._medir


def test_dos_arboles_del_mismo_tamano_no_comparten_manifiesto(tmp_path):
    a = _arbol(tmp_path / "a", "x = 1\n")
    b = _arbol(tmp_path / "b", "y = 2\n")
    ha, ba, fa = cotizar._manifiesto(a)
    hb, bb, fb = cotizar._manifiesto(b)
    assert (ba, fa) == (bb, fb)
    assert ha != hb
    assert cotizar._manifiesto(a) == (ha, ba, fa)


def test_los_conteos_que_se_mueven_no_son_una_repeticion(monkeypatch, tmp_path):
    arbol = _arbol(tmp_path / "t", "x = 1\n")
    real = cotizar._medir
    llamadas = {"n": 0}

    def falso(raiz):
        llamadas["n"] += 1
        celda = dict(real(raiz))
        if llamadas["n"] > 1:
            celda["files"] = celda["files"] + 1
        return celda

    monkeypatch.setattr(cotizar, "_medir", falso)
    with pytest.raises(RuntimeError):
        cotizar._tiempo(arbol, 2)


def test_sin_tarifa_no_hay_precio():
    ejemplo = json.loads((RAIZ / "tarifa.ejemplo.json").read_text(encoding="utf-8"))
    for tarifa in (None, ejemplo, _tarifa(firmada=False), _tarifa(firmada="true")):
        d = cotizar._precio(tarifa, UNIDADES)
        assert d["estado"] == "NO_COTIZADO", tarifa
        assert "total" not in d
        assert d["unidades_facturables"] == UNIDADES


def test_una_tarifa_incompleta_no_cotiza():
    d = cotizar._precio({"firmada": True, "coeficientes": {"sitios": 10}}, UNIDADES)
    assert d["estado"] == "NO_COTIZADO"
    assert "claves" in d["motivo"] and "ficheros" in d["motivo"]


def test_la_aritmetica_es_suma_exacta_sin_redondeo():
    # Coeficientes y conteos impares, cocientes no enteros: el total tiene que ser
    # la suma de los subtotales tal cual, no un entero redondeado.
    tarifa = {"firmada": True, "moneda": "MXN",
              "coeficientes": {"sitios": 333, "claves": 7, "ficheros": 1}}
    d = cotizar._precio(tarifa, UNIDADES)
    assert d["estado"] == "COTIZADO"
    assert [x["subtotal"] for x in d["detalle"]] == [999, 35, 7]
    assert d["total"] == sum(x["subtotal"] for x in d["detalle"]) == 1041
    assert d["total"] == sum(UNIDADES[u] * tarifa["coeficientes"][u] for u in UNIDADES)


def test_la_banda_no_puntua_un_sujeto_que_el_modelo_no_vio():
    cal = json.loads((RAIZ / "fuera-de-dominio-4.json").read_text(encoding="utf-8"))
    sin = cotizar._banda(cal, None)
    assert sin["estado"] == "NO_MEDIDO"
    assert sin["que_falta"] and "bytes de codigo escaneado" in sin["que_falta"]
    # Las dos mitades de la banda son la misma medicion: el sujeto que falta no
    # borra la calibracion ya hecha.
    assert sin["calibracion"]["filas"] == 15
    con = cotizar._banda(cal, 100_000)
    assert con["estado"] == "MEDIDO"
    assert con["bytes_artefacto"] == 100_000
    assert con["calibracion"] == sin["calibracion"]
    assert con["modelo"] == sin["modelo"]


def test_el_cuantil_de_la_banda_cae_antes_del_maximo():
    cal = json.loads((RAIZ / "fuera-de-dominio-4.json").read_text(encoding="utf-8"))
    conocidos = cal["rows"][:15]
    residuos = []
    for i, r in enumerate(conocidos):
        a, b = cotizar._modelo([x for j, x in enumerate(conocidos) if j != i])
        p = a + b * r["bytes"]
        residuos.append(abs(r["cpu_min"] - p) / p)
    residuos.sort()
    indice = math.ceil((len(residuos) + 1) * (1 - cotizar.ALFA)) - 1
    banda = cotizar._banda(cal, 1)
    assert banda["calibracion"]["cuantil_indice"] == indice == 12
    assert banda["calibracion"]["q"] == round(residuos[indice], 4)
    assert banda["calibracion"]["max_residuo"] == round(residuos[-1], 4)
    # La banda es mas estrecha que el peor sujeto: el cuantil no es un maximo.
    assert banda["calibracion"]["q"] < banda["calibracion"]["max_residuo"]
    predicho = banda["predicho_s"]
    q = banda["semicerco_relativo"]
    assert banda["intervalo_s"] == [round(predicho * (1 - q), 4), round(predicho * (1 + q), 4)]


def test_el_rc_lo_fija_el_precio_y_no_el_escaneo(tmp_path):
    arbol = _arbol(tmp_path / "t", "x = 1\n")
    sin = cotizar.cotizar(arbol, None, None, 1)
    assert sin["precio"]["estado"] == "NO_COTIZADO"
    assert cotizar._rc(sin) == replay_censo.NO_MEDIDO


def test_la_cli_devuelve_el_rc_del_precio(tmp_path):
    salida = tmp_path / "cotizacion.json"
    rc = cotizar.main(["--arbol", str(RAIZ / "src" / "fiber_ast_lint"),
                       "--calibracion", str(RAIZ / "fuera-de-dominio-4.json"),
                       "--out", str(salida), "--repeticiones", "1"])
    assert rc == replay_censo.NO_MEDIDO
    doc = json.loads(salida.read_text(encoding="utf-8"))
    assert doc["schema"] == cotizar.ESQUEMA
    assert doc["precio"]["estado"] == "NO_COTIZADO"
    assert doc["tiempo"]["estado"] == "NO_MEDIDO"
    assert doc["sujeto"]["ficheros"] == doc["conteos"]["files"]
    assert doc["sujeto"]["manifiesto_sha256"] == cotizar._manifiesto(RAIZ / "src" / "fiber_ast_lint")[0]
