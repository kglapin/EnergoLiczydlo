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
    zone_transmission_network,
)
from app.engine.internal_gains import total_internal_gains
from app.engine.primary_energy import annual_primary_energy, share_of_renewable_energy
from app.engine.solar import total_solar_gains
from app.engine.systems import (
    annual_dhw_useful_energy,
    constant_efficiency_final_energy,
    default_generation_efficiency,
    dhw_auxiliary_demand_wh,
    dhw_storage_standby_loss_kwh,
    final_energy_dhw,
    heat_pump_cop_map,
    heating_auxiliary_demand_wh,
    ventilation_fan_hours_per_year,
    ventilation_fan_power_w_m2,
)
from app.engine.thermal_balance import (
    TransmissionNetwork,
    solve_zone_5r1c,
    zone_thermal_properties,
)
from app.engine.ventilation import (
    normative_airflow_rate_m3h,
    ventilation_heat_loss,
    ventilation_heat_transfer_coefficient,
)
from app.schemas.models import (
    AnnualIndicators,
    BuildingProject,
    BuildingType,
    CalculationResult,
    ComplianceCheck,
    MonthlyResult,
    OpaqueElement,
    ThermalZone,
    TransparentElement,
    ZoneType,
)

DATA_DIR = Path(os.environ.get("TMY_DATA_PATH", Path(__file__).parents[3] / "data" / "tmy"))

# Zone types for which the solver enforces heating / cooling setpoints.
HEATED_ZONE_TYPES = {ZoneType.HEATED, ZoneType.HEATED_AND_COOLED, ZoneType.SEMI_HEATED}
COOLED_ZONE_TYPES = {ZoneType.COOLED, ZoneType.HEATED_AND_COOLED}
# Zones served by the building ventilation system (airflow share).
CONDITIONED_ZONE_TYPES = HEATED_ZONE_TYPES | COOLED_ZONE_TYPES


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


def _generation_efficiency(system: Any, default: float | None = None) -> float:
    """Read the ηg/SEER field with compatibility for legacy JSON.

    Falls back to the normative per-source-type default when neither the new
    field nor a legacy field is present.
    """
    explicit = getattr(system, "generation_efficiency", None)
    if explicit is not None:
        return float(explicit)

    legacy_map = getattr(system, "efficiency_or_cop_map", {}) or {}
    legacy_value = legacy_map.get("value")
    if legacy_value is not None:
        return float(legacy_value)

    legacy_efficiency = getattr(system, "efficiency", None)
    if legacy_efficiency is not None:
        return float(legacy_efficiency)
    return default_generation_efficiency(system, fallback=default if default else 0.96)


def _distribution_efficiency(system: Any, default: float = 0.95) -> float:
    """Read ηd, falling back to the former distribution-loss field."""
    explicit = getattr(system, "distribution_efficiency", None)
    if explicit is not None:
        return float(explicit)
    legacy = getattr(system, "distribution_loss_factor", None)
    return float(legacy if legacy is not None else default)


def _system_carrier(system: Any) -> str:
    carrier = getattr(system, "fuel_or_carrier", "electricity")
    return str(getattr(carrier, "value", carrier))


def _design_loss_series_w(
    network: TransmissionNetwork,
    h_ve: float,
    t_set_heating: float | None,
    t_e: np.ndarray,
) -> np.ndarray:
    """Transmission + ventilation losses [W] at the heating setpoint.

    Design-condition series used only for source sizing: each conductance is
    driven by its own adjacent-space temperature (ground floors see the
    ground temperature, not the coldest outdoor hour).
    """
    losses = np.zeros(len(t_e), dtype=float)
    if t_set_heating is not None:
        if network.h_opaque > 0.0 and network.t_opaque is not None:
            losses += network.h_opaque * (t_set_heating - network.t_opaque)
        for h, t_adj in zip(network.h_surface, network.t_surface, strict=True):
            losses += h * (t_set_heating - t_adj)
        losses += h_ve * (t_set_heating - t_e)
    return np.maximum(losses, 0.0)


def _design_heating_power_kw(
    design_losses_w: np.ndarray,
    heating_system: Any,
) -> float:
    """Determine source thermal power from the peak calculated heat losses.

    The source is sized against the peak design loss (transmission +
    ventilation at the heating setpoint).  Distribution, storage and control
    efficiencies are applied because the source must provide the useful heat
    lost by those technical subsystems.  Generation efficiency/COP is
    deliberately not used here: nominal source power is thermal output,
    while ηH,g/COP converts it to final carrier energy later in the
    calculation.
    """
    if str(heating_system.system_type) == "none":
        return 0.0

    peak_losses_w = float(np.max(design_losses_w)) if design_losses_w.size else 0.0
    delivery_efficiency = (
        _distribution_efficiency(heating_system)
        * heating_system.storage_efficiency
        * heating_system.control_efficiency
    )
    return float(peak_losses_w / delivery_efficiency / 1000.0)


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


