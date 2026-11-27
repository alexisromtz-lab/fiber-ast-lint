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

import ast
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
    sellado = _sellado()
    rec = r11._reanclar_veredictos(
        r11.recibo(_arte(), str(ARTE), sellado["lote"]),
        r11._leer_prediccion(PRED),
    )
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
    rec = r11._reanclar_veredictos(r11.recibo(_arte(), str(ARTE), _sellado()["lote"]),
                                  r11._leer_prediccion(PRED))
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


# --- los sellos publicados: la prosa tiene lector ---------------------------
#
# El README publica trece prefijos de sello en prosa y hasta aqui ninguno tenia lector:
# editar uno de ellos no rompia nada. El defecto no esta en el recibo —que se verifica
# contra su propio campo— sino en el triangulo README <-> recibo <-> recomputacion, y en
# su denominador: el censo de sellos publicados nunca se declaro.

def _sellos_en_disco() -> list[Path]:
    return sorted(RAIZ.glob("recibo-banda-*.json"))


def _prefijos_publicados() -> set[str]:
    """Todo prefijo de sello que el README imprime, leido de la prosa y no repetido aqui."""
    return set(re.findall(r"`([0-9a-f]{8})…`", (RAIZ / "README.md").read_text()))


def test_el_censo_de_sellos_publicados_es_el_censo_de_sellos_en_disco():
    """Un recibo no esta publicado hasta que su prefijo esta en el README, y viceversa."""
    en_disco = {r11.huella(json.loads(p.read_text()))[:8] for p in _sellos_en_disco()}
    publicado = _prefijos_publicados()
    assert en_disco == publicado, (sorted(en_disco - publicado), sorted(publicado - en_disco))


def test_cada_sello_publicado_se_recomputa_y_coincide():
    """Cada prefijo publicado es el sha256 canonico del recibo que el README dice que es."""
    for ruta in _sellos_en_disco():
        sellado = json.loads(ruta.read_text())
        assert r11.huella(sellado) == sellado["huella"], ruta.name
        assert sellado["huella"][:8] in _prefijos_publicados(), ruta.name


def test_el_sello_del_lote_once_se_publica_entero():
    """La receta `jq | shasum` del README imprime 64 hex; el prefijo solo no lo probaria."""
    entero = re.search(r"`([0-9a-f]{64})`, which is the receipt's own",
                       (RAIZ / "README.md").read_text())
    assert entero, "el README ya no publica entero el sello del recibo de lote 11"
    assert r11.huella(json.loads(SELLADO.read_text())) == entero.group(1)


@pytest.mark.skipif(not JQ.exists(), reason="sin jq no hay segunda implementacion del sello")
def test_una_segunda_implementacion_reproduce_todos_los_sellos():
    """Sin nuestro interprete en el bucle: jq y shasum sobre el censo entero, no sobre uno."""
    for ruta in _sellos_en_disco():
        canon = subprocess.run(
            [str(JQ), "-S", "-c", "del(.huella, .medicion_de_si_mismo)", str(ruta)],
            capture_output=True, text=True, check=True,
        ).stdout.rstrip("\n")
        assert hashlib.sha256(canon.encode()).hexdigest() == json.loads(ruta.read_text())["huella"], ruta.name


# --- la prosa ---------------------------------------------------------------


ZONAS_EN = {"margen_sano": "healthy margin", "banda_de_riesgo": "risk band",
            "fuera_de_cota": "out of bounds"}


def _seccion(titulo: str) -> str:
    """El cuerpo bajo un encabezado, hasta el siguiente: una seccion nueva no alarga la anterior."""
    texto = (RAIZ / "README.md").read_text()
    ini = texto.index(titulo)
    cortes = [i for i in (texto.find("\n### ", ini + 1), texto.find("\n## ", ini + 1)) if i > 0]
    return texto[ini:min(cortes) if cortes else len(texto)]


def _seccion_11() -> str:
    return _seccion("### The boolean lied at the frontier")


def _prosa_11() -> str:
    return " ".join(_seccion_11().split())


def _tabla_de(seccion: str) -> dict[str, list[str]]:
    filas = {}
    for linea in seccion.split("\n"):
        if not linea.startswith("|"):
            continue
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if celdas[0] in ("act", "---") or set(celdas[0]) <= {"-", ":"}:
            continue
        filas[celdas[0]] = celdas
    return filas


def _tabla_11() -> dict[str, list[str]]:
    return _tabla_de(_seccion_11())


def test_la_tabla_del_lote_11_es_el_recibo_y_no_una_copia():
    """Celda a celda contra el recibo: una cifra editada a mano en la tabla no sobrevive."""
    rec, tabla = _sellado(), _tabla_11()
    zonas = ZONAS_EN
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


# --- lote 12: la banda es funcion del acto, no del artefacto ----------------


def _recibo_de(lote: int) -> dict:
    return json.loads((RAIZ / f"recibo-banda-12-lote{lote}.json").read_text())


def _crudo_de(lote: int) -> dict:
    return json.loads((RAIZ / f"fuera-de-dominio-{lote}.json").read_text())


