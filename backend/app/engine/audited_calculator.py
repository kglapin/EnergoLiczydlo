"""Audited calculation entry point.

The annual 5R1C core remains the source of hourly useful-energy demand. This
wrapper validates modelling completeness, prepares normative boundary models,
adds auxiliary electricity omitted by the legacy core and replaces the former
TMY sizing diagnostic with an explicit design-condition load when configured.
"""

from __future__ import annotations

import numpy as np

import app.engine.calculator as core_calculator
from app.engine.design_load import calculate_design_heat_load
from app.engine.ground_iso13370 import prepare_ground_boundaries
from app.engine.heat_recovery import attach_heat_recovery_settings
from app.engine.normative_models import NormativeSettings, load_normative_settings
from app.engine.normative_runtime import annual_heat_recovery_stats
from app.engine.preflight_geometry import (
    apply_net_opaque_areas,
    audit_check,
    enum_value,
    geometry_checks,
)
from app.engine.preflight_systems import (
    model_limit_checks,
    normalise_renewable_carriers,
    system_preflight,
)
from app.schemas.models import BuildingProject, CalculationResult, ComplianceCheck


def _filtered_limit_checks(
    project: BuildingProject,
    settings: NormativeSettings,
) -> list[ComplianceCheck]:
    checks = model_limit_checks(project)
    filtered: list[ComplianceCheck] = []
    for check in checks:
        if settings.ground.enabled and "GROUND_MODEL_SIMPLIFIED" in check.name:
            continue
        if settings.heat_recovery.enabled and "HEAT_RECOVERY_CONSTANT_EFFICIENCY" in check.name:
            continue
        if settings.design_conditions.enabled and "DESIGN_POWER_TMY_PEAK" in check.name:
            continue
        filtered.append(check)
    return filtered


def _used_energy_carriers(project: BuildingProject) -> set[str]:
    carriers: set[str] = set()
    heating = project.systems.heating
    if enum_value(heating.system_type) != "none":
        carriers.add(enum_value(heating.fuel_or_carrier))
    cooling = project.systems.cooling
    if cooling is not None and enum_value(cooling.system_type) != "none":
        carriers.add(enum_value(cooling.fuel_or_carrier))
    dhw = project.systems.dhw
    if enum_value(dhw.system_type) != "none":
        carriers.add(enum_value(dhw.fuel_or_carrier))

    ventilation_type = enum_value(project.ventilation.ventilation_type)
    has_electric_auxiliary = (
        ventilation_type in {"mechanical", "mechanical_with_recovery", "exhaust", "hybrid"}
        or project.general.lighting_indicator_leni is not None
        or enum_value(heating.system_type) != "none"
        or (cooling is not None and enum_value(cooling.system_type) != "none")
        or enum_value(dhw.system_type) != "none"
    )
    if has_electric_auxiliary:
        carriers.add("electricity")
    return carriers


def _legal_readiness_checks(
    project: BuildingProject,
    settings: NormativeSettings,
) -> list[ComplianceCheck]:
    """Validate evidence trail needed for a formal Polish calculation run."""
    if not settings.legal.certificate_mode:
        return []

    has_ground = any(
        enum_value(element.adjacent_space_type) == "ground"
        for element in project.opaque_building_elements
    )
    if has_ground and not (settings.ground.enabled and settings.ground.certificate_mode):
        raise ValueError(
            "Formal calculation mode contains ground-coupled elements. Enable the "
            "ISO 13370 ground model in certificate_mode and provide verified periodic inputs."
        )

    ventilation_type = enum_value(project.ventilation.ventilation_type)
    if (
        ventilation_type == "mechanical_with_recovery"
        and project.ventilation.heat_recovery_efficiency > 0.0
        and not (
            settings.heat_recovery.enabled
            and settings.heat_recovery.certificate_mode
        )
    ):
        raise ValueError(
            "Formal calculation mode with heat recovery requires the detailed "
            "heat-recovery model in certificate_mode and documented device performance."
        )

    if settings.design_conditions.enabled and not settings.design_conditions.certificate_mode:
        raise ValueError(
            "Design load is enabled during a formal calculation but its certificate_mode "
            "is disabled. Either verify its design-condition source or disable design load."
        )

    used_carriers = _used_energy_carriers(project)
    sources = settings.legal.primary_energy_factor_sources
    missing_sources = sorted(
        carrier
        for carrier in used_carriers
        if not str(sources.get(carrier, "")).strip()
    )
    if missing_sources:
        raise ValueError(
            "Formal calculation requires provenance for every used primary-energy "
            "factor wi. Missing source for: " + ", ".join(missing_sources) + ". "
            "Record supplier data when available or explicitly document use of the "
            "regulatory fallback table when supplier data are unavailable."
        )

    return [
        audit_check(
            "POLISH_LEGAL_PROVENANCE",
            "Formal calculation evidence recorded for date "
            f"{settings.legal.calculation_date}; methodology source: "
            f"{settings.legal.methodology_source}; climate source: "
            f"{settings.legal.climate_data_source}; wi provenance available for "
            f"{', '.join(sorted(used_carriers)) or 'no carriers'}.",
            passed=True,
        )
    ]


