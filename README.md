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

## A column is not the row

`acc[fila.codigo] = fila` fails exactly like `acc[fila["codigo"].strip()] = fila` one syntactic
layer down: the key space is **one column of the row**, so any two rows that share the column fuse.
It gets its own form and its own family, because filing it as plain `SELECCION` published the
family as `IDENTIDAD` — "the key is the row" — and that hid the projection while the loss stayed:

```
CANDIDATO columna_no_transversal.py:10  op=pierde  fam=COLUMNA  forma=SELECCION_COLUMNA_BUCLE
```

The detector fires only when the attribute's **root is the loop variable**. `acc[cfg.clave]`,
whose root is a parameter, is a *constant key* — every iteration writes the same slot, a different
defect that this pass does not claim to see — and is reported as `SELECCION`, not as a column.
Whether the column is unique is not knowable statically, so the verdict is `CANDIDATO`; a prior
`if fila.codigo in acc:` turns it into a counted bucket (`guardadas`) and the run goes clean.

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

Seven third-party packages, **599 files, 308 stores**, re-measured 2026-11-25 and pinned in
[`censo.json`](censo.json): each row names the **wheel**, its SHA-256, and the **subtree** that was
analysed. `tests/test_censo.py` fails if any cell of this table stops matching that file.

| package | version | scope | files | stores | pierde | candidates | admitted | column loci |
|---|---|---|---|---|---|---|---|---|
| `mypy` | 2.4.1 | `mypy/` | 195 | 173 | 4 | 18 | **5** | 16 |
| `pylint` | 4.1.4 | `.` | 189 | 55 | 1 | 2 | 0 | 2 |
| `astroid` | 4.3.4 | `.` | 97 | 37 | 0 | 5 | 0 | 5 |
| `dill` | 0.4.1 | `.` | 46 | 16 | 4 | 0 | 0 | 0 |
| `isort` | 9.0.2 | `.` | 45 | 21 | 0 | 4 | 0 | 0 |
| `platformdirs` | 4.14.8 | `.` | 15 | 0 | 0 | 0 | 0 | 0 |
| `tomlkit` | 0.15.3 | `.` | 12 | 6 | 0 | 1 | 0 | 1 |
| **total** | | | **599** | **308** | **9** | **30** | **5** | **24** |

All five admitted loci are in `mypy`: `applytype.py:127` (`tvar.id`), `config_parser.py:543`
(`report_type`), `config_parser.py:666` (`name`), `expandtype.py:113` (`binder.id`) and
`join.py:781` (`tv.id`). The other six packages hold **zero admitted over 404 files**.

### What the pin cost: two rows were talking about a different object

The earlier version of this table said `mypy 195 files` without saying *which mypy*, and the number
does not come from a wheel: no published mypy release between 1.13 and 2.4.1 has 195 `.py` files
(292–336, probed individually). It is the `mypy/` subtree of **2.4.1**, excluding `mypyc/` — a scope,
not a version. The row was right and unfalsifiable at the same time; now it is neither.

Measured on the whole wheel instead, `mypy 2.4.1` is **336 files / 226 stores / 26 candidates / 6
admitted**, and the sixth admits a locus the subtree could not see:
`mypyc/irbuild/main.py:124` (`module.fullname`) — `result[fq] = module_ir` keyed by a module's
fullname, which mypy refuses to let two modules share. Benign, same family as `tv.fullname`.

| package | version | files | stores | pierde | loops | candidates | admitted | column loci |
|---|---|---|---|---|---|---|---|---|
| `mypy` (whole wheel) | 2.4.1 | 336 | 226 | 4 | 2 561 | 26 | 6 | 24 |
| `pydantic` | 2.14.4 | 106 | 143 | 0 | 342 | 10 | **2** | 10 |
| `jsonschema` | 4.26.0 | 37 | 2 | 0 | 98 | 0 | 0 | 0 |

`jsonschema` reproduces the earlier line exactly (37 files, 98 loops). `pydantic` had been quoted as
105 files / 341 loops, which is an earlier 2.14.x; at 2.14.4 it is 106 / 342. And "0 lossy" was
true and incomplete: `pydantic` admits **two** loci, both `param.name` —
`_internal/_signature.py:114` and `v1/utils.py:255`, `merged_params[param.name] = param` over
`inspect.signature(init).parameters`. A `Signature` cannot hold two parameters with one name, so
these are adjudicated benign by the same reasoning already applied to `posonly.name`. Zero
accidents, one package wider.

