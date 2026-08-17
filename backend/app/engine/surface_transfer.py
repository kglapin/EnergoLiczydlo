"""Dynamic surface heat-transfer correlations for hourly envelope analysis."""

from __future__ import annotations

from typing import Literal, TypeAlias, cast

import numpy as np
from numpy.typing import NDArray

FloatArray: TypeAlias = NDArray[np.float64]
SurfaceKind = Literal["wall", "floor", "ceiling"]
ROUGHNESS_MULTIPLIER = {
    "very_rough": 2.17,
    "rough": 1.67,
    "medium": 1.52,
    "medium_smooth": 1.13,
    "smooth": 1.11,
    "very_smooth": 1.00,
}


def _array(value: float | FloatArray) -> FloatArray:
    return cast(FloatArray, np.asarray(value, dtype=np.float64))


def _reg_nonzero_power(value: float | FloatArray, exponent: float, delta: float) -> FloatArray:
    """LBNL/Modelica regularized ``abs(x)**n`` near zero."""
    if not 0.0 < exponent < 2.0 or delta <= 0.0:
        raise ValueError("invalid power regularization parameters")
    x = _array(value)
    absolute = np.abs(x)
    regular = np.power(absolute, exponent)
    delta2 = delta * delta
    y_d = delta**exponent
    yp_d = exponent * delta ** (exponent - 1.0)
    ypp_d = exponent * (exponent - 1.0) * delta ** (exponent - 2.0)
    a1 = -(yp_d / delta - ypp_d) / delta2 / 8.0
    a3 = (ypp_d - 12.0 * a1 * delta2) / 2.0
    a5 = y_d - delta2 * (a3 + delta2 * a1)
    x2 = x * x
    polynomial = a5 + x2 * (a3 + x2 * a1)
    return _array(np.where(absolute > delta, regular, polynomial))


def _reg_step(
    x: float | FloatArray,
    positive_value: float,
    negative_value: float,
    transition: float,
) -> FloatArray:
    """LBNL differentiable step interpolation."""
    value = _array(x)
    if transition <= 0.0:
        return _array(np.where(value > 0.0, positive_value, negative_value))
    ratio = value / transition
    middle = ratio * (ratio**2 - 3.0) * (negative_value - positive_value) / 4.0
    middle += (positive_value + negative_value) / 2.0
    return _array(
        np.where(
            value > transition,
            positive_value,
            np.where(value < -transition, negative_value, middle),
        )
    )


def natural_convection_coefficient(
    delta_t_k: float | FloatArray,
    surface_kind: SurfaceKind,
) -> FloatArray:
    delta = _array(delta_t_k)
    magnitude = np.power(np.abs(delta), 0.3333)
    if surface_kind == "wall":
        factor = np.full_like(delta, 1.3)
    elif surface_kind == "floor":
        factor = np.where(delta > 0.0, 1.51, 0.76)
    elif surface_kind == "ceiling":
        factor = np.where(delta > 0.0, 0.76, 1.51)
    else:
        raise ValueError(f"Unsupported surface kind: {surface_kind}")
    return _array(factor * magnitude)


def wind_direction_modifier(
    surface_azimuth_deg: float,
    wind_direction_deg: float | FloatArray,
) -> FloatArray:
    direction = _array(wind_direction_deg)
    difference = np.abs((direction - float(surface_azimuth_deg) + 180.0) % 360.0 - 180.0)
    x = np.cos(np.deg2rad(difference)) - np.cos(np.deg2rad(100.0))
    return _reg_step(x, 1.0, 0.5, 0.025)


def forced_convection_coefficient(
    *,
    area_m2: float,
    wind_speed_m_s: float | FloatArray,
    wind_direction_deg: float | FloatArray,
    surface_azimuth_deg: float,
    roughness: str = "rough",
) -> FloatArray:
    if area_m2 <= 0.0:
        raise ValueError("area_m2 must be positive")
    if roughness not in ROUGHNESS_MULTIPLIER:
        raise ValueError(f"Unknown surface roughness: {roughness}")
    speed = np.maximum(_array(wind_speed_m_s), 0.0)
    return _array(
        2.537
        * wind_direction_modifier(surface_azimuth_deg, wind_direction_deg)
        * ROUGHNESS_MULTIPLIER[roughness]
        * 2.0
        / area_m2**0.25
        * _reg_nonzero_power(speed, 0.5, 0.5)
    )


def exterior_convection_coefficient(
    *,
    delta_t_k: float | FloatArray,
    surface_kind: SurfaceKind,
    area_m2: float,
    wind_speed_m_s: float | FloatArray,
    wind_direction_deg: float | FloatArray,
    surface_azimuth_deg: float,
    roughness: str = "rough",
    wind_exposed: bool = True,
) -> FloatArray:
    natural = natural_convection_coefficient(delta_t_k, surface_kind)
    if not wind_exposed:
        return natural
    return _array(
        natural
        + forced_convection_coefficient(
            area_m2=area_m2,
            wind_speed_m_s=wind_speed_m_s,
            wind_direction_deg=wind_direction_deg,
            surface_azimuth_deg=surface_azimuth_deg,
            roughness=roughness,
        )
    )


def linearized_longwave_coefficient(
    surface_temperature_c: float | FloatArray,
    radiant_temperature_c: float | FloatArray,
    emissivity: float = 0.9,
) -> FloatArray:
    if not 0.0 <= emissivity <= 1.0:
        raise ValueError("emissivity must be between 0 and 1")
    sigma = 5.670374419e-8
    t_surface = _array(surface_temperature_c) + 273.15
    t_radiant = _array(radiant_temperature_c) + 273.15
    if np.any(t_surface <= 0.0) or np.any(t_radiant <= 0.0):
        raise ValueError("absolute temperatures must be positive")
    return _array(
        emissivity * sigma * (t_surface + t_radiant) * (t_surface**2 + t_radiant**2)
    )


def surface_kind_from_inclination(inclination_deg: float) -> SurfaceKind:
    if inclination_deg < 60.0:
        return "ceiling"
    if inclination_deg > 120.0:
        return "floor"
    return "wall"
