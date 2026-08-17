"""Ventilation and infiltration heat loss calculations.

Implements the hourly ventilation heat transfer coefficient H_ve following
PN-EN ISO 52016-1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.engine.internal_gains import evaluate_schedule
from app.schemas.models import (
    ThermalZone,
    Ventilation,
    VentilationOperationMode,
    VentilationType,
)

# Fixed volumetric heat capacity prescribed by the Polish methodology
# (§ 5.2.3.1): rho_a*c_a = 1200 J/(m3*K).
CP_AIR_VOLUMETRIC = 1200.0

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


def normative_infiltration_rate(construction_year: int) -> float:
    """Return the default infiltration ACH from the methodology.

    When no airtightness test is available, § 5.2.3.2 assigns ``n = 0.2``
    to buildings erected after 1995 and ``n = 0.3`` to older buildings.
    An explicitly entered project value always takes precedence.
    """
    return 0.2 if construction_year > 1995 else 0.3


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
        available_profiles = ", ".join(sorted(NORMATIVE_AIRFLOW_M3_S_M2))
        raise ValueError(
            f"Unsupported ventilation/DHW usage profile: {dhw_usage_profile}. "
            f"Choose one of: {available_profiles}"
        )
    vtype = str(ventilation_type)

    if vtype == "none":
        return 0.0

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


def ventilation_operation_profile(
    ventilation: Ventilation,
    datetimes: pd.DatetimeIndex,
    beta: float = 1.0,
) -> np.ndarray:
    """Return the hourly fan-operation fraction in ``[0, 1]``.

    Continuous ventilation operates at one.  For periodic ventilation an
    explicit ``Ventilation.schedule`` is used when supplied.  The default
    constant schedule is interpreted as the methodology's time-share ``β``;
    this preserves the monthly-method input while allowing the hourly thermal
    solver to use the resulting effective hourly coefficient.
    """
    if ventilation.operation_mode != VentilationOperationMode.PERIODIC:
        return np.ones(len(datetimes), dtype=float)

    schedule = ventilation.schedule
    if schedule is None:
        if not 0.0 <= beta <= 1.0:
            raise ValueError("beta must be between 0 and 1")
        return np.full(len(datetimes), beta, dtype=float)

    profile = np.asarray(evaluate_schedule(schedule, datetimes), dtype=float)
    if profile.shape != (len(datetimes),):
        raise ValueError("Ventilation schedule must produce one value per hour")
    if not np.isfinite(profile).all() or np.any((profile < 0.0) | (profile > 1.0)):
        raise ValueError("Ventilation schedule values must be between 0 and 1")
    return profile


def _hourly_profile(
    operation_profile: np.ndarray | None,
    n: int,
) -> np.ndarray | None:
    if operation_profile is None:
        return None
    profile = np.asarray(operation_profile, dtype=float)
    if profile.shape != (n,):
        raise ValueError("operation_profile must contain one value per hour")
    if not np.isfinite(profile).all() or np.any((profile < 0.0) | (profile > 1.0)):
        raise ValueError("operation_profile values must be between 0 and 1")
    return profile


def _recovery_efficiency(ventilation: Ventilation) -> float:
    """Return the recovery reduction used by the equivalent-airflow model.

    An explicit ``supply_temperature`` is an alternative to the equivalent
    ``1 - η`` reduction: it describes the actual post-treatment supply air.
    Applying both would count heat recovery twice.
    """
    if ventilation.supply_temperature is not None:
        return 0.0
    return ventilation.heat_recovery_efficiency


def ventilation_airflow_components(
    ventilation: Ventilation,
    zone: ThermalZone,
    building_floor_area: float | None = None,
    operation_profile: np.ndarray | None = None,
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """Return effective mechanical and external-air flows [m³/h].

    The first component is the mechanical flow after heat-recovery
    reduction.  The second component is unrecovered outdoor air: background
    infiltration, fan-induced infiltration, natural ventilation or exhaust
    flow.  Separating the components allows a user-supplied supply
    temperature to affect only air that actually comes from the supply system.
    """
    total_area = building_floor_area if building_floor_area else zone.floor_area
    zone_share = zone.floor_area / total_area if total_area > 0 else 0.0
    qv_nominal = (
        0.0
        if ventilation.ventilation_type == VentilationType.NONE
        else ventilation.airflow_rate * zone_share
    )
    qv_inf = ventilation.infiltration_rate * zone.volume
    qv_fan_inf = ventilation.fan_infiltration_rate * zone.volume
    vtype = ventilation.ventilation_type
    profile = _hourly_profile(
        operation_profile,
        0 if operation_profile is None else len(operation_profile),
    )

    if profile is None or ventilation.operation_mode != VentilationOperationMode.PERIODIC:
        if vtype in (
            VentilationType.MECHANICAL,
            VentilationType.MECHANICAL_WITH_RECOVERY,
        ):
            eta_rec = (
                _recovery_efficiency(ventilation)
                if vtype == VentilationType.MECHANICAL_WITH_RECOVERY
                else 0.0
            )
            return qv_nominal * (1.0 - eta_rec), qv_inf + qv_fan_inf
        return 0.0, qv_nominal + qv_inf + qv_fan_inf

    if vtype in (
        VentilationType.MECHANICAL,
        VentilationType.MECHANICAL_WITH_RECOVERY,
    ):
        eta_rec = (
            _recovery_efficiency(ventilation)
            if vtype == VentilationType.MECHANICAL_WITH_RECOVERY
            else 0.0
        )
        return (
            profile * qv_nominal * (1.0 - eta_rec),
            profile * qv_fan_inf + (1.0 - profile) * qv_inf,
        )
    if vtype in (VentilationType.EXHAUST, VentilationType.HYBRID):
        return np.zeros_like(profile), (
            profile * (qv_nominal + qv_fan_inf)
            + (1.0 - profile) * (0.1 * qv_nominal + qv_inf)
        )
    return np.zeros_like(profile), np.full_like(profile, qv_nominal + qv_inf)


def ventilation_heat_transfer_coefficient(
    ventilation: Ventilation,
    zone: ThermalZone,
    building_floor_area: float | None = None,
    operation_profile: np.ndarray | None = None,
) -> float | np.ndarray:
    """Compute H_ve [W/K] for the zone.

    Combines mechanical ventilation airflow and infiltration.  In continuous
    mode this retains the legacy scalar calculation.  In periodic mode the
    optional ``operation_profile`` applies the hourly streams from table 22:
    supply/extract air and fan-induced infiltration during operation, and
    background infiltration while the fans are off.

    ``airflow_rate`` is a building-level total [m3/h]; it is split between
    zones proportionally to floor area so that a multi-zone building does not
    multiply the design airflow.  Pass ``building_floor_area`` equal to the
    sum of all zone floor areas; when omitted, the zone is assumed to be the
    only conditioned zone (backward-compatible single-zone behaviour).
    """
    mechanical_flow, external_flow = ventilation_airflow_components(
        ventilation,
        zone,
        building_floor_area,
        operation_profile,
    )
    total_flow = (
        np.asarray(mechanical_flow, dtype=float)
        + np.asarray(external_flow, dtype=float)
    )
    result = total_flow / 3600.0 * CP_AIR_VOLUMETRIC
    return float(result) if result.ndim == 0 else result


def ventilation_effective_supply_temperature(
    ventilation: Ventilation,
    zone: ThermalZone,
    t_e: np.ndarray,
    building_floor_area: float | None = None,
    operation_profile: np.ndarray | None = None,
) -> np.ndarray:
    """Return the equivalent supply temperature seen by the single 5R1C Hve.

    With no explicit supply temperature the result is outdoor air, including
    the usual equivalent reduction of the recovered mechanical flow.  With a
    supplied temperature, only the mechanical component uses it; infiltration
    and exhaust/natural air still use ``t_e``.
    """
    outdoor = np.asarray(t_e, dtype=float)
    if outdoor.ndim != 1:
        raise ValueError("t_e must be a one-dimensional hourly array")
    if ventilation.supply_temperature is None:
        return outdoor.copy()

    mechanical_flow, external_flow = ventilation_airflow_components(
        ventilation,
        zone,
        building_floor_area,
        operation_profile,
    )
    mechanical = np.asarray(mechanical_flow, dtype=float)
    external = np.asarray(external_flow, dtype=float)
    if mechanical.ndim == 0:
        mechanical = np.full(len(outdoor), float(mechanical))
        external = np.full(len(outdoor), float(external))
    if mechanical.shape != outdoor.shape or external.shape != outdoor.shape:
        raise ValueError("Ventilation airflow components must match the climate length")
    total = mechanical + external
    result = outdoor.copy()
    np.divide(
        mechanical * ventilation.supply_temperature + external * outdoor,
        total,
        out=result,
        where=total > 0.0,
    )
    return result


def ventilation_heat_loss(
    ventilation: Ventilation,
    zone: ThermalZone,
    T_int: pd.Series | np.ndarray,
    T_e: pd.Series | np.ndarray,
    schedule_profile: np.ndarray | None = None,
    building_floor_area: float | None = None,
    operation_profile: np.ndarray | None = None,
    T_supply: pd.Series | np.ndarray | None = None,
) -> np.ndarray:
    """Hourly ventilation heat loss [W] for the zone.

    Positive value means heat leaving the zone (loss).
    """
    H_ve = ventilation_heat_transfer_coefficient(
        ventilation,
        zone,
        building_floor_area,
        operation_profile=operation_profile,
    )
    supply = np.asarray(T_e if T_supply is None else T_supply, dtype=float)
    indoor = np.asarray(T_int, dtype=float)
    outdoor = np.asarray(T_e, dtype=float)
    if supply.shape != indoor.shape or outdoor.shape != indoor.shape:
        raise ValueError("T_int, T_e and T_supply must have matching shapes")
    dT = indoor - supply
    if schedule_profile is not None:
        profile = np.asarray(schedule_profile, dtype=float)
        if profile.shape != indoor.shape:
            raise ValueError("schedule_profile must match the hourly temperature shape")
        if not np.isfinite(profile).all() or np.any((profile < 0.0) | (profile > 1.0)):
            raise ValueError("schedule_profile values must be between 0 and 1")
        if operation_profile is not None:
            raise ValueError("Use either schedule_profile or operation_profile, not both")
        return np.asarray(profile * H_ve * dT, dtype=float)
    return np.asarray(H_ve * dT, dtype=float)
