# Draft: silent reporter overwrite in `flake8/plugins/finder.py`

**Status: DRAFT. Do not file without explicit approval from the repository owner.**

---

## Title

`_classify_plugins` keys reporters by entry-point name and never tests the key, so two plugins
registered under one name leave one reporter unreachable and silent

## Summary

While measuring an out-of-sample population (`pyflakes` 4.1.0, `flake8` 7.5.0, `black` 26.10.1),
`flake8`'s plugin classifier tripped a detector for non-injective key projections. The write is:

```python
reporters = {}                                     # finder.py:317
for loaded in plugins:
    ...
    elif loaded.plugin.entry_point.group == "flake8.report":
        reporters[loaded.entry_name] = loaded       # finder.py:327
```

`entry_name` comes from the installed entry point, so it is whatever the plugin distribution
declares. Nothing constrains two distributions to declare different names, and nothing tests the key
before writing. If two do collide, the second `LoadedPlugin` **replaces** the first.

## Reproduction (no flake8 install required)

The absence of a guard is a property of the shipped source, so it can be measured on the wheel:

```python
import ast, pathlib
src = pathlib.Path("flake8/plugins/finder.py").read_text()
fn = next(n for n in ast.walk(ast.parse(src))
          if isinstance(n, ast.FunctionDef) and n.name == "_classify_plugins")
compara = [n for n in ast.walk(fn) if isinstance(n, ast.Compare)]
mencionan = [n for n in compara
             if any(isinstance(x, ast.Name) and x.id == "reporters" for x in ast.walk(n))]
print(len(compara), len(mencionan))    # 5 0
```

Five comparisons inside `_classify_plugins`, **zero** of them mention `reporters`. A textual census
agrees:

```console
$ grep -rn "reporters" --include=*.py flake8
flake8/plugins/finder.py:317:    reporters = {}
flake8/plugins/finder.py:327:            reporters[loaded.entry_name] = loaded
flake8/plugins/finder.py:350:        reporters=reporters,
flake8/plugins/reporter.py:34:        format_plugin = reporters[format_name]
flake8/options/parse_args.py:48:        formatter_names=list(plugins.reporters),
```

The semantics of the collision are ordinary dict semantics, so they need no install to state: two
loaded reporters with one `entry_name` leave `len(reporters) == 1`, and the first is gone.

## Consequence

The shadowed reporter is not merely shadowed at selection time:

* `reporter_names()` yields `self.reporters.values()`, so the shadowed plugin never appears in the
  `--format` choices printed by `flake8 --help`;
* `reporter.make()` looks up `reporters[format_name]` (or `reporters["default"]`), so there is no
  path by which the shadowed object can be selected;
* no message, warning or exception is produced at any point.

A user who installs a fork of a reporter under the same entry-point name loses one of the two
formatters with no diagnostic that points at the cause.

## Possible fixes (maintainer's call)

1. Refuse the collision where it happens:
   `if loaded.entry_name in reporters: raise ExecutionError(...)`, next to the existing
   `VALID_CODE_PREFIX` check that already runs over the same list.
2. Warn instead of raising, if two reporters under one name should stay legal and last-writer-wins
   is intended.
3. Key the dict by `(group, entry_name)` — but `reporter.make` indexes it by the `--format` string,
   so this only helps if the format string is also disambiguated.

## Impact

Low severity, narrow trigger: it requires two distributions registering a `flake8.report` entry
point under the same name. The class of defect is the interesting part — an accumulator of
capabilities keyed by a name its own author does not control — and that shape is common in plugin
registries, route tables and ETL key maps, where the collision is not rare at all.

## Detection tool

`fiber-ast-lint` (MIT, stdlib only) reports the locus as `CANDIDATO` with
`fam=COLUMNA forma=SELECCION_COLUMNA_BUCLE`, that is: a column of the row (an attribute of the loop
variable) used as the whole key, with no membership guard, on an accumulator that escapes the
function and whose cardinal nobody measures. The tool does not claim the write is a bug; intent is
adjudicated by a human, which is exactly what this draft is asking for.

Subject measured: `flake8-7.5.0-py2.py3-none-any.whl`,
sha256 `637ea1a443a78ed6ee461725cdf71ca93bc5cde0abf25436dbebdc3880b4e078`.