def test_el_instrumento_no_compara_contra_ningun_numero_de_lote():
    """Si el codigo compara contra un lote concreto, el instrumento es una tabla de un dominio."""
    arbol = ast.parse((RAIZ / "bench" / "recibo.py").read_text())
    sospechosas = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Compare):
            continue
        operandos = [nodo.left, *nodo.comparators]
        nombra_lote = any("lote" in ast.unparse(o) for o in operandos)
        contra_entero = any(isinstance(o, ast.Constant) and isinstance(o.value, int) for o in operandos)
        if nombra_lote and contra_entero:
            sospechosas.append(ast.unparse(nodo))
    assert sospechosas == [], sospechosas


def test_la_banda_de_un_acto_no_depende_del_artefacto_que_lo_contiene():
    """A y B estan en los tres artefactos, C, D y E en dos: doce atestaciones, una sola banda."""
    por_acto: dict[str, list[dict]] = {}
    for rec in (_recibo_de(8), _recibo_de(9), _sellado()):
        for fila in rec["actos"]:
            por_acto.setdefault(fila["nombre"], []).append(fila)
    repetidos = {n: f for n, f in por_acto.items() if len(f) > 1}
    assert set(repetidos) == {"A", "B", "C", "D", "E"}
    assert sum(len(f) for f in repetidos.values()) == 12
    for nombre, filas in repetidos.items():
        for clave in ("k", "umbral", "margen", "margen_relativo", "zona"):
            valores = {f[clave] for f in filas}
            assert len(valores) == 1, f"{nombre} cambia {clave} entre artefactos: {valores}"


def test_el_acto_sellado_de_un_lote_anterior_hereda_esa_sesion():
    """El lote 8 no escribe `fuente`: su acto A trae el sellado del lote 7 y ahi se midio."""
    arte = _crudo_de(8)
    assert "fuente" not in arte["acto_a"] and "sellado_lote_7" in arte["acto_a"]
    assert r11._sesion_de(arte["acto_a"], 8) == 7
    assert r11._sesion_de(arte["acto_b"], 8) == 8
    assert r11._sesion_de({"reutilizado": True}, 8) is None


def test_el_recibo_del_lote_8_sale_del_par_acto_a_acto_b():
    arte = _crudo_de(8)
    assert "actos" not in arte
    rec = r11.recibo(arte, str(RAIZ / "fuera-de-dominio-8.json"))
    assert [f["nombre"] for f in rec["actos"]] == ["A", "B"]
    assert rec["sujeto"]["relojes"] == 180
    assert rec["sujeto"]["actos"] == 2


def test_el_lote_de_emision_por_defecto_es_el_del_artefacto():
    for lote in (8, 9, 10):
        fuente = str(RAIZ / f"fuera-de-dominio-{lote}.json")
        assert r11.recibo(_crudo_de(lote), fuente)["lote"] == lote
    # el recibo del lote 11 declara 11 sobre el artefacto del 10: la emision no es la fuente
    assert _sellado()["lote"] == 11 and _arte()["lote"] == 10


def test_dispersion_es_nulo_exactamente_donde_la_sesion_tiene_un_solo_acto():
    """Un acto solo no tiene dispersion: es NO_MEDIDO, nunca 1,0."""
    vistas = set()
    for rec in (_recibo_de(8), _recibo_de(9), _sellado()):
        for fila in rec["actos"]:
            assert (fila["dispersion_dentro"] is None) is (fila["sesion_n"] == 1), fila["nombre"]
            if fila["sesion_n"] > 1:
                assert fila["dispersion_dentro"] > 1.0
        for d in rec["resumen"]["dispersiones_por_sesion"].values():
            assert (d["dispersion"] is None) is (d["n"] == 1)
            vistas.add((d["n"], d["k_min"], d["k_max"]))
    assert {n for n, _, _ in vistas} == {1, 3}


def test_el_recibo_de_un_lote_sin_pre_registro_no_inventa_veredictos():
    assert _recibo_de(8)["veredictos"] == []
    assert _recibo_de(9)["veredictos"] == []
    assert [v["id"] for v in _sellado()["veredictos"]] == ["P1", "P4"]


def test_un_veredicto_sin_pre_registro_declarado_no_existe():
    resumen = {"actos": 2, "publicables_como_booleano": 1, "en_banda_de_riesgo_n": 1,
               "en_banda_de_riesgo": ["B"], "por_zona": {}}
    assert r11._veredictos(resumen, [], None) == []
    assert r11._veredictos(resumen, [], {}) == []
    assert [v["id"] for v in r11._veredictos(resumen, [], {"P1": "x"})] == ["P1"]


def test_los_dos_recibos_del_lote_12_verifican_su_huella():
    for n in (8, 9):
        r = subprocess.run(
            [sys.executable, str(RAIZ / "bench" / "recibo.py"),
             "--artefacto", str(RAIZ / f"fuera-de-dominio-{n}.json"),
             "--check", str(RAIZ / f"recibo-banda-12-lote{n}.json")],
            capture_output=True, text=True, cwd=RAIZ,
        )
        assert r.returncode == 0, r.stderr


def test_el_pre_registro_del_lote_12_declara_cuatro_predicciones_y_cero_relojes():
    pred = json.loads((RAIZ / "prediccion-batch-12.json").read_text())
    assert pred["declared_before_computation"] is True
    assert [p["id"] for p in pred["predictions"]] == ["P1", "P2", "P3", "P4"]
    assert pred["method"]["relojes_nuevos"] == 0
    assert all("falsador" in p for p in pred["predictions"])


