"""Aggregation, not loss: ``acc[k] = acc.get(k, 0) + x`` keeps every fiber."""
def agrupar(filas):
    por_clave = {}
    for fila in filas:
        clave = fila["sku"].strip().lower()
        por_clave[clave] = por_clave.get(clave, 0) + fila["unidades"]
    return por_clave
