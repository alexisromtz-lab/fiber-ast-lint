"""Each test analyses a copy of a single fixture, never the fixture directory.

Analysing the whole ``fixtures/`` tree would let one control contaminate another
(a ``len(...)`` written in one file can make a store in a different file count as
measured). One fixture per copy keeps the population of every assertion known.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def copia(tmp_path):
    def _copia(nombre: str) -> Path:
        raiz = tmp_path / Path(nombre).stem
        raiz.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURES / nombre, raiz / nombre)
        return raiz
    return _copia
