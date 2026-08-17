"""External BESTEST Case 600 validation of the repaired per-construction solver."""

from __future__ import annotations

import os
from collections.abc import Sequence

import numpy as np
import pytest

from app.engine.climate import load_epw, radiation_on_surface
from app.engine.iso52016_hourly import solve_zone_iso52016
from app.engine.solar import solar_gains_transparent
from app.schemas.models import OpaqueElement, ThermalBridgeConfig, TransparentElement
from tests.test_external_bestest import CASE_600_REFERENCE, _download_bestest_weather

Layer = tuple[float, float, float, float]  # thickness, conductivity, cp, density

CASE_600_LENGTH_M = 8.0
CASE_600_WIDTH_M = 6.0
CASE_600_HEIGHT_M = 2.7
CASE_600_WINDOW_AREA_M2 = 12.0
CASE_600_FLOOR_AREA_M2 = CASE_600_LENGTH_M * CASE_600_WIDTH_M
CASE_600_VOLUME_M3 = CASE_600_FLOOR_AREA_M2 * CASE_600_HEIGHT_M
CASE_600_LONG_WALL_M2 = CASE_600_LENGTH_M * CASE_600_HEIGHT_M
CASE_600_SHORT_WALL_M2 = CASE_600_WIDTH_M * CASE_600_HEIGHT_M
CASE_600_SOUTH_OPAQUE_M2 = CASE_600_LONG_WALL_M2 - CASE_600_WINDOW_AREA_M2

# Standard 140 Case 600 uses prescribed combined surface coefficients for the
# lightweight envelope. The floor is a raised/exterior floor; it is not a slab
# coupled to a 2 m soil domain in the benchmark being compared here.
CASE_600_HI_W_M2K = 8.29
CASE_600_HO_W_M2K = 29.3
CASE_600_RSI_M2K_W = 1.0 / CASE_600_HI_W_M2K
CASE_600_RSE_M2K_W = 1.0 / CASE_600_HO_W_M2K

# The published altitude correction converts the nominal 0.5 ACH to 0.414 h⁻¹
# for the Denver weather. Use the same implied density for the explicit room-air
# thermal capacity instead of the generic furniture-capacity fallback.
CASE_600_AIR_DENSITY_KG_M3 = (0.414 / 0.5) * 1.2
CASE_600_AIR_CP_J_KG_K = 1006.0
CASE_600_AIR_HEAT_CAPACITY_J_K = (
    CASE_600_VOLUME_M3 * CASE_600_AIR_DENSITY_KG_M3 * CASE_600_AIR_CP_J_KG_K
)

CASE_600_WINDOW_U_VALUE = 3.0
CASE_600_WINDOW_G_VALUE = 0.789
CASE_600_DIRECT_IAM = (1.0, -0.189, 0.644, -0.596)

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
FLOOR_LAYERS_OUTSIDE_TO_INSIDE: tuple[Layer, ...] = (
    (1.003, 0.040, 0.0, 0.0),
    (0.025, 0.140, 1200.0, 650.0),
)


