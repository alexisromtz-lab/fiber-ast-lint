"""The loss becomes a visible bucket: the loop asks ``k in acc`` first."""
def indexar(registros):
    por_id = {}
    repetidos = []
    for r in registros:
        clave = r["email"].strip().lower()
        if clave in por_id:
            repetidos.append((clave, r))
            continue
        por_id[clave] = r
    return por_id, repetidos
