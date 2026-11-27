"""Las dos predicciones con sujeto tienen veredicto, y el veredicto depende de una direccion.

El lote 17 publico que cincuenta y cinco de las cincuenta y siete predicciones historicas no
nombran un fichero ni un comando. Las dos que si lo nombran se quedaron sin reconciliar, y
una de ellas tenia test verde desde el dia que se escribio. Ese verde no decia que la promesa
fuera cierta: decia que el instrumento no habia encontrado nada dentro de su alcance.

Aqui se mide la diferencia entre esos dos alcances, que es lo que un tercero necesita para
reconciliar la promesa. La regla es una sola y tiene direccion:

    si el alcance del instrumento contiene al de la promesa, un verde es seguro    (medir de mas)
    si el alcance de la promesa contiene al del instrumento, un verde no concluye (medir de menos)

Y la unica combinacion que este fichero prohibe es la que no admite discusion: una promesa
mas ancha que su instrumento no puede publicarse como SOBREVIVE.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SELLO = RAIZ / "reconciliacion-batch-18.json"
SUJETO = RAIZ / "bench" / "recibo.py"

VEREDICTOS = ("SOBREVIVE", "CAE")
DIRECCIONES = ("instrumento_mas_ancho", "promesa_mas_ancha")

# El instrumento que mide «una rama consulta el identificador». Es el mismo regex que usa
# test_r1 en tests/test_recibo.py, a proposito: si se cambiara aqui, la comparacion de
# alcances mediria dos cosas distintas y la diferencia dejaria de significar lo que dice.
RAMA_POR_NOMBRE = re.compile(r"\b(pid|id)\b\s*(==|!=|in\b|not\s+in\b)")


def _sello() -> dict:
    return json.loads(SELLO.read_text(encoding="utf-8"))


def _fuente() -> str:
    return SUJETO.read_text(encoding="utf-8")


def _cuerpo(fuente: str, funcion: str) -> str:
    """El texto de una funcion hasta la siguiente definicion de primer nivel."""
    return fuente.split(f"def {funcion}", 1)[1].split("\ndef ", 1)[0]


def _entrada(pid: str) -> dict:
    entradas = {e["id"]: e for e in _sello()["reconciliaciones"]}
    assert pid in entradas, f"el sello no reconcilia {pid}"
    return entradas[pid]


# --- P2: cero comparaciones de un nombre que contenga lote contra una constante entera ---


def _comparaciones_lote_contra_entero() -> list[str]:
    arbol = ast.parse(_fuente())
    hallazgos: list[str] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Compare):
            continue
        operandos = [nodo.left, *nodo.comparators]
        nombra_lote = any("lote" in ast.unparse(o) for o in operandos)
        contra_entero = any(
            isinstance(o, ast.Constant) and isinstance(o.value, int) for o in operandos
        )
        if nombra_lote and contra_entero:
            hallazgos.append(ast.unparse(nodo))
    return hallazgos


def _comparaciones_totales() -> int:
    return sum(1 for n in ast.walk(ast.parse(_fuente())) if isinstance(n, ast.Compare))


# --- R1: cuantas ramas consultan el identificador, y en que alcance ---


def _ramas_que_consultan_pid(alcance: str) -> int:
    return len(RAMA_POR_NOMBRE.findall(alcance))


def test_p2_su_instrumento_es_mas_ancho_que_la_promesa_y_el_veredicto_se_recomputa() -> None:
    """La promesa acota a if/match/ternario; el instrumento recorre todo ast.Compare."""
    entrada = _entrada("P2")
    hallazgos = _comparaciones_lote_contra_entero()
    assert hallazgos == [], hallazgos
    assert entrada["direccion"] == "instrumento_mas_ancho"
    assert entrada["medicion"]["comparaciones_lote_contra_entero"] == len(hallazgos)
    assert entrada["medicion"]["comparaciones_totales_del_fichero"] == _comparaciones_totales()
    assert entrada["veredicto"] == ("SOBREVIVE" if not hallazgos else "CAE")


def test_r1_su_promesa_es_mas_ancha_que_su_instrumento_y_por_eso_cae() -> None:
    """El mismo instrumento, dos alcances: el fichero entero y el cuerpo de _veredictos_v3.

    El test del lote 14 recorre el cuerpo de _veredictos_v3 y acierta: ahi no hay ninguna
    rama por identificador, y su propio comentario afirma que la rama de _ausencia si existe.
    La promesa hablaba de recibo.py entero. La diferencia entre los dos numeros es el
    hallazgo, y por eso el veredicto es CAE y no un matiz.
    """
    entrada = _entrada("R1")
    fuente = _fuente()
    en_el_fichero = _ramas_que_consultan_pid(fuente)
    en_el_instrumento = _ramas_que_consultan_pid(_cuerpo(fuente, "_veredictos_v3"))
    assert en_el_instrumento == 0, "el test del lote 14 dejaria de pasar"
    assert en_el_fichero > en_el_instrumento, (en_el_fichero, en_el_instrumento)
    assert entrada["direccion"] == "promesa_mas_ancha"
    assert entrada["medicion"]["ramas_que_consultan_pid_en_bench_recibo_py"] == en_el_fichero
    assert entrada["medicion"]["ramas_que_consultan_pid_en_el_cuerpo_de_veredictos_v3"] == 0
    assert entrada["veredicto"] == "CAE"
    assert entrada["mitades"]["ninguna_rama_de_recibo_py_nombra_un_id_para_decidir"] == "CAE"
    assert entrada["mitades"]["dos_ids_misma_forma_mismo_sobrevive"] == "SOBREVIVE"


def test_el_punto_que_decide_sobrevive_por_id_sigue_donde_el_sello_dice() -> None:
    """El falsador de R1 no se cumple por una rama cualquiera: se cumple aqui."""
    fuente = _fuente()
    assert "EVALUADORES.get(" in _cuerpo(fuente, "_evaluar")
    assert "_evaluar(pid" in _cuerpo(fuente, "_veredictos_v2")
    assert _entrada("R1")["medicion"]["punto_que_decide_sobrevive_por_id"].startswith(
        "bench/recibo.py:325"
    )


# --- la ley de direccion ---------------------------------------------------------------


def _violaciones_de_direccion(entradas: list[dict]) -> list[str]:
    """La unica combinacion prohibida: promesa mas ancha y veredicto verde."""
    return [
        str(e.get("id"))
        for e in entradas
        if e.get("direccion") == "promesa_mas_ancha" and e.get("veredicto") == "SOBREVIVE"
    ]


def test_una_promesa_mas_ancha_no_puede_publicar_sobrevive() -> None:
    """La ley muerde sobre entradas construidas: hoy el arbol tiene una sola de cada clase."""
    assert _violaciones_de_direccion(_sello()["reconciliaciones"]) == []
    peligrosa = {"id": "X", "direccion": "promesa_mas_ancha", "veredicto": "SOBREVIVE"}
    segura = {"id": "Y", "direccion": "instrumento_mas_ancho", "veredicto": "SOBREVIVE"}
    caida = {"id": "Z", "direccion": "promesa_mas_ancha", "veredicto": "CAE"}
    assert _violaciones_de_direccion([peligrosa, segura, caida]) == ["X"]


def test_toda_entrada_declara_una_direccion_conocida_y_un_veredicto_conocido() -> None:
    for entrada in _sello()["reconciliaciones"]:
        assert entrada["direccion"] in DIRECCIONES, entrada["id"]
        assert entrada["veredicto"] in VEREDICTOS, entrada["id"]
        assert entrada.get("por_que"), f"{entrada['id']} declara direccion sin decir por que"


# --- el sello nombra su sujeto y nombra su instrumento ---------------------------------


def _tests_del_arbol() -> set[str]:
    nombres: set[str] = set()
    for ruta in sorted((RAIZ / "tests").glob("test_*.py")):
        nombres |= set(re.findall(r"^def (test_\w+)", ruta.read_text(encoding="utf-8"), re.M))
    return nombres


def test_cada_reconciliacion_nombra_un_test_que_existe() -> None:
    """Un veredicto que cita un instrumento inexistente no se puede recomputar."""
    existentes = _tests_del_arbol()
    for entrada in _sello()["reconciliaciones"]:
        ruta, _, nombre = entrada["instrumento"].partition("::")
        assert (RAIZ / ruta).is_file(), ruta
        assert nombre in existentes, (entrada["id"], nombre)


def test_el_sello_nombra_su_sujeto_y_caduca_cuando_el_sujeto_se_mueve() -> None:
    """Un veredicto sobre un fichero que se mueve sin decir sobre que version se midio es prosa."""
    sujeto = _sello()["sujeto"]
    crudo = SUJETO.read_bytes()
    reemitir = "python tests/test_reconciliacion.py --emitir"
    assert sujeto["bytes"] == len(crudo), f"el sujeto cambio: reemitir con `{reemitir}`"
    assert sujeto["sha256"] == hashlib.sha256(crudo).hexdigest(), (
        f"el sujeto cambio: reemitir con `{reemitir}`"
    )


def test_el_censo_heredado_del_sello_es_el_que_mide_el_censo() -> None:
    """El sello publica la deuda; si el censo se mueve, el sello no puede seguir diciendo lo mismo."""
    from test_prediccion_locus import _censo

    censo = _censo()
    heredadas = _sello()["heredadas"]
    for clase in ("con_locus", "umbral_sin_locus", "sin_falsador", "total"):
        assert heredadas[clase] == censo[clase], clase


# --- la tabla del README es el sello, no una copia suya ---------------------------------

SECCION_18 = "## A promise and its instrument are not the same set"


def _seccion_18() -> str:
    """El cuerpo de la seccion, no el fichero: la misma cifra puede salir en otra parte."""
    lineas: list[str] = []
    dentro = False
    for linea in (RAIZ / "README.md").read_text(encoding="utf-8").splitlines():
        if linea.startswith(SECCION_18):
            dentro = True
            continue
        if dentro and linea.startswith("## "):
            break
        if dentro:
            lineas.append(linea)
    assert lineas, f"el README no publica la seccion `{SECCION_18}`"
    return "\n".join(lineas)


def test_el_readme_publica_las_dos_reconciliaciones_y_no_una_copia() -> None:
    """Dos fuentes divergen. La tabla del README se compara celda a celda contra el sello."""
    publicadas = {
        pid: (direccion, veredicto)
        for pid, direccion, veredicto in re.findall(
            r"^\| `(\w+)` \| `(\w+)` \| `(\w+)` \|$", _seccion_18(), re.M
        )
    }
    del_sello = {e["id"]: (e["direccion"], e["veredicto"]) for e in _sello()["reconciliaciones"]}
    assert publicadas, "la seccion no publica ninguna reconciliacion"
    assert publicadas == del_sello, (publicadas, del_sello)


def test_el_readme_nombra_las_dos_direcciones_que_el_sello_declara() -> None:
    """Una direccion que nadie ejemplifica es una definicion sin sujeto."""
    seccion = _seccion_18()
    for clase in _sello()["direcciones"]:
        assert f"`{clase}`" in seccion, clase


def _emitir() -> int:
    """Re-mide el sello: el sujeto, los dos recuentos y el censo. El veredicto es un conteo."""
    import datetime

    doc = _sello()
    crudo = SUJETO.read_bytes()
    doc["sujeto"] = {
        "archivo": "bench/recibo.py",
        "sha256": hashlib.sha256(crudo).hexdigest(),
        "bytes": len(crudo),
        "lineas": crudo.count(b"\n"),
    }
    fuente = _fuente()
    en_el_fichero = _ramas_que_consultan_pid(fuente)
    for entrada in doc["reconciliaciones"]:
        if entrada["id"] == "P2":
            hallazgos = _comparaciones_lote_contra_entero()
            entrada["medicion"]["comparaciones_lote_contra_entero"] = len(hallazgos)
            entrada["medicion"]["comparaciones_totales_del_fichero"] = _comparaciones_totales()
            entrada["veredicto"] = "SOBREVIVE" if not hallazgos else "CAE"
        elif entrada["id"] == "R1":
            entrada["medicion"]["ramas_que_consultan_pid_en_bench_recibo_py"] = en_el_fichero
            entrada["medicion"]["ramas_que_consultan_pid_en_el_cuerpo_de_veredictos_v3"] = (
                _ramas_que_consultan_pid(_cuerpo(fuente, "_veredictos_v3"))
            )
            decide_por_id = "EVALUADORES.get(" in _cuerpo(fuente, "_evaluar")
            entrada["veredicto"] = "CAE" if en_el_fichero or decide_por_id else "SOBREVIVE"
            entrada["mitades"]["ninguna_rama_de_recibo_py_nombra_un_id_para_decidir"] = (
                "CAE" if en_el_fichero else "SOBREVIVE"
            )
    from test_prediccion_locus import _censo

    doc["heredadas"].update({k: v for k, v in _censo().items()})
    doc["fecha"] = datetime.date.today().isoformat()
    SELLO.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"reemitido {SELLO.name} con fecha {doc['fecha']}")
    return 0


if __name__ == "__main__":
    sys.exit(_emitir() if "--emitir" in sys.argv else 0)
