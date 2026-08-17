"""Extended schema for audited PN-EN ISO 52016-1 calculations.

The historical schema remains the compatibility base.  This package adds the
inputs needed by the detailed hourly surface/node model and by room-level
PN-EN 12831-1 design-load calculations without invalidating older project JSON.
"""
from __future__ import annotations

import importlib.util
import sys
from math import isclose
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

_LEGACY_NAME = "app.schemas._legacy_models"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "models.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load legacy schema from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)
for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)

MassDistributionClass = Literal["internal", "external", "middle", "distributed", "internal_external"]


class _SurfaceInputs:
    """Documentation mixin only; Pydantic fields are repeated in concrete models."""


class OpaqueElement(_legacy.OpaqueElement):
    """Opaque element with explicit ISO 52016 surface and five-node inputs.

    The preferred resistance format contains four *core* resistances between
    the five construction nodes, ordered exterior -> interior.  A six-value
    historical format (including surface films) is accepted only for backwards
    compatibility and is rejected by strict ISO 52016 execution.
    """
    areal_heat_capacity: float | None = Field(None, gt=0.0)
    mass_distribution_class: MassDistributionClass | None = None
    thermal_node_capacities_kj_m2k: list[float] | None = None
    thermal_node_resistances_m2k_w: list[float] | None = None
    h_ci_w_m2k: float | None = Field(None, ge=0.0)
    h_ri_w_m2k: float | None = Field(None, ge=0.0)
    h_ce_w_m2k: float | None = Field(None, ge=0.0)
    h_re_w_m2k: float | None = Field(None, ge=0.0)
    sky_view_factor: float | None = Field(None, ge=0.0, le=1.0)
    ground_virtual_resistance_m2k_w: float | None = Field(None, gt=0.0)

    @model_validator(mode="after")
    def validate_hourly_construction_data(self) -> "OpaqueElement":
        capacities = self.thermal_node_capacities_kj_m2k
        resistances = self.thermal_node_resistances_m2k_w
        if capacities is not None:
            if len(capacities) != 5:
                raise ValueError("thermal_node_capacities_kj_m2k must contain exactly 5 values")
            if any(value < 0.0 for value in capacities) or sum(capacities) <= 0.0:
                raise ValueError("thermal node capacities must be non-negative with positive total")
        if resistances is not None:
            if len(resistances) not in {4, 6}:
                raise ValueError("thermal_node_resistances_m2k_w must contain 4 core values or 6 legacy values")
            if any(value <= 0.0 for value in resistances):
                raise ValueError("thermal node resistances must be strictly positive")
            if len(resistances) == 6:
                expected = 1.0 / float(self.u_value)
                actual = float(sum(resistances))
                if not isclose(actual, expected, rel_tol=0.05, abs_tol=0.01):
                    raise ValueError(
                        "Legacy six-resistance data must reproduce 1/U within 5%; "
                        f"got sum(R)={actual:.4f}, 1/U={expected:.4f}"
                    )
        if self.areal_heat_capacity is not None and self.mass_distribution_class is None:
            raise ValueError("mass_distribution_class is required when areal_heat_capacity is supplied")
        return self


class TransparentElement(_legacy.TransparentElement):
    """Transparent element represented by two zero-capacity surface nodes."""
    h_ci_w_m2k: float | None = Field(None, ge=0.0)
    h_ri_w_m2k: float | None = Field(None, ge=0.0)
    h_ce_w_m2k: float | None = Field(None, ge=0.0)
    h_re_w_m2k: float | None = Field(None, ge=0.0)
    core_thermal_resistance_m2k_w: float | None = Field(None, gt=0.0)
    sky_view_factor: float | None = Field(None, ge=0.0, le=1.0)


class ThermalZone(_legacy.ThermalZone):
    """Thermal zone with optional inputs delegated by ISO 52016 to EPB modules."""
    air_furniture_heat_capacity_kj_m2k: float | None = Field(None, gt=0.0)
    operative_air_weight: float | None = Field(None, ge=0.0, le=1.0)
    relative_humidity_min: float | None = Field(None, ge=0.0, le=1.0)
    relative_humidity_max: float | None = Field(None, ge=0.0, le=1.0)
    moisture_generation_kg_s: float | None = Field(None, ge=0.0)

    @model_validator(mode="after")
    def validate_humidity_band(self) -> "ThermalZone":
        if (
            self.relative_humidity_min is not None
            and self.relative_humidity_max is not None
            and self.relative_humidity_min > self.relative_humidity_max
        ):
            raise ValueError("relative_humidity_min cannot exceed relative_humidity_max")
        return self


