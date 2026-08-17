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

# The published altitude adjustment represents the nominal 0.5 ACH at the
# Denver test location as 0.414 h⁻¹. Use the same implied air density for the
# explicit room-air capacitance rather than a generic furniture-capacity proxy.
CASE_600_AIR_DENSITY_KG_M3 = (0.414 / 0.5) * 1.2
CASE_600_AIR_CP_J_KG_K = 1006.0
CASE_600_AIR_HEAT_CAPACITY_J_K = (
    CASE_600_VOLUME_M3 * CASE_600_AIR_DENSITY_KG_M3 * CASE_600_AIR_CP_J_KG_K
)

CASE_600_WINDOW_U_VALUE = 3.0
CASE_600_WINDOW_G_VALUE = 0.789
CASE_600_DIRECT_IAM = (1.0, -0.189, 0.644, -0.596)
CASE_600_WINDOW_CORE_R_M2K_W = 2.0 * 0.003175 / 1.06 + 0.1588

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


def _five_node_material(
    layers_outside_to_inside: Sequence[Layer],
) -> tuple[list[float], list[float], tuple[float, float]]:
    """Map layers to five capacitive nodes plus two explicit surface half-cells.

    Returns capacities [kJ/(m² K)], four centre-to-centre resistances and the
    exterior/interior surface-to-nearest-node half-cell resistances. Surface
    films are intentionally absent: the dynamic solver calculates them from the
    hourly surface state and weather.
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
        capacities.append(max(capacity, 1e-9))

    core_resistances = [bin_r] * 4
    boundary_halves = (0.5 * bin_r, 0.5 * bin_r)
    return capacities, core_resistances, boundary_halves


def _black_sky_temperature_c(climate) -> np.ndarray:
    """Convert EPW horizontal infrared intensity to effective black-sky temperature."""
    if "ghi_infrared" not in climate.columns:
        raise ValueError("BESTEST EPW must contain horizontal infrared radiation intensity")
    sigma = 5.670374419e-8
    infrared = np.asarray(climate["ghi_infrared"], dtype=float)
    if np.any(infrared <= 0.0):
        raise ValueError("BESTEST horizontal infrared radiation must be positive")
    return np.power(infrared / sigma, 0.25) - 273.15


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

    wall_cap, wall_core_r, wall_boundary_r = _five_node_material(WALL_LAYERS_OUTSIDE_TO_INSIDE)
    roof_cap, roof_core_r, roof_boundary_r = _five_node_material(ROOF_LAYERS_OUTSIDE_TO_INSIDE)
    floor_cap, floor_core_r, floor_boundary_r = _five_node_material(
        FLOOR_LAYERS_OUTSIDE_TO_INSIDE
    )

    # Nominal U-values are retained only as project metadata. The dynamic path
    # below uses the verified material R/C plus hourly surface transfer directly.
    wall_u = 1.0 / (sum(wall_core_r) + sum(wall_boundary_r) + 0.13 + 0.04)
    roof_u = 1.0 / (sum(roof_core_r) + sum(roof_boundary_r) + 0.10 + 0.04)
    floor_u = 1.0 / (sum(floor_core_r) + sum(floor_boundary_r) + 0.17 + 0.04)

    def opaque(
        element_id: str,
        name: str,
        area: float,
        u_value: float,
        capacities: list[float],
        core_resistances: list[float],
        *,
        azimuth: float = 0.0,
        inclination: float = 90.0,
        element_type: str = "external_wall",
        absorptance: float = 0.6,
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
            solar_absorptance=absorptance,
            thermal_node_capacities_kj_m2k=capacities,
            thermal_node_resistances_m2k_w=core_resistances,
        )

    opaque_elements = [
        opaque(
            "east",
            "East",
            CASE_600_SHORT_WALL_M2,
            wall_u,
            wall_cap,
            wall_core_r,
            azimuth=90.0,
        ),
        opaque(
            "north",
            "North",
            CASE_600_LONG_WALL_M2,
            wall_u,
            wall_cap,
            wall_core_r,
            azimuth=0.0,
        ),
        opaque(
            "south",
            "South",
            CASE_600_SOUTH_OPAQUE_M2,
            wall_u,
            wall_cap,
            wall_core_r,
            azimuth=180.0,
        ),
        opaque(
            "west",
            "West",
            CASE_600_SHORT_WALL_M2,
            wall_u,
            wall_cap,
            wall_core_r,
            azimuth=270.0,
        ),
        opaque(
            "roof",
            "Roof",
            CASE_600_FLOOR_AREA_M2,
            roof_u,
            roof_cap,
            roof_core_r,
            inclination=0.0,
            element_type="roof",
        ),
        # Case 600 uses a raised floor: outside thermal boundary, no direct
        # solar on the underside and no wind-driven exterior convection there.
        opaque(
            "floor",
            "Raised floor",
            CASE_600_FLOOR_AREA_M2,
            floor_u,
            floor_cap,
            floor_core_r,
            inclination=180.0,
            element_type="ground_floor",
            absorptance=0.0,
        ),
    ]

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

    boundary_resistances = {
        "east": wall_boundary_r,
        "north": wall_boundary_r,
        "south": wall_boundary_r,
        "west": wall_boundary_r,
        "roof": roof_boundary_r,
        "floor": floor_boundary_r,
    }
    window_core = {
        "south-window-1": CASE_600_WINDOW_CORE_R_M2K_W,
        "south-window-2": CASE_600_WINDOW_CORE_R_M2K_W,
    }

    solution = solve_zone_iso52016_dynamic_surfaces(
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
        wind_speed_m_s=climate["v_wind"].to_numpy(dtype=float),
        wind_direction_deg=climate["dir_wind"].to_numpy(dtype=float),
        sky_temperature_c=_black_sky_temperature_c(climate),
        opaque_boundary_resistances_m2k_w=boundary_resistances,
        window_core_resistances_m2k_w=window_core,
        air_heat_capacity_j_k=CASE_600_AIR_HEAT_CAPACITY_J_K,
        internal_convective_fraction=0.4,
        solar_convective_fraction=0.0,
        hvac_convective_fraction=1.0,
        operative_air_weight=1.0,
        wind_exposed_by_element={"floor": False},
        roughness_by_element={
            "east": "rough",
            "north": "rough",
            "south": "rough",
            "west": "rough",
            "roof": "rough",
            "floor": "rough",
            "south-window-1": "very_smooth",
            "south-window-2": "very_smooth",
        },
        emissivity_by_element={
            "east": 0.9,
            "north": 0.9,
            "south": 0.9,
            "west": 0.9,
            "roof": 0.9,
            "floor": 0.9,
            "south-window-1": 0.84,
            "south-window-2": 0.84,
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
