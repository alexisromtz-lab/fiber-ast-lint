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

### Closing is not certifying: the code a receipt may publish

The identity `almacenes == pierde + guardadas + acumulacion + posicional + cardinal_sin_medir` is
arithmetic: over a package with no store it evaluates `0 = 0` and closes. That closure is a
tautology, and until `0.4.5` the census published it as `"reconciles": true, "rc": 0` on
`platformdirs` (15 files, 0 stores) and `pyflakes` (23 files, 0 stores) — two rows certifying a
conservation over an empty population. A downstream verifier caught it, not this repository.

The two questions are now separate fields, and only one of them is a signature:

| field | question | `platformdirs` |
|---|---|---|
| `rc` | did the **scan** find anything to report? | `0` — a linter on a file with no loop says nothing |
| `reconcilia` | does the discard census add up? | `true` — `0 = 0` is the identity, and it holds |
| `certifica` | may a **receipt** sign a conservation? | `false` — there is no population to conserve |
| `rc_certificado` | the code an `acta` publishes | `2` (`NO_MEDIDO`) |

`reconcilia` and `certifica` differ on exactly one case — zero stores — and that is the case the
census had wrong. The scan's exit code is deliberately **not** changed: a package with no store is
out of this instrument's scope, not broken, and failing a pre-commit hook for being out of scope is
a false red in the safe direction but still a false red. The receipt contract is the strict one: no
population, no certificate, and `NO_MEDIDO` is a truthful thing to publish.

`tests/test_detect.py` pins the pair on one fixture, `tests/test_cli.py` pins the two codes in one
payload, and `tests/test_censo.py` re-derives the four census surfaces from the terms instead of
believing them: `certifica` is `stores > 0`, `rc_certificado` is `2` exactly when the universe is
empty, `reconciles` holds on every row (`0 = 0` included), and `rc` is `1` iff there is at least one
candidate — a code the linter earned, never a code a receipt may publish.

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
measured on the same own-tooling corpus:

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

Own corpus — the sibling tree's `tools/`, 240 `.py` files, content manifest `d8f332778664c35c`:

| loops | stores | pierde | guardadas | acumulacion | posicional | sin medir | candidates | admitted |
|---|---|---|---|---|---|---|---|---|
| 3 051 | 413 | 13 | 53 | 85 | 23 | 239 | 25 | 22 |

Recomputed 2026-11-26 with `fiber-ast-lint <tree>/tools --json`. The digest is the SHA-256 of
`sha256(content)  path` over the sorted file list, so the row names a subject even though that
subject cannot be fetched.

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

The own-corpus row further up **cannot be pinned the way the others are**: it is internal tooling
that does not ship, so there is no artifact to fetch and no SHA-256 to compare. It is pinned by
**subject** instead — 240 files, manifest `d8f332778664c35c`, recomputable on any checkout of that
tree with the command above. It is evidence about us, not a reproducible claim about this tool, and
it is not used here for any cross-package arithmetic.

### The pin has a reader, and the reader runs in CI

A pin nothing exercises is a testimony with extra fields. `bench/replay_censo.py` fetches each
artifact from PyPI, refuses to measure if its SHA-256 differs from the pinned one **or** from the
digest PyPI publishes for it, unpacks it, and recomputes the six published fields:

```console
$ python bench/replay_censo.py
mypy 2.4.1 mypy:
  identico: files=195 stores=173 pierde=4 candidates=18 admitted=5 column_loci=16
...
pyflakes 4.1.0 .:
  identico: files=23 stores=0 pierde=0 candidates=0 admitted=0 column_loci=0
flake8 7.5.0 .:
  identico: files=33 stores=3 pierde=0 candidates=1 admitted=1 column_loci=1
black 26.10.1 .:
  identico: files=42 stores=23 pierde=2 candidates=2 admitted=0 column_loci=2

REPLAY IDENTICO · 13 filas · instrumento 0.4.4
```

The three trailing rows are the out-of-sample population measured below: they were **added to the
pin after being chosen for density**, so their presence here proves the pin reproduces, not that the
7-package totals grew.

Its exit code says which of four things happened, and the ladder is a supremum, not first-error-wins:

| code | meaning | what it means for the reader |
|---|---|---|
| `0` | every row reproduced | the tables are still claims about artifacts |
| `1` | a published cell did not reproduce | either the code moved or a row is wrong; both are defects |
| `2` | a corpus could not be fetched | `NO_MEDIDO`; **it never masks a `1`** |
| `4` | the bytes are not the pinned artifact | nothing below it is interpretable |

The `replay-censo` job in `.github/workflows/ci.yml` runs it on every push, so the census is checked
on a machine that is not this one — which is the only thing that made the `mypy` and `pydantic`
corrections possible in the first place. `tests/test_replay_censo.py` drives the ladder offline with
a toy corpus, because a reader that can only say "identical" is a mirror.

### A density that reversed when the instrument improved

The previous version of this file reported *1.95 % foreign vs 6.13 % own* lossy density and
concluded the style was a property of the codebase. **That comparison is retracted.** Both figures
came from a classifier that could not see column keys (`acc[fila.columna]`), and 24 of the 30
foreign candidates are exactly that form. Measured today, with one instrument on both sides:

| universe | candidates / stores |
|---|---|
| foreign (7 packages) | 30 / 308 = **9.74 %** |
| own (240 files of tooling, `d8f332778664c35c`) | 25 / 413 = **6.05 %** |

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

### A population nobody had read: three linters, one defect

Every figure above comes from ten rows, and those rows have been read more than once. That is a
training set wearing a census's clothes, and it is the first thing a critical reader will say. So
the prediction was written down **before any artifact was fetched** (it travels in the commit
message that publishes this section):

> **H_out_of_sample.** Over `pyflakes`, `flake8` and `black` at their latest PyPI release — chosen
> by a rule that never looks at code: *the other analyzers of the ecosystem the seven rows already
> sample*, which is the **densest** population available, so the test runs in the hard direction —
> **100 % of the emitted candidates, adjudicated one by one, are non-injective key projections**;
> `reconciles` closes on all three; **no new classifier rule is needed**. Recall is *not* claimed: a
> dense population measures precision, not what the tool misses.

| project | version | files | stores | candidates | admitted | `reconciles` |
|---|---|---|---|---|---|---|
| `pyflakes` | 4.1.0 | 23 | 0 | 0 | 0 | yes — 0 stores, no certificate |
| `flake8` | 7.5.0 | 33 | 3 | 1 | **1** | yes |
| `black` | 26.10.1 | 42 | 23 | 2 | 0 | yes |
| **added** | | **98** | **26** | **3** | **1** | 2/3 |

One correction, published rather than absorbed: the prediction said `reconciles` closes on all
three, and under the definition in force when it was written that was true — `pyflakes` closes
`0 = 0 + 0 + 0 + 0 + 0`. It is a tautology over an empty population: it *reconciles* and it does not
*certify*, which the `0.4.5` law (below) splits into two fields. The row now says `yes` and carries
no certificate, so the out-of-sample population is **26 stores over two packages**, not three. The
pre-registered sentence stays verbatim above: rewriting a prediction after seeing the answer is how
predictions stop being predictions.

The three rows are pinned in [`censo.json`](censo.json) by wheel and SHA-256 like the rest, and they
are **not** folded into the `599 files / 308 stores` above. The percentages are not recomputed
either: adding rows to a denominator *after choosing them for their density* is the same selection
the table exists to refuse.

Three candidates, three adjudications, no surprises:

| locus | key | what would make the key unique | verdict |
|---|---|---|---|
| `flake8/plugins/finder.py:327` | `loaded.entry_name` | the reporter's entry-point name — and nothing tests it | **real loss**, silent |
| `black/parsing.py:113` | `grammar.version` | one version per grammar object | benign, and `LATENTE` |
| `black/parsing.py:132` | `grammar.version` | same dict, second `except` arm | same locus, filed twice by design |

**The `flake8` one is a defect.** `_classify_plugins` writes `reporters[loaded.entry_name] = loaded`
inside a loop, and nothing tests membership first:

```console
$ grep -rn "reporters" --include=*.py flake8
flake8/plugins/finder.py:317:    reporters = {}
flake8/plugins/finder.py:327:            reporters[loaded.entry_name] = loaded
flake8/plugins/finder.py:350:        reporters=reporters,
flake8/plugins/reporter.py:34:        format_plugin = reporters[format_name]
flake8/options/parse_args.py:48:        formatter_names=list(plugins.reporters),
```

