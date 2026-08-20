"""Polish regulatory monthly calculation used for formal certificate indicators.

The current Polish methodology regulation defines annual heating/cooling useful
energy as sums of monthly balances. The 8760-hour ISO 52016 model remains a
parallel physical analysis; it does not replace this legally prescribed layer.

Where the regulation delegates a coefficient to a Polish Standard (notably
heating gain-utilization and cooling loss-utilization factors), formal mode
requires a verified 12-month series instead of embedding an unverified
standard-table approximation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import app.engine.calculator as core
from app.engine.normative_models import PolishCertificateMonthlySettings
from app.engine.primary_energy import annual_primary_energy, share_of_renewable_energy
from app.engine.systems import (
    annual_dhw_useful_energy,
    dhw_auxiliary_demand_wh,
    dhw_storage_standby_loss_kwh,
    heating_auxiliary_demand_wh,
    ventilation_fan_power_w_m2,
)
from app.engine.ventilation import (
    NORMATIVE_AIRFLOW_M3_S_M2,
    normative_infiltration_rate,
)
from app.schemas.models import (
    AdjacentSpaceType,
    AnnualIndicators,
    BuildingProject,
    BuildingType,
    ComplianceCheck,
    MonthlyResult,
    ThermalZone,
    VentilationType,
    ZoneType,
)

DAYS_PER_MONTH = np.asarray([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
HOURS_PER_MONTH = DAYS_PER_MONTH * 24.0
CP_AIR_VOLUMETRIC_J_M3K = 1200.0

HEATED_ZONE_TYPES = {
    ZoneType.HEATED,
    ZoneType.HEATED_AND_COOLED,
    ZoneType.SEMI_HEATED,
}
COOLED_ZONE_TYPES = {ZoneType.COOLED, ZoneType.HEATED_AND_COOLED}
CONTINUOUS_VENTILATION_PROFILES = {
    "residential_single_family",
    "residential_multi_family_lump_sum",
    "residential_multi_family_individual_metering",
    "collective_residential",
}


@dataclass(frozen=True)
class PolishMonthlyCertificateResult:
    annual_indicators: AnnualIndicators
    monthly: tuple[MonthlyResult, ...]
    compliance: tuple[ComplianceCheck, ...]
    final_energy_by_carrier_wh: dict[str, float]
    heating_useful_kwh: float
    cooling_useful_kwh: float
    dhw_useful_kwh: float


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _series(
    mapping: dict[str, list[float]],
    key: str,
    label: str,
) -> np.ndarray:
    values = mapping.get(key)
    if values is None:
        raise ValueError(f"Formal monthly calculation requires {label} for '{key}'")
    array = np.asarray(values, dtype=float)
    if array.shape != (12,):
        raise ValueError(f"{label} for '{key}' must contain 12 values")
    return array


def _optional_series(
    mapping: dict[str, list[float]],
    key: str,
) -> np.ndarray | None:
    values = mapping.get(key)
    if values is None:
        return None
    array = np.asarray(values, dtype=float)
    if array.shape != (12,):
        raise ValueError(f"Monthly series for '{key}' must contain 12 values")
    return array


def _zone_internal_gain_density(
    project: BuildingProject,
    zone: ThermalZone,
    settings: PolishCertificateMonthlySettings,
) -> float:
    explicit = settings.internal_gain_density_w_m2_by_zone.get(zone.id)
    if explicit is not None:
        return float(explicit)
    normative = project.internal_gains.normative_power_density_w_m2
    if normative is None:
        raise ValueError(f"Formal monthly calculation requires q_int for zone '{zone.id}'")
    return float(normative)


def _monthly_solar_gains_kwh(
    project: BuildingProject,
    zone: ThermalZone,
    settings: PolishCertificateMonthlySettings,
) -> np.ndarray:
    gains = np.zeros(12, dtype=float)
    for element in project.transparent_building_elements:
        if element.zone_id != zone.id:
            continue
        irradiation = _series(
            settings.solar_irradiation_kwh_m2_by_element,
            element.id,
            "monthly solar irradiation [kWh/m²]",
        )
        glazing_share = 1.0 - float(element.frame_factor)
        gains += (
            float(element.area)
            * glazing_share
            * float(element.g_value)
            * float(element.shading_factor)
            * irradiation
        )
    return gains


def _monthly_adjacent_temperature(
    project: BuildingProject,
    element_id: str,
    adjacent_type: AdjacentSpaceType,
    settings: PolishCertificateMonthlySettings,
) -> np.ndarray | None:
    if adjacent_type == AdjacentSpaceType.OUTDOOR:
        return np.asarray(settings.monthly_outdoor_temperature_c, dtype=float)
    if adjacent_type == AdjacentSpaceType.GROUND:
        return _series(
            settings.ground_adjacent_temperature_c_by_element,
            element_id,
            "monthly ground-side temperature [°C]",
        )
    if adjacent_type == AdjacentSpaceType.UNHEATED_ZONE:
        return _series(
            settings.unheated_adjacent_temperature_c_by_element,
            element_id,
            "monthly unheated-space temperature [°C]",
        )
    if adjacent_type == AdjacentSpaceType.HEATED_ZONE:
        return None
    element = next(item for item in project.opaque_building_elements if item.id == element_id)
    if element.adjacent_temperature is None:
        raise ValueError(
            f"Element '{element_id}' requires adjacent_temperature in formal calculation"
        )
    return np.full(12, float(element.adjacent_temperature), dtype=float)


def _monthly_transmission_kwh(
    project: BuildingProject,
    zone: ThermalZone,
    indoor_temperature_c: np.ndarray,
    settings: PolishCertificateMonthlySettings,
) -> np.ndarray:
    outdoor = np.asarray(settings.monthly_outdoor_temperature_c, dtype=float)
    transfer = np.zeros(12, dtype=float)

    for element in project.opaque_building_elements:
        if element.zone_id != zone.id:
            continue
        adjacent = _monthly_adjacent_temperature(
            project,
            element.id,
            element.adjacent_space_type,
            settings,
        )
        if adjacent is None:
            continue
        transfer += (
            float(element.area)
            * float(element.u_value)
            * (indoor_temperature_c - adjacent)
            * HOURS_PER_MONTH
            / 1000.0
        )

    for element in project.transparent_building_elements:
        if element.zone_id != zone.id:
            continue
        transfer += (
            float(element.area)
            * float(element.u_value)
            * (indoor_temperature_c - outdoor)
            * HOURS_PER_MONTH
            / 1000.0
        )

    bridge_h_w_k = 0.0
    for bridge in project.thermal_bridges.linear_bridges:
        if bridge.zone_id == zone.id:
            bridge_h_w_k += float(bridge.psi_value) * float(bridge.length)
    for bridge in project.thermal_bridges.point_bridges:
        if bridge.zone_id == zone.id:
            bridge_h_w_k += float(bridge.chi_value) * int(bridge.count)
    transfer += bridge_h_w_k * (indoor_temperature_c - outdoor) * HOURS_PER_MONTH / 1000.0
    return transfer


def _zone_beta(
    project: BuildingProject,
    zone: ThermalZone,
    settings: PolishCertificateMonthlySettings,
) -> np.ndarray:
    explicit = _optional_series(settings.beta_by_zone, zone.id)
    if explicit is not None:
        return explicit
    profile = _enum_value(project.general.dhw_usage_profile)
    if profile in CONTINUOUS_VENTILATION_PROFILES:
        return np.ones(12, dtype=float)
    if project.ventilation.usage_share_beta is not None:
        return np.full(12, float(project.ventilation.usage_share_beta), dtype=float)
    raise ValueError(f"Formal monthly calculation requires monthly beta for zone '{zone.id}'")


def _zone_base_airflow_m3h(
    project: BuildingProject,
    zone: ThermalZone,
    conditioned_area: float,
) -> tuple[float, bool]:
    ventilation = project.ventilation
    if ventilation.airflow_rate > 0.0:
        share = zone.floor_area / conditioned_area if conditioned_area > 0.0 else 0.0
        return float(ventilation.airflow_rate * share), True
    profile = _enum_value(project.general.dhw_usage_profile)
    density = NORMATIVE_AIRFLOW_M3_S_M2.get(profile)
    if density is None:
        raise ValueError(f"No regulatory basic airflow is available for usage profile '{profile}'")
    return float(density * zone.floor_area * 3600.0), False


def _monthly_effective_ventilation_flow_m3h(
    project: BuildingProject,
    zone: ThermalZone,
    conditioned_area: float,
    settings: PolishCertificateMonthlySettings,
) -> tuple[np.ndarray, bool]:
    ventilation = project.ventilation
    vtype = ventilation.ventilation_type
    if vtype == VentilationType.NONE:
        return np.zeros(12, dtype=float), False

    base, explicit_base = _zone_base_airflow_m3h(project, zone, conditioned_area)
    beta = _zone_beta(project, zone, settings)
    profile = _enum_value(project.general.dhw_usage_profile)
    continuous = profile in CONTINUOUS_VENTILATION_PROFILES
    infiltration_rate = (
        float(ventilation.infiltration_rate)
        if "infiltration_rate" in ventilation.model_fields_set
        else normative_infiltration_rate(project.general.construction_year)
    )
    infiltration = infiltration_rate * zone.volume
    fan_infiltration = float(ventilation.fan_infiltration_rate) * zone.volume

    if vtype == VentilationType.NATURAL:
        if continuous:
            return np.full(12, base + infiltration), False
        return (beta + 0.2 * (1.0 - beta)) * base + infiltration, False

    if vtype in {VentilationType.EXHAUST, VentilationType.HYBRID}:
        if continuous:
            return np.full(12, base + fan_infiltration), False
        return (
            beta * (base + fan_infiltration) + (1.0 - beta) * (0.1 * base + infiltration)
        ), False

    if vtype in {
        VentilationType.MECHANICAL,
        VentilationType.MECHANICAL_WITH_RECOVERY,
    }:
        if explicit_base:
            reduction = np.ones(12, dtype=float)
            used_default_reduction = False
        else:
            reduction = _optional_series(
                settings.supply_extract_reduction_by_zone,
                zone.id,
            )
            if reduction is None:
                reduction = np.full(12, 0.75, dtype=float)
                used_default_reduction = True
            else:
                used_default_reduction = False
        supply = base * reduction
        if vtype == VentilationType.MECHANICAL_WITH_RECOVERY:
            recovery = _series(
                settings.recovery_effectiveness_by_zone,
                zone.id,
                "monthly heat-recovery effectiveness",
            )
        else:
            recovery = np.zeros(12, dtype=float)
        operating = (1.0 - recovery) * supply + fan_infiltration
        if continuous:
            return operating, used_default_reduction
        return (
            beta * operating + (1.0 - beta) * infiltration,
            used_default_reduction,
        )

    raise ValueError(f"Unsupported ventilation type: {vtype}")


def _monthly_ventilation_kwh(
    project: BuildingProject,
    zone: ThermalZone,
    indoor_temperature_c: np.ndarray,
    conditioned_area: float,
    settings: PolishCertificateMonthlySettings,
) -> tuple[np.ndarray, bool]:
    outdoor = np.asarray(settings.monthly_outdoor_temperature_c, dtype=float)
    flow_m3h, default_reduction = _monthly_effective_ventilation_flow_m3h(
        project,
        zone,
        conditioned_area,
        settings,
    )
    h_ve = flow_m3h / 3600.0 * CP_AIR_VOLUMETRIC_J_M3K
    return (
        h_ve * (indoor_temperature_c - outdoor) * HOURS_PER_MONTH / 1000.0,
        default_reduction,
    )


def _zone_monthly_useful_energy(
    project: BuildingProject,
    zone: ThermalZone,
    conditioned_area: float,
    settings: PolishCertificateMonthlySettings,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, bool]:
    solar = _monthly_solar_gains_kwh(project, zone, settings)
    q_int = _zone_internal_gain_density(project, zone, settings)
    internal = q_int * zone.floor_area * HOURS_PER_MONTH / 1000.0
    gains = solar + internal
    heating = np.zeros(12, dtype=float)
    cooling = np.zeros(12, dtype=float)
    report_tr = np.zeros(12, dtype=float)
    report_ve = np.zeros(12, dtype=float)
    used_default_reduction = False

    if zone.zone_type in HEATED_ZONE_TYPES:
        override = _optional_series(settings.heating_useful_override_kwh_by_zone, zone.id)
        if override is not None:
            heating = np.maximum(override, 0.0)
        else:
            tint_h = _series(
                settings.heating_internal_temperature_c_by_zone,
                zone.id,
                "monthly heating internal temperature",
            )
            eta_gains = _series(
                settings.heating_gain_utilization_by_zone,
                zone.id,
                "monthly heating gain-utilization factor",
            )
            qtr_h = _monthly_transmission_kwh(project, zone, tint_h, settings)
            qve_h, fallback = _monthly_ventilation_kwh(
                project,
                zone,
                tint_h,
                conditioned_area,
                settings,
            )
            used_default_reduction |= fallback
            heating = np.maximum(qtr_h + qve_h - eta_gains * gains, 0.0)
            report_tr += qtr_h
            report_ve += qve_h

    if zone.zone_type in COOLED_ZONE_TYPES:
        override = _optional_series(settings.cooling_useful_override_kwh_by_zone, zone.id)
        if override is not None:
            cooling = np.maximum(override, 0.0)
        else:
            tint_c = _series(
                settings.cooling_internal_temperature_c_by_zone,
                zone.id,
                "monthly cooling internal temperature",
            )
            eta_losses = _series(
                settings.cooling_loss_utilization_by_zone,
                zone.id,
                "monthly cooling loss-utilization factor",
            )
            qtr_c = _monthly_transmission_kwh(project, zone, tint_c, settings)
            qve_c, fallback = _monthly_ventilation_kwh(
                project,
                zone,
                tint_c,
                conditioned_area,
                settings,
            )
            used_default_reduction |= fallback
            cooling = np.maximum(gains - eta_losses * (qtr_c + qve_c), 0.0)
            if zone.zone_type not in HEATED_ZONE_TYPES:
                report_tr += qtr_c
                report_ve += qve_c

    return heating, cooling, internal, solar, report_tr, report_ve, used_default_reduction


def _dhw_final_energy_wh(
    project: BuildingProject, dhw_useful_wh: float
) -> tuple[float, float | None]:
    """Return (final energy [Wh], total efficiency ηW,tot or None)."""
    system = project.systems.dhw
    if _enum_value(system.system_type) == "none":
        return 0.0, None
    generation = core._generation_efficiency(system, default=0.96)
    tank_kind = (
        "electric"
        if _enum_value(system.system_type) in {"electric_storage", "electric_instantaneous"}
        else ("gas" if "gas" in _enum_value(system.system_type) else "indirect")
    )
    if system.storage_volume_dm3 is not None:
        if system.storage_location is None:
            raise ValueError("storage_location is required for DHW storage")
        standby = dhw_storage_standby_loss_kwh(
            system.storage_volume_dm3,
            location=system.storage_location,
            tank_kind=tank_kind,
            insulation_mm=system.storage_insulation_mm,
        )
        delta_d_kwh = dhw_useful_wh / 1000.0 * (1.0 / system.distribution_efficiency - 1.0)
        e_k = float((dhw_useful_wh / 1000.0 + delta_d_kwh + standby) * 1000.0 / generation)
        # Gdy straty zasobnika z tabeli 13, ηW,tot nie jest prostym iloczynem.
        total_eff = float(dhw_useful_wh / e_k) if e_k > 0.0 else None
        return e_k, total_eff
    total_efficiency = (
        generation
        * system.storage_efficiency
        * system.distribution_efficiency
        * system.utilization_efficiency
    )
    return float(dhw_useful_wh / total_efficiency), float(total_efficiency)


def _final_energy_by_carrier(
    project: BuildingProject,
    heating_useful_wh: float,
    cooling_useful_wh: float,
    dhw_useful_wh: float,
    settings: PolishCertificateMonthlySettings,
    fan_hours: float,
) -> tuple[dict[str, float], float | None, float]:
    """Return (final by carrier, dhw_total_efficiency, dhw_aux_wh)."""
    final: dict[str, float] = {}
    heating = project.systems.heating
    if _enum_value(heating.system_type) != "none":
        efficiency = core._total_system_efficiency(
            heating,
            core._generation_efficiency(heating),
        )
        carrier = core._system_carrier(heating)
        final[carrier] = final.get(carrier, 0.0) + heating_useful_wh / efficiency

    cooling = project.systems.cooling
    if cooling is not None and _enum_value(cooling.system_type) != "none":
        efficiency = core._total_system_efficiency(
            cooling,
            core._generation_efficiency(cooling),
        )
        carrier = core._system_carrier(cooling)
        final[carrier] = final.get(carrier, 0.0) + cooling_useful_wh / efficiency

    dhw = project.systems.dhw
    dhw_total_efficiency: float | None = None
    if _enum_value(dhw.system_type) != "none":
        carrier = core._system_carrier(dhw)
        e_k_dhw, dhw_total_efficiency = _dhw_final_energy_wh(project, dhw_useful_wh)
        final[carrier] = final.get(carrier, 0.0) + e_k_dhw

    area = float(project.general.conditioned_floor_area)
    electric_aux_wh = 0.0
    dhw_aux_wh = 0.0
    if _enum_value(heating.system_type) != "none":
        explicit = core._explicit_auxiliary_energy_wh(heating)
        electric_aux_wh += (
            explicit
            if explicit is not None
            else heating_auxiliary_demand_wh(
                _enum_value(heating.system_type),
                area,
                installation_type=heating.installation_type,
            )
        )
    if cooling is not None and _enum_value(cooling.system_type) != "none":
        explicit = core._explicit_auxiliary_energy_wh(cooling)
        if explicit is not None:
            electric_aux_wh += explicit
    if _enum_value(dhw.system_type) != "none":
        dhw_explicit = core._explicit_auxiliary_energy_wh(dhw)
        dhw_aux_wh = (
            dhw_explicit
            if dhw_explicit is not None
            else dhw_auxiliary_demand_wh(
                _enum_value(dhw.system_type),
                area,
                distribution_type=_enum_value(dhw.distribution_type),
            )
        )
        electric_aux_wh += dhw_aux_wh

    ventilation = project.ventilation
    if ventilation.ventilation_type in {
        VentilationType.MECHANICAL,
        VentilationType.MECHANICAL_WITH_RECOVERY,
        VentilationType.EXHAUST,
        VentilationType.HYBRID,
    }:
        fan_power = float(ventilation.mechanical_fan_power or 0.0)
        if fan_power == 0.0:
            airflow = max(float(ventilation.airflow_rate), 0.0)
            if airflow == 0.0:
                profile = _enum_value(project.general.dhw_usage_profile)
                density = NORMATIVE_AIRFLOW_M3_S_M2.get(profile)
                if density is None:
                    raise ValueError(f"No fan airflow fallback for profile '{profile}'")
                airflow = density * area * 3600.0
            ach = airflow / project.general.heated_volume
            fan_power = (
                ventilation_fan_power_w_m2(
                    _enum_value(ventilation.ventilation_type),
                    ach,
                )
                * area
            )
        electric_aux_wh += fan_power * fan_hours

    if settings.preheater_electricity_kwh_by_month:
        electric_aux_wh += float(sum(settings.preheater_electricity_kwh_by_month)) * 1000.0

    leni = project.general.lighting_indicator_leni
    if leni is not None and project.general.building_type != BuildingType.RESIDENTIAL:
        lighting_area = project.general.lighting_area_m2 or area
        electric_aux_wh += leni * lighting_area * 1000.0

    final["electricity"] = final.get("electricity", 0.0) + electric_aux_wh
    return final, dhw_total_efficiency, dhw_aux_wh


def _formal_fan_hours(
    project: BuildingProject,
    settings: PolishCertificateMonthlySettings,
) -> float:
    if project.ventilation.ventilation_type not in {
        VentilationType.MECHANICAL,
        VentilationType.MECHANICAL_WITH_RECOVERY,
        VentilationType.EXHAUST,
        VentilationType.HYBRID,
    }:
        return 0.0
    conditioned = [
        zone
        for zone in project.thermal_zones
        if zone.zone_type in HEATED_ZONE_TYPES | COOLED_ZONE_TYPES
    ]
    total_area = sum(zone.floor_area for zone in conditioned)
    if total_area <= 0.0:
        return 0.0
    weighted_beta = np.zeros(12, dtype=float)
    for zone in conditioned:
        weighted_beta += _zone_beta(project, zone, settings) * zone.floor_area / total_area
    return float(np.sum(weighted_beta * HOURS_PER_MONTH))


def calculate_polish_monthly_certificate(
    project: BuildingProject,
    settings: PolishCertificateMonthlySettings,
) -> PolishMonthlyCertificateResult:
    """Calculate formal annual indicators from the monthly regulation method."""
    if not settings.enabled:
        raise ValueError("Polish monthly certificate engine is not enabled")
    if not settings.official_bip_climate_data:
        raise ValueError(
            "Formal certificate calculation requires climate data from the official "
            "Polish ministerial BIP source for the selected meteorological station"
        )

    area = float(project.general.conditioned_floor_area)
    total_h = np.zeros(12, dtype=float)
    total_c = np.zeros(12, dtype=float)
    total_int = np.zeros(12, dtype=float)
    total_sol = np.zeros(12, dtype=float)
    total_tr = np.zeros(12, dtype=float)
    total_ve = np.zeros(12, dtype=float)
    default_rn_used = False

    for zone in project.thermal_zones:
        if zone.zone_type not in HEATED_ZONE_TYPES | COOLED_ZONE_TYPES:
            continue
        h, c, qint, qsol, qtr, qve, fallback_rn = _zone_monthly_useful_energy(
            project,
            zone,
            area,
            settings,
        )
        total_h += h
        total_c += c
        total_int += qint
        total_sol += qsol
        total_tr += qtr
        total_ve += qve
        default_rn_used |= fallback_rn

    dhw_useful_wh = (
        annual_dhw_useful_energy(
            area,
            project.general.dhw_usage_profile,
        )
        if _enum_value(project.systems.dhw.system_type) != "none"
        else 0.0
    )
    monthly_dhw_kwh = dhw_useful_wh / 1000.0 * DAYS_PER_MONTH / 365.0
    heating_useful_wh = float(np.sum(total_h)) * 1000.0
    cooling_useful_wh = float(np.sum(total_c)) * 1000.0
    fan_hours = _formal_fan_hours(project, settings)
    final, dhw_total_efficiency, dhw_aux_wh = _final_energy_by_carrier(
        project,
        heating_useful_wh,
        cooling_useful_wh,
        dhw_useful_wh,
        settings,
        fan_hours,
    )
    final_total_wh = sum(final.values())
    primary_wh, emissions_t = annual_primary_energy(final, project.primary_energy)
    useful_total_wh = heating_useful_wh + cooling_useful_wh + dhw_useful_wh

    indicators = AnnualIndicators(
        eu_kwh_m2_year=useful_total_wh / 1000.0 / area,
        ek_kwh_m2_year=final_total_wh / 1000.0 / area,
        ep_kwh_m2_year=primary_wh / 1000.0 / area,
        ec_tco2_m2_year=emissions_t / area,
        u_oze_percent=share_of_renewable_energy(final),
        heating_kwh_m2_year=heating_useful_wh / 1000.0 / area,
        cooling_kwh_m2_year=cooling_useful_wh / 1000.0 / area,
        dhw_kwh_m2_year=dhw_useful_wh / 1000.0 / area,
        dhw_total_efficiency=dhw_total_efficiency,
        dhw_auxiliary_energy_kwh_year=dhw_aux_wh / 1000.0,
    )

    monthly = tuple(
        MonthlyResult(
            month=month + 1,
            heating_kwh=float(total_h[month]),
            cooling_kwh=float(total_c[month]),
            dhw_kwh=float(monthly_dhw_kwh[month]),
            internal_gains_kwh=float(total_int[month]),
            solar_gains_kwh=float(total_sol[month]),
            transmission_losses_kwh=float(total_tr[month]),
            ventilation_losses_kwh=float(total_ve[month]),
        )
        for month in range(12)
    )

    checks = [
        ComplianceCheck(
            name="Informacja normatywna: POLISH_CERTIFICATE_MONTHLY_METHOD",
            passed=True,
            message=(
                "Formal Eu/Ek/Ep use the monthly balance prescribed by Annex 1 "
                "of the Polish methodology regulation. The 8760-hour ISO 52016 "
                "result remains a separate analytical result."
            ),
        )
    ]
    if default_rn_used:
        checks.append(
            ComplianceCheck(
                name="Informacja normatywna: SUPPLY_EXTRACT_RN_FALLBACK",
                passed=True,
                message=(
                    "No project-specific monthly supply/extract reduction factor rn "
                    "was supplied for at least one zone; the regulatory fallback "
                    "rn=0.75 was used."
                ),
            )
        )

    return PolishMonthlyCertificateResult(
        annual_indicators=indicators,
        monthly=monthly,
        compliance=tuple(checks),
        final_energy_by_carrier_wh=final,
        heating_useful_kwh=heating_useful_wh / 1000.0,
        cooling_useful_kwh=cooling_useful_wh / 1000.0,
        dhw_useful_kwh=dhw_useful_wh / 1000.0,
    )
