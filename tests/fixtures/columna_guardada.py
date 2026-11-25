"""Same column, but the collision becomes a counted bucket instead of a loss."""


def indexar_por_codigo(filas):
    por_codigo = {}
    repetidos = []
    for fila in filas:
        if fila.codigo in por_codigo:
            repetidos.append(fila)
            continue
        por_codigo[fila.codigo] = fila
    return por_codigo, repetidos
