"""Six keys in, four names out: a whitelist drawn from the codomain cannot help.

The shape is taken from the collision we measured in ``mypy/config_parser.py``
(six ini keys projected onto four reporter names, two collisions) and reduced to
a pure function so it can be asserted without installing mypy.
"""
INIFILE_KEYS = [
    "any-exprs",
    "any_exprs",
    "xslt-html",
    "xslt_html",
    "line-count",
    "misc",
]

# A whitelist of ALLOWED OUTPUTS. It contains the image of both non-trivial
# fibers, so it validates the syntax while leaving the kernel untouched.
REPORTER_NAMES = {"any-exprs", "xslt-html", "line-count", "misc"}


def nombre_de_reporter(k: str) -> str:
    return k.replace("_", "-").strip()


def construir_reporteros(llaves):
    por_nombre = {}
    for k in llaves:
        nombre = nombre_de_reporter(k)
        if nombre not in REPORTER_NAMES:
            continue
        por_nombre[nombre] = k
    return por_nombre


def construir_tabla(config):
    """A caller, so the accumulator escapes *and* someone calls it."""
    return construir_reporteros(config)


def resumen(config):
    return len(construir_reporteros(config))
