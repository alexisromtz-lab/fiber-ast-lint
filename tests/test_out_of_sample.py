"""The three shapes of the out-of-sample population, recomputed offline.

`H_out_of_sample` in the README adjudicates three candidates found in `pyflakes`,
`flake8` and `black`. Two of those adjudications rest on a severity split that no
reader can check without downloading three wheels, so the shapes are distilled
here: same store, same key family, same escape, and nothing else. If a rule
change ever moves `CANDIDATO`, `LATENTE` and "no store" apart, this fails before
a release note can call the move an improvement.

The second half pins the published table against `censo.json`, so the three rows
cannot drift away from the artifact they claim to describe.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fiber_ast_lint.cli import construir

RAIZ = Path(__file__).resolve().parents[1]
README = (RAIZ / "README.md").read_text(encoding="utf-8")
CENSO = json.loads((RAIZ / "censo.json").read_text(encoding="utf-8"))

# flake8 7.5.0, flake8/plugins/finder.py:327 -- the accumulator escapes and
# nobody measures its cardinal, so the loss can reach a consumer.
CANDIDATO_ESCAPA = '''\
class Plugins:
    def __init__(self, reporters):
        self.reporters = reporters


def classify(plugins):
    reporters = {}
    for loaded in plugins:
        reporters[loaded.entry_name] = loaded
    return Plugins(reporters)


def load_plugins(plugins):
    return classify(plugins)
'''

# black 26.10.1, black/parsing.py:113 -- same shape, but the accumulator is
# local and its only observer is max(), so no consumer can be reached.
LATENTE_LOCAL = '''\
def parse(grammars, src):
    errors = {}
    for grammar in grammars:
        try:
            return grammar.parse(src)
        except ValueError:
            errors[grammar.version] = "invalid"
    assert len(errors) >= 1
    raise errors[max(errors)]
'''

# pyflakes 4.1.0 -- the write goes through the loop target, not into an
# accumulator. This is the zero that must stay a zero.
SIN_ALMACEN = '''\
def bind(scopes, name, value):
    for scope in scopes:
        scope[name] = value
'''


def _analizar(tmp_path: Path, nombre: str, fuente: str) -> dict:
    ruta = tmp_path / f"{nombre}.py"
    ruta.write_text(fuente, encoding="utf-8")
    return construir(str(ruta))


def test_una_proyeccion_que_escapa_se_admite(tmp_path):
    d = _analizar(tmp_path, "candidato", CANDIDATO_ESCAPA)
    assert d["almacenes"] == 1 and d["reconcilia"] is True
    (c,) = d["candidatos"]
    assert c["clave"] == "loaded.entry_name"
    assert c["forma"] == "SELECCION_COLUMNA_BUCLE"
    assert c["escapa"] is True and c["llamadas"] == 1
    assert c["severidad"] == "CANDIDATO"


def test_una_proyeccion_local_se_queda_latente(tmp_path):
    d = _analizar(tmp_path, "latente", LATENTE_LOCAL)
    assert d["almacenes"] == 1 and d["reconcilia"] is True
    (c,) = d["candidatos"]
    assert c["clave"] == "grammar.version"
    assert c["escapa"] is False and c["poblacion"] == "pierde"
    assert c["severidad"] == "LATENTE"


def test_escribir_a_traves_del_objetivo_no_es_un_almacen(tmp_path):
    d = _analizar(tmp_path, "sin_almacen", SIN_ALMACEN)
    assert d["almacenes"] == 0
    assert d["candidatos"] == []


def _tabla_agregada() -> dict[str, list[str]]:
    lineas = README.splitlines()
    inicio = next(i for i, l in enumerate(lineas) if l.startswith("| project | version |"))
    filas: dict[str, list[str]] = {}
    for linea in lineas[inicio + 1:]:
        if not linea.startswith("|"):
            break
        celdas = [c.strip().replace("**", "").replace("`", "")
                  for c in linea.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in celdas) or celdas[0] == "added":
            continue
        filas[celdas[0]] = celdas
    return filas


def test_la_tabla_de_fuera_de_muestra_dice_lo_que_dice_el_censo():
    filas = _tabla_agregada()
    assert set(filas) == set(CENSO["out_of_sample"]["packages"])
    for package, (_, version, files, stores, cand, adm, reconciles) in filas.items():
        r = next(x for x in CENSO["rows"] if x["package"] == package)
        assert re.sub(r"\s", "", version) == r["version"], package
        assert (int(files), int(stores), int(cand), int(adm)) == (
            r["files"], r["stores"], r["candidates"], r["admitted"]), package
        assert (reconciles == "yes") is r["reconciles"], package
