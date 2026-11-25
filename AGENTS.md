# AGENTS.md — fiber-ast-lint

Operating notes for whoever (human or agent) touches this repository. This is a **product**
repository: it has no relation to any internal corpus, and it must not borrow vocabulary from one.

## What this repository is

A detector for one defect class: a dictionary built as `acc[π(k)] = v` where `π` is not injective
keeps `|im(π)|` of `|domain|` and destroys the rest without an exception. The public contract is
this README plus the exit codes; nothing else is promised.

## Invariants — do not break them

1. **The exit code is the contract.** `0` clean · `1` candidates · `2` empty universe · `4` broken
   structure. An empty or failed universe reported as `0` is the bug this tool exists to refuse.
2. **No measurement of zero by omission.** Anything the analyser cannot see is declared
   `NO_MEDIDO` / `SIN_LEN` with its reason. A silent zero is a lie with a number attached.
3. **The census must reconcile.** `almacenes == pierde + guardadas + acumulacion + posicional +
   cardinal_sin_medir`. If it does not, the tool must refuse (`RC 4`), not round.
4. **No false authority.** A candidate is a candidate. The tool never prints "defect"; intent is
   adjudicated by a human, and the README says so.
5. **Zero runtime dependencies.** Standard library only. A debugger-friendly one-file install is
   the entire distribution strategy.
6. **A ported detector must reproduce its oracle.** When the classifier changes, run it against a
   known list of admitted loci and compare sets, not counts. Counts agree while the sets differ.

## Commands

```console
python -m pytest -q                       # the whole suite, no network
python -m fiber_ast_lint src --json       # self-analysis
python -m fiber_ast_lint tests/fixtures   # must exit 1: the control battery has candidates
```

## Where the tests come from

Every test is anchored to a fixture under `tests/fixtures/` that exists to be classified exactly
one way. A fixture is a **control**, not an example: `espacio_no_transversal.py` reproduces the
real `mypy` collision (six keys, four names), `monoidal_conserva.py` is aggregation,
`guardada_conserva.py` is a counted bucket, `posicional_conserva.py` is a sequence store, and
`grafo_consumidores.py` carries the three consumer forms of the second pass.

## Style

Small modules, dataclasses, no cleverness in the analyser: someone must be able to read
`detect.py` and disagree with a line. Comments explain *why* a branch exists, never *what* the
line does.
