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

# Normatywne podstawowe strumienie powietrza V_ve,1,s [m3/(s·m2)] - tabele
# 24 (mieszkalne, grawitacyjna / mechaniczna wywiewna) i 25 (użyteczności
# publicznej itd.) rozporządzenia. Klucz = profil użytkowania CWU.
NORMATIVE_AIRFLOW_M3_S_M2: dict[str, float] = {
    "residential_single_family": 0.31e-3,
    "residential_multi_family_lump_sum": 0.31e-3,
    "residential_multi_family_individual_metering": 0.31e-3,
    "office": 0.56e-3,
    "education": 0.56e-3,
    "healthcare": 0.42e-3,
    "retail_services": 0.33e-3,
    "collective_residential": 0.42e-3,
    "warehouse": 0.08e-3,
}

# Stopień zmniejszenia strumienia r_n dla wentylacji nawiewno-wywiewnej
# (wzór (71) i przypis) przy braku danych o regulacji.
SUPPLY_EXTRACT_FLOW_REDUCTION = 0.75


def normative_airflow_rate_m3h(
    dhw_usage_profile: str,
    floor_area_m2: float,
    ventilation_type: str,
    beta: float = 1.0,
) -> float:
    """Uśredniony w czasie strumień podstawowy [m3/h] wg tabel 21/22/24/25.

    Budynek mieszkalny (tabela 21): praca ciągła, strumień V0 (bez β).
    Budynki użyteczności publicznej (tabela 22): strumień podstawowy działa
    w udziale czasu β, poza okresem użytkowania pozostaje strumień
    zredukowany: 0,2·V0 (grawitacyjna), 0,1·V_ex (wywiewna), 0
    (nawiewno-wywiewna).  Dla nawiewno-wywiewnej stosowane jest r_n = 0,75
    oraz odzysk ciepła (1 - η_oc).
    """
    base = NORMATIVE_AIRFLOW_M3_S_M2.get(str(dhw_usage_profile))
    if base is None:
        base = 0.31e-3  # brak profilu -> wartość mieszkaniowa
    vtype = str(ventilation_type)

    residential = str(dhw_usage_profile).startswith("residential")
    if residential:
        beta = 1.0  # tabela 21: praca ciągła

    if vtype in ("mechanical", "mechanical_with_recovery"):
        base = base * SUPPLY_EXTRACT_FLOW_REDUCTION  # r_n, wzór (71)
        share = beta  # tabela 22 w.3: β·V_su, poza użytkowaniem 0
    elif vtype in ("exhaust", "hybrid"):
        share = beta + (1.0 - beta) * 0.1  # tabela 22 w.2
    else:  # natural / none
        share = beta + (1.0 - beta) * 0.2  # tabela 22 w.1

    return base * share * floor_area_m2 * 3600.0


def ventilation_heat_transfer_coefficient(
    ventilation: Ventilation,
    zone: ThermalZone,
    building_floor_area: float | None = None,
) -> float:
    """Compute H_ve [W/K] for the zone.

    Combines mechanical ventilation airflow and infiltration.
    Heat recovery efficiency reduces the effective airflow.

    ``airflow_rate`` is a building-level total [m3/h]; it is split between
    zones proportionally to floor area so that a multi-zone building does not
    multiply the design airflow.  Pass ``building_floor_area`` equal to the
    sum of all zone floor areas; when omitted, the zone is assumed to be the
    only conditioned zone (backward-compatible single-zone behaviour).
    """
    total_area = building_floor_area if building_floor_area else zone.floor_area
    zone_share = zone.floor_area / total_area if total_area > 0 else 0.0

    # Convert m3/h to m3/s
    qv_mech = ventilation.airflow_rate * zone_share / 3600.0
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
    building_floor_area: float | None = None,
) -> np.ndarray:
    """Hourly ventilation heat loss [W] for the zone.

    Positive value means heat leaving the zone (loss).
    """
    H_ve = ventilation_heat_transfer_coefficient(ventilation, zone, building_floor_area)
    dT = np.asarray(T_int) - np.asarray(T_e)
    if schedule_profile is not None:
        return np.asarray(schedule_profile * H_ve * dT, dtype=float)
    return np.asarray(H_ve * dT, dtype=float)
