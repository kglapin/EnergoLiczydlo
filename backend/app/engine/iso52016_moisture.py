"""PN-EN ISO 52016-1 clause 6.5.14 hourly moisture balance.

The zone moisture state is humidity ratio x [kg water/kg dry air].  Ventilation
and infiltration use their physical incoming-air flow, internal moisture sources
are explicit, and humidification/dehumidification is solved as the load needed
to maintain the requested humidity-ratio band.  Moisture buffering by materials
is an optional signed source supplied by the applicable input method.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias, cast

import numpy as np
from numpy.typing import NDArray

FloatArray: TypeAlias = NDArray[np.float64]
RHO_DRY_AIR_KG_M3 = 1.2
SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True)
class MoistureSolution:
    humidity_ratio: FloatArray
    relative_humidity: FloatArray
    humidification_kg_s: FloatArray
    dehumidification_kg_s: FloatArray
    latent_heating_w: FloatArray
    latent_cooling_w: FloatArray


def _arr(value) -> FloatArray:
    return cast(FloatArray, np.asarray(value, dtype=np.float64))


def saturation_vapour_pressure_pa(temperature_c: float | FloatArray) -> FloatArray:
    """Saturation vapour pressure over water/ice [Pa]."""
    t = _arr(temperature_c)
    result = np.where(
        t >= 0.0,
        610.5 * np.exp(17.2694 * t / (t + 237.29)),
        610.5 * np.exp(21.8746 * t / (t + 265.5)),
    )
    return _arr(result)


def humidity_ratio_from_rh(
    temperature_c: float | FloatArray,
    relative_humidity: float | FloatArray,
    pressure_pa: float | FloatArray = 101325.0,
) -> FloatArray:
    """Return humidity ratio [kg/kg dry air] from RH expressed as 0..1."""
    t = _arr(temperature_c)
    rh = _arr(relative_humidity)
    p = _arr(pressure_pa)
    if np.any((rh < 0.0) | (rh > 1.0)):
        raise ValueError("relative_humidity must be between 0 and 1")
    vapour = rh * saturation_vapour_pressure_pa(t)
    denominator = p - vapour
    if np.any(denominator <= 0.0):
        raise ValueError("Atmospheric pressure must exceed vapour pressure")
    return _arr(0.622 * vapour / denominator)


def rh_from_humidity_ratio(
    temperature_c: float | FloatArray,
    humidity_ratio: float | FloatArray,
    pressure_pa: float | FloatArray = 101325.0,
) -> FloatArray:
    t = _arr(temperature_c)
    x = _arr(humidity_ratio)
    p = _arr(pressure_pa)
    vapour = p * x / (0.622 + x)
    saturation = saturation_vapour_pressure_pa(t)
    return _arr(np.clip(vapour / np.maximum(saturation, 1e-9), 0.0, 1.0))


def solve_zone_moisture(
    *,
    zone_volume_m3: float,
    indoor_temperature_c: FloatArray,
    incoming_airflow_m3h: float | FloatArray,
    supply_humidity_ratio: FloatArray,
    atmospheric_pressure_pa: FloatArray,
    relative_humidity_min: float | FloatArray | None,
    relative_humidity_max: float | FloatArray | None,
    moisture_generation_kg_s: float | FloatArray = 0.0,
    moisture_buffer_kg_s: float | FloatArray = 0.0,
    latent_heat_vaporization_j_kg: float = 2_500_000.0,
    initial_humidity_ratio: float | None = None,
) -> MoistureSolution:
    """Solve the implicit one-hour zone moisture balance.

    Positive humidification/dehumidification arrays are reported separately.
    A positive ``moisture_buffer_kg_s`` means absorption by materials (a sink);
    a negative value means desorption into the air.
    """
    if zone_volume_m3 <= 0.0:
        raise ValueError("zone_volume_m3 must be positive")
    t = _arr(indoor_temperature_c)
    n = len(t)
    flow = np.broadcast_to(_arr(incoming_airflow_m3h), (n,)).astype(float)
    x_supply = np.broadcast_to(_arr(supply_humidity_ratio), (n,)).astype(float)
    pressure = np.broadcast_to(_arr(atmospheric_pressure_pa), (n,)).astype(float)
    generation = np.broadcast_to(_arr(moisture_generation_kg_s), (n,)).astype(float)
    buffer_sink = np.broadcast_to(_arr(moisture_buffer_kg_s), (n,)).astype(float)
    if np.any(flow < 0.0) or np.any(generation < 0.0):
        raise ValueError("airflow and moisture generation must be non-negative")

    def _setpoint(value, name: str) -> FloatArray | None:
        if value is None:
            return None
        arr = np.broadcast_to(_arr(value), (n,)).astype(float)
        if np.any((arr < 0.0) | (arr > 1.0)):
            raise ValueError(f"{name} must be between 0 and 1")
        return arr

    rh_min = _setpoint(relative_humidity_min, "relative_humidity_min")
    rh_max = _setpoint(relative_humidity_max, "relative_humidity_max")
    if rh_min is not None and rh_max is not None and np.any(rh_min > rh_max):
        raise ValueError("minimum relative humidity cannot exceed maximum")

    x_min = None if rh_min is None else humidity_ratio_from_rh(t, rh_min, pressure)
    x_max = None if rh_max is None else humidity_ratio_from_rh(t, rh_max, pressure)
    storage_kg_dry_air_s = RHO_DRY_AIR_KG_M3 * zone_volume_m3 / SECONDS_PER_HOUR
    mdot_air = RHO_DRY_AIR_KG_M3 * flow / 3600.0

    x = _arr(np.empty(n))
    humid = _arr(np.zeros(n))
    dehumid = _arr(np.zeros(n))
    if initial_humidity_ratio is None:
        if x_min is not None and x_max is not None:
            previous = float(0.5 * (x_min[0] + x_max[0]))
        elif x_min is not None:
            previous = float(x_min[0])
        elif x_max is not None:
            previous = float(x_max[0])
        else:
            previous = float(x_supply[0])
    else:
        previous = float(initial_humidity_ratio)

    for hour in range(n):
        source = generation[hour] - buffer_sink[hour]
        denominator = storage_kg_dry_air_s + mdot_air[hour]
        numerator = (
            storage_kg_dry_air_s * previous
            + mdot_air[hour] * x_supply[hour]
            + source
        )
        free = numerator / max(denominator, 1e-12)
        target = free
        if x_min is not None and free < x_min[hour]:
            target = float(x_min[hour])
            humid[hour] = max(denominator * target - numerator, 0.0)
        elif x_max is not None and free > x_max[hour]:
            target = float(x_max[hour])
            dehumid[hour] = max(numerator - denominator * target, 0.0)
        x[hour] = max(target, 0.0)
        previous = x[hour]

    rh = rh_from_humidity_ratio(t, x, pressure)
    latent_h = _arr(humid * latent_heat_vaporization_j_kg)
    latent_c = _arr(dehumid * latent_heat_vaporization_j_kg)
    return MoistureSolution(x, rh, humid, dehumid, latent_h, latent_c)
