"""Sonda desechable: un cero implicito nuevo, con coma, sin declarar."""


def saldo_pendiente(registro):
    return registro.get("saldo_pendiente", 0)
