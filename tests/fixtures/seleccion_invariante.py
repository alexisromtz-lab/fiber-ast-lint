"""The attribute root is a parameter, not the loop variable: not a column of the row.

Declared limit: this is a constant key (every iteration writes the same slot), a
different defect that this pass does not claim to see. It must not be reported
as a column projection, because doing so would attribute the loss to the wrong
mechanism.
"""


def por_config(origen, cfg):
    out = {}
    for item in origen:
        out[cfg.clave] = item
    return out