def _five_node_construction(
    layers_outside_to_inside: Sequence[Layer],
    *,
    r_si: float,
    r_se: float,
) -> tuple[list[float], list[float]]:
    """Map material layers to five finite-volume nodes, preserving total R/C."""
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

    wall_u = 1.0 / (
        0.009 / 0.14
        + 0.066 / 0.04
        + 0.012 / 0.16
        + CASE_600_RSI_M2K_W
        + CASE_600_RSE_M2K_W
    )
    roof_u = 1.0 / (
        0.019 / 0.14
        + 0.1118 / 0.04
        + 0.01 / 0.16
        + CASE_600_RSI_M2K_W
        + CASE_600_RSE_M2K_W
    )
    floor_u = 1.0 / (
        1.003 / 0.04
        + 0.025 / 0.14
        + CASE_600_RSI_M2K_W
        + CASE_600_RSE_M2K_W
    )

    wall_nodes = _five_node_construction(
        WALL_LAYERS_OUTSIDE_TO_INSIDE,
        r_si=CASE_600_RSI_M2K_W,
        r_se=CASE_600_RSE_M2K_W,
    )
    roof_nodes = _five_node_construction(
        ROOF_LAYERS_OUTSIDE_TO_INSIDE,
        r_si=CASE_600_RSI_M2K_W,
        r_se=CASE_600_RSE_M2K_W,
    )
    floor_nodes = _five_node_construction(
        FLOOR_LAYERS_OUTSIDE_TO_INSIDE,
        r_si=CASE_600_RSI_M2K_W,
        r_se=CASE_600_RSE_M2K_W,
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
        absorptance: float = 0.6,
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
            solar_absorptance=absorptance,
            thermal_node_capacities_kj_m2k=capacities,
            thermal_node_resistances_m2k_w=resistances,
            h_ci_w_m2k=CASE_600_HI_W_M2K,
            h_ri_w_m2k=0.0,
            h_ce_w_m2k=CASE_600_HO_W_M2K,
            h_re_w_m2k=0.0,
        )

    opaque_elements = [
        opaque("east", "East", CASE_600_SHORT_WALL_M2, wall_u, wall_nodes, azimuth=90.0),
        opaque("north", "North", CASE_600_LONG_WALL_M2, wall_u, wall_nodes, azimuth=0.0),
        opaque(
            "south",
            "South",
            CASE_600_SOUTH_OPAQUE_M2,
            wall_u,
            wall_nodes,
            azimuth=180.0,
        ),
        opaque("west", "West", CASE_600_SHORT_WALL_M2, wall_u, wall_nodes, azimuth=270.0),
        opaque(
            "roof",
            "Roof",
            CASE_600_FLOOR_AREA_M2,
            roof_u,
            roof_nodes,
            inclination=0.0,
            element_type="roof",
        ),
        # Raised floor: outdoor thermal boundary, but no incident solar on the
        # underside in the benchmark geometry.
        opaque(
            "floor",
            "Raised floor",
            CASE_600_FLOOR_AREA_M2,
            floor_u,
            floor_nodes,
            inclination=180.0,
            element_type="ground_floor",
            absorptance=0.0,
        ),
    ]

    window_core_r = (
        1.0 / CASE_600_WINDOW_U_VALUE - CASE_600_RSI_M2K_W - CASE_600_RSE_M2K_W
    )
    transparent = [
        TransparentElement(
            id="south-window-1",
            name="South window 1",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=CASE_600_WINDOW_AREA_M2 / 2.0,
            u_value=CASE_600_WINDOW_U_VALUE,
            g_value=CASE_600_WINDOW_G_VALUE,
            frame_factor=0.001,
            h_ci_w_m2k=CASE_600_HI_W_M2K,
            h_ri_w_m2k=0.0,
            h_ce_w_m2k=CASE_600_HO_W_M2K,
            h_re_w_m2k=0.0,
            core_thermal_resistance_m2k_w=window_core_r,
        ),
        TransparentElement(
            id="south-window-2",
            name="South window 2",
            zone_id="bestest",
            orientation_azimuth=180.0,
            area=CASE_600_WINDOW_AREA_M2 / 2.0,
            u_value=CASE_600_WINDOW_U_VALUE,
            g_value=CASE_600_WINDOW_G_VALUE,
            frame_factor=0.001,
            h_ci_w_m2k=CASE_600_HI_W_M2K,
            h_ri_w_m2k=0.0,
            h_ce_w_m2k=CASE_600_HO_W_M2K,
            h_re_w_m2k=0.0,
            core_thermal_resistance_m2k_w=window_core_r,
        ),
    ]

    transparent_solar = sum(
        (
            solar_gains_transparent(
                element,
                climate,
                direct_incidence_coefficients=CASE_600_DIRECT_IAM,
            )
            for element in transparent
        ),
        np.zeros(8760, dtype=float),
    )
    opaque_solar: dict[str, np.ndarray] = {}
    for element in opaque_elements:
        if element.id == "floor":
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
        h_ve=0.414 * CASE_600_VOLUME_M3 * 1200.0 / 3600.0,
        t_e=climate["T_e"].to_numpy(dtype=float),
        phi_int=np.full(8760, 200.0),
        phi_sol_transparent=np.asarray(transparent_solar, dtype=float),
        opaque_solar_absorbed_w_by_element=opaque_solar,
        t_set_heating=20.0,
        t_set_cooling=27.0,
        internal_convective_fraction=0.4,
        air_furniture_heat_capacity_j_k=CASE_600_AIR_HEAT_CAPACITY_J_K,
        floor_area_m2=CASE_600_FLOOR_AREA_M2,
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
