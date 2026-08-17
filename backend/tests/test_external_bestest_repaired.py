"""External BESTEST Case 600 validation of the repaired per-construction solver."""

from __future__ import annotations

import os

import numpy as np
import pytest

from app.engine.climate import load_epw, radiation_on_surface
from app.engine.iso52016_hourly import solve_zone_iso52016
from app.engine.solar import solar_gains_transparent
from app.schemas.models import (
    AdjacentSpaceType,
    OpaqueElement,
    ThermalBridgeConfig,
    TransparentElement,
)
from tests.test_external_bestest import CASE_600_REFERENCE, _download_bestest_weather


@pytest.mark.skipif(
    os.environ.get("RUN_EXTERNAL_BENCHMARKS") != "1",
    reason="set RUN_EXTERNAL_BENCHMARKS=1 to download public BESTEST weather",
)
def test_repaired_solver_bestest_case_600_is_inside_published_reference_band(
    tmp_path,
) -> None:
    epw_path = tmp_path / "DRYCOLDTMY.epw"
    _download_bestest_weather(epw_path)
    climate = load_epw(epw_path)

    wall_u = 1.0 / (0.009 / 0.14 + 0.066 / 0.04 + 0.012 / 0.16 + 0.13 + 0.04)
    roof_u = 1.0 / (0.019 / 0.14 + 0.1118 / 0.04 + 0.01 / 0.16 + 0.10 + 0.04)
    floor_u = 1.0 / (25.075 + 0.025 / 0.14 + 0.17 + 0.04)
    window_u = 1.0 / (2.0 * 0.003175 / 1.06 + 0.1588 + 0.13 + 0.04)

    # BESTEST low-mass record: 51,289.8 J/(m² floor K) over 48 m² floor.
    # Distribute the same total capacity across the opaque test envelope. This
    # preserves the published building heat capacity while the repaired solver
    # assigns it to individual constructions instead of one zone-wide lump.
    opaque_area = 16.2 + 16.2 + 4.2 + 16.2 + 48.0 + 48.0
    total_capacity_j_k = 51289.8 * 48.0
    areal_capacity_kj_m2k = total_capacity_j_k / opaque_area / 1000.0

    def opaque(
        element_id: str,
        name: str,
        area: float,
        u_value: float,
        *,
        azimuth: float = 0.0,
        inclination: float = 90.0,
        element_type: str = "external_wall",
        adjacent: AdjacentSpaceType = AdjacentSpaceType.OUTDOOR,
        adjacent_temperature: float | None = None,
    ) -> OpaqueElement:
        return OpaqueElement(
            id=element_id,
            name=name,
            zone_id="bestest",
            element_type=element_type,
            orientation_azimuth=azimuth,
            inclination=inclination,
            area=area,
            u_value=u_value,
            solar_absorptance=0.6,
            adjacent_space_type=adjacent,
            adjacent_temperature=adjacent_temperature,
            areal_heat_capacity=areal_capacity_kj_m2k,
            mass_distribution_class="distributed",
        )

    opaque_elements = [
        opaque("east", "East", 16.2, wall_u, azimuth=90.0),
        opaque("north", "North", 16.2, wall_u, azimuth=0.0),
        opaque("south", "South", 4.2, wall_u, azimuth=180.0),
        opaque("west", "West", 16.2, wall_u, azimuth=270.0),
        opaque(
            "roof",
            "Roof",
            48.0,
            roof_u,
            inclination=0.0,
            element_type="roof",
        ),
        opaque(
            "floor",
            "Ground floor",
            48.0,
            floor_u,
            inclination=180.0,
            element_type="ground_floor",
            adjacent=AdjacentSpaceType.CONSTANT_TEMPERATURE,
            adjacent_temperature=10.0,
        ),
    ]
    transparent = [
        TransparentElement(
            id="south-window-1",
            name="South window 1",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=6.0,
            u_value=window_u,
            g_value=0.68,
            frame_factor=0.0,
        ),
        TransparentElement(
            id="south-window-2",
            name="South window 2",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=6.0,
            u_value=window_u,
            g_value=0.68,
            frame_factor=0.0,
        ),
    ]

    transparent_solar = sum(
        (solar_gains_transparent(element, climate) for element in transparent),
        np.zeros(8760, dtype=float),
    )
    opaque_solar: dict[str, np.ndarray] = {}
    for element in opaque_elements:
        if element.adjacent_space_type != AdjacentSpaceType.OUTDOOR:
            opaque_solar[element.id] = np.zeros(8760, dtype=float)
            continue
        irradiance = radiation_on_surface(
            climate,
            float(element.inclination),
            float(element.orientation_azimuth),
        )
        opaque_solar[element.id] = (
            float(element.area)
            * float(element.solar_absorptance)
            * np.asarray(irradiance, dtype=float)
        )

    solution = solve_zone_iso52016(
        opaque_elements=opaque_elements,
        transparent_elements=transparent,
        bridges=ThermalBridgeConfig(),
        zone_id="bestest",
        h_ve=0.5 * 129.6 * 1200.0 / 3600.0,
        t_e=climate["T_e"].to_numpy(dtype=float),
        phi_int=np.full(8760, 200.0),
        phi_sol_transparent=np.asarray(transparent_solar, dtype=float),
        opaque_solar_absorbed_w_by_element=opaque_solar,
        t_set_heating=20.0,
        t_set_cooling=27.0,
        internal_convective_fraction=0.4,
        max_warmup_cycles=30,
        warmup_tolerance_k=0.01,
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
