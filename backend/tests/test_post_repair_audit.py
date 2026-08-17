"""Independent post-repair audit of the hourly and Polish monthly engines.

Every audit category from the 2026-08-17 review has at least one executable
assertion here. The manual tests deliberately use small inputs whose expected
result can be calculated without another simulation program.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.engine.design_load import calculate_design_heat_load
from app.engine.envelope import (
    compute_opaque_heat_loss,
    compute_thermal_bridge_loss,
    compute_transparent_heat_loss,
)
from app.engine.ground_iso13370 import (
    characteristic_dimension_m,
    equivalent_thickness_m,
    slab_on_ground_u_value_w_m2k,
)
from app.engine.heat_recovery import attach_heat_recovery_settings, heat_recovery_state
from app.engine.internal_gains import (
    evaluate_schedule,
    internal_gains,
    normative_internal_gain_w_m2,
    total_internal_gains,
)
from app.engine.iso52016_hourly import solve_zone_iso52016
from app.engine.normative_models import (
    DesignConditionsSettings,
    HeatRecoverySettings,
    PolishCertificateMonthlySettings,
)
from app.engine.polish_certificate_monthly import calculate_polish_monthly_certificate
from app.engine.solar import solar_gains_transparent
from app.engine.ventilation import (
    ventilation_effective_supply_temperature,
    ventilation_heat_loss,
    ventilation_heat_transfer_coefficient,
)
from app.schemas.models import (
    DesignRoom,
    InternalGainSource,
    InternalGains,
    LinearThermalBridge,
    OpaqueElement,
    PointThermalBridge,
    Schedule,
    ThermalBridgeConfig,
    ThermalZone,
    TransparentElement,
    Ventilation,
)
from scripts.test_building import make_test_project


def _index(hours: int) -> pd.DatetimeIndex:
    return pd.date_range("2023-01-01", periods=hours, freq="h")


def _explicit_wall(
    *,
    area: float = 25.0,
    u_value: float = 1.0,
    element_id: str = "wall",
) -> OpaqueElement:
    # R total = 1/U = 1.0 m²K/W; capacities total 200 kJ/(m²K).
    return OpaqueElement(
        id=element_id,
        name=element_id,
        zone_id="z1",
        area=area,
        u_value=u_value,
        solar_absorptance=0.0,
        thermal_node_capacities_kj_m2k=[40.0] * 5,
        thermal_node_resistances_m2k_w=[0.13, 0.2075, 0.2075, 0.2075, 0.2075, 0.04],
    )


def _monthly_reference_project():
    project = make_test_project()
    zone = project.thermal_zones[0]
    zone.id = "z1"
    zone.name = "Reference"
    zone.floor_area = 100.0
    zone.volume = 250.0
    zone.occupancy_density = 0.0
    zone.setpoint_heating = 20.0
    zone.setpoint_cooling = None
    project.general.conditioned_floor_area = 100.0
    project.general.usable_floor_area = 100.0
    project.general.heated_volume = 250.0
    project.opaque_building_elements = [
        OpaqueElement(
            id="wall",
            name="Wall",
            zone_id="z1",
            area=25.0,
            u_value=1.0,
            solar_absorptance=0.0,
        )
    ]
    project.transparent_building_elements = []
    project.thermal_bridges = ThermalBridgeConfig()
    project.ventilation = Ventilation(
        ventilation_type="none",
        airflow_rate=0.0,
        infiltration_rate=0.0,
        fan_infiltration_rate=0.0,
    )
    project.internal_gains = InternalGains(
        occupancy=InternalGainSource(power_density=0.0),
        lighting=InternalGainSource(power_density=0.0),
        equipment=InternalGainSource(power_density=0.0),
        normative_power_density_w_m2=0.0,
    )
    project.systems.cooling = None
    project.systems.dhw.system_type = "none"
    return project


# ---------------------------------------------------------------------------
# CATEGORY 1 + CATEGORY 2: normative mapping and >=15 hand-calculated checks
# ---------------------------------------------------------------------------


def test_manual_01_opaque_transmission_25m2_u1_dt20_is_500w() -> None:
    element = OpaqueElement(id="w", name="w", zone_id="z", area=25.0, u_value=1.0)
    actual = compute_opaque_heat_loss(element, np.array([20.0]), np.array([0.0]))
    assert actual[0] == pytest.approx(500.0)


def test_manual_02_transparent_transmission_5m2_u2_dt20_is_200w() -> None:
    element = TransparentElement(
        id="win",
        name="win",
        zone_id="z",
        area=5.0,
        u_value=2.0,
        g_value=0.5,
    )
    actual = compute_transparent_heat_loss(element, np.array([20.0]), np.array([0.0]))
    assert actual[0] == pytest.approx(200.0)


def test_manual_03_thermal_bridges_are_60w() -> None:
    zone = ThermalZone(id="z", name="z", floor_area=25.0, volume=125.0)
    bridges = ThermalBridgeConfig(
        linear_bridges=[
            LinearThermalBridge(
                id="lb",
                name="lb",
                psi_value=0.1,
                length=10.0,
                zone_id="z",
            )
        ],
        point_bridges=[
            PointThermalBridge(
                id="pb",
                name="pb",
                chi_value=0.5,
                count=4,
                zone_id="z",
            )
        ],
    )
    actual = compute_thermal_bridge_loss(
        bridges,
        zone,
        np.array([20.0]),
        np.array([0.0]),
    )
    # 0.1*10*20 + 0.5*4*20 = 20 + 40 = 60 W.
    assert actual[0] == pytest.approx(60.0)


def test_manual_04_ventilation_360m3h_has_hve_120w_per_k() -> None:
    zone = ThermalZone(id="z", name="z", floor_area=100.0, volume=250.0)
    ventilation = Ventilation(
        ventilation_type="mechanical",
        airflow_rate=360.0,
        infiltration_rate=0.0,
        fan_infiltration_rate=0.0,
    )
    h_ve = ventilation_heat_transfer_coefficient(ventilation, zone, 100.0)
    assert float(h_ve) == pytest.approx(360.0 / 3600.0 * 1200.0)


def test_manual_05_ventilation_loss_360m3h_dt20_is_2400w() -> None:
    zone = ThermalZone(id="z", name="z", floor_area=100.0, volume=250.0)
    ventilation = Ventilation(
        ventilation_type="mechanical",
        airflow_rate=360.0,
        infiltration_rate=0.0,
        fan_infiltration_rate=0.0,
    )
    loss = ventilation_heat_loss(
        ventilation,
        zone,
        np.array([20.0]),
        np.array([0.0]),
        building_floor_area=100.0,
    )
    assert loss[0] == pytest.approx(2400.0)


def test_manual_06_horizontal_transparent_solar_gain_is_1200w() -> None:
    frame = pd.DataFrame(
        {
            "GHI": [600.0],
            "DNI": [1000.0],
            "DHI": [100.0],
            "sun_zenith": [60.0],
            "sun_azimuth": [180.0],
        },
        index=_index(1),
    )
    element = TransparentElement(
        id="win",
        name="win",
        zone_id="z",
        area=10.0,
        u_value=1.0,
        g_value=0.5,
        frame_factor=0.2,
        shading_factor=0.5,
        inclination=0.0,
    )
    gain = solar_gains_transparent(element, frame)
    # I = 1000*cos60 + 100 = 600; Aglass=8; g*shade=.25.
    assert gain[0] == pytest.approx(1200.0)


def test_manual_07_full_shading_makes_solar_gain_zero() -> None:
    frame = pd.DataFrame(
        {
            "GHI": [600.0],
            "DNI": [1000.0],
            "DHI": [100.0],
            "sun_zenith": [60.0],
            "sun_azimuth": [180.0],
        },
        index=_index(1),
    )
    element = TransparentElement(
        id="win",
        name="win",
        zone_id="z",
        area=10.0,
        u_value=1.0,
        g_value=0.5,
        frame_factor=0.2,
        shading_factor=0.0,
        inclination=0.0,
    )
    assert solar_gains_transparent(element, frame)[0] == pytest.approx(0.0)


def test_manual_08_residential_normative_internal_gain_is_6_8wm2() -> None:
    assert normative_internal_gain_w_m2(
        "residential",
        "residential_single_family",
    ) == pytest.approx(6.8)


def test_manual_09_constant_schedule_quarter_is_quarter() -> None:
    schedule = Schedule(type="constant", constant_value=0.25)
    result = evaluate_schedule(schedule, _index(3))
    assert result == pytest.approx([0.25, 0.25, 0.25])


def test_manual_10_occupancy_internal_gain_is_80w() -> None:
    source = InternalGainSource(power_density=80.0)
    gain = internal_gains(0.02, 50.0, source, _index(1), per_person=True)
    assert gain[0] == pytest.approx(80.0)


def test_manual_11_area_internal_gain_is_100w() -> None:
    source = InternalGainSource(power_density=2.0)
    gain = internal_gains(0.0, 50.0, source, _index(1), per_person=False)
    assert gain[0] == pytest.approx(100.0)


def test_manual_12_total_internal_gain_is_330w() -> None:
    gains = InternalGains(
        occupancy=InternalGainSource(power_density=80.0),
        lighting=InternalGainSource(power_density=2.0),
        equipment=InternalGainSource(power_density=3.0),
        normative_power_density_w_m2=None,
    )
    actual = total_internal_gains(0.02, 50.0, gains, _index(1))
    assert actual[0] == pytest.approx(80.0 + 100.0 + 150.0)


def test_manual_13_ground_characteristic_dimension_is_2_5m() -> None:
    assert characteristic_dimension_m(25.0, 20.0) == pytest.approx(2.5)


def test_manual_14_ground_equivalent_thickness_includes_both_surface_terms() -> None:
    actual = equivalent_thickness_m(2.0, 2.0, 0.3)
    assert actual == pytest.approx(0.3 + 2.0 * (0.17 + 2.0 + 0.04))


def test_manual_15_ground_u_value_matches_correct_formula_branch() -> None:
    area = 25.0
    perimeter = 20.0
    conductivity = 2.0
    resistance = 2.0
    thickness = 0.3
    b_prime = 2.0 * area / perimeter
    d_t = 0.3 + 2.0 * (0.17 + 2.0 + 0.04)
    expected = conductivity / (0.457 * b_prime + d_t)
    assert d_t >= b_prime
    assert slab_on_ground_u_value_w_m2k(
        area,
        perimeter,
        conductivity,
        resistance,
        thickness,
    ) == pytest.approx(expected)


def test_manual_16_room_design_load_one_wall_is_1000w() -> None:
    project = make_test_project()
    project.thermal_zones[0].id = "z1"
    project.thermal_zones[0].floor_area = 150.0
    project.thermal_zones[0].volume = 375.0
    project.opaque_building_elements = [
        OpaqueElement(id="wall", name="wall", zone_id="z1", area=25.0, u_value=1.0)
    ]
    project.transparent_building_elements = []
    project.thermal_bridges = ThermalBridgeConfig()
    project.ventilation = Ventilation(
        ventilation_type="none",
        airflow_rate=0.0,
        infiltration_rate=0.0,
    )
    project.design_rooms = [
        DesignRoom(
            id="room",
            name="room",
            zone_id="z1",
            floor_area=150.0,
            volume=375.0,
            design_temperature_c=20.0,
            opaque_element_ids=["wall"],
        )
    ]
    result = calculate_design_heat_load(
        project,
        DesignConditionsSettings(
            enabled=True,
            certificate_mode=True,
            outdoor_design_temperature_c=-20.0,
            source="manual audit condition",
        ),
        annual_mean_outdoor_c=8.0,
    )
    assert result.total_w == pytest.approx(25.0 * 1.0 * 40.0)


def test_manual_17_monthly_january_transmission_is_372kwh() -> None:
    project = _monthly_reference_project()
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[0.0] * 12,
        heating_internal_temperature_c_by_zone={"z1": [20.0] * 12},
        heating_gain_utilization_by_zone={"z1": [1.0] * 12},
        internal_gain_density_w_m2_by_zone={"z1": 0.0},
    )
    result = calculate_polish_monthly_certificate(project, settings)
    assert result.monthly[0].heating_kwh == pytest.approx(
        25.0 * 1.0 * 20.0 * 31.0 * 24.0 / 1000.0
    )


# ---------------------------------------------------------------------------
# CATEGORY 3: edge cases
# ---------------------------------------------------------------------------


def test_edge_zero_ventilation_and_zero_gains_are_finite() -> None:
    solution = solve_zone_iso52016(
        opaque_elements=[_explicit_wall()],
        transparent_elements=[],
        bridges=ThermalBridgeConfig(),
        zone_id="z1",
        h_ve=0.0,
        t_e=np.zeros(24),
        phi_int=np.zeros(24),
        phi_sol_transparent=np.zeros(24),
        opaque_solar_absorbed_w_by_element={"wall": np.zeros(24)},
        t_set_heating=20.0,
        t_set_cooling=None,
        require_explicit_construction_nodes=True,
    )
    assert np.isfinite(solution.t_air).all()
    assert np.isfinite(solution.q_heating).all()
    assert np.all(solution.q_heating >= 0.0)


def test_edge_negative_ventilation_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        solve_zone_iso52016(
            opaque_elements=[_explicit_wall()],
            transparent_elements=[],
            bridges=ThermalBridgeConfig(),
            zone_id="z1",
            h_ve=-1.0,
            t_e=np.zeros(1),
            phi_int=np.zeros(1),
            phi_sol_transparent=np.zeros(1),
            opaque_solar_absorbed_w_by_element={"wall": np.zeros(1)},
            t_set_heating=20.0,
            t_set_cooling=None,
            require_explicit_construction_nodes=True,
        )


# ---------------------------------------------------------------------------
# CATEGORY 4: hour-by-hour and 3-day energy balance
# ---------------------------------------------------------------------------


def test_three_day_new_solver_energy_balance_closes_hour_by_hour() -> None:
    wall = _explicit_wall()
    outdoor = np.concatenate(
        [np.full(24, -10.0), np.full(24, 10.0), np.full(24, 32.0)]
    )
    h_ve = np.full(72, 60.0)
    phi_int = np.full(72, 200.0)
    solution = solve_zone_iso52016(
        opaque_elements=[wall],
        transparent_elements=[],
        bridges=ThermalBridgeConfig(),
        zone_id="z1",
        h_ve=h_ve,
        t_e=outdoor,
        t_supply=outdoor,
        phi_int=phi_int,
        phi_sol_transparent=np.zeros(72),
        opaque_solar_absorbed_w_by_element={"wall": np.zeros(72)},
        t_set_heating=20.0,
        t_set_cooling=26.0,
        require_explicit_construction_nodes=True,
    )
    capacities = np.asarray([40.0] * 5) * 25.0 * 1000.0
    nodes = solution.construction_node_temperatures["wall"]
    previous = np.vstack([np.full((1, 5), 20.0), nodes[:-1]])
    storage_w = np.sum(capacities * (nodes - previous), axis=1) / 3600.0
    ventilation_loss = h_ve * (solution.t_air - outdoor)
    hvac = solution.q_heating - solution.q_cooling
    residual = storage_w - (
        phi_int + hvac - solution.q_transmission - ventilation_loss
    )
    day_max = {
        "winter": float(np.max(np.abs(residual[:24]))),
        "transition": float(np.max(np.abs(residual[24:48]))),
        "summer": float(np.max(np.abs(residual[48:]))),
    }
    print("POST_REPAIR_3DAY_BALANCE_W=", day_max)
    assert max(day_max.values()) < 1e-7


# ---------------------------------------------------------------------------
# CATEGORY 5 + CATEGORY 7: cross-engine validation and unit conversion
# ---------------------------------------------------------------------------


def test_hourly_and_monthly_match_constant_reference_and_units() -> None:
    wall = _explicit_wall()
    hourly = solve_zone_iso52016(
        opaque_elements=[wall],
        transparent_elements=[],
        bridges=ThermalBridgeConfig(),
        zone_id="z1",
        h_ve=0.0,
        t_e=np.zeros(8760),
        phi_int=np.zeros(8760),
        phi_sol_transparent=np.zeros(8760),
        opaque_solar_absorbed_w_by_element={"wall": np.zeros(8760)},
        t_set_heating=20.0,
        t_set_cooling=None,
        require_explicit_construction_nodes=True,
        warmup_tolerance_k=0.001,
    )
    project = _monthly_reference_project()
    monthly = calculate_polish_monthly_certificate(
        project,
        PolishCertificateMonthlySettings(
            enabled=True,
            official_bip_climate_data=True,
            monthly_outdoor_temperature_c=[0.0] * 12,
            heating_internal_temperature_c_by_zone={"z1": [20.0] * 12},
            heating_gain_utilization_by_zone={"z1": [1.0] * 12},
            internal_gain_density_w_m2_by_zone={"z1": 0.0},
        ),
    )
    hourly_kwh = float(hourly.q_heating.sum()) / 1000.0
    expected_kwh = 25.0 * 1.0 * 20.0 * 8760.0 / 1000.0
    relative = abs(hourly_kwh - monthly.heating_useful_kwh) / expected_kwh
    print(
        "POST_REPAIR_ENGINE_CROSSCHECK=",
        {
            "hourly_kwh": hourly_kwh,
            "monthly_kwh": monthly.heating_useful_kwh,
            "manual_kwh": expected_kwh,
            "relative_difference": relative,
        },
    )
    assert hourly_kwh == pytest.approx(expected_kwh, rel=1e-4)
    assert monthly.heating_useful_kwh == pytest.approx(expected_kwh, rel=1e-12)
    assert relative < 1e-4


def test_unit_conversion_constant_1000w_for_year_is_8760kwh() -> None:
    wall = _explicit_wall(area=50.0)
    hourly = solve_zone_iso52016(
        opaque_elements=[wall],
        transparent_elements=[],
        bridges=ThermalBridgeConfig(),
        zone_id="z1",
        h_ve=0.0,
        t_e=np.zeros(8760),
        phi_int=np.zeros(8760),
        phi_sol_transparent=np.zeros(8760),
        opaque_solar_absorbed_w_by_element={"wall": np.zeros(8760)},
        t_set_heating=20.0,
        t_set_cooling=None,
        require_explicit_construction_nodes=True,
        warmup_tolerance_k=0.001,
    )
    assert float(hourly.q_heating.sum()) / 1000.0 == pytest.approx(8760.0, rel=1e-4)


# ---------------------------------------------------------------------------
# CATEGORY 1 structural mapping + CATEGORY 6 benchmark precondition
# ---------------------------------------------------------------------------


def test_each_opaque_construction_has_its_own_five_nodes() -> None:
    first = _explicit_wall(element_id="w1")
    second = _explicit_wall(element_id="w2")
    solution = solve_zone_iso52016(
        opaque_elements=[first, second],
        transparent_elements=[],
        bridges=ThermalBridgeConfig(),
        zone_id="z1",
        h_ve=0.0,
        t_e=np.zeros(2),
        phi_int=np.zeros(2),
        phi_sol_transparent=np.zeros(2),
        opaque_solar_absorbed_w_by_element={"w1": np.zeros(2), "w2": np.zeros(2)},
        t_set_heating=20.0,
        t_set_cooling=None,
        require_explicit_construction_nodes=True,
    )
    assert set(solution.construction_node_temperatures) == {"w1", "w2"}
    assert solution.construction_node_temperatures["w1"].shape == (2, 5)
    assert solution.construction_node_temperatures["w2"].shape == (2, 5)


# ---------------------------------------------------------------------------
# CATEGORY 8: signs and no double counting of heat recovery
# ---------------------------------------------------------------------------


def test_heat_recovery_is_not_double_counted_and_uses_correct_sign() -> None:
    zone = ThermalZone(
        id="z",
        name="z",
        floor_area=100.0,
        volume=250.0,
        setpoint_heating=20.0,
        setpoint_cooling=26.0,
    )
    ventilation = Ventilation(
        ventilation_type="mechanical_with_recovery",
        airflow_rate=360.0,
        heat_recovery_efficiency=0.8,
        infiltration_rate=0.0,
        fan_infiltration_rate=0.0,
    )
    attach_heat_recovery_settings(ventilation, HeatRecoverySettings(enabled=True))
    h_ve = float(
        ventilation_heat_transfer_coefficient(
            ventilation,
            zone,
            100.0,
            operation_profile=np.ones(1),
        )
    )
    supply = ventilation_effective_supply_temperature(
        ventilation,
        zone,
        np.asarray([0.0]),
        building_floor_area=100.0,
        operation_profile=np.ones(1),
        extract_temperature_c=np.asarray([20.0]),
    )
    loss = ventilation_heat_loss(
        ventilation,
        zone,
        np.asarray([20.0]),
        np.asarray([0.0]),
        T_supply=supply,
        building_floor_area=100.0,
        operation_profile=np.ones(1),
    )
    assert h_ve == pytest.approx(120.0)
    assert supply[0] == pytest.approx(16.0)
    assert loss[0] == pytest.approx(120.0 * (20.0 - 16.0))
    assert loss[0] == pytest.approx(480.0)


def test_cooling_energy_need_is_nonnegative() -> None:
    solution = solve_zone_iso52016(
        opaque_elements=[_explicit_wall()],
        transparent_elements=[],
        bridges=ThermalBridgeConfig(),
        zone_id="z1",
        h_ve=0.0,
        t_e=np.full(24, 35.0),
        phi_int=np.zeros(24),
        phi_sol_transparent=np.zeros(24),
        opaque_solar_absorbed_w_by_element={"wall": np.zeros(24)},
        t_set_heating=None,
        t_set_cooling=26.0,
        require_explicit_construction_nodes=True,
    )
    assert np.all(solution.q_cooling >= 0.0)
    assert float(solution.q_cooling.sum()) > 0.0
