"""External BESTEST Case 600 validation of the dynamic-surface solver."""

from __future__ import annotations

import os
from collections.abc import Sequence

import numpy as np
import pytest

from app.engine.climate import load_epw, radiation_on_surface
from app.engine.iso52016_dynamic_surfaces import solve_zone_iso52016_dynamic_surfaces
from app.engine.solar import solar_gains_transparent
from app.schemas.models import OpaqueElement, ThermalBridgeConfig, TransparentElement
from tests.test_external_bestest import CASE_600_REFERENCE, _download_bestest_weather

Layer = tuple[float, float, float, float]
LENGTH, WIDTH, HEIGHT = 8.0, 6.0, 2.7
WINDOW_AREA = 12.0
FLOOR_AREA = LENGTH * WIDTH
VOLUME = FLOOR_AREA * HEIGHT
LONG_WALL = LENGTH * HEIGHT
SHORT_WALL = WIDTH * HEIGHT
SOUTH_OPAQUE = LONG_WALL - WINDOW_AREA
AIR_DENSITY = (0.414 / 0.5) * 1.2
AIR_CAPACITY = VOLUME * AIR_DENSITY * 1006.0
WINDOW_U = 3.0
WINDOW_G = 0.789
DIRECT_IAM = (1.0, -0.189, 0.644, -0.596)
WINDOW_CORE_R = 2.0 * 0.003175 / 1.06 + 0.1588

WALL: tuple[Layer, ...] = (
    (0.009, 0.140, 900.0, 530.0),
    (0.066, 0.040, 840.0, 12.0),
    (0.012, 0.160, 840.0, 950.0),
)
ROOF: tuple[Layer, ...] = (
    (0.019, 0.140, 900.0, 530.0),
    (0.1118, 0.040, 840.0, 12.0),
    (0.010, 0.160, 840.0, 950.0),
)
FLOOR: tuple[Layer, ...] = ((1.003, 0.040, 0.0, 0.0), (0.025, 0.140, 1200.0, 650.0))


def _nodes(layers: Sequence[Layer]) -> tuple[list[float], list[float], tuple[float, float]]:
    inside_out = list(reversed(layers))
    layer_r = [d / k for d, k, _, _ in inside_out]
    layer_c = [d * cp * rho / 1000.0 for d, _, cp, rho in inside_out]
    step = sum(layer_r) / 5.0
    ranges: list[tuple[float, float, float]] = []
    x = 0.0
    for r, c in zip(layer_r, layer_c, strict=True):
        ranges.append((x, x + r, c))
        x += r
    capacities: list[float] = []
    for node in range(5):
        start, end = node * step, (node + 1) * step
        value = 0.0
        for lo, hi, capacity in ranges:
            overlap = max(0.0, min(end, hi) - max(start, lo))
            if overlap > 0.0:
                value += capacity * overlap / (hi - lo)
        capacities.append(max(value, 1e-9))
    return capacities, [step] * 4, (step / 2.0, step / 2.0)


def _sky_temperature(climate) -> np.ndarray:
    sigma = 5.670374419e-8
    infrared = np.asarray(climate["ghi_infrared"], dtype=float)
    if np.any(infrared <= 0.0):
        raise ValueError("BESTEST infrared radiation must be positive")
    return np.power(infrared / sigma, 0.25) - 273.15


