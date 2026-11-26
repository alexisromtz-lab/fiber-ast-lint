"""El lector del pin no puede exigir mas que el instrumento.

`fiber-ast-lint` acepta un arbol o un modulo suelto -- `detect.py` mira `is_file()`
antes de `is_dir()` --, asi que un scope legitimo puede ser `six.py`. El replay
pedia directorio y por eso declaraba `RUPTURA` sobre un pin correcto: era una
suposicion del lector, no un defecto del objeto. Este test construye el caso
minimo y comprueba que el replay lo mide en vez de romperlo.
"""
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "bench"))

import replay_censo  # noqa: E402


def _pin_de_una_fila(medido, sha256="0" * 64):
    return {"package": "solo", "version": "1.0.0", "artifact": "solo-1.0.0-py3-none-any.whl",
            "scope": "solo.py", "sha256": sha256, **medido}


def _cache(tmp_path):
    base = tmp_path / "cache"
    paquete = base / "solo-1.0.0"
    paquete.mkdir(parents=True)
    (paquete / "solo.py").write_text("def f(v):\n    return v\n", encoding="utf-8")
    return base, paquete


def test_el_replay_acepta_un_scope_que_es_un_fichero(tmp_path):
    base, paquete = _cache(tmp_path)
    pin = tmp_path / "pin.json"
    pin.write_text(json.dumps({"instrument_version": "0.0.0",
                               "rows": [_pin_de_una_fila(replay_censo._medir(paquete / "solo.py"))]}),
                   encoding="utf-8")

    rc = replay_censo.main(["--censo", str(pin), "--desde", str(base)])
    assert rc == 0, "un modulo suelto es un scope legitimo y el replay lo rompia"


def test_el_replay_acepta_un_modulo_al_extraer_la_rueda(tmp_path, monkeypatch):
    # La rama de descarga resuelve el scope por otro camino. Se sustituye la
    # descarga por una rueda local con el mismo digest: sin red y con el mismo
    # contrato, que es lo que la rama comprueba.
    import hashlib
    import zipfile

    rueda = tmp_path / "solo-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(rueda, "w") as z:
        z.writestr("solo.py", "def f(v):\n    return v\n")
    digest = hashlib.sha256(rueda.read_bytes()).hexdigest()
    monkeypatch.setattr(replay_censo, "_traer", lambda *a, **k: (rueda, digest, 0))

    _, paquete = _cache(tmp_path)
    pin = tmp_path / "pin.json"
    pin.write_text(json.dumps({"instrument_version": "0.0.0",
                               "rows": [_pin_de_una_fila(replay_censo._medir(paquete / "solo.py"), digest)]}),
                   encoding="utf-8")

    rc = replay_censo.main(["--censo", str(pin), "--dir", str(tmp_path / "destino")])
    assert rc == 0, "la rama de descarga tambien tiene que aceptar un modulo suelto"


def test_el_escaneo_cuenta_un_fichero_como_universo(tmp_path):
    _, paquete = _cache(tmp_path)
    p = subprocess.run(
        [sys.executable, "-m", "fiber_ast_lint", str(paquete / "solo.py"), "--json"],
        capture_output=True, text=True, cwd=RAIZ)
    assert p.returncode == 0
    assert json.loads(p.stdout)["archivos"] == 1, \
        "el escaner trata un fichero como universo de un fichero, y el pin lo copia"
