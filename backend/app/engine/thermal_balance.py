"""Hourly thermal-balance solver following the ISO 52016-1 methodology.

This module provides a simplified single-zone dynamic model used as a
starting point. It is equivalent to the 5R1C lumped-parameter model from
ISO 13790 (a predecessor concept also underlying ISO 52016-1) and will be
extended to a more detailed multi-node representation as the project matures.
"""

from __future__ import annotations

import numpy as np

# Wh/K per m2 of conditioned floor area; typical ranges:
# light-weight construction ~ 30, medium ~ 80, heavy ~ 160
DEFAULT_CM_PER_M2 = 60.0  # Wh/(m2*K)


def thermal_capacity(floor_area: float, cm_per_m2: float = DEFAULT_CM_PER_M2) -> float:
    """Total thermal capacity C_m [Wh/K] of the zone."""
    return floor_area * cm_per_m2


def solve_hourly_balance(
    H_tr: float,
    H_ve: float,
    Q_int: np.ndarray,
    Q_sol: np.ndarray,
    T_e: np.ndarray,
    T_set_heating: float,
    T_set_cooling: float | None,
    C_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Solve the single-zone dynamic thermal balance for one year.

    Parameters
    ----------
    H_tr : float
        Total transmission heat transfer coefficient [W/K].
    H_ve : float
        Total ventilation heat transfer coefficient [W/K].
    Q_int : np.ndarray
        Internal gains [W] per hour (8760).
    Q_sol : np.ndarray
        Solar gains entering the internal air node [W] per hour (8760).
    T_e : np.ndarray
        Outdoor air temperature [°C] per hour (8760).
    T_set_heating : float
        Heating setpoint [°C].
    T_set_cooling : float | None
        Cooling setpoint [°C]; if None, cooling is disabled.
    C_m : float
        Thermal capacity [Wh/K].

    Returns
    -------
    T_int : np.ndarray
        Indoor air temperature [°C] (8760).
    Q_H : np.ndarray
        Heating demand [Wh] per hour (sensible, positive).
    Q_C : np.ndarray
        Cooling demand [Wh] per hour (sensible, positive).
    Q_bal : np.ndarray
        Net heat balance before HVAC correction [W].
    """
    n = len(T_e)
    dt = 1.0  # hours
    H = H_tr + H_ve

    T_int = np.empty(n, dtype=float)
    Q_H = np.zeros(n, dtype=float)
    Q_C = np.zeros(n, dtype=float)
    Q_bal = np.zeros(n, dtype=float)

    # Initial temperature guess = heating setpoint
    T_prev = float(T_set_heating)

    # Common denominator for the implicit Euler discretisation
    denom = C_m / dt + H

    for t in range(n):
        # Free-floating indoor temperature (no HVAC yet)
        T_free = (C_m / dt * T_prev + Q_int[t] + Q_sol[t] + H * T_e[t]) / denom

        # Heating demand if too cold
        if T_free < T_set_heating:
            T_int[t] = T_set_heating
            Q_H[t] = (T_set_heating - T_free) * denom * dt  # Wh
            Q_C[t] = 0.0
        # Cooling demand if too warm
        elif T_set_cooling is not None and T_free > T_set_cooling:
            T_int[t] = T_set_cooling
            Q_C[t] = (T_free - T_set_cooling) * denom * dt  # Wh
            Q_H[t] = 0.0
        else:
            T_int[t] = T_free
            Q_H[t] = 0.0
            Q_C[t] = 0.0

        # Net balance for diagnostics (W)
        Q_bal[t] = Q_int[t] + Q_sol[t] - H * (T_int[t] - T_e[t])
        T_prev = float(T_int[t])

    return T_int, Q_H, Q_C, Q_bal
