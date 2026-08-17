"""External BESTEST/ASHRAE-140 support and reduced-model diagnostics.

The authoritative Case 600 public-band gate for the repaired detailed solver
lives in ``test_external_bestest_repaired.py``.  This module keeps the pinned
public weather source, reference intervals and a deliberately reduced 5R1C
comparison.  The reduced model is diagnostic only and must not be presented as
an independent BESTEST conformance result.
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
    OpaqueElement,
    ThermalBridgeConfig,
    TransparentElement,
)

BESTEST_WEATHER_URL = (
    "https://raw.githubusercontent.com/NatLabRockies/BESTEST-GSR/main/"
    "integration_testing/weather/DRYCOLDTMY.epw"
)
BESTEST_WEATHER_SHA256 = "a0c27c3eaf22c5f32e1337ddde10f90f9e181a3b732ee78385013fd99b58818b"

# Published reference intervals from the LBL BESTEST user guide / Standard
# 140-2007 comparison table. Energy values are converted from J to kWh;
# cooling is compared as an absolute load because source models store it as a
# negative heat flow. The Case 600 annual-cooling maximum is 7.964 MWh; 7.278
# MWh is one individual program result, not the maximum of the reference set.
CASE_600_REFERENCE = {
    "annual_heating_kwh": (15465600000 / 3600000, 20552400000 / 3600000),
    "annual_cooling_kwh": (22093200000 / 3600000, 28670400000 / 3600000),
    "peak_heating_w": (3437.0, 4354.0),
    "peak_cooling_w": (5965.0, 6827.0),
}

# The GSR EnergyPlus workflow publishes one concrete Case 600 result.  It is
# retained only as a coarse outlier detector for the reduced 5R1C translation.
GSR_CASE_600 = {
    "annual_heating_kwh": 4325.0,
    "annual_cooling_kwh": 6041.67,
    "peak_heating_w": 3204.16,
    "peak_cooling_w": 6352.44,
}

CASE_600_LENGTH_M = 8.0
CASE_600_WIDTH_M = 6.0
CASE_600_HEIGHT_M = 2.7
CASE_600_WINDOW_AREA_M2 = 12.0
CASE_600_FLOOR_AREA_M2 = CASE_600_LENGTH_M * CASE_600_WIDTH_M
CASE_600_LONG_WALL_M2 = CASE_600_LENGTH_M * CASE_600_HEIGHT_M
CASE_600_SHORT_WALL_M2 = CASE_600_WIDTH_M * CASE_600_HEIGHT_M
CASE_600_SOUTH_OPAQUE_M2 = CASE_600_LONG_WALL_M2 - CASE_600_WINDOW_AREA_M2


def test_external_bestest_mass_records_map_to_5r1c_properties() -> None:
    """Check the published BESTEST mass records against our 5R1C inputs."""
    for heat_capacity, mass_factor in ((51289.8, 4.522), (249272.0, 2.7)):
        kappa = heat_capacity / (mass_factor * 1000.0)
        properties = zone_thermal_properties(
            CASE_600_FLOOR_AREA_M2,
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


def _reduced_5r1c_case_600_solution(epw_path: Path, integrated_g_value: float):
    """Run a reduced 5R1C approximation using the published Case 600 geometry."""
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
            area=CASE_600_SHORT_WALL_M2,
            u_value=wall_u,
        ),
        OpaqueElement(
            id="north",
            name="North",
            zone_id="bestest",
            orientation_azimuth=0.0,
            area=CASE_600_LONG_WALL_M2,
            u_value=wall_u,
        ),
        OpaqueElement(
            id="south",
            name="South",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=CASE_600_SOUTH_OPAQUE_M2,
            u_value=wall_u,
        ),
        OpaqueElement(
            id="west",
            name="West",
            zone_id="bestest",
            orientation_azimuth=270.0,
            area=CASE_600_SHORT_WALL_M2,
            u_value=wall_u,
        ),
        OpaqueElement(
            id="roof",
            name="Roof",
            zone_id="bestest",
            element_type="roof",
            inclination=0.0,
            area=CASE_600_FLOOR_AREA_M2,
            u_value=roof_u,
        ),
        OpaqueElement(
            id="floor",
            name="Floor",
            zone_id="bestest",
            element_type="ground_floor",
            inclination=180.0,
            area=CASE_600_FLOOR_AREA_M2,
            u_value=floor_u,
            # Case 600 defines Outdoors + NoSun + NoWind for this surface.
            # OUTDOOR is the schema default; zero absorptance suppresses the
            # solar term in this reduced model.
            solar_absorptance=0.0,
        ),
    ]
    transparent = [
        TransparentElement(
            id="south-window-1",
            name="South window 1",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=CASE_600_WINDOW_AREA_M2 / 2.0,
            u_value=window_u,
            g_value=integrated_g_value,
            frame_factor=0.0,
        ),
        TransparentElement(
            id="south-window-2",
            name="South window 2",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=CASE_600_WINDOW_AREA_M2 / 2.0,
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
        CASE_600_FLOOR_AREA_M2,
        kappa_kj_m2k=51289.8 / (4.522 * 1000.0),
        am_per_floor_area=4.522,
    )
    return solve_zone_5r1c(
        network=network,
        # This reduced diagnostic keeps the same altitude-adjusted equivalent
        # used by the detailed benchmark. It is not the conformance gate.
        h_ve=0.414 * 129.6 * 1200.0 / 3600.0,
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
def test_reduced_5r1c_case_600_diagnostic_stays_near_energyplus_result(
    tmp_path: Path,
) -> None:
    """Keep the reduced solver useful as an outlier detector, not a conformance gate."""
    epw_path = tmp_path / "DRYCOLDTMY.epw"
    _download_bestest_weather(epw_path)
    solution = _reduced_5r1c_case_600_solution(epw_path, integrated_g_value=0.68)

    actual = {
        "annual_heating_kwh": float(solution.q_heating.sum()) / 1000.0,
        "annual_cooling_kwh": float(solution.q_cooling.sum()) / 1000.0,
        "peak_heating_w": float(solution.q_heating.max()),
        "peak_cooling_w": float(solution.q_cooling.max()),
    }
    assert all(np.isfinite(value) and value >= 0.0 for value in actual.values())

    # 35% is deliberately broad: the reduced 5R1C translation does not model
    # the detailed construction nodes/surface balances used by the audited
    # solver. The official reference-band assertions are intentionally absent
    # here and live only in test_external_bestest_repaired.py.
    for key, reference in GSR_CASE_600.items():
        assert actual[key] == pytest.approx(reference, rel=0.35)
