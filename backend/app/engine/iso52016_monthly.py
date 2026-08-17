"""PN-EN ISO 52016-1 clause 6.6 monthly utilization-factor method.

This module is deliberately independent from the Polish legal certificate
engine.  Reference parameters a0 and tau0 are Annex-A/national choices and are
therefore inputs rather than guessed constants in strict mode.
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
    time_constant_h: np.ndarray


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
    gamma = np.asarray(gamma, dtype=float)
    a = np.asarray(a, dtype=float)
    result = np.ones(np.broadcast_shapes(gamma.shape, a.shape), dtype=float)
    g, aa = np.broadcast_arrays(gamma, a)
    regular = (g > 0.0) & ~np.isclose(g, 1.0)
    result[regular] = (1.0 - np.power(g[regular], aa[regular])) / (
        1.0 - np.power(g[regular], aa[regular] + 1.0)
    )
    equal = np.isclose(g, 1.0)
    result[equal] = aa[equal] / (aa[equal] + 1.0)
    result[g <= 0.0] = 1.0
    return np.asarray(np.clip(result, 0.0, 1.0), dtype=float)


def cooling_loss_utilization(gamma: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Cooling loss-utilization factor from clause 6.6.10.3.

    gamma is the cooling heat-balance ratio Q_gn / Q_ht.  The inverse-power
    form is the cooling counterpart of the heating utilization equation.
    """
    gamma = np.asarray(gamma, dtype=float)
    a = np.asarray(a, dtype=float)
    result = np.zeros(np.broadcast_shapes(gamma.shape, a.shape), dtype=float)
    g, aa = np.broadcast_arrays(gamma, a)
    regular = (g > 0.0) & ~np.isclose(g, 1.0)
    result[regular] = (1.0 - np.power(g[regular], -aa[regular])) / (
        1.0 - np.power(g[regular], -(aa[regular] + 1.0))
    )
    equal = np.isclose(g, 1.0)
    result[equal] = aa[equal] / (aa[equal] + 1.0)
    result[g <= 0.0] = 0.0
    return np.asarray(np.clip(result, 0.0, 1.0), dtype=float)


def calculate_monthly_zone_energy(
    *,
    heat_transfer_kwh: np.ndarray,
    heat_gains_kwh: np.ndarray,
    effective_internal_capacity_j_k: float,
    transmission_h_w_k: np.ndarray | float,
    ventilation_h_w_k: np.ndarray | float,
    heating_reference_a0: float,
    heating_reference_tau0_h: float,
    cooling_reference_a0: float,
    cooling_reference_tau0_h: float,
) -> MonthlyZoneEnergy:
    """Calculate 12 monthly sensible heating/cooling needs.

    Signed transfer is not accepted here: callers supply the positive monthly
    heat-transfer magnitude used by the utilization-factor method and positive
    internal+solar gains. Heating and cooling are evaluated separately from the
    same balance, as required by clause 6.6.3.
    """
    losses = np.asarray(heat_transfer_kwh, dtype=float)
    gains = np.asarray(heat_gains_kwh, dtype=float)
    if losses.shape != (12,) or gains.shape != (12,):
        raise ValueError("monthly ISO 52016 inputs must contain 12 values")
    if np.any(losses < 0.0) or np.any(gains < 0.0):
        raise ValueError("monthly transfer and gain magnitudes must be non-negative")
    tau = zone_time_constant_h(
        effective_internal_capacity_j_k,
        transmission_h_w_k,
        ventilation_h_w_k,
    )
    tau = np.broadcast_to(tau, (12,)).astype(float)
    a_h = numerical_parameter(heating_reference_a0, tau, heating_reference_tau0_h)
    a_c = numerical_parameter(cooling_reference_a0, tau, cooling_reference_tau0_h)

    gamma_h = np.divide(gains, losses, out=np.full(12, np.inf), where=losses > 0.0)
    eta_h = heating_gain_utilization(gamma_h, a_h)
    heating = np.maximum(losses - eta_h * gains, 0.0)

    gamma_c = np.divide(gains, losses, out=np.full(12, np.inf), where=losses > 0.0)
    eta_c = cooling_loss_utilization(gamma_c, a_c)
    cooling = np.maximum(gains - eta_c * losses, 0.0)
    return MonthlyZoneEnergy(heating, cooling, eta_h, eta_c, tau)
