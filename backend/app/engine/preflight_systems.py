"""Technical-system preflight rules and explicit modelling-assumption checks."""

from __future__ import annotations

from math import isclose

from app.engine.preflight_geometry import audit_check, enum_value
from app.schemas.models import BuildingProject, ComplianceCheck

HYDRONIC_HEATING_SOURCES = {
    "gas_boiler",
    "gas_condensing",
    "oil_boiler",
    "biomass_boiler",
    "coal_boiler",
    "heat_pump_air",
    "heat_pump_ground",
    "heat_pump_water",
    "district_heating",
}
DHW_STORAGE_SOURCES = {
    "electric_storage",
    "heat_pump_air",
    "heat_pump_ground",
    "heat_pump_water",
    "district_heating",
}


def system_preflight(project: BuildingProject) -> list[ComplianceCheck]:
    checks: list[ComplianceCheck] = []
    heating = project.systems.heating
    heating_type = enum_value(heating.system_type)
    if heating_type != "none":
        explicit_aux = getattr(heating, "auxiliary_energy_kwh_year", None)
        installation = str(getattr(heating, "installation_type", None) or "").strip()
        if heating_type in HYDRONIC_HEATING_SOURCES and explicit_aux is None and not installation:
            checks.append(
                audit_check(
                    "HEATING_INSTALLATION_NOT_CLASSIFIED",
                    "No heating installation type and no explicit auxiliary electricity were provided. "
                    "Select an installation type or enter auxiliary_energy_kwh_year before treating EK/EP as final.",
                )
            )
    dhw = project.systems.dhw
    dhw_type = enum_value(dhw.system_type)
    if dhw_type in DHW_STORAGE_SOURCES and dhw_type != "none":
        volume = getattr(dhw, "storage_volume_dm3", None)
        storage_eff = float(getattr(dhw, "storage_efficiency", 1.0))
        if volume is None and isclose(storage_eff, 1.0, rel_tol=0.0, abs_tol=1e-9):
            checks.append(
                audit_check(
                    "DHW_STORAGE_LOSSES_NOT_DEFINED",
                    "The selected DHW source normally includes storage, but no tank geometry was supplied and ηW,s=1.000. "
                    "Enter tank data or an explicit non-unity storage efficiency.",
                )
            )
        elif volume is None:
            checks.append(
                audit_check(
                    "DHW_STORAGE_MANUAL_EFFICIENCY",
                    f"No tank geometry was supplied; storage losses use ηW,s={storage_eff:.3f}.",
                    passed=True,
                )
            )
    if not project.thermal_bridges.linear_bridges and not project.thermal_bridges.point_bridges:
        checks.append(
            audit_check(
                "THERMAL_BRIDGES_NOT_ENTERED",
                "No linear or point thermal bridges were entered. H_bridge=0 W/K is used and may understate transmission losses.",
            )
        )
    return checks


def _iso52016_checks(project: BuildingProject) -> list[ComplianceCheck]:
    raw = project.metadata.get("normative", {}) if isinstance(project.metadata, dict) else {}
    hourly = raw.get("hourly_iso52016", {}) if isinstance(raw, dict) else {}
    strict = (
        bool(hourly.get("strict_conformance") or hourly.get("certificate_mode"))
        if isinstance(hourly, dict)
        else False
    )
    checks: list[ComplianceCheck] = []
    if strict:
        checks.append(
            audit_check(
                "ISO52016_STRICT_INPUT_MODE",
                "PN-EN ISO 52016-1 strict input mode is enabled. Missing EPB-delegated surface, construction, sky, ground or zone-capacity inputs cause calculation failure instead of silent defaults.",
                passed=True,
            )
        )
    else:
        checks.append(
            audit_check(
                "ISO52016_COMPATIBILITY_INPUT_MODE",
                "The hourly ISO 52016 solver may infer compatibility values for missing EPB-delegated inputs. "
                "The resulting analytical run must not be labelled fully conformant until strict_conformance=true succeeds.",
            )
        )

    legacy_resistance_elements = [
        element.name
        for element in project.opaque_building_elements
        if getattr(element, "thermal_node_resistances_m2k_w", None) is not None
        and len(element.thermal_node_resistances_m2k_w) == 6
    ]
    if legacy_resistance_elements:
        checks.append(
            audit_check(
                "ISO52016_LEGACY_SURFACE_FILM_RESISTANCES",
                "Six-resistance legacy construction data include surface films and are accepted only for compatibility. "
                "Strict ISO 52016 uses four core resistances plus explicit h_ci/h_ri/h_ce/h_re. Affected: "
                + ", ".join(legacy_resistance_elements),
            )
        )
    if any(
        enum_value(element.adjacent_space_type) == "unheated_zone"
        for element in project.opaque_building_elements
    ):
        checks.append(
            audit_check(
                "ISO52016_UNHEATED_ADJACENT_ZONE_INPUT",
                "Elements adjacent to an unconditioned zone require the 6.5.9 adjacent-zone temperature method or a verified boundary profile. "
                "A heuristic fixed offset cannot be treated as a strict ISO 52016 input.",
            )
        )
    return checks


def model_limit_checks(project: BuildingProject) -> list[ComplianceCheck]:
    checks: list[ComplianceCheck] = []
    checks.extend(_iso52016_checks(project))
    if any(
        enum_value(element.adjacent_space_type) == "ground"
        for element in project.opaque_building_elements
    ):
        checks.append(
            audit_check(
                "GROUND_MODEL_SIMPLIFIED",
                "Without certificate-grade ground settings, ground elements retain a diagnostic periodic boundary. "
                "Strict ISO 52016 requires the ISO 13370/13789 virtual-ground resistance and monthly virtual temperatures.",
            )
        )
    ventilation = project.ventilation
    vent_type = enum_value(ventilation.ventilation_type)
    recovery = float(ventilation.heat_recovery_efficiency)
    if vent_type == "mechanical_with_recovery" and recovery > 0.0:
        checks.append(
            audit_check(
                "HEAT_RECOVERY_CONSTANT_EFFICIENCY",
                f"Without the detailed recovery model, heat recovery is represented by constant η={recovery:.3f}; frost, bypass and manufacturer maps are not represented.",
            )
        )
    if enum_value(project.systems.heating.system_type) != "none":
        checks.append(
            audit_check(
                "DESIGN_POWER_TMY_PEAK",
                "The legacy design_heating_power diagnostic is a TMY peak. Formal design load must use either the separate PN-EN 12831-1 room path or the ISO 52016 design-weather sequence procedure.",
            )
        )
    airflow = float(ventilation.airflow_rate)
    beta = ventilation.usage_share_beta
    airflow_origin = "normative fallback requested" if airflow == 0.0 else "explicit"
    checks.append(
        audit_check(
            "VENTILATION_INPUTS",
            f"Ventilation inputs: type={vent_type}, airflow={airflow:.2f} m³/h ({airflow_origin}), "
            f"infiltration={float(ventilation.infiltration_rate):.3f} 1/h, heat recovery={recovery:.3f}, "
            f"beta={beta if beta is not None else 'profile default'}.",
            passed=True,
        )
    )
    electricity_fp = float(project.primary_energy.electricity.fp)
    checks.append(
        audit_check(
            "PRIMARY_ENERGY_FACTOR",
            f"Electricity primary-energy factor used by this project: wi={electricity_fp:.3f}. Verify carrier factors against the legal basis applicable on the certificate date.",
            passed=True,
        )
    )
    return checks


def normalise_renewable_carriers(project: BuildingProject) -> None:
    return None
