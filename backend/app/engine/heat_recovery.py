"""Dynamic heat-recovery controls for the hourly ventilation balance.

The model evaluates sensible heat recovery at every hour, with optional
manufacturer efficiency points, summer bypass and frost-protection strategies.
A preheater is accounted as purchased electricity by the audited calculator.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log

import numpy as np

from app.engine.normative_models import HeatRecoverySettings
from app.schemas.models import ThermalZone, Ventilation, VentilationType

CP_AIR_VOLUMETRIC_J_M3K = 1200.0


@dataclass(frozen=True)
class HeatRecoveryState:
    supply_temperature_c: np.ndarray
    exhaust_outlet_temperature_c: np.ndarray
    effective_efficiency: np.ndarray
    bypass_active: np.ndarray
    frost_risk: np.ndarray
    preheater_power_w: np.ndarray


def attach_heat_recovery_settings(
    ventilation: Ventilation,
    settings: HeatRecoverySettings,
) -> None:
    """Attach parsed advanced settings to a calculation-only project copy."""
    object.__setattr__(ventilation, "_heat_recovery_settings", settings)


def detailed_heat_recovery_settings(
    ventilation: Ventilation,
) -> HeatRecoverySettings | None:
    """Return attached detailed settings when they are enabled and applicable."""
    settings = getattr(ventilation, "_heat_recovery_settings", None)
    if not isinstance(settings, HeatRecoverySettings) or not settings.enabled:
        return None
    if ventilation.ventilation_type != VentilationType.MECHANICAL_WITH_RECOVERY:
        return None
    return settings


def dew_point_temperature_c(temperature_c: float, relative_humidity: float) -> float:
    """Magnus approximation of dew-point temperature [°C]."""
    if not 0.0 < relative_humidity <= 1.0:
        raise ValueError("relative_humidity must be in (0, 1]")
    a = 17.62
    b = 243.12
    gamma = log(relative_humidity) + a * temperature_c / (b + temperature_c)
    return b * gamma / (a - gamma)


def _efficiency_profile(
    settings: HeatRecoverySettings,
    nominal_efficiency: float,
    t_outdoor: np.ndarray,
) -> np.ndarray:
    if not settings.efficiency_curve:
        return np.full_like(t_outdoor, nominal_efficiency, dtype=float)
    points = sorted(settings.efficiency_curve, key=lambda point: point.outdoor_temperature_c)
    x = np.asarray([point.outdoor_temperature_c for point in points], dtype=float)
    y = np.asarray([point.efficiency for point in points], dtype=float)
    return np.asarray(np.interp(t_outdoor, x, y), dtype=float)


def _bypass_mask(
    settings: HeatRecoverySettings,
    zone: ThermalZone,
    t_outdoor: np.ndarray,
) -> np.ndarray:
    if not settings.summer_bypass_enabled:
        return np.zeros_like(t_outdoor, dtype=bool)
    if settings.bypass_min_outdoor_c is None or settings.bypass_max_outdoor_c is None:
        raise ValueError("Summer bypass temperature limits are required")
    indoor_reference = zone.setpoint_cooling
    if indoor_reference is None:
        return np.zeros_like(t_outdoor, dtype=bool)
    return (
        (t_outdoor >= settings.bypass_min_outdoor_c)
        & (t_outdoor <= settings.bypass_max_outdoor_c)
        & (t_outdoor <= indoor_reference - settings.bypass_indoor_margin_k)
    )


def _frost_risk_mask(
    settings: HeatRecoverySettings,
    t_extract: np.ndarray,
    t_exhaust_out: np.ndarray,
) -> np.ndarray:
    below_freezing_limit = t_exhaust_out < min(0.0, settings.frost_exhaust_limit_c)
    if settings.indoor_relative_humidity is None:
        return below_freezing_limit
    dew_point = np.asarray(
        [
            dew_point_temperature_c(float(temp), settings.indoor_relative_humidity)
            for temp in t_extract
        ],
        dtype=float,
    )
    return below_freezing_limit & (t_exhaust_out < dew_point)


def heat_recovery_state(
    ventilation: Ventilation,
    zone: ThermalZone,
    t_outdoor_c: np.ndarray,
    mechanical_flow_m3h: float | np.ndarray,
    operation_profile: np.ndarray | None = None,
    *,
    capacity_fraction: float = 1.0,
) -> HeatRecoveryState:
    """Evaluate sensible recovery, bypass and frost protection hour by hour.

    ``capacity_fraction`` allocates central-unit preheater power to the current
    zone. The annual sum therefore never multiplies one physical preheater by
    the number of thermal zones.
    """
    if not 0.0 <= capacity_fraction <= 1.0:
        raise ValueError("capacity_fraction must be between 0 and 1")
    outdoor = np.asarray(t_outdoor_c, dtype=float)
    if outdoor.ndim != 1:
        raise ValueError("t_outdoor_c must be one-dimensional")
    n = len(outdoor)
    flow = np.asarray(mechanical_flow_m3h, dtype=float)
    if flow.ndim == 0:
        flow = np.full(n, float(flow), dtype=float)
    if flow.shape != outdoor.shape:
        raise ValueError("mechanical airflow must match outdoor temperature shape")
    if operation_profile is None:
        operation = np.ones(n, dtype=float)
    else:
        operation = np.asarray(operation_profile, dtype=float)
        if operation.shape != outdoor.shape:
            raise ValueError("operation profile must match outdoor temperature shape")
    flow = np.maximum(flow, 0.0) * np.clip(operation, 0.0, 1.0)

    settings = detailed_heat_recovery_settings(ventilation)
    if settings is None:
        eta = np.full(n, ventilation.heat_recovery_efficiency, dtype=float)
        t_extract = np.full(n, zone.setpoint_heating, dtype=float)
        supply = outdoor + eta * (t_extract - outdoor)
        exhaust = t_extract - eta * (t_extract - outdoor)
        return HeatRecoveryState(
            supply,
            exhaust,
            eta,
            np.zeros(n, dtype=bool),
            np.zeros(n, dtype=bool),
            np.zeros(n, dtype=float),
        )

    eta = np.clip(
        _efficiency_profile(settings, ventilation.heat_recovery_efficiency, outdoor),
        0.0,
        1.0,
    )
    t_extract = np.full(n, zone.setpoint_heating, dtype=float)
    bypass = _bypass_mask(settings, zone, outdoor) & (flow > 0.0)
    eta = np.where(bypass, 0.0, eta)

    preheated = outdoor.copy()
    preheater_power = np.zeros(n, dtype=float)
    exhaust = t_extract - eta * (t_extract - preheated)
    frost_risk = _frost_risk_mask(settings, t_extract, exhaust) & (flow > 0.0) & ~bypass

    if settings.frost_strategy == "disable_recovery":
        eta = np.where(frost_risk, 0.0, eta)
    elif settings.frost_strategy == "reduce_recovery":
        denominator = np.maximum(t_extract - outdoor, 1e-9)
        safe_eta = np.clip(
            (t_extract - settings.frost_exhaust_limit_c) / denominator,
            0.0,
            1.0,
        )
        eta = np.where(frost_risk, np.minimum(eta, safe_eta), eta)
    elif settings.frost_strategy == "preheater":
        max_input_power = float(settings.preheater_max_power_w or 0.0) * capacity_fraction
        active = frost_risk & (eta > 1e-9) & (flow > 1e-9)
        target_preheat = np.where(
            active,
            t_extract - (t_extract - settings.frost_exhaust_limit_c) / np.maximum(eta, 1e-9),
            outdoor,
        )
        required_delta = np.maximum(target_preheat - outdoor, 0.0)
        thermal_required = flow / 3600.0 * CP_AIR_VOLUMETRIC_J_M3K * required_delta
        input_required = thermal_required / settings.preheater_efficiency
        preheater_power = np.where(active, np.minimum(input_required, max_input_power), 0.0)
        delivered_thermal = preheater_power * settings.preheater_efficiency
        rise = np.divide(
            delivered_thermal,
            flow / 3600.0 * CP_AIR_VOLUMETRIC_J_M3K,
            out=np.zeros_like(delivered_thermal),
            where=flow > 1e-9,
        )
        preheated = outdoor + rise
        denominator = np.maximum(t_extract - preheated, 1e-9)
        safe_eta = np.clip(
            (t_extract - settings.frost_exhaust_limit_c) / denominator,
            0.0,
            1.0,
        )
        eta = np.where(active, np.minimum(eta, safe_eta), eta)

    eta = np.where(flow > 0.0, eta, 0.0)
    supply = preheated + eta * (t_extract - preheated)
    exhaust = t_extract - eta * (t_extract - preheated)
    supply = np.where(bypass, outdoor, supply)
    exhaust = np.where(bypass, t_extract, exhaust)

    return HeatRecoveryState(
        supply_temperature_c=np.asarray(supply, dtype=float),
        exhaust_outlet_temperature_c=np.asarray(exhaust, dtype=float),
        effective_efficiency=np.asarray(eta, dtype=float),
        bypass_active=np.asarray(bypass, dtype=bool),
        frost_risk=np.asarray(frost_risk, dtype=bool),
        preheater_power_w=np.asarray(preheater_power, dtype=float),
    )