No `in reporters`, no `setdefault`, no post-hoc duplicate check. Two plugins registered under
`flake8.report` with one entry-point name leave one reporter **unreachable**: it never reaches
`reporter_names()`, so it does not even appear among the `--format` choices, and nothing is
reported. The dict escapes the function (`Plugins(reporters=…)`), `_classify_plugins` has one
caller, and nobody calls `len(reporters)` — which is exactly why this locus is `CANDIDATO` while the
two `black` ones are `LATENTE` at the same shape. Severity here is about whether a loss can reach a
consumer, not about how suspicious the line looks.

`black` is the control in the other direction: `errors[grammar.version] = InvalidInput(…)` appears
once per `except` arm, and the keys *are* distinct in the population actually instantiated
(`python_grammar`, `python_grammar_async_keywords`, `python_grammar_soft_keywords`). The tool files
both anyway — it cannot read the grammar table — and demotes them because `errors` never leaves
`lib2to3_parse` and its only observer is `max(errors)`. Same adjudication line as the 24 column loci,
reached without special-casing anything.

`pyflakes` is the negative control: 73 loops and **zero** stores, because its dict writes go through
the loop target itself (`for scope in …: scope[k] = v`) or through attributes, and neither is an
accumulator. Zero stores, therefore zero candidates — a measured zero, not a missing one.

The three shapes are distilled into `tests/test_out_of_sample.py`, which recomputes the split
(`CANDIDATO` / `LATENTE` / no store) on every run, offline. The upstream disclosure for `flake8` is
drafted in [`docs/FLAKE8_REPORT_DRAFT.md`](docs/FLAKE8_REPORT_DRAFT.md) and is **not filed**.

### Four domains the census never touches, and the denominator that was wrong

The section above tests *precision*, and it cannot test *yield*, because its three packages were
chosen for density: they are more linters. The first question a buyer asks is the opposite one —
*how much work does my repository generate?* — and it needs strata the census does not contain.

The rule, fixed before a line of their code was read: **one package per domain** — command line
(`click`), HTTP client (`requests`), attribute model (`attrs`), tabulation (`tabulate`). Latest PyPI
wheel of each on 2026-11-26, pin checked against PyPI's own digest, named subtree analysed, no
install, no network during analysis.

What was **not** fixed is a number. These five rows were measured before any prediction existed, so
this section is **exploratory** and publishes no constant — the mirror image of the paragraph above,
where the prediction came first and survived. The status travels in
[`fuera-de-dominio.json`](fuera-de-dominio.json) as a field the tests read, not as prose.

| package | version | scope | files | stores | `sin_len` | candidates | admitted | `reconciles` |
|---|---|---|---:|---:|---:|---:|---:|---|
| `attrs` | 26.1.0 | `attr/` | 13 | 28 | 26 | **11** | 9 | yes |
| `attrs` | 26.1.0 | `attrs/` | 6 | 0 | 0 | 0 | 0 | yes — 0 stores, no certificate |
| `click` | 8.5.1 | `click/` | 17 | 6 | 2 | 0 | 0 | yes |
| `requests` | 2.34.2 | `requests/` | 19 | 9 | 6 | **3** | 1 | yes |
| `tabulate` | 0.10.0 | `tabulate/` | 1 | 4 | 1 | 0 | 0 | yes |
| **added** | | | **56** | **47** | **35** | **14** | **10** | 5/5 |

`attrs` ships two trees and both are analysed: `attr/` is the package, `attrs/` the newer namespace,
and the empty row is published as an empty row — a zero with a certificate, not a blind spot.

**The denominator was wrong.** Across the 13 rows of [`censo.json`](censo.json) and these 5 — 18
rows over 18 distinct artifacts — `candidates ≤ sin_len` holds without exception. A candidate can
only be born of a store whose cardinality is not published, so `almacenes` is the pre-filter
population and `sin_len` the post-filter one, and a quotient over `almacenes` divides one population
by the other. Over the right denominator:

| population | stores | `sin_len` | candidates | cand / stores | cand / `sin_len` |
|---|---:|---:|---:|---:|---:|
| 13 census rows | 308 | 209 | 30 | 9.74 % | 14.35 % |
| these 5 rows | 47 | 35 | 14 | 29.79 % | 40.00 % |

The two samples are **not added and not averaged**: the census samples development tooling and this
one samples four other domains, so a pooled mean would be a mean over a stratum the table chose.
What the pair says is the thing a rate cannot say — the yield is a property of the *code*, not of
the instrument, and it moves by a factor of three between two strata of the same language.

**A site is not a finding.** The 14 candidates are 11 sites of one key in `attr/` — `a.name`, in
`asdict`, `_collect_base_attrs`, `_collect_base_attrs_broken`, `_ClassBuilder.add_setattr` and
`_make_init_script` — plus three single sites in `requests/`. Counted as constructs that a human
adjudicates, they are **8**, not 14; the same key over five places is one judgment and five loci.
`tabulate` writes `d[key] = row` over a list it derived, and loses 2 stores doing it, with zero
candidates: losing a store is not finding one.

**What it costs, measured.** The five scans are 2.06 s of wall clock for 56 files, minimum of three
runs each, interpreter start included (`0.083 s` of the `attrs/` row is almost all start). At that
price the scan is not the audit — adjudicating the 8 constructs is — and the scan's real commercial
use is the other way round: **it is the instrument that prices the job**, because the load ranges
from 0 loci in 10 stores (`click` + `tabulate`) to 11 in 28. A quote written before that scan is a
guess; after it, it is a count.

### A batch named before it was fetched: four predictions, four survivors

Everything above is exploratory, and it says so in a field: the five rows were measured before any
prediction existed, so they may name directions and may not name rates. This batch inverts the
order. `prediccion-batch-2.json` was committed at `9a85d69` — with the five packages named, the four
claims written and their `cota_error` declared — **before a single byte of the wheels existed**. The
commit is the receipt for the order; the file carries the digest of the prediction so a later edit
cannot pass for it.

| package | version | files | stores | `sin_len` | candidates | cand / `sin_len` |
|---|---:|---:|---:|---:|---:|---:|
| jinja2 | 3.1.6 | 25 | 12 | 7 | 1 | 14.3 % |
| urllib3 | 2.8.0 | 36 | 7 | 3 | 0 | 0 % |
| packaging | 26.4 | 22 | 18 | 15 | 5 | 33.3 % |
| idna | 3.20 | 10 | 0 | 0 | 0 | — |
| six | 1.17.0 | 1 | 0 | 0 | 0 | — |
| **added** | | **94** | **37** | **25** | **6** | **24.0 %** |

| | claim | declared | measured | |
|---|---|---|---|---|
| P1 | `candidates <= sin_len` in every row | 5 of 5 | 5 of 5 | passes (control) |
| P2 | per-row `candidates / sin_len <= 0.50` | 5 of 5 | 3 of 3 with `sin_len > 0` | passes |
| P3 | pooled quotient in `[0.10, 0.45]` | 0.25 | 0.240 | passes |
| P4 | seconds in `[0.0238·F, 0.055·F]` | `[2.24, 5.17]` | 2.75 | passes |

P1 is declared a **control**, not a finding: the mechanism makes it nearly a theorem, and confirming
a theorem informs nothing. The one with content is P3 — the declared point was 0.25, the measured
0.240, and the band was written before knowing it would agree that closely. What the four survivors
do **not** establish is a rate for the population: the batch is one I chose, and a band wide enough
to survive is a band wide enough to be uninformative about its own width.

Two things the batch found that no prediction asked for. `packaging` contributes a **second species**
of candidate — `PROYECCION_ARRIBA_CON_PERDIDA`, five of the six, four of them inside `parse_email` —
where batch 1 was 12 of 14 `SELECCION_COLUMNA_BUCLE`; the earlier stratum simply did not contain the
other mechanism, which is the argument against reading one sample as the shape of the instrument.
And the six candidates are **three** keys: `extension.identifier` once, `normed_group_name` once,
and `name` four times in one function. Adjudication is priced per group, so the quote is 3 decisions.

**The cost model chose its regressor.** Fitted on the ten out-of-sample rows, files give
`s = 0.2034 + 0.01847·ficheros` with `R² = 0.457` and a worst residual of 279 %; loops give
`s = 0.1578 + 0.00649·bucles` with `R² = 0.845` and 120 %. Loops explain almost twice the variance
and neither explains the clock: between 0.08 s and 0.16 s of interpreter start dominates a scan this
size. So the honest quote is a band with a fixed term and a per-loop term — and `R² = 0.845` over ten
points with two parameters is an ordering between two regressors, not a model. **That ordering was
retired by the next batch**: see *A batch that killed its own unit of invoice*, below.

