"""The second pass: does anyone measure the cardinal one hop away?

The local pass says ``SIN_LEN`` when the ``len`` lives in another scope. That is
an honest "not measured here", not a zero; this pass closes the hop through the
call site, but only when the call site resolves to the *same* object. A bare
name is homonymy, not identity, and is published as its own population.
"""
from __future__ import annotations

from pathlib import Path

from fiber_ast_lint.graph import consumos

FIXTURES = Path(__file__).parent / "fixtures"
G = "grafo_consumidores"


def test_las_tres_formas_de_consumo(copia):
    raiz = copia("grafo_consumidores.py")
    out = consumos(raiz, {f"{G}::construir", f"{G}::llenar"})
    assert set(out.exactos) == {f"{G}::construir", f"{G}::llenar"}
    assert {c.forma for c in out.de(f"{G}::construir")} == {"VINCULO", "DIRECTO"}
    assert {c.forma for c in out.de(f"{G}::llenar")} == {"PARAMETRO"}
    directo = [c for c in out.de(f"{G}::construir") if c.forma == "DIRECTO"][0]
    assert directo.linea_llamada == directo.linea_consumo == 20
    assert directo.via == "EXACTO"


def test_un_len_anterior_a_la_llamada_no_es_consumidor(tmp_path):
    (tmp_path / "mod.py").write_text(
        "def productor(items):\n"
        "    acc = {}\n"
        "    for k in items:\n"
        "        acc[k.lower()] = k\n"
        "    return acc\n"
        "\n"
        "def antes(items):\n"
        "    n = len(items)\n"
        "    tabla = productor(items)\n"
        "    return tabla, n\n",
        encoding="utf-8",
    )
    assert consumos(tmp_path, {"mod::productor"}).de("mod::productor") == []


def test_llamada_sin_consumo_no_inventa_consumidor(copia):
    raiz = copia("grafo_consumidores.py")
    out = consumos(raiz, {"grafo_consumidores::consumidor_ausente"})
    assert out.exactos == {"grafo_consumidores::consumidor_ausente": []}


def test_sin_productores_no_recorre_nada(copia):
    assert consumos(copia("grafo_consumidores.py"), set()).exactos == {}


def test_ignora_directorios_de_terceros(tmp_path):
    interno = tmp_path / "__pycache__"
    interno.mkdir()
    (interno / "basura.py").write_text(
        "def productor(x):\n    return x\n\nprint(len(productor(1)))\n",
        encoding="utf-8",
    )
    assert consumos(tmp_path, {"basura::productor"}).de("basura::productor") == []


def test_el_consumidor_nombra_archivo_y_lineas(copia):
    raiz = copia("grafo_consumidores.py")
    c = consumos(raiz, {f"{G}::llenar"}).de(f"{G}::llenar")[0]
    assert c.archivo == "grafo_consumidores.py"
    assert (c.linea_llamada, c.linea_consumo) == (25, 26)
    assert "PARAMETRO" in str(c)


def test_ficheros_de_los_fixtures_cuentan_igual():
    """The fixture directory itself is a universe: three producers, three sites."""
    out = consumos(FIXTURES, {f"{G}::construir", f"{G}::llenar"})
    assert out.sitios_exactos == 3


# --------------------------------------------------------------------------- #
# Identity vs homonymy: the defect this pass exists to avoid
# --------------------------------------------------------------------------- #
def test_homonimia_no_atribuye_el_consumidor_ajeno(tmp_path):
    """Two ``medir`` in different modules are two objects, not one."""
    (tmp_path / "a.py").write_text(
        "def medir(items):\n"
        "    acc = {}\n"
        "    for k in items:\n"
        "        acc[k.lower()] = k\n"
        "    return acc\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "def medir(x):\n"
        "    return {i: i for i in x}\n"
        "\n"
        "def usa(x):\n"
        "    return len(medir(x))\n",
        encoding="utf-8",
    )
    out = consumos(tmp_path, {"a::medir"})
    assert out.de("a::medir") == []
    assert out.de("b::medir") == []
    # ``usa`` calls the ``b`` object: a resolved identity, not a producer, so it
    # is not homonymy either and must not be counted as a possible consumer.
    assert out.no_resueltos == 0


def test_import_nombrado_resuelve_la_identidad(tmp_path):
    (tmp_path / "a.py").write_text(
        "def medir(x):\n    return {i: i for i in x}\n", encoding="utf-8"
    )
    (tmp_path / "c.py").write_text(
        "from a import medir\n"
        "\n"
        "def usa(x):\n"
        "    return len(medir(x))\n",
        encoding="utf-8",
    )
    (tmp_path / "d.py").write_text(
        "from a import medir as m\n"
        "\n"
        "def usa(x):\n"
        "    return len(m(x))\n",
        encoding="utf-8",
    )
    out = consumos(tmp_path, {"a::medir"})
    assert [(c.archivo, c.forma) for c in out.de("a::medir")] == [
        ("c.py", "DIRECTO"), ("d.py", "DIRECTO")]