def _reported_transmission_losses(
    zone: ThermalZone,
    opaque: list[OpaqueElement],
    transparent: list[TransparentElement],
    project: BuildingProject,
    t_air: np.ndarray,
    t_e: np.ndarray,
) -> np.ndarray:
    """Element-wise transmission losses [W] evaluated at the solved air temperature.

    Using the simulated indoor temperature (instead of the setpoint) makes the
    monthly loss breakdown consistent with the simulated heating/cooling need.
    """
    q_tr = np.zeros(len(t_e), dtype=float)
    for o_el in opaque:
        q_tr += compute_opaque_heat_loss(o_el, t_air, t_e)
    for t_el in transparent:
        q_tr += compute_transparent_heat_loss(t_el, t_air, t_e)
    q_tr += compute_thermal_bridge_loss(project.thermal_bridges, zone, t_air, t_e)
    return q_tr


def _aggregate_zone_results(
    zone: ThermalZone,
    df: pd.DataFrame,
    project: BuildingProject,
    building_floor_area: float,
    ventilation: Any,
) -> dict[str, Any]:
    # Filter elements for this zone
    opaque: list[OpaqueElement] = [
        el for el in project.opaque_building_elements if el.zone_id == zone.id
    ]
    transparent: list[TransparentElement] = [
        el for el in project.transparent_building_elements if el.zone_id == zone.id
    ]
    t_e = df["T_e"].to_numpy()

    # Transmission network for the dynamic solver.  Ground, unheated and
    # constant-temperature adjacencies enter with their own driving
    # temperature; partitions between equally conditioned zones drop out.
    network = zone_transmission_network(
        opaque, transparent, project.thermal_bridges, t_e, zone_id=zone.id
    )

    # Ventilation (building airflow split between zones by floor area)
    H_ve = ventilation_heat_transfer_coefficient(ventilation, zone, building_floor_area)

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

    # Setpoints apply only to zones whose zone_type declares heating /
    # cooling (metodologia: Q_C,nd only for chłodzone strefy); other zones
    # free-float.
    T_set_heating = zone.setpoint_heating if zone.zone_type in HEATED_ZONE_TYPES else None
    T_set_cooling = (
        zone.setpoint_cooling
        if zone.zone_type in COOLED_ZONE_TYPES and zone.setpoint_cooling is not None
        else None
    )

    solution = solve_zone_5r1c(
        network=network,
        h_ve=H_ve,
        t_e=t_e,
        phi_int=q_int,
        phi_sol=q_solar,
        properties=zone_thermal_properties(zone.floor_area),
        t_set_heating=T_set_heating,
        t_set_cooling=T_set_cooling,
    )

    # Loss breakdown reported at the simulated air temperature
    q_transmission = _reported_transmission_losses(
        zone, opaque, transparent, project, solution.t_air, t_e
    )
    q_ventilation = ventilation_heat_loss(
        ventilation, zone, solution.t_air, t_e, building_floor_area=building_floor_area
    )

    # Design-condition losses for source sizing (setpoint-based)
    design_losses = _design_loss_series_w(network, H_ve, T_set_heating, t_e)

    return {
        "T_int": solution.t_air,
        "T_op": solution.t_operative,
        "Q_H": solution.q_heating,
        "Q_C": solution.q_cooling,
        "q_int": q_int,
        "q_solar": q_solar,
        "q_transmission": q_transmission,
        "q_ventilation": q_ventilation,
        "design_losses": design_losses,
        "H_tr": network.h_total,
        "H_ve": H_ve,
        "floor_area": zone.floor_area,
    }


