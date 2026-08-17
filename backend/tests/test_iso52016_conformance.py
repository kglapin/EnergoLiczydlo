"""Structural and analytical conformance tests for PN-EN ISO 52016-1 clause 6.5."""
from __future__ import annotations

import numpy as np
import pytest

from app.engine.iso52016_hourly import solve_zone_iso52016
from app.engine.iso52016_moisture import (
    humidity_ratio_from_rh,
    rh_from_humidity_ratio,
    solve_zone_moisture,
)
from app.schemas.models import OpaqueElement, ThermalBridgeConfig, TransparentElement


def _strict_wall(**updates):
    data = dict(
        id="wall", name="Wall", zone_id="z1", area=10.0, u_value=0.5,
        solar_absorptance=0.0,
        thermal_node_capacities_kj_m2k=[0.0, 20.0, 40.0, 20.0, 0.0],
        thermal_node_resistances_m2k_w=[0.40, 0.40, 0.40, 0.40],
        h_ci_w_m2k=2.5, h_ri_w_m2k=5.0, h_ce_w_m2k=20.0, h_re_w_m2k=5.0,
        sky_view_factor=0.0,
    )
    data.update(updates)
    return OpaqueElement(**data)


def _strict_window(**updates):
    data = dict(
        id="window", name="Window", zone_id="z1", area=2.0, u_value=1.2,
        g_value=0.6, frame_factor=0.0, shading_factor=1.0,
        h_ci_w_m2k=2.5, h_ri_w_m2k=5.0, h_ce_w_m2k=20.0, h_re_w_m2k=5.0,
        core_thermal_resistance_m2k_w=0.66,
    )
    data.update(updates)
    return TransparentElement(**data)


def _solve(*, wall=None, windows=(), outdoor=0.0, heating=20.0, cooling=None, solar=None, strict=True):
    n = 24
    wall = wall or _strict_wall()
    solar_array = np.zeros(n) if solar is None else np.asarray(solar, dtype=float)
    return solve_zone_iso52016(
        opaque_elements=[wall], transparent_elements=list(windows),
        bridges=ThermalBridgeConfig(), zone_id="z1", h_ve=0.0,
        t_e=np.full(n, outdoor), phi_int=np.zeros(n),
        phi_sol_transparent=solar_array,
        opaque_solar_absorbed_w_by_element={wall.id: np.zeros(n)},
        t_set_heating=heating, t_set_cooling=cooling,
        air_furniture_heat_capacity_j_k=1_000_000.0,
        sky_temperature_difference_k=0.0,
        solar_radiant_distribution=(
            {wall.id: 0.8, windows[0].id: 0.2} if windows and np.any(solar_array) else None
        ),
        strict_conformance=strict,
    )


def test_opaque_nodes_are_five_and_ordered_exterior_to_interior() -> None:
    result = _solve()
    nodes = result.construction_node_temperatures["wall"]
    assert nodes.shape == (24, 5)
    # With cold exterior and heated interior, the exterior node is colder.
    assert np.all(nodes[:, 0] < nodes[:, -1])


def test_transparent_element_has_two_zero_capacity_surface_nodes() -> None:
    result = _solve(windows=[_strict_window()])
    assert result.transparent_node_temperatures is not None
    assert result.transparent_node_temperatures["window"].shape == (24, 2)


def test_hvac_controls_operative_temperature_not_air_temperature() -> None:
    result = _solve(outdoor=-10.0)
    assert np.allclose(result.t_operative, 20.0, atol=1e-7)
    # Cold mean-radiant surfaces require air temperature above the operative setpoint.
    assert np.mean(result.t_air) > 20.0
    assert result.t_mean_radiant is not None
    assert np.mean(result.t_mean_radiant) < 20.0


