"""Positive controls for the second pass (call sites that measure the cardinal)."""
def construir(items):
    acc = {}
    for k, v in items:
        acc[k.strip().lower()] = v
    return acc


def llenar(destino, items):
    for k, v in items:
        destino[k.strip().lower()] = v


def consumidor_vinculo(items):
    tabla = construir(items)
    return len(tabla)


def consumidor_directo(items):
    return len(construir(items))


def consumidor_parametro(items):
    tabla = {}
    llenar(tabla, items)
    return len(tabla)


def consumidor_ausente(items):
    return construir(items)
