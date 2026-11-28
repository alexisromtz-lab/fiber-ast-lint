def total(filas):
    return sum(d.get("saldo_pendiente", 0) for d in filas)
