"""Runtime helpers shared by audited normative extensions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.engine.heat_recovery import heat_recovery_state
from app.engine.ventilation import (
    normative_airflow_rate_m3h,
    normative_infiltration_rate,
    ventilation_airflow_components,
    ventilation_operation_profile,
)
from app.schemas.models import BuildingProject, Ventilation, ZoneType

CONDITIONED_TYPES = {
    ZoneType.HEATED,
    ZoneType.COOLED,
    ZoneType.HEATED_AND_COOLED,
    ZoneType.SEMI_HEATED,
}


@dataclass(frozen=True)
class HeatRecoveryAnnualStats:
    preheater_energy_wh: float
    bypass_hours: int
    frost_risk_hours: int
    recovery_active_hours: int


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def resolve_hourly_ventilation(
    project: BuildingProject,
    datetimes: pd.DatetimeIndex,
) -> tuple[Ventilation, np.ndarray, float]:
    """Resolve defaults exactly as the annual calculator does."""
    ventilation = project.ventilation
    if "infiltration_rate" not in ventilation.model_fields_set:
        ventilation = ventilation.model_copy(
            update={
                "infiltration_rate": normative_infiltration_rate(
                    project.general.construction_year
                )
            }
        )
        advanced = getattr(project.ventilation, "_heat_recovery_settings", None)
        if advanced is not None:
            object.__setattr__(ventilation, "_heat_recovery_settings", advanced)

    building_floor_area = sum(
        zone.floor_area
        for zone in project.thermal_zones
        if zone.zone_type in CONDITIONED_TYPES
    )
    profile_value = _enum_value(project.general.dhw_usage_profile)
    residential = profile_value.startswith("residential")
    beta = (
        ventilation.usage_share_beta
        if ventilation.usage_share_beta is not None
        else (1.0 if residential else 0.3)
    )

    if ventilation.airflow_rate == 0.0:
        normative_beta = (
            1.0 if _enum_value(ventilation.operation_mode) == "periodic" else beta
        )
        airflow = normative_airflow_rate_m3h(
            profile_value,
            building_floor_area,
            _enum_value(ventilation.ventilation_type),
            beta=normative_beta,
        )
        ventilation = ventilation.model_copy(update={"airflow_rate": airflow})
        advanced = getattr(project.ventilation, "_heat_recovery_settings", None)
        if advanced is not None:
            object.__setattr__(ventilation, "_heat_recovery_settings", advanced)

    operation = ventilation_operation_profile(ventilation, datetimes, beta=beta)
    return ventilation, operation, float(building_floor_area)


def annual_heat_recovery_stats(
    project: BuildingProject,
    climate: pd.DataFrame,
) -> HeatRecoveryAnnualStats:
    """Return preheater electricity and controller operating-hour diagnostics."""
    ventilation, operation, building_area = resolve_hourly_ventilation(
        project, climate.index
    )
    outdoor = climate["T_e"].to_numpy(dtype=float)
    total_preheater = np.zeros(len(outdoor), dtype=float)
    bypass_any = np.zeros(len(outdoor), dtype=bool)
    frost_any = np.zeros(len(outdoor), dtype=bool)
    recovery_any = np.zeros(len(outdoor), dtype=bool)

    for zone in project.thermal_zones:
        if zone.zone_type not in CONDITIONED_TYPES:
            continue
        mechanical, _external = ventilation_airflow_components(
            ventilation,
            zone,
            building_area,
            operation_profile=operation,
        )
        flow = np.asarray(mechanical, dtype=float)
        if flow.ndim == 0:
            flow = np.full(len(outdoor), float(flow), dtype=float)
        capacity_fraction = zone.floor_area / building_area if building_area > 0.0 else 0.0
        state = heat_recovery_state(
            ventilation,
            zone,
            outdoor,
            flow,
            operation_profile=None,
            capacity_fraction=capacity_fraction,
        )
        total_preheater += state.preheater_power_w
        bypass_any |= state.bypass_active
        frost_any |= state.frost_risk
        recovery_any |= (state.effective_efficiency > 0.0) & (flow > 0.0)

    return HeatRecoveryAnnualStats(
        preheater_energy_wh=float(np.sum(total_preheater)),
        bypass_hours=int(np.count_nonzero(bypass_any)),
        frost_risk_hours=int(np.count_nonzero(frost_any)),
        recovery_active_hours=int(np.count_nonzero(recovery_any)),
    )
