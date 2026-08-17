"""Room-level design-load compatibility layer.

When ``BuildingProject.design_rooms`` is supplied, design transmission,
ventilation and heat-up loads are calculated per room and then aggregated to
zones and the whole building. Certificate mode fails closed if the room model
is absent or if an envelope item is not assigned to a room.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.engine.ventilation import (
    ventilation_effective_supply_temperature,
    ventilation_heat_transfer_coefficient,
)
from app.schemas.models import ThermalZone

_LEGACY_NAME = "app.engine._legacy_design_load"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "design_load.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load legacy design load from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)


@dataclass(frozen=True)
class RoomDesignLoad:
    room_id: str
    room_name: str
    zone_id: str
    transmission_w: float
    ventilation_w: float
    heat_up_w: float
    total_w: float


@dataclass(frozen=True)
class BuildingDesignLoad:
    zones: tuple
    total_w: float
    rooms: tuple[RoomDesignLoad, ...] = ()


def _room_transmission_load_w(
    project,
    room,
    settings,
    annual_mean_outdoor_c: float,
) -> float:
    outdoor = _legacy._design_outdoor_temperature(settings)
    zone = next(zone for zone in project.thermal_zones if zone.id == room.zone_id)
    indoor = float(
        room.design_temperature_c
        if room.design_temperature_c is not None
        else zone.setpoint_heating
    )
    opaque_by_id = {element.id: element for element in project.opaque_building_elements}
    transparent_by_id = {
        element.id: element for element in project.transparent_building_elements
    }
    linear_by_id = {bridge.id: bridge for bridge in project.thermal_bridges.linear_bridges}
    point_by_id = {bridge.id: bridge for bridge in project.thermal_bridges.point_bridges}

    load = 0.0
    for element_id in room.opaque_element_ids:
        element = opaque_by_id[element_id]
        adjacent = _legacy._opaque_adjacent_temperature(
            element,
            settings,
            outdoor,
            annual_mean_outdoor_c,
        )
        if adjacent is not None:
            load += float(element.area) * float(element.u_value) * max(
                indoor - adjacent,
                0.0,
            )
    for element_id in room.transparent_element_ids:
        element = transparent_by_id[element_id]
        load += float(element.area) * float(element.u_value) * max(
            indoor - outdoor,
            0.0,
        )
    delta_outdoor = max(indoor - outdoor, 0.0)
    for bridge_id in room.linear_bridge_ids:
        bridge = linear_by_id[bridge_id]
        load += float(bridge.psi_value) * float(bridge.length) * delta_outdoor
    for bridge_id in room.point_bridge_ids:
        bridge = point_by_id[bridge_id]
        load += float(bridge.chi_value) * int(bridge.count) * delta_outdoor
    return float(max(load, 0.0))


def _room_ventilation_load_w(
    project,
    room,
    settings,
    ventilation,
    building_floor_area: float,
) -> float:
    if ventilation.ventilation_type == _legacy.VentilationType.NONE:
        return 0.0
    zone = next(zone for zone in project.thermal_zones if zone.id == room.zone_id)
    indoor = float(
        room.design_temperature_c
        if room.design_temperature_c is not None
        else zone.setpoint_heating
    )
    room_zone = ThermalZone(
        id=f"design-room:{room.id}",
        name=room.name,
        zone_type=zone.zone_type,
        floor_area=room.floor_area,
        volume=room.volume,
        setpoint_heating=indoor,
        setpoint_cooling=zone.setpoint_cooling,
        occupancy_density=0.0,
    )
    room_ventilation = ventilation
    if room.ventilation_airflow_m3h is not None:
        # The ventilation function interprets airflow_rate as a building total
        # and multiplies by floor-area share. Scale it so this synthetic room
        # receives exactly the explicitly specified design flow.
        building_equivalent = float(room.ventilation_airflow_m3h) * (
            building_floor_area / room.floor_area
        )
        room_ventilation = room_ventilation.model_copy(
            update={"airflow_rate": building_equivalent}
        )
    if room.infiltration_rate_1h is not None:
        room_ventilation = room_ventilation.model_copy(
            update={"infiltration_rate": float(room.infiltration_rate_1h)}
        )

    outdoor = np.asarray([_legacy._design_outdoor_temperature(settings)], dtype=float)
    h_ve = ventilation_heat_transfer_coefficient(
        room_ventilation,
        room_zone,
        building_floor_area,
        operation_profile=np.ones(1, dtype=float),
    )
    h_value = float(np.asarray(h_ve, dtype=float).reshape(-1)[0])
    supply = ventilation_effective_supply_temperature(
        room_ventilation,
        room_zone,
        outdoor,
        building_floor_area=building_floor_area,
        operation_profile=np.ones(1, dtype=float),
        extract_temperature_c=np.asarray([indoor], dtype=float),
    )
    return float(max(h_value * (indoor - float(supply[0])), 0.0))


def _validate_room_assignment_for_certificate(project) -> None:
    assigned_opaque = {
        element_id for room in project.design_rooms for element_id in room.opaque_element_ids
    }
    assigned_transparent = {
        element_id
        for room in project.design_rooms
        for element_id in room.transparent_element_ids
    }
    assigned_linear = {
        bridge_id for room in project.design_rooms for bridge_id in room.linear_bridge_ids
    }
    assigned_point = {
        bridge_id for room in project.design_rooms for bridge_id in room.point_bridge_ids
    }
    expected_opaque = {
        element.id
        for element in project.opaque_building_elements
        if element.adjacent_space_type != _legacy.AdjacentSpaceType.HEATED_ZONE
    }
    expected_transparent = {element.id for element in project.transparent_building_elements}
    expected_linear = {bridge.id for bridge in project.thermal_bridges.linear_bridges}
    expected_point = {bridge.id for bridge in project.thermal_bridges.point_bridges}
    missing = (
        (expected_opaque - assigned_opaque)
        | (expected_transparent - assigned_transparent)
        | (expected_linear - assigned_linear)
        | (expected_point - assigned_point)
    )
    if missing:
        raise ValueError(
            "Certificate-grade design load requires every envelope item to be "
            "assigned to a design room. Missing: " + ", ".join(sorted(missing))
        )


def calculate_design_heat_load(
    project,
    settings,
    annual_mean_outdoor_c: float,
) -> BuildingDesignLoad:
    if not settings.enabled:
        return BuildingDesignLoad(zones=(), total_w=0.0, rooms=())
    _legacy._design_outdoor_temperature(settings)

    if not project.design_rooms:
        if settings.certificate_mode:
            raise ValueError(
                "Certificate-grade PN-EN 12831-1 design load requires "
                "BuildingProject.design_rooms"
            )
        legacy_result = _legacy.calculate_design_heat_load(
            project,
            settings,
            annual_mean_outdoor_c,
        )
        return BuildingDesignLoad(
            zones=legacy_result.zones,
            total_w=legacy_result.total_w,
            rooms=(),
        )

    if settings.certificate_mode:
        _validate_room_assignment_for_certificate(project)

    ventilation = _legacy._resolved_design_ventilation(project)
    building_floor_area = sum(room.floor_area for room in project.design_rooms)
    zone_area = {
        zone.id: sum(
            room.floor_area for room in project.design_rooms if room.zone_id == zone.id
        )
        for zone in project.thermal_zones
    }
    room_results: list[RoomDesignLoad] = []
    for room in project.design_rooms:
        transmission = _room_transmission_load_w(
            project,
            room,
            settings,
            annual_mean_outdoor_c,
        )
        ventilation_loss = _room_ventilation_load_w(
            project,
            room,
            settings,
            ventilation,
            building_floor_area,
        )
        zone_heat_up = float(settings.heat_up_power_by_zone_w.get(room.zone_id, 0.0))
        heat_up = (
            zone_heat_up * room.floor_area / zone_area[room.zone_id]
            if zone_area.get(room.zone_id, 0.0) > 0.0
            else 0.0
        )
        total = transmission + ventilation_loss + heat_up
        room_results.append(
            RoomDesignLoad(
                room_id=room.id,
                room_name=room.name,
                zone_id=room.zone_id,
                transmission_w=transmission,
                ventilation_w=ventilation_loss,
                heat_up_w=heat_up,
                total_w=total,
            )
        )

    zone_results = []
    for zone in project.thermal_zones:
        members = [room for room in room_results if room.zone_id == zone.id]
        if not members:
            continue
        zone_results.append(
            _legacy.ZoneDesignLoad(
                zone_id=zone.id,
                zone_name=zone.name,
                transmission_w=sum(item.transmission_w for item in members),
                ventilation_w=sum(item.ventilation_w for item in members),
                heat_up_w=sum(item.heat_up_w for item in members),
                total_w=sum(item.total_w for item in members),
            )
        )
    return BuildingDesignLoad(
        zones=tuple(zone_results),
        total_w=float(sum(room.total_w for room in room_results)),
        rooms=tuple(room_results),
    )


_legacy.calculate_design_heat_load = calculate_design_heat_load
