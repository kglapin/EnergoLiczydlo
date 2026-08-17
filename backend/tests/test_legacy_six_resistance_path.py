"""Regression tests for the historical six-resistance construction input."""

from __future__ import annotations

import numpy as np

from app.engine.iso52016_hourly import solve_zone_iso52016
from app.schemas.models import OpaqueElement, ThermalBridgeConfig


def _wall() -> OpaqueElement:
    return OpaqueElement(
        id="wall",
        name="Wall",
        zone_id="zone",
        area=10.0,
        u_value=0.5,
        thermal_node_capacities_kj_m2k=[1.0] * 5,
        thermal_node_resistances_m2k_w=[0.20, 0.40, 0.40, 0.40, 0.40, 0.20],
    )


def _solve(*, absorbed_solar_w: float):
    return solve_zone_iso52016(
        opaque_elements=[_wall()],
        transparent_elements=[],
        bridges=ThermalBridgeConfig(),
        zone_id="zone",
        h_ve=0.0,
        t_e=np.zeros(8760, dtype=float),
        phi_int=np.zeros(8760, dtype=float),
        phi_sol_transparent=np.zeros(8760, dtype=float),
        opaque_solar_absorbed_w_by_element={"wall": np.full(8760, absorbed_solar_w, dtype=float)},
        t_set_heating=20.0,
        t_set_cooling=None,
        require_explicit_construction_nodes=True,
        max_warmup_cycles=20,
        warmup_tolerance_k=1e-6,
    )


def test_six_resistance_input_preserves_declared_u_value_at_periodic_steady_state() -> None:
    """The complete air-to-boundary R-path must remain equal to 1/U."""
    solution = _solve(absorbed_solar_w=0.0)

    expected_w = 10.0 * 0.5 * 20.0
    assert np.allclose(solution.q_heating, expected_w, rtol=1e-6, atol=1e-4)
    assert solution.periodic_residual_k <= 1e-6


def test_exterior_surface_solar_is_not_injected_at_first_node_centre() -> None:
    """Eliminating the exterior surface must preserve the sol-air balance.

    The compatibility film has Rse=0.04 m²K/W. With 100 W/m² absorbed solar,
    the steady sol-air temperature rises by 4 K. The declared U-value therefore
    reduces the 20 K conductive load by A*U*4 K = 20 W. A full 1000 W source
    inserted at the first material node would bypass the exterior half-layer
    and produce a much larger, non-physical reduction.
    """
    solution = _solve(absorbed_solar_w=1000.0)

    expected_w = 10.0 * 0.5 * (20.0 - 100.0 * 0.04)
    assert np.allclose(solution.q_heating, expected_w, rtol=1e-6, atol=1e-4)
    assert solution.periodic_residual_k <= 1e-6
