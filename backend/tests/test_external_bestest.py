"""External BESTEST/ASHRAE-140 comparison checks.

The full external-weather comparison is opt-in because it downloads a public
weather file.  The reference values and the thermal-mass mapping are kept
local and deterministic; the network test is run in this audit with
``RUN_EXTERNAL_BENCHMARKS=1``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pytest

from app.engine.climate import load_epw
from app.engine.envelope import zone_transmission_network
from app.engine.solar import total_solar_gains
from app.engine.thermal_balance import solve_zone_5r1c, zone_thermal_properties
from app.schemas.models import (
    AdjacentSpaceType,
    OpaqueElement,
    ThermalBridgeConfig,
    TransparentElement,
)

BESTEST_WEATHER_URL = (
    "https://raw.githubusercontent.com/NatLabRockies/BESTEST-GSR/main/"
    "integration_testing/weather/DRYCOLDTMY.epw"
)
BESTEST_WEATHER_SHA256 = "a0c27c3eaf22c5f32e1337ddde10f90f9e181a3b732ee78385013fd99b58818b"

# Published reference intervals from LBL Modelica BESTEST Case 600.
# Energy values are converted from J to kWh; cooling is compared as an
# absolute load because the source stores it as a negative heat flow.
CASE_600_REFERENCE = {
    "annual_heating_kwh": (15465600000 / 3600000, 20552400000 / 3600000),
    "annual_cooling_kwh": (22093200000 / 3600000, 26200800000 / 3600000),
    "peak_heating_w": (3437.0, 4354.0),
    "peak_cooling_w": (5965.0, 6827.0),
}

# The GSR EnergyPlus workflow publishes one concrete Case 600 result.  This
# is used as an approximate outlier detector for this project's simplified
# 5R1C envelope translation, not as a certification tolerance.
GSR_CASE_600 = {
    "annual_heating_kwh": 4325.0,
    "annual_cooling_kwh": 6041.67,
    "peak_heating_w": 3204.16,
    "peak_cooling_w": 6352.44,
}


def test_external_bestest_mass_records_map_to_5r1c_properties() -> None:
    """Check the published BESTEST mass records against our 5R1C inputs."""
    for heat_capacity, mass_factor in ((51289.8, 4.522), (249272.0, 2.7)):
        kappa = heat_capacity / (mass_factor * 1000.0)
        properties = zone_thermal_properties(
            48.0,
            kappa_kj_m2k=kappa,
            am_per_floor_area=mass_factor,
        )
        assert properties.capacity / properties.floor_area == pytest.approx(heat_capacity)
        assert properties.area_mass / properties.floor_area == pytest.approx(mass_factor)


def _download_bestest_weather(target: Path) -> None:
    with urlopen(BESTEST_WEATHER_URL, timeout=30) as response:
        target.write_bytes(response.read())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    assert digest == BESTEST_WEATHER_SHA256


def _bestest_case_600_solution(epw_path: Path, integrated_g_value: float):
    """Run the reduced 5R1C equivalent of external BESTEST Case 600."""
    climate = load_epw(epw_path)
    wall_u = 1.0 / (0.009 / 0.14 + 0.066 / 0.04 + 0.012 / 0.16 + 0.13 + 0.04)
    roof_u = 1.0 / (0.019 / 0.14 + 0.1118 / 0.04 + 0.01 / 0.16 + 0.10 + 0.04)
    floor_u = 1.0 / (25.075 + 0.025 / 0.14 + 0.17 + 0.04)
    window_u = 1.0 / (2.0 * 0.003175 / 1.06 + 0.1588 + 0.13 + 0.04)
    opaque = [
        OpaqueElement(
            id="east",
            name="East",
            zone_id="bestest",
            orientation_azimuth=90.0,
            area=16.2,
            u_value=wall_u,
        ),
        OpaqueElement(
            id="north",
            name="North",
            zone_id="bestest",
            orientation_azimuth=0.0,
            area=16.2,
            u_value=wall_u,
        ),
        OpaqueElement(
            id="south",
            name="South",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=4.2,
            u_value=wall_u,
        ),
        OpaqueElement(
            id="west",
            name="West",
            zone_id="bestest",
            orientation_azimuth=270.0,
            area=16.2,
            u_value=wall_u,
        ),
        OpaqueElement(
            id="roof",
            name="Roof",
            zone_id="bestest",
            element_type="roof",
            inclination=0.0,
            area=48.0,
            u_value=roof_u,
        ),
        OpaqueElement(
            id="floor",
            name="Ground floor",
            zone_id="bestest",
            element_type="ground_floor",
            inclination=180.0,
            area=48.0,
            u_value=floor_u,
            adjacent_space_type=AdjacentSpaceType.GROUND,
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
            g_value=integrated_g_value,
            frame_factor=0.0,
        ),
        TransparentElement(
            id="south-window-2",
            name="South window 2",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=6.0,
            u_value=window_u,
            g_value=integrated_g_value,
            frame_factor=0.0,
        ),
    ]
    t_e = climate["T_e"].to_numpy()
    network = zone_transmission_network(
        opaque,
        transparent,
        ThermalBridgeConfig(),
        t_e,
        zone_id="bestest",
    )
    solar_transparent, solar_opaque = total_solar_gains(transparent, opaque, climate)
    properties = zone_thermal_properties(
        48.0,
        kappa_kj_m2k=51289.8 / (4.522 * 1000.0),
        am_per_floor_area=4.522,
    )
    return solve_zone_5r1c(
        network=network,
        h_ve=0.5 * 129.6 * 1200.0 / 3600.0,
        t_e=t_e,
        phi_int=np.full(8760, 200.0),
        phi_sol=solar_transparent + solar_opaque,
        properties=properties,
        t_set_heating=20.0,
        t_set_cooling=27.0,
    )


@pytest.mark.skipif(
    os.environ.get("RUN_EXTERNAL_BENCHMARKS") != "1",
    reason="set RUN_EXTERNAL_BENCHMARKS=1 to download the public BESTEST weather file",
)
def test_external_bestest_case_600_is_inside_published_reference_band(
    tmp_path: Path,
) -> None:
    epw_path = tmp_path / "DRYCOLDTMY.epw"
    _download_bestest_weather(epw_path)
    solution = _bestest_case_600_solution(epw_path, integrated_g_value=0.68)

    annual_heating = float(solution.q_heating.sum())
    annual_cooling = float(solution.q_cooling.sum())
    peak_heating = float(solution.q_heating.max())
    peak_cooling = float(solution.q_cooling.max())
    assert CASE_600_REFERENCE["annual_heating_kwh"][0] * 1000 <= annual_heating <= (
        CASE_600_REFERENCE["annual_heating_kwh"][1] * 1000
    )
    assert CASE_600_REFERENCE["annual_cooling_kwh"][0] * 1000 <= annual_cooling <= (
        CASE_600_REFERENCE["annual_cooling_kwh"][1] * 1000
    )
    assert CASE_600_REFERENCE["peak_heating_w"][0] <= peak_heating <= (
        CASE_600_REFERENCE["peak_heating_w"][1]
    )
    assert CASE_600_REFERENCE["peak_cooling_w"][0] <= peak_cooling <= (
        CASE_600_REFERENCE["peak_cooling_w"][1]
    )

    # The simplified mapping should remain close to the concrete EnergyPlus
    # workflow result, with 25% reserved for differences in surface films,
    # solar transposition and ground-temperature treatment.
    actual = {
        "annual_heating_kwh": annual_heating / 1000.0,
        "annual_cooling_kwh": annual_cooling / 1000.0,
        "peak_heating_w": peak_heating,
        "peak_cooling_w": peak_cooling,
    }
    for key, reference in GSR_CASE_600.items():
        assert actual[key] == pytest.approx(reference, rel=0.25)
