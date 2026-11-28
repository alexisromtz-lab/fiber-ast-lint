"""Command line entry point: ``fiber-ast-lint [ruta ...]``.

Exit codes (the tool's own contract, stable):
  0  no candidates: every write either aggregates, is guarded, is positional
     or has no measurable cardinal
  1  candidates to review (never "defects": a static pass can only name them)
     ``--rc-decidido`` narrows that 1 to the rows the certificate did not
     refute; the default code is unchanged, so a published receipt keeps its
     number.
  2  empty universe (no Python file was analysed) - never reported as 0
  4  the instrument does not reconcile, or a file could not be parsed

With several paths the run's code is the SUPREMUM of the individual codes under
``4 > 1 > 2 > 0`` (see :func:`fiber_ast_lint.rc.combinar_rc`), never ``max``:
an empty path must not hide a proven candidate in another path.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, graph
from .adjudicador_ast import SIN_CAUSA
from .causa import ADJUDICADOR, INTERPRETE, REFUTADAS, causas
from .detect import RC_CANDIDATO, RC_CONSERVACION, RC_OK, RC_VACIO, Analisis, analizar
from .rc import combinar_rc


def _fila(loc, causa: str = "") -> str:
    extra = f" [{loc.nota}]" if loc.nota else ""
    pub = f" pub={loc.publica}" if loc.publica not in ("", "SIN_LEN") else ""
    caus = f" causa={causa}" if causa else ""
    nombre = loc.qn or loc.fn or "<modulo>"
    return (f"{loc.severidad:9s} {loc.rel}:{loc.linea}  op={loc.op:11s} "
            f"fam={loc.familia:22s} forma={loc.forma:28s} "
            f"fn={nombre}{pub}{caus}  {loc.clave}{extra}")


def construir(raiz: str, interproc: bool = True) -> dict:
    a = analizar(raiz)
    caus = causas(raiz, a.loci)
    claves = {graph.clave_de(loc.rel, loc.qn or loc.fn)
              for loc in a.candidatos if (loc.qn or loc.fn)}
    consumos = graph.consumos(raiz, claves) if (interproc and claves) else graph.Consumos()
    for loc in a.loci:
        if not (loc.qn or loc.fn):
            continue
        lista = consumos.de(graph.clave_de(loc.rel, loc.qn or loc.fn))
        if lista:
            loc.consumidor = str(lista[0])
    return {
        "raiz": a.raiz,
        "archivos": a.archivos,
        "fallas": a.fallas,
        "for_medidos": a.for_medidos,
        "almacenes": a.almacenes,
        "pierde": a.pierde,
        "guardadas": a.guardadas,
        "acumulacion": a.acumulacion,
        "posicional": a.posicional,
        "sin_len": a.sin_len,
        "reconcilia": a.reconcilia(),
        "causas": caus,
        "abiertas": abiertas(a, caus),
        "candidatos": [
            {
                "archivo": x.rel, "linea": x.linea, "clave": x.clave,
                "familia": x.familia, "forma": x.forma, "funcion": x.fn,
                "qualname": x.qn, "poblacion": x.poblacion, "escapa": x.escapa,
                "llamadas": x.llamadas, "publica": x.publica,
                "severidad": x.severidad, "consumidor": x.consumidor,
                "causa": caus.get((x.rel, x.linea), SIN_CAUSA),
            }
            for x in sorted(a.loci, key=lambda y: (y.rel, y.linea)) if x.candidato
        ],
        "analisis": a,
        "consumos": consumos,
    }


def abiertas(a: Analisis, caus: dict) -> int:
    """How many candidates the certificate did not refute.

    A row with ``causa`` in ``REFUTADAS`` is decided and asks no reader. Every
    other row stays open, ``fichero_no_parsea`` included: it measures the parser.
    """
    return sum(1 for x in a.candidatos
               if caus.get((x.rel, x.linea), SIN_CAUSA) not in REFUTADAS)


def rc_de(a: Analisis, abiertas_: int | None = None) -> int:
    """Per-universe code. Order matters: a broken file is not an empty universe.

    ``abiertas_`` is the opt-in reading (``--rc-decidido``): the code counts only
    the rows still open, so a corpus whose slices are provably positional stops
    turning the gate red on its own refutations.
    """
    if a.fallas:
        return RC_CONSERVACION
    if not a.archivos:
        return RC_VACIO
    if not a.reconcilia():
        return RC_CONSERVACION
    if abiertas_ is None:
        return RC_CANDIDATO if a.candidatos else RC_OK
    return RC_CANDIDATO if abiertas_ else RC_OK


def rc_certificado(a: Analisis) -> int:
    """El codigo que un recibo puede publicar. Un universo sin almacen es NO_MEDIDO.

    No es el codigo del escaneo: un linter sobre un fichero sin bucles no tiene
    nada que decir (0), pero un acta que firma ``reconcilia: true`` sobre cero
    almacenes afirma una conservacion que su poblacion no sostiene.
    """
    return RC_VACIO if not a.almacenes else rc_de(a)


def _payload(r: dict) -> dict:
    a = r["analisis"]
    c = r["consumos"]
    return {
        "instrument": "fiber-ast-lint", "instrument_version": __version__,
        "adjudicador": ADJUDICADOR, "interprete": INTERPRETE,
        "raiz": r["raiz"], "archivos": r["archivos"], "fallas": r["fallas"],
        "for_medidos": r["for_medidos"], "almacenes": r["almacenes"],
        "pierde": r["pierde"], "guardadas": r["guardadas"],
        "acumulacion": r["acumulacion"], "posicional": r["posicional"],
        "sin_len": r["sin_len"], "reconcilia": r["reconcilia"],
        "abiertas": r["abiertas"],
        "rc": rc_de(a), "rc_certificado": rc_certificado(a),
        "rc_decidido": rc_de(a, r["abiertas"]),
        "certifica": a.certifica(), "candidatos": r["candidatos"],
        "consumidores": {k: [str(x) for x in v] for k, v in c.exactos.items()},
        "consumidores_por_nombre": c.sitios_por_nombre,
        "consumidores_por_self": c.sitios_por_self,
        "llamadas_self_ajenas": c.ajenas_por_self,
        "llamadas_sin_identidad": c.no_resueltos,
    }


def _informe(r: dict, solo_candidatos: bool) -> None:
    a = r["analisis"]
    c = r["consumos"]
    for loc in sorted(a.loci, key=lambda y: (not y.candidato, y.rel, y.linea)):
        if solo_candidatos and not loc.candidato:
            continue
        print(_fila(loc, r["causas"].get((loc.rel, loc.linea), "")))
    print(f"CENSO archivos={a.archivos} fallas={a.fallas} for_medidos={a.for_medidos}")
    print(f"CONSERVACION almacenes={a.almacenes} == pierde={a.pierde} + guardadas={a.guardadas}"
          f" + acumulacion={a.acumulacion} + posicional={a.posicional}"
          f" + cardinal_sin_medir={a.sin_len}")
    cand = a.candidatos
    print(f"CANDIDATOS total={len(cand)} == admitidos={len(a.admitidos)}"
          f" + latentes={len(cand) - len(a.admitidos)}"
          f"  (admitido = proyecta con perdida, escapa y alguien la llama)")
    con_consumidor = [x for x in cand if x.consumidor]
    print(f"INTERPROC con_consumidor={len(con_consumidor)} de {len(cand)}"
          f" · productores_con_sitio={c.productores_con_sitio}"
          f" · sitios_por_identidad={c.sitios_exactos}"
          f" · sitios_por_self={c.sitios_por_self}"
          f" · sitios_por_nombre={c.sitios_por_nombre}"
          f" · llamadas_sin_identidad={c.no_resueltos}")
    for clave, lista in sorted(c.exactos.items()):
        for x in lista[:3]:
            print(f"  consumidor {x}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fiber-ast-lint", description=__doc__)
    p.add_argument("ruta", nargs="*", default=["."], help="directorios a analizar")
    p.add_argument("--json", action="store_true", help="salida JSON determinista")
    p.add_argument("--sin-interproc", action="store_true",
                   help="omite la segunda pasada (sitios de llamada)")
    p.add_argument("--solo-candidatos", action="store_true",
                   help="no imprime los loci LATENTE/INFO")
    p.add_argument("-q", "--quiet", action="store_true", help="solo el codigo de salida")
    p.add_argument("--rc-decidido", action="store_true",
                   help="el codigo solo cuenta las filas que la causa no refuta")
    args = p.parse_args(argv)

    resultados = [construir(ruta, interproc=not args.sin_interproc)
                  for ruta in (args.ruta or ["."])]
    codigos: list[int] = []
    for i, r in enumerate(resultados):
        a = r["analisis"]
        if a.fallas and not args.quiet:
            for e in a.errores:
                print(f"FALLA ANALISIS {e}", file=sys.stderr)
        if not a.archivos and not a.fallas and not args.quiet:
            print(f"UNIVERSO VACIO: sin modulos .py bajo {a.raiz}", file=sys.stderr)
        if not a.fallas and a.archivos and not a.reconcilia():
            print(f"INSTRUMENTO NO RECONCILIA en {a.raiz}:"
                  f" el censo de descartes no cuadra", file=sys.stderr)
        codigos.append(rc_de(a, r["abiertas"] if args.rc_decidido else None))
        if args.json or args.quiet:
            continue
        if len(resultados) > 1:
            print(f"=== {a.raiz} ===")
        _informe(r, args.solo_candidatos)

    if args.json:
        cuerpo = [_payload(r) for r in resultados]
        print(json.dumps(cuerpo[0] if len(cuerpo) == 1 else cuerpo,
                         indent=2, ensure_ascii=False, sort_keys=True))
    return combinar_rc(*codigos)


if __name__ == "__main__":
    raise SystemExit(main())
