"""Analytical and physical-regression tests for normative hourly extensions."""

from __future__ import annotations

import numpy as np
import pytest

from app.engine.design_load import calculate_design_heat_load
from app.engine.ground_iso13370 import (
    characteristic_dimension_m,
    diagnostic_periodic_response,
    periodic_ground_temperature,
    slab_on_ground_u_value_w_m2k,
    soil_penetration_depth_m,
)
from app.engine.heat_recovery import (
    attach_heat_recovery_settings,
    dew_point_temperature_c,
    heat_recovery_state,
)
from app.engine.normative_models import (
    DesignConditionsSettings,
    GroundISO13370Settings,
    HeatRecoverySettings,
)
from app.schemas.models import OpaqueElement, ThermalZone, Ventilation
from scripts.test_building import make_test_project


def test_iso13370_characteristic_dimension_is_two_area_over_perimeter() -> None:
    assert characteristic_dimension_m(100.0, 40.0) == pytest.approx(5.0)


def test_iso13370_more_floor_resistance_reduces_ground_u_value() -> None:
    common = {
        "area_m2": 100.0,
        "exposed_perimeter_m": 40.0,
        "soil_conductivity_w_mk": 2.0,
        "external_wall_thickness_m": 0.30,
    }
    weak = slab_on_ground_u_value_w_m2k(
        floor_thermal_resistance_m2k_w=1.0,
        **common,
    )
    strong = slab_on_ground_u_value_w_m2k(
        floor_thermal_resistance_m2k_w=5.0,
        **common,
    )
    assert weak > 0.0
    assert strong > 0.0
    assert strong < weak


def test_soil_penetration_depth_and_diagnostic_response_are_physical() -> None:
    penetration = soil_penetration_depth_m(2.0, 1800.0, 900.0)
    ratio, lag_days = diagnostic_periodic_response(2.0, 2.0, 1800.0, 900.0)
    assert penetration > 0.0
    assert 0.0 < ratio < 1.0
    assert 0.0 < lag_days < 365.0


def test_periodic_ground_temperature_preserves_annual_mean_and_attenuates() -> None:
    hours = np.arange(8760, dtype=float)
    outdoor = 8.0 + 12.0 * np.cos(2.0 * np.pi * hours / 8760.0)
    ground = periodic_ground_temperature(outdoor, amplitude_ratio=0.25, phase_shift_days=60.0)
    assert float(np.mean(ground)) == pytest.approx(8.0, abs=1e-9)
    assert (float(np.max(ground)) - float(np.min(ground))) == pytest.approx(6.0, rel=1e-3)


def test_ground_certificate_mode_refuses_missing_material_properties() -> None:
    with pytest.raises(ValueError, match="requires explicit material inputs"):
        GroundISO13370Settings(enabled=True, certificate_mode=True)


def _recovery_zone() -> ThermalZone:
    return ThermalZone(
        id="zone",
        name="Zone",
        floor_area=100.0,
        volume=250.0,
        setpoint_heating=20.0,
        setpoint_cooling=26.0,
    )


def _detailed_ventilation(settings: HeatRecoverySettings) -> Ventilation:
    ventilation = Ventilation(
        ventilation_type="mechanical_with_recovery",
        airflow_rate=200.0,
        heat_recovery_efficiency=0.8,
        infiltration_rate=0.0,
    )
    attach_heat_recovery_settings(ventilation, settings)
    return ventilation


def test_dynamic_recovery_matches_sensible_heat_exchanger_equation() -> None:
    settings = HeatRecoverySettings(enabled=True)
    ventilation = _detailed_ventilation(settings)
    state = heat_recovery_state(
        ventilation,
        _recovery_zone(),
        np.asarray([0.0]),
        mechanical_flow_m3h=200.0,
    )
    assert state.supply_temperature_c[0] == pytest.approx(16.0)
    assert state.exhaust_outlet_temperature_c[0] == pytest.approx(4.0)
    assert state.effective_efficiency[0] == pytest.approx(0.8)


