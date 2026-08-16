"""High-level calculator entry point for a BuildingProject."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.engine.climate import load_epw
from app.engine.envelope import (
    compute_opaque_heat_loss,
    compute_thermal_bridge_loss,
    compute_transparent_heat_loss,
    total_transmission_coefficient,
)
from app.engine.internal_gains import total_internal_gains
from app.engine.primary_energy import annual_primary_energy, share_of_renewable_energy
from app.engine.solar import total_solar_gains
from app.engine.systems import (
    constant_efficiency_final_energy,
    dhw_energy_demand,
    final_energy_dhw,
    heat_pump_cop_map,
)
from app.engine.thermal_balance import solve_hourly_balance, thermal_capacity
from app.engine.ventilation import ventilation_heat_loss, ventilation_heat_transfer_coefficient
from app.schemas.models import (
    AnnualIndicators,
    BuildingProject,
    CalculationResult,
    ComplianceCheck,
    MonthlyResult,
    OpaqueElement,
    ThermalZone,
    TransparentElement,
    VentilationType,
    ZoneType,
)

DATA_DIR = Path(os.environ.get("TMY_DATA_PATH", Path(__file__).parents[3] / "data" / "tmy"))

# Zone types for which the solver enforces heating / cooling setpoints.
HEATED_ZONE_TYPES = {ZoneType.HEATED, ZoneType.HEATED_AND_COOLED, ZoneType.SEMI_HEATED}
COOLED_ZONE_TYPES = {ZoneType.COOLED, ZoneType.HEATED_AND_COOLED}


def _monthly_sums(series: np.ndarray) -> list[float]:
    """Sum a 8760-hour array into 12 monthly values (non-leap year)."""
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    out = []
    h = 0
    for d in days_per_month:
        n = d * 24
        out.append(float(np.sum(series[h : h + n])))
        h += n
    return out


def _load_climate(project: BuildingProject) -> pd.DataFrame:
    station = project.climate_station_id
    # Try a couple of naming conventions
    candidates = [
        DATA_DIR / f"{station}.epw",
        DATA_DIR / station / f"{station}.epw",
    ]
    for cand in candidates:
        if cand.exists():
            return load_epw(cand)
    raise FileNotFoundError(f"No climate file found for station {station} in {DATA_DIR}")


def _aggregate_zone_results(
    zone: ThermalZone,
    df: pd.DataFrame,
    project: BuildingProject,
) -> dict[str, Any]:
    # Filter elements for this zone
    opaque: list[OpaqueElement] = [
        el for el in project.opaque_building_elements if el.zone_id == zone.id
    ]
    transparent: list[TransparentElement] = [
        el for el in project.transparent_building_elements if el.zone_id == zone.id
    ]

    # Transmission losses per element
    q_tr_elements = np.zeros(len(df), dtype=float)
    for o_el in opaque:
        q_tr_elements += compute_opaque_heat_loss(o_el, zone.setpoint_heating, df["T_e"])
    for t_el in transparent:
        q_tr_elements += compute_transparent_heat_loss(t_el, zone.setpoint_heating, df["T_e"])
    q_bridges = compute_thermal_bridge_loss(
        project.thermal_bridges, zone, zone.setpoint_heating, df["T_e"]
    )
    q_transmission = q_tr_elements + q_bridges  # W

    # Ventilation
    H_ve = ventilation_heat_transfer_coefficient(project.ventilation, zone)
    q_ventilation = ventilation_heat_loss(
        project.ventilation, zone, zone.setpoint_heating, df["T_e"]
    )

    # Solar gains (transparent + reduced opaque absorption per ISO 52016-1)
    q_sol_trans, q_sol_abs = total_solar_gains(transparent, opaque, df)
    q_solar = q_sol_trans + q_sol_abs

    # Internal gains
    q_int = total_internal_gains(
        zone.occupancy_density,
        zone.floor_area,
        project.internal_gains,
        df.index,
    )

    # Thermal-balance coefficients
    H_tr = total_transmission_coefficient(
        opaque, transparent, project.thermal_bridges, zone_id=zone.id
    )

    # Dynamic thermal-balance solver. Setpoints apply only to zones whose
    # zone_type declares heating / cooling; unheated zones free-float.
    C_m = thermal_capacity(zone.floor_area)
    T_set_heating = (
        zone.setpoint_heating if zone.zone_type in HEATED_ZONE_TYPES else None
    )
    T_set_cooling = (
        zone.setpoint_cooling
        if zone.zone_type in COOLED_ZONE_TYPES and zone.setpoint_cooling is not None
        else None
    )

    T_int, Q_H, Q_C, Q_bal = solve_hourly_balance(
        H_tr=H_tr,
        H_ve=H_ve,
        Q_int=q_int,
        Q_sol=q_solar,
        T_e=df["T_e"].to_numpy(),
        T_set_heating=T_set_heating,
        T_set_cooling=T_set_cooling,
        C_m=C_m,
    )

    return {
        "T_int": T_int,
        "Q_H": Q_H,
        "Q_C": Q_C,
        "q_int": q_int,
        "q_solar": q_solar,
        "q_transmission": q_transmission,
        "q_ventilation": q_ventilation,
        "Q_bal": Q_bal,
        "H_tr": H_tr,
        "H_ve": H_ve,
        "floor_area": zone.floor_area,
    }


def calculate_building_energy(project: BuildingProject) -> CalculationResult:
    """Run the hourly energy calculation for a full BuildingProject."""
    df = _load_climate(project)
    datetimes = df.index

    total_Q_H = np.zeros(len(df), dtype=float)
    total_Q_C = np.zeros(len(df), dtype=float)
    total_q_int = np.zeros(len(df), dtype=float)
    total_q_solar = np.zeros(len(df), dtype=float)
    total_q_transmission = np.zeros(len(df), dtype=float)
    total_q_ventilation = np.zeros(len(df), dtype=float)
    total_T_int = np.zeros(len(df), dtype=float)
    total_zone_area = 0.0

    conditioned_area = project.general.conditioned_floor_area

    # Aggregate over all thermal zones
    for zone in project.thermal_zones:
        zr = _aggregate_zone_results(zone, df, project)
        total_Q_H += zr["Q_H"]
        total_Q_C += zr["Q_C"]
        total_q_int += zr["q_int"]
        total_q_solar += zr["q_solar"]
        total_q_transmission += zr["q_transmission"]
        total_q_ventilation += zr["q_ventilation"]

    # Final energy for heating
    heating_sys = project.systems.get("heating", {})
    sys_type = heating_sys.get("system_type", "heat_pump_air")
    fuel = heating_sys.get("fuel_or_carrier", "electricity")
    distribution_loss = heating_sys.get("distribution_loss_factor", 0.95)

    if sys_type.startswith("heat_pump"):
        cop = heat_pump_cop_map(
            df["T_e"].to_numpy(),
            T_sink=heating_sys.get("sink_temperature", 35.0),
            source_type="air" if "air" in sys_type else "water",
            rated_cop=heating_sys.get("efficiency_or_cop_map", {}).get("value", 3.0),
        )
        E_k_H = total_Q_H / cop / distribution_loss
    else:
        eff = heating_sys.get("efficiency_or_cop_map", {}).get("value", 0.9)
        E_k_H = constant_efficiency_final_energy(total_Q_H, eff, distribution_loss)

    # Final energy for cooling
    cooling_sys = project.systems.get("cooling", {})
    if cooling_sys:
        cop_c = cooling_sys.get("efficiency_or_cop_map", {}).get("value", 3.0)
        E_k_C = constant_efficiency_final_energy(total_Q_C, cop_c)
    else:
        E_k_C = np.zeros(len(df), dtype=float)

    # DHW
    # Use the first heated zone for occupancy/floor-area reference
    allowed_zone_types = {"heated", "heated_and_cooled"}
    heated_zones = [
        z for z in project.thermal_zones if z.zone_type in allowed_zone_types
    ]
    if heated_zones:
        ref_zone = heated_zones[0]
        dhw_system = project.systems.get("dhw", {})
        Q_dhw_year = dhw_energy_demand(
            daily_demand_per_person=dhw_system.get("daily_demand_per_person", 50.0),
            occupancy_density=ref_zone.occupancy_density,
            floor_area=ref_zone.floor_area,
            target_temperature=dhw_system.get("target_temperature", 55.0),
            cold_water_temperature=dhw_system.get("cold_water_temperature", 10.0),
        )
        # Distribute DHW demand over hours proportionally to occupancy schedule
        dhw_schedule = total_internal_gains(
            ref_zone.occupancy_density,
            ref_zone.floor_area,
            project.internal_gains,
            datetimes,
        )
        denominator = float(np.sum(dhw_schedule)) or 1.0
        Q_dhw_hourly = Q_dhw_year * dhw_schedule / denominator
        dhw_eff = project.systems.get("dhw", {}).get("efficiency", 0.9)
        E_k_DHW = final_energy_dhw(Q_dhw_hourly, dhw_eff)
    else:
        E_k_DHW = np.zeros(len(df), dtype=float)

    # Ventilation auxiliary (fans)
    vent_power = project.ventilation.mechanical_fan_power or 0.0
    if project.ventilation.ventilation_type == VentilationType.MECHANICAL:
        E_k_vent = np.full(len(df), vent_power)  # W
    else:
        E_k_vent = np.zeros(len(df), dtype=float)

    # Aggregate final energy by carrier (simple mapping)
    dhw_system_type = dhw_system.get("system_type", "")
    final_energy_by_carrier: dict[str, float] = {}
    final_energy_by_carrier[fuel] = float(np.sum(E_k_H)) + float(np.sum(E_k_C))
    final_energy_by_carrier["electricity"] = float(np.sum(E_k_vent)) + (
        float(np.sum(E_k_DHW)) if dhw_system_type.startswith("electric") else 0.0
    )
    # Ensure no double counting if fuel is electricity for heating
    final_energy_by_carrier["electricity"] = max(
        final_energy_by_carrier.get("electricity", 0.0), 0.0
    )

    # Useful energy Eu = Q_H + Q_C + DHW useful energy [Wh/year]
    E_u_total_wh = float(np.sum(total_Q_H)) + float(np.sum(total_Q_C)) + float(np.sum(Q_dhw_hourly))

    # Final energy Ek [Wh/year]
    E_k_total_wh = sum(final_energy_by_carrier.values())

    # Primary energy / emissions
    E_p_total_wh, E_C_total_kg = annual_primary_energy(
        final_energy_by_carrier, project.primary_energy
    )

    # Indicators per m2 of conditioned floor area [kWh/(m2*year)]
    eu = E_u_total_wh / 1000.0 / conditioned_area
    ek = E_k_total_wh / 1000.0 / conditioned_area
    ep = E_p_total_wh / 1000.0 / conditioned_area
    ec = E_C_total_kg / conditioned_area
    u_oze = share_of_renewable_energy(final_energy_by_carrier)

    heating_m2 = float(np.sum(total_Q_H)) / 1000.0 / conditioned_area
    cooling_m2 = float(np.sum(total_Q_C)) / 1000.0 / conditioned_area
    dhw_m2 = float(np.sum(Q_dhw_hourly)) / 1000.0 / conditioned_area

    # Monthly aggregation
    monthly: list[MonthlyResult] = []
    for month in range(1, 13):
        monthly.append(
            MonthlyResult(
                month=month,
                heating_kwh=_monthly_sums(total_Q_H)[month - 1] / 1000.0,
                cooling_kwh=_monthly_sums(total_Q_C)[month - 1] / 1000.0,
                dhw_kwh=_monthly_sums(Q_dhw_hourly)[month - 1] / 1000.0,
                internal_gains_kwh=_monthly_sums(total_q_int)[month - 1] / 1000.0,
                solar_gains_kwh=_monthly_sums(total_q_solar)[month - 1] / 1000.0,
                transmission_losses_kwh=_monthly_sums(total_q_transmission)[month - 1] / 1000.0,
                ventilation_losses_kwh=_monthly_sums(total_q_ventilation)[month - 1] / 1000.0,
            )
        )

    # Compliance placeholder
    compliance: list[ComplianceCheck] = []
    # Polish regulation examples (WT 2021 residential / non-residential)
    ep_limit = 75.0 if project.general.building_type.value == "residential" else 110.0
    compliance.append(
        ComplianceCheck(
            name=f"Wymaganie EP < {ep_limit} kWh/(m²·rok)",
            passed=ep < ep_limit,
            message=f"Obliczone EP = {ep:.2f} kWh/(m²·rok)",
        )
    )
    compliance.append(
        ComplianceCheck(
            name="Eu >= 0",
            passed=eu >= 0,
            message=f"Obliczone Eu = {eu:.2f} kWh/(m²·rok)",
        )
    )

    return CalculationResult(
        project_id=str(uuid.uuid4()),
        status="success",
        annual_indicators=AnnualIndicators(
            eu_kwh_m2_year=eu,
            ek_kwh_m2_year=ek,
            ep_kwh_m2_year=ep,
            ec_tco2_m2_year=ec,
            u_oze_percent=u_oze,
            heating_kwh_m2_year=heating_m2,
            cooling_kwh_m2_year=cooling_m2,
            dhw_kwh_m2_year=dhw_m2,
        ),
        monthly=monthly,
        hourly={
            "Q_H": total_Q_H.tolist(),
            "Q_C": total_Q_C.tolist(),
            "T_int": (
                total_T_int / total_zone_area if total_zone_area > 0 else df["T_e"].to_numpy()
            ).tolist(),
        },
        compliance=compliance,
    )