class LinearThermalBridge(_legacy.LinearThermalBridge):
    adjacent_space_type: AdjacentSpaceType | None = None
    adjacent_temperature: float | None = None


class PointThermalBridge(_legacy.PointThermalBridge):
    element_id: str | None = None
    adjacent_space_type: AdjacentSpaceType | None = None
    adjacent_temperature: float | None = None


class ThermalBridgeConfig(_legacy.ThermalBridgeConfig):
    linear_bridges: list[LinearThermalBridge] = Field(default_factory=list)
    point_bridges: list[PointThermalBridge] = Field(default_factory=list)


class DesignRoom(_legacy.BaseModel):
    id: str = Field(..., min_length=1)
    name: str
    zone_id: str = Field(..., min_length=1)
    floor_area: float = Field(..., gt=0.0)
    volume: float = Field(..., gt=0.0)
    design_temperature_c: float | None = None
    ventilation_airflow_m3h: float | None = Field(None, ge=0.0)
    infiltration_rate_1h: float | None = Field(None, ge=0.0)
    opaque_element_ids: list[str] = Field(default_factory=list)
    transparent_element_ids: list[str] = Field(default_factory=list)
    linear_bridge_ids: list[str] = Field(default_factory=list)
    point_bridge_ids: list[str] = Field(default_factory=list)


class BuildingProject(_legacy.BuildingProject):
    opaque_building_elements: list[OpaqueElement]
    transparent_building_elements: list[TransparentElement]
    thermal_zones: list[ThermalZone]
    thermal_bridges: ThermalBridgeConfig = Field(default_factory=ThermalBridgeConfig)
    design_rooms: list[DesignRoom] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_design_rooms(self) -> "BuildingProject":
        if not self.design_rooms:
            return self
        zones = {zone.id: zone for zone in self.thermal_zones}
        room_ids = [room.id for room in self.design_rooms]
        if len(room_ids) != len(set(room_ids)):
            raise ValueError("Design room IDs must be unique")
        unknown = sorted({room.zone_id for room in self.design_rooms} - set(zones))
        if unknown:
            raise ValueError("Unknown thermal zone referenced by design room: " + ", ".join(unknown))
        known_sets = {
            "opaque_element_ids": {item.id for item in self.opaque_building_elements},
            "transparent_element_ids": {item.id for item in self.transparent_building_elements},
            "linear_bridge_ids": {item.id for item in self.thermal_bridges.linear_bridges},
            "point_bridge_ids": {item.id for item in self.thermal_bridges.point_bridges},
        }
        used: dict[str, str] = {}
        for room in self.design_rooms:
            for field_name, known in known_sets.items():
                values = getattr(room, field_name)
                missing = sorted(set(values) - known)
                if missing:
                    raise ValueError(f"Design room '{room.id}' has unknown {field_name}: " + ", ".join(missing))
                for value in values:
                    key = f"{field_name}:{value}"
                    if key in used and used[key] != room.id:
                        raise ValueError(f"Envelope item '{value}' is assigned to more than one design room")
                    used[key] = room.id
        for zone_id, zone in zones.items():
            rooms = [room for room in self.design_rooms if room.zone_id == zone_id]
            if not rooms:
                continue
            area = sum(room.floor_area for room in rooms)
            volume = sum(room.volume for room in rooms)
            if not isclose(area, zone.floor_area, rel_tol=1e-6, abs_tol=0.01):
                raise ValueError(f"Design-room floor areas in zone '{zone_id}' must sum to zone floor area")
            if not isclose(volume, zone.volume, rel_tol=1e-6, abs_tol=0.01):
                raise ValueError(f"Design-room volumes in zone '{zone_id}' must sum to zone volume")
        return self


OpaqueElement.model_rebuild()
TransparentElement.model_rebuild()
ThermalZone.model_rebuild()
ThermalBridgeConfig.model_rebuild()
BuildingProject.model_rebuild()
