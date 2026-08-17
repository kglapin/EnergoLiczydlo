"""Extended schema used by the audited calculation runtime.

The repository historically stored the schema in ``app/schemas/models.py``.
Python prefers a package over a same-named module, so this package loads the
legacy schema and adds the fields that are required by the detailed hourly
construction model and room-level design-load calculation without breaking
older project JSON files.
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
if _spec is None or _spec.loader is None:  # pragma: no cover - import guard
    raise ImportError(f"Cannot load legacy schema from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)

MassDistributionClass = Literal[
    "internal",
    "external",
    "middle",
    "distributed",
    "internal_external",
]


class OpaqueElement(_legacy.OpaqueElement):
    """Opaque element with optional explicit hourly thermal-node properties.

    ``areal_heat_capacity`` is expressed in kJ/(m² K). It and
    ``mass_distribution_class`` provide a backwards-compatible reduced input.
    For a traceable detailed calculation the five nodal capacities and six
    nodal resistances can be supplied explicitly. Resistances are per unit area
    in m²K/W and include the inside and outside surface paths, therefore their
    sum should be consistent with ``1 / U``.
    """

    areal_heat_capacity: float | None = Field(None, gt=0.0)
    mass_distribution_class: MassDistributionClass | None = None
    thermal_node_capacities_kj_m2k: list[float] | None = None
    thermal_node_resistances_m2k_w: list[float] | None = None

    @model_validator(mode="after")
    def validate_hourly_construction_data(self) -> OpaqueElement:
        capacities = self.thermal_node_capacities_kj_m2k
        resistances = self.thermal_node_resistances_m2k_w
        if (capacities is None) != (resistances is None):
            raise ValueError(
                "thermal_node_capacities_kj_m2k and "
                "thermal_node_resistances_m2k_w must be supplied together"
            )
        if capacities is not None:
            if len(capacities) != 5:
                raise ValueError(
                    "thermal_node_capacities_kj_m2k must contain exactly 5 values"
                )
            if any(value < 0.0 for value in capacities) or sum(capacities) <= 0.0:
                raise ValueError("thermal node capacities must be non-negative and non-zero")
        if resistances is not None:
            if len(resistances) != 6:
                raise ValueError(
                    "thermal_node_resistances_m2k_w must contain exactly 6 values"
                )
            if any(value <= 0.0 for value in resistances):
                raise ValueError("thermal node resistances must be strictly positive")
            expected = 1.0 / float(self.u_value)
            actual = float(sum(resistances))
            if not isclose(actual, expected, rel_tol=0.05, abs_tol=0.01):
                raise ValueError(
                    "Sum of thermal_node_resistances_m2k_w must reproduce 1/U "
                    f"within 5%; got sum(R)={actual:.4f}, 1/U={expected:.4f}"
                )
        if self.areal_heat_capacity is not None and self.mass_distribution_class is None:
            raise ValueError(
                "mass_distribution_class is required when areal_heat_capacity is supplied"
            )
        return self


class DesignRoom(_legacy.BaseModel):
    """One room used by the PN-EN 12831-1 design-load layer."""

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
    """Project schema extended with detailed constructions and design rooms."""

    opaque_building_elements: list[OpaqueElement]
    design_rooms: list[DesignRoom] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_design_rooms(self) -> BuildingProject:
        if not self.design_rooms:
            return self

        zone_by_id = {zone.id: zone for zone in self.thermal_zones}
        room_ids = [room.id for room in self.design_rooms]
        if len(room_ids) != len(set(room_ids)):
            raise ValueError("Design room IDs must be unique")
        unknown_zones = sorted({room.zone_id for room in self.design_rooms} - set(zone_by_id))
        if unknown_zones:
            raise ValueError(
                "Unknown thermal zone referenced by design room: " + ", ".join(unknown_zones)
            )

        opaque_ids = {element.id for element in self.opaque_building_elements}
        transparent_ids = {element.id for element in self.transparent_building_elements}
        linear_ids = {bridge.id for bridge in self.thermal_bridges.linear_bridges}
        point_ids = {bridge.id for bridge in self.thermal_bridges.point_bridges}
        used: dict[str, str] = {}
        for room in self.design_rooms:
            for field_name, values, known in (
                ("opaque_element_ids", room.opaque_element_ids, opaque_ids),
                ("transparent_element_ids", room.transparent_element_ids, transparent_ids),
                ("linear_bridge_ids", room.linear_bridge_ids, linear_ids),
                ("point_bridge_ids", room.point_bridge_ids, point_ids),
            ):
                missing = sorted(set(values) - known)
                if missing:
                    raise ValueError(
                        f"Design room '{room.id}' has unknown {field_name}: "
                        + ", ".join(missing)
                    )
                for value in values:
                    key = f"{field_name}:{value}"
                    previous = used.get(key)
                    if previous is not None and previous != room.id:
                        raise ValueError(
                            f"Envelope item '{value}' is assigned to more than one design room"
                        )
                    used[key] = room.id

        for zone_id, zone in zone_by_id.items():
            rooms = [room for room in self.design_rooms if room.zone_id == zone_id]
            if not rooms:
                continue
            area = sum(room.floor_area for room in rooms)
            volume = sum(room.volume for room in rooms)
            if not isclose(area, zone.floor_area, rel_tol=1e-6, abs_tol=0.01):
                raise ValueError(
                    f"Design-room floor areas in zone '{zone_id}' must sum to zone floor area; "
                    f"got rooms={area:g}, zone={zone.floor_area:g}"
                )
            if not isclose(volume, zone.volume, rel_tol=1e-6, abs_tol=0.01):
                raise ValueError(
                    f"Design-room volumes in zone '{zone_id}' must sum to zone volume; "
                    f"got rooms={volume:g}, zone={zone.volume:g}"
                )
        return self


BuildingProject.model_rebuild()
