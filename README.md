# fiber-ast-lint

**Finds the dictionary writes that silently fuse two rows into one key.**

```python
por_nombre[name.replace("_", "-")] = cfg   # two different names, one slot
```

No exception. No warning. The line is valid Python and every row is valid on its own. `ruff`,
`mypy --strict` and `pylint` all report nothing, because nothing is wrong with any single row:
what is wrong is the *cardinality of the whole*, and no mainstream linter measures it.

`fiber-ast-lint` names those writes, separates real overwrites from harmless aggregation, and
then answers the question that decides whether the loss can ever be caught at runtime: **does
anyone measure the cardinal that would betray it?**

```console
$ uvx fiber-ast-lint tests/fixtures/espacio_no_transversal.py
CANDIDATO espacio_no_transversal.py:31  op=pierde      fam=ESPACIO+NORMALIZA      forma=PROYECCION_ARRIBA_CON_PERDIDA fn=construir_reporteros  nombre [nombre_de_reporter() linea 28 proyecta]
CENSO archivos=1 fallas=0 for_medidos=1
CONSERVACION almacenes=1 == pierde=0 + guardadas=0 + acumulacion=0 + posicional=0 + cardinal_sin_medir=1
CANDIDATOS total=1 == admitidos=1 + latentes=0  (admitido = proyecta con perdida, escapa y alguien la llama)
INTERPROC con_consumidor=1 de 1 · productores_con_sitio=1 · sitios_por_identidad=1 · sitios_por_nombre=0 · llamadas_sin_identidad=0
  consumidor espacio_no_transversal::construir_reporteros() espacio_no_transversal.py:41 -> len en :41 [DIRECTO/EXACTO]
```

Paths are files or directories; several of them are allowed (`fiber-ast-lint src tests`).

## The law

Let `π` be the function that builds the key (`lower()`, `strip()`, `replace()`, `basename()`,
a regex…). A dict built as `acc[π(k)] = v` keeps `|im(π)|` of the `|domain|` entries it received.
The destroyed mass is

```
núcleo(π) = Σ_y ( |π⁻¹(y)| − 1 )
```

and it is destroyed **silently**: the program cannot tell that it happened, because nothing it
can observe ever had the missing entries.

Two consequences this tool implements instead of mentioning:

1. **A whitelist cannot save it.** A guard of the form `if π(k) in ALLOWED` constrains the
   *codomain*. It suppresses the loss only when the inputs it lets through form a transversal of
   the partition induced by `π`:

   ```
   ∀ y ∈ π(W):  |W ∩ π⁻¹(y)| = 1
   ```

   `verificar_transversal(W, π)` decides this without running the program.
2. **Only a counted bucket makes the loss visible.** `if k not in acc: reject.append(k)` turns an
   invisible loss into a number you can log, alert on, or reconcile.

## Install

```console
uvx fiber-ast-lint [ruta]        # no install
pip install fiber-ast-lint       # or: pipx install fiber-ast-lint
```

Python ≥ 3.11, zero runtime dependencies (stdlib `ast` only).

## Exit codes (the contract)

| code | meaning |
|---|---|
| `0` | no candidates: every write aggregates, is guarded, is positional, or has no measurable cardinal |
| `1` | candidates to review — never "defects": a static pass can only name them |
| `2` | empty universe: no Python file was analysed. **Never reported as 0** |
| `4` | the instrument's own census does not reconcile, or a file failed to parse |

`4` is not decoration. The tool publishes what it discarded (`almacenes == pierde + guardadas +
acumulacion + posicional + cardinal_sin_medir`) and refuses to emit a report when those buckets
do not add up. A detector whose own numbers do not close is a detector whose silence means nothing.

With several paths (`fiber-ast-lint src tests`) the run's code is the **supremum** of the
individual codes under `4 > 1 > 2 > 0`, not the maximum of the integers: an empty path (`2`) must
not hide a candidate proven in another path (`1`), and nothing outranks a broken bucket (`4`).
`max(1, 2) == 2` — that is why the operator is spelled out instead of inferred.

## What it classifies

For every `for` loop, each write into an accumulator falls in exactly one class:

| class | shape | verdict |
|---|---|---|
| `pierde` | `acc[π(k)] = v`, value does not read `acc`, no membership test | **CANDIDATO** when `π` can fuse two keys |
| `acumulacion` | `acc[k] = acc.get(k, 0) + x` | aggregation, not loss — whoever measures it |
| `guardadas` | the loop asks `k in acc` anywhere | the loss is a countable bucket |
| `posicional` | `s[i] = x` on a sequence | replaces a row, cannot change cardinality |
| `cardinal_sin_medir` | nobody calls `len(acc)` in the scope | the loss is invisible even to the program |

A candidate is **admitted** only when the accumulator escapes its function *and* someone in the
analysed universe calls that function. Otherwise the report says `LATENTE` instead of spending a
reader's time on a defect that cannot change a decision.

## The second pass: who reads the cardinal one hop away?

`len(acc)` is often written by the caller, not by the builder. A second AST pass closes one hop
through the call site and labels it:

