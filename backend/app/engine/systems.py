"""Building technical-system models: heating, cooling and DHW final energy.

This module converts useful energy needs (Q_H, Q_C, Q_W) into final energy
consumption E_k, taking into account generator efficiency / COP and
distribution / emission / control losses.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# Default seasonal generation efficiencies / COPs per source type, mirroring
# the values from the methodology tables (rozporządzenie Dz.U. 2015 poz. 376,
# tabele 2-26) that the frontend presets also use.  Used only when a project
# carries no explicit generation efficiency.
DEFAULT_GENERATION_EFFICIENCY: dict[str, float] = {
    "electric_direct": 0.99,
    "gas_boiler": 0.87,
    "gas_condensing": 0.94,
    "oil_boiler": 0.87,
    "biomass_boiler": 0.70,
    "coal_boiler": 0.82,
    "fireplace": 0.70,
    "heat_pump_air": 3.0,
    "heat_pump_ground": 4.0,
    "heat_pump_water": 4.0,
    "district_heating": 0.98,
    "split_ac": 3.9,
    "multisplit_vrv": 4.1,
    "vrv": 4.1,
    "liquid_chiller_air": 4.0,
    "liquid_chiller_water": 5.6,
    "passive_ground_cooling": 10.0,
    "absorption_cooling": 0.8,
    # DHW-only sources (tabela 6 of the methodology)
    "electric_storage": 0.96,
    "electric_instantaneous": 0.99,
    "gas_instantaneous": 0.85,
}

# DHW source efficiencies differ from the space-heating values for shared
# source types (lower DHW temperatures / part load); these follow tabela 6
# and the frontend presets.
DHW_GENERATION_EFFICIENCY: dict[str, float] = {
    "gas_boiler": 0.83,
    "gas_condensing": 0.85,
    "heat_pump_air": 2.6,
    "heat_pump_ground": 3.0,
    "heat_pump_water": 3.0,
    "district_heating": 0.97,
}


def default_generation_efficiency(system: Any, fallback: float = 0.96) -> float:
    """Seasonal efficiency/COP fallback for a system without explicit data."""
    system_type = str(getattr(system, "system_type", ""))
    is_dhw = getattr(system, "distribution_type", None) is not None
    if is_dhw and system_type in DHW_GENERATION_EFFICIENCY:
        return DHW_GENERATION_EFFICIENCY[system_type]
    return DEFAULT_GENERATION_EFFICIENCY.get(system_type, fallback)


def total_system_efficiency(
    generation_efficiency: float,
    distribution_efficiency: float,
    storage_efficiency: float,
    control_efficiency: float,
) -> float:
    """Return the total seasonal system efficiency/COP product.

    The generation term is ηH,g/ηC,g (or COP/SEER); the remaining terms are
    the distribution, storage and control/use factors.  The product may be
    greater than one for heat pumps and cooling systems because COP/SEER is
    not bounded by one.
    """
    values = (
        generation_efficiency,
        distribution_efficiency,
        storage_efficiency,
        control_efficiency,
    )
    if any(value <= 0.0 for value in values):
        raise ValueError("System efficiency components must be positive")
    return float(np.prod(values))


def constant_efficiency_final_energy(
    Q_demand_wh: np.ndarray, efficiency: float, distribution_factor: float = 1.0
) -> np.ndarray:
    """Final energy [Wh] for a system with constant efficiency/COP."""
    if efficiency <= 0:
        raise ValueError("Efficiency must be positive")
    return np.where(Q_demand_wh > 0, Q_demand_wh / efficiency / distribution_factor, 0.0)


def heat_pump_cop_map(
    T_e: pd.Series | np.ndarray,
    T_sink: float,
    source_type: str = "air",
    rated_cop: float = 3.5,
    rated_T_source: float = 7.0,
    rated_T_sink: float = 35.0,
) -> np.ndarray:
    """Simple COP map for an air-source or water-source heat pump.

    Uses a Carnot-like relative approach: COP scales with the ratio of
    temperature lifts. This is a placeholder; production should use
    manufacturer or standard (EN 14511 / EN 14825) part-load curves.

    Parameters
    ----------
    T_e : array-like
        Heat source temperature [°C].
    T_sink : float
        Heating water temperature [°C].
    source_type : str
        'air' or 'water'.
    rated_cop : float
        COP at rated conditions.
    rated_T_source : float
        Rated source temperature [°C].
    rated_T_sink : float
        Rated sink temperature [°C].

    Returns
    -------
    np.ndarray
        Hourly COP values.
    """
    T_source_k = np.asarray(T_e, dtype=float) + 273.15
    T_sink_k = T_sink + 273.15
    rated_source_k = rated_T_source + 273.15
    rated_sink_k = rated_T_sink + 273.15

    # Carnot-relative scaling (very simplified)
    theoretical_ratio = (T_source_k / (T_sink_k - T_source_k)) / (
        rated_source_k / (rated_sink_k - rated_source_k)
    )
    cop = rated_cop * theoretical_ratio
    return np.clip(cop, 1.0, 6.0)


DHW_WATER_SPECIFIC_HEAT_KJ_KG_K = 4.19
DHW_WATER_DENSITY_KG_L = 1.0
DHW_TAP_TEMPERATURE_C = 55.0
DHW_COLD_WATER_TEMPERATURE_C = 10.0
DHW_DAYS_PER_YEAR = 365
DHW_STORAGE_HOURS_PER_YEAR = 8760.0  # t_sW, wzór (30)

# Tabela 13: jednostkowa strata ciepła zasobnika q_S [W/dm³] w zależności od
# lokalizacji, pojemności i rodzaju zasobnika. Klucz objętości = najmniejsza
# objętość normowa >= zadanej; "-" w normie (kolumna elektryczna w miejscu
# poboru dla dużych objętości) oznaczona jako None.
_STORAGE_LOSS_TABLE_13: dict[tuple[str, int], dict[str, float | None]] = {
    ("unheated", 25): {"100": 0.68, "50": 1.13, "20": 2.04, "electric": 2.80, "gas": 3.13},
    ("unheated", 50): {"100": 0.54, "50": 0.86, "20": 1.58, "electric": 2.80, "gas": 3.07},
    ("unheated", 100): {"100": 0.43, "50": 0.65, "20": 1.23, "electric": 2.80, "gas": 3.02},
    ("unheated", 200): {"100": 0.34, "50": 0.49, "20": 0.95, "electric": None, "gas": 2.96},
    ("unheated", 500): {"100": 0.25, "50": 0.34, "20": 0.68, "electric": None, "gas": 2.89},
    ("unheated", 1000): {"100": 0.20, "50": 0.26, "20": 0.53, "electric": None, "gas": 2.84},
    ("unheated", 1500): {"100": 0.18, "50": 0.22, "20": 0.46, "electric": None, "gas": 2.81},
    ("unheated", 2000): {"100": 0.16, "50": 0.20, "20": 0.41, "electric": None, "gas": 2.78},
    ("heated", 25): {"100": 0.55, "50": 0.92, "20": 1.66, "electric": 2.28, "gas": 2.55},
    ("heated", 50): {"100": 0.44, "50": 0.70, "20": 1.29, "electric": 2.28, "gas": 2.50},
    ("heated", 100): {"100": 0.35, "50": 0.53, "20": 1.00, "electric": 2.28, "gas": 2.46},
    ("heated", 200): {"100": 0.28, "50": 0.40, "20": 0.78, "electric": None, "gas": 2.41},
    ("heated", 500): {"100": 0.21, "50": 0.28, "20": 0.56, "electric": None, "gas": 2.35},
    ("heated", 1000): {"100": 0.17, "50": 0.21, "20": 0.43, "electric": None, "gas": 2.31},
    ("heated", 1500): {"100": 0.14, "50": 0.18, "20": 0.37, "electric": None, "gas": 2.28},
    ("heated", 2000): {"100": 0.13, "50": 0.16, "20": 0.33, "electric": None, "gas": 2.27},
}
_STORAGE_VOLUMES = [25, 50, 100, 200, 500, 1000, 1500, 2000]


def storage_unit_loss_w_dm3(
    volume_dm3: float,
    location: str = "unheated",
    tank_kind: str = "indirect",
    insulation_mm: float | None = None,
) -> float | None:
    """Strata jednostkowa zasobnika q_S [W/dm³] wg tabeli 13 rozporządzenia.

    ``tank_kind``: "indirect" (pośrednio podgrzewane / biwalentne solarne /
    elektryczne całodobowe - wg grubości izolacji), "electric" (w miejscu
    poboru), "gas" (zasobniki gazowe).  Objętość zaokrąglana w górę do
    najbliższego wiersza tabeli (powyżej 2000 dm3 brak danych -> None).
    """
    if volume_dm3 <= 0:
        raise ValueError("storage volume must be positive")
    if location not in {"heated", "unheated"}:
        raise ValueError("storage location must be 'heated' or 'unheated'")
    if tank_kind not in {"indirect", "electric", "gas"}:
        raise ValueError("tank_kind must be 'indirect', 'electric' or 'gas'")
    row_volume = next((v for v in _STORAGE_VOLUMES if volume_dm3 <= v), None)
    if row_volume is None:
        return None
    row = _STORAGE_LOSS_TABLE_13[(location, row_volume)]
    if tank_kind == "electric":
        return row["electric"]
    if tank_kind == "gas":
        return row["gas"]
    if insulation_mm is None:
        raise ValueError("insulation_mm is required for an indirect storage tank")
    insulation_key = next(
        (key for key in ("100", "50", "20") if np.isclose(float(key), insulation_mm)),
        None,
    )
    if insulation_key is None:
        raise ValueError(
            "insulation_mm must be one of the normative table-13 values: 20, 50 or 100"
        )
    return row[insulation_key]


def dhw_storage_standby_loss_kwh(
    volume_dm3: float,
    location: str = "unheated",
    tank_kind: str = "indirect",
    insulation_mm: float | None = None,
) -> float | None:
    """Roczne straty ciepła zasobnika ΔQ_W,s [kWh/rok] wg wzoru (30):

    ΔQ_W,s = V_S · q_S · t_sW · 10⁻³  (dm³ · W/dm³ · h -> Wh -> kWh).
    """
    q_s = storage_unit_loss_w_dm3(volume_dm3, location, tank_kind, insulation_mm)
    if q_s is None:
        return None
    return volume_dm3 * q_s * DHW_STORAGE_HOURS_PER_YEAR / 1000.0


# Rozporządzenie, załącznik nr 1, § 5.3, tabela 27: (VWi [dm³/(m²·d)], kR).
# Profiles with a value range or a value defined only from documentation are
# deliberately not represented here; the UI must not invent a normative value.
DHW_PROFILE_PARAMETERS: dict[str, tuple[float, float]] = {
    "residential_single_family": (1.40, 0.90),
    "residential_multi_family_lump_sum": (2.00, 0.90),
    "residential_multi_family_individual_metering": (1.60, 0.90),
    "office": (0.35, 0.70),
    "education": (0.80, 0.55),
    "healthcare": (6.50, 1.00),
    "retail_services": (0.60, 0.78),
    "collective_residential": (3.75, 0.60),
    "warehouse": (0.10, 0.70),
}


def annual_dhw_useful_energy(floor_area_m2: float, usage_profile: str) -> float:
    """Calculate annual useful DHW energy Q_W,nd [Wh] from § 5.3/table 27.

    Q_W,nd = VWi · Af · cW · ρW · (θW - θ0) · kR · tR / 3600.
    The regulatory equation produces kWh/year because cW is expressed in
    kJ/(kg·K); the engine uses Wh internally, so the result is multiplied by
    1000. The DHW source efficiency is deliberately not used at this stage.
    """
    profile_key = str(getattr(usage_profile, "value", usage_profile))
    try:
        vwi_l_m2_day, correction_factor = DHW_PROFILE_PARAMETERS[profile_key]
    except KeyError as exc:
        available_profiles = ", ".join(sorted(DHW_PROFILE_PARAMETERS))
        raise ValueError(
            f"Unsupported DHW usage profile: {profile_key}. Choose one of: {available_profiles}"
        ) from exc

    energy_kwh = (
        vwi_l_m2_day
        * floor_area_m2
        * DHW_WATER_SPECIFIC_HEAT_KJ_KG_K
        * DHW_WATER_DENSITY_KG_L
        * (DHW_TAP_TEMPERATURE_C - DHW_COLD_WATER_TEMPERATURE_C)
        * correction_factor
        * DHW_DAYS_PER_YEAR
        / 3600.0
    )
    return energy_kwh * 1000.0


def final_energy_dhw(
    Q_demand_wh: float | np.ndarray,
    efficiency: float,
    standby_loss_factor: float = 1.0,
) -> float | np.ndarray:
    """Final energy for DHW [Wh] including storage and distribution losses."""
    if efficiency <= 0:
        raise ValueError("Efficiency must be positive")
    return Q_demand_wh / efficiency * standby_loss_factor


# ---------------------------------------------------------------------------
# Energia pomocnicza E_el,pom - tabela 20 rozporządzenia (q_el [W/m2], t_el [h]).
# Wiersze mapowane na typ źródła i powierzchnię Af; wentylatory zależą od
# krotności wymiany i udziału czasu użytkowania β.
# ---------------------------------------------------------------------------

Tabela20Row = tuple[float, float]  # (q_el [W/m2], t_el [h/rok])


def heating_auxiliary_demand_wh(
    system_type: str,
    floor_area_m2: float,
    installation_type: str | None = None,
) -> float:
    """E_el,pom,H [Wh/rok] wg wzoru (37) i tabeli 20.

    Source rows (7--10) are combined with receiver-side circulation-pump
    rows (1--2) when the installation classification is known. A hydronic
    boiler or heat pump therefore includes both its source controls and the
    heating-circuit pump. An unclassified installation does not invent a
    pump demand.
    """
    st = str(system_type)
    if floor_area_m2 <= 0:
        raise ValueError("floor_area_m2 must be positive")
    rows: list[Tabela20Row] = []
    small = floor_area_m2 <= 250.0
    if st in ("gas_boiler", "gas_condensing", "oil_boiler", "coal_boiler", "fireplace"):
        # 7: napęd pomocniczy i regulacja kotła do ogrzewania
        rows.append((0.50, 2520.0) if small else (0.15, 3900.0))
    elif st == "heat_pump_water":
        rows.append((0.70, 1600.0))
    elif st == "heat_pump_ground":
        rows.append((0.45, 1600.0))
    elif st == "district_heating":
        rows.append((0.09, 8760.0))  # 10: regulacja węzła cieplnego
    # electric_direct: brak urządzeń pomocniczych

    installation = str(installation_type or "")
    if installation == "water_radiators":
        rows.append((0.30, 5700.0) if floor_area_m2 <= 250.0 else (0.15, 4700.0))
    elif installation == "water_surface":
        if floor_area_m2 > 250.0:
            raise ValueError(
                "Table 20 does not provide a default circulation-pump row for "
                "water-surface systems above 250 m2; enter explicit auxiliary energy"
            )
        rows.append((0.50, 6700.0))
    return sum(q * t * floor_area_m2 for q, t in rows)


def dhw_auxiliary_demand_wh(
    system_type: str,
    floor_area_m2: float,
    distribution_type: str | None = None,
) -> float:
    """E_el,pom,W [Wh/rok] wg wzoru (38) i tabeli 20 (kluczowe wiersze)."""
    st = str(system_type)
    dist = str(distribution_type or "")
    small = floor_area_m2 <= 250.0
    rows: list[Tabela20Row] = []
    if st in ("gas_boiler", "gas_condensing", "oil_boiler", "coal_boiler", "fireplace"):
        rows.append((1.40, 310.0) if small else (0.50, 410.0))  # 6: napęd kotła
        rows.append((0.25, 270.0) if small else (0.20, 580.0))  # 4: pompa ładująca
    elif st == "heat_pump_water":
        rows.append((0.70, 400.0))
    elif st == "heat_pump_ground":
        rows.append((0.45, 400.0))
    elif st == "district_heating":
        rows.append((0.09, 8760.0))  # 10: regulacja węzła (CO + CWU)
    # 3: pompa cyrkulacyjna tylko dla systemów z obiegiem cyrkulacyjnym
    if dist in (
        "central_circulation_uninsulated",
        "central_circulation_insulated",
        "central_circulation_time_limited",
    ):
        rows.append((0.15, 8760.0) if small else (0.04, 7300.0))
    # electric_storage / electric_instantaneous: brak urządzeń pomocniczych
    return sum(q * t * floor_area_m2 for q, t in rows)


def ventilation_fan_power_w_m2(ventilation_type: str, air_change_rate: float) -> float:
    """q_el wentylatorów [W/m2] wg tabeli 20, wiersze 12/13."""
    supply_extract = ventilation_type in ("mechanical", "mechanical_with_recovery")
    if supply_extract:  # 12: centrala nawiewno-wywiewna
        return 0.50 if air_change_rate <= 0.6 else 1.30
    if ventilation_type in ("exhaust", "hybrid"):  # 13: centrala wywiewna
        return 0.40 if air_change_rate <= 0.6 else 0.90
    return 0.0


def ventilation_fan_hours_per_year(beta: float) -> float:
    """t_el wentylatorów = 8760 · β (przypis tabeli 20)."""
    return 8760.0 * min(max(beta, 0.0), 1.0)
