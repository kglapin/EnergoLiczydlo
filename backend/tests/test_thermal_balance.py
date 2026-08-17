"""Analytic tests of the 5R1C zone solver (ISO 13790 / PN-EN ISO 52016-1)."""

import numpy as np
import pytest

from app.engine.thermal_balance import (
    TransmissionNetwork,
    opaque_external_conductance,
    solve_zone_5r1c,
    zone_thermal_properties,
)

N = 8760


def test_opaque_external_conductance_preserves_opaque_u_value():
    """The Htr,em/Htr,ms series path must equal the input Htr,op."""
    h_opaque = 50.0
    h_ms = 9.1 * 250.0
    h_em = opaque_external_conductance(h_opaque, h_ms)
    equivalent = 1.0 / (1.0 / h_em + 1.0 / h_ms)
    assert equivalent == pytest.approx(h_opaque, rel=1e-12)


def test_opaque_external_conductance_rejects_invalid_split():
    with pytest.raises(ValueError, match="H_tr,op < H_tr,ms"):
        opaque_external_conductance(100.0, 100.0)


def _network(h_opaque: float = 50.0, drive: float = -10.0) -> TransmissionNetwork:
    net = TransmissionNetwork()
    net.add_opaque(h_opaque, np.full(N, drive))
    net.add_surface(30.0, np.full(N, drive))  # windows, same drive for tests
    return net


def test_no_load_at_setpoint_with_zero_gains():
    """With T_e = T_set_heating and no gains/losses, no heating/cooling needed."""
    net = _network(drive=20.0)
    solution = solve_zone_5r1c(
        network=net,
        h_ve=30.0,
        t_e=np.full(N, 20.0),
        phi_int=np.zeros(N),
        phi_sol=np.zeros(N),
        properties=zone_thermal_properties(100.0),
        t_set_heating=20.0,
        t_set_cooling=26.0,
    )
    assert np.sum(solution.q_heating) == 0.0
    assert np.sum(solution.q_cooling) == 0.0
    np.testing.assert_allclose(solution.t_air, 20.0, atol=1e-6)


def _effective_gains(phi_int: float, phi_sol: float, h_surface: float, at: float) -> float:
    """phi_ia + phi_m + phi_st after the ISO 13790 split.

    The standard drops the fraction H_tr,w/(9.1*A_t) of the (0.5*phi_int +
    phi_sol) stream associated with the glazing; the solver must conserve
    exactly this effective total.
    """
    dropped = h_surface / (9.1 * at)
    return 0.5 * phi_int + (1.0 - dropped) * (0.5 * phi_int + phi_sol)


def test_steady_state_heating_matches_analytic():
    """Constant cold outdoor: converged hourly heating equals node losses - gains.

    In the 5R1C network the air, surface and mass nodes settle at different
    temperatures, so the analytic steady state is the energy balance
    evaluated at the *node* temperatures, not a lumped U*A*(T_set - T_e).
    """
    h_op, h_w, h_ve = 50.0, 30.0, 30.0  # W/K
    t_e_val, t_set, gains = -10.0, 20.0, 800.0
    net = TransmissionNetwork()
    net.add_opaque(h_op, np.full(N, t_e_val))
    net.add_surface(h_w, np.full(N, t_e_val))
    solution = solve_zone_5r1c(
        network=net,
        h_ve=h_ve,
        t_e=np.full(N, t_e_val),
        phi_int=np.full(N, gains),
        phi_sol=np.zeros(N),
        properties=zone_thermal_properties(100.0),
        t_set_heating=t_set,
        t_set_cooling=None,
    )
    t_s = solution.t_surface
    hem = opaque_external_conductance(h_op, 9.1 * 250.0)
    losses = (
        hem * (solution.t_mass_mean - t_e_val)
        + h_w * (t_s - t_e_val)
        + h_ve * (solution.t_air - t_e_val)
    )
    effective = _effective_gains(gains, 0.0, h_w, 450.0)
    # After the initial mass transient: heating + effective gains = losses.
    np.testing.assert_allclose(
        solution.q_heating[500:] + effective, losses[500:], rtol=1e-8
    )
    assert np.all(solution.q_cooling == 0.0)
    np.testing.assert_allclose(solution.t_air[500:], t_set, atol=1e-9)


