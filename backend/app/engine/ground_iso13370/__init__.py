"""Corrected ISO 13370 compatibility layer.

The historical implementation omitted the external surface resistance from
its equivalent floor thickness. This wrapper corrects that term and patches
the legacy preparation routine so every production call uses the corrected
formula.
"""

from __future__ import annotations

import importlib.util
import sys
from math import log, pi
from pathlib import Path

_LEGACY_NAME = "app.engine._legacy_ground_iso13370"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "ground_iso13370.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load legacy ground model from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)

R_SE_GROUND_M2K_W = 0.04


def equivalent_thickness_m(
    soil_conductivity_w_mk: float,
    floor_thermal_resistance_m2k_w: float,
    external_wall_thickness_m: float,
) -> float:
    """Equivalent floor thickness with both inside and outside surface terms."""
    if soil_conductivity_w_mk <= 0.0 or floor_thermal_resistance_m2k_w <= 0.0:
        raise ValueError("Soil conductivity and floor resistance must be positive")
    if external_wall_thickness_m < 0.0:
        raise ValueError("external_wall_thickness_m must be non-negative")
    return external_wall_thickness_m + soil_conductivity_w_mk * (
        R_SI_FLOOR_DOWN_M2K_W
        + floor_thermal_resistance_m2k_w
        + R_SE_GROUND_M2K_W
    )


def slab_on_ground_u_value_w_m2k(
    area_m2: float,
    exposed_perimeter_m: float,
    soil_conductivity_w_mk: float,
    floor_thermal_resistance_m2k_w: float,
    external_wall_thickness_m: float,
) -> float:
    """Return the corrected slab-on-ground thermal transmittance [W/(m² K)]."""
    b_prime = characteristic_dimension_m(area_m2, exposed_perimeter_m)
    d_t = equivalent_thickness_m(
        soil_conductivity_w_mk,
        floor_thermal_resistance_m2k_w,
        external_wall_thickness_m,
    )
    conductivity = soil_conductivity_w_mk
    if d_t < b_prime:
        return float(
            2.0
            * conductivity
            / (pi * b_prime + d_t)
            * log(pi * b_prime / d_t + 1.0)
        )
    return float(conductivity / (0.457 * b_prime + d_t))


# The legacy preparation function resolves these names in its own module
# namespace. Patch them so production preparation uses the corrected formula.
_legacy.equivalent_thickness_m = equivalent_thickness_m
_legacy.slab_on_ground_u_value_w_m2k = slab_on_ground_u_value_w_m2k
prepare_ground_boundaries = _legacy.prepare_ground_boundaries
