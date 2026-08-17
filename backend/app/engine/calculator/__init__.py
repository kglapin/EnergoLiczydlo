"""Runtime calculator with repaired hourly-solver selection.

Direct low-level core calls retain the reduced 5R1C path unless they explicitly
enable ``metadata.normative.hourly_iso52016.enabled``. Projects prepared by
the public ``audited_calculator`` use the per-construction five-node solver by
default unless the project explicitly opts out. This preserves low-level
regression semantics while fixing the user-facing calculation path.

Detailed heat recovery is solved iteratively with the resulting zone-air
(extract) temperature instead of being frozen at the heating setpoint.
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
from app.engine.normative_models import load_normative_settings
from app.engine.solar import total_solar_gains
from app.engine.thermal_balance import solve_zone_5r1c, zone_thermal_properties
from app.engine.ventilation import (
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
    cooling = (
        zone.setpoint_cooling
        if zone.zone_type in COOLED_ZONE_TYPES and zone.setpoint_cooling is not None
        else None
    )
    return heating, cooling


def _detailed_hourly_enabled(project, settings) -> bool:
    """Resolve solver selection while preserving explicit project choice."""
    normative = project.metadata.get("normative", {})
    if isinstance(normative, dict):
        hourly = normative.get("hourly_iso52016", {})
        if isinstance(hourly, dict) and "enabled" in hourly:
            return bool(settings.hourly_iso52016.enabled)
    # The audited public path attaches validated settings before calling core.
    return getattr(project, "_normative_settings", None) is not None


def _aggregate_zone_results(
    zone,
    df,
    project,
    building_floor_area: float,
    ventilation,
    operation_profile: np.ndarray,
):
    opaque = [
        element for element in project.opaque_building_elements if element.zone_id == zone.id
    ]
    transparent = [
        element
        for element in project.transparent_building_elements
        if element.zone_id == zone.id
    ]
    t_e = df["T_e"].to_numpy(dtype=float)

    network = zone_transmission_network(
        opaque,
        transparent,
        project.thermal_bridges,
        t_e,
        zone_id=zone.id,
    )
    h_ve = ventilation_heat_transfer_coefficient(
        ventilation,
        zone,
        building_floor_area,
        operation_profile=operation_profile,
    )
    q_sol_trans, q_sol_abs_reduced = total_solar_gains(transparent, opaque, df)
    q_solar_report = q_sol_trans + q_sol_abs_reduced
    q_int = total_internal_gains(
        zone.occupancy_density,
        zone.floor_area,
        project.internal_gains,
        df.index,
    )
    t_set_heating, t_set_cooling = _setpoints(zone)

    settings = load_normative_settings(project)
    detailed_hourly = _detailed_hourly_enabled(project, settings)
    recovery_is_detailed = detailed_heat_recovery_settings(ventilation) is not None
    extract_temperature: np.ndarray | None = None
    solution = None
    t_supply = t_e.copy()

    for _ in range(8):
        t_supply = ventilation_effective_supply_temperature(
            ventilation,
            zone,
            t_e,
            building_floor_area=building_floor_area,
            operation_profile=operation_profile,
            extract_temperature_c=extract_temperature,
        )
        if detailed_hourly:
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
                require_explicit_construction_nodes=(
                    settings.hourly_iso52016.certificate_mode
                ),
                max_warmup_cycles=settings.hourly_iso52016.max_warmup_cycles,
                warmup_tolerance_k=settings.hourly_iso52016.warmup_tolerance_k,
            )
        else:
            properties = zone_thermal_properties(zone.floor_area)
            solution = solve_zone_5r1c(
                network=network,
                h_ve=h_ve,
                t_e=t_e,
                phi_int=q_int,
                phi_sol=q_solar_report,
                properties=properties,
                t_set_heating=t_set_heating,
                t_set_cooling=t_set_cooling,
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
            ventilation,
            zone,
            t_e,
            building_floor_area=building_floor_area,
            operation_profile=operation_profile,
            extract_temperature_c=extract_temperature,
        )

    if detailed_hourly:
        q_transmission = np.asarray(solution.q_transmission, dtype=float)
    else:
        properties = zone_thermal_properties(zone.floor_area)
        q_transmission = _legacy._reported_transmission_losses(
            network,
            solution,
            properties,
        )
    q_ventilation = ventilation_heat_loss(
        ventilation,
        zone,
        solution.t_air,
        t_e,
        T_supply=t_supply,
        building_floor_area=building_floor_area,
        operation_profile=operation_profile,
    )
    design_losses = _legacy._design_loss_series_w(
        network,
        h_ve,
        t_set_heating,
        t_supply,
    )
    return {
        "T_int": solution.t_air,
        "T_op": solution.t_operative,
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
        "hourly_solver": (
            "per_construction_5node" if detailed_hourly else "legacy_reduced_5r1c"
        ),
    }


_legacy._aggregate_zone_results = _aggregate_zone_results


def calculate_building_energy(project):
    """Run annual aggregation while preserving historical monkeypatch hooks."""
    _legacy._aggregate_zone_results = _aggregate_zone_results
    _legacy._load_climate = globals()["_load_climate"]
    return _legacy.calculate_building_energy(project)
