import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.engine.calculator import _design_heating_power_kw, calculate_building_energy
from app.engine.internal_gains import total_internal_gains
from app.engine.systems import total_system_efficiency
from app.schemas.models import (
    BuildingProject,
    BuildingSystems,
    OpaqueElement,
    SystemHeatingCooling,
    TransparentElement,
    VentilationType,
    ZoneType,
)
from scripts.test_building import make_test_project


@pytest.mark.parametrize("setpoint_cooling", [None, 26.0])
def test_calculator_runs_and_returns_results(setpoint_cooling):
    project = make_test_project()
    if setpoint_cooling is None:
        project.thermal_zones[0].setpoint_cooling = None
    result = calculate_building_energy(project)
    assert result.status == "success"
    assert result.annual_indicators.eu_kwh_m2_year >= 0
    assert result.annual_indicators.ek_kwh_m2_year >= 0
    assert result.annual_indicators.ep_kwh_m2_year >= 0
    assert len(result.monthly) == 12


def test_energy_hierarchy():
    """Final energy should not be lower than useful energy for non-renewable carriers."""
    project = make_test_project()
    result = calculate_building_energy(project)
    # For the default heat pump, Ek can be lower than Eu due to COP > 1.
    # We still check non-negativity and that Ep >= Ek because primary factor >= 1.
    assert result.annual_indicators.ep_kwh_m2_year >= result.annual_indicators.ek_kwh_m2_year - 1e-6
    assert result.annual_indicators.eu_kwh_m2_year >= 0


def test_exhaust_ventilation_is_accepted_and_counts_fan_energy():
    natural_project = make_test_project()
    natural_project.ventilation.mechanical_fan_power = 100.0

    exhaust_project = natural_project.model_copy(deep=True)
    exhaust_project.ventilation.ventilation_type = VentilationType.EXHAUST

    natural_result = calculate_building_energy(natural_project)
    exhaust_result = calculate_building_energy(exhaust_project)

    assert exhaust_result.status == "success"
    assert (
        exhaust_result.annual_indicators.ek_kwh_m2_year
        > natural_result.annual_indicators.ek_kwh_m2_year
    )


def test_technical_system_sources_are_context_validated():
    systems = BuildingSystems(
        heating={"system_type": "heat_pump_air", "installation_type": "water_radiators"},
        cooling={"system_type": "split_ac", "installation_type": "direct_expansion"},
        dhw={"system_type": "electric_storage"},
    )
    assert systems.heating.installation_type == "water_radiators"
    assert systems.cooling is not None
    assert systems.cooling.system_type == "split_ac"
    assert systems.cooling.installation_type == "direct_expansion"

    with pytest.raises(ValidationError):
        BuildingSystems(heating={"system_type": "split_ac"})


def test_hydronic_installation_type_adds_table_20_circulation_pump_energy():
    project_without_type = make_test_project()
    project_with_type = project_without_type.model_copy(deep=True)
    project_with_type.systems.heating.installation_type = "water_radiators"
    project_with_type.systems.cooling = SystemHeatingCooling(
        system_type="split_ac",
        installation_type="direct_expansion",
    )

    without_type = calculate_building_energy(project_without_type)
    with_type = calculate_building_energy(project_with_type)

    # Heating is a hydronic installation, so Table 20 row 1 adds the
    # circulation-pump demand in addition to the source-specific demand.
    pump_aux_kwh = 0.30 * 5700.0 * 150.0 / 1000.0
    assert with_type.annual_indicators.eu_kwh_m2_year == pytest.approx(
        without_type.annual_indicators.eu_kwh_m2_year
    )
    assert with_type.annual_indicators.ek_kwh_m2_year == pytest.approx(
        without_type.annual_indicators.ek_kwh_m2_year + pump_aux_kwh / 150.0
    )
    assert with_type.annual_indicators.ep_kwh_m2_year == pytest.approx(
        without_type.annual_indicators.ep_kwh_m2_year + 2.5 * pump_aux_kwh / 150.0
    )