def test_la_tabla_del_lote_12_es_la_union_de_los_tres_recibos():
    """La tabla de atestacion se recomputa: agrupar los recibos por acto y celda a celda."""
    recibos = {"8": _recibo_de(8), "9": _recibo_de(9), "10": _sellado()}
    por_acto: dict[str, dict[str, float | str]] = {}
    lotes: dict[str, list[str]] = {}
    for lote, rec in recibos.items():
        for fila in rec["actos"]:
            por_acto[fila["nombre"]] = fila
            lotes.setdefault(fila["nombre"], []).append(lote)
    tabla = _tabla_de(_seccion("### The band is a function of the act"))
    assert set(tabla) == set(por_acto) == set("ABCDEFGH")
    for nombre, fila in por_acto.items():
        c = tabla[nombre]
        cuantos = "lotes" if len(lotes[nombre]) > 1 else "lote"
        assert c[1] == f"{cuantos} {', '.join(lotes[nombre])}"
        assert c[2] == f"{fila['k']:.4f}".replace(".", ",")
        assert c[3] == ZONAS_EN[fila["zona"]]
        assert c[4] == str(len(lotes[nombre]))
    assert sum(len(v) for v in lotes.values()) == 15
    assert sum(1 for v in lotes.values() if len(v) > 1) == 5


def test_la_prosa_del_lote_12_nombra_sus_cifras_y_su_error_de_cuenta():
    """Doce atestaciones, quince celdas, y el trece del pre-registro publicado sin corregir."""
    prosa = " ".join(_seccion("### The band is a function of the act").split())
    for lote in (8, 9):
        assert _recibo_de(lote)["huella"] in prosa
    assert _sellado()["huella"][:8] in prosa
    assert "zero discrepancies" in prosa
    assert "twelve attestations" in prosa and "fifteen cells" in prosa
    assert "said \"thirteen cells\"" in prosa or 'said "thirteen cells"' in prosa
    assert "thirty-two band-and-session magnitudes" in prosa
    assert "the arithmetic of the prediction did not" in prosa


# --- lote 13: la poblacion juzgada iguala la poblacion declarada -------------

FUENTES_13 = {8: RAIZ / "fuera-de-dominio-8.json",
              9: RAIZ / "fuera-de-dominio-9.json",
              10: RAIZ / "fuera-de-dominio-10.json",
              11: RAIZ / "fuera-de-dominio-10.json"}


def _v2(lote: int) -> dict:
    return json.loads((RAIZ / f"recibo-banda-13-lote{lote}.json").read_text())


def test_el_recibo_v2_juzga_exactamente_lo_que_declara_su_pre_registro():
    """Dos fuentes que no se miran: el fichero del pre-registro en disco y la lista emitida."""
    declaradas = emitidas = evaluadas = 0
    for lote in (8, 9, 10, 11):
        rec = _v2(lote)
        pred = json.loads((RAIZ / rec["pre_registro"]["ruta"]).read_text())
        assert rec["schema"] == r11.CONTRATO_V2
        assert [v["id"] for v in rec["veredictos"]] == [p["id"] for p in pred["predictions"]]
        assert rec["resumen"]["veredictos"]["declaradas"] == len(pred["predictions"])
        assert rec["resumen"]["veredictos"]["emitidas"] == len(rec["veredictos"])
        declaradas += len(pred["predictions"])
        emitidas += len(rec["veredictos"])
        evaluadas += rec["resumen"]["veredictos"]["evaluadas"]
    assert (declaradas, emitidas, evaluadas) == (13, 13, 2)
    # Donde los dos lectores juzgan, tienen que coincidir: el nuevo no reinterpreta lo juzgado.
    viejo = {v["id"]: v for v in json.loads((RAIZ / "recibo-banda-11.json").read_text())["veredictos"]}
    nuevo = {v["id"]: v for v in _v2(11)["veredictos"]}
    assert set(viejo) < set(nuevo)
    for pid, v in viejo.items():
        assert nuevo[pid]["estado"] == "evaluado", pid
        assert nuevo[pid]["sobrevive"] == v["sobrevive"], pid
        assert nuevo[pid]["medido"] == v["medido"], pid


def test_un_veredicto_declarado_o_se_mide_o_dice_por_que_no_se_midio():
    """El juicio se recomputa con el codigo: si el lector miente, la ley no lo tapa el sello."""
    for lote in (8, 9, 10, 11):
        rec = r11.recibo_v2(json.loads(FUENTES_13[lote].read_text()), str(FUENTES_13[lote]), None,
                            RAIZ / f"prediccion-batch-{lote}.json")
        assert rec["veredictos"] == _v2(lote)["veredictos"], lote
        for v in rec["veredictos"]:
            assert v["prediccion"], v
            if v["estado"] == "evaluado":
                assert isinstance(v["sobrevive"], bool) and v["medido"] is not None, v
                assert "causa" not in v, v
                continue
            assert v["estado"] == "no_medido", v
            assert v["causa"] in r11.CAUSAS, v
            assert "sobrevive" not in v, v
            if v["causa"] == "fuera_de_la_huella":
                assert "::" in v["locus"], v
            elif v["causa"] == "metrica_ausente":
                assert v["evalua"], v


