"""Analytical tests for the Polish regulatory monthly certificate layer."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from app.engine.normative_models import PolishCertificateMonthlySettings
from app.engine.polish_certificate_monthly import calculate_polish_monthly_certificate
from app.schemas.models import (
    DHWSourceType,
    OpaqueElement,
    Ventilation,
    VentilationType,
    ZoneType,
)
from scripts.test_building import make_test_project

DAYS = np.asarray([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], dtype=float)
HOURS = DAYS * 24.0


def _simple_heating_project():
    project = make_test_project()
    zone = project.thermal_zones[0]
    zone.zone_type = ZoneType.HEATED
    zone.setpoint_heating = 20.0
    zone.setpoint_cooling = None
    project.opaque_building_elements = [
        OpaqueElement(
            id="wall",
            name="Wall",
            zone_id=zone.id,
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
        ventilation_type=VentilationType.NONE,
        airflow_rate=0.0,
        infiltration_rate=0.0,
    )
    project.internal_gains.normative_power_density_w_m2 = 0.0
    project.systems.cooling = None
    project.systems.dhw.system_type = DHWSourceType.NONE
    return project


def test_enabled_monthly_certificate_requires_twelve_outdoor_values() -> None:
    with pytest.raises(ValidationError, match="exactly 12 monthly values"):
        PolishCertificateMonthlySettings(
            enabled=True,
            monthly_outdoor_temperature_c=[-5.0] * 11,
        )


def test_monthly_heating_balance_closes_analytically_without_gains() -> None:
    project = _simple_heating_project()
    zone = project.thermal_zones[0]
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[-10.0] * 12,
        heating_internal_temperature_c_by_zone={zone.id: [20.0] * 12},
        heating_gain_utilization_by_zone={zone.id: [0.0] * 12},
        internal_gain_density_w_m2_by_zone={zone.id: 0.0},
    )

    result = calculate_polish_monthly_certificate(project, settings)
    expected_monthly = 10.0 * 0.2 * (20.0 - (-10.0)) * HOURS / 1000.0
    actual = np.asarray([month.heating_kwh for month in result.monthly])
    assert actual == pytest.approx(expected_monthly)
    assert result.heating_useful_kwh == pytest.approx(float(np.sum(expected_monthly)))
    assert result.heating_useful_kwh == pytest.approx(525.6)


def test_heating_gain_utilization_reduces_monthly_demand() -> None:
    project = _simple_heating_project()
    zone = project.thermal_zones[0]
    project.internal_gains.normative_power_density_w_m2 = 1.0
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[-10.0] * 12,
        heating_internal_temperature_c_by_zone={zone.id: [20.0] * 12},
        heating_gain_utilization_by_zone={zone.id: [0.5] * 12},
    )

    result = calculate_polish_monthly_certificate(project, settings)
    losses = 10.0 * 0.2 * 30.0 * HOURS / 1000.0
    gains = 1.0 * zone.floor_area * HOURS / 1000.0
    expected = np.maximum(losses - 0.5 * gains, 0.0)
    actual = np.asarray([month.heating_kwh for month in result.monthly])
    assert actual == pytest.approx(expected)


def test_monthly_cooling_balance_uses_loss_utilization_factor() -> None:
    project = _simple_heating_project()
    zone = project.thermal_zones[0]
    zone.zone_type = ZoneType.COOLED
    zone.setpoint_cooling = 26.0
    project.opaque_building_elements = []
    project.internal_gains.normative_power_density_w_m2 = 5.0
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[26.0] * 12,
        cooling_internal_temperature_c_by_zone={zone.id: [26.0] * 12},
        cooling_loss_utilization_by_zone={zone.id: [0.0] * 12},
    )

    result = calculate_polish_monthly_certificate(project, settings)
    expected = 5.0 * zone.floor_area * HOURS / 1000.0
    actual = np.asarray([month.cooling_kwh for month in result.monthly])
    assert actual == pytest.approx(expected)


def test_formal_monthly_engine_rejects_unconfirmed_official_bip_climate() -> None:
    project = _simple_heating_project()
    zone = project.thermal_zones[0]
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=False,
        monthly_outdoor_temperature_c=[-10.0] * 12,
        heating_internal_temperature_c_by_zone={zone.id: [20.0] * 12},
        heating_gain_utilization_by_zone={zone.id: [0.0] * 12},
    )
    with pytest.raises(ValueError, match="official Polish ministerial BIP"):
        calculate_polish_monthly_certificate(project, settings)


def test_mechanical_recovery_requires_monthly_effectiveness_in_certificate_engine() -> None:
    project = _simple_heating_project()
    zone = project.thermal_zones[0]
    project.ventilation = Ventilation(
        ventilation_type=VentilationType.MECHANICAL_WITH_RECOVERY,
        airflow_rate=200.0,
        heat_recovery_efficiency=0.8,
        infiltration_rate=0.0,
    )
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[-10.0] * 12,
        heating_internal_temperature_c_by_zone={zone.id: [20.0] * 12},
        heating_gain_utilization_by_zone={zone.id: [0.0] * 12},
    )
    with pytest.raises(ValueError, match="monthly heat-recovery effectiveness"):
        calculate_polish_monthly_certificate(project, settings)


def test_heating_override_supports_verified_nonstandard_monthly_procedure() -> None:
    project = _simple_heating_project()
    zone = project.thermal_zones[0]
    override = [100.0 + month for month in range(12)]
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[0.0] * 12,
        heating_useful_override_kwh_by_zone={zone.id: override},
        useful_energy_override_evidence_by_zone={
            zone.id: "verified external monthly calculation; sha256=test"
        },
        internal_gain_density_w_m2_by_zone={zone.id: 0.0},
    )
    result = calculate_polish_monthly_certificate(project, settings)
    assert [month.heating_kwh for month in result.monthly] == pytest.approx(override)
    assert result.heating_useful_kwh == pytest.approx(sum(override))
