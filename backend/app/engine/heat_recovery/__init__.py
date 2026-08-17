"""Dynamic heat-recovery compatibility layer with zone-temperature coupling."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_LEGACY_NAME = "app.engine._legacy_heat_recovery"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "heat_recovery.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load legacy heat recovery from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)


def _extract_temperature_profile(
    zone,
    outdoor: np.ndarray,
    extract_temperature_c: float | np.ndarray | None,
) -> np.ndarray:
    if extract_temperature_c is not None:
        extract = np.asarray(extract_temperature_c, dtype=float)
        if extract.ndim == 0:
            extract = np.full(outdoor.shape, float(extract), dtype=float)
        if extract.shape != outdoor.shape:
            raise ValueError("extract_temperature_c must match outdoor temperature shape")
        if not np.isfinite(extract).all():
            raise ValueError("extract_temperature_c must contain finite values")
        return extract

    # Backwards-compatible first estimate before the zone/recovery iteration:
    # heating setpoint in cold hours and cooling setpoint in hot hours. The
    # calculator subsequently feeds the solved zone temperature back here.
    heating = float(zone.setpoint_heating)
    cooling = zone.setpoint_cooling
    if cooling is None:
        return np.full(outdoor.shape, heating, dtype=float)
    return np.where(outdoor > float(cooling), float(cooling), heating).astype(float)


def heat_recovery_state(
    ventilation,
    zone,
    t_outdoor_c: np.ndarray,
    mechanical_flow_m3h: float | np.ndarray,
    operation_profile: np.ndarray | None = None,
    *,
    capacity_fraction: float = 1.0,
    extract_temperature_c: float | np.ndarray | None = None,
):
    """Evaluate sensible recovery using the actual/externalized extract temperature.

    ``extract_temperature_c`` should be the solved zone-air temperature. When
    omitted, a setpoint-based initial estimate is used so direct calls remain
    deterministic and summer cooling never reuses the heating setpoint.
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
    t_extract = _extract_temperature_profile(zone, outdoor, extract_temperature_c)

    settings = detailed_heat_recovery_settings(ventilation)
    if settings is None:
        eta = np.full(n, ventilation.heat_recovery_efficiency, dtype=float)
        eta = np.where(flow > 0.0, eta, 0.0)
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
            t_extract
            - (t_extract - settings.frost_exhaust_limit_c) / np.maximum(eta, 1e-9),
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


_legacy.heat_recovery_state = heat_recovery_state
