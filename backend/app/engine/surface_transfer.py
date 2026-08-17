"""Dynamic surface heat-transfer correlations for hourly envelope analysis.

The functions in this module implement the same basic free- and forced-
convection correlations used by the LBNL Buildings library BESTEST models.
They are deliberately independent from the certificate engine: surface-film
physics belongs to the detailed hourly analysis and must not silently alter the
formal monthly method.
"""

from __future__ import annotations

from typing import Literal, TypeAlias, cast

import numpy as np
from numpy.typing import NDArray

FloatArray: TypeAlias = NDArray[np.float64]
SurfaceKind = Literal["wall", "floor", "ceiling"]

ROUGHNESS_MULTIPLIER: dict[str, float] = {
    "very_rough": 2.17,
    "rough": 1.67,
    "medium": 1.52,
    "medium_smooth": 1.13,
    "smooth": 1.11,
    "very_smooth": 1.00,
}


def _array(value: float | FloatArray) -> FloatArray:
    return cast(FloatArray, np.asarray(value, dtype=np.float64))


def natural_convection_coefficient(
    delta_t_k: float | FloatArray,
    surface_kind: SurfaceKind,
) -> FloatArray:
    """Return free-convection coefficient in W/(m² K).

    ``delta_t_k`` is surface temperature minus adjacent air temperature.
    Coefficients follow the Walton/BLAST correlations used by the LBNL
    Buildings library:

    - wall: ``1.3 |ΔT|^(1/3)``;
    - floor: 1.51 when the surface is warmer, 0.76 when it is colder;
    - ceiling: the floor coefficients are reversed.
    """
    delta = _array(delta_t_k)
    magnitude = np.power(np.abs(delta), 0.3333)
    if surface_kind == "wall":
        factor = np.full_like(delta, 1.3)
    elif surface_kind == "floor":
        factor = np.where(delta > 0.0, 1.51, 0.76)
    elif surface_kind == "ceiling":
        factor = np.where(delta > 0.0, 0.76, 1.51)
    else:  # pragma: no cover - Literal protects normal callers
        raise ValueError(f"Unsupported surface kind: {surface_kind}")
    return cast(FloatArray, factor * magnitude)


def wind_direction_modifier(
    surface_azimuth_deg: float,
    wind_direction_deg: float | FloatArray,
) -> FloatArray:
    """Return 1.0 windward or 0.5 leeward using the 100° transition.

    EPW wind direction is the direction *from* which the wind arrives, with
    0° = North. Project surface azimuth uses 0° = North as well. A surface is
    treated as windward when the angular difference is at most 100°.
    """
    direction = _array(wind_direction_deg)
    difference = np.abs((direction - float(surface_azimuth_deg) + 180.0) % 360.0 - 180.0)
    return cast(FloatArray, np.where(difference <= 100.0, 1.0, 0.5))


def forced_convection_coefficient(
    *,
    area_m2: float,
    wind_speed_m_s: float | FloatArray,
    wind_direction_deg: float | FloatArray,
    surface_azimuth_deg: float,
    roughness: str = "rough",
) -> FloatArray:
    """Return Sparrow/Ramsey/Mass wind-driven exterior convection coefficient.

    The LBNL implementation assumes a square surface, reducing the published
    perimeter-based relationship to ``2.537 * W * R * 2 / A^0.25 * sqrt(v)``.
    Wind speeds are clipped at zero; the exact LBNL low-speed regularisation is
    intentionally not needed for hourly EPW data because the limiting value is
    zero and the product remains continuous.
    """
    if area_m2 <= 0.0:
        raise ValueError("area_m2 must be positive")
    if roughness not in ROUGHNESS_MULTIPLIER:
        raise ValueError(f"Unknown surface roughness: {roughness}")
    speed = np.maximum(_array(wind_speed_m_s), 0.0)
    modifier = wind_direction_modifier(surface_azimuth_deg, wind_direction_deg)
    coefficient = (
        2.537
        * modifier
        * ROUGHNESS_MULTIPLIER[roughness]
        * 2.0
        / area_m2**0.25
        * np.sqrt(speed)
    )
    return cast(FloatArray, coefficient)


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
    """Return total exterior convection coefficient in W/(m² K)."""
    natural = natural_convection_coefficient(delta_t_k, surface_kind)
    if not wind_exposed:
        return natural
    forced = forced_convection_coefficient(
        area_m2=area_m2,
        wind_speed_m_s=wind_speed_m_s,
        wind_direction_deg=wind_direction_deg,
        surface_azimuth_deg=surface_azimuth_deg,
        roughness=roughness,
    )
    return cast(FloatArray, natural + forced)


def linearized_longwave_coefficient(
    surface_temperature_c: float | FloatArray,
    radiant_temperature_c: float | FloatArray,
    emissivity: float = 0.9,
) -> FloatArray:
    """Linearise long-wave exchange between two temperatures.

    ``h_r = ε σ (T_s + T_r) (T_s² + T_r²)`` with temperatures in kelvin.
    """
    if not 0.0 <= emissivity <= 1.0:
        raise ValueError("emissivity must be between 0 and 1")
    sigma = 5.670374419e-8
    t_surface = _array(surface_temperature_c) + 273.15
    t_radiant = _array(radiant_temperature_c) + 273.15
    if np.any(t_surface <= 0.0) or np.any(t_radiant <= 0.0):
        raise ValueError("absolute temperatures must be positive")
    return cast(
        FloatArray,
        emissivity * sigma * (t_surface + t_radiant) * (t_surface**2 + t_radiant**2),
    )


def surface_kind_from_inclination(inclination_deg: float) -> SurfaceKind:
    """Map project inclination (0° up, 90° wall, 180° down) to a surface kind."""
    if inclination_deg < 60.0:
        return "ceiling"
    if inclination_deg > 120.0:
        return "floor"
    return "wall"