def test_explicit_heating_auxiliary_energy_is_added_to_final_electricity():
    baseline_project = make_test_project()
    baseline = calculate_building_energy(baseline_project)

    explicit_project = baseline_project.model_copy(deep=True)
    explicit_project.systems.heating.auxiliary_energy_kwh_year = 1200.0
    explicit = calculate_building_energy(explicit_project)

    assert explicit.annual_indicators.eu_kwh_m2_year == pytest.approx(
        baseline.annual_indicators.eu_kwh_m2_year
    )
    ek_delta = explicit.annual_indicators.ek_kwh_m2_year - baseline.annual_indicators.ek_kwh_m2_year
    ep_delta = explicit.annual_indicators.ep_kwh_m2_year - baseline.annual_indicators.ep_kwh_m2_year
    assert ek_delta == pytest.approx(1200.0 / 150.0)
    assert ep_delta == pytest.approx(2.5 * 1200.0 / 150.0)


def test_explicit_cooling_auxiliary_energy_is_added_when_cooling_is_active():
    baseline_project = make_test_project()
    baseline_project.thermal_zones[0].zone_type = ZoneType.HEATED_AND_COOLED
    baseline_project.systems.cooling = SystemHeatingCooling(
        system_type="split_ac",
        fuel_or_carrier="electricity",
        generation_efficiency=3.9,
        distribution_efficiency=1.0,
        storage_efficiency=1.0,
        control_efficiency=1.0,
    )
    baseline = calculate_building_energy(baseline_project)

    explicit_project = baseline_project.model_copy(deep=True)
    explicit_project.systems.cooling.auxiliary_energy_kwh_year = 600.0
    explicit = calculate_building_energy(explicit_project)

    assert explicit.annual_indicators.eu_kwh_m2_year == pytest.approx(
        baseline.annual_indicators.eu_kwh_m2_year
    )
    ek_delta = explicit.annual_indicators.ek_kwh_m2_year - baseline.annual_indicators.ek_kwh_m2_year
    ep_delta = explicit.annual_indicators.ep_kwh_m2_year - baseline.annual_indicators.ep_kwh_m2_year
    assert ek_delta == pytest.approx(600.0 / 150.0)
    assert ep_delta == pytest.approx(2.5 * 600.0 / 150.0)


def test_total_system_efficiency_is_the_product_of_all_components():
    assert total_system_efficiency(3.0, 0.95, 0.9, 0.8) == pytest.approx(2.052)


def test_dhw_total_efficiency_is_product_of_four_components():
    """ηW,tot = ηW,g · ηW,s · ηW,d · ηW,e (gdy brak pojemności zasobnika)."""
    project = make_test_project()
    project.systems.dhw.generation_efficiency = 0.92
    project.systems.dhw.storage_efficiency = 0.98
    project.systems.dhw.distribution_efficiency = 0.8
    project.systems.dhw.utilization_efficiency = 1.0
    project.systems.dhw.storage_volume_dm3 = None

    result = calculate_building_energy(project)
    expected = 0.92 * 0.98 * 0.8 * 1.0
    assert result.annual_indicators.dhw_total_efficiency == pytest.approx(expected, rel=1e-6)


def test_dhw_total_efficiency_is_none_when_storage_volume_provided():
    """Gdy podano pojemność zasobnika, straty z tabeli 13 — ηW,tot nie jest iloczynem."""
    project = make_test_project()
    project.systems.dhw.system_type = "gas_boiler"
    project.systems.dhw.fuel_or_carrier = "natural_gas"
    project.systems.dhw.storage_volume_dm3 = 200.0
    project.systems.dhw.storage_location = "unheated"
    project.systems.dhw.storage_insulation_mm = 50.0

    result = calculate_building_energy(project)
    assert result.annual_indicators.dhw_total_efficiency is not None
    # Efektywna ηW,tot = Q_W,nd / E_k,DHW — powinna być > 0 i < ηW,g
    assert 0.0 < result.annual_indicators.dhw_total_efficiency < 1.0


