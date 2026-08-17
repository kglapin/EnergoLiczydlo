"""ISO 13370 / ISO 13789 ground compatibility for the ISO 52016 runtime.

The steady slab U-value correction is retained.  For certificate-grade hourly
ISO 52016 integration, the ground preparation additionally consumes the
virtual-ground resistance and 12 monthly virtual temperatures required by
clause 6.5.8.2 instead of substituting a synthetic sinusoidal boundary.
"""
from __future__ import annotations

import importlib.util
import sys
from math import log, pi
from pathlib import Path

import numpy as np

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
_MONTH_HOURS = np.asarray([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]) * 24


def equivalent_thickness_m(
    soil_conductivity_w_mk: float,
    floor_thermal_resistance_m2k_w: float,
    external_wall_thickness_m: float,
) -> float:
    if soil_conductivity_w_mk <= 0.0 or floor_thermal_resistance_m2k_w <= 0.0:
        raise ValueError("Soil conductivity and floor resistance must be positive")
    if external_wall_thickness_m < 0.0:
        raise ValueError("external_wall_thickness_m must be non-negative")
    return external_wall_thickness_m + soil_conductivity_w_mk * (
        R_SI_FLOOR_DOWN_M2K_W + floor_thermal_resistance_m2k_w + R_SE_GROUND_M2K_W
    )


def slab_on_ground_u_value_w_m2k(
    area_m2: float,
    exposed_perimeter_m: float,
    soil_conductivity_w_mk: float,
    floor_thermal_resistance_m2k_w: float,
    external_wall_thickness_m: float,
) -> float:
    b_prime = characteristic_dimension_m(area_m2, exposed_perimeter_m)
    d_t = equivalent_thickness_m(
        soil_conductivity_w_mk,
        floor_thermal_resistance_m2k_w,
        external_wall_thickness_m,
    )
    conductivity = soil_conductivity_w_mk
    if d_t < b_prime:
        return float(
            2.0 * conductivity / (pi * b_prime + d_t)
            * log(pi * b_prime / d_t + 1.0)
        )
    return float(conductivity / (0.457 * b_prime + d_t))


_legacy.equivalent_thickness_m = equivalent_thickness_m
_legacy.slab_on_ground_u_value_w_m2k = slab_on_ground_u_value_w_m2k
_legacy_prepare_ground_boundaries = _legacy.prepare_ground_boundaries


def _monthly_virtual_profile(values: list[float]) -> np.ndarray:
    if len(values) != 12:
        raise ValueError("virtual ground temperature profile must contain 12 monthly values")
    profile = np.concatenate(
        [np.full(int(hours), float(value), dtype=float) for hours, value in zip(_MONTH_HOURS, values, strict=True)]
    )
    if profile.shape != (8760,):  # pragma: no cover
        raise RuntimeError("monthly virtual-ground expansion did not create 8760 hours")
    return profile


def prepare_ground_boundaries(project, t_e, settings):
    """Prepare ISO 13370 properties and ISO 52016 virtual ground boundaries."""
    checks = list(_legacy_prepare_ground_boundaries(project, t_e, settings))
    if not settings.enabled:
        return checks

    configured = getattr(settings, "elements", {}) or {}
    for element in project.opaque_building_elements:
        adjacent = str(getattr(element.adjacent_space_type, "value", element.adjacent_space_type))
        if adjacent != "ground":
            continue
        config = configured.get(element.id)
        virtual_r = None if config is None else getattr(config, "virtual_ground_resistance_m2k_w", None)
        monthly_t = None if config is None else getattr(config, "virtual_ground_temperature_c_by_month", None)
        if settings.certificate_mode and (virtual_r is None or monthly_t is None):
            raise ValueError(
                f"Ground element '{element.name}' requires virtual_ground_resistance_m2k_w "
                "and virtual_ground_temperature_c_by_month for certificate-grade ISO 52016"
            )
        if virtual_r is not None:
            object.__setattr__(element, "ground_virtual_resistance_m2k_w", float(virtual_r))
        if monthly_t is not None:
            object.__setattr__(element, "_ground_temperature_profile", _monthly_virtual_profile(monthly_t))
            checks.append(
                _legacy._check(
                    "ISO52016_VIRTUAL_GROUND_BOUNDARY",
                    f"'{element.name}': ISO 52016 virtual ground resistance and 12 monthly "
                    "virtual-ground temperatures were applied from the ISO 13370/13789 input set.",
                    passed=True,
                )
            )
        elif not settings.certificate_mode:
            checks.append(
                _legacy._check(
                    "ISO52016_GROUND_DIAGNOSTIC_BOUNDARY",
                    f"'{element.name}': diagnostic periodic soil boundary retained; it is not "
                    "reported as the clause 6.5.8.2 virtual-ground boundary.",
                    passed=False,
                )
            )
    return checks
