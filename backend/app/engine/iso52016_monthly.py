"""PN-EN ISO 52016-1 clause 6.6 monthly utilization-factor method.

This module is deliberately independent from the Polish legal certificate
engine. Heating and cooling are evaluated as two separate monthly calculations,
with their own transfer/gain inputs and time constants, as required by 6.6.3.
Reference parameters a0 and tau0 are Annex-A/national choices and are therefore
explicit inputs rather than guessed constants in strict mode.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MonthlyZoneEnergy:
    heating_kwh: np.ndarray
    cooling_kwh: np.ndarray
    heating_gain_utilization: np.ndarray
    cooling_loss_utilization: np.ndarray
    heating_time_constant_h: np.ndarray
    cooling_time_constant_h: np.ndarray


def zone_time_constant_h(
    effective_internal_capacity_j_k: float,
    transmission_h_w_k: np.ndarray | float,
    ventilation_h_w_k: np.ndarray | float,
) -> np.ndarray:
    """Clause 6.6.10.4 zone time constant [h]."""
    if effective_internal_capacity_j_k <= 0.0:
        raise ValueError("effective_internal_capacity_j_k must be positive")
    h_total = np.asarray(transmission_h_w_k, dtype=float) + np.asarray(
        ventilation_h_w_k, dtype=float
    )
    if np.any(h_total <= 0.0):
        raise ValueError("monthly heat-transfer coefficient must be positive")
    return np.asarray(effective_internal_capacity_j_k / (3600.0 * h_total), dtype=float)


def numerical_parameter(a0: float, tau_h: np.ndarray, tau0_h: float) -> np.ndarray:
    if a0 <= 0.0 or tau0_h <= 0.0:
        raise ValueError("a0 and tau0_h must be positive")
    return np.asarray(a0 + np.asarray(tau_h, dtype=float) / tau0_h, dtype=float)


def heating_gain_utilization(gamma: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Heating gain-utilization factor from clause 6.6.10.2."""
    g, aa = np.broadcast_arrays(np.asarray(gamma, dtype=float), np.asarray(a, dtype=float))
    result = np.ones(g.shape, dtype=float)
    regular = (g > 0.0) & np.isfinite(g) & ~np.isclose(g, 1.0)
    result[regular] = (1.0 - np.power(g[regular], aa[regular])) / (
        1.0 - np.power(g[regular], aa[regular] + 1.0)
    )
    equal = np.isclose(g, 1.0)
    result[equal] = aa[equal] / (aa[equal] + 1.0)
    result[np.isposinf(g)] = 0.0
    result[g <= 0.0] = 1.0
    return np.asarray(np.clip(result, 0.0, 1.0), dtype=float)


def cooling_loss_utilization(gamma: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Cooling loss-utilization factor from clause 6.6.10.3."""
    g, aa = np.broadcast_arrays(np.asarray(gamma, dtype=float), np.asarray(a, dtype=float))
    result = np.zeros(g.shape, dtype=float)
    regular = (g > 0.0) & np.isfinite(g) & ~np.isclose(g, 1.0)
    result[regular] = (1.0 - np.power(g[regular], -aa[regular])) / (
        1.0 - np.power(g[regular], -(aa[regular] + 1.0))
    )
    equal = np.isclose(g, 1.0)
    result[equal] = aa[equal] / (aa[equal] + 1.0)
    result[np.isposinf(g)] = 1.0
    result[g <= 0.0] = 0.0
    return np.asarray(np.clip(result, 0.0, 1.0), dtype=float)


def _monthly(values: np.ndarray, name: str) -> np.ndarray:
    result = np.asarray(values, dtype=float)
    if result.shape != (12,):
        raise ValueError(f"{name} must contain 12 monthly values")
    if np.any(result < 0.0) or not np.isfinite(result).all():
        raise ValueError(f"{name} must contain finite non-negative values")
    return result


def calculate_monthly_zone_energy(
    *,
    heating_heat_transfer_kwh: np.ndarray,
    heating_heat_gains_kwh: np.ndarray,
    cooling_heat_transfer_kwh: np.ndarray,
    cooling_heat_gains_kwh: np.ndarray,
    effective_internal_capacity_j_k: float,
    heating_transmission_h_w_k: np.ndarray | float,
    heating_ventilation_h_w_k: np.ndarray | float,
    cooling_transmission_h_w_k: np.ndarray | float,
    cooling_ventilation_h_w_k: np.ndarray | float,
    heating_reference_a0: float,
    heating_reference_tau0_h: float,
    cooling_reference_a0: float,
    cooling_reference_tau0_h: float,
) -> MonthlyZoneEnergy:
    """Calculate 12 monthly sensible heating and cooling needs independently."""
    h_transfer = _monthly(heating_heat_transfer_kwh, "heating_heat_transfer_kwh")
    h_gains = _monthly(heating_heat_gains_kwh, "heating_heat_gains_kwh")
    c_transfer = _monthly(cooling_heat_transfer_kwh, "cooling_heat_transfer_kwh")
    c_gains = _monthly(cooling_heat_gains_kwh, "cooling_heat_gains_kwh")

    tau_h = np.broadcast_to(
        zone_time_constant_h(
            effective_internal_capacity_j_k,
            heating_transmission_h_w_k,
            heating_ventilation_h_w_k,
        ),
        (12,),
    ).astype(float)
    tau_c = np.broadcast_to(
        zone_time_constant_h(
            effective_internal_capacity_j_k,
            cooling_transmission_h_w_k,
            cooling_ventilation_h_w_k,
        ),
        (12,),
    ).astype(float)
    a_h = numerical_parameter(heating_reference_a0, tau_h, heating_reference_tau0_h)
    a_c = numerical_parameter(cooling_reference_a0, tau_c, cooling_reference_tau0_h)

    gamma_h = np.divide(
        h_gains,
        h_transfer,
        out=np.full(12, np.inf),
        where=h_transfer > 0.0,
    )
    eta_h = heating_gain_utilization(gamma_h, a_h)
    heating = np.maximum(h_transfer - eta_h * h_gains, 0.0)

    gamma_c = np.divide(
        c_gains,
        c_transfer,
        out=np.full(12, np.inf),
        where=c_transfer > 0.0,
    )
    eta_c = cooling_loss_utilization(gamma_c, a_c)
    cooling = np.maximum(c_gains - eta_c * c_transfer, 0.0)
    return MonthlyZoneEnergy(heating, cooling, eta_h, eta_c, tau_h, tau_c)