def test_v1_publica_una_caida_donde_no_hay_medida_y_v2_dice_metrica_ausente():
    """Q3: ningun acto de fuera-de-dominio-8.json declara coste_compuerta_s."""
    arte = _crudo_de(8)
    assert not [a for a in r11._actos(arte) if a.get("coste_compuerta_s")]
    fuente = str(FUENTES_13[8])
    v1 = r11._reanclar_veredictos(r11.recibo(arte, fuente), r11._leer_prediccion(PRED))
    p4_v1 = next(v for v in v1["veredictos"] if v["id"] == "P4")
    assert p4_v1["sobrevive"] is False
    assert p4_v1["medido"]["acto_mas_caro"] is None
    p4 = next(v for v in r11.recibo_v2(arte, fuente, None, PRED)["veredictos"] if v["id"] == "P4")
    assert p4["estado"] == "no_medido"
    assert p4["causa"] == "metrica_ausente"
    assert "sobrevive" not in p4


def test_un_recibo_se_verifica_con_el_contrato_que_el_declara_y_no_con_el_de_hoy():
    """Q4: los tres recibos v1 siguen verificando despues de nacer el contrato recibo/2."""
    pares = {11: "recibo-banda-11.json",
             8: "recibo-banda-12-lote8.json",
             9: "recibo-banda-12-lote9.json"}
    for lote, nombre in pares.items():
        sellado = json.loads((RAIZ / nombre).read_text())
        assert sellado["schema"] == r11.CONTRATO_V1
        r = subprocess.run(
            [sys.executable, str(RAIZ / "bench" / "recibo.py"),
             "--artefacto", str(FUENTES_13[lote]), "--check", str(RAIZ / nombre)],
            capture_output=True, text=True, cwd=RAIZ,
        )
        assert r.returncode == 0, r.stdout + r.stderr


def test_el_recibo_cita_su_pre_registro_por_hash_y_no_por_promesa():
    """Q5: la cita se comprueba con shasum, sin ejecutar el escaner ni creer la prosa."""
    for lote in (8, 9, 10, 11):
        cita = _v2(lote)["pre_registro"]
        crudo = (RAIZ / cita["ruta"]).read_bytes()
        assert cita["sha256"] == hashlib.sha256(crudo).hexdigest()
        assert cita["predictions"] == len(json.loads(crudo)["predictions"])
        assert cita["declared_before_computation"] is True
        assert "/" not in cita["ruta"]
    for viejo in ("recibo-banda-11.json", "recibo-banda-12-lote8.json",
                  "recibo-banda-12-lote9.json"):
        assert "pre_registro" not in json.loads((RAIZ / viejo).read_text())


def test_un_pre_registro_ausente_no_es_un_pre_registro_vacio():
    arte = _crudo_de(8)
    fuente = str(FUENTES_13[8])
    sin = r11.recibo_v2(arte, fuente)
    assert sin["veredictos"] == [] and sin["pre_registro"] is None
    assert sin["resumen"]["veredictos"]["declaradas"] is None
    con = r11.recibo_v2(arte, fuente, None, RAIZ / "prediccion-batch-8.json")
    assert len(con["veredictos"]) == 3
    assert {v["estado"] for v in con["veredictos"]} == {"no_medido"}


def test_un_identificador_sin_evaluador_se_publica_sin_evaluador_y_no_se_omite():
    resumen = {"actos": 2, "publicables_como_booleano": 1, "en_banda_de_riesgo_n": 1}
    v = r11._veredictos_v2(resumen, [], [{"id": "Z9", "claim": "una prediccion futura"}])
    assert len(v) == 1
    assert v[0]["estado"] == "no_medido" and v[0]["causa"] == "sin_evaluador"
    assert v[0]["id"] == "Z9"


def test_el_drenaje_del_contrato_v1_tiene_numero():
    """Q1: diez declaradas y dos juzgadas; seis drenadas a lista vacia y ocho sin juicio."""
    declaradas = juzgadas = a_vacia = 0
    for lote, nombre in ((8, "recibo-banda-12-lote8.json"),
                         (9, "recibo-banda-12-lote9.json"),
                         (11, "recibo-banda-11.json")):
        pred = json.loads((RAIZ / f"prediccion-batch-{lote}.json").read_text())
        rec = json.loads((RAIZ / nombre).read_text())
        declaradas += len(pred["predictions"])
        juzgadas += len(rec["veredictos"])
        if not rec["veredictos"]:
            a_vacia += len(pred["predictions"])
    assert (declaradas, juzgadas, a_vacia) == (10, 2, 6)
    assert declaradas - juzgadas == 8
    assert a_vacia * 2 > declaradas


def test_los_cuatro_recibos_del_lote_13_verifican_su_huella():
    for lote in (8, 9, 10, 11):
        r = subprocess.run(
            [sys.executable, str(RAIZ / "bench" / "recibo.py"),
             "--artefacto", str(FUENTES_13[lote]),
             "--check", str(RAIZ / f"recibo-banda-13-lote{lote}.json")],
            capture_output=True, text=True, cwd=RAIZ,
        )
        assert r.returncode == 0, r.stdout + r.stderr


# --- el lote 14: el juicio como funcion del predicado -----------------------

PREDICADOS_14 = {n: RAIZ / f"predicado-batch-{n}.json" for n in (8, 9, 10, 11)}