**The reader had the assumption, not the object.** `six` is a module, not a package, and the scanner
accepts a file — it checks `is_file()` before `is_dir()`. `bench/replay_censo.py` demanded a
directory, so it declared `RUPTURA` on a correct pin. That is the class of defect this repository
keeps finding: a fact about the reader mistaken for a fact about the subject. Fixed on both branches
and pinned by `tests/test_replay_scope.py`, whose two tests each kill the `is_dir()` mutant of their
own branch.

### A batch that killed its own unit of invoice

The batch before this one left a sentence that could be sold: adjudication is priced per group, and
the clock is priced per loop. Both claims rested on five packages. `prediccion-batch-3.json` was
committed at `a713ad2` naming five *other* packages — `charset-normalizer`, `pyparsing`, `pygments`,
`tomli`, `colorama` — and four claims, **before any byte was fetched**; `bench/lote.py` is the reader
that goes and gets them, so the batch no longer depends on a shell transcript.

| package | version | files | stores | `sin_len` | loops | sites | keys | s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| charset-normalizer | 3.5.3 | 12 | 7 | 2 | 43 | 0 | 0 | 0.263 |
| pyparsing | 3.3.3 | 17 | 9 | 9 | 82 | 4 | 1 | 0.701 |
| pygments | 2.21.0 | 343 | 51 | 44 | 369 | 2 | 2 | 4.941 |
| tomli | 2.5.0 | 4 | 0 | 0 | 6 | 0 | 0 | 0.100 |
| colorama | 0.4.6 | 13 | 0 | 0 | 9 | 0 | 0 | 0.136 |
| **added** | | **389** | **67** | **55** | **509** | **6** | **3** | **6.141** |

| | claim | declared | measured | |
|---|---|---|---|---|
| P1 | every row reconciles, `candidates <= sin_len` | 5 of 5 | 5 of 5 | passes (control) |
| P2 | ≥ 3 of 5 rows have a repeated key, and pooled sites/keys ≥ 1.3 | ≥ 3 rows | 1 row; 6/3 = 2.0 | **refuted on the count** |
| P3 | `measured / predicted` in `[0.55, 2.60]` for rows with ≥ 50 loops | 0 rows outside | 1.016 and 1.936 | **not readable** |
| P4 | loops still beat files out of sample, by ≥ 0.20 in `R²` | ≥ 0.20 | −0.0177 | **refuted, order inverted** |

**What died was the frequency, not the fibre.** Six sites closed by three decisions is the same
quotient as the previous batch — 2.0, exactly. What the previous batch had no right to infer from one
case is that collisions are *common*: across ten rows that have any site at all, two have a repeated
key. The fibre is real and its prevalence was never measured; P2 asserted the second and died on it.

**P3 is the one that cannot be read, and that is the finding.** Its band says
`measured / predicted`, and the extremes it was stretched from — 0.70 and 2.20 — had been written down
in the other orientation. Under its own words the two rows in the domain land at 1.016 and 1.936 and
survive; read as `predicted / measured` the large row is 0.517 and dies. One key, two subjects: a
prediction whose orientation is chosen after the datum is not a prediction. The schema now demands
`ratio_orientation` on any claim that compares a measurement to a model, and
`tests/test_censo_fuera.py` fails a new prediction file that omits it; this file is the documented
exception, pinned as such so it cannot become a silent one.

**The loop model is gone.** Re-fitted on the fifteen out-of-sample rows:

| regressor | model | `R²` | worst residual |
|---|---|---:|---|
| bytes | `s = 0.12027 + 0.0000039·bytes` | 0.9822 | 361 % (attrs, 6 files) |
| files | `s = 0.23382 + 0.0138009·ficheros` | 0.9664 | 281 % (attrs, 6 files) |
| loops | `s = -0.12141 + 0.0126910·bucles` | 0.9487 | 246 % (attrs, 6 files) |

Loops drop from best to worst. The previous batch fitted files from 1 to 36; this one adds a project
of 343 files carrying 369 loops — 1.08 loops per file against 5.6 in `jinja2`. The advantage was the
sample's narrow range, not the object's structure. Note the negative intercept: a line that says a
scan of nothing takes minus a tenth of a second is not a model, it is a fit. All three regressors fail
on the same row, the four-file project, where interpreter start is larger than the scan. So the quote
is a fixed term plus size, and relative error is only punitive above roughly ten files — **nothing is
priced per loop**. *Fixed term plus size* does not survive either: see the next section, where the byte
turns out to identify neither the subject nor the work.

**The rate is a property of the project, not of the instrument.** Pooled `candidates / sin_len`:

| batch | candidates | `sin_len` | pooled |
|---|---:|---:|---:|
| 1 (exploratory) | 14 | 35 | 40.0 % |
| 2 (confirmatory) | 6 | 25 | 24.0 % |
| 3 (this one) | 6 | 55 | 10.9 % |
| **cumulative** | **26** | **115** | **22.6 %** |

Within the single stratum "runtime library of a backend" the per-project quotient runs from 0 of 2 to
11 of 26. 22.6 % over 115 stores is defensible as a summary of a heterogeneous population and is not
a rate to quote per project.

Two rows certify their own emptiness (`tomli`, `colorama`: zero stores, `rc_certificado = 2`,
`certifica = false`), and five of the six sites are `PROYECCION_ARRIBA_CON_PERDIDA` — the species
batch 1 never saw in 14 sites. Six sites do not support a species ratio; the direction is worth
recording and the number is not.

### The invoice is not denominated in seconds

Batch 3 closed with a pricing rule — *fixed term plus size* — derived from an `R²` of 0.9822. Two
things were wrong with it and only one of them was arithmetic. `R²` measures how the rows order, not
how far a prediction lands: the leave-one-out relative error of that same fit runs 14 % to 80 %. And
the fitted variable, artifact bytes, is not the thing the scanner works on.

So this batch stops fitting and asks the prior question: **is the clock a subject at all?** Twenty
subjects measured with two clocks in the same run — wall (`perf_counter` around the subprocess) and
CPU of the child (`getrusage(RUSAGE_CHILDREN)`, `utime + stime`, delta around the same call) — five
repetitions each. Fifteen of the twenty are the pinned subjects of batches 1–3, re-downloaded and
re-verified by sha256, so the comparison is paired: same subject, two clocks, one difference.

| id | claim | band | measured | verdict |
|---|---|---|---|---|
| P1 | control: pins and counts replay | 15 of 15 | 15 of 15 sha256, 15 of 15 counts | **survives** |
| P2 | CPU clock quotable | LOO median ≤ 10 %, max ≤ 25 % | median **16.7 %**, max **81.5 %** | **refuted** |
| P3 | the noise is the wall clock's | median spread ratio ≥ 2.0 | **2.77** (wall 3.03×, CPU 1.12×) | **survives** |
| P4 | the intercept is start-up | ratio in [0.5, 2.0] | **0.66** (wall: 0.38) | **survives** |
| P5 | extrapolates to five new packages | every row ≤ 25 % | 4 of 5; `docutils` **66.3 %** | **refuted** |

The CPU clock wins every paired comparison — lower error than wall (median 16.7 % against 26.4 %),
`R²` 0.9404 against 0.7327 over all twenty rows, and an intercept that matches the measured start-up of
the tool on an empty tree to within a factor of 1.5 while the wall clock's misses by 2.6×. It still
does not quote, and the reason is not the clock:

| same artifact, two sessions | published | CPU today | wall today | CPU / published | wall / published |
|---|---:|---:|---:|---:|---:|
| `pygments` (343 files, 1 250 147 B) | 4.941 s | 10.370 s | 16.204 s | 2.10× | 3.28× |

Across the fifteen re-measured subjects the drift is **1.23×–2.27× in CPU** and **1.26×–3.93× in
wall** (medians 1.81× and 2.50×). Nothing about the work changed: same `sha256`, same file count,
same candidate list, byte for byte. A tariff in seconds has to absorb that factor in the price, and a
number that absorbs an unknown factor is a margin, not a price.