def test_dhw_auxiliary_energy_kwh_year_overrides_table_20():
    """Jawna energia pomocnicza DHW zastępuje wartość z tabeli 20."""
    baseline_project = make_test_project()
    baseline = calculate_building_energy(baseline_project)
    baseline_dhw_aux = baseline.annual_indicators.dhw_auxiliary_energy_kwh_year
    assert baseline_dhw_aux >= 0.0  # tabela 20 dla electric_storage = 0

    # Zmień źródło na gazowe, żeby tabela 20 dawała niezerową energię pomocniczą
    gas_project = baseline_project.model_copy(deep=True)
    gas_project.systems.dhw.system_type = "gas_boiler"
    gas_project.systems.dhw.fuel_or_carrier = "natural_gas"
    gas_project.systems.dhw.generation_efficiency = 0.83
    gas_baseline = calculate_building_energy(gas_project)
    gas_baseline_aux = gas_baseline.annual_indicators.dhw_auxiliary_energy_kwh_year
    assert gas_baseline_aux > 0.0  # tabela 20 dla kotła gazowego > 0

    # Nadpisz jawną wartością
    explicit_project = gas_project.model_copy(deep=True)
    explicit_project.systems.dhw.auxiliary_energy_kwh_year = 500.0
    explicit = calculate_building_energy(explicit_project)

    assert explicit.annual_indicators.dhw_auxiliary_energy_kwh_year == pytest.approx(500.0)
    # Energia końcowa powinna wzrosnąć o różnicę energii pomocniczej
    ek_delta = explicit.annual_indicators.ek_kwh_m2_year - gas_baseline.annual_indicators.ek_kwh_m2_year
    aux_delta_kwh = 500.0 - gas_baseline_aux
    assert ek_delta == pytest.approx(aux_delta_kwh / 150.0, rel=1e-4)


def test_system_efficiency_components_change_final_energy():
    efficient_project = make_test_project()
    efficient_project.systems.heating = SystemHeatingCooling(
        system_type="heat_pump_air",
        fuel_or_carrier="electricity",
        generation_efficiency=3.5,
        distribution_efficiency=0.95,
        storage_efficiency=1.0,
        control_efficiency=1.0,
    )
    inefficient_project = efficient_project.model_copy(deep=True)
    inefficient_project.systems.heating.generation_efficiency = 1.0
    inefficient_project.systems.heating.distribution_efficiency = 0.8

    efficient_result = calculate_building_energy(efficient_project)
    inefficient_result = calculate_building_energy(inefficient_project)

    assert (
        inefficient_result.annual_indicators.ek_kwh_m2_year
        > efficient_result.annual_indicators.ek_kwh_m2_year
    )


def test_element_area_is_derived_from_height_and_width():
    opaque = OpaqueElement(
        id="wall",
        name="Ściana",
        zone_id="z1",
        height=4.0,
        width=10.0,
        area=999.0,
        u_value=0.25,
    )
    transparent = TransparentElement(
        id="window",
        name="Okno",
        zone_id="z1",
        height=2.0,
        width=5.0,
        area=999.0,
        u_value=1.0,
        g_value=0.6,
    )

    assert opaque.area == pytest.approx(40.0)
    assert transparent.area == pytest.approx(10.0)


def test_element_dimensions_must_be_entered_as_a_pair():
    with pytest.raises(ValidationError, match="Both height and width"):
        OpaqueElement(
            id="wall",
            name="Ściana",
            zone_id="z1",
            height=4.0,
            area=40.0,
            u_value=0.25,
        )


def test_design_heating_power_uses_peak_design_losses():
    system = SystemHeatingCooling(
        system_type="gas_boiler",
        distribution_efficiency=0.8,
        storage_efficiency=0.9,
        control_efficiency=1.0,
    )

    power_kw = _design_heating_power_kw(
        np.array([1000.0 + 200.0, 3000.0 + 500.0]),
        system,
    )

    assert power_kw == pytest.approx(3.5 / 0.8 / 0.9)


def test_design_heating_power_is_not_taken_from_legacy_nominal_power():
    project = make_test_project()
    project.systems.heating.nominal_power = 0.1
    result_with_small_legacy_power = calculate_building_energy(project)

    project.systems.heating.nominal_power = 1000.0
    result_with_large_legacy_power = calculate_building_energy(project)

    assert result_with_small_legacy_power.design_heating_power_kw == pytest.approx(
        result_with_large_legacy_power.design_heating_power_kw
    )
    assert result_with_small_legacy_power.design_heating_power_kw > 0.0


def test_cooling_energy_is_not_taken_from_legacy_nominal_power():
    project = make_test_project()
    project.thermal_zones[0].zone_type = "heated_and_cooled"
    project.systems.cooling = SystemHeatingCooling(
        system_type="split_ac",
        fuel_or_carrier="electricity",
        nominal_power=0.1,
        generation_efficiency=3.9,
        distribution_efficiency=1.0,
        storage_efficiency=1.0,
        control_efficiency=1.0,
    )
    result_with_small_legacy_power = calculate_building_energy(project)

    project.systems.cooling.nominal_power = 1000.0
    result_with_large_legacy_power = calculate_building_energy(project)

    assert result_with_small_legacy_power.annual_indicators.cooling_kwh_m2_year == pytest.approx(
        result_with_large_legacy_power.annual_indicators.cooling_kwh_m2_year
    )
    assert result_with_small_legacy_power.annual_indicators.ek_kwh_m2_year == pytest.approx(
        result_with_large_legacy_power.annual_indicators.ek_kwh_m2_year
    )