def _v3(lote: int) -> dict:
    return json.loads((RAIZ / f"recibo-banda-14-lote{lote}.json").read_text())


def _crudo14(lote: int) -> dict:
    """El artefacto con el que se emitio el recibo: el lote 11 se juzga sobre el del lote 10."""
    return json.loads(FUENTES_13[lote].read_text())


def _rec14(lote: int) -> dict:
    """Recomputa el recibo v3 en proceso: es lo que permite matar mutantes del interprete."""
    return r11.recibo_v3(_crudo14(lote), str(FUENTES_13[lote]), lote,
                         RAIZ / f"prediccion-batch-{lote}.json", PREDICADOS_14[lote])


def _ids(rec: dict) -> dict:
    return {v["id"]: v for v in rec["veredictos"]}


def test_r3_las_poblaciones_del_lote_14_son_las_declaradas():
    """10 expresables y 3 no: el numero lo fija el pre-registro, no el codigo."""
    declaradas = sum(len(json.loads(PREDICADOS_14[lote].read_text())["predicados"])
                     for lote in (8, 9, 10, 11))
    vistos = {"declaradas": 0, "evaluado": 0, "no_medido": 0}
    for lote in (8, 9, 10, 11):
        for v in _rec14(lote)["veredictos"]:
            vistos["declaradas"] += 1
            vistos[v["estado"]] += 1
    assert vistos == {"declaradas": 13, "evaluado": 10, "no_medido": 3}
    assert declaradas == 10
    ciegas = {v["id"] for lote in (8, 9, 10, 11) for v in _rec14(lote)["veredictos"]
              if v["estado"] == "no_medido"}
    assert ciegas == {"L3", "P2", "P3"}


def test_r2_el_predicado_juzga_lo_mismo_que_el_evaluador_cableado():
    """P1 y P4 tienen las dos vias escritas; el lote 14 no puede cambiar su veredicto."""
    cableado = _ids(json.loads((RAIZ / "recibo-banda-13-lote11.json").read_text()))
    con_pred = _ids(_rec14(11))
    for pid in ("P1", "P4"):
        assert con_pred[pid]["estado"] == "evaluado"
        assert con_pred[pid]["sobrevive"] == cableado[pid]["sobrevive"], pid
        assert con_pred[pid]["via"] == "predicado"


def test_r1_el_juicio_no_depende_del_identificador_sino_de_la_forma():
    """El mismo predicado bajo dos nombres distintos tiene que dar el mismo veredicto."""
    doc = r11._resolucion(_rec14(11))
    forma = {"expr": {"de": "/resumen/publicables_como_booleano", "agrega": "valor"},
             "rel": "gt", "valor": 3}
    a = r11.predicado.evaluar(forma, doc)
    b = r11.predicado.evaluar(json.loads(json.dumps(forma)), doc)
    assert a == b and a["estado"] == "evaluado"
    mapa = {"P1": {"evalua": forma}, "ZZ": {"evalua": forma}}
    preds = json.loads((RAIZ / "prediccion-batch-11.json").read_text())["predictions"]
    v = {x["id"]: x for x in r11._veredictos_v3(_rec14(11), preds + [{"id": "ZZ",
                                                                     "claim": "la misma forma"}],
                                                mapa)}
    assert v["P1"]["sobrevive"] == v["ZZ"]["sobrevive"] is True
    # Y el codigo no puede consultar el identificador para decidir. La guarda nombra el
    # parametro real: buscar la palabra 'id' no ve 'pid', y una guarda que no puede fallar
    # sobre lo que prohibe no es una guarda, es una promesa.
    fuente = (RAIZ / "bench" / "recibo.py").read_text()
    cuerpo = fuente.split("def _veredictos_v3", 1)[1].split("\ndef ", 1)[0]
    rama_por_nombre = re.compile(r"\b(pid|id)\b\s*(==|!=|in\b|not\s+in\b)")
    assert rama_por_nombre.search(cuerpo) is None, cuerpo
    # Y la guarda tiene que ser capaz de ver la rama que si existe: la tabla de la ausencia.
    ausencia = fuente.split("def _ausencia", 1)[1].split("\ndef ", 1)[0]
    assert rama_por_nombre.search(ausencia) is not None, ausencia


def test_r4_una_poblacion_vacia_no_es_una_poblacion_que_cumple():
    doc = {"actos": [{"nombre": "A", "hechos": {"minimo_s": 0.2}}]}
    pred = {"de": "/actos/*/hechos/sonda_sobre_min", "todos": {"rel": "le", "valor": 1.15}}
    v = r11.predicado.evaluar(pred, doc)
    assert (v["estado"], v["causa"]) == ("no_medido", "poblacion_vacia"), v
    assert r11.predicado.evaluar({"no": pred}, doc)["estado"] == "no_medido"


def test_r5_un_predicado_ilegible_no_es_un_predicado_falso():
    doc = {"x": 1}
    for roto in ({"expr": {"de": "/x", "agrega": "valor"}, "rel": "aproximado", "valor": 1},
                 {"expr": {"de": "/x", "agrega": "mediana"}, "rel": "lt", "valor": 1},
                 {"expr": {"de": "/x", "agrega": "valor"}, "rel": "lt"},
                 {"expr": {"op": "suma", "a": {"de": "/x", "agrega": "valor"},
                           "b": {"de": "/x", "agrega": "valor"}},
                  "rel": "lt", "valor": 2}):
        v = r11.predicado.evaluar(roto, doc)
        assert v["estado"] == "no_medido" and v["causa"] == "predicado_ilegible", roto
        assert "sobrevive" not in v