def calculate_building_energy(project: BuildingProject) -> CalculationResult:
    """Run the hourly energy calculation for a full BuildingProject."""
    df = _load_climate(project)
    n = len(df)

    total_Q_H = np.zeros(n, dtype=float)
    total_Q_C = np.zeros(n, dtype=float)
    total_q_int = np.zeros(n, dtype=float)
    total_q_solar = np.zeros(n, dtype=float)
    total_q_transmission = np.zeros(n, dtype=float)
    total_q_ventilation = np.zeros(n, dtype=float)
    total_T_int = np.zeros(n, dtype=float)
    total_T_op = np.zeros(n, dtype=float)
    total_design_losses = np.zeros(n, dtype=float)
    total_zone_area = 0.0

    conditioned_area = project.general.conditioned_floor_area
    # Ventilation airflow is shared between conditioned zones only.
    building_floor_area = sum(
        zone.floor_area
        for zone in project.thermal_zones
        if zone.zone_type in CONDITIONED_ZONE_TYPES
    )

    # Wentylacja: przy airflow_rate = 0 pobierz strumień normatywny z tabel
    # 21/22/24/25 (V0 wg profilu użytkowania CWU, β i r_n).
    ventilation = project.ventilation
    profile_value = str(
        getattr(project.general.dhw_usage_profile, "value", project.general.dhw_usage_profile)
    )
    if ventilation.airflow_rate == 0.0:
        residential = profile_value.startswith("residential")
        beta = (
            ventilation.usage_share_beta
            if ventilation.usage_share_beta is not None
            else (1.0 if residential else 0.3)
        )
        normative_m3h = normative_airflow_rate_m3h(
            profile_value,
            building_floor_area,
            str(getattr(ventilation.ventilation_type, "value", ventilation.ventilation_type)),
            beta=beta,
        )
        ventilation = ventilation.model_copy(update={"airflow_rate": normative_m3h})

    # Aggregate over all thermal zones
    for zone in project.thermal_zones:
        zr = _aggregate_zone_results(zone, df, project, building_floor_area, ventilation)
        total_Q_H += zr["Q_H"]
        total_Q_C += zr["Q_C"]
        total_q_int += zr["q_int"]
        total_q_solar += zr["q_solar"]
        total_q_transmission += zr["q_transmission"]
        total_q_ventilation += zr["q_ventilation"]
        total_design_losses += zr["design_losses"]
        # Area-weighted indoor temperature across zones
        total_T_int += zr["T_int"] * zone.floor_area
        total_T_op += zr["T_op"] * zone.floor_area
        total_zone_area += zone.floor_area

    # Final energy for heating
    heating_sys = project.systems.heating
    sys_type = str(heating_sys.system_type)
    heating_efficiency = _generation_efficiency(heating_sys)
    heating_distribution = _distribution_efficiency(heating_sys)
    heating_system_efficiency = (
        heating_distribution
        * heating_sys.storage_efficiency
        * heating_sys.control_efficiency
    )
    design_heating_power_kw = _design_heating_power_kw(total_design_losses, heating_sys)

    if sys_type == "none":
        E_k_H = np.zeros(n, dtype=float)
    elif sys_type.startswith("heat_pump"):
        t_e_arr = df["T_e"].to_numpy()
        if sys_type in ("heat_pump_ground", "heat_pump_water"):
            # Brine/water source temperature is set by the ground loop, not
            # by the outdoor air; without an explicit value the rated COP is
            # used as the seasonal average.
            if heating_sys.source_temperature is not None:
                t_source = np.full(n, heating_sys.source_temperature, dtype=float)
                cop = heat_pump_cop_map(
                    t_source,
                    T_sink=heating_sys.sink_temperature,
                    source_type="water",
                    rated_cop=heating_efficiency,
                )
            else:
                cop = np.full(n, heating_efficiency, dtype=float)
        else:
            cop = heat_pump_cop_map(
                t_e_arr,
                T_sink=heating_sys.sink_temperature,
                source_type="air",
                rated_cop=heating_efficiency,
            )
        E_k_H = total_Q_H / cop / heating_system_efficiency
    else:
        E_k_H = constant_efficiency_final_energy(
            total_Q_H,
            heating_efficiency,
            heating_system_efficiency,
        )

    # Final energy for cooling
    cooling_sys = project.systems.cooling
    if cooling_sys is not None and str(cooling_sys.system_type) != "none":
        seer = _generation_efficiency(cooling_sys)
        cooling_system_efficiency = (
            cooling_sys.storage_efficiency
            * _distribution_efficiency(cooling_sys)
            * cooling_sys.control_efficiency
        )
        E_k_C = constant_efficiency_final_energy(
            total_Q_C,
            seer,
            cooling_system_efficiency,
        )
    else:
        E_k_C = np.zeros(n, dtype=float)

    # DHW: Q_W,nd comes from the regulatory annual-use equation (§ 5.3,
    # table 27). Losses follow § 4.1.3: distribution losses enter through the
    # multiplicative ηW,d proxy, storage standby losses ΔQ_W,s are computed
    # from table 13 / eq. (30) when the tank volume is given.
    dhw_system = project.systems.dhw
    Q_dhw_hourly = np.zeros(n, dtype=float)
    E_k_DHW: np.ndarray
    if str(dhw_system.system_type) != "none":
        Q_dhw_year = annual_dhw_useful_energy(
            project.general.conditioned_floor_area,
            project.general.dhw_usage_profile,
        )
        # The methodology specifies an annual demand. A uniform hourly split
        # preserves that annual value for monthly reporting without deriving
        # DHW demand from occupancy schedules or number of occupants.
        Q_dhw_hourly = np.full(n, Q_dhw_year / n, dtype=float)
        dhw_generation = _generation_efficiency(dhw_system, default=0.96)

        tank_kind = (
            "electric"
            if str(dhw_system.system_type) in ("electric_storage", "electric_instantaneous")
            else ("gas" if "gas" in str(dhw_system.system_type) else "indirect")
        )
        standby_loss_kwh = None
        if dhw_system.storage_volume_dm3 is not None:
            standby_loss_kwh = dhw_storage_standby_loss_kwh(
                dhw_system.storage_volume_dm3,
                location=dhw_system.storage_location or "unheated",
                tank_kind=tank_kind,
                insulation_mm=dhw_system.storage_insulation_mm or 50.0,
            )
        if standby_loss_kwh is not None:
            # (29)-(30): ΔQ_W,d z ηW,d, ΔQ_W,s z tabeli 13; E_k = (Q + ΔQ_d +
            # ΔQ_s)/η_W,g (pole storage_efficiency nie jest już potrzebne).
            delta_d_kwh = Q_dhw_year / 1000.0 * (1.0 / dhw_system.distribution_efficiency - 1.0)
            total_dhw_kwh = Q_dhw_year / 1000.0 + delta_d_kwh + standby_loss_kwh
            # rozkład rocznej energii końcowej równomiernie na godziny
            E_k_DHW = np.full(n, total_dhw_kwh * 1000.0 / dhw_generation / n)
        else:
            dhw_efficiency = (
                dhw_generation
                * dhw_system.storage_efficiency
                * dhw_system.distribution_efficiency
                * dhw_system.utilization_efficiency
            )
            E_k_DHW = np.asarray(final_energy_dhw(Q_dhw_hourly, dhw_efficiency))
    else:
        E_k_DHW = np.zeros(n, dtype=float)

    # Wbudowana instalacja oświetlenia (wzór (35)): Q_k,L = LENI·A_L, tylko
    # dla budynków niemieszkalnych; nośnik = energia elektryczna.
    E_k_L_wh = 0.0
    leni = project.general.lighting_indicator_leni
    if leni is not None and project.general.building_type != BuildingType.RESIDENTIAL:
        lighting_area = project.general.lighting_area_m2 or conditioned_area
        E_k_L_wh = leni * lighting_area * 1000.0

    # Energia pomocnicza E_el,pom (wzory (37)-(38), tabela 20): pompy i
    # regulacja źródeł oraz wentylatory.
    E_aux_wh = 0.0
    if str(heating_sys.system_type) != "none":
        E_aux_wh += heating_auxiliary_demand_wh(
            str(heating_sys.system_type), conditioned_area
        )
    if str(dhw_system.system_type) != "none":
        E_aux_wh += dhw_auxiliary_demand_wh(
            str(dhw_system.system_type),
            conditioned_area,
            distribution_type=str(getattr(dhw_system.distribution_type, "value", "")),
        )

    # Ventilation auxiliary (fans, tabela 20 rows 12/13): energia roczna
    # wentylatorów [Wh], rozłożona równomiernie na godziny pracy 8760·β.
    vent_type_value = str(
        getattr(ventilation.ventilation_type, "value", ventilation.ventilation_type)
    )
    E_k_vent_wh = 0.0
    if vent_type_value in ("mechanical", "mechanical_with_recovery", "exhaust", "hybrid"):
        vent_power = ventilation.mechanical_fan_power or 0.0
        if vent_power == 0.0:
            # Normatywnie: q_el z tabeli 20 wg krotności wymiany powietrza.
            ach = ventilation.airflow_rate / project.general.heated_volume
            vent_power = ventilation_fan_power_w_m2(vent_type_value, ach) * conditioned_area
        residential = profile_value.startswith("residential")
        beta = (
            ventilation.usage_share_beta
            if ventilation.usage_share_beta is not None
            else (1.0 if residential else 0.3)
        )
        E_k_vent_wh = vent_power * ventilation_fan_hours_per_year(beta)

    # Aggregate final energy by carrier (simple mapping)
    final_energy_by_carrier: dict[str, float] = {}
    if str(heating_sys.system_type) != "none":
        heating_carrier = _system_carrier(heating_sys)
        final_energy_by_carrier[heating_carrier] = float(np.sum(E_k_H))
    if cooling_sys is not None and str(cooling_sys.system_type) != "none":
        cooling_carrier = _system_carrier(cooling_sys)
        final_energy_by_carrier[cooling_carrier] = (
            final_energy_by_carrier.get(cooling_carrier, 0.0) + float(np.sum(E_k_C))
        )
    if str(dhw_system.system_type) != "none":
        dhw_carrier = _system_carrier(dhw_system)
        final_energy_by_carrier[dhw_carrier] = (
            final_energy_by_carrier.get(dhw_carrier, 0.0) + float(np.sum(E_k_DHW))
        )
    final_energy_by_carrier["electricity"] = (
        final_energy_by_carrier.get("electricity", 0.0)
        + E_k_vent_wh
        + E_k_L_wh
        + E_aux_wh
    )

    # Useful energy Eu = Q_H + Q_C + DHW useful energy + lighting [Wh/year];
    # energia pomocnicza (pompy, wentylatory) jest końcowa, nie użytkowa.
    E_u_total_wh = (
        float(np.sum(total_Q_H)) + float(np.sum(total_Q_C)) + float(np.sum(Q_dhw_hourly)) + E_k_L_wh
    )

    # Final energy Ek [Wh/year]
    E_k_total_wh = sum(final_energy_by_carrier.values())

    # Primary energy / emissions
    E_p_total_wh, E_C_total_t = annual_primary_energy(
        final_energy_by_carrier, project.primary_energy
    )

    # Indicators per m2 of conditioned floor area [kWh/(m2*year)]
    eu = E_u_total_wh / 1000.0 / conditioned_area
    ek = E_k_total_wh / 1000.0 / conditioned_area
    ep = E_p_total_wh / 1000.0 / conditioned_area
    ec = E_C_total_t / conditioned_area
    u_oze = share_of_renewable_energy(final_energy_by_carrier)

    heating_m2 = float(np.sum(total_Q_H)) / 1000.0 / conditioned_area
    cooling_m2 = float(np.sum(total_Q_C)) / 1000.0 / conditioned_area
    dhw_m2 = float(np.sum(Q_dhw_hourly)) / 1000.0 / conditioned_area

    # Monthly aggregation (each series summed once)
    monthly_heating = _monthly_sums(total_Q_H)
    monthly_cooling = _monthly_sums(total_Q_C)
    monthly_dhw = _monthly_sums(Q_dhw_hourly)
    monthly_int = _monthly_sums(total_q_int)
    monthly_sol = _monthly_sums(total_q_solar)
    monthly_tr = _monthly_sums(total_q_transmission)
    monthly_ve = _monthly_sums(total_q_ventilation)

    monthly: list[MonthlyResult] = []
    for month in range(1, 13):
        monthly.append(
            MonthlyResult(
                month=month,
                heating_kwh=monthly_heating[month - 1] / 1000.0,
                cooling_kwh=monthly_cooling[month - 1] / 1000.0,
                dhw_kwh=monthly_dhw[month - 1] / 1000.0,
                internal_gains_kwh=monthly_int[month - 1] / 1000.0,
                solar_gains_kwh=monthly_sol[month - 1] / 1000.0,
                transmission_losses_kwh=monthly_tr[month - 1] / 1000.0,
                ventilation_losses_kwh=monthly_ve[month - 1] / 1000.0,
            )
        )

    # Compliance checks: informational comparison only. The limits do not
    # come from this methodology regulation (which defines no EP limits);
    # they are indicative values, not a legal pass/fail requirement.
    compliance: list[ComplianceCheck] = []
    building_type_value = str(
        getattr(project.general.building_type, "value", project.general.building_type)
    )
    ep_limit = 75.0 if building_type_value == "residential" else 110.0
    compliance.append(
        ComplianceCheck(
            name=(
                f"Kontrola informacyjna: EP < {ep_limit} kWh/(m²·rok) "
                "(wartość poglądowa, nie jest wymaganiem prawnym)"
            ),
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
        design_heating_power_kw=design_heating_power_kw,
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
            "T_op": (
                total_T_op / total_zone_area if total_zone_area > 0 else df["T_e"].to_numpy()
            ).tolist(),
        },
        compliance=compliance,
    )
