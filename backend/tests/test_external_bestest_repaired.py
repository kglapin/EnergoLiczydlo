"""External BESTEST Case 600 validation of the repaired per-construction solver."""

from __future__ import annotations

import os
from collections.abc import Sequence

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

Layer = tuple[float, float, float, float]  # thickness, conductivity, cp, density

# Published Case 600 box geometry: 8 m x 6 m x 2.7 m, with two 6 m²
# south-facing windows. Keep these dimensions explicit so the benchmark cannot
# accidentally pass with an undersized envelope.
CASE_600_LENGTH_M = 8.0
CASE_600_WIDTH_M = 6.0
CASE_600_HEIGHT_M = 2.7
CASE_600_WINDOW_AREA_M2 = 12.0
CASE_600_FLOOR_AREA_M2 = CASE_600_LENGTH_M * CASE_600_WIDTH_M
CASE_600_LONG_WALL_M2 = CASE_600_LENGTH_M * CASE_600_HEIGHT_M
CASE_600_SHORT_WALL_M2 = CASE_600_WIDTH_M * CASE_600_HEIGHT_M
CASE_600_SOUTH_OPAQUE_M2 = CASE_600_LONG_WALL_M2 - CASE_600_WINDOW_AREA_M2
# LBNL's ISO 13790 implementation of the ASHRAE 140-2007 Case 600 uses
# Uwin ~= 2.984 W/(m²K) and an integrated solar gain factor g = 0.789.
# The layer-derived U-value below is 2.987 W/(m²K), so the same reference
# glazing is represented here with g=0.789 rather than an arbitrary 0.68.
CASE_600_WINDOW_G_VALUE = 0.789

WALL_LAYERS_OUTSIDE_TO_INSIDE: tuple[Layer, ...] = (
    (0.009, 0.140, 900.0, 530.0),
    (0.066, 0.040, 840.0, 12.0),
    (0.012, 0.160, 840.0, 950.0),
)
ROOF_LAYERS_OUTSIDE_TO_INSIDE: tuple[Layer, ...] = (
    (0.019, 0.140, 900.0, 530.0),
    (0.1118, 0.040, 840.0, 12.0),
    (0.010, 0.160, 840.0, 950.0),
)
FLOOR_LAYERS_BOUNDARY_TO_INSIDE: tuple[Layer, ...] = (
    (1.003, 0.040, 0.0, 0.0),
    (0.025, 0.140, 1200.0, 650.0),
)