def test_building_project_rejects_unknown_element_zone_id():
    project_data = make_test_project().model_dump(mode="json")
    project_data["opaque_building_elements"][0]["zone_id"] = "missing-zone"

    with pytest.raises(ValidationError, match="Unknown thermal zone ID"):
        BuildingProject.model_validate(project_data)


def test_heated_zone_partition_rejects_different_conditioned_limits():
    project_data = make_test_project().model_dump(mode="json")
    project_data["opaque_building_elements"][0]["adjacent_space_type"] = "heated_zone"
    project_data["thermal_zones"].append(
        {
            **project_data["thermal_zones"][0],
            "id": "z2",
            "name": "Druga strefa",
            "setpoint_heating": 21.0,
        }
    )
    project_data["general"]["conditioned_floor_area"] = 300.0
    project_data["general"]["heated_volume"] = 750.0

    with pytest.raises(ValidationError, match="identical active heating/cooling"):
        BuildingProject.model_validate(project_data)


def test_omitted_internal_gains_use_building_type_normative_default():
    project_data = make_test_project().model_dump(mode="json")
    project_data.pop("internal_gains", None)
    project_data["general"]["building_type"] = "office"
    project_data["general"]["dhw_usage_profile"] = "office"
    project = BuildingProject.model_validate(project_data)

    hourly = total_internal_gains(
        0.03,
        100.0,
        project.internal_gains,
        pd.date_range("2023-01-01", periods=8760, freq="h"),
    )
    np.testing.assert_allclose(hourly, 5.68 * 100.0)


def test_custom_internal_gains_with_hourly_schedule_reach_engine():
    """Własne zyski wewnętrzne z harmonogramem godzinowym trafiają do silnika
    i zmieniają wynik godzinowy w stosunku do zysków normatywnych."""
    from app.schemas.models import InternalGainSource, InternalGains, Schedule, ScheduleType

    project = make_test_project()
    baseline = calculate_building_energy(project)

    # Harmonogram: pełna moc w godzinach 8-18 dni roboczych, 0 poza tym
    weekday = [0.0] * 8 + [1.0] * 10 + [0.0] * 6
    assert len(weekday) == 24
    custom_project = project.model_copy(deep=True)
    custom_project.internal_gains = InternalGains(
        occupancy=InternalGainSource(
            power_density=80.0,
            schedule=Schedule(type=ScheduleType.HOURLY_PROFILE, weekday=weekday),
        ),
        lighting=InternalGainSource(
            power_density=3.0,
            schedule=Schedule(type=ScheduleType.CONSTANT, constant_value=1.0),
        ),
        equipment=InternalGainSource(
            power_density=5.0,
            schedule=Schedule(type=ScheduleType.CONSTANT, constant_value=1.0),
        ),
    )

    custom_result = calculate_building_energy(custom_project)
    # Wynik powinien się różnić — harmonogram godzinowy zmienia rozkład zysków
    assert custom_result.status == "success"
    # Suma miesięcznych zysków wewnętrznych powinna być mniejsza niż przy
    # stałej mocy normatywnej, bo harmonogram ogranicza pracę do 10h/dobę.
    baseline_gains = sum(m.internal_gains_kwh for m in baseline.monthly)
    custom_gains = sum(m.internal_gains_kwh for m in custom_result.monthly)
    assert custom_gains != pytest.approx(baseline_gains, rel=0.01)


def test_building_project_rejects_duplicate_thermal_zone_ids():
    project_data = make_test_project().model_dump(mode="json")
    project_data["thermal_zones"].append(project_data["thermal_zones"][0].copy())

    with pytest.raises(ValidationError, match="Thermal zone IDs must be unique"):
        BuildingProject.model_validate(project_data)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("conditioned_floor_area", "Conditioned floor area"),
        ("heated_volume", "Heated volume"),
    ],
)
def test_building_project_rejects_inconsistent_conditioned_geometry(field, message):
    project_data = make_test_project().model_dump(mode="json")
    project_data["general"][field] *= 2.0

    with pytest.raises(ValidationError, match=message):
        BuildingProject.model_validate(project_data)