The two refutations are defects of the **regressor**, and they are worth naming because a fit cannot
see them. `attrs` ships one wheel and the tool can scan either subtree of it: `attr/` (13 files,
0.654 s of CPU) or `attrs/` (6 files, 0.126 s). Both rows carry `bytes = 67548`, because bytes
measures the artifact and not the subject — a 5.2× difference in work under one value of the
variable. `docutils` goes the other way: 634 701 B in 129 files cost 8.859 s of CPU, more than
`setuptools` at 876 263 B in 227 files (8.279 s). Bytes see neither which subtree you scan nor how
dense the code is.

**What this buys, and what it withdraws.** What reproduced between sessions was the count: fifteen of
fifteen subjects returned the same files, stores, loops, buckets and signatures, and no subject
returned the same time. So the unit of the invoice is the **unit of work** — a site closed by its key
(batch 3) inside an area certified by its receipt (`conservation/1`) — and the clock is a scheduling
input: how long delivery takes, not what it costs. The rule this batch withdraws is batch 3's own
"fixed term plus size": the byte neither predicts the work nor identifies the subject. What it does
not withdraw is CPU over wall for planning — that survived, at 1.6× less error.


Three candidates establish precision and nothing else — a sample that small cannot say whether a
defect of a given class is *caught*. So the other direction, measured on truth I constructed, which
is weaker than the wild and stronger than nothing: five plants appended to real modules of the pinned
`flake8` 7.5.0 tree, each accumulator returned by its function and called once from a helper.

| plant | what the body does | form the tool names | verdict |
|---|---|---|---|
| `statistics.py:137` | `indice[entry.code] = entry` | `SELECCION_COLUMNA_BUCLE` | **`CANDIDATO`** |
| `processor.py:461` | `clave = linea.strip()` then `indice[clave] = linea` | `PROYECCION_ARRIBA_CON_PERDIDA` | **`CANDIDATO`** |
| `processor.py:468` | `indice[linea.lower()] = linea` | `PROYECCION_VISIBLE` | **`CANDIDATO`** |
| `statistics.py:146` | `if entry.code not in indice: indice[entry.code] = entry` | — | silent, `guardadas` |
| `statistics.py:154` | `cuenta[entry.code] = cuenta.get(entry.code, 0) + 1` | — | silent, `acumulacion` |

Totals on the mutated tree against the pristine one: `almacenes` 3 → 8 — exactly the five plants, no
more — `guardadas` 0 → 1, `acumulacion` 0 → 1, candidates 1 → 4, and `archivos` **33 → 33**. The row
that was already there (`finder.py:327`) reports the same locus, same form, same escape. The buckets
still close and `reconciles` is true on both sides: `8 = 0 + 1 + 1 + 0 + 6`.

The triplet is the point, and it is why the two controls are keyed by `entry.code` like the first
plant instead of by something obviously safe. Three bodies, one key expression, three verdicts:
the classifier is not reacting to the *shape of the key*, it is reacting to whether a lost row can
reach a consumer. A rule that fired on all three would pass any fixture suite that only plants
defects.

**Limit, stated rather than implied:** the truth here is mine. A plant shows that the classifier
*can* fire on each form in a real module; it says nothing about how often the shape occurs in the
wild. That is what the seven-row census and the out-of-sample rows measure — and neither of them is
recall. `tests/test_kill_matrix.py` recomputes the matrix offline on the five shapes.

### The quote that refuses to give a number

Batch 4 ended with the invoice denominated in counts and a clock published beside it. The obvious
next step is to turn that clock into a price, and the obvious way to do it is to hand a client a
number. This batch hands over three things instead, and the third one is a refusal.

**The control found the defect, not the reading of the artifact.** Re-running
`bench/replay_censo.py` over the batch-4 file died with `KeyError: 'sha256'` on the fifth row added
last batch. Five rows — `wcwidth`, `sqlparse`, `pyflakes`, `docutils`, `setuptools` — published
`sha256_medido`, a *measurement*, where the file's contract asks for `sha256`, a *pin*: the thing a
reader compares against. They were transcriptions, not rows, and a third party could not re-read
them. Repaired by pointing each pin at its own measurement and recording the repair in the
artifact's `defect_found` block. The replay then returned **20 `identico:` lines, rc 0**, up from
15 rows that were actually legible. A control that only ever runs against foreign artifacts finds
only foreign defects.

**The band is conformal, and it is narrower than the prediction said.** Fifteen calibration rows,
leave-one-out residuals, quantile at index `ceil((n+1)(1-α))-1 = 12` of 15 with `α = 0,2`:

| | value |
|---|---:|
| `q` (half-width, relative) | **0,4258** |
| max LOO residual | 0,8147 |
| residuals, sorted | 0,02 · 0,04 · 0,04 · 0,05 · 0,09 · 0,12 · 0,14 · 0,17 · 0,27 · 0,28 · 0,30 · 0,33 · **0,43** · 0,46 · 0,81 |

The prediction asked for `q ≥ 0,50` and this is 0,4258, so **P2 is refuted**. The reason is
structural, not lucky: the quantile lands three positions before the maximum, because the maximum
is one subject (`pygments`, 0,8147) and the quantile does not need it. A band sized to the worst
subject in the calibration set would have been 0,81 wide — the pessimistic prediction was what you
get by confusing a maximum with a quantile.

Coverage on the five held-out rows is **4 of 5**, exactly the `1 - α` the method promises:

| package | bytes | `cpu_min` | predicted | rel. error | inside |
|---|---:|---:|---:|---:|:--:|
| wcwidth | 329 353 | 2,8333 | 2,8026 | 0,0110 | yes |
| sqlparse | 51 200 | 0,4919 | 0,5042 | 0,0243 | yes |
| pyflakes | 66 258 | 0,6791 | 0,6286 | 0,0804 | yes |
| docutils | 634 701 | 8,8588 | 5,3258 | 0,6634 | **no** |
| setuptools | 876 263 | 8,2786 | 7,3219 | 0,1307 | yes |

The one that falls outside is `docutils` again — the subject batch 4 already named as a regressor
failure, 634 701 B and 129 files costing more than a larger artifact. The band holds for subjects
that look like the calibration set, and this table says out loud when one does not.

**What the instrument will quote, and what it will not.** `bench/cotizar.py` returns counts, a
manifest digest, its own two clocks and a price:

```
sujeto          src/fiber_ast_lint   7 files · 55 596 py bytes
manifiesto      8093a1f2558cf42f…
conteos         sitios 2 · claves 2 · ficheros 7
reloj           cpu_min 0,4303 s · wall_min 0,5071 s (3 repetitions, identical counts)
tiempo          NO_MEDIDO
precio          NO_COTIZADO        rc 2
```

`tiempo` is `NO_MEDIDO` because the CPU model was fitted on **artifact bytes** and the subject here
is a **disk tree**: two different objects under one word, which is the `attrs` defect named in the
batch-4 section. The instrument says which subject it lacks rather than returning a number from a
model that never saw one. `precio` is `NO_COTIZADO` because no tariff is shipped with coefficients:
arithmetic over a coefficient the repository invented would be a price, and a price is not a
measurement. `tarifa.ejemplo.json` carries `firmada: false` for exactly that reason — the same file
with `firmada: true` yields `total = 2·1500 + 2·800 + 7·0 = 4600`, computed by the function that
emits it and never typed by hand. The example exists so the arithmetic is exercised; it is not a
quotation.

**The line worth keeping:** counts reproduced 15 of 15 across sessions and now replay 20 of 20, so
they are what a quote is denominated in. Time is a band with a stated coverage and a subject it does
not cross. The invoice is denominated in work, and the clock is an input to scheduling — that is the
whole of what this batch certifies.

### The model's subject

Batch 5 named its own wall in one sentence: the CPU model was fitted on **artifact bytes** and the
subject a client brings is a **disk tree**, so the quote refused. A refusal is only correct if the
wall is where it said it was. This batch moves the regressor and nothing else.

**Nothing is timed again.** The twenty clocks of batch 4 are reused exactly as they stand — same
subjects, same instrument, same session of origin — and the only change is the `x`: the bytes of
Python the scanner actually walks, summed over the subtree each row declares. Two fits over the same
twenty `y` values make the comparison paired, so any difference in error belongs to the change of
regressor.

| regressor | `a` | `b` | R² | LOO p50 | LOO max | `q` | coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| artifact bytes | 0,08108 | 8.263263e-06 | 0,9891 | 0,1666 | 0,8147 | 0,4258 | **4/5** |
| scanned `.py` bytes | 0,16778 | 2.236874e-06 | 0,9931 | 0,1506 | **0,3936** | 0,3018 | **2/5** |

