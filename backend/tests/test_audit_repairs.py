"""Regression tests for defects found by the 2026-08-17 technical audit."""

from __future__ import annotations

from datetime import date
import inspect

import numpy as np
import pandas as pd
import pytest

import app.engine.calculator as core_calculator
import app.engine.climate as climate_module
from app.engine.audited_calculator import _legal_readiness_checks
from app.engine.design_load import calculate_design_heat_load
from app.engine.ground_iso13370 import (
    equivalent_thickness_m,
    slab_on_ground_u_value_w_m2k,
)
from app.engine.heat_recovery import attach_heat_recovery_settings, heat_recovery_state
from app.engine.iso52016_hourly import solve_zone_iso52016
from app.engine.normative_models import (
    DesignConditionsSettings,
    HeatRecoverySettings,
    LegalProvenanceSettings,
    NormativeSettings,
    PolishCertificateMonthlySettings,
)
from app.engine.polish_certificate_monthly import calculate_polish_monthly_certificate
from app.schemas.models import (
    BuildingProject,
    BuildingSystems,
    DesignRoom,
    GeneralInfo,
    InternalGainSource,
    InternalGains,
    OpaqueElement,
    SystemDHW,
    SystemHeatingCooling,
    ThermalBridgeConfig,
    ThermalZone,
    Ventilation,
)


def _zero_internal_gains() -> InternalGains:
    return InternalGains(
        occupancy=InternalGainSource(power_density=0.0),
        lighting=InternalGainSource(power_density=0.0),
        equipment=InternalGainSource(power_density=0.0),
        normative_power_density_w_m2=None,
    )


def _project(
    *,
    wall_area: float = 25.0,
    wall_u: float = 1.0,
    metadata: dict | None = None,
    wall_kwargs: dict | None = None,
    design_rooms: list[DesignRoom] | None = None,
) -> BuildingProject:
    element_kwargs = dict(wall_kwargs or {})
    return BuildingProject(
        project_name="Naprawy audytu",
        metadata=metadata or {},
        general=GeneralInfo(
            building_name="Budynek testowy",
            building_type="residential",
            dhw_usage_profile="residential_single_family",
            construction_year=2020,
            conditioned_floor_area=100.0,
            usable_floor_area=100.0,
            heated_volume=250.0,
            number_of_storeys=1,
        ),
        climate_station_id="synthetic",
        thermal_zones=[
            ThermalZone(
                id="z1",
                name="Strefa",
                floor_area=100.0,
                volume=250.0,
                setpoint_heating=20.0,
                setpoint_cooling=26.0,
                occupancy_density=0.0,
            )
        ],
        opaque_building_elements=[
            OpaqueElement(
                id="wall",
                name="Ściana",
                zone_id="z1",
                area=wall_area,
                u_value=wall_u,
                solar_absorptance=0.0,
                **element_kwargs,
            )
        ],
        transparent_building_elements=[],
        design_rooms=design_rooms or [],
        thermal_bridges=ThermalBridgeConfig(),
        ventilation=Ventilation(
            ventilation_type="none",
            airflow_rate=0.0,
            infiltration_rate=0.0,
            fan_infiltration_rate=0.0,
        ),
        internal_gains=_zero_internal_gains(),
        systems=BuildingSystems(
            heating=SystemHeatingCooling(
                system_type="electric_direct",
                fuel_or_carrier="electricity",
                generation_efficiency=1.0,
                distribution_efficiency=1.0,
                storage_efficiency=1.0,
                control_efficiency=1.0,
                auxiliary_energy_kwh_year=0.0,
            ),
            cooling=SystemHeatingCooling(system_type="none", fuel_or_carrier="electricity"),
            dhw=SystemDHW(system_type="none"),
        ),
    )


def _constant_climate(temperature_c: float) -> pd.DataFrame:
    index = pd.date_range("2023-01-01", periods=8760, freq="h")
    return pd.DataFrame(
        {
            "T_e": np.full(8760, temperature_c),
            "GHI": np.zeros(8760),
            "DNI": np.zeros(8760),
            "DHI": np.zeros(8760),
            "sun_zenith": np.full(8760, 90.0),
            "sun_azimuth": np.zeros(8760),
        },
        index=index,
    )


