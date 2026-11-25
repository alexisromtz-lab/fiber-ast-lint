"""The key is ONE COLUMN of the row: ``fila.codigo``, not the row.

Two rows that share the column fuse into one slot. Nothing in the file says
whether the column is unique, so the write is a candidate, never a defect.
"""


def indexar_por_codigo(filas):
    por_codigo = {}
    for fila in filas:
        por_codigo[fila.codigo] = fila
    return por_codigo


def cardinal(filas):
    tabla = indexar_por_codigo(filas)
    return len(tabla)
