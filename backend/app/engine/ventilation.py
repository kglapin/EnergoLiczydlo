"""Ventilation and infiltration heat loss calculations.

Implements the hourly ventilation heat transfer coefficient H_ve following
PN-EN ISO 52016-1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.engine.climate import AIR_DENSITY_KG_M3, AIR_SPECIFIC_HEAT_J_KGK
from app.schemas.models import ThermalZone, Ventilation

CP_AIR_VOLUMETRIC = AIR_DENSITY_KG_M3 * AIR_SPECIFIC_HEAT_J_KGK  # J/(m3*K) ~= 1206


def ventilation_heat_transfer_coefficient(
    ventilation: Ventilation,
    zone: ThermalZone,
) -> float:
    """Compute H_ve [W/K] for the zone.

    Combines mechanical ventilation airflow and infiltration.
    Heat recovery efficiency reduces the effective airflow.
    """
    # Convert m3/h to m3/s
    qv_mech = ventilation.airflow_rate / 3600.0
    # Infiltration: air changes per hour -> m3/s
    qv_inf = ventilation.infiltration_rate * zone.volume / 3600.0

    # Effective mechanical airflow after heat recovery
    eta_rec = ventilation.heat_recovery_efficiency
    qv_eff_mech = qv_mech * (1.0 - eta_rec)

    # Infiltration is unrecoverable
    qv_total = qv_eff_mech + qv_inf

    return qv_total * CP_AIR_VOLUMETRIC


def ventilation_heat_loss(
    ventilation: Ventilation,
    zone: ThermalZone,
    T_int: pd.Series | np.ndarray,
    T_e: pd.Series | np.ndarray,
    schedule_profile: np.ndarray | None = None,
) -> np.ndarray:
    """Hourly ventilation heat loss [W] for the zone.

    Positive value means heat leaving the zone (loss).
    """
    H_ve = ventilation_heat_transfer_coefficient(ventilation, zone)
    dT = np.asarray(T_int) - np.asarray(T_e)
    if schedule_profile is not None:
        return np.asarray(schedule_profile * H_ve * dT, dtype=float)
    return np.asarray(H_ve * dT, dtype=float)