```
DIRECTO     len(build(...))                      consumer is the call itself
VINCULO     x = build(...)   then len(x)         consumer is the caller's variable
PARAMETRO  build(x)          then len(x)         accumulator arrived as a parameter
```

**Declared limits, never reported as zero:** no attribute form (`len(x.keys())`), no aliasing
through containers, nothing beyond one hop, and no `*`-import expansion (such a call is published
as unresolved instead of being resolved by guess).

Cross-module consumers are resolved by **qualified identity** — `(module, qualname)` built from
the module's own binding table, with `import`/`from ... import`/relative-import aliases and
attribute forms (`mod.f()`, `Cls.m()`). Name matching alone is not identity, and the difference is
measured on the same 239-file corpus:

| resolution | call sites attributed to a producer |
|---|---|
| bare name (what a naive pass does) | **434**, spread over 19 names — `main` alone accounts for 227, `medir` for 35 |
| qualified identity | **9** sites, **2** producing functions |

Of the 25 candidates, exactly **2** have an identity-matched consumer that reaches `len()`:
`medir_tax_mcp.py:156` (`medir` → `medir_tax_mcp.py:757`, `len` at `:763`) and
`poda_mcp_hostinger.py:1019` (`_claves_enablement` → `:1394`, `len` at `:1400`). Two call sites
that could not be resolved at all are published under `por_nombre` and are **never** promoted to
identity. Treat `INTERPROC` as *a reader exists*, not as *losses are observable*: the remaining 23
candidates keep their honest `SIN_LEN` verdict.

## Evidence

Measured 2026-11-25 with this package; every number is reproducible with
`fiber-ast-lint <ruta> --json`.

Own corpus (239 files of Python tooling):

| loops | stores | pierde | guardadas | acumulacion | posicional | sin medir | candidates | admitted |
|---|---|---|---|---|---|---|---|---|
| 3 032 | 408 | 13 | 53 | 85 | 21 | 236 | 25 | 22 |

Seven third-party packages (599 files, 308 stores): 6 lossy writes, **2 admitted, both in `mypy`**.
Across the other six — `pylint` (189 files), `astroid` (97), `isort` (45), `platformdirs` (15),
`tomlkit` (12), `dill` (46) — **zero admitted loci over 359 files**. Two more in place, without
copying them out of `site-packages`: `jsonschema` (37 files, 98 loops, 0 lossy) and `pydantic`
(105 files, 341 loops, 0 lossy).

Density of lossy projection per store: **1.95 % foreign vs 6.13 % own**. The density is not a
property of Python; it is a property of the codebase — the style that normalises session names,
paths and tool names by trade.

### The one real defect found so far

`mypy/config_parser.py:543` builds reporter names as `name.replace("-", "_")` and then re-projects
them back, so six ini keys land on four names: `any-exprs`/`any_exprs` and
`xslt-html`/`xslt_html` collapse. The whitelist `REPORTER_NAMES` that guards the write contains
the images of both fibers, which is exactly why it cannot help — the guard was validated by the
syntax and blind to the kernel. Reduction to a pure function lives in
`tests/fixtures/espacio_no_transversal.py`; the upstream issue is drafted in
[`docs/MYPY_REPORT_DRAFT.md`](docs/MYPY_REPORT_DRAFT.md) and not yet filed.

The second `mypy` locus (`config_parser.py:666`) is an **intentional** kernel: it maps CLI option
names onto internal keys and knows the collision is a merge. This tool does not claim to read
intent — it says `CANDIDATO`, and a human adjudicates. Two admitted, two adjudicated, one defect.

## Library use

```python
from fiber_ast_lint import analizar, verificar_transversal, verificar_conservacion

a = analizar("src/")
for loc in a.admitidos:
    print(loc.rel, loc.linea, loc.clave, loc.severidad)

verificar_transversal(["any-exprs", "xslt-html"], str.lower)     # -> {"transversal": True, ...}

# the bucket law, with strict positivity
verificar_conservacion(dominio=67, imagen=68, rechazos=0, colisiones=-1)
# -> {"conserva": False, "cubetas_negativas": {"colisiones": -1}, ...}
```

`verificar_conservacion` exists because a bucket defined by subtraction closes in ℤ even when the
counts are incompatible: `68 + 0 + (−1) = 67`. The arithmetic agrees; the census is a lie. Only
`bucket >= 0` refutes it.

## Known limits

- A static pass names candidates; it cannot decide intent. `CANDIDATO` is where review starts.
- Dynamic keys (`acc[f(k, i)] = v` with `k` mutated in the loop) are not modelled.
- Dict comprehensions are counted in the census but not reported as loci (they cannot be observed
  by a caller: the loss happens before the object exists).
- Only `for` loops; `while` accumulators are out of scope today (see the tests for the enumerator).

## Version note

`0.1.0` files an aggregation (`acumulacion`) in its own bucket whatever the population, instead of
filing it under `cardinal_sin_medir`. The *loci* are unchanged; only the census wording is.

## License

MIT — see [LICENSE](LICENSE).