def _prepare_normative_extensions(
    project: BuildingProject,
    checks: list[ComplianceCheck],
    settings: NormativeSettings,
) -> None:
    needs_climate = (
        settings.ground.enabled
        or settings.heat_recovery.enabled
        or settings.design_conditions.enabled
    )
    climate = core_calculator._load_climate(project) if needs_climate else None

    if settings.ground.enabled:
        if climate is None:
            raise RuntimeError("Ground preparation requires climate data")
        checks.extend(
            prepare_ground_boundaries(
                project,
                climate["T_e"].to_numpy(dtype=float),
                settings.ground,
            )
        )

    if settings.heat_recovery.enabled:
        vent_type = enum_value(project.ventilation.ventilation_type)
        if vent_type != "mechanical_with_recovery":
            raise ValueError(
                "metadata.normative.heat_recovery can only be enabled for "
                "mechanical_with_recovery ventilation"
            )
        if project.ventilation.supply_temperature is not None:
            raise ValueError(
                "Detailed heat recovery cannot be combined with explicit supply_temperature"
            )
        attach_heat_recovery_settings(project.ventilation, settings.heat_recovery)
        if settings.heat_recovery.summer_bypass_enabled and not any(
            zone.setpoint_cooling is not None for zone in project.thermal_zones
        ):
            message = (
                "Summer bypass is enabled but no zone has a cooling/free-cooling "
                "temperature target; bypass cannot be activated deterministically."
            )
            if settings.heat_recovery.certificate_mode:
                raise ValueError(message)
            checks.append(audit_check("HEAT_RECOVERY_BYPASS_NO_TARGET", message))
        checks.append(
            audit_check(
                "HEAT_RECOVERY_DYNAMIC",
                "Heat recovery is evaluated hour by hour with full physical "
                "mechanical airflow, dynamic supply temperature, summer bypass "
                "and the configured frost-protection strategy. Performance source: "
                f"{settings.heat_recovery.performance_source or 'not supplied'}.",
                passed=True,
            )
        )

    has_ground = any(
        enum_value(element.adjacent_space_type) == "ground"
        for element in project.opaque_building_elements
    )
    if (
        settings.design_conditions.enabled
        and settings.design_conditions.certificate_mode
        and has_ground
        and not settings.ground.enabled
    ):
        raise ValueError(
            "Certificate-grade design load contains ground-coupled elements; "
            "enable metadata.normative.ground and provide ISO 13370 inputs first"
        )

    checks.extend(_legal_readiness_checks(project, settings))
    object.__setattr__(project, "_normative_settings", settings)
    if climate is not None:
        object.__setattr__(project, "_normative_climate", climate)


def prepare_project_for_audited_calculation(
    project: BuildingProject,
) -> tuple[BuildingProject, list[ComplianceCheck]]:
    """Return a corrected deep copy plus audit checks; never mutate caller input."""
    corrected = project.model_copy(deep=True)
    checks: list[ComplianceCheck] = []

    checks.extend(geometry_checks(corrected))
    checks.extend(system_preflight(corrected))
    apply_net_opaque_areas(corrected, checks)
    settings = load_normative_settings(corrected)
    _prepare_normative_extensions(corrected, checks, settings)
    checks.extend(_filtered_limit_checks(corrected, settings))
    normalise_renewable_carriers(corrected)
    return corrected, checks


