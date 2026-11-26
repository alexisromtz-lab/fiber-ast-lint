"""El recibo con banda: lo que el booleano calla.

Los tests de este archivo atacan dos cosas distintas. Primero, la aritmetica del recibo,
sobre entradas sinteticas: la zona, el margen, la dispersion de una sesion con un solo
acto, la cotizacion del arnes. Segundo, el recibo sellado del lote 10: cada cifra que
publica tiene que salir de un acto del artefacto, y la huella tiene que recomputarse igual
desde una copia sin el escaner.

Ninguna cifra se copia: se deriva del artefacto y se compara con el recibo. Un test que
escribe la constante que deberia derivar no prueba nada.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "bench"))

import recibo as r11  # noqa: E402

ARTE = RAIZ / "fuera-de-dominio-10.json"
SELLADO = RAIZ / "recibo-banda-11.json"
PRED = RAIZ / "prediccion-batch-11.json"


def _arte() -> dict:
    return json.loads(ARTE.read_text())


def _sellado() -> dict:
    return json.loads(SELLADO.read_text())


def _acto(nombre: str) -> dict:
    return next(a for a in _arte()["actos"] if a["nombre"] == nombre)


# --- aritmetica de la banda -------------------------------------------------


def test_la_banda_parte_el_eje_en_tres_zonas_y_su_frontera_es_el_umbral():
    assert r11._zona(0.10, 0.30) == "margen_sano"
    assert r11._zona(0.15, 0.30) == "margen_sano"  # k == q/2 aun no es riesgo
    assert r11._zona(0.20, 0.30) == "banda_de_riesgo"
    assert r11._zona(0.30, 0.30) == "banda_de_riesgo"  # k == q no lo excede
    assert r11._zona(0.31, 0.30) == "fuera_de_cota"


def test_el_margen_es_la_distancia_a_la_frontera_y_no_el_lado_en_que_se_cae():
    dentro = r11._banda(0.20, 0.3018)
    fuera = r11._banda(0.40, 0.3018)
    assert dentro["margen"] == round(0.3018 - 0.20, 4)
    assert fuera["margen"] < 0
    assert dentro["margen_relativo"] == round(dentro["margen"] / 0.3018, 4)
    assert dentro["mitad_umbral"] == round(0.3018 / 2, 4)


def test_una_sesion_de_un_solo_acto_no_tiene_dispersion_y_lo_declara():
    disp = r11._dispersiones([
        {"nombre": "A", "fuente": "fuera-de-dominio-8.json (sellado del lote 7)", "jitter_relativo": 0.6054},
        {"nombre": "B", "fuente": "fuera-de-dominio-8.json (acto propio del lote 8)", "jitter_relativo": 0.2498},
    ])
    assert disp[7]["n"] == 1 and disp[7]["dispersion"] is None
    assert disp[8]["n"] == 1 and disp[8]["dispersion"] is None


def test_la_dispersion_dentro_de_una_sesion_es_cociente_de_extremos():
    disp = r11._dispersiones([
        {"nombre": "C", "fuente": "fuera-de-dominio-9.json (acto propio del lote 9)", "jitter_relativo": 0.1280},
        {"nombre": "D", "fuente": "fuera-de-dominio-9.json (acto propio del lote 9)", "jitter_relativo": 0.1155},
    ])
    assert disp[9]["n"] == 2
    assert disp[9]["dispersion"] == round(0.1280 / 0.1155, 4)


def test_la_sesion_sale_de_la_fuente_y_no_del_orden_de_la_lista():
    actos = [dict(_acto(n)) for n in ("H", "A", "F", "B")]
    disp = r11._dispersiones(actos)
    por_nombre = {a["nombre"]: r11._sesion(a["fuente"]) for a in actos}
    assert por_nombre == {"A": 7, "B": 8, "F": 10, "H": 10}
    assert disp[10]["n"] == 2


def test_la_cotizacion_paga_el_arnes_en_cada_uso_y_publica_la_cota_sin_el():
    acto = {"coste_compuerta_s": 200.0, "coste_arnes_s": 150.0, "mediana_s": 0.5}
    c = r11._cotizacion(acto)
    assert c["sonda_s"] == round(9 * 0.5, 4)
    assert c["coste_uso_s"] == round(150.0 + 9 * 0.5, 4)
    # pagar el arnes hace cada uso mas caro, y por tanto amortiza el acto en menos usos
    assert c["usos_para_amortizar"] < c["usos_sin_arnes"] == 45


def test_un_acto_sin_coste_declarado_no_se_cotiza_y_no_se_rellena_con_cero():
    assert r11._cotizacion({"mediana_s": 0.5}) is None
    assert r11._cotizacion({"coste_compuerta_s": 1.0, "mediana_s": 0.5}) is None


# --- el recibo sellado ------------------------------------------------------


def test_la_huella_no_depende_de_lo_que_costo_emitir_el_recibo():
    base = r11.recibo(_arte(), str(ARTE))
    otro = dict(base, medicion_de_si_mismo={"coste_verificacion_s": 99.0})
    assert r11.huella(base) == r11.huella(otro) == base["huella"]


def test_cada_cifra_del_recibo_sale_de_un_acto_del_artefacto():
    arte, rec = _arte(), _sellado()
    por_nombre = {a["nombre"]: a for a in arte["actos"]}
    for fila in rec["actos"]:
        a = por_nombre[fila["nombre"]]
        assert fila["k"] == a["jitter_relativo"]
        assert fila["umbral"] == a["q"]
        assert fila["margen"] == round(a["q"] - a["jitter_relativo"], 4)
        assert fila["zona"] == r11._zona(a["jitter_relativo"], a["q"])
        assert fila["publicable_como_booleano"] is a["publicable"]
        assert fila["coste_compuerta_s"] == a.get("coste_compuerta_s")


def test_el_booleano_y_la_banda_discrepan_donde_el_margen_ya_se_gasto():
    rec = _sellado()
    discrepan = [
        f["nombre"] for f in rec["actos"]
        if f["publicable_como_booleano"] and f["zona"] != "margen_sano"
    ]
    assert discrepan == rec["resumen"]["en_banda_de_riesgo"]
    assert len(discrepan) >= 1


def test_los_veredictos_se_derivan_de_las_zonas_y_no_se_escriben():
    rec = _sellado()
    pub = rec["resumen"]["publicables_como_booleano"]
    riesgo = rec["resumen"]["en_banda_de_riesgo_n"]
    p1 = next(v for v in rec["veredictos"] if v["id"] == "P1")
    assert p1["sobrevive"] is (1 <= riesgo and riesgo * 2 <= pub)
    cotizados = [f for f in rec["actos"] if f["cotizacion"]]
    caro = max(cotizados, key=lambda f: f["coste_compuerta_s"])
    p4 = next(v for v in rec["veredictos"] if v["id"] == "P4")
    assert p4["medido"]["acto_mas_caro"] == caro["nombre"]
    assert p4["sobrevive"] is (20 <= caro["cotizacion"]["usos_para_amortizar"] <= 40)


def test_el_recibo_sellado_es_lo_que_recomputa_el_artefacto():
    rec = r11._reanclar_veredictos(
        r11.recibo(_arte(), str(ARTE)),
        r11._leer_prediccion(PRED),
    )
    sellado = _sellado()
    assert rec["huella"] == sellado["huella"]
    assert sellado["huella"] == r11.huella(sellado)


def test_el_pre_registro_del_lote_11_conserva_sus_cuatro_predicciones():
    pred = json.loads(PRED.read_text())
    assert [p["id"] for p in pred["predictions"]] == ["P1", "P2", "P3", "P4"]
    assert pred["declared_before_computation"] is True
    assert all("falsador" in p or ("falsador_bajo" in p and "falsador_alto" in p)
               for p in pred["predictions"])


def test_verificar_el_recibo_cuesta_menos_de_una_centesima_parte_de_medir_la_compuerta():
    t0 = time.perf_counter()
    rec = r11._reanclar_veredictos(r11.recibo(_arte(), str(ARTE)), r11._leer_prediccion(PRED))
    coste = time.perf_counter() - t0
    total = sum(a.get("coste_compuerta_s") or 0.0 for a in _arte()["actos"])
    assert total > 400.0
    assert coste / total <= 0.01, f"verificar costo {coste:.4f} s contra {total:.1f} s medidos"
    assert rec["huella"] == _sellado()["huella"]


def test_el_recibo_se_verifica_sin_el_escaner(tmp_path: Path):
    """El claim comercial: un tercero con cuatro archivos recomputa el veredicto."""
    (tmp_path / "bench").mkdir()
    for f in ("bench/recibo.py", "fuera-de-dominio-10.json", "recibo-banda-11.json",
              "prediccion-batch-11.json"):
        (tmp_path / f).write_bytes((RAIZ / f).read_bytes())
    assert not (tmp_path / "src").exists()
    r = subprocess.run(
        [sys.executable, str(tmp_path / "bench" / "recibo.py"),
         "--artefacto", str(tmp_path / "fuera-de-dominio-10.json"),
         "--check", str(tmp_path / "recibo-banda-11.json"),
         "--prediccion", str(tmp_path / "prediccion-batch-11.json")],
        capture_output=True, text=True, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0, r.stderr
    assert _sellado()["huella"] in r.stdout


def test_un_recibo_manipulado_no_verifica(tmp_path: Path):
    (tmp_path / "bench").mkdir()
    (tmp_path / "bench" / "recibo.py").write_bytes((RAIZ / "bench" / "recibo.py").read_bytes())
    (tmp_path / "fuera-de-dominio-10.json").write_bytes(ARTE.read_bytes())
    manipulado = dict(_sellado())
    manipulado["actos"][0]["k"] = round(manipulado["actos"][0]["k"] - 0.01, 4)
    (tmp_path / "r.json").write_text(json.dumps(manipulado))
    r = subprocess.run(
        [sys.executable, str(tmp_path / "bench" / "recibo.py"),
         "--artefacto", str(tmp_path / "fuera-de-dominio-10.json"), "--check", str(tmp_path / "r.json")],
        capture_output=True, text=True, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 4
    assert "HUELLA DISTINTA" in r.stderr


def test_un_artefacto_ilegible_devuelve_rc_2(tmp_path: Path):
    (tmp_path / "malo.json").write_text("{no es json")
    assert r11.main(["--artefacto", str(tmp_path / "malo.json"), "--salida", str(tmp_path / "x.json")]) == 2


@pytest.mark.skipif(not (RAIZ / ".git").exists(), reason="sin historia git no hay archivo que exportar")
def test_el_recibo_sellado_viaja_en_el_arbol_y_no_solo_en_el_disco():
    r = subprocess.run(["git", "cat-file", "-e", "HEAD:recibo-banda-11.json"], cwd=RAIZ)
    if r.returncode != 0:
        pytest.skip("el recibo aun no esta en HEAD: corre en el acto de aterrizaje")
    blob = subprocess.run(["git", "rev-parse", "HEAD:recibo-banda-11.json"],
                          cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    assert blob == hashlib.sha1(
        b"blob " + str(SELLADO.stat().st_size).encode() + b"\0" + SELLADO.read_bytes()
    ).hexdigest()


JQ = Path("/usr/bin/jq")


@pytest.mark.skipif(not JQ.exists(), reason="sin jq no hay segunda implementacion del sello")
def test_la_huella_se_reproduce_con_jq_y_shasum_sin_python():
    """El claim comercial: el sello no depende de que exista nuestro interprete."""
    canon = subprocess.run(
        [str(JQ), "-S", "-c", "del(.huella, .medicion_de_si_mismo)", str(SELLADO)],
        capture_output=True, text=True, check=True,
    ).stdout.rstrip("\n")
    assert hashlib.sha256(canon.encode()).hexdigest() == _sellado()["huella"]


# --- la prosa ---------------------------------------------------------------


def _seccion_11() -> str:
    texto = (RAIZ / "README.md").read_text()
    ini = texto.index("### The boolean lied at the frontier")
    fin = texto.index("## Fixtures census", ini)
    return texto[ini:fin]


def _prosa_11() -> str:
    return " ".join(_seccion_11().split())


def _tabla_11() -> dict[str, list[str]]:
    filas = {}
    for linea in _seccion_11().split("\n"):
        if not linea.startswith("|"):
            continue
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if celdas[0] in ("act", "---") or set(celdas[0]) <= {"-", ":"}:
            continue
        filas[celdas[0]] = celdas
    return filas


def test_la_tabla_del_lote_11_es_el_recibo_y_no_una_copia():
    """Celda a celda contra el recibo: una cifra editada a mano en la tabla no sobrevive."""
    rec, tabla = _sellado(), _tabla_11()
    zonas = {"margen_sano": "healthy margin", "banda_de_riesgo": "risk band",
             "fuera_de_cota": "out of bounds"}
    assert set(tabla) == {a["nombre"] for a in rec["actos"]}
    for a in rec["actos"]:
        c = tabla[a["nombre"]]
        assert c[1] == str(a["sesion"])
        assert c[2] == f"{a['k']:.4f}".replace(".", ",")
        assert c[3] == f"{a['mitad_umbral']:.4f}".replace(".", ",")
        assert c[4] == f"{a['umbral']:.4f}".replace(".", ",")
        assert c[5] == f"{a['margen']:.4f}".replace(".", ",")
        assert c[6] == f"{100 * a['margen_relativo']:.2f}".replace(".", ",")
        assert c[7] == zonas[a["zona"]]
        assert c[8] == ("yes" if a["publicable_como_booleano"] else "no")


def test_cada_cifra_de_la_prosa_del_lote_11_tiene_lector():
    rec, prosa = _sellado(), _prosa_11()
    assert rec["huella"] in prosa
    for a in rec["actos"]:
        assert f"{a['k']:.4f}".replace(".", ",") in prosa, f"k de {a['nombre']} sin lector"
        pct = f"{100 * a['margen_relativo']:.2f}".replace(".", ",")
        assert pct in prosa, f"margen de {a['nombre']} sin lector: {pct}"
    r = rec["resumen"]
    assert r["en_banda_de_riesgo_n"] == 1
    assert f"{len(r['por_zona']['margen_sano'])} acts sit in the healthy half" in prosa
    assert f"{len(r['por_zona']['banda_de_riesgo'])} in the risk band" in prosa
    assert f"{len(r['por_zona']['fuera_de_cota'])} out of bounds" in prosa
    assert "the boolean and the band disagree exactly once" in prosa.lower()
    assert "20 to 40" in prosa and "it fell" in prosa.lower()


def test_la_prosa_cotiza_el_acto_mas_caro_con_las_dos_cotas():
    rec, arte, prosa = _sellado(), _arte(), _prosa_11()
    caro = max((a for a in rec["actos"] if a["cotizacion"]), key=lambda a: a["coste_compuerta_s"])
    cot = caro["cotizacion"]
    assert f"{cot['coste_uso_s']:.1f}".replace(".", ",") + " s per use" in prosa
    assert f"{cot['usos_sin_arnes']} uses" in prosa
    bruto = next(a for a in arte["actos"] if a["nombre"] == caro["nombre"])
    assert f"{bruto['coste_compuerta_s']:.1f}".replace(".", ",") in prosa
    assert f"{bruto['coste_arnes_s']:.1f}".replace(".", ",") in prosa


def test_la_prosa_no_fija_un_coste_de_verificacion_que_cambia_en_cada_emision():
    """El coste de emitir el recibo es volatil: publicarlo como cifra seria publicar el reloj."""
    rec, prosa = _sellado(), _prosa_11()
    assert rec["medicion_de_si_mismo"]["coste_verificacion_s"] != 0
    assert "of the order of a microsecond" in prosa
    assert "1e-05" in prosa
    assert not re.search(r"\d,\d{4,6} s against", prosa)


def test_la_prosa_no_nombra_una_zona_que_el_recibo_no_tiene():
    rec, prosa = _sellado(), _prosa_11()
    nombres = {"margen_sano": "healthy margin", "banda_de_riesgo": "risk band",
               "fuera_de_cota": "out of bounds"}
    for zona, ingles in nombres.items():
        if rec["resumen"]["por_zona"][zona]:
            assert ingles in prosa, zona
        else:
            assert ingles not in prosa, zona


def test_el_veredicto_p1_no_confunde_un_acto_en_riesgo_con_la_mayoria_en_riesgo():
    resumen = {"actos": 8, "publicables_como_booleano": 4, "en_banda_de_riesgo_n": 3,
               "en_banda_de_riesgo": ["B", "C", "D"], "por_zona": {}}
    p1 = next(v for v in r11._veredictos(resumen, [], {"P1": "x"}) if v["id"] == "P1")
    assert p1["sobrevive"] is False  # 3 de 4 es la mayoria: el umbral q esta mal, no el booleano
    resumen["en_banda_de_riesgo_n"] = 2
    p1 = next(v for v in r11._veredictos(resumen, [], {"P1": "x"}) if v["id"] == "P1")
    assert p1["sobrevive"] is True  # 2 de 4 es exactamente la mitad
    resumen["en_banda_de_riesgo_n"] = 0
    p1 = next(v for v in r11._veredictos(resumen, [], {"P1": "x"}) if v["id"] == "P1")
    assert p1["sobrevive"] is False  # ninguno en riesgo: la banda no anadia nada




def test_cada_acto_hereda_la_sesion_de_su_fuente_y_no_de_su_posicion():
    """La sesion es del sujeto, no del indice: dos actos del mismo lote comparten ventana."""
    arte = _arte()
    rec = r11.recibo(arte, "fuera-de-dominio-10.json")
    for bruto, b in zip(arte["actos"], rec["actos"]):
        assert b["sesion"] == r11._sesion(bruto["fuente"])
    sesiones = [b["sesion"] for b in rec["actos"]]
    assert len(set(sesiones)) < len(sesiones), "todas distintas: la sesion vino del indice"
    assert sesiones.count(9) == 3 and sesiones.count(10) == 3
    for b in rec["actos"]:
        if b["sesion_n"] == 1:
            assert b["dispersion_dentro"] is None
        else:
            assert b["dispersion_dentro"] > 1


def test_el_veredicto_p4_cotiza_el_mismo_acto_que_el_recibo():
    rec = _sellado()
    caro = max((a for a in rec["actos"] if a["cotizacion"]), key=lambda a: a["coste_compuerta_s"])
    p4 = next(v for v in rec["veredictos"] if v["id"] == "P4")
    assert p4["medido"]["acto_mas_caro"] == caro["nombre"]
    assert p4["medido"]["usos_sin_arnes"] == caro["cotizacion"]["usos_sin_arnes"]
    assert p4["medido"]["usos_para_amortizar"] == caro["cotizacion"]["usos_para_amortizar"]