def test_free_float_converges_to_outdoor():
    """No setpoints and no gains: all node temperatures relax to T_e."""
    net = _network(drive=5.0)
    solution = solve_zone_5r1c(
        network=net,
        h_ve=30.0,
        t_e=np.full(N, 5.0),
        phi_int=np.zeros(N),
        phi_sol=np.zeros(N),
        properties=zone_thermal_properties(100.0),
        t_set_heating=None,
        t_set_cooling=None,
    )
    assert np.sum(solution.q_heating) == 0.0
    assert np.sum(solution.q_cooling) == 0.0
    np.testing.assert_allclose(solution.t_air[-1], 5.0, atol=1e-6)
    np.testing.assert_allclose(solution.t_mass[-1], 5.0, atol=1e-6)


def test_gain_splitting_conserves_energy():
    """Steady free-float: node losses equal the injected gains."""
    net = _network(drive=10.0)
    phi_int = np.full(N, 1000.0)
    phi_sol = np.full(N, 2000.0)
    solution = solve_zone_5r1c(
        network=net,
        h_ve=30.0,
        t_e=np.full(N, 10.0),
        phi_int=phi_int,
        phi_sol=phi_sol,
        properties=zone_thermal_properties(100.0),
        t_set_heating=None,
        t_set_cooling=None,
    )
    t_s = solution.t_surface
    hem = opaque_external_conductance(50.0, 9.1 * 250.0)
    losses = (
        hem * (solution.t_mass_mean - 10.0)
        + 30.0 * (t_s - 10.0)
        + 30.0 * (solution.t_air - 10.0)
    )
    effective = _effective_gains(1000.0, 2000.0, 30.0, 450.0)
    # tau ~ C_m/H ~ 104 h; by hour 3000 the mass transient has fully decayed.
    np.testing.assert_allclose(losses[3000:], effective, rtol=1e-8)


def test_cooling_demand_when_hot():
    """Constant hot outdoor temperature with gains should produce cooling."""
    net = _network(drive=30.0)
    solution = solve_zone_5r1c(
        network=net,
        h_ve=30.0,
        t_e=np.full(N, 30.0),
        phi_int=np.full(N, 500.0),
        phi_sol=np.full(N, 1000.0),
        properties=zone_thermal_properties(100.0),
        t_set_heating=20.0,
        t_set_cooling=26.0,
    )
    assert np.sum(solution.q_cooling) > 0.0
    # After the initial mass transient the air node sits exactly at the
    # cooling setpoint (the first hours warm the mass from its cold start).
    np.testing.assert_allclose(solution.t_air[500:], 26.0, atol=1e-9)


def test_zero_ventilation_is_solved():
    """h_ve = 0 must not break the linear solve."""
    net = _network(drive=0.0)
    solution = solve_zone_5r1c(
        network=net,
        h_ve=0.0,
        t_e=np.zeros(N),
        phi_int=np.zeros(N),
        phi_sol=np.zeros(N),
        properties=zone_thermal_properties(100.0),
        t_set_heating=20.0,
        t_set_cooling=None,
    )
    assert solution.q_heating.sum() > 0.0


def test_thermal_properties_formula():
    props = zone_thermal_properties(120.0, kappa_kj_m2k=165.0)
    assert props.area_total_internal == pytest.approx(4.5 * 120.0)
    assert props.area_mass == pytest.approx(2.5 * 120.0)
    # C_m = kappa [kJ/(m2*K)] * 1000 * A_m  ->  J/K
    assert props.capacity == pytest.approx(165_000.0 * 300.0)
    assert props.h_tr_is == pytest.approx(3.45 * 540.0)
    assert props.h_tr_ms == pytest.approx(9.1 * 300.0)


def test_transmission_network_weighted_drive():
    """Merging conductances must produce the U*A-weighted driving temperature."""
    net = TransmissionNetwork()
    net.add_opaque(20.0, np.full(10, 0.0))
    net.add_opaque(30.0, np.full(10, 10.0))
    assert net.h_opaque == pytest.approx(50.0)
    np.testing.assert_allclose(net.t_opaque, 6.0)