def test_iso52016_schema_has_construction_level_mass_inputs() -> None:
    required = {"areal_heat_capacity", "mass_distribution_class"}
    assert required.issubset(OpaqueElement.model_fields)
    assert "thermal_node_capacities_kj_m2k" in OpaqueElement.model_fields
    assert "thermal_node_resistances_m2k_w" in OpaqueElement.model_fields


def test_iso52010_runtime_uses_perez_not_hay_davies() -> None:
    source = inspect.getsource(climate_module.radiation_on_surface).lower()
    assert "perez" in source
    assert "haydavies" not in source


def test_iso13370_equivalent_thickness_includes_rse() -> None:
    actual = equivalent_thickness_m(2.0, 2.0, 0.3)
    expected = 0.3 + 2.0 * (0.17 + 2.0 + 0.04)
    assert actual == pytest.approx(expected)


def test_iso13370_slab_formula_uses_correct_branch_after_rse_fix() -> None:
    area = 25.0
    perimeter = 20.0
    conductivity = 2.0
    resistance = 2.0
    thickness = 0.3
    b_prime = 2.0 * area / perimeter
    d_t = equivalent_thickness_m(conductivity, resistance, thickness)
    if d_t < b_prime:
        expected = (
            2.0
            * conductivity
            / (np.pi * b_prime + d_t)
            * np.log(np.pi * b_prime / d_t + 1.0)
        )
    else:
        expected = conductivity / (0.457 * b_prime + d_t)
    assert slab_on_ground_u_value_w_m2k(
        area,
        perimeter,
        conductivity,
        resistance,
        thickness,
    ) == pytest.approx(expected)


def test_heat_recovery_hot_hour_uses_cooling_extract_reference() -> None:
    zone = ThermalZone(
        id="z1",
        name="Strefa",
        floor_area=100.0,
        volume=250.0,
        setpoint_heating=20.0,
        setpoint_cooling=26.0,
    )
    ventilation = Ventilation(
        ventilation_type="mechanical_with_recovery",
        airflow_rate=200.0,
        heat_recovery_efficiency=0.8,
        infiltration_rate=0.0,
    )
    attach_heat_recovery_settings(ventilation, HeatRecoverySettings(enabled=True))
    result = heat_recovery_state(ventilation, zone, np.array([30.0]), 200.0)
    assert result.supply_temperature_c[0] == pytest.approx(26.8)


def test_heat_recovery_accepts_actual_extract_temperature() -> None:
    zone = ThermalZone(id="z1", name="Strefa", floor_area=100.0, volume=250.0)
    ventilation = Ventilation(
        ventilation_type="mechanical_with_recovery",
        airflow_rate=200.0,
        heat_recovery_efficiency=0.8,
        infiltration_rate=0.0,
    )
    attach_heat_recovery_settings(ventilation, HeatRecoverySettings(enabled=True))
    result = heat_recovery_state(
        ventilation,
        zone,
        np.array([30.0]),
        200.0,
        extract_temperature_c=np.array([24.0]),
    )
    assert result.supply_temperature_c[0] == pytest.approx(25.2)


def test_legacy_hourly_year_warms_up_to_periodic_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(wall_area=25.0, wall_u=1.0)
    climate = _constant_climate(0.0)
    monkeypatch.setattr(core_calculator, "_load_climate", lambda _project: climate)
    result = core_calculator.calculate_building_energy(project)
    heating_kwh = result.annual_indicators.heating_kwh_m2_year * 100.0
    assert heating_kwh == pytest.approx(4380.0, rel=1e-7)


def test_legacy_1000w_constant_loss_aggregates_to_8760kwh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(wall_area=50.0, wall_u=1.0)
    climate = _constant_climate(0.0)
    monkeypatch.setattr(core_calculator, "_load_climate", lambda _project: climate)
    result = core_calculator.calculate_building_energy(project)
    assert sum(month.heating_kwh for month in result.monthly) == pytest.approx(
        8760.0,
        rel=1e-7,
    )


def test_hourly_and_polish_monthly_match_steady_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(wall_area=25.0, wall_u=1.0)
    climate = _constant_climate(0.0)
    monkeypatch.setattr(core_calculator, "_load_climate", lambda _project: climate)
    hourly = core_calculator.calculate_building_energy(project)
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
    hourly_kwh = hourly.annual_indicators.heating_kwh_m2_year * 100.0
    assert hourly_kwh == pytest.approx(4380.0, rel=1e-7)
    assert monthly.heating_useful_kwh == pytest.approx(4380.0, rel=1e-12)
    assert abs(hourly_kwh - monthly.heating_useful_kwh) / 4380.0 < 1e-6