The own-corpus row further up (239 files, 413 stores) **cannot be pinned**: it is internal tooling
that does not ship. It is evidence about us, not a reproducible claim about this tool, and it is not
used here for any cross-package arithmetic.

### A density that reversed when the instrument improved

The previous version of this file reported *1.95 % foreign vs 6.13 % own* lossy density and
concluded the style was a property of the codebase. **That comparison is retracted.** Both figures
came from a classifier that could not see column keys (`acc[fila.columna]`), and 24 of the 30
foreign candidates are exactly that form. Measured today, with one instrument on both sides:

| universe | candidates / stores |
|---|---|
| foreign (7 packages) | 30 / 308 = **9.74 %** |
| own (240 files of tooling) | 25 / 413 = **6.05 %** |

The relation reverses. A density measured with a blinder is not a density, and the two numbers are
not reconciled here because reconciling them would mean pretending one instrument produced both.

### What the column form found: 24 loci, 5 admitted, zero accidents

Every one of the 24 is a real column projection — the key is an attribute of the loop variable, not
a syntactic accident — and each is adjudicable in a line:

| column | loci | why it does not merge |
|---|---|---|
| `tvar.id`, `binder.id`, `tv.id`, `v.id` | 9 | `mypy` allocates `TypeVarId` monotonically: one id, one binder |
| `tv.fullname`, `n.fullname` | 3 | qualified name, unique per definition |
| `item_name.value`, `arg.value`, `keyword.value` | 4 | the key is an AST node: one node, one slot |
| `posonly.name`, `arg.name`, `kwarg.name` | 3 | the grammar forbids two parameters with one name |
| `base.type` | 2 | the key is the type object itself |
| `key.key` (`tomlkit`) | 1 | TOML forbids duplicate keys in a table |
| `decorator.name` (`pylint`) | 1 | `@overload` twice is legal — **this collision is real**, at a cost of one lint message |
| `module.fig_id` (`pylint`) | 1 | unique per diagram node |

One genuine hole, and it costs a repeated lint message. Zero accidental hits. Nineteen of the 24
stay `LATENTE` not because the detector doubts them but because nobody calls `len()` on the
accumulator — and the verdict stays `CANDIDATO` because the tool cannot read the contract that
makes a column unique. That contract is the reader's, and adjudicating it is not a false positive.

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
intent — it says `CANDIDATO`, and a human adjudicates. Five admitted, four adjudicated benign,
one defect.

## Fixtures census, recomputed by the test suite

Every number below is recomputed on each test run by `tests/test_readme.py`, which builds the
census with the real code and fails if any cell of this table disagrees. The larger censuses further
down need corpora that do not live in this repository, so they are dated and their provenance is
stated; this one is not a claim, it is an assertion.

| universe | files | stores | lose | guarded | aggregate | positional | unmeasured | candidates |
|---|---|---|---|---|---|---|---|---|
| `tests/fixtures` | 9 | 9 | 0 | 2 | 1 | 1 | 5 | 4 |

`stores` is `fallas + guarded + aggregate + positional + unmeasured`, and the run refuses to report
(RC 4) if it does not close. Note the size of `unmeasured`: five of nine stores have no cardinal
anybody reads, so the tool stays silent about them instead of inventing a verdict.

## Cost, measured before optimising anything

An honest baseline first: a benchmark published *after* the fix cannot predict anything.

| universe | files | **CPU** (median of 7) | CPU min | CPU per file |
|---|---|---|---|---|
| `pylint` 4.1.4 | 189 | **2.05 s** | 1.65 s | 10.8 ms |

**Retraction of a previously published number.** This table used to read `37.8 s wall / 5.24 s
CPU`, taken on a host at load average 53. That figure does not reproduce: the same code, same 189
files, measures 1.65–2.05 s of CPU today. A wall clock under contention is not a measurement, and
neither is a CPU time read from a machine where every other tab is compiling — the process spends
its slices in page faults and in the scheduler, and both are billed to it. The number is withdrawn,
not adjusted.

