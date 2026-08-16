"""Building technical-system models: heating, cooling and DHW final energy.

This module converts useful energy needs (Q_H, Q_C, Q_W) into final energy
consumption E_k, taking into account generator efficiency / COP and
distribution / emission / control losses.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def constant_efficiency_final_energy(
    Q_demand_wh: np.ndarray, efficiency: float, distribution_factor: float = 1.0
) -> np.ndarray:
    """Final energy [Wh] for a system with constant efficiency/COP."""
    if efficiency <= 0:
        raise ValueError("Efficiency must be positive")
    return np.where(Q_demand_wh > 0, Q_demand_wh / efficiency / distribution_factor, 0.0)


def heat_pump_cop_map(
    T_e: pd.Series | np.ndarray,
    T_sink: float,
    source_type: str = "air",
    rated_cop: float = 3.5,
    rated_T_source: float = 7.0,
    rated_T_sink: float = 35.0,
) -> np.ndarray:
    """Simple COP map for an air-source or water-source heat pump.

    Uses a Carnot-like relative approach: COP scales with the ratio of
    temperature lifts. This is a placeholder; production should use
    manufacturer or standard (EN 14511 / EN 14825) part-load curves.

    Parameters
    ----------
    T_e : array-like
        Heat source temperature [°C].
    T_sink : float
        Heating water temperature [°C].
    source_type : str
        'air' or 'water'.
    rated_cop : float
        COP at rated conditions.
    rated_T_source : float
        Rated source temperature [°C].
    rated_T_sink : float
        Rated sink temperature [°C].

    Returns
    -------
    np.ndarray
        Hourly COP values.
    """
    T_source_k = np.asarray(T_e, dtype=float) + 273.15
    T_sink_k = T_sink + 273.15
    rated_source_k = rated_T_source + 273.15
    rated_sink_k = rated_T_sink + 273.15

    # Carnot-relative scaling (very simplified)
    theoretical_ratio = (
        (T_source_k / (T_sink_k - T_source_k))
        / (rated_source_k / (rated_sink_k - rated_source_k))
    )
    cop = rated_cop * theoretical_ratio
    return np.clip(cop, 1.0, 6.0)


def dhw_energy_demand(
    daily_demand_per_person: float,
    occupancy_density: float,
    floor_area: float,
    target_temperature: float,
    cold_water_temperature: float,
    days: int = 365,
) -> float:
    """Annual DHW useful energy demand [Wh].

    Parameters
    ----------
    daily_demand_per_person : float
        Litres of DHW per person per day.
    occupancy_density : float
        Persons per m2.
    floor_area : float
        m2.
    target_temperature : float
        °C.
    cold_water_temperature : float
        °C.
    days : int
        Days per year.

    Returns
    -------
    float
        Annual useful DHW energy [Wh].
    """
    persons = occupancy_density * floor_area
    litres_per_year = daily_demand_per_person * persons * days
    # Water specific heat ≈ 4.18 kJ/(kg*K); 1 litre ≈ 1 kg; result in Wh
    energy_wh = litres_per_year * 4180.0 * (target_temperature - cold_water_temperature) / 3600.0
    return energy_wh


def final_energy_dhw(
    Q_demand_wh: float, efficiency: float, standby_loss_factor: float = 1.0
) -> float:
    """Final energy for DHW [Wh] including storage and distribution losses."""
    if efficiency <= 0:
        raise ValueError("Efficiency must be positive")
    return Q_demand_wh / efficiency * standby_loss_factor