The first row is a reproduction, not a new claim: refitting on artifact bytes returns batch 5's
`q = 0,4258` and `max = 0,8147` to the digit. The second row is the batch. The worst
subject stops being the worst — 0,3936 against 0,8147 is **P1 surviving** —
and the median moves from 0,1666 to 0,1506, **P2 surviving** with
0,0164 of margin against the 0,167 threshold.

**The regressor that could not see.** `attrs` ships two subtrees inside one wheel, `attr/` and
`attrs/`, both 67 548 artifact bytes, clocks 0,6538 s and
0,1259 s. On artifact bytes the model is blind by construction: the same `x` gives
the same prediction, ratio **1,00×**, and the measured order is lost. On
scanned bytes the two subtrees are 191 766 B and 1 557 B, and
the model returns 0,5967 s against 0,1713 s:
ratio **3,484×**, in the measured order. That is **P4 surviving**, and it is
the sharpest thing this batch says — a regressor that maps two different objects to one number cannot
be repaired by a better band, only by a different `x`.

**docutils refuted the one prediction that named it.** P3 said the subject with the most code
relative to its artifact would come back inside the band. It goes the other way: 0,6634 →
**1,1020** against a `q` of 0,3018. Its
1 809 028 scanned bytes predict
4,2144 s and it costs 8,8588 s
— docutils is slow *per scanned byte*, and changing the regressor removed the one thing artifact size
was doing to hide it. Coverage falls to 2 of 5 with it:

| package | scanned bytes | `cpu_min` | predicted | rel. error | inside |
|---|---:|---:|---:|---:|:--:|
| sqlparse | 146 489 | 0,4919 | 0,4955 | 0,0072 | yes |
| pyflakes | 296 870 | 0,6791 | 0,8318 | 0,1836 | yes |
| wcwidth | 1 739 138 | 2,8333 | 4,0581 | 0,301809 | **no** (boundary) |
| setuptools | 2 611 450 | 8,2786 | 6,0093 | 0,3776 | **no** |
| docutils | 1 809 028 | 8,8588 | 4,2144 | 1,1020 | **no** |

One of those is not a clean "no": `wcwidth` lands at 0,301809 against
`q = 0,3018`, outside by nine parts in a million — a boundary case, declared as one rather than
counted as a success or a failure. A model can be better on every calibration row and worse out of
sample, and here the reason is computable: scanned-over-artifact bytes runs from
**0,0231×** (`tomli`) to
**5,2805×** (`six`). Artifact bytes are not a proxy for scanned
bytes at any multiplier; they are a different quantity that happens to correlate well inside the
fifteen rows that fitted it.

**The finding that arrived sideways: the band is barely twice the instrument.** Quoting the
local tree with the new model gives `predicho 0,2921 s` and an interval
`[0,2040, 0,3803]`; today's reading (0,2103) lands inside it
— **P5 surviving** on its own terms, by 3 % above the lower bound. But the same tree, timed ten
times in each of 9 consecutive blocks, does this:

```
jitter per block   0,0444 · 0,0432 · 0,0056 · 0,0039 · 0,0039 · 0,0115 · 0,0048 · 0,0056 · 0,0036   s
median             0,0056 s      worst 0,0444 s      best  0,0036 s
band half-width    0,0882 s      -> the worst block clears it by 1,99×
```

A twelvefold range inside one session, on one subject, from one instrument. The band of record still
clears it, and that is not the same as saying the band is larger than the machine: a block measured
earlier in this same session reached **0,0963 s**, over the half-width, and that reading is a
transcription here rather than a file — which is precisely why the two populations have to be
measured in the same act, not in two acts that are minutes apart. Two populations again, the same law
as a partition of a single one: the band measures model error, the jitter measures the machine, and
an interval that only reports the first has collapsed the difference that decides whether it means
anything.

**So what may be invoiced.** Counts. The invoice stays denominated in sites, keys and files —
replayed 20 of 20, with the scanner's own `files` count and an independent `.py` glob agreeing on
**20 of 20** rows: two instruments,
one universe, not two columns of one calculation. The clock becomes a capacity input for a disk tree
instead of a refusal — `bench/cotizar.py --modelo codigo` returns a banded time — and it ships with
the size below which the jitter, not the model, is what the interval would be made of:
**0,1471 s** of predicted time, where the half-width would equal the worst
block measured here. `precio` stays `NO_COTIZADO`: no tariff ships with coefficients, and that
refusal is the honest reading of a `firmada: false` file.

The whole batch is one command, and it re-derives every figure above from the wheels rather than
transcribing them:

```bash
PYTHONPATH=src:bench python bench/sujeto.py --dir /tmp/censo6 --artefacto
```

It writes `fuera-de-dominio-6.json`, the artifact of record: the twenty rows with their pins, both
fits, both bands, the jitter and the quote. Every number in this section is read from that file by
the test suite, so a figure that stops matching it fails CI instead of ageing quietly.

### The instrument's noise floor, per subject

Batch 6 ended on an admission it could not pay for: the half-width had been calibrated on **one**
tree, and a block of that same session had already beaten it. Publishability is a claim about a
subject, so this batch takes it to five. The five were fixed by *predicted* time — the batch-6 fit
`a + b·bytes`, never a clock — and each was given the same protocol: nine blocks of ten readings,
a reading being the minimum of three full scans, with `q` and both coefficients frozen at the
values batch 6 published. Four hundred and fifty clocks over five thousand seconds of declared
wall, no external clone, nothing written outside this repository.

**Zero of five are publishable.** The rule the artifact applies is the one batch 6 wrote down,
neither looser nor tighter: a subject is publishable when `q × predicted` exceeds its worst block
jitter, that is when `jitter / predicted` stays under 0,3018.

| package | scanned bytes | predicted | worst block jitter | half-width | jitter / predicted | publishable |
|---|---:|---:|---:|---:|---:|:--:|
| attrs | 1 557 | 0,1713 | 0,0651 | 0,0517 | 0,3800 | **no** |
| tomli | 30 691 | 0,2364 | 0,1713 | 0,0713 | 0,7246 | **no** |
| pyflakes | 296 870 | 0,8318 | 0,5036 | 0,2510 | 0,6054 | **no** |
| setuptools | 2 611 450 | 6,0093 | 4,9052 | 1,8136 | 0,8163 | **no** |
| pygments | 4 577 209 | 10,4064 | 3,5568 | 3,1407 | 0,3418 | **no** |

The narrowest refusal is the largest subject, at 0,3418 — over `q` by an eighth — and the widest
is `setuptools`, at 0,8163, over it by 2,70×. Neither end of the size range buys publishability,
which is the finding: size is what the model is denominated in and not what the gate is. Two of
the three pre-registered claims were written to be falsified, and both were:

- **J1 survives.** The smallest subject by predicted time, `attrs/attrs`, was predicted to come
  back over `q` — the interval there is noise wearing the format of an interval. Measured 0,3800
  against 0,3018.
- **J2 falls.** The two largest subjects were predicted to come back under 0,05, on the argument
  that a big subject has band to spare. They came back at 0,8163 and 0,3418 — 16,3 and 6,8 times
  the threshold, not a few per cent over it.
- **J3 falls.** The median block jitter was predicted to land between 0,003 s and 0,05 s in all
  five subjects, on the argument that the floor is a property of the machine and the machine did
  not change. It landed at 0,0221 · 0,1286 · 0,3570 · 1,0867 · 0,0703 s: the smallest subject sits
  inside that window and the other four clear its upper edge by 1,4, 2,6, 7,1 and 21,7 times.

Both failures say the same thing, and it is not that the machine is noisy. It is that the noise is
not a constant of the machine:

- scanned bytes span **2 939,8×** from the smallest subject to the largest, and the absolute
  jitter spans **75,3×** — 39,0 times less than the span it would cover if it were a property of
  the code.
- the jitter per megabyte falls from 41,8112 s/MB on `attrs` to 0,7771 s/MB on `pygments`, a
  factor of 53,8: the larger the tree, the smaller the noise relative to it.
- the quantity that stays put is the one nobody had written down, `jitter / predicted`: between
  0,3418 and 0,8163, mean 0,5736, a spread of 2,39× across a population that varies by three
  orders of magnitude in size.

**The noise enters only upward, which is why the statistic chosen for it has no ceiling.** The 450
readings behind that table, per subject:

