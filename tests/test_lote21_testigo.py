"""El testigo hermano paga la deuda del lote 20, y su recibo cierra por medida.

El lote 20 archivo un locus externo como defecto del instrumento: la funcion que vigila la
repeticion con un conjunto hermano y la que no mira nada reciban el mismo veredicto. El lote
21 ensena al observador a ver quien alimenta el testigo, y este fichero custodia las dos
cosas que un cambio asi puede romper: la ventana congelada que dice que solo un locus se
movio, y la afirmacion de P4 de que con las features publicadas no se construye un filtro de
alta confianza. La segunda se prueba por enumeracion, no por lectura.

Las features de una candidata interna se calculan aqui, en vivo: el recibo congela las siete
externas porque su fuente no esta en el arbol, y las cuatro internas porque su fuente si lo
esta y copiarlas dejaria el recibo sin lector.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

from fiber_ast_lint.cli import construir

RAIZ = Path(__file__).resolve().parents[1]
PRE_REGISTRO = RAIZ / "prediccion-batch-21.json"
RECIBO = RAIZ / "recibo-lote21-20261127.json"
FIXTURES = RAIZ / "tests" / "fixtures"

FEATURES = ["familia", "forma", "escapa", "llamadas_positivas"]
CONSTANTES = ["poblacion", "publica"]

PREDICCIONES = ["P1", "P2", "P3", "P4"]
ADMITIDAS = ["espacio_no_transversal.py:31", "columna_no_transversal.py:11"]


def _cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _candidatas_internas() -> list[dict]:
    r = construir(str(FIXTURES), interproc=False)
    return [
        {
            "locus": f"{loc.rel}:{loc.linea}",
            "vector": {
                "familia": loc.familia,
                "forma": loc.forma,
                "escapa": loc.escapa,
                "llamadas_positivas": loc.llamadas > 0,
                "poblacion": loc.poblacion,
                "publica": loc.publica,
            },
        }
        for loc in r["analisis"].loci
        if loc.candidato
    ]


def _filas() -> list[tuple[str, dict, str]]:
    """Las once filas de la busqueda: siete externas del recibo y cuatro internas vivas."""
    recibo = _cargar(RECIBO)
    filas = [
        (e["locus"], {**e["vector"], "llamadas_positivas": e["llamadas_crudo"] > 0}, "externo")
        for e in recibo["ventana_externa"]["candidatas_despues"]
    ]
    filas += [(c["locus"], c["vector"], "interno") for c in _candidatas_internas()]
    return filas


def _pasa(vector: dict, cons: list[tuple[str, str, object]]) -> bool:
    for nombre, op, valor in cons:
        if op == "=" and vector[nombre] != valor:
            return False
        if op == "!=" and vector[nombre] == valor:
            return False
    return True


def _dominios(features: list[str], filas: list[tuple[str, dict, str]]) -> list[list]:
    return [
        [None] + [("=", v) for v in dominio] + [("!=", v) for v in dominio]
        for dominio in (sorted({f[1][n] for f in filas}, key=str) for n in features)
    ]


def _predicados(features: list[str], filas: list[tuple[str, dict, str]]) -> int:
    return len(list(itertools.product(*_dominios(features, filas))))


def _separadores(
    features: list[str],
    positivas: list[str],
    negativas: list[str],
    filas: list[tuple[str, dict, str]],
) -> list[list[tuple[str, str, object]]]:
    salida = []
    for combo in itertools.product(*_dominios(features, filas)):
        cons = [(features[i], c[0], c[1]) for i, c in enumerate(combo) if c]
        if all(_pasa(v, cons) for n, v, _ in filas if n in positivas) and not any(
            _pasa(v, cons) for n, v, _ in filas if n in negativas
        ):
            salida.append(cons)
    return salida


def test_el_pre_registro_cerro_antes_del_parche() -> None:
    recibo = _cargar(RECIBO)
    pre = recibo["pre_registro"]
    assert pre["ruta"] == PRE_REGISTRO.name
    assert pre["sha256"] == _sha(PRE_REGISTRO) == pre["verificado_en_este_acto"]
    assert pre["declarado_antes"] is True
    assert pre["hipotesis"] == PREDICCIONES
    assert [p["id"] for p in _cargar(PRE_REGISTRO)["predictions"]] == PREDICCIONES


def test_la_ventana_congelada_sigue_siendo_la_de_la_prediccion() -> None:
    # Sin red: la huella del fichero congelado se compara contra la que declaro el
    # pre-registro, no contra una descarga de hoy.
    pred = _cargar(PRE_REGISTRO)["universo"]["ventana_externa"]["ficheros"]
    recibo = _cargar(RECIBO)["ventana_externa"]
    assert recibo["sha256_recomputado_identico"] is True
    assert recibo["ficheros"] == pred
    assert len(pred) == 5
    for fichero in pred:
        assert len(fichero["sha256"]) == 64, fichero["ruta"]
        assert fichero["url"].endswith(fichero["ruta"]), fichero["ruta"]
        assert fichero["sha"] in fichero["url"], fichero["ruta"]


def test_un_solo_locus_cambia_de_cubeta_en_la_ventana() -> None:
    """P3: el predicado nuevo alcanza exactamente el locus que vigila, y ninguno mas."""
    ventana = _cargar(RECIBO)["ventana_externa"]
    antes = {c["locus"] for c in ventana["candidatas_antes"]}
    despues = {c["locus"] for c in ventana["candidatas_despues"]}
    assert antes - despues == {"src/safo/ratebudget.py:1239"}
    assert despues - antes == set()
    assert (ventana["medido_antes"]["guardadas"], ventana["medido_despues"]["guardadas"]) == (1, 2)
    assert (ventana["medido_antes"]["sin_len"], ventana["medido_despues"]["sin_len"]) == (15, 14)
    for nombre in ("archivos", "almacenes", "pierde", "acumulacion", "posicional"):
        assert ventana["medido_antes"][nombre] == ventana["medido_despues"][nombre], nombre
    assert [r["locus"] for r in _cargar(RECIBO)["reclasificados"]] == [
        "src/safo/ratebudget.py:1239"
    ]


def test_un_testigo_alimentado_por_suscripcion_por_append_o_en_cadena(tmp_path: Path) -> None:
    """El testigo no tiene por que crecer con `add`: cualquier escritura de la clave vale."""
    (tmp_path / "alimentados.py").write_text(
        "def por_suscripcion(rows):\n"
        "    out = {}\n"
        "    visto = {}\n"
        "    for r in rows:\n"
        "        k = r.name.lower()\n"
        "        if k in visto:\n"
        "            continue\n"
        "        visto[k] = True\n"
        "        out[k] = r\n"
        "    return out\n"
        "\n"
        "\n"
        "def por_llamada_encadenada(rows, valida):\n"
        "    out = {}\n"
        "    nombres = []\n"
        "    for r in rows:\n"
        "        k = r.name.lower()\n"
        "        if k not in nombres and valida(k):\n"
        "            nombres.append(k)\n"
        "            out[k] = r\n"
        "    return out\n"
        "\n"
        "\n"
        "def por_append(rows):\n"
        "    out = {}\n"
        "    vistos = []\n"
        "    for r in rows:\n"
        "        k = r.name.lower()\n"
        "        if k in vistos:\n"
        "            continue\n"
        "        vistos.append(k)\n"
        "        out[k] = r\n"
        "    return out\n",
        encoding="utf-8",
    )
    r = construir(str(tmp_path), interproc=False)
    # Ningun locus: los tres acumuladores y su testigo quedan medidos. Cuatro almacenes, no
    # tres, porque en `por_suscripcion` el testigo tambien se vigila a si mismo.
    assert r["analisis"].loci == []
    assert r["analisis"].guardadas == 4
    assert r["analisis"].reconcilia()


def test_el_limite_declarado_tambien_se_mide(tmp_path: Path) -> None:
    """Falso negativo publicado: un hermano que solo comparte la clave retira el almacen.

    `errores` no vigila la repeticion: cuenta cuantas veces se repite una clave, y cuando la
    repeticion llega, `out[k]` se escribe encima sin defensa. El predicado infiere inventario
    de la clave compartida y da por vigilado un almacen que pierde filas. Se fija como
    frontera conocida, no como acierto: un falso negativo declarado se puede acotar, uno
    escondido se descubre en el issue de un tercero.
    """
    (tmp_path / "inventario_ajeno.py").write_text(
        "def deposito(rows):\n"
        "    out = {}\n"
        "    errores = {}\n"
        "    for r in rows:\n"
        "        k = r.name.lower()\n"
        "        if k in errores:\n"
        "            errores[k] += 1\n"
        "            out[k] = r\n"
        "            continue\n"
        "        errores[k] = 0\n"
        "        out[k] = r\n"
        "    return out\n",
        encoding="utf-8",
    )
    r = construir(str(tmp_path), interproc=False)
    # El defecto, medido: cuando la clave se repite, la rama de `errores` escribe `out[k]`
    # encima del inquilino anterior. El instrumento no ve perder nada.
    assert r["analisis"].loci == []
    assert r["analisis"].pierde == 0
    assert r["analisis"].guardadas == r["analisis"].almacenes
    assert r["analisis"].reconcilia()
    recibo = _cargar(RECIBO)
    limites = " ".join(recibo["instrumento"]["limites_declarados"])
    assert "comparte la clave" in limites


def test_el_testigo_propio_y_la_lista_fija_conservan_su_cubeta(tmp_path: Path) -> None:
    """El borde del predicado nuevo: `if k in out` no es hermano, y una lista fija no se alimenta."""
    (tmp_path / "bordes.py").write_text(
        "PERMITIDOS = {'a', 'b'}\n"
        "\n"
        "\n"
        "def testigo_propio(rows):\n"
        "    out = {}\n"
        "    for r in rows:\n"
        "        k = r.name.lower()\n"
        "        if k in out:\n"
        "            continue\n"
        "        out[k] = r\n"
        "    return out\n"
        "\n"
        "\n"
        "def lista_fija(rows):\n"
        "    out = {}\n"
        "    for r in rows:\n"
        "        k = r.name.lower()\n"
        "        if k not in PERMITIDOS:\n"
        "            continue\n"
        "        out[k] = r\n"
        "    return out\n",
        encoding="utf-8",
    )
    r = construir(str(tmp_path), interproc=False)
    poblacion = {loc.fn: loc.poblacion for loc in r["analisis"].loci}
    assert poblacion == {"lista_fija": "cardinal_sin_medir"}
    assert r["analisis"].guardadas == 1


def test_ningun_predicado_separa_los_dos_admitidos() -> None:
    """P4 por enumeracion: el falsador se cumple si aparece un separador."""
    filas = _filas()
    externas = [n for n, _, k in filas if k == "externo"]
    internas = [n for n, _, k in filas if k == "interno"]
    assert len(externas) == 7
    assert len(internas) == 4
    assert set(ADMITIDAS) <= set(internas)

    # Dos de las seis features son constantes sobre la poblacion: no pueden separar nada.
    for nombre in CONSTANTES:
        assert len({v[nombre] for _, v, _ in filas}) == 1, nombre

    assert _predicados(FEATURES, filas) == 1925
    assert _predicados(FEATURES + CONSTANTES, filas) == 17325

    con_llamadas = [
        n for n, v, k in filas if k == "externo" and v["llamadas_positivas"]
    ]
    no_admitidas = [n for n in internas if n not in ADMITIDAS]
    for negativas in (externas, con_llamadas, externas + no_admitidas):
        assert _separadores(FEATURES, ADMITIDAS, negativas, filas) == []

    recibo = _cargar(RECIBO)["separabilidad"]
    assert recibo["poblacion"] == {
        "filas": 11,
        "externas": 7,
        "internas_candidatas": 4,
    }
    assert recibo["espacio"] == {"seis_features": 17325, "cuatro_features": 1925}
    assert recibo["separadores_dos_admitidos"] == {
        "contra_siete_externas": 0,
        "contra_seis_de_llamadas_positivas": 0,
        "contra_externas_mas_internas_no_positivas": 0,
    }


def test_la_lectura_estrecha_compra_precision_silenciando_tres_de_cuatro() -> None:
    """Sensibilidad posterior: si solo `espacio_no_transversal.py:31` cuenta como defecto."""
    filas = _filas()
    positivas = ["espacio_no_transversal.py:31"]
    negativas = [n for n, _, _ in filas if n not in positivas]
    separadores = _separadores(FEATURES, positivas, negativas, filas)
    assert len(separadores) == 45

    internas = [n for n, _, k in filas if k == "interno"]
    recalls: dict[int, int] = {}
    for cons in separadores:
        vivas = sum(1 for n, v, _ in filas if n in internas and _pasa(v, cons))
        recalls[vivas] = recalls.get(vivas, 0) + 1
    assert recalls == {1: 45}

    fijan = sum(
        1
        for cons in separadores
        if any(f == "familia" and op == "=" and v == "ESPACIO+NORMALIZA" for f, op, v in cons)
    )
    niegan = sum(
        1
        for cons in separadores
        if any(f == "familia" and op == "!=" and v == "CONJUNTO+ESPACIO" for f, op, v in cons)
    )
    assert (fijan, niegan) == (36, 9)

    recibo = _cargar(RECIBO)["separabilidad"]["sensibilidad_posterior"]
    assert recibo["separadores"] == 45
    assert recibo["recall_sobre_las_cuatro_internas"] == {"1": 45}
    assert recibo["fijan_familia_espacio_normaliza"] == 36
    assert recibo["niegan_familia_conjunto_espacio"] == 9


def test_dos_loci_de_signo_opuesto_son_indistinguibles_por_sus_features() -> None:
    """La identidad que vuelve P4 un teorema, comprobada sobre las seis features."""
    filas = dict((n, v) for n, v, _ in _filas())
    externa = filas["custom_components/opnsense/device_tracker_evidence.py:539"]
    interna = filas["columna_no_transversal.py:11"]
    assert external_seis(externa) == external_seis(interna)
    recibo = _cargar(RECIBO)["separabilidad"]
    assert "device_tracker_evidence.py:539" in recibo["identidad_que_lo_vuelve_teorema"]


def external_seis(vector: dict) -> dict:
    return {k: vector[k] for k in FEATURES + CONSTANTES}


def test_el_recibo_no_abre_reportes_y_declara_el_siguiente_acto() -> None:
    recibo = _cargar(RECIBO)
    assert recibo["schema"] == "fiber-ast-lint/lote21/1"
    assert [v["id"] for v in recibo["veredictos"]] == PREDICCIONES
    assert {v["veredicto"] for v in recibo["veredictos"]} == {"CONFIRMADA"}
    assert recibo["no_se_hizo"]["reportes_abiertos"] == 0
    assert "lote 22" in recibo["proximo_acto"]["nombre"]
    assert recibo["censo_reemision"]["replay"]["rc"] == 0
    assert "REPLAY IDENTICO · 13 filas" in recibo["censo_reemision"]["replay"]["cola"]
