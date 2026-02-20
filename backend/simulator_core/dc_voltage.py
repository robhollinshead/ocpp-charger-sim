"""DC pack voltage model: sigmoid-based OCV (open-circuit voltage) from SOC."""
import math

DEFAULT_CELLS = 108


def ocv_from_soc(soc: float) -> float:
    """
    Compute single-cell open-circuit voltage from state of charge.

    Args:
        soc: State of charge as a fraction [0, 1].

    Returns:
        Cell voltage in volts (typically 3.2–4.2V for Li-ion).
    """
    Vmin = 3.2
    Vmax = 4.2
    plateau = 0.95 - 0.25 / (1 + math.exp(20 * (soc - 0.5)))
    return Vmin + (Vmax - Vmin) * plateau


def get_pack_voltage_V(soc_pct: float, cells: int = DEFAULT_CELLS) -> float:
    """
    Compute DC pack voltage from SOC percentage.

    Args:
        soc_pct: State of charge as a percentage [0, 100].
        cells: Number of cells in series (default 108).

    Returns:
        Pack voltage in volts.
    """
    soc = max(0.0, min(100.0, soc_pct)) / 100.0
    return ocv_from_soc(soc) * cells