| package | best of 90 | median | worst | worst / best | block minima, best to worst | readings above 2× best |
|---|---:|---:|---:|---:|---:|---:|
| attrs | 0,0834 | 0,1319 | 0,1485 | 1,7806 | 1,5264 | 0/90 |
| tomli | 0,1286 | 0,2288 | 0,3064 | 2,3826 | 1,7698 | 21/90 |
| pyflakes | 0,5011 | 0,6973 | 1,0125 | 2,0206 | 1,3858 | 1/90 |
| setuptools | 5,5739 | 5,9811 | 11,9140 | 2,1375 | 1,5818 | 5/90 |
| pygments | 7,1131 | 7,2910 | 11,1724 | 1,5707 | 1,0906 | 0/90 |

An interruption can add time and can never take it away, so the minimum is the only estimate of
the code's cost that survives contention; `max − min`, the batch-7 statistic, is an estimate of
the scheduler. Taking the worst of nine blocks takes the maximum of a one-sided quantity, and a
one-sided quantity has no ceiling by construction: more blocks can only widen it. That is the
whole difference between a noise floor and a band, and it is why the answer is *no* five times
instead of four.

**The figure that closes the argument.** Batch 6's own subject — the local tree, worst block
jitter 0,0444 s, predicted 0,2921 s — sat at `jitter / predicted = 0,1520`, while `q / 2 =
0,1509`. The tree the half-width was calibrated on lay within eight parts in a thousand of the
point where band and jitter are the same size, and that is where the published minimum of 0,1471 s
comes from: it is that act's jitter divided by `q`, not a property of the scanner. Today's mean is
0,5736, which is 3,77× the condition `q` was read in — same scanner, same machine, a different
act.

So `publicable` stops being a figure a benchmark hands to a quote and becomes a reading the quote
has to take itself. That is the next order, already written: `prediccion-batch-8.json` asks
whether the floor can be sampled **inside** the act that quotes — one subject, its own nine
blocks, its own `jitter / predicted` — refusing to publish when that ratio does not stay under
`q`. The point is the cost: the gate would then be paid in the act instead of in a second act
apart from it, which is the only way a quote can carry its own resolution.

The batch is one command, and it re-derives every figure above rather than transcribing it:

```bash
PYTHONPATH=src:bench python bench/ruido.py --dir /tmp/censo7 --artefacto
```

It writes `fuera-de-dominio-7.json`: the five subjects with their pins, their ninety readings
each, the noise of every block, the verdicts against the frozen prediction and the comparison of
scales. Every cell of both tables above is read from that file by the test suite, so a figure that
stops matching the artifact fails CI instead of ageing quietly.

### The floor is a reading of the act

Batch 7 refused five subjects measured in one window and could not say why the refusal did not order
by size: the largest tree came back the tightest, so the gate did not look like a property of the
code — but nothing had yet shown the quantity *moving* on a subject that did not move. This batch is
one subject and two acts. Act A is the ninety clocks batch 7 already paid on `pyflakes/pyflakes`;
they are reused exactly as they stand, never re-timed, so the comparison is paired. Act B is the
same protocol, the same pin and another window: 90 new clocks, 164,3 s of wall, run once and
published whatever it said.

**The subject is provably one object, by two measurements.** The 296 870 scanned bytes match the
pin, and the wheel's `sha256` is the one batch 7 recorded: the two checks that would have to
disagree for the tree to be another one. So the act is the only variable — and act B came back at
`jitter / predicted` = 0,2498, against 0,6054 in act A.

| statistic | act A | act B | A / B |
|---|---:|---:|---:|
| minimum of 90 readings | 0,5011 | 0,2384 | 2,10 |
| median | 0,6973 | 0,3286 | 2,12 |
| maximum | 1,0125 | 0,5534 | 1,83 |
| worst block jitter | 0,5036 | 0,2078 | 2,42 |
| median block jitter | 0,3570 | 0,1342 | 2,66 |
| `jitter / predicted` | 0,6054 | 0,2498 | 2,42 |
| `min / jitter` | 0,9950 | 1,1473 | 1,15 |

The minimum is the discriminant, and it needs no threshold at all. An interruption can add time and
can never take it away, so the smallest of ninety readings is the closest thing to what the scan
costs; it moved by **2,10×** on a tree that did not change. The lower half of the distribution moved
together — minimum 2,10, median 2,12 — while the tail moved less, the maximum by 1,83: the second
act was faster *and* cleaner, and the relative dispersion fell from 0,7222 to 0,6324 of the median.
Both published magnitudes moved by 1,83 to 2,42 times; what barely moved is the dimensionless one,
`min / jitter`, 0,9950 → 1,1473, a factor of **1,15×**.

**The three pre-registered claims, as frozen.** What follows is what was written before the act, not
what the act made convenient. Two of the three fell:

| id | pre-registered threshold | measured | verdict |
|---|---|---|---|
| K1 | `k_B` < 0,1509 | 0,2498, against 0,6054 | **falls** |
| K2 | halves differ by < 0,1509 | 0,1938 vs 0,2498, difference 0,0560 | **survives** |
| K3 | `min_B / min_A` in [0,90; 1,10] | 0,2384 / 0,5011 = 0,4758 | **falls** |

**K1 fell, and the fall is a defect of the order, not a finding about the world.** Its threshold was
`q / 2` = 0,1509, but batch 6 defines `q` as the *half*-width: the interval it publishes for its own
subject is [0,204, 0,3803] around 0,2921, which is that prediction times 1 ∓ 0,3018 to the last
published digit. So the boundary every earlier batch applied — and the one the section above states
in words, *stays under* 0,3018 — is `q`, not `q / 2`. The act landed at 0,2498, strictly inside the
gap between the two published thresholds: 0,1509 < 0,2498 < 0,3018. Two statements in this
repository, both about the same act, give **opposite** verdicts on it: the frozen prediction says
not publishable, the rule written one batch earlier says publishable.

Neither is retro-fitted, and the prediction is not re-scored with a threshold it did not freeze. The
disjunction needed something other than the threshold: it needed a quantity that survives the change
of act, and both thresholds only paraphrase one. `min_B / min_A` = 0,4758 — K3, which fell — says
the minimum does not survive it either, so no single second travels. What the pair does show is
narrower and firmer: **the same tree, twice, does not keep its floor.** The floor is a reading of
the act.

**Inside the act the floor is nearly stationary; the tail is where the act shows.** The nine blocks
of act B, each ten readings of the minimum of three scans:

| block | best | median | worst | jitter |
|---:|---:|---:|---:|---:|
| 1 | 0,2384 | 0,2504 | 0,3726 | 0,1342 |
| 2 | 0,2459 | 0,3009 | 0,3297 | 0,0838 |
| 3 | 0,2680 | 0,3828 | 0,4292 | 0,1612 |
| 4 | 0,2543 | 0,2744 | 0,3816 | 0,1273 |
| 5 | 0,2878 | 0,3309 | 0,3876 | 0,0998 |
| 6 | 0,2487 | 0,3044 | 0,3707 | 0,1220 |
| 7 | 0,2972 | 0,3885 | 0,4422 | 0,1450 |
| 8 | 0,2867 | 0,4099 | 0,4503 | 0,1636 |
| 9 | 0,3456 | 0,3755 | 0,5534 | 0,2078 |

K2 survives because the two halves of the act agree to 0,0560 — 0,1938 against 0,2498, a ratio of
1,29 — well inside its threshold. But the spread *inside* the act is 2,48× between its mildest and
its worst block, the same size as the 2,42× between acts. Both readings are true at once: the worst
of four blocks is stable, the worst of one is not, and no window — however well chosen — makes a
single block trustworthy.

**Why this forbids a boolean interface.** `k` is the quantity; `publicable` is that quantity
projected against a parameter, `q · predicted > jitter`. This act sits in the interval where the two
published values of that parameter disagree, so the bit would be a coin toss between two documents
of record. What a receipt can carry is the pair — `k` = 0,2498 and the threshold it was compared
against — so a reader applies either rule and sees which one it applied. A boolean deletes exactly
the parameter that is in dispute, and this batch is the proof that it is in dispute.

**What travels is a ratio, not a duration.** Across two acts on one tree, `min` moved 2,10× and
`jitter` 2,42×, while `min / jitter` moved 1,15×. If that holds over more than two acts, a quote can
be denominated in the act's own minimum with its uncertainty carried as a dimensionless quotient,
and the seconds of that uncertainty become free of the act's speed by construction. Two acts are not
a population, so the claim is frozen before its own measurement in `prediccion-batch-9.json`: three
further acts on the same pinned tree, with the falsifier written there — the dispersion of `min /
jitter` exceeding the dispersion of `min` itself.

