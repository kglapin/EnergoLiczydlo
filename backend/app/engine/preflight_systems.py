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
    """Expose missing inputs that can suppress losses in the current core."""
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
                    "The core can therefore omit receiver-side circulation-pump electricity. Select an "
                    "installation type or enter auxiliary_energy_kwh_year before treating EK/EP as final.",
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
                    "The selected DHW source normally includes storage, but no tank geometry was supplied "
                    "and ηW,s=1.000. Standby storage losses are therefore zero in the numerical result. "
                    "Enter tank volume/location/insulation or an explicit non-unity storage efficiency.",
                )
            )
        elif volume is None:
            checks.append(
                audit_check(
                    "DHW_STORAGE_MANUAL_EFFICIENCY",
                    f"No tank geometry was supplied; storage losses are represented by the explicit "
                    f"seasonal storage efficiency ηW,s={storage_eff:.3f}.",
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


def model_limit_checks(project: BuildingProject) -> list[ComplianceCheck]:
    """Report important simplifications that cannot be inferred away safely."""
    checks: list[ComplianceCheck] = []
    if any(
        enum_value(element.adjacent_space_type) == "ground"
        for element in project.opaque_building_elements
    ):
        checks.append(
            audit_check(
                "GROUND_MODEL_SIMPLIFIED",
                "Ground-coupled elements use the documented periodic ground-temperature approximation, "
                "not a complete PN-EN ISO 13370 equivalent-slab model. Treat this as a modelling limitation for formal certification.",
            )
        )

    ventilation = project.ventilation
    vent_type = enum_value(ventilation.ventilation_type)
    if vent_type == "mechanical_with_recovery" and float(ventilation.heat_recovery_efficiency) > 0.0:
        checks.append(
            audit_check(
                "HEAT_RECOVERY_CONSTANT_EFFICIENCY",
                f"Heat recovery is represented by a constant efficiency η={float(ventilation.heat_recovery_efficiency):.3f}; "
                "frost protection, summer bypass and manufacturer performance curves are not modelled by the current input schema.",
            )
        )

    if enum_value(project.systems.heating.system_type) != "none":
        checks.append(
            audit_check(
                "DESIGN_POWER_TMY_PEAK",
                "design_heating_power_kw is based on the maximum hourly transmission+ventilation loss in the selected TMY series. "
                "It must not be treated as a substitute for a separate design heat-load calculation using the applicable design outdoor temperature.",
            )
        )

    airflow = float(ventilation.airflow_rate)
    beta = ventilation.usage_share_beta
    checks.append(
        audit_check(
            "VENTILATION_INPUTS",
            f"Ventilation inputs before core fallbacks: type={vent_type}, airflow={airflow:.2f} m³/h "
            f"({'normative fallback requested' if airflow == 0.0 else 'explicit'}), "
            f"infiltration={float(ventilation.infiltration_rate):.3f} 1/h, "
            f"heat recovery={float(ventilation.heat_recovery_efficiency):.3f}, "
            f"beta={beta if beta is not None else 'profile default'}.",
            passed=True,
        )
    )
    checks.append(
        audit_check(
            "PRIMARY_ENERGY_FACTOR",
            f"Electricity primary-energy factor used by this project: wi={float(project.primary_energy.electricity.fp):.3f}. "
            "Verify all carrier factors against the legal basis applicable on the certificate date.",
            passed=True,
        )
    )
    return checks


def normalise_renewable_carriers(project: BuildingProject) -> None:
    """Compatibility hook retained for the audited pipeline.

    Renewable-share handling is fixed directly in ``primary_energy.py`` for
    biomass, biogas, solar, wind, geothermal and the legacy renewable bucket,
    so carrier names no longer need to be rewritten on the calculation copy.
    """
    return None
