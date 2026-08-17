"""Runtime calculator with audited PN-EN ISO 52016-1 hourly integration.

The public audited path selects the detailed nodal solver by default; direct
legacy calls may still opt into the historical reduced model.  Detailed heat
recovery is iterated with solved extract-air temperature.  When requested,
clause 6.5.14 moisture/latent loads are solved after the sensible state.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_LEGACY_NAME = "app.engine._legacy_calculator"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "calculator.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load legacy calculator from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)
for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)

from app.engine.climate import radiation_on_surface
from app.engine.heat_recovery import detailed_heat_recovery_settings
from app.engine.iso52016_hourly import solve_zone_iso52016
from app.engine.iso52016_moisture import humidity_ratio_from_rh, solve_zone_moisture
from app.engine.normative_models import load_normative_settings
from app.engine.solar import total_solar_gains
from app.engine.thermal_balance import solve_zone_5r1c, zone_thermal_properties
from app.engine.ventilation import (
    ventilation_airflow_components,
    ventilation_effective_supply_temperature,
    ventilation_heat_loss,
    ventilation_heat_transfer_coefficient,
)
from app.schemas.models import AdjacentSpaceType


def _raw_opaque_solar_absorption(opaque, df) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    for element in opaque:
        if element.adjacent_space_type != AdjacentSpaceType.OUTDOOR:
            result[element.id] = np.zeros(len(df), dtype=float)
            continue
        irradiance = radiation_on_surface(
            df,
            surface_tilt=float(element.inclination),
            surface_azimuth=float(element.orientation_azimuth),
        )
        result[element.id] = (
            float(element.area)
            * float(element.solar_absorptance)
            * np.asarray(irradiance, dtype=float)
        )
    return result


def _setpoints(zone):
    heating = zone.setpoint_heating if zone.zone_type in HEATED_ZONE_TYPES else None
    cooling = zone.setpoint_cooling if zone.zone_type in COOLED_ZONE_TYPES and zone.setpoint_cooling is not None else None
    return heating, cooling


def _detailed_hourly_enabled(project, settings) -> bool:
    normative = project.metadata.get("normative", {})
    if isinstance(normative, dict):
        hourly = normative.get("hourly_iso52016", {})
        if isinstance(hourly, dict) and "enabled" in hourly:
            return bool(settings.hourly_iso52016.enabled)
    return getattr(project, "_normative_settings", None) is not None


def _hourly_value(value, n: int) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    return np.full(n, float(array), dtype=float) if array.ndim == 0 else array


def _physical_incoming_airflow_m3h(ventilation, zone, building_floor_area, operation_profile, n: int) -> np.ndarray:
    """Return physical incoming outdoor-air flow for the moisture balance.

    Detailed recovery mode already preserves the physical mechanical flow.  In
    the legacy scalar-recovery mode undo only the historical sensible
    ``1-eta`` reduction; moisture transport itself is never reduced by sensible
    heat-recovery efficiency.
    """
    mechanical, external = ventilation_airflow_components(
        ventilation, zone, building_floor_area, operation_profile
    )
    mechanical = _hourly_value(mechanical, n)
    external = _hourly_value(external, n)
    if (
        str(getattr(ventilation.ventilation_type, "value", ventilation.ventilation_type))
        == "mechanical_with_recovery"
        and detailed_heat_recovery_settings(ventilation) is None
        and ventilation.supply_temperature is None
        and ventilation.heat_recovery_efficiency < 1.0
    ):
        mechanical = mechanical / max(1.0 - float(ventilation.heat_recovery_efficiency), 1e-9)
    return np.maximum(mechanical + external, 0.0)


def _moisture_result(zone, df, project, ventilation, operation_profile, building_floor_area, solution, settings):
    moisture = settings.moisture_iso52016
    if not moisture.enabled:
        return None
    if "RH" not in df.columns:
        raise ValueError("ISO 52016 moisture calculation requires outdoor relative humidity")
    pressure = (
        df["P_atm"].to_numpy(dtype=float)
        if "P_atm" in df.columns
        else np.full(len(df), 101325.0, dtype=float)
    )
    if moisture.strict_conformance and "P_atm" not in df.columns:
        raise ValueError("Strict ISO 52016 moisture calculation requires atmospheric pressure")
    outdoor_rh = df["RH"].to_numpy(dtype=float)
    if np.nanmax(outdoor_rh) > 1.0:
        outdoor_rh = outdoor_rh / 100.0
    x_out = humidity_ratio_from_rh(df["T_e"].to_numpy(dtype=float), outdoor_rh, pressure)
    generation = moisture.moisture_generation_kg_s_by_zone.get(
        zone.id, zone.moisture_generation_kg_s
    )
    if generation is None:
        if moisture.strict_conformance:
            raise ValueError(
                f"Strict ISO 52016 moisture calculation requires moisture generation for zone '{zone.id}'"
            )
        generation = 0.0
    if moisture.strict_conformance and (
        zone.relative_humidity_min is None and zone.relative_humidity_max is None
    ):
        raise ValueError(
            f"Strict ISO 52016 moisture calculation requires a humidity setpoint for zone '{zone.id}'"
        )
    airflow = _physical_incoming_airflow_m3h(
        ventilation, zone, building_floor_area, operation_profile, len(df)
    )
    return solve_zone_moisture(
        zone_volume_m3=float(zone.volume),
        indoor_temperature_c=np.asarray(solution.t_air, dtype=float),
        incoming_airflow_m3h=airflow,
        supply_humidity_ratio=x_out,
        atmospheric_pressure_pa=pressure,
        relative_humidity_min=zone.relative_humidity_min,
        relative_humidity_max=zone.relative_humidity_max,
        moisture_generation_kg_s=float(generation),
        moisture_buffer_kg_s=float(moisture.moisture_buffer_kg_s_by_zone.get(zone.id, 0.0)),
        latent_heat_vaporization_j_kg=moisture.latent_heat_vaporization_j_kg,
    )


def _aggregate_zone_results(zone, df, project, building_floor_area: float, ventilation, operation_profile: np.ndarray):
    opaque = [element for element in project.opaque_building_elements if element.zone_id == zone.id]
    transparent = [element for element in project.transparent_building_elements if element.zone_id == zone.id]
    t_e = df["T_e"].to_numpy(dtype=float)
    network = zone_transmission_network(opaque, transparent, project.thermal_bridges, t_e, zone_id=zone.id)
    h_ve = ventilation_heat_transfer_coefficient(
        ventilation, zone, building_floor_area, operation_profile=operation_profile
    )
    q_sol_trans, q_sol_abs_reduced = total_solar_gains(transparent, opaque, df)
    q_solar_report = q_sol_trans + q_sol_abs_reduced
    q_int = total_internal_gains(
        zone.occupancy_density, zone.floor_area, project.internal_gains, df.index
    )
    t_set_heating, t_set_cooling = _setpoints(zone)
    settings = load_normative_settings(project)
    detailed_hourly = _detailed_hourly_enabled(project, settings)
    hourly = settings.hourly_iso52016
    recovery_is_detailed = detailed_heat_recovery_settings(ventilation) is not None
    extract_temperature: np.ndarray | None = None
    solution = None
    t_supply = t_e.copy()

    for _ in range(8):
        t_supply = ventilation_effective_supply_temperature(
            ventilation, zone, t_e,
            building_floor_area=building_floor_area,
            operation_profile=operation_profile,
            extract_temperature_c=extract_temperature,
        )
        if detailed_hourly:
            capacity_kj_m2k = hourly.air_furniture_heat_capacity_kj_m2k_by_zone.get(
                zone.id, zone.air_furniture_heat_capacity_kj_m2k
            )
            capacity_j_k = (
                None if capacity_kj_m2k is None
                else float(capacity_kj_m2k) * float(zone.floor_area) * 1000.0
            )
            solution = solve_zone_iso52016(
                opaque_elements=opaque,
                transparent_elements=transparent,
                bridges=project.thermal_bridges,
                zone_id=zone.id,
                h_ve=h_ve,
                t_e=t_e,
                phi_int=q_int,
                phi_sol_transparent=q_sol_trans,
                opaque_solar_absorbed_w_by_element=_raw_opaque_solar_absorption(opaque, df),
                t_set_heating=t_set_heating,
                t_set_cooling=t_set_cooling,
                t_supply=t_supply,
                internal_convective_fraction=hourly.internal_convective_fraction,
                solar_convective_fraction=hourly.solar_convective_fraction,
                hvac_convective_fraction=hourly.hvac_convective_fraction,
                operative_air_weight=(
                    float(zone.operative_air_weight)
                    if zone.operative_air_weight is not None
                    else hourly.operative_air_weight
                ),
                air_furniture_heat_capacity_j_k=capacity_j_k,
                floor_area_m2=zone.floor_area,
                sky_temperature_difference_k=(
                    hourly.sky_temperature_difference_k
                    if hourly.sky_temperature_difference_k is not None else 11.0
                ),
                solar_radiant_distribution=hourly.solar_radiant_distribution_by_zone.get(zone.id),
                max_heating_power_w=hourly.max_heating_power_w_by_zone.get(zone.id),
                max_cooling_power_w=hourly.max_cooling_power_w_by_zone.get(zone.id),
                require_explicit_construction_nodes=hourly.certificate_mode,
                strict_conformance=hourly.strict_conformance,
                max_warmup_cycles=hourly.max_warmup_cycles,
                warmup_tolerance_k=hourly.warmup_tolerance_k,
            )
        else:
            properties = zone_thermal_properties(zone.floor_area)
            solution = solve_zone_5r1c(
                network=network, h_ve=h_ve, t_e=t_e, phi_int=q_int,
                phi_sol=q_solar_report, properties=properties,
                t_set_heating=t_set_heating, t_set_cooling=t_set_cooling,
                t_supply=t_supply,
            )
        if not recovery_is_detailed:
            break
        solved_extract = np.asarray(solution.t_air, dtype=float)
        if extract_temperature is not None:
            residual = float(np.max(np.abs(solved_extract - extract_temperature)))
            if residual <= 0.01:
                extract_temperature = solved_extract
                break
            extract_temperature = 0.5 * extract_temperature + 0.5 * solved_extract
        else:
            extract_temperature = solved_extract
    if solution is None:  # pragma: no cover
        raise RuntimeError("Hourly zone solver did not produce a solution")

    if recovery_is_detailed and extract_temperature is not None:
        t_supply = ventilation_effective_supply_temperature(
            ventilation, zone, t_e,
            building_floor_area=building_floor_area,
            operation_profile=operation_profile,
            extract_temperature_c=extract_temperature,
        )
    q_transmission = (
        np.asarray(solution.q_transmission, dtype=float)
        if detailed_hourly
        else _legacy._reported_transmission_losses(
            network, solution, zone_thermal_properties(zone.floor_area)
        )
    )
    q_ventilation = ventilation_heat_loss(
        ventilation, zone, solution.t_air, t_e, T_supply=t_supply,
        building_floor_area=building_floor_area, operation_profile=operation_profile,
    )
    design_losses = _legacy._design_loss_series_w(network, h_ve, t_set_heating, t_supply)
    moisture_result = _moisture_result(
        zone, df, project, ventilation, operation_profile, building_floor_area,
        solution, settings
    ) if detailed_hourly else None
    result = {
        "T_int": solution.t_air,
        "T_op": solution.t_operative,
        "T_mrt": getattr(solution, "t_mean_radiant", solution.t_surface),
        "T_supply": t_supply,
        "Q_H": solution.q_heating,
        "Q_C": solution.q_cooling,
        "q_int": q_int,
        "q_solar": q_solar_report,
        "q_transmission": q_transmission,
        "q_ventilation": q_ventilation,
        "design_losses": design_losses,
        "H_tr": network.h_total,
        "H_ve": h_ve,
        "floor_area": zone.floor_area,
        "hourly_solver": "iso52016_surface_nodal" if detailed_hourly else "legacy_reduced_5r1c",
    }
    if detailed_hourly:
        result["unmet_heating_k"] = solution.unmet_heating_k
        result["unmet_cooling_k"] = solution.unmet_cooling_k
    if moisture_result is not None:
        result.update({
            "humidity_ratio": moisture_result.humidity_ratio,
            "relative_humidity": moisture_result.relative_humidity,
            "Q_H_latent": moisture_result.latent_heating_w,
            "Q_C_latent": moisture_result.latent_cooling_w,
        })
    return result


_legacy._aggregate_zone_results = _aggregate_zone_results


def calculate_building_energy(project):
    _legacy._aggregate_zone_results = _aggregate_zone_results
    _legacy._load_climate = globals()["_load_climate"]
    return _legacy.calculate_building_energy(project)
