"""El giro hacia afuera pide sujetos licenciables, y el censo no los tiene.

El lote 19 cruzo la frontera con un sujeto y no pudo publicar su hallazgo: el sujeto no
declara licencia. El lote 20 no busca mas sujetos del mismo tipo; mide el denominador antes
de clonar nada y publica la respuesta cruda, porque un filtro corrido contra la API y no
congelado deja un denominador que ningun tercero puede recomputar.

Estas pruebas leen el censo congelado y recomputan el filtro. Cinco cierran el triangulo
pre-registro, censo y recibo. La ultima era una deuda —el instrumento reconoce el testigo
por pertenencia solo cuando nombra al propio acumulador, y el codigo real vigila con un
conjunto hermano— y el lote 21 la paga: la prueba cambio de signo sin cambiar de sujeto.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from fiber_ast_lint.cli import construir

RAIZ = Path(__file__).resolve().parents[1]
PRE_REGISTRO = RAIZ / "prediccion-batch-20.json"
CENSO = RAIZ / "censo-20-20261127.json"
RECIBO = RAIZ / "recibo-lote20-20261127.json"
SECCION_20 = "## The frontier returns a defect of the instrument"

SHA = re.compile(r"\b[0-9a-f]{40}\b")


def _cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_el_pre_registro_declara_los_dos_tramos_antes_de_medir() -> None:
    doc = _cargar(PRE_REGISTRO)
    assert doc["batch"] == 20
    assert doc["declared_before_computation"] is True
    universo = doc["universo"]
    assert set(universo) >= {"20A", "20B"}
    # El tramo ancho no es una lista recordada: es un procedimiento con parametros fijos.
    procedimiento = " ".join(universo["20B"].values())
    for licencia in ("mit", "apache-2.0", "bsd-3-clause"):
        assert licencia in procedimiento, licencia
    assert "cincuenta y doce mil kibibytes" in procedimiento
    assert "cinco resultados" in procedimiento
    assert "no la puede reproducir nadie" in procedimiento


def test_el_censo_congelado_tiene_cuarenta_y_ocho_filas() -> None:
    censo = _cargar(CENSO)
    assert censo["total_filas"] == 48
    assert len(censo["filtro_20A"]["repos_con_python"]) == 9
    assert len(censo["filtro_20A"]["repos_con_licencia"]) == 13


def test_python_y_licencia_son_disjuntos_y_el_tramo_estrecho_da_cero() -> None:
    """P1: el cuello de botella hacia afuera es el censo, no la precision del instrumento."""
    filtro = _cargar(CENSO)["filtro_20A"]
    assert filtro["con_ambas"] == 0
    assert filtro["con_ambas"] <= 3
    # Recomputado desde las filas, no leido del resumen: el resumen podria mentir.
    filas = _cargar(CENSO)["filas"]
    assert len(filas) == 48
    legales = [f["repo"] for f in filas
               if f["python_en_lenguajes"] and f["spdx"] not in (None, "NOASSERTION")]
    assert legales == filtro["repos_con_python_y_licencia"]
    assert sorted(f["repo"] for f in filas if f["python_en_lenguajes"]) == filtro["repos_con_python"]


def test_el_tramo_ancho_se_disparo_y_su_filtro_de_tamano_excluyo_seis() -> None:
    tramo = _cargar(CENSO)["tramo_20B"]
    assert tramo["disparado"] is True
    todos = [i for busqueda in tramo["resultados"].values() for i in busqueda["items"]]
    assert len(todos) == 15
    elegibles = [i for i in todos if i["kib"] <= tramo["tope_kib"]]
    assert len(elegibles) == 9
    # El filtro se paga solo: la busqueda devuelve repositorios declarados de gigabytes.
    assert max(i["kib"] for i in todos) > 10 * tramo["tope_kib"]


def test_los_nueve_sujetos_escaneados_declaran_sha_y_no_un_relleno() -> None:
    """P4: un candidato sin sha no es citable por un tercero, es una frase."""
    sujetos = _cargar(CENSO)["escaneo"]["sujetos"]
    assert len(sujetos) == 9
    for sujeto in sujetos:
        assert SHA.fullmatch(sujeto["sha"]), sujeto["repo"]
        assert set(sujeto["sha"]) != {"0"}, sujeto["repo"]


def test_la_tasa_de_cardinal_sin_medir_supera_la_mitad() -> None:
    """P3: el instrumento no dispara por estilo; dispara donde nadie mira la cardinalidad."""
    escaneo = _cargar(CENSO)["escaneo"]
    almacenes = sum(s["almacenes"] for s in escaneo["sujetos"])
    tasa = escaneo["sin_len"] / almacenes
    assert almacenes == 251
    assert escaneo["sin_len"] == 187
    assert tasa > 0.5


def test_el_censo_y_el_recibo_se_citan_por_su_digest() -> None:
    """Triangulo del lote 16: el recibo no puede citar un censo que no es el del arbol."""
    recibo = _cargar(RECIBO)
    assert recibo["censo"]["sha256"] == _sha(CENSO)
    assert recibo["pre_registro"]["sha256"] == _sha(PRE_REGISTRO)


def test_ningun_locus_se_publica_sin_haberse_leido() -> None:
    """El acto externo no es el barrido: es la lectura. Cinco de seis refutan al instrumento
    clavado en el sujeto, y el sexto acusa al instrumento. Cero reportes abiertos."""
    revision = _cargar(RECIBO)["revision"]
    assert revision["candidatos"] == 27
    assert revision["loci_productivos_distintos"] == 6
    assert revision["loci_leidos"] == revision["loci_productivos_distintos"]
    assert revision["loci_sin_leer_en_rutas_productivas"] == 0
    for locus in revision["loci"]:
        assert locus["razon"].strip(), locus["loci"]
        assert locus["veredicto"] in {"REFUTADO_COMO_DEFECTO_DEL_SUJETO",
                                      "DEFECTO_DEL_INSTRUMENTO"}
    supervivientes = [x for x in revision["loci"]
                      if x["veredicto"] == "DEFECTO_DEL_INSTRUMENTO"]
    assert len(supervivientes) == 1
    assert _cargar(RECIBO)["no_se_hizo"]["reportes_abiertos"] == 0


def test_el_testigo_hermano_solo_cuenta_si_alguien_lo_alimenta(tmp_path: Path) -> None:
    """Deuda del lote 20, pagada: el testigo hermano se ve, la lista blanca no.

    El instrumento sabia ver `if key in acc`, solo sobre el propio acumulador. El codigo real
    vigila la colision con un conjunto hermano del mismo espacio de claves, y una escritura
    flota sobre el mismo `out[k]`. Lo que separa vigilar de no mirar no es el nombre del
    testigo sino la escritura que lo alimenta: `lista_blanca` consulta un conjunto fijo que el
    bucle nunca crece, asi que la clave sigue pisando al inquilino anterior.
    """
    (tmp_path / "dos.py").write_text(
        "PERMITIDOS = {'a', 'b'}\n"
        "\n"
        "\n"
        "def hermano(rows):\n"
        "    out = {}\n"
        "    seen = set()\n"
        "    for r in rows:\n"
        "        k = r.name.lower()\n"
        "        if k in seen:\n"
        "            continue\n"
        "        seen.add(k)\n"
        "        out[k] = r\n"
        "    return out\n"
        "\n"
        "\n"
        "def lista_blanca(rows):\n"
        "    out = {}\n"
        "    for r in rows:\n"
        "        k = r.name.lower()\n"
        "        if k not in PERMITIDOS:\n"
        "            continue\n"
        "        out[k] = r\n"
        "    return out\n"
        "\n"
        "\n"
        "def len_propio(rows):\n"
        "    out = {}\n"
        "    for r in rows:\n"
        "        out[r.name.lower()] = r\n"
        "    if len(out) != len(rows):\n"
        "        raise ValueError('colapso')\n"
        "    return out\n"
        "\n"
        "\n"
        "def sin_testigo(rows):\n"
        "    out = {}\n"
        "    for r in rows:\n"
        "        out[r.name.lower()] = r\n"
        "    return out\n",
        encoding="utf-8",
    )
    r = construir(str(tmp_path), interproc=False)
    poblacion = {loc.fn: loc.poblacion for loc in r["analisis"].loci}
    assert poblacion["len_propio"] == "pierde"
    assert poblacion["sin_testigo"] == "cardinal_sin_medir"
    # Lo que se movio en el lote 21: el hermano deja de emitir locus y pasa a la
    # poblacion medida. El que consulta una lista fija se queda donde estaba.
    assert "hermano" not in poblacion
    assert poblacion["lista_blanca"] == "cardinal_sin_medir"
    assert r["analisis"].guardadas == 1


def test_el_readme_narra_el_acto_y_no_solo_lo_anuncia() -> None:
    lineas = (RAIZ / "README.md").read_text(encoding="utf-8").splitlines()
    dentro = False
    cuerpo: list[str] = []
    for linea in lineas:
        if linea.startswith(SECCION_20):
            dentro = True
            continue
        if dentro and linea.startswith("## "):
            break
        if dentro:
            cuerpo.append(linea)
    texto = "\n".join(cuerpo)
    assert texto.strip(), f"falta la seccion {SECCION_20!r}"
    for cifra in ("48", "0", "187", "27"):
        assert cifra in texto, cifra