def _apply_preheater_energy(
    result: CalculationResult,
    project: BuildingProject,
    settings: NormativeSettings,
    checks: list[ComplianceCheck],
) -> dict[str, float | int]:
    if not settings.heat_recovery.enabled:
        return {}
    climate = getattr(project, "_normative_climate", None)
    if climate is None:
        raise RuntimeError("Dynamic heat-recovery accounting requires climate data")
    stats = annual_heat_recovery_stats(project, climate)
    preheater_kwh = stats.preheater_energy_wh / 1000.0
    area = float(project.general.conditioned_floor_area)

    if preheater_kwh > 0.0:
        base_ek_kwh = result.annual_indicators.ek_kwh_m2_year * area
        renewable_kwh = base_ek_kwh * result.annual_indicators.u_oze_percent / 100.0
        new_ek_kwh = base_ek_kwh + preheater_kwh
        electricity = project.primary_energy.electricity
        result.annual_indicators.ek_kwh_m2_year = new_ek_kwh / area
        result.annual_indicators.ep_kwh_m2_year += preheater_kwh * electricity.fp / area
        result.annual_indicators.ec_tco2_m2_year += (
            preheater_kwh * electricity.we / 1000.0 / area
        )
        result.annual_indicators.u_oze_percent = (
            0.0 if new_ek_kwh <= 0.0 else 100.0 * renewable_kwh / new_ek_kwh
        )

    checks.append(
        audit_check(
            "HEAT_RECOVERY_RUNTIME",
            "Dynamic recovery runtime: "
            f"recovery active {stats.recovery_active_hours} h, "
            f"summer bypass {stats.bypass_hours} h, frost-risk {stats.frost_risk_hours} h, "
            f"preheater electricity {preheater_kwh:.2f} kWh/year. "
            "Preheater electricity is included in Ek, Ep and CO2.",
            passed=True,
        )
    )
    return {
        "preheater_energy_kwh": preheater_kwh,
        "recovery_active_hours": stats.recovery_active_hours,
        "bypass_hours": stats.bypass_hours,
        "frost_risk_hours": stats.frost_risk_hours,
    }


def _apply_design_load(
    result: CalculationResult,
    project: BuildingProject,
    settings: NormativeSettings,
    checks: list[ComplianceCheck],
) -> dict[str, object]:
    if not settings.design_conditions.enabled:
        return {"tmy_peak_diagnostic_kw": result.design_heating_power_kw}

    climate = getattr(project, "_normative_climate", None)
    if climate is None:
        raise RuntimeError("Design-load calculation requires climate data")
    outdoor_design = settings.design_conditions.outdoor_design_temperature_c
    if outdoor_design is None:
        raise RuntimeError("Validated design outdoor temperature is missing")
    tmy_diagnostic = float(result.design_heating_power_kw)
    annual_mean_outdoor = float(np.mean(climate["T_e"].to_numpy(dtype=float)))
    design = calculate_design_heat_load(
        project,
        settings.design_conditions,
        annual_mean_outdoor,
    )
    result.design_heating_power_kw = design.total_w / 1000.0
    zones = {
        zone.zone_id: {
            "name": zone.zone_name,
            "transmission_kw": zone.transmission_w / 1000.0,
            "ventilation_kw": zone.ventilation_w / 1000.0,
            "heat_up_kw": zone.heat_up_w / 1000.0,
            "total_kw": zone.total_w / 1000.0,
        }
        for zone in design.zones
    }
    checks.append(
        audit_check(
            "DESIGN_LOAD_EXPLICIT_CONDITIONS",
            "Project design heat load uses explicit outdoor design temperature "
            f"{outdoor_design:.1f} °C "
            f"(source: {settings.design_conditions.source or 'not supplied'}), "
            f"not the coldest TMY hour. Building useful design load = "
            f"{design.total_w / 1000.0:.3f} kW. The previous TMY peak remains "
            f"diagnostic only ({tmy_diagnostic:.3f} kW).",
            passed=True,
        )
    )
    return {
        "design_load_kw": design.total_w / 1000.0,
        "tmy_peak_diagnostic_kw": tmy_diagnostic,
        "zones": zones,
    }


def calculate_building_energy(project: BuildingProject) -> CalculationResult:
    """Run audited hourly energy calculation with optional normative extensions."""
    corrected, checks = prepare_project_for_audited_calculation(project)
    settings_value = getattr(corrected, "_normative_settings", None)
    settings = (
        settings_value
        if isinstance(settings_value, NormativeSettings)
        else load_normative_settings(corrected)
    )
    result = core_calculator.calculate_building_energy(corrected)

    recovery_diag = _apply_preheater_energy(result, corrected, settings, checks)
    design_diag = _apply_design_load(result, corrected, settings, checks)
    hourly = dict(result.hourly or {})
    hourly["normative_diagnostics"] = {
        "ground_enabled": settings.ground.enabled,
        "ground_certificate_mode": settings.ground.certificate_mode,
        "heat_recovery": recovery_diag,
        "design_load": design_diag,
        "formal_legal_mode": settings.legal.certificate_mode,
    }
    result.hourly = hourly
    result.compliance = checks + list(result.compliance)
    return result
