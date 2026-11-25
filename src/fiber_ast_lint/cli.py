"""Command line entry point: ``fiber-ast-lint [ruta]``.

Exit codes (the tool's own contract, stable):
  0  no candidates: every write either aggregates, is guarded, is positional
     or has no measurable cardinal
  1  candidates to review (never "defects": a static pass can only name them)
  2  empty universe (no Python file was analysed) - never reported as 0
  4  the instrument does not reconcile: its own census does not add up
"""
from __future__ import annotations

import argparse
import json
import sys

from . import graph
from .detect import RC_CANDIDATO, RC_CONSERVACION, RC_OK, RC_VACIO, analizar


def _fila(loc) -> str:
    extra = f" [{loc.nota}]" if loc.nota else ""
    pub = f" pub={loc.publica}" if loc.publica not in ("", "SIN_LEN") else ""
    return (f"{loc.severidad:9s} {loc.rel}:{loc.linea}  op={loc.op:11s} "
            f"fam={loc.familia:22s} forma={loc.forma:28s} "
            f"fn={loc.fn or '<modulo>'}{pub}  {loc.clave}{extra}")


def construir(raiz: str, interproc: bool = True) -> dict:
    a = analizar(raiz)
    productores = {loc.fn for loc in a.candidatos if loc.fn}
    consumos = graph.consumidores(raiz, productores) if (interproc and productores) else {}
    for loc in a.loci:
        lista = consumos.get(loc.fn) or []
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
        "candidatos": [
            {
                "archivo": x.rel, "linea": x.linea, "clave": x.clave,
                "familia": x.familia, "forma": x.forma, "funcion": x.fn,
                "poblacion": x.poblacion, "escapa": x.escapa,
                "llamadas": x.llamadas, "publica": x.publica,
                "severidad": x.severidad, "consumidor": x.consumidor,
            }
            for x in sorted(a.loci, key=lambda y: (y.rel, y.linea)) if x.candidato
        ],
        "analisis": a,
        "consumos": consumos,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fiber-ast-lint", description=__doc__)
    p.add_argument("ruta", nargs="?", default=".", help="directorio a analizar")
    p.add_argument("--json", action="store_true", help="salida JSON determinista")
    p.add_argument("--sin-interproc", action="store_true",
                   help="omite la segunda pasada (sitios de llamada)")
    p.add_argument("--solo-candidatos", action="store_true",
                   help="no imprime los loci LATENTE/INFO")
    p.add_argument("-q", "--quiet", action="store_true", help="solo el codigo de salida")
    args = p.parse_args(argv)

    r = construir(args.ruta, interproc=not args.sin_interproc)
    a = r["analisis"]
    # Order matters: a universe made only of unparsable files has zero analysed
    # modules, and reporting that as "empty" would hide the failure behind a
    # legitimate-looking code.
    if a.fallas:
        for e in a.errores:
            print(f"FALLA ANALISIS {e}", file=sys.stderr)
        return RC_CONSERVACION
    if not a.archivos:
        if not args.quiet:
            print(f"UNIVERSO VACIO: sin modulos .py bajo {a.raiz}", file=sys.stderr)
        return RC_VACIO
    if not a.reconcilia():
        print("INSTRUMENTO NO RECONCILIA: el censo de descartes no cuadra",
              file=sys.stderr)
        return RC_CONSERVACION

    if args.json:
        payload = {k: v for k, v in r.items() if k not in ("analisis", "consumos")}
        payload["consumidores"] = {k: [str(c) for c in v] for k, v in r["consumos"].items()}
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    elif not args.quiet:
        for loc in sorted(a.loci, key=lambda y: (not y.candidato, y.rel, y.linea)):
            if args.solo_candidatos and not loc.candidato:
                continue
            print(_fila(loc))
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
              f" · productores_con_sitio={len(r['consumos'])}")
        for nombre, lista in sorted(r["consumos"].items()):
            for c in lista[:3]:
                print(f"  consumidor {c}")

    return RC_CANDIDATO if a.candidatos else RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