def _five_node_construction(
    layers_outside_to_inside: Sequence[Layer],
    *,
    r_si: float,
    r_se: float,
) -> tuple[list[float], list[float]]:
    """Map published material layers to five finite-volume nodes.

    The construction is partitioned into five equal intervals in thermal-
    resistance coordinates. Nodal heat capacity is integrated from the actual
    materials over each interval. Six path resistances connect the indoor film,
    five node centres and the external/boundary film, preserving total R and C.
    """
    layers_inside_to_outside = list(reversed(layers_outside_to_inside))
    layer_r = [
        thickness / conductivity for thickness, conductivity, _, _ in layers_inside_to_outside
    ]
    layer_c = [
        thickness * specific_heat * density / 1000.0
        for thickness, _, specific_heat, density in layers_inside_to_outside
    ]
    material_r = sum(layer_r)
    bin_r = material_r / 5.0

    ranges: list[tuple[float, float, float]] = []
    position = 0.0
    for resistance, capacity in zip(layer_r, layer_c, strict=True):
        ranges.append((position, position + resistance, capacity))
        position += resistance

    capacities: list[float] = []
    for node in range(5):
        start = node * bin_r
        end = (node + 1) * bin_r
        capacity = 0.0
        for layer_start, layer_end, layer_capacity in ranges:
            overlap = max(0.0, min(end, layer_end) - max(start, layer_start))
            if overlap > 0.0 and layer_end > layer_start:
                capacity += layer_capacity * overlap / (layer_end - layer_start)
        # Zero-capacity insulation is physically valid; a tiny numerical floor
        # keeps compatibility with schemas that require strictly positive nodes.
        capacities.append(max(capacity, 1e-9))

    resistances = [r_si + 0.5 * bin_r, *([bin_r] * 4), r_se + 0.5 * bin_r]
    return capacities, resistances


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

    wall_nodes = _five_node_construction(
        WALL_LAYERS_OUTSIDE_TO_INSIDE,
        r_si=0.13,
        r_se=0.04,
    )
    roof_nodes = _five_node_construction(
        ROOF_LAYERS_OUTSIDE_TO_INSIDE,
        r_si=0.10,
        r_se=0.04,
    )
    floor_nodes = _five_node_construction(
        FLOOR_LAYERS_BOUNDARY_TO_INSIDE,
        r_si=0.17,
        r_se=0.04,
    )

    def opaque(
        element_id: str,
        name: str,
        area: float,
        u_value: float,
        nodes: tuple[list[float], list[float]],
        *,
        azimuth: float = 0.0,
        inclination: float = 90.0,
        element_type: str = "external_wall",
        adjacent: AdjacentSpaceType = AdjacentSpaceType.OUTDOOR,
        adjacent_temperature: float | None = None,
    ) -> OpaqueElement:
        capacities, resistances = nodes
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
            thermal_node_capacities_kj_m2k=capacities,
            thermal_node_resistances_m2k_w=resistances,
        )

    opaque_elements = [
        opaque(
            "east",
            "East",
            CASE_600_SHORT_WALL_M2,
            wall_u,
            wall_nodes,
            azimuth=90.0,
        ),
        opaque(
            "north",
            "North",
            CASE_600_LONG_WALL_M2,
            wall_u,
            wall_nodes,
            azimuth=0.0,
        ),
        opaque(
            "south",
            "South",
            CASE_600_SOUTH_OPAQUE_M2,
            wall_u,
            wall_nodes,
            azimuth=180.0,
        ),
        opaque(
            "west",
            "West",
            CASE_600_SHORT_WALL_M2,
            wall_u,
            wall_nodes,
            azimuth=270.0,
        ),
        opaque(
            "roof",
            "Roof",
            CASE_600_FLOOR_AREA_M2,
            roof_u,
            roof_nodes,
            inclination=0.0,
            element_type="roof",
        ),
        # The published geometry marks the floor as Outdoors + NoSun + NoWind.
        # It is therefore driven by outdoor air, not by an invented 10°C ground
        # boundary. Solar is explicitly suppressed below. The project schema
        # uses "ground_floor" as the closest semantic element type while the
        # adjacent-space field retains the benchmark's OUTDOOR boundary.
        opaque(
            "floor",
            "Floor",
            CASE_600_FLOOR_AREA_M2,
            floor_u,
            floor_nodes,
            inclination=180.0,
            element_type="ground_floor",
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
            g_value=CASE_600_WINDOW_G_VALUE,
            frame_factor=0.0,
        ),
        TransparentElement(
            id="south-window-2",
            name="South window 2",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=CASE_600_WINDOW_AREA_M2 / 2.0,
            u_value=window_u,
            g_value=CASE_600_WINDOW_G_VALUE,
            frame_factor=0.0,
        ),
    ]

    transparent_solar = sum(
        (solar_gains_transparent(element, climate) for element in transparent),
        np.zeros(8760, dtype=float),
    )
    opaque_solar: dict[str, np.ndarray] = {}
    for element in opaque_elements:
        if element.id == "floor" or element.adjacent_space_type != AdjacentSpaceType.OUTDOOR:
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
        # The ASHRAE 140-2007 simplified reference translation uses the
        # altitude-adjusted 0.414 h⁻¹ value for the Denver test weather.
        h_ve=0.414 * 129.6 * 1200.0 / 3600.0,
        t_e=climate["T_e"].to_numpy(dtype=float),
        phi_int=np.full(8760, 200.0),
        phi_sol_transparent=np.asarray(transparent_solar, dtype=float),
        opaque_solar_absorbed_w_by_element=opaque_solar,
        t_set_heating=20.0,
        t_set_cooling=27.0,
        internal_convective_fraction=0.4,
        require_explicit_construction_nodes=True,
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
