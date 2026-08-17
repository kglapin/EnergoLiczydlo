"""Project design heat-load calculation separated from annual TMY simulation.

The calculation uses explicit project design conditions and reports room/zone
heat loads as useful thermal power. It deliberately does not use the coldest
TMY hour and does not divide the building load by generator COP/efficiency.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.engine.normative_models import DesignConditionsSettings
from app.engine.ventilation import (
    normative_airflow_rate_m3h,
    normative_infiltration_rate,
    ventilation_effective_supply_temperature,
    ventilation_heat_transfer_coefficient,
)
from app.schemas.models import (
    AdjacentSpaceType,
    BuildingProject,
    OpaqueElement,
    ThermalZone,
    Ventilation,
    VentilationType,
    ZoneType,
)

CONDITIONED_TYPES = {
    ZoneType.HEATED,
    ZoneType.HEATED_AND_COOLED,
    ZoneType.SEMI_HEATED,
}


@dataclass(frozen=True)
class ZoneDesignLoad:
    zone_id: str
    zone_name: str
    transmission_w: float
    ventilation_w: float
    heat_up_w: float
    total_w: float


@dataclass(frozen=True)
class BuildingDesignLoad:
    zones: tuple[ZoneDesignLoad, ...]
    total_w: float


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _design_outdoor_temperature(settings: DesignConditionsSettings) -> float:
    value = settings.outdoor_design_temperature_c
    if value is None:
        raise ValueError("Design-load calculation requires outdoor design temperature")
    return float(value)


def _resolved_design_ventilation(project: BuildingProject) -> Ventilation:
    ventilation = project.ventilation
    if "infiltration_rate" not in ventilation.model_fields_set:
        ventilation = ventilation.model_copy(
            update={
                "infiltration_rate": normative_infiltration_rate(
                    project.general.construction_year
                )
            }
        )
    if ventilation.airflow_rate != 0.0:
        return ventilation
    floor_area = sum(
        zone.floor_area
        for zone in project.thermal_zones
        if zone.zone_type in CONDITIONED_TYPES
    )
    profile = _enum_value(project.general.dhw_usage_profile)
    airflow = normative_airflow_rate_m3h(
        profile,
        floor_area,
        _enum_value(ventilation.ventilation_type),
        beta=1.0,
    )
    resolved = ventilation.model_copy(update={"airflow_rate": airflow})
    advanced = getattr(project.ventilation, "_heat_recovery_settings", None)
    if advanced is not None:
        object.__setattr__(resolved, "_heat_recovery_settings", advanced)
    return resolved


def _ground_design_temperature(
    element: OpaqueElement,
    annual_mean_outdoor_c: float,
) -> float:
    profile = getattr(element, "_ground_temperature_profile", None)
    if profile is None:
        return annual_mean_outdoor_c
    values = np.asarray(profile, dtype=float)
    return float(np.mean(values))


def _opaque_adjacent_temperature(
    element: OpaqueElement,
    settings: DesignConditionsSettings,
    outdoor_design_c: float,
    annual_mean_outdoor_c: float,
) -> float | None:
    adjacent = element.adjacent_space_type
    if adjacent == AdjacentSpaceType.OUTDOOR:
        return outdoor_design_c
    if adjacent == AdjacentSpaceType.GROUND:
        return _ground_design_temperature(element, annual_mean_outdoor_c)
    if adjacent == AdjacentSpaceType.CONSTANT_TEMPERATURE:
        value = element.adjacent_temperature
        if value is None:
            raise ValueError(
                f"Element {element.id} requires adjacent_temperature"
            )
        return float(value)
    if adjacent == AdjacentSpaceType.UNHEATED_ZONE:
        element_id = str(element.id)
        explicit = settings.unheated_adjacent_temperature_by_element_c.get(element_id)
        if explicit is not None:
            return float(explicit)
        if settings.certificate_mode:
            raise ValueError(
                "Design load requires explicit unheated adjacent temperature for "
                f"element '{element_id}' in certificate mode"
            )
        return outdoor_design_c + 3.0
    if adjacent == AdjacentSpaceType.HEATED_ZONE:
        return None
    raise ValueError(f"Unsupported adjacent-space type: {adjacent}")


def _zone_transmission_load_w(
    project: BuildingProject,
    zone: ThermalZone,
    settings: DesignConditionsSettings,
    annual_mean_outdoor_c: float,
) -> float:
    outdoor = _design_outdoor_temperature(settings)
    indoor = float(zone.setpoint_heating)
    load = 0.0

    for element in project.opaque_building_elements:
        if element.zone_id != zone.id:
            continue
        adjacent = _opaque_adjacent_temperature(
            element,
            settings,
            outdoor,
            annual_mean_outdoor_c,
        )
        if adjacent is None:
            continue
        load += float(element.area) * float(element.u_value) * max(indoor - adjacent, 0.0)

    for element in project.transparent_building_elements:
        if element.zone_id != zone.id:
            continue
        load += float(element.area) * float(element.u_value) * max(indoor - outdoor, 0.0)

    delta_outdoor = max(indoor - outdoor, 0.0)
    for bridge in project.thermal_bridges.linear_bridges:
        if bridge.zone_id == zone.id:
            load += float(bridge.psi_value) * float(bridge.length) * delta_outdoor
    for bridge in project.thermal_bridges.point_bridges:
        if bridge.zone_id == zone.id:
            load += float(bridge.chi_value) * int(bridge.count) * delta_outdoor

    return float(max(load, 0.0))


def _zone_ventilation_load_w(
    project: BuildingProject,
    zone: ThermalZone,
    ventilation: Ventilation,
    settings: DesignConditionsSettings,
    building_floor_area: float,
) -> float:
    if ventilation.ventilation_type == VentilationType.NONE:
        return 0.0
    outdoor = np.asarray([_design_outdoor_temperature(settings)], dtype=float)
    operation = np.ones(1, dtype=float)
    h_ve = ventilation_heat_transfer_coefficient(
        ventilation,
        zone,
        building_floor_area,
        operation_profile=operation,
    )
    h_value = float(np.asarray(h_ve, dtype=float).reshape(-1)[0])
    supply = ventilation_effective_supply_temperature(
        ventilation,
        zone,
        outdoor,
        building_floor_area=building_floor_area,
        operation_profile=operation,
    )
    return float(max(h_value * (zone.setpoint_heating - float(supply[0])), 0.0))


def calculate_design_heat_load(
    project: BuildingProject,
    settings: DesignConditionsSettings,
    annual_mean_outdoor_c: float,
) -> BuildingDesignLoad:
    """Calculate useful design heat load for conditioned zones [W]."""
    if not settings.enabled:
        return BuildingDesignLoad(zones=(), total_w=0.0)
    _design_outdoor_temperature(settings)
    ventilation = _resolved_design_ventilation(project)
    building_floor_area = sum(
        zone.floor_area
        for zone in project.thermal_zones
        if zone.zone_type in CONDITIONED_TYPES
    )
    zone_results: list[ZoneDesignLoad] = []

    for zone in project.thermal_zones:
        if zone.zone_type not in CONDITIONED_TYPES:
            continue
        transmission = _zone_transmission_load_w(
            project,
            zone,
            settings,
            annual_mean_outdoor_c,
        )
        ventilation_loss = _zone_ventilation_load_w(
            project,
            zone,
            ventilation,
            settings,
            building_floor_area,
        )
        heat_up = float(settings.heat_up_power_by_zone_w.get(zone.id, 0.0))
        total = transmission + ventilation_loss + heat_up
        zone_results.append(
            ZoneDesignLoad(
                zone_id=zone.id,
                zone_name=zone.name,
                transmission_w=transmission,
                ventilation_w=ventilation_loss,
                heat_up_w=heat_up,
                total_w=total,
            )
        )

    return BuildingDesignLoad(
        zones=tuple(zone_results),
        total_w=float(sum(zone.total_w for zone in zone_results)),
    )