def test_air_furniture_capacity_is_part_of_dynamic_state() -> None:
    result = solve_zone_iso52016(
        opaque_elements=[_strict_wall()], transparent_elements=[],
        bridges=ThermalBridgeConfig(), zone_id="z1", h_ve=0.0,
        t_e=np.zeros(6), phi_int=np.array([1000.0, 0, 0, 0, 0, 0]),
        phi_sol_transparent=np.zeros(6),
        opaque_solar_absorbed_w_by_element={"wall": np.zeros(6)},
        t_set_heating=None, t_set_cooling=None,
        air_furniture_heat_capacity_j_k=2_000_000.0,
        sky_temperature_difference_k=0.0,
        strict_conformance=True,
    )
    assert result.t_air[0] > result.t_air[1] > result.t_air[2]


def test_strict_mode_rejects_missing_delegated_surface_coefficients() -> None:
    wall = OpaqueElement(
        id="wall", name="Wall", zone_id="z1", area=10.0, u_value=0.5,
        thermal_node_capacities_kj_m2k=[0, 20, 40, 20, 0],
        thermal_node_resistances_m2k_w=[0.4, 0.4, 0.4, 0.4],
    )
    with pytest.raises(ValueError, match="surface coefficients"):
        solve_zone_iso52016(
            opaque_elements=[wall], transparent_elements=[], bridges=ThermalBridgeConfig(),
            zone_id="z1", h_ve=0.0, t_e=np.zeros(1), phi_int=np.zeros(1),
            phi_sol_transparent=np.zeros(1),
            opaque_solar_absorbed_w_by_element={"wall": np.zeros(1)},
            t_set_heating=None, t_set_cooling=None,
            air_furniture_heat_capacity_j_k=1_000_000.0,
            sky_temperature_difference_k=0.0, strict_conformance=True,
        )


def test_longwave_sky_exchange_increases_heating_load() -> None:
    wall = _strict_wall(sky_view_factor=1.0)
    base = solve_zone_iso52016(
        opaque_elements=[wall], transparent_elements=[], bridges=ThermalBridgeConfig(),
        zone_id="z1", h_ve=0.0, t_e=np.zeros(24), phi_int=np.zeros(24),
        phi_sol_transparent=np.zeros(24), opaque_solar_absorbed_w_by_element={"wall": np.zeros(24)},
        t_set_heating=20.0, t_set_cooling=None, air_furniture_heat_capacity_j_k=1_000_000.0,
        sky_temperature_difference_k=0.0, strict_conformance=True,
    )
    sky = solve_zone_iso52016(
        opaque_elements=[wall], transparent_elements=[], bridges=ThermalBridgeConfig(),
        zone_id="z1", h_ve=0.0, t_e=np.zeros(24), phi_int=np.zeros(24),
        phi_sol_transparent=np.zeros(24), opaque_solar_absorbed_w_by_element={"wall": np.zeros(24)},
        t_set_heating=20.0, t_set_cooling=None, air_furniture_heat_capacity_j_k=1_000_000.0,
        sky_temperature_difference_k=11.0, strict_conformance=True,
    )
    assert sky.q_heating.sum() > base.q_heating.sum()


def test_humidity_ratio_round_trip() -> None:
    x = humidity_ratio_from_rh(np.array([20.0]), np.array([0.5]), np.array([101325.0]))
    rh = rh_from_humidity_ratio(np.array([20.0]), x, np.array([101325.0]))
    assert rh[0] == pytest.approx(0.5, rel=1e-6)


def test_moisture_solver_clamps_to_humidity_band_and_reports_latent_load() -> None:
    n = 4
    t = np.full(n, 20.0)
    p = np.full(n, 101325.0)
    x_supply = humidity_ratio_from_rh(t, np.full(n, 0.20), p)
    result = solve_zone_moisture(
        zone_volume_m3=100.0, indoor_temperature_c=t,
        incoming_airflow_m3h=np.full(n, 100.0), supply_humidity_ratio=x_supply,
        atmospheric_pressure_pa=p, relative_humidity_min=0.40,
        relative_humidity_max=0.60, moisture_generation_kg_s=0.0,
    )
    assert np.all(result.relative_humidity >= 0.40 - 1e-8)
    assert result.humidification_kg_s.sum() > 0.0
    assert result.latent_heating_w.sum() > 0.0
