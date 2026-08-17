"""Extended schema for audited PN-EN ISO 52016-1 calculations.

The historical schema remains the compatibility base. This package adds the
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

AdjacentSpaceType = _legacy.AdjacentSpaceType

MassDistributionClass = Literal[
    "internal", "external", "middle", "distributed", "internal_external"
]


class OpaqueElement(_legacy.OpaqueElement):
    """Opaque element with explicit ISO 52016 surface and five-node inputs.

    The preferred resistance format contains four core resistances between the
    five construction nodes, ordered exterior -> interior. A six-value
    historical format (including surface films) is accepted for compatibility.
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
    def validate_iso52016_surface_inputs(self) -> OpaqueElement:
        caps = self.thermal_node_capacities_kj_m2k
        resistances = self.thermal_node_resistances_m2k_w
        if (caps is None) != (resistances is None):
            raise ValueError(
                "thermal_node_capacities_kj_m2k and thermal_node_resistances_m2k_w "
                "must be provided together"
            )
        if caps is not None and resistances is not None:
            if len(caps) != 5:
                raise ValueError("thermal_node_capacities_kj_m2k must contain exactly 5 values")
            if len(resistances) not in {4, 6}:
                raise ValueError(
                    "thermal_node_resistances_m2k_w must contain 4 core values; "
                    "the historical 6-value surface-inclusive representation is accepted "
                    "only for compatibility"
                )
            if any(value < 0.0 for value in caps):
                raise ValueError("thermal node capacities must be >= 0")
            if not any(value > 0.0 for value in caps):
                raise ValueError("at least one thermal node capacity must be > 0")
            if any(value <= 0.0 for value in resistances):
                raise ValueError("thermal node resistances must be > 0")
        return self


class TransparentElement(_legacy.TransparentElement):
    """Transparent element with explicit linearised surface-film data."""

    h_ci_w_m2k: float | None = Field(None, ge=0.0)
    h_ri_w_m2k: float | None = Field(None, ge=0.0)
    h_ce_w_m2k: float | None = Field(None, ge=0.0)
    h_re_w_m2k: float | None = Field(None, ge=0.0)
    sky_view_factor: float | None = Field(None, ge=0.0, le=1.0)


class DesignRoom(_legacy.BaseModel):
    """Room-level inputs used by the PN-EN 12831-1 design-load layer."""

    id: str
    name: str
    zone_id: str
    floor_area: float = Field(gt=0.0)
    volume: float = Field(gt=0.0)
    design_temperature_c: float | None = None
    opaque_element_ids: list[str] = Field(default_factory=list)
    transparent_element_ids: list[str] = Field(default_factory=list)
    linear_bridge_ids: list[str] = Field(default_factory=list)
    point_bridge_ids: list[str] = Field(default_factory=list)
    ventilation_airflow_m3h: float | None = Field(None, ge=0.0)
    infiltration_rate_1h: float | None = Field(None, ge=0.0)


class BuildingProject(_legacy.BuildingProject):
    """Project schema extended without breaking historical JSON payloads."""

    opaque_building_elements: list[OpaqueElement]
    transparent_building_elements: list[TransparentElement]
    design_rooms: list[DesignRoom] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_design_rooms(self) -> BuildingProject:
        zone_ids = {zone.id for zone in self.thermal_zones}
        room_ids: set[str] = set()
        room_area_by_zone: dict[str, float] = {}
        room_volume_by_zone: dict[str, float] = {}
        for room in self.design_rooms:
            if room.id in room_ids:
                raise ValueError(f"Duplicate design room id: {room.id}")
            room_ids.add(room.id)
            if room.zone_id not in zone_ids:
                raise ValueError(f"Design room {room.id} references unknown zone {room.zone_id}")
            room_area_by_zone[room.zone_id] = (
                room_area_by_zone.get(room.zone_id, 0.0) + room.floor_area
            )
            room_volume_by_zone[room.zone_id] = (
                room_volume_by_zone.get(room.zone_id, 0.0) + room.volume
            )

        for zone in self.thermal_zones:
            if zone.id not in room_area_by_zone:
                continue
            if not isclose(room_area_by_zone[zone.id], zone.floor_area, rel_tol=0.02, abs_tol=0.1):
                raise ValueError(
                    f"Design-room floor areas for zone {zone.id} must sum to the zone floor area "
                    f"within 2%; got {room_area_by_zone[zone.id]:.3f} vs {zone.floor_area:.3f} m²"
                )
            if not isclose(room_volume_by_zone[zone.id], zone.volume, rel_tol=0.02, abs_tol=0.1):
                raise ValueError(
                    f"Design-room volumes for zone {zone.id} must sum to the zone volume within 2%; "
                    f"got {room_volume_by_zone[zone.id]:.3f} vs {zone.volume:.3f} m³"
                )
        return self