The batch is one command, and it re-derives every figure above rather than transcribing it:

```bash
PYTHONPATH=src:bench python bench/piso.py --dir /tmp/censo8 --artefacto
```

It writes `fuera-de-dominio-8.json`: both acts with their pins and their ninety readings each, the
noise of every block, the paired comparison and the verdicts against the frozen prediction. Every
cell of every table above is read from that file by the test suite, so a figure that stops matching
it fails CI instead of ageing quietly. `--desde` recomposes the document from readings already paid
— act A rebuilt from the sealed batch-7 artifact, act B read back from its progress file and its
summary recomputed from the raw blocks — so a recomposition can never quietly become a second act.

### Nothing travels but the counts

Batch 8 put one pinned tree in two acts and showed the floor moving; it could not show what stays.
Two acts are not a population, and the one quantity that looked stable — `min / jitter`, 1,15×
against 2,10× for the minimum — was chosen after seeing that pair. This batch pays for three more acts
on the same pin, ninety clocks each, and it times the gate itself. All three claims frozen in
`prediccion-batch-9.json` fell.

| act | minimum | median | worst block jitter | `min / jitter` | `k` | publishable |
|---|---:|---:|---:|---:|---:|---|
| A | 0,5011 | 0,6973 | 0,5036 | 0,9950 | 0,6054 | no |
| B | 0,2384 | 0,3286 | 0,2078 | 1,1473 | 0,2498 | yes |
| C | 0,3002 | 0,3968 | 0,1065 | 2,8188 | 0,1280 | yes |
| D | 0,3243 | 0,3810 | 0,1108 | 2,9269 | 0,1332 | yes |
| E | 0,2882 | 0,3451 | 0,0961 | 2,9990 | 0,1155 | yes |

| quantity | five acts, max / min |
|---|---:|
| minimum | 2,10 |
| worst block jitter | 5,24 |
| `min / jitter` | 3,01 |
| `k` | 5,24 |

| id | pre-registered threshold | measured | verdict |
|---|---|---|---|
| L1 | `min / jitter` dispersion ≤ 1,30 **and** `min` dispersion ≥ 1,80 | 3,01 and 2,10 | **falls** |
| L2 | `min / jitter` in [0,90; 1,40] in all five acts | 0,9950 to 2,9990 | **falls** |
| L3 | within-act over between-act ratio in [0,80; 1,25] | 0,2766 | **falls** |

**The quotient is the loser, not the winner, and L1 fell against its own falsifier.** The falsifier
was written before the act: dispersion of `min / jitter` above 1,50, or dispersion of `min` below
1,50. It measured 3,01 — twice the falsifier — while the minimum moved 2,10. The quantity batch 8
nominated as the one that travels is the one that travels worst, because `jitter` alone moves 5,24×
and the quotient inherits that movement divided by 2,10. Two acts made it look stable: both
magnitudes happened to move by nearly the same factor. Three more separate them. A ratio of two noisy
quantities is not an invariant, it is a coincidence of covariance.

**L2 fell by three times its ceiling, and the quiet window is the reason.** Acts C, D and E put
`min / jitter` at 2,8188, 2,9269 and 2,9990 against a ceiling of 1,40. On a quiet machine the jitter
collapses faster than the minimum does — 0,5036 to 0,0961 is 5,24×, while the minimum only falls
2,10× — so a ratio with the jitter in the denominator has no ceiling, exactly as it had no floor.

**What does stay is the session, and it is frozen, not concluded.** Acts C, D and E were three
consecutive windows of one session: `k` at 0,1280, 0,1332 and 0,1155, a dispersion of 1,15× between
the three against 5,24× across the five. Inside the session the quotient moves 4,5× less than
between sessions. One session is one observation, so this is written into
`prediccion-batch-10.json` before its own act rather than concluded here.

**The boolean survives all five acts and hides a 2,16× change in the floor.** Four of the five acts
are publishable under `q` = 0,3018, and their floors do not agree: 0,2078 s in act B against 0,0961 s
in act E. The bit answers yes to both, so it answers the same to a quote whose uncertainty is twice
the other's. What a receipt has to carry is the measured `k`, the threshold it was compared against,
and how far `k` moved between the acts of the population it came from — none of which a boolean can
hold.

**The gate is not free, and this batch is the first to say what it costs.** `coste_compuerta_s` is
the wall clock the ninety clocks of an act burn to certify the floor:

| act | gate wall | per clock | gate / cheapest scan |
|---|---:|---:|---:|
| C | 209,5 s | 2,3 s | 698 |
| D | 132,1 s | 1,5 s | 407 |
| E | 109,6 s | 1,2 s | 380 |

451,3 s of wall bought the 270 new clocks. The gate burns between 380 and 698 of the cheapest scans it
calibrates, and even that price is a reading of the act: per clock it fell from 2,3 s to 1,2 s across
one session, 1,91× on a constant workload. So the corpus no longer measures only the noise of the
environment and not the cost of measuring it: a quote that certifies its own floor pays 110 to 210 s
for the certificate, which on a tree this size is the whole budget of the quote.

**L3 is not decidable as frozen, and the defect is arithmetic.** Its `claim` divides
`max(jitter) / min(minimum)` per act and averages; its `cota_error` divides one act's block-jitter
dispersion by the dispersion of `min`. On batch 8's own two acts the first gives 0,4464 and the second
1,1797 — 2,4797 / 2,1019, where 2,4797 is act B's internal dispersion and not a mean over acts. The
two are not the same quantity, and only the second passes the frozen range. L3 is scored with the
formula its `claim` declares, which is the one the range freezes: 0,2766. The other number is
published as `l3_cota_media`, 1,6992. Neither the order nor the score is retro-fitted; the breach is
declared.

**What this leaves a quote.** Counts travel: bytes scanned and nodes visited are the same in every
act, and they are the only quantities this population puts inside a receipt without a timestamp. A
temporal band exists only inside the act that quotes it, and certifying it costs 380 to 698 of the
scans it calibrates. Anything else is a second inherited from another window, and this batch has five
windows on one tree that disagree by 5,24×.

```bash
PYTHONPATH=src:bench python bench/ventana.py --dir /tmp/censo9 --artefacto
```

It writes `fuera-de-dominio-9.json`: the five acts with their pins, their ninety readings each, the
noise of every block, the within-act dispersions, the verdicts against the frozen prediction, the
declared defect of L3 and the wall cost of each gate. Acts A and B are read back from
`fuera-de-dominio-8.json` and never re-timed, so the sample is paired; `--desde` recomposes the
document from acts already paid, so a recomposition can never quietly become a fourth act.

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
    rev: v0.4.6
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

### `self.m(...)` was invisible, and resolving it changed no verdict

The second pass resolves a call by identity, not by name. Until 0.4.2 the identity
came only from the import table, so a call written `self.medir(x)` resolved to
nothing — and, worse, was not even *counted* as unresolved, because the bare-name
matching compared the callee against `Caja.medir` instead of `medir`. The
published blindness was therefore scoped to module-level producers while method
producers were silently dropped: not attributed, not counted, not visible.

Both halves are fixed. The bare name of a method producer is its last segment,
and a `self.m(...)`/`cls.m(...)` call whose enclosing class defines `m` resolves
to `(module, Clase.m)` with evidence `SELF`, read from the syntax tree rather
than from a binding. Inheritance, `super()`, and any other receiver stay
`NO_MEDIDO` on purpose: a name that matches is not an identity.

Measured on the ten pinned corpora of `censo.json`, before → after:

| population | before | after |
|---|---|---|
| call sites attributed by identity (`EXACTO`) | 4 | 4 |
| call sites attributed by the new `SELF` rule | — | 15 |
| unknown sites (`por_nombre`) | 38 | 32 |
| of which, `mypy` | 38 | 6 |
| of which, discarded entirely by the old key | 0 | 26 |
| sites whose reader was found | 0 | 0 |

The two populations close by hand: 38 seen before + 26 revealed by the key fix =
64; of those, 32 left the unknown population (15 now attributed to a producer,
17 resolved to a method that is not one) and 32 remain. The residual is entirely
`mypy` — inherited or aliased receivers, which stay `NO_MEDIDO` by design.

The counter-intuitive row is the last one. Resolving identity is not measuring:
of the 15 newly attributed call sites, **not one** calls `len()` on the value
within one hop, so no reader appeared and no verdict moved — all ten pinned rows
re-derive identical under `bench/replay_censo.py`, which CI runs on every push.

