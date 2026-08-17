"""Ventilation compatibility layer with extract-temperature aware recovery."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

from app.engine.heat_recovery import detailed_heat_recovery_settings, heat_recovery_state

_LEGACY_NAME = "app.engine._legacy_ventilation"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "ventilation.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load legacy ventilation from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)


def ventilation_effective_supply_temperature(
    ventilation,
    zone,
    t_e: np.ndarray,
    building_floor_area: float | None = None,
    operation_profile: np.ndarray | None = None,
    *,
    extract_temperature_c: float | np.ndarray | None = None,
) -> np.ndarray:
    """Return equivalent supply temperature using the supplied extract profile."""
    outdoor = np.asarray(t_e, dtype=float)
    if outdoor.ndim != 1:
        raise ValueError("t_e must be a one-dimensional hourly array")

    detailed = detailed_heat_recovery_settings(ventilation)
    if detailed is None and ventilation.supply_temperature is None:
        return outdoor.copy()
    if detailed is not None and ventilation.supply_temperature is not None:
        raise ValueError(
            "Detailed heat-recovery control and explicit supply_temperature are "
            "alternative models and cannot be used simultaneously"
        )

    mechanical_flow, external_flow = ventilation_airflow_components(
        ventilation,
        zone,
        building_floor_area,
        operation_profile,
    )
    mechanical = _as_hourly_flow(mechanical_flow, len(outdoor))
    external = _as_hourly_flow(external_flow, len(outdoor))

    if detailed is not None:
        total_area = building_floor_area if building_floor_area else zone.floor_area
        capacity_fraction = zone.floor_area / total_area if total_area > 0.0 else 0.0
        recovery = heat_recovery_state(
            ventilation,
            zone,
            outdoor,
            mechanical,
            operation_profile=None,
            capacity_fraction=capacity_fraction,
            extract_temperature_c=extract_temperature_c,
        )
        mechanical_supply = recovery.supply_temperature_c
    else:
        if ventilation.supply_temperature is None:
            raise RuntimeError("Explicit supply temperature disappeared during evaluation")
        mechanical_supply = np.full(
            len(outdoor),
            float(ventilation.supply_temperature),
            dtype=float,
        )

    total = mechanical + external
    result = outdoor.copy()
    np.divide(
        mechanical * mechanical_supply + external * outdoor,
        total,
        out=result,
        where=total > 0.0,
    )
    return result


_legacy.ventilation_effective_supply_temperature = ventilation_effective_supply_temperature