def test_una_magnitud_ausente_es_una_causa_y_no_un_cero():
    doc = {"actos": [{"nombre": "A", "hechos": {}}]}
    v = r11.predicado.evaluar(
        {"expr": {"de": "/actos/A/hechos/minimo_s", "agrega": "valor"}, "rel": "lt", "valor": 1},
        doc)
    assert (v["estado"], v["causa"]) == ("no_medido", "metrica_ausente"), v


def test_la_poblacion_de_un_cuantificador_es_la_que_declara_la_magnitud():
    """M2 no la votan los actos que no corrieron la sonda: seria inventar un cero."""
    actos = _acto_de_los_fuera_de_dominio(10)
    con = [a for a in actos if "sonda_sobre_min" in a]
    sin = [dict(a, nombre="Z") for a in actos if "sonda_sobre_min" not in a]
    assert con and sin
    doc = {"actos": con + sin}
    v = r11.predicado.evaluar(
        {"de": "/actos/*/hechos/sonda_sobre_min", "todos": {"rel": "le", "valor": 1.15}},
        r11._resolucion({"actos": [{**a, "hechos": r11._hechos(a)} for a in doc["actos"]]}))
    m = v["medido"]
    assert m["poblacion"] == len(con) and m["cumplen"] == m["poblacion"], v


def _acto_de_los_fuera_de_dominio(lote: int) -> list[dict]:
    return r11._actos(json.loads((RAIZ / f"fuera-de-dominio-{lote}.json").read_text()))


def test_la_resolucion_no_depende_del_orden_en_que_el_json_se_escribio():
    doc = {"m": {"b": 2, "a": 1, "c": 3}}
    ordenado = r11.predicado.resolver(doc, "/m/*")
    desordenado = r11.predicado.resolver({"m": {"c": 3, "a": 1, "b": 2}}, "/m/*")
    assert ordenado == desordenado == [1, 2, 3]


def test_un_acto_se_nombra_y_no_se_cuenta():
    """'/actos/B' tiene que decir lo mismo aunque el artefacto reordene sus actos."""
    doc = {"actos": [{"nombre": "A", "k": 1}, {"nombre": "B", "k": 2}]}
    assert r11.predicado.resolver(doc, "/actos/B/k") == [2]
    invertido = {"actos": [{"nombre": "B", "k": 2}, {"nombre": "A", "k": 1}]}
    assert r11.predicado.resolver(invertido, "/actos/B/k") == [2]
    assert r11.predicado.resolver(invertido, "/actos/0/k") == [2]


def test_el_predicado_cita_su_pre_registro_por_hash_y_si_el_texto_cambia_no_vale():
    for lote in (8, 9, 10, 11):
        p = json.loads(PREDICADOS_14[lote].read_text())
        real = hashlib.sha256((RAIZ / f"prediccion-batch-{lote}.json").read_bytes()).hexdigest()
        assert p["cita_pre_registro"]["sha256"] == real, lote
    _, cita, _ = r11.predicado.leer(PREDICADOS_14[8])
    assert cita["cita_pre_registro"]["sha256"] == hashlib.sha256(
        (RAIZ / "prediccion-batch-8.json").read_bytes()).hexdigest()


def test_los_cuatro_recibos_del_lote_14_verifican_su_huella():
    for lote in (8, 9, 10, 11):
        r = subprocess.run(
            [sys.executable, str(RAIZ / "bench" / "recibo.py"),
             "--artefacto", str(FUENTES_13[lote]),
             "--check", str(RAIZ / f"recibo-banda-14-lote{lote}.json")],
            capture_output=True, text=True, cwd=RAIZ,
        )
        assert r.returncode == 0, r.stdout + r.stderr


def test_el_contrato_v2_no_cambia_cuando_el_v3_anade_causas():
    """Las causas del v3 no pueden reescribir el resumen de un recibo ya sellado."""
    assert r11.CAUSAS[: len(r11.CAUSAS_V2)] == r11.CAUSAS_V2
    for lote in (8, 9, 10, 11):
        rec = r11.recibo_v2(_crudo14(lote), str(FUENTES_13[lote]), lote,
                            RAIZ / f"prediccion-batch-{lote}.json")
        sellado = json.loads((RAIZ / f"recibo-banda-13-lote{lote}.json").read_text())
        # ``medicion_de_si_mismo`` lo mide main, no recibo_v2: fuera del objeto firmado.
        sellado.pop("medicion_de_si_mismo", None)
        assert rec == sellado, lote


