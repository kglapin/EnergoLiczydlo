"""Regression tests for the historical six-resistance construction input."""

from __future__ import annotations

import numpy as np

from app.engine.iso52016_hourly import solve_zone_iso52016
from app.schemas.models import OpaqueElement, ThermalBridgeConfig


def test_six_resistance_input_preserves_declared_u_value_at_periodic_steady_state() -> None:
    """The complete air-to-boundary R-path must remain equal to 1/U.

    The six-value compatibility representation stores two surface/half-node
    boundary resistances and four node-to-node core resistances. Dropping the
    half-node pieces would shorten the path from 2.0 to 1.77 m²K/W in this
    case and raise the steady heat loss from 100 W to about 113 W.
    """
    area = 10.0
    u_value = 0.5
    element = OpaqueElement(
        id="wall",
        name="Wall",
        zone_id="zone",
        area=area,
        u_value=u_value,
        thermal_node_capacities_kj_m2k=[1.0] * 5,
        thermal_node_resistances_m2k_w=[0.20, 0.40, 0.40, 0.40, 0.40, 0.20],
    )

    solution = solve_zone_iso52016(
        opaque_elements=[element],
        transparent_elements=[],
        bridges=ThermalBridgeConfig(),
        zone_id="zone",
        h_ve=0.0,
        t_e=np.zeros(8760, dtype=float),
        phi_int=np.zeros(8760, dtype=float),
        phi_sol_transparent=np.zeros(8760, dtype=float),
        opaque_solar_absorbed_w_by_element={"wall": np.zeros(8760, dtype=float)},
        t_set_heating=20.0,
        t_set_cooling=None,
        require_explicit_construction_nodes=True,
        max_warmup_cycles=20,
        warmup_tolerance_k=1e-6,
    )

    expected_w = area * u_value * 20.0
    assert np.allclose(solution.q_heating, expected_w, rtol=1e-6, atol=1e-4)
    assert solution.periodic_residual_k <= 1e-6
