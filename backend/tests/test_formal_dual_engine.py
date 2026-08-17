"""Integration tests for separation of hourly analysis and formal certificate result."""

from __future__ import annotations

from app.engine.audited_calculator import _replace_with_formal_monthly_result
from app.engine.normative_models import NormativeSettings, PolishCertificateMonthlySettings
from app.schemas.models import AnnualIndicators, CalculationResult, MonthlyResult, Ventilation
from scripts.test_building import make_test_project


def _dummy_hourly_result() -> CalculationResult:
    monthly = [
        MonthlyResult(
            month=month,
            heating_kwh=999.0,
            cooling_kwh=0.0,
            dhw_kwh=0.0,
            internal_gains_kwh=0.0,
            solar_gains_kwh=0.0,
            transmission_losses_kwh=0.0,
            ventilation_losses_kwh=0.0,
        )
        for month in range(1, 13)
    ]
    return CalculationResult(
        project_id="test",
        status="success",
        design_heating_power_kw=1.0,
        annual_indicators=AnnualIndicators(
            eu_kwh_m2_year=999.0,
            ek_kwh_m2_year=999.0,
            ep_kwh_m2_year=999.0,
            ec_tco2_m2_year=0.0,
            u_oze_percent=0.0,
            heating_kwh_m2_year=999.0,
            cooling_kwh_m2_year=0.0,
            dhw_kwh_m2_year=0.0,
        ),
        monthly=monthly,
        hourly={},
        compliance=[],
    )


def test_formal_monthly_result_replaces_primary_indicators_but_preserves_hourly_analysis() -> None:
    project = make_test_project()
    zone = project.thermal_zones[0]
    project.opaque_building_elements = []
    project.transparent_building_elements = []
    project.thermal_bridges.linear_bridges = []
    project.thermal_bridges.point_bridges = []
    project.ventilation = Ventilation(
        ventilation_type="none",
        airflow_rate=0.0,
        infiltration_rate=0.0,
    )
    project.internal_gains.normative_power_density_w_m2 = 0.0
    project.systems.cooling = None
    project.systems.dhw.system_type = "none"

    certificate = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[0.0] * 12,
        heating_useful_override_kwh_by_zone={zone.id: [10.0] * 12},
        useful_energy_override_evidence_by_zone={
            zone.id: "verified external monthly calculation; sha256=test"
        },
        internal_gain_density_w_m2_by_zone={zone.id: 0.0},
    )
    settings = NormativeSettings.model_construct(
        polish_certificate=certificate,
        legal=NormativeSettings().legal.model_copy(update={"certificate_mode": True}),
    )
    result = _dummy_hourly_result()
    checks = []

    diagnostics = _replace_with_formal_monthly_result(
        result,
        project,
        settings,
        checks,
    )

    assert result.annual_indicators.eu_kwh_m2_year != 999.0
    assert (
        result.annual_indicators.heating_kwh_m2_year
        == 120.0 / project.general.conditioned_floor_area
    )
    assert [month.heating_kwh for month in result.monthly] == [10.0] * 12
    hourly = diagnostics["iso52016_hourly_analysis"]
    assert isinstance(hourly, dict)
    assert hourly["annual_indicators"]["eu_kwh_m2_year"] == 999.0
    assert diagnostics["primary_result_method"] == "polish_regulation_monthly"