def test_summer_bypass_disables_recovery_when_outdoor_air_can_free_cool() -> None:
    settings = HeatRecoverySettings(
        enabled=True,
        summer_bypass_enabled=True,
        bypass_min_outdoor_c=15.0,
        bypass_max_outdoor_c=24.0,
        bypass_indoor_margin_k=1.0,
    )
    ventilation = _detailed_ventilation(settings)
    state = heat_recovery_state(
        ventilation,
        _recovery_zone(),
        np.asarray([20.0]),
        mechanical_flow_m3h=200.0,
    )
    assert bool(state.bypass_active[0])
    assert state.effective_efficiency[0] == pytest.approx(0.0)
    assert state.supply_temperature_c[0] == pytest.approx(20.0)


def test_frost_preheater_energy_and_exhaust_temperature_close_analytically() -> None:
    settings = HeatRecoverySettings(
        enabled=True,
        frost_strategy="preheater",
        indoor_relative_humidity=0.50,
        frost_exhaust_limit_c=0.0,
        preheater_max_power_w=2000.0,
        preheater_efficiency=1.0,
    )
    ventilation = _detailed_ventilation(settings)
    state = heat_recovery_state(
        ventilation,
        _recovery_zone(),
        np.asarray([-20.0]),
        mechanical_flow_m3h=200.0,
    )
    # At eta=0.8 and extract=20°C, exhaust=0°C requires preheating outdoor
    # air to -5°C: 200/3600 * 1200 * 15 = 1000 W.
    assert bool(state.frost_risk[0])
    assert state.preheater_power_w[0] == pytest.approx(1000.0)
    assert state.exhaust_outlet_temperature_c[0] == pytest.approx(0.0, abs=1e-9)
    assert state.supply_temperature_c[0] == pytest.approx(15.0)


def test_central_preheater_capacity_is_not_multiplied_by_zone_count() -> None:
    settings = HeatRecoverySettings(
        enabled=True,
        frost_strategy="preheater",
        indoor_relative_humidity=0.50,
        frost_exhaust_limit_c=0.0,
        preheater_max_power_w=1000.0,
        preheater_efficiency=1.0,
    )
    ventilation = _detailed_ventilation(settings)
    zone = _recovery_zone()
    first = heat_recovery_state(
        ventilation,
        zone,
        np.asarray([-30.0]),
        mechanical_flow_m3h=100.0,
        capacity_fraction=0.5,
    )
    second = heat_recovery_state(
        ventilation,
        zone,
        np.asarray([-30.0]),
        mechanical_flow_m3h=100.0,
        capacity_fraction=0.5,
    )
    assert first.preheater_power_w[0] <= 500.0 + 1e-9
    assert second.preheater_power_w[0] <= 500.0 + 1e-9
    assert first.preheater_power_w[0] + second.preheater_power_w[0] <= 1000.0 + 1e-9


def test_dew_point_increases_with_relative_humidity() -> None:
    dry = dew_point_temperature_c(20.0, 0.30)
    humid = dew_point_temperature_c(20.0, 0.70)
    assert humid > dry
    assert humid < 20.0


def test_design_load_uses_explicit_design_temperature_not_tmy_or_cop() -> None:
    project = make_test_project()
    project.opaque_building_elements = [
        OpaqueElement(
            id="wall",
            name="Wall",
            zone_id="zone_1",
            element_type="external_wall",
            area=10.0,
            u_value=0.2,
            adjacent_space_type="outdoor",
        )
    ]
    project.transparent_building_elements = []
    project.thermal_bridges.linear_bridges = []
    project.thermal_bridges.point_bridges = []
    project.ventilation = Ventilation(
        ventilation_type="none",
        airflow_rate=0.0,
        infiltration_rate=0.0,
    )
    project.systems.heating.generation_efficiency = 99.0
    settings = DesignConditionsSettings(
        enabled=True,
        outdoor_design_temperature_c=-10.0,
        source="test design condition",
        heat_up_power_by_zone_w={"zone_1": 40.0},
    )

    result = calculate_design_heat_load(project, settings, annual_mean_outdoor_c=8.0)
    assert len(result.zones) == 1
    # 10 m² * 0.2 W/(m²K) * (20 - -10) K = 60 W; + 40 W heat-up.
    assert result.zones[0].transmission_w == pytest.approx(60.0)
    assert result.zones[0].ventilation_w == pytest.approx(0.0)
    assert result.zones[0].heat_up_w == pytest.approx(40.0)
    assert result.total_w == pytest.approx(100.0)