def test_atributo_de_modulo_importado_resuelve_la_identidad(tmp_path):
    (tmp_path / "a.py").write_text(
        "def medir(x):\n    return {i: i for i in x}\n", encoding="utf-8"
    )
    (tmp_path / "c.py").write_text(
        "import a\n"
        "\n"
        "def usa(x):\n"
        "    return len(a.medir(x))\n",
        encoding="utf-8",
    )
    out = consumos(tmp_path, {"a::medir"})
    assert [(c.archivo, c.forma) for c in out.de("a::medir")] == [("c.py", "DIRECTO")]


def test_metodo_de_clase_resuelve_la_identidad(tmp_path):
    (tmp_path / "k.py").write_text(
        "class Caja:\n"
        "    def medir(self, x):\n"
        "        return {i: i for i in x}\n"
        "\n"
        "def usa(box, x):\n"
        "    return len(Caja.medir(box, x))\n",
        encoding="utf-8",
    )
    out = consumos(tmp_path, {"k::Caja.medir"})
    assert [(c.archivo, c.forma) for c in out.de("k::Caja.medir")] == [("k.py", "DIRECTO")]


def test_nombre_no_resuelto_se_publica_como_poblacion_aparte(tmp_path):
    """A * import is not expanded: the name matches, the identity is unknown."""
    (tmp_path / "a.py").write_text(
        "def medir(x):\n    return {i: i for i in x}\n", encoding="utf-8"
    )
    (tmp_path / "e.py").write_text(
        "from a import *\n"
        "\n"
        "def usa(x):\n"
        "    return len(medir(x))\n",
        encoding="utf-8",
    )
    out = consumos(tmp_path, {"a::medir"})
    assert out.de("a::medir") == []
    assert out.no_resueltos == 1
    assert out.sitios_por_nombre == 1
    assert list(out.por_nombre) == ["medir"]


def test_una_llamada_a_self_resuelve_al_metodo_y_no_a_la_funcion_homonima(tmp_path):
    """The trap: a module function and a method share a name.

    ``mypy`` has exactly this shape (``applytype.apply_generic_arguments`` next to
    a method of the same name). A name-based rule would credit every ``self.``
    call to the module function; the enclosing class is read from the tree.
    """
    (tmp_path / "k.py").write_text(
        "def medir(x):\n"
        "    return {i: i for i in x}\n"
        "\n"
        "class Caja:\n"
        "    def medir(self, x):\n"
        "        return {i: i for i in x}\n"
        "\n"
        "    def usa(self, x):\n"
        "        tabla = self.medir(x)\n"
        "        return len(tabla)\n",
        encoding="utf-8",
    )
    out = consumos(tmp_path, {"k::medir", "k::Caja.medir"})
    assert [(c.forma, c.via) for c in out.de("k::Caja.medir")] == [("VINCULO", "SELF")]
    assert out.de("k::medir") == []
    assert out.sitios_por_nombre == 0
    assert out.no_resueltos == 0


def test_un_metodo_heredado_queda_sin_resolver(tmp_path):
    """Declared limit: the base class is not consulted, so the site stays unknown."""
    (tmp_path / "h.py").write_text(
        "class Base:\n"
        "    def medir(self, x):\n"
        "        return {i: i for i in x}\n"
        "\n"
        "class Hija(Base):\n"
        "    def usa(self, x):\n"
        "        return len(self.medir(x))\n",
        encoding="utf-8",
    )
    out = consumos(tmp_path, {"h::Base.medir"})
    assert out.de("h::Base.medir") == []
    assert out.sitios_por_nombre == 1
    assert list(out.por_nombre) == ["medir"]


def test_self_resuelto_sin_lector_es_conocido_y_no_es_consumo(tmp_path):
    """Identity is not a measurement: a resolved call with no ``len`` adds nothing."""
    (tmp_path / "k.py").write_text(
        "class Caja:\n"
        "    def medir(self, x):\n"
        "        return {i: i for i in x}\n"
        "\n"
        "    def usa(self, x):\n"
        "        return self.medir(x)\n",
        encoding="utf-8",
    )
    out = consumos(tmp_path, {"k::Caja.medir"})
    assert out.de("k::Caja.medir") == []
    assert out.sitios_llamada == 1
    assert out.sitios_por_self == 1
    assert out.sitios_por_nombre == 0


def test_una_llamada_self_a_un_metodo_ajeno_cuenta_pero_no_se_atribuye(tmp_path):
    """Identity known, verdict irrelevant: counted so the populations stay closed."""
    (tmp_path / "k.py").write_text(
        "class Caja:\n"
        "    def medir(self, x):\n"
        "        return {i: i for i in x}\n"
        "\n"
        "    def otro(self, x):\n"
        "        return len(x)\n"
        "\n"
        "    def usa(self, x):\n"
        "        return self.otro(x)\n",
        encoding="utf-8",
    )
    out = consumos(tmp_path, {"k::Caja.medir"})
    assert out.sitios_por_self == 0
    assert out.ajenas_por_self == 1
    assert out.sitios_por_nombre == 0
