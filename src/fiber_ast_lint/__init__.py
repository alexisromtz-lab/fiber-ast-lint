"""fiber-ast-lint: static detection of lossy key projections.

A dictionary built as ``acc[pi(k)] = v`` with a non-injective ``pi`` silently
keeps ``|im(pi)|`` of the entries it received. Mainstream linters do not see it:
the code is valid Python and each row is valid on its own. This package names
those loci, separates real overwrites from monoidal aggregation, and reports
whether anyone measures (or publishes) the cardinal that betrays the loss.
"""
from .detect import Analisis, Locus, analizar
from .graph import Consumidor, Consumos, consumos, clave_de, modulo_de
from .rc import combinar_rc, precedencia
from .transversal import Fibra, es_transversal, fibra, verificar_conservacion, verificar_transversal

__version__ = "0.4.2"
__all__ = [
    "Analisis", "Locus", "analizar",
    "Consumidor", "Consumos", "consumos", "clave_de", "modulo_de",
    "combinar_rc", "precedencia",
    "Fibra", "fibra", "es_transversal", "verificar_transversal",
    "verificar_conservacion", "__version__",
]
