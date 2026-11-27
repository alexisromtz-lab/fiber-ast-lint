"""El instrumento cruzando la frontera: mide su propio alcance sobre codigo ajeno.

El lote 19 gasta el primer acto hacia afuera y el resultado no es un hallazgo sobre el
sujeto. Es una medida sobre el instrumento: de cinco almacenes del sujeto, cuatro tienen
la cardinal sin medir, y la clase ``cardinal_sin_medir`` no significa "el instrumento no
pudo": significa "nadie llama ``len`` en el ambito, la perdida es invisible incluso para
el programa". La regla fuerte solo ve una perdida cuando el sujeto ya la vigila.

Un cero sobre codigo ajeno es entonces la interseccion entre los almacenes del sujeto y
los almacenes que el sujeto mide. Publicarlo sin esa interseccion es el falso verde en la
direccion peligrosa que el lote 18 nombro.

El par que lo fija se ejercita aqui sin red: el mismo instrumento, dos universos, uno con
testigo y otro sin el.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RECIBO = RAIZ / "recibo-externo-20261127.json"
SECCION_19 = "## The instrument measures its own reach before it measures anyone else"

SHA = re.compile(r"^[0-9a-f]{40}$")


def _recibo() -> dict:
    return json.loads(RECIBO.read_text(encoding="utf-8"))


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(RAIZ), *args], capture_output=True, text=True
    )


def test_el_recibo_nombra_sus_dos_sujetos_con_sha_completo() -> None:
    """Un recibo externo sin sha del instrumento no dice con que version se midio."""
    doc = _recibo()
    assert SHA.match(doc["instrumento"]["sha"]), doc["instrumento"]["sha"]
    assert SHA.match(doc["sujeto"]["sha"]), doc["sujeto"]["sha"]
    assert doc["instrumento"]["dependencias"] == [], (
        "una dependencia externa hace que un tercero no pueda reproducir el acto en un comando"
    )


def test_el_sha_del_instrumento_existe_en_este_repositorio() -> None:
    """La mitad verificable sin red: el recibo no puede citar una version que nunca existio.

    La otra mitad —que el sujeto siga en el sha medido— necesita red y no se comprueba aqui.
    Se declara NO_MEDIDO en el recibo en lugar de darse por buena.
    """
    sha = _recibo()["instrumento"]["sha"]
    existe = _git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0
    assert existe, f"el recibo cita el commit {sha}, que no esta en este repositorio"


def test_el_sha_del_sujeto_no_es_un_relleno() -> None:
    """Un sha de cuarenta ceros cumple el formato y no nombra a nadie.

    El sha del sujeto no se puede re-verificar sin red, asi que lo unico que se puede exigir
    aqui es que no sea un relleno: ni constante, ni el del propio instrumento.
    """
    doc = _recibo()
    sha_sujeto = doc["sujeto"]["sha"]
    assert len(set(sha_sujeto)) > 1, "el sha del sujeto es constante"
    assert sha_sujeto != doc["instrumento"]["sha"], "el sujeto y el instrumento no son el mismo"


def test_el_sujeto_sin_licencia_no_publica_loci() -> None:
    """Publicar una ruta interna de un sujeto sin licencia es redistribuir su codigo.

    La ley del lote 17 exige locus; la ausencia de licencia lo prohibe. La tension se
    declara, y este test impide que alguien la resuelva anadiendo el locus de todos modos.
    """
    doc = _recibo()
    assert doc["permiso"]["estado"] == "NO_MEDIDO_POR_FALTA_DE_LICENCIA"
    crudo = RECIBO.read_text(encoding="utf-8")
    assert ".py:" not in crudo, "el recibo publica un locus del sujeto"
    assert "def " not in crudo, "el recibo reproduce codigo del sujeto"


def test_la_conservacion_del_recibo_suma_y_declara_lo_no_medido() -> None:
    """La identidad del censo tiene que cerrar tambien fuera de casa."""
    m = _recibo()["medicion"]
    suma = (
        m["pierde"] + m["guardadas"] + m["acumulacion"] + m["posicional"]
        + m["cardinal_sin_medir"]
    )
    assert m["almacenes"] == suma, (m["almacenes"], suma)
    assert m["candidatos_admitidos"] == 0, "si aparecio un candidato, el veredicto P2 cambia"
    assert m["cardinal_sin_medir"] > 0, (
        "si el sujeto midiera sus cardinales, el hallazgo del acto no seria este"
    )


def test_un_almacen_sin_testigo_no_emite_candidato_y_uno_con_testigo_si(
    tmp_path: Path,
) -> None:
    """El par que sostiene la lectura: la diferencia no es el codigo, es quien mira.

    El primer universo es un dict indexado en un bucle donde nadie llama ``len``: el
    instrumento lo cuenta como almacen y no puede decir si pierde, asi que calla. El
    segundo son los fixtures del arbol, escritos con testigo y con llamada, y ahi si
    admite. Mismo instrumento, misma regla, distinto observador.
    """
    from fiber_ast_lint.cli import construir, rc_de

    sin_testigo = tmp_path / "sin_testigo"
    sin_testigo.mkdir()
    (sin_testigo / "m.py").write_text(
        'def f(filas):\n'
        '    d = {}\n'
        '    for r in filas:\n'
        '        d[r["k"]] = r\n'
        '    return d\n',
        encoding="utf-8",
    )
    mudo = construir(str(sin_testigo), interproc=False)
    assert mudo["almacenes"] >= 1
    assert mudo["sin_len"] >= 1
    assert mudo["analisis"].admitidos == []
    assert rc_de(mudo["analisis"]) == 0

    con_testigo = construir(str(RAIZ / "tests" / "fixtures"), interproc=False)
    assert len(con_testigo["analisis"].admitidos) >= 1
    assert rc_de(con_testigo["analisis"]) == 1


def test_el_readme_publica_la_medida_del_acto_y_su_lectura() -> None:
    """La cifra que justifica el acto externo tiene que estar escrita, no solo medida."""
    lineas: list[str] = []
    dentro = False
    for linea in (RAIZ / "README.md").read_text(encoding="utf-8").splitlines():
        if linea.startswith(SECCION_19):
            dentro = True
            continue
        if dentro and linea.startswith("## "):
            break
        if dentro:
            lineas.append(linea)
    seccion = "\n".join(lineas)
    assert seccion, f"el README no publica la seccion `{SECCION_19}`"
    m = _recibo()["medicion"]
    assert f"`{m['almacenes']}`" in seccion, m["almacenes"]
    assert f"`{m['cardinal_sin_medir']}`" in seccion, m["cardinal_sin_medir"]