def test_formal_mode_rejects_unverified_useful_energy_override() -> None:
    project = _project(wall_area=25.0, wall_u=1.0)
    with pytest.raises(ValueError, match="override|evidence"):
        settings = NormativeSettings(
            polish_certificate=PolishCertificateMonthlySettings(
                enabled=True,
                official_bip_climate_data=True,
                monthly_outdoor_temperature_c=[0.0] * 12,
                heating_useful_override_kwh_by_zone={"z1": [0.0] * 12},
            ),
            legal=LegalProvenanceSettings(
                certificate_mode=True,
                calculation_date=date(2026, 8, 17),
                methodology_source="test",
                climate_data_source="test",
                utilization_factor_source="test",
                ventilation_factor_source="test",
                primary_energy_factor_sources={"electricity": "test"},
            ),
        )
        _legal_readiness_checks(project, settings)


def test_verified_monthly_override_is_allowed() -> None:
    project = _project()
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[0.0] * 12,
        heating_useful_override_kwh_by_zone={"z1": [10.0] * 12},
        useful_energy_override_evidence_by_zone={"z1": "external calculation SHA256:test"},
        internal_gain_density_w_m2_by_zone={"z1": 0.0},
    )
    result = calculate_polish_monthly_certificate(project, settings)
    assert result.heating_useful_kwh == pytest.approx(120.0)


def test_project_schema_has_room_level_design_model() -> None:
    assert "design_rooms" in BuildingProject.model_fields


def test_room_level_design_load_matches_manual_wall_case() -> None:
    room = DesignRoom(
        id="r1",
        name="Pokój",
        zone_id="z1",
        floor_area=100.0,
        volume=250.0,
        design_temperature_c=20.0,
        opaque_element_ids=["wall"],
    )
    project = _project(design_rooms=[room])
    settings = DesignConditionsSettings(
        enabled=True,
        certificate_mode=True,
        outdoor_design_temperature_c=-20.0,
        source="test",
    )
    result = calculate_design_heat_load(project, settings, annual_mean_outdoor_c=8.0)
    assert len(result.rooms) == 1
    assert result.rooms[0].transmission_w == pytest.approx(1000.0)
    assert result.total_w == pytest.approx(1000.0)


def test_design_load_certificate_mode_rejects_missing_rooms() -> None:
    project = _project()
    settings = DesignConditionsSettings(
        enabled=True,
        certificate_mode=True,
        outdoor_design_temperature_c=-20.0,
        source="test",
    )
    with pytest.raises(ValueError, match="design_rooms"):
        calculate_design_heat_load(project, settings, annual_mean_outdoor_c=8.0)


def test_detailed_hourly_solver_has_five_nodes_per_construction_and_closes_steady_year() -> None:
    wall = OpaqueElement(
        id="wall",
        name="Ściana",
        zone_id="z1",
        area=25.0,
        u_value=1.0,
        solar_absorptance=0.0,
        thermal_node_capacities_kj_m2k=[40.0, 40.0, 40.0, 40.0, 40.0],
        thermal_node_resistances_m2k_w=[0.13, 0.2075, 0.2075, 0.2075, 0.2075, 0.04],
    )
    solution = solve_zone_iso52016(
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
    assert solution.construction_node_temperatures["wall"].shape == (8760, 5)
    assert solution.used_inferred_construction is False
    assert solution.q_heating.sum() / 1000.0 == pytest.approx(4380.0, rel=1e-4)
    assert np.mean(solution.q_transmission) == pytest.approx(500.0, rel=1e-4)
    assert solution.periodic_residual_k <= 0.001


def test_detailed_hourly_certificate_mode_rejects_inferred_construction() -> None:
    wall = OpaqueElement(
        id="wall",
        name="Ściana",
        zone_id="z1",
        area=25.0,
        u_value=1.0,
        areal_heat_capacity=200.0,
        mass_distribution_class="distributed",
    )
    with pytest.raises(ValueError, match="explicit five-node"):
        solve_zone_iso52016(
            opaque_elements=[wall],
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