That is the useful result, and it points the other way from the one I expected:
the 9.74 % foreign density is **not** an artifact of a resolver that gave up. It
was measured with a resolver that could not see `self.` and it did not move when
the resolver learned to. The unknown population also shrank while growing — 26
sites now appear that the old key silently discarded — which is the honest
direction for a census: a smaller number obtained by counting fewer places is
not an improvement.

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
own-corpus row (240 files, `413` stores) is marked as pinnable by subject digest only and is excluded
from all cross-package arithmetic. Two of the published rows were also wrong in a way that no
amount of care would have caught: `mypy` was scoped to `mypy/` (the wheel has 336 `.py` files,
the package 195) and `pydantic` had moved a version. Pinning the artifact is what made both visible.

`0.4.2` gives the second pass a second identity rule and changes no verdict. `self.m(...)`
calls to a method of the enclosing class now resolve to `(module, Clase.m)` with evidence `SELF`;
the bare-name key that matched them against `Clase.m` instead of `m` is fixed, which reveals 26
sites it had been discarding. `0.4.2` also gives the own-corpus row a subject: it had been copied
as `239 files / 408 stores` in one place and `239 files / 413 stores` in another, and the tree is
`240 / 413` — one file added, four stores with it. All ten rows of `censo.json` re-derive identical, and the number of
candidates whose reader is found stays at zero — the section above is about the instrument's
blindness ending, not about the density moving.

After `0.4.2`, the pin grew and the wheel did not: thirteen rows, `instrument_version` still
`0.4.2`. That is deliberate — the version names the **binary that produced a row**, not the number
of rows, and a documentation-and-pin change that leaves `src/` untouched should not mint a version
whose artifact is byte-identical to the previous one. The three out-of-sample rows reproduce from
PyPI like the rest (`REPLAY IDENTICO · 13 filas · instrumento 0.4.4`, RC 0), and `totals_seven` still
describes only the seven, which is why it is called `totals_seven` and not `total`.

`0.4.3` publishes the terms instead of the verdict. Every row of `censo.json` declared
`"reconciles": true` and carried `stores` and `pierde` — and **none of the four buckets**
(`guardadas`, `acumulacion`, `posicional`, `sin_len`) whose sum makes `reconciles` true. A third
party could read the claim and could not check it: the equation was computed, then thrown away.

| package | version | scope | stores | = | pierde | guardadas | acumulacion | posicional | sin_len |
|---|---|---|---:|---|---:|---:|---:|---:|---:|
| `mypy` | 2.4.1 | `mypy/` | 173 | = | 4 | 25 | 7 | 12 | 125 |
| `pylint` | 4.1.4 | `.` | 55 | = | 1 | 14 | 4 | 4 | 32 |
| `astroid` | 4.3.4 | `.` | 37 | = | 0 | 10 | 0 | 1 | 26 |
| `dill` | 0.4.1 | `.` | 16 | = | 4 | 1 | 1 | 1 | 9 |
| `isort` | 9.0.2 | `.` | 21 | = | 0 | 2 | 2 | 3 | 14 |
| `platformdirs` | 4.14.8 | `.` | 0 | = | 0 | 0 | 0 | 0 | 0 |
| `tomlkit` | 0.15.3 | `.` | 6 | = | 0 | 2 | 1 | 0 | 3 |
| **seven** | | | **308** | = | **9** | **54** | **15** | **21** | **209** |

`bench/replay_censo.py --anotar` writes the buckets back and refuses the row if the residual is not
zero, so the table above cannot be produced by a script that disagrees with it. Re-running it is
what found the defect it was written to prevent: measurements were keyed by `artifact` alone, and
the two `mypy` rows share one wheel (`mypy-2.4.1-py3-none-any.whl`) with two scopes, so the
wheel-root row (226 stores) overwrote the package row (173) and the annotation reported a rupture
that existed only in the writing. Keyed by `(artifact, scope)`, all thirteen rows reconcile.

`tests/test_censo.py` no longer believes the flag either: it recomputes
`pierde + guardadas + acumulacion + posicional + sin_len == stores` per row and on `totals_seven`,
so a row that says `reconciles: true` and does not close fails the suite. The `instrument_version`
of the rows stays `0.4.2` for the reason above — the *analyzer* that produced the numbers did not
change; only the part of the script that recorded them did.

The same window closed the other half of the out-of-sample question. Precision on three candidates
cannot say whether a defect is *caught*, so three losing forms and two controls were planted inside
the pinned `flake8` tree: `stores` 3 → 8 (exactly the plants), both guards silent, and the row that
was already there unchanged. Three tests now hold the classifier to that matrix offline.

`0.4.4` makes the JSON name its author. `--json` reported what it measured and never which binary
measured it, so a receipt copied out of a CI log could not be traced to a version, and a receipt
that had aged was indistinguishable from one that had been edited. Every document now carries
`instrument` and `instrument_version` at the root, stamped by the package that ran. The census was
re-run over all thirteen pinned artifacts with `0.4.4` before its `instrument_version` moved: every
cell identical, `totals_seven` unchanged — a stamp is only a measurement if the run that produced it
is the run that wrote it.

`0.4.5` splits closing from certifying. Two census rows — `platformdirs` and `pyflakes`, 15 and 23
files, zero stores each — closed `0 = 0 + 0 + 0 + 0 + 0` and published `"reconciles": true,
"rc": 0`: a tautology sold as a conservation. The identity stays; the signature now requires a
population. `--json` publishes both codes with a name (`certifica`, `rc_certificado`) and the scan's
exit code does not move, because being out of scope is not a defect. The two rows were **re-emitted,
not edited**: their wheels re-downloaded, their SHA-256 checked against the pins, the analyzer
re-run, and every measured cell came back identical — only `reconciles` and `rc` moved, which is
the whole claim: the law changed and the data did not. The defect was found by a downstream
verifier grading this census, which is the reader this repository did not have.

`0.4.6` gives the two codes their own keys in the census. `0.4.5` separated the questions in
`--json` and then fixed the census by **overwriting** the two collided values: on `platformdirs` and
`pyflakes`, `reconciles` came back `false` and `rc` came back `2` — the arithmetic flag and the scan
code answering with the certificate's answer. Those two rows then contradicted the table four
paragraphs above them in this same file, which says `reconcilia: true, rc: 0` for `platformdirs`,
because one key was carrying two subjects. The census now publishes the four names the payload
already had — `rc`, `rc_certificado`, `reconciles`, `certifica` — and `bench/replay_censo.py`
**compares and annotates all four**, so a row is a function of the artifact instead of a
transcription of a decision. The re-run is its own evidence: eleven of thirteen rows identical, and
the only cells that moved are the two that were wrong — `rc` `2 → 0` and `reconciles` `false → true`
on both empty universes, with `rc_certificado: 2` and `certifica: false` published beside them.

The reason it matters beyond this repository: `1` is "the scan found candidates" here and "the act
declared a collision" in the receipt contract. The two ladders share `0`, `1` and `2` and disagree
in the middle, which is worse than sharing none — partial agreement is what licenses a consumer to
map the integer and print a claim nobody made.

After `0.4.6` the pin grew again and the wheel did not: `fuera-de-dominio.json` is a **second
instance of the same schema** (`fiber-ast-lint/censo/1`), five rows over four domains, and `src/` is
untouched — so it mints no version, by the rule stated above. Its status is a field, not an
adjective: `EXPLORATORIO`, because the rows were measured before any prediction existed, and a
sample that was not predicted may name directions and may not name rates. What it establishes
without a rate is the containment `candidates ≤ sin_len`, which holds on all 18 rows of both files,
and what it publishes without a rate is the denominator correction: `almacenes` is the pre-filter
population, `sin_len` the post-filter one.

## License

MIT — see [LICENSE](LICENSE).

## Field notes

This repository belongs to an audit corpus whose measurements are published as
field notes. Two of them come from the same work:

- [Auditar un escáner de secretos con un escáner de secretos no mide nada](https://dev.to/alexisromtz7/auditar-un-escaner-de-secretos-con-un-escaner-de-secretos-no-mide-nada-3f5o)
- [Casi la mitad del código de 22 proyectos depende de un ciclo, y el indicador habitual premia al que peor está](https://dev.to/alexisromtz7/casi-la-mitad-del-codigo-de-22-proyectos-depende-de-un-ciclo-y-el-indicador-habitual-premia-al-que-3ecn)
