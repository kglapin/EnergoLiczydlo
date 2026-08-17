"""PN-EN ISO 52016-1 clauses 6.5.4.5 and 6.5.5 design sensible loads.

This is distinct from the PN-EN 12831-1 room design-load layer.  The caller
supplies the hourly design-weather sequence from the applicable ISO 15927
procedure.  The sequence is repeated to provide at least 14 days of
initialization, then the normal ISO 52016 hourly solver is used with continuous
operation, unlimited capacity and fully convective delivery for the basic
heating/cooling design load.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import TypeAlias, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from app.engine.climate import radiation_on_surface
from app.engine.internal_gains import total_internal_gains
from app.engine.iso52016_hourly import solve_zone_iso52016
from app.engine.solar import total_solar_gains
from app.engine.ventilation import (
    ventilation_effective_supply_temperature,
    ventilation_heat_transfer_coefficient,
    ventilation_operation_profile,
)
from app.schemas.models import BuildingProject

FloatArray: TypeAlias = NDArray[np.float64]


def _arr(value: object) -> FloatArray:
    return cast(FloatArray, np.asarray(value, dtype=np.float64))


@dataclass(frozen=True)
class ZoneDesignProfile:
    zone_id: str
    heating_w: FloatArray
    cooling_w: FloatArray
    heating_design_w: float
    cooling_design_w: float


@dataclass(frozen=True)
class ISO52016DesignLoadResult:
    zones: tuple[ZoneDesignProfile, ...]
    heating_design_w: float
    cooling_design_w: float
    heating_profile_w: FloatArray
    cooling_profile_w: FloatArray
    initialization_days: int


def _tile(values: FloatArray, repetitions: int) -> FloatArray:
    return _arr(np.tile(_arr(values), repetitions))


def _raw_opaque_solar(opaque, climate: pd.DataFrame) -> dict[str, FloatArray]:
    result: dict[str, FloatArray] = {}
    for element in opaque:
        adjacent = str(getattr(element.adjacent_space_type, "value", element.adjacent_space_type))
        if adjacent != "outdoor":
            result[element.id] = np.zeros(len(climate), dtype=float)
            continue
        poa = radiation_on_surface(
            climate,
            surface_tilt=float(element.inclination),
            surface_azimuth=float(element.orientation_azimuth),
        )
        result[element.id] = (
            float(element.area) * float(element.solar_absorptance) * np.asarray(poa, dtype=float)
        )
    return result


def calculate_iso52016_design_load(
    project: BuildingProject,
    design_climate: pd.DataFrame,
    *,
    outdoor_design_temperature_c: float | None = None,
    climate_source: str | None = None,
    internal_gain_factor: float = 0.40,
    strict_conformance: bool = True,
    sky_temperature_difference_k: float = 11.0,
    minimum_initialization_days: int = 14,
) -> ISO52016DesignLoadResult:
    """Calculate basic annual design sensible heating/cooling loads.

    ``design_climate`` must contain the hourly columns used by the normal
    climate/solar routines.  For heating, when ``outdoor_design_temperature_c``
    is supplied, the mean outdoor temperature of the design sequence is
    checked against that EN 12831-1 design temperature as required by 6.5.4.5.2.
    Provenance of the sequence is mandatory in strict mode because whether the
    ISO 15927 heating/cooling design-weather construction is correct cannot be
    inferred from temperatures alone.
    """
    required = {"T_e", "GHI", "DNI", "DHI", "sun_zenith", "sun_azimuth"}
    missing = required - set(design_climate.columns)
    if missing:
        raise ValueError("design climate is missing: " + ", ".join(sorted(missing)))
    n = len(design_climate)
    if n == 0 or n % 24 != 0:
        raise ValueError("design climate must contain a whole number of 24-hour days")
    if strict_conformance and not str(climate_source or "").strip():
        raise ValueError("Strict ISO 52016 design load requires design-climate provenance")
    t_e_base = design_climate["T_e"].to_numpy(dtype=float)
    if outdoor_design_temperature_c is not None:
        mean = float(np.mean(t_e_base))
        if abs(mean - float(outdoor_design_temperature_c)) > 0.1:
            raise ValueError(
                "Heating design-weather mean must equal the EN 12831-1 outdoor design "
                f"temperature; got mean={mean:.2f} °C, design={outdoor_design_temperature_c:.2f} °C"
            )
    if not 0.0 <= internal_gain_factor <= 1.0:
        raise ValueError("internal_gain_factor must be between 0 and 1")

    days = n // 24
    warmup_repetitions = max(1, ceil(minimum_initialization_days / days))
    repetitions = warmup_repetitions + 1
    initialization_days = warmup_repetitions * days
    t_e = _tile(t_e_base, repetitions)
    building_floor_area = sum(zone.floor_area for zone in project.thermal_zones)
    zone_results: list[ZoneDesignProfile] = []

    for zone in project.thermal_zones:
        opaque = [item for item in project.opaque_building_elements if item.zone_id == zone.id]
        windows = [
            item for item in project.transparent_building_elements if item.zone_id == zone.id
        ]
        operation_base = ventilation_operation_profile(project.ventilation, design_climate.index)
        h_ve_base = ventilation_heat_transfer_coefficient(
            project.ventilation,
            zone,
            building_floor_area,
            operation_profile=operation_base,
        )
        h_ve = _tile(np.broadcast_to(np.asarray(h_ve_base, dtype=float), (n,)), repetitions)
        extract_base: FloatArray = _arr(np.full(n, float(zone.setpoint_heating)))
        t_supply_base = ventilation_effective_supply_temperature(
            project.ventilation,
            zone,
            t_e_base,
            building_floor_area=building_floor_area,
            operation_profile=operation_base,
            extract_temperature_c=extract_base,
        )
        t_supply = _tile(t_supply_base, repetitions)
        q_int_base = (
            total_internal_gains(
                zone.occupancy_density,
                zone.floor_area,
                project.internal_gains,
                design_climate.index,
            )
            * internal_gain_factor
        )
        q_sol_base, _ = total_solar_gains(windows, opaque, design_climate)
        raw_base = _raw_opaque_solar(opaque, design_climate)
        raw = {key: _tile(value, repetitions) for key, value in raw_base.items()}
        capacity = zone.air_furniture_heat_capacity_kj_m2k
        solution = solve_zone_iso52016(
            opaque_elements=opaque,
            transparent_elements=windows,
            bridges=project.thermal_bridges,
            zone_id=zone.id,
            h_ve=h_ve,
            t_e=t_e,
            phi_int=_tile(q_int_base, repetitions),
            phi_sol_transparent=_tile(q_sol_base, repetitions),
            opaque_solar_absorbed_w_by_element=raw,
            t_set_heating=float(zone.setpoint_heating),
            t_set_cooling=(None if zone.setpoint_cooling is None else float(zone.setpoint_cooling)),
            t_supply=t_supply,
            internal_convective_fraction=0.40,
            solar_convective_fraction=0.10,
            hvac_convective_fraction=1.00,
            operative_air_weight=(
                0.50 if zone.operative_air_weight is None else float(zone.operative_air_weight)
            ),
            air_furniture_heat_capacity_j_k=(
                None if capacity is None else float(capacity) * float(zone.floor_area) * 1000.0
            ),
            floor_area_m2=float(zone.floor_area),
            sky_temperature_difference_k=sky_temperature_difference_k,
            strict_conformance=strict_conformance,
        )
        heating = np.asarray(solution.q_heating[-n:], dtype=float)
        cooling = np.asarray(solution.q_cooling[-n:], dtype=float)
        zone_results.append(
            ZoneDesignProfile(
                zone_id=zone.id,
                heating_w=heating,
                cooling_w=cooling,
                heating_design_w=float(np.max(heating)),
                cooling_design_w=float(np.max(cooling)),
            )
        )

    if not zone_results:
        zeros: FloatArray = _arr(np.zeros(n))
        return ISO52016DesignLoadResult((), 0.0, 0.0, zeros, zeros, initialization_days)
    heating_sum = _arr(np.sum([item.heating_w for item in zone_results], axis=0))
    cooling_sum = _arr(np.sum([item.cooling_w for item in zone_results], axis=0))
    return ISO52016DesignLoadResult(
        zones=tuple(zone_results),
        heating_design_w=float(np.max(heating_sum)),
        cooling_design_w=float(np.max(cooling_sum)),
        heating_profile_w=np.asarray(heating_sum, dtype=float),
        cooling_profile_w=np.asarray(cooling_sum, dtype=float),
        initialization_days=initialization_days,
    )
