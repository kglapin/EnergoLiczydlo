"""Focused regression tests for the hourly normative calculation path.

These tests are deliberately independent of the live TMY file.  Where the
high-level calculator is exercised, the climate loader is replaced with a
synthetic 8760-hour year so the expected result is analytical and repeatable.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.engine.calculator import _generation_efficiency, calculate_building_energy
from app.engine.climate import make_synthetic_year
from app.engine.envelope import zone_transmission_network
from app.engine.internal_gains import (
    normative_internal_gain_w_m2,
    normative_internal_gains,
    total_internal_gains,
)
from app.engine.systems import (
    heating_auxiliary_demand_wh,
    storage_unit_loss_w_dm3,
)
from app.engine.thermal_balance import (
    TransmissionNetwork,
    solve_zone_5r1c,
    zone_thermal_properties,
)
from app.engine.ventilation import normative_infiltration_rate
from app.schemas.models import (
    BuildingSystems,
    InternalGainSource,
    LinearThermalBridge,
    OpaqueElement,
    PrimaryEnergyFactors,
    SystemDHW,
    SystemHeatingCooling,
    ThermalBridgeConfig,
    ThermalZone,
    Ventilation,
    ZoneType,
)
from scripts.test_building import make_test_project


def test_source_catalogue_fallback_is_not_masked_by_legacy_cop_default():
    """A new gas/cooling system must not inherit the legacy value 3.0."""
    assert _generation_efficiency(
        SystemHeatingCooling(system_type="gas_boiler")
    ) == pytest.approx(0.87)
    assert _generation_efficiency(
        SystemHeatingCooling(system_type="split_ac")
    ) == pytest.approx(3.9)

    legacy = SystemHeatingCooling(
        system_type="gas_boiler",
        efficiency_or_cop_map={"constant": True, "value": 0.91},
    )
    assert _generation_efficiency(legacy) == pytest.approx(0.91)


def test_current_primary_energy_default_is_2023_electricity_factor():
    assert PrimaryEnergyFactors().electricity.fp == pytest.approx(2.5)


@pytest.mark.parametrize(
    ("construction_year", "expected"), [(1995, 0.3), (1996, 0.2), (2020, 0.2)]
)
def test_default_infiltration_matches_methodology_year_rule(construction_year, expected):
    assert normative_infiltration_rate(construction_year) == pytest.approx(expected)


def test_calculator_applies_year_rule_only_when_infiltration_was_omitted(monkeypatch):
    climate = make_synthetic_year(T_e=0.0, GHI=0.0, DNI=0.0, DHI=0.0)
    monkeypatch.setattr("app.engine.calculator._load_climate", lambda project: climate)

    omitted = make_test_project()
    omitted.general.construction_year = 1980
    omitted.ventilation = Ventilation(
        ventilation_type="natural", airflow_rate=120.0, fan_infiltration_rate=0.0
    )
    explicit = omitted.model_copy(deep=True)
    explicit.ventilation = omitted.ventilation.model_copy(
        update={"infiltration_rate": 0.3}
    )

    omitted_result = calculate_building_energy(omitted)
    explicit_result = calculate_building_energy(explicit)
    assert omitted_result.annual_indicators.eu_kwh_m2_year == pytest.approx(
        explicit_result.annual_indicators.eu_kwh_m2_year
    )


def test_source_defaults_infer_their_energy_carrier():
    assert SystemHeatingCooling(system_type="gas_boiler").fuel_or_carrier == "natural_gas"
    assert SystemHeatingCooling(system_type="biomass_boiler").fuel_or_carrier == "biomass"
    assert SystemDHW(system_type="gas_instantaneous").fuel_or_carrier == "natural_gas"


def test_hourly_thermal_need_is_converted_with_seasonal_heat_pump_cop(monkeypatch):
    climate = make_synthetic_year(T_e=0.0, GHI=0.0, DNI=0.0, DHI=0.0)
    monkeypatch.setattr("app.engine.calculator._load_climate", lambda project: climate)
    project = make_test_project()
    project.systems.heating = SystemHeatingCooling(
        system_type="heat_pump_air",
        generation_efficiency=3.5,
        distribution_efficiency=1.0,
        storage_efficiency=1.0,
        control_efficiency=1.0,
    )
    project.systems.dhw = SystemDHW(system_type="none")
    result = calculate_building_energy(project)
    assert result.annual_indicators.eu_kwh_m2_year > 0.0
    assert result.annual_indicators.ek_kwh_m2_year == pytest.approx(
        result.annual_indicators.eu_kwh_m2_year / 3.5
    )


def test_explicit_energy_carrier_is_not_overwritten_by_source_default():
    system = SystemHeatingCooling(
        system_type="gas_boiler", fuel_or_carrier="biomass"
    )
    assert system.fuel_or_carrier == "biomass"


@pytest.mark.parametrize(
    ("beta", "expected"),
    [(0.0, 1.6), (0.3, 5.68), (1.0, 15.2)],
)
def test_normative_office_internal_gain_density_matches_table_26(beta, expected):
    assert normative_internal_gain_w_m2("office", "office", beta) == pytest.approx(expected)


def test_normative_internal_gain_rejects_beta_outside_methodology_range():
    with pytest.raises(ValueError, match="between 0 and 1"):
        normative_internal_gain_w_m2("office", "office", beta=1.01)


def test_generated_normative_internal_gains_do_not_depend_on_zone_occupancy_density():
    gains = normative_internal_gains("office", "office", beta=0.3)
    index = make_synthetic_year().index
    at_default_density = total_internal_gains(0.03, 100.0, gains, index)
    at_different_density = total_internal_gains(0.08, 100.0, gains, index)
    expected = normative_internal_gain_w_m2("office", "office", 0.3) * 100.0
    np.testing.assert_allclose(at_default_density, expected)
    np.testing.assert_allclose(at_different_density, expected)


def test_normative_internal_gain_marker_yields_to_explicit_hourly_schedule():
    gains = normative_internal_gains("office", "office", beta=0.3)
    gains.occupancy = InternalGainSource(
        power_density=gains.occupancy.power_density,
        schedule={"type": "constant", "constant_value": 0.0},
    )
    index = make_synthetic_year().index
    result = total_internal_gains(0.03, 100.0, gains, index)
    expected = (
        gains.lighting.power_density + gains.equipment.power_density
    ) * 100.0
    np.testing.assert_allclose(result, expected)


@pytest.mark.parametrize("bad_insulation", [10.0, 80.0, 120.0])
def test_storage_table_does_not_silently_round_unsupported_insulation(bad_insulation):
    with pytest.raises(ValueError, match="20, 50 or 100"):
        storage_unit_loss_w_dm3(100.0, "unheated", "indirect", bad_insulation)


def test_storage_table_rejects_unknown_location_and_tank_kind():
    with pytest.raises(ValueError, match="storage location"):
        storage_unit_loss_w_dm3(100.0, "basement", "electric")
    with pytest.raises(ValueError, match="tank_kind"):
        storage_unit_loss_w_dm3(100.0, "heated", "unknown")


def test_storage_table_requires_insulation_for_indirect_tank():
    with pytest.raises(ValueError, match="insulation_mm is required"):
        storage_unit_loss_w_dm3(100.0, "unheated", "indirect")


def test_dhw_model_requires_storage_location_when_volume_is_supplied():
    with pytest.raises(ValueError, match="storage_location is required"):
        SystemDHW(system_type="electric_storage", storage_volume_dm3=100.0)


def test_dhw_model_requires_insulation_for_indirect_storage():
    with pytest.raises(ValueError, match="storage_insulation_mm is required"):
        SystemDHW(
            system_type="heat_pump_air",
            storage_volume_dm3=100.0,
            storage_location="heated",
        )


def test_heating_auxiliary_includes_hydronic_radiator_pump_when_classified():
    source_aux = 0.50 * 2520.0 * 150.0
    pump_aux = 0.30 * 5700.0 * 150.0
    assert heating_auxiliary_demand_wh("gas_boiler", 150.0) == pytest.approx(source_aux)
    assert heating_auxiliary_demand_wh(
        "gas_boiler", 150.0, installation_type="water_radiators"
    ) == pytest.approx(source_aux + pump_aux)


def test_heating_auxiliary_uses_table_20_underfloor_pump_row():
    assert heating_auxiliary_demand_wh(
        "electric_direct", 150.0, installation_type="water_surface"
    ) == pytest.approx(0.50 * 6700.0 * 150.0)


def test_hourly_solver_accepts_variable_ventilation_coefficient_and_preserves_setpoint():
    hours = 24
    h_ve = np.arange(1.0, hours + 1.0)
    solution = solve_zone_5r1c(
        network=TransmissionNetwork(),
        h_ve=h_ve,
        t_e=np.zeros(hours),
        phi_int=np.zeros(hours),
        phi_sol=np.zeros(hours),
        properties=zone_thermal_properties(100.0),
        t_set_heating=20.0,
        t_set_cooling=None,
    )
    np.testing.assert_allclose(solution.t_air, 20.0, atol=1e-9)
    np.testing.assert_allclose(solution.q_heating, 20.0 * h_ve)
    assert solution.q_cooling.sum() == pytest.approx(0.0)


def test_transmission_network_includes_linear_and_point_bridges_once():
    zone = ThermalZone(id="z1", name="z1", floor_area=100.0, volume=250.0)
    wall = OpaqueElement(
        id="wall", name="wall", zone_id="z1", area=20.0, u_value=0.2
    )
    bridges = ThermalBridgeConfig(
        linear_bridges=[
            LinearThermalBridge(
                id="lb", name="lb", zone_id="z1", psi_value=0.05, length=10.0
            )
        ],
        point_bridges=[],
    )
    network = zone_transmission_network(
        [wall], [], bridges, np.zeros(8760), zone_id=zone.id
    )
    assert network.h_opaque == pytest.approx(20.0 * 0.2 + 0.05 * 10.0)


def test_cooling_auxiliary_changes_final_and_primary_energy_but_not_useful_energy(monkeypatch):
    climate = make_synthetic_year(T_e=30.0, GHI=0.0, DNI=0.0, DHI=0.0)
    monkeypatch.setattr("app.engine.calculator._load_climate", lambda project: climate)

    project = make_test_project()
    project.thermal_zones[0].zone_type = ZoneType.HEATED_AND_COOLED
    project.systems.heating = SystemHeatingCooling(system_type="none")
    project.systems.dhw = SystemDHW(system_type="none")
    project.systems.cooling = SystemHeatingCooling(
        system_type="split_ac",
        fuel_or_carrier="electricity",
        generation_efficiency=4.0,
        distribution_efficiency=0.9,
        storage_efficiency=0.95,
        control_efficiency=0.9,
    )
    project.internal_gains = project.internal_gains.model_copy(
        update={
            "occupancy": InternalGainSource(power_density=0.0),
            "lighting": InternalGainSource(power_density=0.0),
            "equipment": InternalGainSource(power_density=0.0),
            "normative_power_density_w_m2": None,
        }
    )

    baseline = calculate_building_energy(project)
    project.systems.cooling.auxiliary_energy_kwh_year = 100.0
    with_auxiliary = calculate_building_energy(project)

    assert baseline.annual_indicators.cooling_kwh_m2_year > 0.0
    assert with_auxiliary.annual_indicators.eu_kwh_m2_year == pytest.approx(
        baseline.annual_indicators.eu_kwh_m2_year
    )
    assert with_auxiliary.annual_indicators.ek_kwh_m2_year == pytest.approx(
        baseline.annual_indicators.ek_kwh_m2_year + 100.0 / 150.0
    )
    assert with_auxiliary.annual_indicators.ep_kwh_m2_year == pytest.approx(
        baseline.annual_indicators.ep_kwh_m2_year + 2.5 * 100.0 / 150.0
    )


def test_monthly_hourly_closure_for_cooling_and_useful_energy(monkeypatch):
    climate = make_synthetic_year(T_e=30.0, GHI=0.0, DNI=0.0, DHI=0.0)
    monkeypatch.setattr("app.engine.calculator._load_climate", lambda project: climate)
    project = make_test_project()
    project.thermal_zones[0].zone_type = ZoneType.HEATED_AND_COOLED
    project.systems.heating = SystemHeatingCooling(system_type="none")
    project.systems.dhw = SystemDHW(system_type="none")
    project.systems.cooling = SystemHeatingCooling(
        system_type="split_ac", generation_efficiency=4.0,
        distribution_efficiency=1.0, storage_efficiency=1.0, control_efficiency=1.0,
    )
    project.internal_gains = project.internal_gains.model_copy(
        update={
            "occupancy": InternalGainSource(power_density=0.0),
            "lighting": InternalGainSource(power_density=0.0),
            "equipment": InternalGainSource(power_density=0.0),
            "normative_power_density_w_m2": None,
        }
    )
    result = calculate_building_energy(project)
    hourly_cooling = np.asarray(result.hourly["Q_C"], dtype=float)
    monthly_cooling_wh = sum(month.cooling_kwh for month in result.monthly) * 1000.0
    assert hourly_cooling.shape == (8760,)
    assert monthly_cooling_wh == pytest.approx(hourly_cooling.sum(), rel=1e-10)
    assert result.annual_indicators.eu_kwh_m2_year == pytest.approx(
        hourly_cooling.sum() / 1000.0 / 150.0, rel=1e-10
    )


def test_building_system_validation_keeps_heating_and_cooling_catalogues_separate():
    with pytest.raises(ValueError, match="Invalid heating system source"):
        BuildingSystems(heating={"system_type": "split_ac"})
    with pytest.raises(ValueError, match="Invalid cooling system source"):
        BuildingSystems(
            heating={"system_type": "electric_direct"},
            cooling={"system_type": "gas_boiler"},
        )