@pytest.mark.skipif(
    os.environ.get("RUN_EXTERNAL_BENCHMARKS") != "1",
    reason="set RUN_EXTERNAL_BENCHMARKS=1 to download public BESTEST weather",
)
def test_repaired_solver_bestest_case_600_is_inside_published_reference_band(tmp_path) -> None:
    epw = tmp_path / "DRYCOLDTMY.epw"
    _download_bestest_weather(epw)
    climate = load_epw(epw)
    wall_c, wall_r, wall_half = _nodes(WALL)
    roof_c, roof_r, roof_half = _nodes(ROOF)
    floor_c, floor_r, floor_half = _nodes(FLOOR)

    def element(
        element_id: str,
        area: float,
        capacities: list[float],
        resistances: list[float],
        *,
        azimuth: float = 0.0,
        inclination: float = 90.0,
        element_type: str = "external_wall",
        absorptance: float = 0.6,
    ) -> OpaqueElement:
        u = 1.0 / (sum(resistances) + 2.0 * resistances[0] / 2.0 + 0.17)
        return OpaqueElement(
            id=element_id,
            name=element_id,
            zone_id="bestest",
            element_type=element_type,
            orientation_azimuth=azimuth,
            inclination=inclination,
            area=area,
            u_value=u,
            solar_absorptance=absorptance,
            thermal_node_capacities_kj_m2k=capacities,
            thermal_node_resistances_m2k_w=resistances,
        )

    opaque = [
        element("east", SHORT_WALL, wall_c, wall_r, azimuth=90.0),
        element("north", LONG_WALL, wall_c, wall_r),
        element("south", SOUTH_OPAQUE, wall_c, wall_r, azimuth=180.0),
        element("west", SHORT_WALL, wall_c, wall_r, azimuth=270.0),
        element("roof", FLOOR_AREA, roof_c, roof_r, inclination=0.0, element_type="roof"),
        element(
            "floor",
            FLOOR_AREA,
            floor_c,
            floor_r,
            inclination=180.0,
            element_type="ground_floor",
            absorptance=0.0,
        ),
    ]
    windows = [
        TransparentElement(
            id=f"south-window-{index}",
            name=f"south-window-{index}",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=WINDOW_AREA / 2.0,
            u_value=WINDOW_U,
            g_value=WINDOW_G,
            frame_factor=0.001,
        )
        for index in (1, 2)
    ]
    transparent_solar = sum(
        (solar_gains_transparent(window, climate, direct_incidence_coefficients=DIRECT_IAM) for window in windows),
        np.zeros(8760),
    )
    opaque_solar: dict[str, np.ndarray] = {}
    for item in opaque:
        if item.id == "floor":
            opaque_solar[item.id] = np.zeros(8760)
        else:
            irradiance = radiation_on_surface(
                climate, float(item.inclination), float(item.orientation_azimuth)
            )
            opaque_solar[item.id] = item.area * item.solar_absorptance * np.asarray(irradiance)

    solution = solve_zone_iso52016_dynamic_surfaces(
        opaque_elements=opaque,
        transparent_elements=windows,
        bridges=ThermalBridgeConfig(),
        zone_id="bestest",
        h_ve=0.414 * VOLUME * 1200.0 / 3600.0,
        t_e=climate["T_e"].to_numpy(dtype=float),
        phi_int=np.full(8760, 200.0),
        phi_sol_transparent=transparent_solar,
        opaque_solar_absorbed_w_by_element=opaque_solar,
        t_set_heating=20.0,
        t_set_cooling=27.0,
        wind_speed_m_s=climate["v_wind"].to_numpy(dtype=float),
        wind_direction_deg=climate["dir_wind"].to_numpy(dtype=float),
        sky_temperature_c=_sky_temperature(climate),
        opaque_boundary_resistances_m2k_w={
            "east": wall_half,
            "north": wall_half,
            "south": wall_half,
            "west": wall_half,
            "roof": roof_half,
            "floor": floor_half,
        },
        window_core_resistances_m2k_w={window.id: WINDOW_CORE_R for window in windows},
        air_heat_capacity_j_k=AIR_CAPACITY,
        internal_convective_fraction=0.4,
        solar_convective_fraction=0.0,
        hvac_convective_fraction=1.0,
        operative_air_weight=1.0,
        wind_exposed_by_element={"floor": False},
        roughness_by_element={
            **{item.id: "rough" for item in opaque},
            **{window.id: "very_smooth" for window in windows},
        },
        emissivity_by_element={
            **{item.id: 0.9 for item in opaque},
            **{window.id: 0.84 for window in windows},
        },
        max_warmup_cycles=30,
        warmup_tolerance_k=0.01,
        nonlinear_iterations=5,
        nonlinear_tolerance_k=0.02,
    )
    actual = {
        "annual_heating_kwh": float(solution.q_heating.sum()) / 1000.0,
        "annual_cooling_kwh": float(solution.q_cooling.sum()) / 1000.0,
        "peak_heating_w": float(solution.q_heating.max()),
        "peak_cooling_w": float(solution.q_cooling.max()),
    }
    print("POST_REPAIR_BESTEST_CASE_600=", actual)
    print("POST_REPAIR_BESTEST_REFERENCE=", CASE_600_REFERENCE)
    print("POST_REPAIR_BESTEST_PERIODIC_RESIDUAL_K=", solution.periodic_residual_k)
    for key, value in actual.items():
        lower, upper = CASE_600_REFERENCE[key]
        assert lower <= value <= upper, (key, value, lower, upper)