def test_un_v3_sin_el_interprete_al_lado_no_se_publica_verde(tmp_path: Path):
    (tmp_path / "bench").mkdir()
    (tmp_path / "bench" / "recibo.py").write_bytes((RAIZ / "bench" / "recibo.py").read_bytes())
    for f in ("fuera-de-dominio-10.json", "prediccion-batch-11.json",
              "predicado-batch-11.json", "recibo-banda-14-lote11.json"):
        (tmp_path / f).write_bytes((RAIZ / f).read_bytes())
    r = subprocess.run(
        [sys.executable, str(tmp_path / "bench" / "recibo.py"),
         "--artefacto", str(tmp_path / "fuera-de-dominio-10.json"),
         "--check", str(tmp_path / "recibo-banda-14-lote11.json")],
        capture_output=True, text=True, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 5, r.stdout + r.stderr
    assert "predicado.py" in r.stderr
    # Con el interprete al lado verifica: son cinco archivos, no cuatro.
    (tmp_path / "bench" / "predicado.py").write_bytes((RAIZ / "bench" / "predicado.py").read_bytes())
    r = subprocess.run(
        [sys.executable, str(tmp_path / "bench" / "recibo.py"),
         "--artefacto", str(tmp_path / "fuera-de-dominio-10.json"),
         "--check", str(tmp_path / "recibo-banda-14-lote11.json")],
        capture_output=True, text=True, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_un_v2_se_verifica_sin_el_interprete_al_lado():
    """El claim comercial del v2 no puede cobrar un modulo que su contrato no nombra."""
    assert "predicado" not in (RAIZ / "recibo-banda-11.json").read_text()


def test_un_pre_registro_alterado_invalida_la_traduccion_que_lo_cita(tmp_path: Path):
    """Traducir no es editar: si el texto cambio, el predicado deja de valer y el recibo no sale."""
    retocado = json.loads((RAIZ / "prediccion-batch-8.json").read_text())
    retocado["title"] = str(retocado.get("title", "")) + " (retocado)"
    (tmp_path / "prediccion-batch-8.json").write_text(json.dumps(retocado))
    (tmp_path / "predicado-batch-8.json").write_bytes(PREDICADOS_14[8].read_bytes())
    with pytest.raises(r11.predicado.Ilegible):
        r11.predicado.leer(tmp_path / "predicado-batch-8.json")

    (tmp_path / "bench").mkdir()
    for f in ("recibo.py", "predicado.py"):
        (tmp_path / "bench" / f).write_bytes((RAIZ / "bench" / f).read_bytes())
    (tmp_path / "fuera-de-dominio-8.json").write_bytes(FUENTES_13[8].read_bytes())
    r = subprocess.run(
        [sys.executable, str(tmp_path / "bench" / "recibo.py"),
         "--artefacto", str(tmp_path / "fuera-de-dominio-8.json"),
         "--prediccion", str(tmp_path / "prediccion-batch-8.json"),
         "--predicados", str(tmp_path / "predicado-batch-8.json"),
         "--lote", "8", "--salida", str(tmp_path / "r.json")],
        capture_output=True, text=True, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 5, r.stdout + r.stderr
    assert not (tmp_path / "r.json").exists()


# --- el lote 15: un grado de composicion y la ausencia declarada ------------

PREDICADO_15 = RAIZ / "predicado-batch-15.json"
PREDICADO_15_LOTE11 = RAIZ / "predicado-batch-15-lote11.json"


def test_la_profundidad_dos_juzga_lo_que_el_lote_nueve_declaro_no_expresable():
    """L3 era el unico hueco expresivo medido: se cierra con un grado, no con un lenguaje."""
    viejo = json.loads((RAIZ / "predicado-batch-9.json").read_text())
    assert [a for a in viejo["no_se_traduce"] if str(a).startswith("L3")]
    nuevo = json.loads(PREDICADO_15.read_text())
    assert nuevo["no_se_traduce"] == []
    l3 = nuevo["predicados"][0]
    assert l3["id"] == "L3"
    assert r11.predicado.validar(l3["evalua"]) == []
    assert r11.predicado.clasificar(l3["evalua"]) == "expresable"
    resumen = json.loads((RAIZ / "recibo-banda-15-lote9.json").read_text())["resumen"]
    assert (resumen["veredictos"]["evaluadas"], resumen["veredictos"]["no_medidas"]) == (1, 0)


def test_un_texto_congelado_ambiguo_publica_las_dos_lecturas_y_no_elige():
    """La banda 0,80-1,25 es reciproca de si misma: no hay lectura comoda que escoger."""
    l3 = json.loads((RAIZ / "recibo-banda-15-lote9.json").read_text())["veredictos"][0]
    cifras = [c["expr"] for c in l3["medido"]["y"]]
    assert len(set(cifras)) == 2, cifras
    dentro = [c for c in cifras if 0.8 <= c <= 1.25]
    assert len(dentro) == 1, cifras
    assert l3["sobrevive"] is False
    regla = json.loads(PREDICADO_15.read_text())["regla_de_lectura"]
    assert len(regla["lecturas"]) == 2 and regla["falsifier"]


def test_la_gramatica_se_decide_sin_documento_y_vence_a_la_ausencia_de_dato():
    """Sin el validador estatico, un predicado hondo sobre un hueco diria 'falta el dato'."""
    hondo = {"expr": {"de": "/actos/*",
                      "despliega": {"de": "/b/*",
                                    "despliega": {"de": "/c", "agrega": "valor"},
                                    "agrega": "media"},
                      "agrega": "media"},
             "rel": "lt", "valor": 1}
    defectos = r11.predicado.validar(hondo)
    assert defectos and "profundidad" in defectos[0], defectos
    assert r11.predicado.clasificar(hondo) == "inexpresable"
    # El documento no trae el puntero: sin validacion previa la causa seria metrica_ausente.
    v = r11._veredictos_v3({"actos": []}, [{"id": "X", "claim": "profundidad 3"}],
                           {"X": {"evalua": hondo}})
    assert (v[0]["estado"], v[0]["causa"]) == ("no_medido", "predicado_ilegible"), v[0]


def test_una_cadena_no_declara_motivo_y_la_tabla_responde_por_ella():
    """P2 y P3 viajan como prosa en el lote 11; prosa no es una causa declarada."""
    mapa, _, ausencias = r11.predicado.leer(RAIZ / "predicado-batch-11.json")
    assert set(mapa) == {"P1", "P4"}
    assert ausencias["P2"].get("motivo") is None
    assert r11._ausencia("P2", ausencias) == {"estado": "no_medido",
                                              "causa": "fuera_de_la_huella",
                                              "locus": r11.FUERA_DE_LA_HUELLA["P2"]}
    decl = {"P2": {"id": "P2", "motivo": "metrica_ausente", "locus": "x:1"}}
    assert r11._ausencia("P2", decl) == {"estado": "no_medido",
                                         "causa": "metrica_ausente", "locus": "x:1"}


def test_los_veredictos_del_lote_quince_son_los_del_catorce_byte_a_byte():
    """Abrir un grado de composicion no puede mover lo que ya estaba juzgado."""
    a = json.loads((RAIZ / "recibo-banda-15-lote11.json").read_text())["veredictos"]
    b = json.loads((RAIZ / "recibo-banda-14-lote11.json").read_text())["veredictos"]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_el_sello_declara_su_pre_registro_y_el_verificador_no_lo_adivina(tmp_path):
    """Un recibo puede juzgar un pre-registro anterior; adivinar por lote lo falsearia."""
    (tmp_path / "bench").mkdir()
    for f in ("recibo.py", "predicado.py"):
        (tmp_path / "bench" / f).write_bytes((RAIZ / "bench" / f).read_bytes())
    for f in ("fuera-de-dominio-10.json", "prediccion-batch-11.json",
              "predicado-batch-15-lote11.json", "recibo-banda-15-lote11.json"):
        (tmp_path / f).write_bytes((RAIZ / f).read_bytes())
    # No se copia prediccion-batch-15.json: si el verificador adivina, no encuentra nada.
    r = subprocess.run(
        [sys.executable, str(tmp_path / "bench" / "recibo.py"),
         "--artefacto", str(tmp_path / "fuera-de-dominio-10.json"),
         "--check", str(tmp_path / "recibo-banda-15-lote11.json")],
        capture_output=True, text=True, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_el_predicado_del_lote_quince_reproduce_el_recibo_que_emitio(tmp_path):
    """El fichero de predicado es carga, no adorno: recomputar debe dar la huella sellada.

    Sin esto, cambiar ``y`` por ``o`` en L3 (una lectura dentro de banda basta para sobrevivir)
    pasaria la suite entera sin que ningun test lo notara.
    """
    (tmp_path / "bench").mkdir()
    for f in ("recibo.py", "predicado.py"):
        (tmp_path / "bench" / f).write_bytes((RAIZ / "bench" / f).read_bytes())
    for f in ("fuera-de-dominio-9.json", "prediccion-batch-9.json", "prediccion-batch-15.json",
              "predicado-batch-15.json", "recibo-banda-15-lote9.json"):
        (tmp_path / f).write_bytes((RAIZ / f).read_bytes())
    r = subprocess.run(
        [sys.executable, str(tmp_path / "bench" / "recibo.py"),
         "--artefacto", str(tmp_path / "fuera-de-dominio-9.json"),
         "--check", str(tmp_path / "recibo-banda-15-lote9.json")],
        capture_output=True, text=True, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_en_profundidad_dos_un_nodo_mudo_no_vota_y_no_se_lee_como_cero():
    """La ausencia se propaga dentro del paso compuesto: el cero seria un voto falso."""
    doc = {"actos": [
        {"hechos": {"bloques": [{"min_s": 2.0, "jitter_s": 1.0}, {"min_s": 6.0, "jitter_s": 1.0}]}},
        {"hechos": {"bloques": [{"min_s": 4.0, "jitter_s": 1.0}]}},
        {"hechos": {"bloques": [{"min_s": 99.0}]}},
        {"hechos": {"bloques": []}},
    ]}
    pred = {"expr": {"de": "/actos/*",
                     "despliega": {"op": "razon",
                                   "a": {"de": "/hechos/bloques/*/min_s", "agrega": "min"},
                                   "b": {"de": "/hechos/bloques/*/jitter_s", "agrega": "max"}},
                     "agrega": "media"},
            "rel": "entre", "valor": [0.0, 10.0]}
    v = r11.predicado.evaluar(pred, doc)
    assert (v["estado"], v["sobrevive"]) == ("evaluado", True)
    # Votan dos de cuatro actos: media(2, 4) = 3,0. Contarlos como cero daria 1,5.
    assert v["medido"]["expr"] == 3.0, v["medido"]
    solo_mudos = {"actos": [{"hechos": {"bloques": [{"min_s": 99.0}]}}]}
    mudo = r11.predicado.evaluar(pred, solo_mudos)
    assert (mudo["estado"], mudo["causa"]) == ("no_medido", "poblacion_vacia"), mudo