### `H_memo_ast`: a pre-registered hypothesis, killed by its own falsifier

The hypothesis was registered here *before* any code was written, with the falsifier attached:

- **Claim.** A memoised post-order pass (name censuses, `len` census, scope parent tables) brings
  `pylint` under **3 s of CPU**.
- **Falsifier.** If the CPU cost does not at least *halve*, the hypothesis dies and gets published
  dead — a 1.3× win is not worth the risk of a rewrite.
- **Invariant it may not break.** Every locus of the 189-file census identical before and after.

The rewrite was built in full — one post-order traversal per module computing all seven censuses
(writes, reads, rebinds, measured cardinals, born sequences, born dicts, membership questions), the
per-scope assignment table made lazy, and the per-`FunctionDef` return census folded into the same
pass — and then measured against the untouched original, interleaved, seven rounds each:

| | node visits | visits / node | CPU median | CPU min |
|---|---|---|---|---|
| original | 2 552 987 | 11.61 | 2.05 s | 1.65 s |
| post-order | 925 953 | 4.21 | 1.57 s | 1.45 s |

Node visits fall by 64 %. CPU falls by **1.31×** (median) / 1.14× (min). Output is identical: the
37 loci of the `pylint` census match byte for byte, and the whole test suite passes unchanged.

**The falsifier is met, so the hypothesis is dead and the rewrite was reverted.** Two things it
taught, both worth more than the 24 %:

1. **The diagnosis was wrong.** `visits / node` measured over corpus fractions of 25 %, 50 % and
   100 % is flat — 9.72, 9.60, 10.04 — so the original analysis is *already linear in nodes*. It was
   never quadratic and nesting depth was never "the hidden multiplier"; the earlier text here said
   it was, and that sentence is retracted. The truth is a constant: ~10 walks per node, all of them
   cheap C-level traversals.
2. **Node visits are a proxy that overstates the work.** Cutting 64 % of the visits bought 24 % of
   the CPU, because each removed visit was a tight specialised loop and each replacement does seven
   `isinstance` checks to rebuild the same answer. Any future claim about this instrument has to be
   stated in CPU seconds; a visit counter will lie to you by a factor of nearly three.

A profiled run is worse than useless for this question: under `cProfile` the same original reports
`29.6 s` of wall and `2 214 631` `ast.walk` calls, because the profiler charges every generator
resume. The baseline above was taken without it.

The tool is a batch and pre-commit check. At 10.8 ms of CPU per file it will audit a 5 000-file
repository in about 54 s, which is the intended use.

### Adopting it without PyPI

`.pre-commit-hooks.yaml` is in the repository root:

```yaml
repos:
  - repo: https://github.com/alexisromtz-lab/fiber-ast-lint
    rev: v0.4.1
    hooks:
      - id: fiber-ast-lint
```

The hook passes the staged files to the binary, so the run's code is the supremum of their
individual codes under `4 > 1 > 2 > 0`. Exit `1` stops the commit with candidates to adjudicate —
that is the intended friction, and it is why the finding is *named* rather than called a defect.
`--sin-interproc` skips the second pass when you only want the local census; `-q` prints the code
and nothing else.

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

`0.4.0` adds no detector and changes no locus. It adds the reader this README was missing
(`tests/test_readme.py` recomputes the fixtures census and the exit-code contract and fails if this
file disagrees with the code), ships `.pre-commit-hooks.yaml`, and publishes the `H_memo_ast`
refutation above instead of the 24 % it bought.

`0.4.1` publishes the census instead of quoting it. `censo.json` pins every corpus by wheel,
SHA-256 and analysed subtree, so a reader who never had my disk can re-derive the tables; the
own-corpus row (`239` files, `413` stores) is explicitly marked as not pinnable and is excluded
from all cross-package arithmetic. Two of the published rows were also wrong in a way that no
amount of care would have caught: `mypy` was scoped to `mypy/` (the wheel has 336 `.py` files,
the package 195) and `pydantic` had moved a version. Pinning the artifact is what made both visible.

## License

MIT — see [LICENSE](LICENSE).
