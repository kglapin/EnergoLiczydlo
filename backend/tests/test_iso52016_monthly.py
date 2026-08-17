"""Analytical checks for PN-EN ISO 52016-1 clause 6.6 helpers."""
from __future__ import annotations

import numpy as np
import pytest

from app.engine.iso52016_monthly import (
    calculate_monthly_zone_energy,
    heating_gain_utilization,
    numerical_parameter,
    zone_time_constant_h,
)


def test_zone_time_constant_uses_internal_capacity_and_total_h() -> None:
    tau = zone_time_constant_h(3_600_000.0, 50.0, 50.0)
    assert float(tau) == pytest.approx(10.0)


def test_heating_utilization_gamma_one_uses_analytical_limit() -> None:
    eta = heating_gain_utilization(np.array([1.0]), np.array([2.0]))
    assert eta[0] == pytest.approx(2.0 / 3.0)


def test_numerical_parameter_increases_with_time_constant() -> None:
    result = numerical_parameter(1.0, np.array([10.0, 20.0]), 10.0)
    assert np.allclose(result, [2.0, 3.0])


def _monthly(**updates):
    kwargs = dict(
        heating_heat_transfer_kwh=np.full(12, 100.0),
        heating_heat_gains_kwh=np.zeros(12),
        cooling_heat_transfer_kwh=np.full(12, 100.0),
        cooling_heat_gains_kwh=np.zeros(12),
        effective_internal_capacity_j_k=36_000_000.0,
        heating_transmission_h_w_k=80.0,
        heating_ventilation_h_w_k=20.0,
        cooling_transmission_h_w_k=80.0,
        cooling_ventilation_h_w_k=20.0,
        heating_reference_a0=1.0,
        heating_reference_tau0_h=15.0,
        cooling_reference_a0=1.0,
        cooling_reference_tau0_h=15.0,
    )
    kwargs.update(updates)
    return calculate_monthly_zone_energy(**kwargs)


def test_monthly_no_gains_returns_full_heating_losses_and_zero_cooling() -> None:
    result = _monthly()
    assert np.allclose(result.heating_kwh, 100.0)
    assert np.allclose(result.cooling_kwh, 0.0)


def test_monthly_gains_reduce_heating_need() -> None:
    result = _monthly(heating_heat_gains_kwh=np.full(12, 50.0))
    assert np.all(result.heating_kwh < 100.0)
    assert np.all(result.heating_kwh >= 0.0)


def test_heating_and_cooling_use_independent_monthly_inputs() -> None:
    result = _monthly(
        heating_heat_gains_kwh=np.zeros(12),
        cooling_heat_gains_kwh=np.full(12, 150.0),
        cooling_heat_transfer_kwh=np.full(12, 50.0),
        cooling_transmission_h_w_k=30.0,
        cooling_ventilation_h_w_k=20.0,
    )
    assert np.allclose(result.heating_kwh, 100.0)
    assert np.all(result.cooling_kwh > 0.0)
    assert not np.allclose(result.heating_time_constant_h, result.cooling_time_constant_h)
