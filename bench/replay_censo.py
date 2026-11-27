"""Re-derive `censo.json` from the artifacts it names.

The census is a claim about wheels, so the only honest way to check it is to go
and get the wheels. This script fetches each row's artifact from PyPI, checks
its SHA-256 against both the pin and PyPI's own digest, unpacks it, runs the
analyzer on the declared subtree, and compares the measured cells -- the counts,
the four buckets, and the pair of codes (`rc` for the scan, `rc_certificado` for
the act) with the pair of booleans that name them.

    python bench/replay_censo.py            # temp dir, deleted at the end
    python bench/replay_censo.py --dir /tmp/censo --keep
    python bench/replay_censo.py --solo mypy

Exit codes follow the same ladder the package uses, extended with the one case
the package cannot have: the premise itself broke.

    0  every row reproduced exactly
    1  a published cell did not reproduce (our code moved, or the row is wrong)
    2  NO_MEDIDO -- PyPI unreachable, nothing was checked
    4  the pin ruptured -- the artifact is not the one the census names, so no
       divergence below it can be interpreted

4 outranks 1 on purpose: a wrong artifact makes every other verdict unreadable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from fiber_ast_lint.rc import DEFECTO, RUPTURA, VACIO, combinar_rc  # noqa: E402

CENSO = RAIZ / "censo.json"
UA = {"User-Agent": "fiber-ast-lint-censo-replay/1"}
# The first six are what the census has always compared. The four after them are
# the buckets that make `reconciles` checkable by somebody who is not this
# script: without them a reader has to believe the flag.
CUBETAS = ("guardadas", "acumulacion", "posicional", "sin_len")

# The seven-package table in README.md is a declared population, not "every row
# that is not the instrument": the census also carries an out-of-sample batch and
# a second mypy row over the whole wheel, and neither belongs in this total.
SIETE = (("mypy", "mypy"), ("pylint", "."), ("astroid", "."), ("dill", "."),
         ("isort", "."), ("platformdirs", "."), ("tomlkit", "."))
CAMPOS = ("files", "stores", "pierde", "candidates", "admitted", "column_loci") + CUBETAS

# Two surfaces the payload already publishes with their own names. The census
# used to carry only `rc` and `reconciles`, and on the two empty universes those
# two held the *certificate* answer while the other eleven held the *scan*
# answer: one key, two subjects. A consumer cannot tell `1` ("the scan found
# candidates") from `1` ("the receipt declared a collision"), so both are pinned.
FIRMA = ("rc", "rc_certificado", "reconciles", "certifica")

# The verdicts are this package's own codes, not a private ladder: 1 is a proven
# defect, 2 is blindness, 4 is a broken premise, and the operator is the one the
# CLI already uses so a batch of rows cannot compose differently here than there.
OK, DIVERGE, NO_MEDIDO = 0, DEFECTO, VACIO
VEREDICTO = {OK: "REPLAY IDENTICO", DIVERGE: "REPLAY CON DIVERGENCIA",
             NO_MEDIDO: "NO_MEDIDO", RUPTURA: "PIN ROTO"}


def _get(url: str) -> bytes:
    peticion = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(peticion, timeout=120) as r:
        return r.read()


def _traer(package: str, artifact: str, destino: Path) -> tuple[Path | None, str, int]:
    """Return (path, digest declared by PyPI, rc). rc is 0, 2 or 4."""
    try:
        meta = json.loads(_get(f"https://pypi.org/pypi/{package}/json"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"  NO_MEDIDO: PyPI sin respuesta para {package}: {exc}")
        return None, "", NO_MEDIDO
    for entrada in meta.get("urls", []):
        if entrada.get("filename") != artifact:
            continue
        datos = _get(entrada["url"])
        destino.write_bytes(datos)
        return destino, entrada.get("digests", {}).get("sha256", ""), OK
    print(f"  RUPTURA: {package} ya no publica {artifact}")
    return None, "", RUPTURA


def _medir(raiz: Path) -> dict:
    p = subprocess.run([sys.executable, "-m", "fiber_ast_lint", str(raiz), "--json"],
                       capture_output=True, text=True, cwd=RAIZ)
    if not p.stdout.strip():
        raise RuntimeError(f"sin JSON para {raiz}: {p.stderr.strip()[:400]}")
    d = json.loads(p.stdout)
    cand = d["candidatos"]
    # `claves` is not compared by the replay; it is what the invoice is counted
    # in -- one adjudication closes every site that shares a key -- and a second
    # definition of a row would be a second thing to keep in sync.
    # The bytes the scanner walked, not the bytes of the wheel it came from: the
    # model in `cotizar.py` was fitted on artifact bytes and a tree is not that
    # subject (batch 5). This is the same tree the counts are over.
    if raiz.is_file():
        bytes_py = raiz.stat().st_size
    else:
        bytes_py = sum(f.stat().st_size for f in sorted(raiz.rglob("*.py")) if f.is_file())
    return {"claves": [c["clave"] for c in cand],
            "bytes_py": bytes_py,
            "species": {f: sum(1 for c in cand if c["forma"] == f)
                        for f in sorted({c["forma"] for c in cand})},
            "files": d["archivos"], "stores": d["almacenes"], "pierde": d["pierde"],
            "loops": d["for_medidos"],
            **{k: d[k] for k in CUBETAS},
            "candidates": len(cand),
            "admitted": sum(1 for c in cand if c["severidad"] == "CANDIDATO"),
            "column_loci": sum(1 for c in cand if c["forma"] == "SELECCION_COLUMNA_BUCLE"),
            "rc": d["rc"], "rc_certificado": d["rc_certificado"],
            "reconciles": d["reconcilia"], "certifica": d["certifica"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Replay the census from its artifacts.")
    ap.add_argument("--dir", help="cache directory (default: a temporary one)")
    ap.add_argument("--keep", action="store_true", help="do not delete the cache")
    ap.add_argument("--solo", action="append", default=None,
                    help="only this package (repeatable)")
    ap.add_argument("--censo", help="read this census file instead of ./censo.json")
    ap.add_argument("--desde", help="measure from this cache dir; download nothing")
    ap.add_argument("--anotar", action="store_true",
                    help="write the measured cells back into the census, so the "
                         "row can be reconciled by someone else")
    a = ap.parse_args(argv)

    censo = json.loads(Path(a.censo or CENSO).read_text(encoding="utf-8"))
    filas = [r for r in censo["rows"] if not a.solo or r["package"] in a.solo]
    if not filas:
        print("NO_MEDIDO: el filtro no selecciona ninguna fila")
        return NO_MEDIDO

    propio = a.dir is None
    base = Path(a.dir) if a.dir else Path(tempfile.mkdtemp(prefix="censo-"))
    base.mkdir(parents=True, exist_ok=True)

    try:
        peor, medidas = OK, {}
        for r in filas:
            print(f"{r['package']} {r['version']} {r['scope']}:")
            if a.desde:
                raiz = Path(a.desde) / f"{r['package']}-{r['version']}" / r["scope"]
                if not raiz.exists():
                    print(f"  NO_MEDIDO: falta {raiz}")
                    peor = combinar_rc(peor, NO_MEDIDO)
                    continue
                real = _medir(raiz)
                medidas[(r["artifact"], r["scope"])] = real
                difs = {k: (real[k], r[k]) for k in CAMPOS + FIRMA
                        if k in r and real[k] != r[k]}
                if difs:
                    print("  DIVERGE: " + ", ".join(f"{k} medido={m} pin={p}"
                                                    for k, (m, p) in difs.items()))
                    peor = combinar_rc(peor, DIVERGE)
                else:
                    print("  identico: " + " ".join(f"{k}={real[k]}" for k in CAMPOS + FIRMA))
                continue
            rueda, dig_pypi, rc = _traer(r["package"], r["artifact"], base / r["artifact"])
            if rc:
                peor = combinar_rc(peor, rc)
                continue
            dig_local = hashlib.sha256(rueda.read_bytes()).hexdigest()
            if dig_local != r["sha256"]:
                print(f"  RUPTURA: sha256 {dig_local[:16]} != pin {r['sha256'][:16]}")
                peor = combinar_rc(peor, RUPTURA)
                continue
            if dig_pypi and dig_pypi != dig_local:
                print("  RUPTURA: PyPI declara otro digest para su propio artefacto")
                peor = combinar_rc(peor, RUPTURA)
                continue
            destino = base / f"{r['package']}-{r['version']}"
            if not destino.is_dir():
                with zipfile.ZipFile(rueda) as z:
                    z.extractall(destino)
            raiz = destino / r["scope"]
            # El escaner acepta un arbol o un modulo suelto, asi que el pin no
            # puede exigir directorio: `six.py` es un scope legitimo y pedirle
            # una carpeta era una suposicion del lector, no del objeto.
            if not raiz.exists():
                print(f"  RUPTURA: el artefacto no contiene {r['scope']}")
                peor = combinar_rc(peor, RUPTURA)
                continue
            real = _medir(raiz)
            medidas[(r["artifact"], r["scope"])] = real
            sin_anotar = [k for k in CUBETAS if k not in r]
            if sin_anotar:
                print("  SIN ANOTAR: " + ", ".join(sin_anotar)
                      + " (reconciles no es comprobable por un tercero)")
            difs = {k: (real[k], r[k]) for k in CAMPOS + FIRMA
                    if k in r and real[k] != r[k]}
            if difs:
                print("  DIVERGE: " + ", ".join(f"{k} medido={m} pin={p}"
                                                for k, (m, p) in difs.items()))
                peor = combinar_rc(peor, DIVERGE)
            else:
                print("  identico: " + " ".join(f"{k}={real[k]}" for k in CAMPOS + FIRMA))

        if a.anotar:
            tocadas = 0
            for r in censo["rows"]:
                real = medidas.get((r["artifact"], r["scope"]))
                if real is None:
                    continue
                for k in CAMPOS + FIRMA:
                    r[k] = real[k]
                residuo = r["stores"] - r["pierde"] - sum(real[k] for k in CUBETAS)
                if residuo:
                    print(f"  RUPTURA: {r['package']} {r['scope']}: "
                          f"residuo {residuo} tras anotar")
                    peor = combinar_rc(peor, RUPTURA)
                tocadas += 1
            import fiber_ast_lint

            censo["instrument_version"] = fiber_ast_lint.__version__
            print(f"ANOTADO {tocadas} filas · instrumento {censo['instrument_version']}")

        siete = [r for r in filas if (r["package"], r["scope"]) in SIETE]
        claves = [(r["artifact"], r["scope"]) for r in siete]
        if len(siete) == len(SIETE) and all(c in medidas for c in claves):
            suma = {k: sum(medidas[c][k] for c in claves) for k in CAMPOS}
            pin = {k: v for k, v in censo["totals_seven"].items() if k in suma}
            if suma != pin:
                print(f"  DIVERGE: totals_seven medido={suma} pin={pin}")
                peor = combinar_rc(peor, DIVERGE)
            else:
                print(f"totales de siete paquetes identicos: {pin}")
            if a.anotar:
                censo["totals_seven"] = suma

        if a.anotar:
            destino_censo = Path(a.censo or CENSO)
            destino_censo.write_text(
                json.dumps(censo, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
            print(f"ESCRITO {destino_censo}")

        print(f"\n{VEREDICTO[peor]} · {len(filas)} filas"
              f" · instrumento {censo['instrument_version']}")
        return peor
    finally:
        if propio and not a.keep:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
