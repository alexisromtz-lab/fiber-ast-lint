"""El falsador tiene umbral y no tiene sujeto: una prediccion sin locus no se puede reconciliar.

Los quince pre-registros del arbol declaran cincuenta y siete predicciones con su falsador
escrito y sin casilla donde escribir si se cumplieron. Ese hueco tiene una causa medible, y
no es la que parecia: el registro si sabe *cuando* muere una prediccion —treinta y seis de
las cincuenta y siete fijan un umbral— y no sabe *donde* muere, porque dos de las cincuenta
y siete nombran un fichero. Un umbral sin locus es una cifra sin sujeto, que es exactamente
lo que la primera regla de conducta del corpus prohibe... y que el corpus nunca se aplico a
si mismo. Un tercero no puede recomputar la muerte de una prediccion que no dice sobre que
fichero se mide.

El lote 17 no rellena ningun resultado historico: mide el hueco, lo publica con lector y lo
cierra hacia adelante. `prediccion-batch-17.json` es la ley y su primer cumplidor; los lotes
dos a dieciseis quedan como estan, en NO_MEDIDO declarado y no en cero.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# El primer lote obligado a declarar locus. La ley entra en vigor en el fichero que la
# declara, y el censo mide los anteriores: un pre-registro no se reescribe al dictar la ley.
PRIMER_LOTE_CON_LOTUS = 17
ULTIMO_LOTE_CENSADO = 16

# Un falsador tiene sujeto cuando nombra un fichero o un comando. El patron no adivina: una
# ruta bajo el arbol, un nombre de fichero con extension, o una invocacion de git o pytest.
PATRON_LOTUS = re.compile(
    r"\b(?:tests|tools|bench|src)/[\w./-]+"
    r"|\b[\w-]+\.(?:json|py|md|txt|html|sh|toml)\b"
    r"|\b(?:git|pytest)\s+\w"
)

SECCION_17 = "## A falsifier without a locus is a threshold with no subject"


def _batch_de(ruta: Path, doc: dict) -> int | None:
    """El lote del pre-registro: el campo si lo declara, el nombre del fichero si no.

    Tres de los quince pre-registros (`prediccion-batch-2`, `-3`, `-4`) no declaran `batch`,
    y filtrar solo por el campo habria publicado cuarenta y cuatro predicciones donde hay
    cincuenta y siete. El nombre del fichero es parte del artefacto: se lee, no se supone.
    """
    if isinstance(doc.get("batch"), int):
        return doc["batch"]
    match = re.fullmatch(r"prediccion-batch-(\d+)\.json", ruta.name)
    return int(match.group(1)) if match else None


def _pre_registros(techo: int) -> list[tuple[Path, dict]]:
    """Los pre-registros con lote declarado o deducible y no mayor que el techo."""
    salida: list[tuple[Path, dict]] = []
    for ruta in sorted(RAIZ.glob("prediccion-batch-*.json")):
        doc = json.loads(ruta.read_text(encoding="utf-8"))
        lote = _batch_de(ruta, doc)
        if lote is not None and lote <= techo:
            salida.append((ruta, doc))
    return salida


def _falsador(prediccion: dict) -> str:
    return str(prediccion.get("falsifier") or prediccion.get("falsador") or "").strip()


def _locus_declarado(prediccion: dict) -> str:
    """El locus como dato: cadena, o mapa de cadenas. Vacio si no declara nada."""
    valor = prediccion.get("locus")
    if isinstance(valor, str):
        return valor.strip()
    if isinstance(valor, dict):
        return " ".join(str(v) for v in valor.values()).strip()
    return ""


def _clase(prediccion: dict) -> str:
    """Tres clases disjuntas. `con_locus` exige sujeto, no prosa."""
    if not _falsador(prediccion):
        return "sin_falsador"
    if _locus_declarado(prediccion) or PATRON_LOTUS.search(_falsador(prediccion)):
        return "con_locus"
    return "umbral_sin_locus"


def _censo() -> dict[str, int]:
    censo = {"con_locus": 0, "umbral_sin_locus": 0, "sin_falsador": 0}
    for _ruta, doc in _pre_registros(ULTIMO_LOTE_CENSADO):
        for prediccion in doc["predictions"]:
            censo[_clase(prediccion)] += 1
    censo["total"] = sum(censo.values())
    return censo


def _faltan_locus(lote: int | None, doc: dict) -> list[str]:
    """Ids de las predicciones que incumplen la ley. Un lote anterior a la ley no incumple."""
    if lote is None or lote < PRIMER_LOTE_CON_LOTUS:
        return []
    return [p["id"] for p in doc.get("predictions", []) if not _locus_declarado(p)]


def _seccion_17() -> list[str]:
    dentro = False
    salida: list[str] = []
    for linea in (RAIZ / "README.md").read_text(encoding="utf-8").splitlines():
        if linea.startswith(SECCION_17):
            dentro = True
            continue
        if dentro and linea.startswith("## "):
            break
        if dentro:
            salida.append(linea)
    assert salida, f"el README no publica la seccion `{SECCION_17}`"
    return salida


def test_el_pre_registro_del_lote_17_se_declaro_antes_de_medir() -> None:
    doc = json.loads((RAIZ / "prediccion-batch-17.json").read_text(encoding="utf-8"))
    assert doc["declared_before_computation"] is True
    assert doc["batch"] == PRIMER_LOTE_CON_LOTUS
    assert [p["id"] for p in doc["predictions"]] == ["P1", "P2"]
    assert doc["cost"]["relojes_nuevos"] == 0


def test_el_censo_de_falsadores_es_el_que_el_readme_publica() -> None:
    """Un censo que solo vive en el test es una cifra creida; el numero tiene que estar escrito."""
    censo = _censo()
    publicados = {
        clase: int(n)
        for clase, n in re.findall(r"\| `(\w+)` \| (\d+) \|", "\n".join(_seccion_17()))
    }
    assert publicados, "la seccion no publica ninguna clase del censo"
    recomputado = {k: censo[k] for k in publicados}
    assert publicados == recomputado, (publicados, recomputado)


def test_ningun_falsador_historico_declara_locus_como_dato() -> None:
    """El hecho que abre el lote: el locus es prosa, no campo, en los cincuenta y siete."""
    sin_campo = [
        (ruta.name, p["id"])
        for ruta, doc in _pre_registros(ULTIMO_LOTE_CENSADO)
        for p in doc["predictions"]
        if _locus_declarado(p)
    ]
    assert sin_campo == [], (
        "aparecio un locus como dato antes de que la ley existiera; "
        "eso cambia el diagnostico y hay que publicarlo, no ignorarlo"
    )


def test_el_validador_de_locus_grita_y_calla() -> None:
    """La rama que hoy no tiene sujeto se ejercita con documentos sinteticos.

    Un guardian que solo corre sobre un conjunto vacio devuelve verde por no mirar. Aqui
    la ley se prueba sobre tres casos que se construyen, no sobre el arbol de hoy.
    """
    con_locus = {"batch": 18, "predictions": [{"id": "X", "locus": "tests/test_cli.py:40"}]}
    sin_locus = {"batch": 18, "predictions": [{"id": "X", "claim": "algo"}]}
    historico = {"batch": 16, "predictions": [{"id": "X", "claim": "algo"}]}
    assert _faltan_locus(18, con_locus) == []
    assert _faltan_locus(18, sin_locus) == ["X"]
    assert _faltan_locus(16, historico) == []


def test_todo_lote_desde_el_diecisiete_declara_locus() -> None:
    """El trinquete sobre el arbol real. Hoy tiene un solo cumplidor y se nombra."""
    con_ley = [
        (ruta, doc)
        for ruta, doc in _pre_registros(10**6)
        if _batch_de(ruta, doc) >= PRIMER_LOTE_CON_LOTUS
    ]
    assert con_ley, "ningun pre-registro posterior a la ley: el trinquete no mide nada"
    defectos = {ruta.name: _faltan_locus(_batch_de(ruta, doc), doc) for ruta, doc in con_ley}
    assert {k: v for k, v in defectos.items() if v} == {}, defectos


def test_el_denominador_no_depende_del_campo_batch() -> None:
    """Tres pre-registros no declaran `batch` y filtrar por el campo perdia trece predicciones."""
    sin_campo = sorted(
        ruta.name
        for ruta in RAIZ.glob("prediccion-batch-*.json")
        if not isinstance(json.loads(ruta.read_text(encoding="utf-8")).get("batch"), int)
    )
    assert sin_campo == [
        "prediccion-batch-2.json", "prediccion-batch-3.json", "prediccion-batch-4.json"
    ], sin_campo
    incluidos = {ruta.name for ruta, _doc in _pre_registros(ULTIMO_LOTE_CENSADO)}
    assert set(sin_campo) <= incluidos, sorted(set(sin_campo) - incluidos)


def test_la_clasificacion_no_depende_del_orden_ni_de_la_clave() -> None:
    """`falsifier` y `falsador` son el mismo objeto con dos nombres; el censo no los separa."""
    ruta = RAIZ / "prediccion-batch-11.json"
    doc = json.loads(ruta.read_text(encoding="utf-8"))
    renombrado = {
        **doc,
        "predictions": [
            {("falsifier" if "falsador" in p else "falsador"): p.get("falsifier") or p.get("falsador"),
             **{k: v for k, v in p.items() if k not in ("falsifier", "falsador")}}
            for p in doc["predictions"]
        ],
    }
    assert [_clase(p) for p in doc["predictions"]] == [
        _clase(p) for p in renombrado["predictions"]
    ]
