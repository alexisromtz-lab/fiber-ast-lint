"""A sequence has no key space: ``s[i] = x`` replaces a row, never removes one."""
def normalizar_lineas(lineas):
    salida = list(lineas)
    for i, linea in enumerate(salida):
        salida[i] = linea.strip().lower()
    return salida
