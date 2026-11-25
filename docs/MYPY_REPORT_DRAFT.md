# Draft: silent key collapse in `mypy/config_parser.py`

**Status: DRAFT. Do not file without explicit approval from the repository owner.**

---

## Title

`config_parser.py:543` — two distinct ini keys collapse onto one reporter name, and the
`REPORTER_NAMES` guard cannot prevent it

## Summary

While auditing a static-analysis class (non-injective key projections), `mypy`'s config parser
tripped the detector. Reduced to its pure expression, the write at `mypy/config_parser.py:543` is:

```python
report_type = key[:-7].replace("_", "-")        # :541
if report_type in defaults.REPORTER_NAMES:      # :542
    report_dirs[report_type] = str(section[key])  # :543
```

`π = lambda key: key[:-7].replace("_", "-")` is not injective: keys that differ only in the
separator (`any_exprs_report` vs `any-exprs_report`) land on the same name. The guard does not
help, because `REPORTER_NAMES` is a set of **images**: it contains `any-exprs` and `xslt-html`,
which are precisely the images of the two non-trivial fibers, so both members of each pair pass
the guard and the second write overwrites the first.

## Reproduction (pure function, no mypy installed)

```python
REPORTER_NAMES = {"any-exprs", "html", "linecount", "xslt-html"}

def pi(key: str) -> str:
    return key[:-7].replace("_", "-")

keys = ["any_exprs_report", "any-exprs_report",
        "xslt_html_report", "xslt-html_report",
        "linecount_report", "html_report"]

pasantes = [k for k in keys if pi(k) in REPORTER_NAMES]
imagen = {pi(k) for k in pasantes}
print(len(pasantes), len(imagen))   # 6 4  -> two slots lost, no error raised
```

Observed: `6 4`. Two names are silently overwritten (`any-exprs`, `xslt-html`). No exception, no
warning, and `mypy --strict` reports nothing, because every individual line is correct.

## Why the guard cannot fix it

`if π(k) in W` constrains the codomain. It suppresses the collapse only when the inputs it admits
form a *transversal* of the partition induced by `π`:

```
∀ y ∈ π(W):  |{k admitted : π(k) = y}| = 1
```

A whitelist that contains images of non-trivial fibers fails this by construction, so no value of
`REPORTER_NAMES` can protect a key space containing both spellings.

## Possible fixes (maintainer's call)

1. Compare the **raw key** against a set of allowed keys instead of the projected image.
2. Keep the projection but detect the collision: `if report_type in report_dirs: <report>`.
3. Leave as is if the collapse is intentional (last-writer-wins between the `_` and `-` spellings
   of the same option), in which case a one-line comment at `:543` records the decision.

## Impact

Low severity in practice — it requires an ini file that specifies both spellings of the same
option, which is unusual but legal. The class of defect is the interesting part: the same shape
appears in catalog ingestion, ETL key mapping and session-name normalisation, where it is not
unusual at all.

## Detection tool

`fiber-ast-lint` (MIT, stdlib only) reports the locus as `CANDIDATO` with
`fam=ESPACIO+NORMALIZA forma=PROYECCION_ARRIBA_CON_PERDIDA`. It does not claim the write is a bug;
intent is adjudicated by a human, which is exactly what this draft is asking for.
