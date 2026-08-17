"""Wykonawcze testy pełnego audytu technicznego silnika energetycznego.

Plik powstał wyłącznie na gałęzi audytowej. Testy oznaczone ``xfail`` opisują
wymaganie audytowe, którego obecna implementacja nie spełnia. Dzięki temu cały
zestaw może się wykonać do końca i jednocześnie jednoznacznie raportować
znalezione niezgodności zamiast zatrzymywać się na pierwszym błędzie.
"""

from __future__ import annotations

from datetime import date
import inspect

import numpy as np
import pandas as pd
import pytest

import app.engine.calculator as core_calculator
import app.engine.climate as climate_module
from app.engine.audited_calculator import _legal_readiness_checks
from app.engine.design_load import calculate_design_heat_load
from app.engine.envelope import (
    compute_opaque_heat_loss,
    compute_thermal_bridge_loss,
    compute_transparent_heat_loss,
)
from app.engine.ground_iso13370 import (
    characteristic_dimension_m,
    equivalent_thickness_m,
    slab_on_ground_u_value_w_m2k,
)
from app.engine.heat_recovery import (
    attach_heat_recovery_settings,
    heat_recovery_state,
)
from app.engine.internal_gains import internal_gains
from app.engine.normative_models import (
    DesignConditionsSettings,
    HeatRecoverySettings,
    LegalProvenanceSettings,
    NormativeSettings,
    PolishCertificateMonthlySettings,
)
from app.engine.polish_certificate_monthly import (
    _monthly_solar_gains_kwh,
    _monthly_transmission_kwh,
    _monthly_ventilation_kwh,
    calculate_polish_monthly_certificate,
)
from app.engine.solar import solar_gains_transparent
from app.engine.thermal_balance import (
    H_MS_W_M2K,
    SECONDS_PER_HOUR,
    TransmissionNetwork,
    opaque_external_conductance,
    solve_zone_5r1c,
    zone_thermal_properties,
)
from app.engine.ventilation import (
    ventilation_heat_loss,
    ventilation_heat_transfer_coefficient,
)
from app.schemas.models import (
    BuildingProject,
    BuildingSystems,
    GeneralInfo,
    InternalGainSource,
    InternalGains,
    LinearThermalBridge,
    OpaqueElement,
    PointThermalBridge,
    Schedule,
    SystemDHW,
    SystemHeatingCooling,
    ThermalBridgeConfig,
    ThermalZone,
    TransparentElement,
    Ventilation,
    ZoneType,
)


def _zero_internal_gains() -> InternalGains:
    return InternalGains(
        occupancy=InternalGainSource(power_density=0.0),
        lighting=InternalGainSource(power_density=0.0),
        equipment=InternalGainSource(power_density=0.0),
        normative_power_density_w_m2=None,
    )


def _simple_project(
    *,
    wall_area: float = 25.0,
    wall_u: float = 1.0,
    ventilation: Ventilation | None = None,
    zone_type: ZoneType = ZoneType.HEATED,
) -> BuildingProject:
    return BuildingProject(
        project_name="Audyt ręczny",
        general=GeneralInfo(
            building_name="Budynek referencyjny audytu",
            building_type="residential",
            dhw_usage_profile="residential_single_family",
            construction_year=2020,
            conditioned_floor_area=100.0,
            usable_floor_area=100.0,
            heated_volume=250.0,
            number_of_storeys=1,
        ),
        climate_station_id="synthetic",
        thermal_zones=[
            ThermalZone(
                id="z1",
                name="Strefa 1",
                zone_type=zone_type,
                floor_area=100.0,
                volume=250.0,
                setpoint_heating=20.0,
                setpoint_cooling=26.0,
                occupancy_density=0.0,
            )
        ],
        opaque_building_elements=[
            OpaqueElement(
                id="wall",
                name="Ściana testowa",
                zone_id="z1",
                element_type="external_wall",
                area=wall_area,
                u_value=wall_u,
                solar_absorptance=0.0,
            )
        ],
        transparent_building_elements=[],
        thermal_bridges=ThermalBridgeConfig(),
        ventilation=ventilation
        or Ventilation(
            ventilation_type="none",
            airflow_rate=0.0,
            infiltration_rate=0.0,
            fan_infiltration_rate=0.0,
        ),
        internal_gains=_zero_internal_gains(),
        systems=BuildingSystems(
            heating=SystemHeatingCooling(
                system_type="electric_direct",
                fuel_or_carrier="electricity",
                generation_efficiency=1.0,
                distribution_efficiency=1.0,
                storage_efficiency=1.0,
                control_efficiency=1.0,
                auxiliary_energy_kwh_year=0.0,
            ),
            cooling=SystemHeatingCooling(
                system_type="none",
                fuel_or_carrier="electricity",
            ),
            dhw=SystemDHW(system_type="none"),
        ),
    )


def _constant_climate(temperature_c: float) -> pd.DataFrame:
    index = pd.date_range("2023-01-01", periods=8760, freq="h")
    return pd.DataFrame(
        {
            "T_e": np.full(8760, temperature_c),
            "GHI": np.zeros(8760),
            "DNI": np.zeros(8760),
            "DHI": np.zeros(8760),
            "sun_zenith": np.full(8760, 90.0),
            "sun_azimuth": np.zeros(8760),
        },
        index=index,
    )


# ---------------------------------------------------------------------------
# 1. Testy jednostkowe z ręcznie policzonym wynikiem oczekiwanym
# ---------------------------------------------------------------------------


def test_manual_01_opaque_transmission_25m2_u1_dt20_is_500w() -> None:
    element = OpaqueElement(
        id="wall",
        name="Ściana",
        zone_id="z1",
        area=25.0,
        u_value=1.0,
    )
    result = compute_opaque_heat_loss(element, np.array([20.0]), np.array([0.0]))
    assert result[0] == pytest.approx(25.0 * 1.0 * 20.0)


def test_manual_02_transparent_transmission_5m2_u2_dt20_is_200w() -> None:
    element = TransparentElement(
        id="window",
        name="Okno",
        zone_id="z1",
        area=5.0,
        u_value=2.0,
        g_value=0.5,
    )
    result = compute_transparent_heat_loss(element, np.array([20.0]), np.array([0.0]))
    assert result[0] == pytest.approx(5.0 * 2.0 * 20.0)


def test_manual_03_linear_thermal_bridge_is_20w() -> None:
    zone = ThermalZone(id="z1", name="Strefa", floor_area=25.0, volume=125.0)
    bridges = ThermalBridgeConfig(
        linear_bridges=[
            LinearThermalBridge(
                id="lb",
                name="Mostek liniowy",
                zone_id="z1",
                psi_value=0.1,
                length=10.0,
            )
        ]
    )
    result = compute_thermal_bridge_loss(
        bridges,
        zone,
        np.array([20.0]),
        np.array([0.0]),
    )
    assert result[0] == pytest.approx(0.1 * 10.0 * 20.0)


def test_manual_04_point_thermal_bridge_is_40w() -> None:
    zone = ThermalZone(id="z1", name="Strefa", floor_area=25.0, volume=125.0)
    bridges = ThermalBridgeConfig(
        point_bridges=[
            PointThermalBridge(
                id="pb",
                name="Mostek punktowy",
                zone_id="z1",
                chi_value=0.5,
                count=4,
            )
        ]
    )
    result = compute_thermal_bridge_loss(
        bridges,
        zone,
        np.array([20.0]),
        np.array([0.0]),
    )
    assert result[0] == pytest.approx(0.5 * 4.0 * 20.0)


def test_manual_05_ventilation_360m3h_has_hve_120w_per_k() -> None:
    zone = ThermalZone(id="z1", name="Strefa", floor_area=100.0, volume=250.0)
    ventilation = Ventilation(
        ventilation_type="natural",
        airflow_rate=360.0,
        infiltration_rate=0.0,
        fan_infiltration_rate=0.0,
    )
    result = ventilation_heat_transfer_coefficient(ventilation, zone)
    assert result == pytest.approx(360.0 / 3600.0 * 1200.0)


def test_manual_06_ventilation_loss_360m3h_dt20_is_2400w() -> None:
    zone = ThermalZone(id="z1", name="Strefa", floor_area=100.0, volume=250.0)
    ventilation = Ventilation(
        ventilation_type="natural",
        airflow_rate=360.0,
        infiltration_rate=0.0,
        fan_infiltration_rate=0.0,
    )
    result = ventilation_heat_loss(
        ventilation,
        zone,
        np.array([20.0]),
        np.array([0.0]),
    )
    assert result[0] == pytest.approx(2400.0)


def test_manual_07_transparent_solar_gain_is_2000w(monkeypatch: pytest.MonkeyPatch) -> None:
    element = TransparentElement(
        id="window",
        name="Okno",
        zone_id="z1",
        area=10.0,
        u_value=1.0,
        g_value=0.5,
        frame_factor=0.2,
        shading_factor=1.0,
    )
    df = pd.DataFrame(index=pd.date_range("2023-01-01", periods=1, freq="h"))
    monkeypatch.setattr(
        "app.engine.solar.radiation_on_surface",
        lambda *args, **kwargs: pd.Series([500.0], index=df.index),
    )
    result = solar_gains_transparent(element, df)
    assert result[0] == pytest.approx(10.0 * 0.8 * 0.5 * 500.0)


def test_manual_08_full_shading_makes_transparent_solar_gain_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    element = TransparentElement(
        id="window",
        name="Okno",
        zone_id="z1",
        area=10.0,
        u_value=1.0,
        g_value=0.5,
        frame_factor=0.2,
        shading_factor=0.0,
    )
    df = pd.DataFrame(index=pd.date_range("2023-01-01", periods=1, freq="h"))
    monkeypatch.setattr(
        "app.engine.solar.radiation_on_surface",
        lambda *args, **kwargs: pd.Series([1000.0], index=df.index),
    )
    result = solar_gains_transparent(element, df)
    assert result[0] == pytest.approx(0.0)


def test_manual_09_occupancy_gain_is_80w() -> None:
    source = InternalGainSource(power_density=80.0, schedule=Schedule())
    index = pd.date_range("2023-01-01", periods=1, freq="h")
    result = internal_gains(0.1, 10.0, source, index, per_person=True)
    assert result[0] == pytest.approx(80.0 * 0.1 * 10.0)


def test_manual_10_lighting_gain_is_50w() -> None:
    source = InternalGainSource(power_density=5.0, schedule=Schedule())
    index = pd.date_range("2023-01-01", periods=1, freq="h")
    result = internal_gains(0.0, 10.0, source, index, per_person=False)
    assert result[0] == pytest.approx(5.0 * 10.0)


def test_manual_11_zero_schedule_makes_internal_gain_zero() -> None:
    source = InternalGainSource(
        power_density=5.0,
        schedule=Schedule(type="constant", constant_value=0.0),
    )
    index = pd.date_range("2023-01-01", periods=1, freq="h")
    result = internal_gains(0.0, 10.0, source, index, per_person=False)
    assert result[0] == pytest.approx(0.0)


def test_manual_12_ground_characteristic_dimension_25m2_p20_is_2_5m() -> None:
    assert characteristic_dimension_m(25.0, 20.0) == pytest.approx(2.5)


def test_manual_13_slab_u_value_matches_implemented_formula() -> None:
    area = 25.0
    perimeter = 20.0
    conductivity = 2.0
    floor_resistance = 2.0
    wall_thickness = 0.3
    b_prime = 2.0 * area / perimeter
    d_t = equivalent_thickness_m(conductivity, floor_resistance, wall_thickness)
    expected = (
        2.0
        * conductivity
        / (np.pi * b_prime + d_t)
        * np.log(np.pi * b_prime / d_t + 1.0)
    )
    result = slab_on_ground_u_value_w_m2k(
        area,
        perimeter,
        conductivity,
        floor_resistance,
        wall_thickness,
    )
    assert result == pytest.approx(expected)


def test_manual_14_design_load_one_wall_is_1000w() -> None:
    project = _simple_project(wall_area=25.0, wall_u=1.0)
    settings = DesignConditionsSettings(
        enabled=True,
        outdoor_design_temperature_c=-20.0,
    )
    result = calculate_design_heat_load(project, settings, annual_mean_outdoor_c=8.0)
    assert result.zones[0].transmission_w == pytest.approx(25.0 * 1.0 * 40.0)
    assert result.zones[0].ventilation_w == pytest.approx(0.0)
    assert result.total_w == pytest.approx(1000.0)


def test_manual_15_monthly_january_transmission_is_372kwh() -> None:
    project = _simple_project(wall_area=25.0, wall_u=1.0)
    zone = project.thermal_zones[0]
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[0.0] * 12,
    )
    result = _monthly_transmission_kwh(
        project,
        zone,
        np.full(12, 20.0),
        settings,
    )
    assert result[0] == pytest.approx(25.0 * 1.0 * 20.0 * 744.0 / 1000.0)


def test_manual_16_monthly_january_ventilation_is_1785_6kwh() -> None:
    ventilation = Ventilation(
        ventilation_type="natural",
        airflow_rate=360.0,
        infiltration_rate=0.0,
        fan_infiltration_rate=0.0,
    )
    project = _simple_project(ventilation=ventilation)
    zone = project.thermal_zones[0]
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[0.0] * 12,
    )
    result, _fallback = _monthly_ventilation_kwh(
        project,
        zone,
        np.full(12, 20.0),
        100.0,
        settings,
    )
    expected = 360.0 / 3600.0 * 1200.0 * 20.0 * 744.0 / 1000.0
    assert result[0] == pytest.approx(expected)


def test_manual_17_monthly_solar_gain_is_200kwh() -> None:
    project = _simple_project()
    project.transparent_building_elements = [
        TransparentElement(
            id="window",
            name="Okno",
            zone_id="z1",
            area=10.0,
            u_value=1.0,
            g_value=0.5,
            frame_factor=0.2,
            shading_factor=0.5,
        )
    ]
    settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[0.0] * 12,
        solar_irradiation_kwh_m2_by_element={"window": [100.0] * 12},
    )
    result = _monthly_solar_gains_kwh(project, project.thermal_zones[0], settings)
    assert result[0] == pytest.approx(10.0 * 0.8 * 0.5 * 0.5 * 100.0)


def test_manual_18_hourly_solver_pure_ventilation_need_equals_hve_dt() -> None:
    hours = 24
    h_ve = 120.0
    solution = solve_zone_5r1c(
        network=TransmissionNetwork(),
        h_ve=h_ve,
        t_e=np.zeros(hours),
        phi_int=np.zeros(hours),
        phi_sol=np.zeros(hours),
        properties=zone_thermal_properties(100.0),
        t_set_heating=20.0,
        t_set_cooling=None,
    )
    np.testing.assert_allclose(solution.q_heating, 120.0 * 20.0, atol=1e-7)


# ---------------------------------------------------------------------------
# 2. Testy graniczne i błędne dane
# ---------------------------------------------------------------------------


def test_edge_zero_ventilation_is_finite_and_zero() -> None:
    project = _simple_project()
    zone = project.thermal_zones[0]
    h_ve = ventilation_heat_transfer_coefficient(project.ventilation, zone)
    assert h_ve == pytest.approx(0.0)
    loss = ventilation_heat_loss(
        project.ventilation,
        zone,
        np.array([20.0]),
        np.array([-20.0]),
    )
    assert np.isfinite(loss).all()
    assert loss[0] == pytest.approx(0.0)


def test_edge_solver_rejects_negative_ventilation_coefficient() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        solve_zone_5r1c(
            network=TransmissionNetwork(),
            h_ve=-1.0,
            t_e=np.zeros(1),
            phi_int=np.zeros(1),
            phi_sol=np.zeros(1),
            properties=zone_thermal_properties(100.0),
            t_set_heating=20.0,
            t_set_cooling=None,
        )


def test_edge_solver_rejects_zero_floor_area_before_singular_network() -> None:
    with pytest.raises(ValueError, match="positive"):
        zone_thermal_properties(0.0)


def test_edge_100_percent_recovery_stays_finite() -> None:
    zone = ThermalZone(
        id="z1",
        name="Strefa",
        floor_area=100.0,
        volume=250.0,
        setpoint_heating=20.0,
    )
    ventilation = Ventilation(
        ventilation_type="mechanical_with_recovery",
        airflow_rate=200.0,
        heat_recovery_efficiency=1.0,
        infiltration_rate=0.0,
    )
    result = heat_recovery_state(
        ventilation,
        zone,
        np.array([-20.0, 0.0, 20.0]),
        200.0,
    )
    assert np.isfinite(result.supply_temperature_c).all()
    np.testing.assert_allclose(result.supply_temperature_c, 20.0)


# ---------------------------------------------------------------------------
# 3. Kontrola bilansu energii dla dnia zimowego, przejściowego i letniego
# ---------------------------------------------------------------------------


def test_three_day_reduced_network_energy_balance_closes_hour_by_hour() -> None:
    t_e = np.concatenate(
        [
            np.full(24, -10.0),
            np.full(24, 10.0),
            np.full(24, 32.0),
        ]
    )
    n = len(t_e)
    network = TransmissionNetwork()
    network.add_opaque(50.0, t_e)
    network.add_surface(15.0, t_e)
    properties = zone_thermal_properties(100.0)
    h_ve = np.full(n, 60.0)
    phi_int = np.full(n, 300.0)
    phi_sol = np.concatenate(
        [np.zeros(24), np.full(24, 200.0), np.full(24, 500.0)]
    )
    solution = solve_zone_5r1c(
        network=network,
        h_ve=h_ve,
        t_e=t_e,
        phi_int=phi_int,
        phi_sol=phi_sol,
        properties=properties,
        t_set_heating=20.0,
        t_set_cooling=26.0,
    )

    h_is = properties.h_tr_is
    h_ms = properties.h_tr_ms
    h_em = opaque_external_conductance(network.h_opaque, h_ms)
    frac_mass = properties.area_mass / properties.area_total_internal
    frac_surface = max(
        0.0,
        1.0
        - frac_mass
        - sum(network.h_surface) / (H_MS_W_M2K * properties.area_total_internal),
    )
    phi_ia = 0.5 * phi_int
    phi_rest = 0.5 * phi_int + phi_sol
    phi_m = frac_mass * phi_rest
    phi_st = frac_surface * phi_rest
    phi_hc = solution.q_heating - solution.q_cooling

    previous_mass = 20.0
    max_global_residual_w = 0.0
    daily_maxima: list[float] = []
    residuals: list[float] = []
    for hour in range(n):
        mass_mean = 0.5 * (previous_mass + solution.t_mass[hour])
        storage_w = (
            properties.capacity
            * (solution.t_mass[hour] - previous_mass)
            / SECONDS_PER_HOUR
        )
        external_to_mass_w = h_em * (t_e[hour] - mass_mean)
        surface_external_w = sum(
            h * (drive[hour] - solution.t_surface[hour])
            for h, drive in zip(network.h_surface, network.t_surface, strict=True)
        )
        ventilation_w = h_ve[hour] * (t_e[hour] - solution.t_air[hour])
        assigned_gains_w = phi_ia[hour] + phi_m[hour] + phi_st[hour]
        source_sum_w = (
            assigned_gains_w
            + phi_hc[hour]
            + external_to_mass_w
            + surface_external_w
            + ventilation_w
        )
        residual = storage_w - source_sum_w
        residuals.append(residual)
        max_global_residual_w = max(max_global_residual_w, abs(residual))
        previous_mass = solution.t_mass[hour]

    for day in range(3):
        daily = residuals[day * 24 : (day + 1) * 24]
        daily_maxima.append(max(abs(value) for value in daily))

    print(
        "AUDYT_BILANS_DOBOWY_W=",
        {
            "zimowy": daily_maxima[0],
            "przejsciowy": daily_maxima[1],
            "letni": daily_maxima[2],
            "maksimum": max_global_residual_w,
        },
    )
    assert max_global_residual_w < 1e-7


# ---------------------------------------------------------------------------
# 4. Krzyżowa walidacja silnika godzinowego i polskiej metody miesięcznej
# ---------------------------------------------------------------------------


def test_hourly_and_monthly_engines_agree_for_steady_no_gain_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _simple_project(wall_area=25.0, wall_u=1.0)
    climate = _constant_climate(0.0)
    monkeypatch.setattr(core_calculator, "_load_climate", lambda _project: climate)

    hourly = core_calculator.calculate_building_energy(project)
    monthly_settings = PolishCertificateMonthlySettings(
        enabled=True,
        official_bip_climate_data=True,
        monthly_outdoor_temperature_c=[0.0] * 12,
        heating_internal_temperature_c_by_zone={"z1": [20.0] * 12},
        heating_gain_utilization_by_zone={"z1": [1.0] * 12},
        internal_gain_density_w_m2_by_zone={"z1": 0.0},
    )
    monthly = calculate_polish_monthly_certificate(project, monthly_settings)

    hourly_kwh = hourly.annual_indicators.heating_kwh_m2_year * 100.0
    monthly_kwh = monthly.heating_useful_kwh
    manual_kwh = 25.0 * 1.0 * 20.0 * 8760.0 / 1000.0
    relative_difference = abs(hourly_kwh - monthly_kwh) / monthly_kwh
    print(
        "AUDYT_POROWNANIE_SILNIKOW=",
        {
            "godzinowy_kWh": hourly_kwh,
            "miesieczny_kWh": monthly_kwh,
            "reczny_kWh": manual_kwh,
            "roznica_wzgledna": relative_difference,
        },
    )
    assert hourly_kwh == pytest.approx(manual_kwh, rel=1e-7)
    assert monthly_kwh == pytest.approx(manual_kwh, rel=1e-12)
    assert relative_difference < 0.001


# ---------------------------------------------------------------------------
# 5. Niezgodności normatywne wykrywane jako oczekiwane niepowodzenia
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ISO 52016-1 metoda godzinowa wymaga właściwości cieplnych i węzłów "
        "poszczególnych przegród; obecny model ma jedną pojemność dla całej strefy."
    ),
)
def test_iso52016_requires_construction_level_thermal_mass_inputs() -> None:
    required_fields = {"areal_heat_capacity", "mass_distribution_class"}
    assert required_fields.issubset(set(OpaqueElement.model_fields))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ISO 52010-1 stosuje uproszczony model Pereza, a obecna transpozycja "
        "promieniowania używa modelu Hay-Davies."
    ),
)
def test_iso52010_surface_irradiance_uses_simplified_perez_not_hay_davies() -> None:
    source = inspect.getsource(climate_module.radiation_on_surface).lower()
    assert "perez" in source
    assert "haydavies" not in source


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Równoważna grubość w metodzie płyty na gruncie powinna uwzględniać "
        "również opór przejmowania po stronie zewnętrznej; funkcja nie ma takiego składnika."
    ),
)
def test_iso13370_equivalent_thickness_includes_external_surface_resistance() -> None:
    conductivity = 2.0
    floor_resistance = 2.0
    wall_thickness = 0.3
    r_si = 0.17
    r_se = 0.04
    expected = wall_thickness + conductivity * (r_si + floor_resistance + r_se)
    actual = equivalent_thickness_m(
        conductivity,
        floor_resistance,
        wall_thickness,
    )
    assert actual == pytest.approx(expected)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Model odzysku ciepła używa przez cały rok temperatury zadanej ogrzewania "
        "jako temperatury wywiewu, także podczas chłodzenia."
    ),
)
def test_heat_recovery_cooling_uses_actual_extract_temperature() -> None:
    zone = ThermalZone(
        id="z1",
        name="Strefa",
        zone_type="heated_and_cooled",
        floor_area=100.0,
        volume=250.0,
        setpoint_heating=20.0,
        setpoint_cooling=26.0,
    )
    ventilation = Ventilation(
        ventilation_type="mechanical_with_recovery",
        airflow_rate=200.0,
        heat_recovery_efficiency=0.8,
        infiltration_rate=0.0,
    )
    settings = HeatRecoverySettings(enabled=True)
    attach_heat_recovery_settings(ventilation, settings)
    result = heat_recovery_state(
        ventilation,
        zone,
        np.array([30.0]),
        200.0,
    )
    expected_supply = 30.0 + 0.8 * (26.0 - 30.0)
    assert result.supply_temperature_c[0] == pytest.approx(expected_supply)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PN-EN 12831-1 obejmuje obciążenie pojedynczych pomieszczeń; schemat "
        "projektu nie posiada modelu pomieszczeń wymaganych do pełnej procedury."
    ),
)
def test_en12831_design_load_has_individual_room_model() -> None:
    assert "design_rooms" in BuildingProject.model_fields


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Tryb formalny dopuszcza dowolną 12-miesięczną serię override energii "
        "użytkowej bez dedykowanego dowodu pochodzenia tej serii."
    ),
)
def test_formal_mode_rejects_unverified_useful_energy_override() -> None:
    project = _simple_project(wall_area=1000.0, wall_u=5.0)
    settings = NormativeSettings(
        polish_certificate=PolishCertificateMonthlySettings(
            enabled=True,
            official_bip_climate_data=True,
            monthly_outdoor_temperature_c=[-20.0] * 12,
            heating_useful_override_kwh_by_zone={"z1": [0.0] * 12},
        ),
        legal=LegalProvenanceSettings(
            certificate_mode=True,
            calculation_date=date(2026, 8, 17),
            methodology_source="Rozporządzenie - test audytowy",
            climate_data_source="BIP - test audytowy",
            utilization_factor_source="Polska Norma - test audytowy",
            ventilation_factor_source="Rozporządzenie - test audytowy",
            primary_energy_factor_sources={"electricity": "Źródło testowe"},
        ),
    )
    with pytest.raises(ValueError, match="override|zewnętrz"):
        _legal_readiness_checks(project, settings)


# ---------------------------------------------------------------------------
# 6. Test jednostek, znaków i kolejności działań
# ---------------------------------------------------------------------------


def test_units_monthly_aggregation_1000w_constant_equals_8760kwh_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _simple_project(wall_area=50.0, wall_u=1.0)
    climate = _constant_climate(0.0)
    monkeypatch.setattr(core_calculator, "_load_climate", lambda _project: climate)
    result = core_calculator.calculate_building_energy(project)
    annual_from_months = sum(month.heating_kwh for month in result.monthly)
    assert annual_from_months == pytest.approx(8760.0)


def test_sign_cooling_is_reported_as_positive_energy_need() -> None:
    solution = solve_zone_5r1c(
        network=TransmissionNetwork(),
        h_ve=120.0,
        t_e=np.full(24, 40.0),
        phi_int=np.zeros(24),
        phi_sol=np.zeros(24),
        properties=zone_thermal_properties(100.0),
        t_set_heating=None,
        t_set_cooling=26.0,
    )
    assert np.all(solution.q_cooling >= 0.0)
    assert np.all(solution.q_heating >= 0.0)
    assert not np.any((solution.q_heating > 0.0) & (solution.q_cooling > 0.0))


def test_detailed_recovery_is_not_counted_twice_in_hve_and_supply_temperature() -> None:
    zone = ThermalZone(
        id="z1",
        name="Strefa",
        floor_area=100.0,
        volume=250.0,
        setpoint_heating=20.0,
    )
    ventilation = Ventilation(
        ventilation_type="mechanical_with_recovery",
        airflow_rate=360.0,
        heat_recovery_efficiency=0.8,
        infiltration_rate=0.0,
        fan_infiltration_rate=0.0,
    )
    attach_heat_recovery_settings(ventilation, HeatRecoverySettings(enabled=True))
    h_ve = ventilation_heat_transfer_coefficient(ventilation, zone)
    recovery = heat_recovery_state(
        ventilation,
        zone,
        np.array([0.0]),
        360.0,
    )
    expected_hve_full_flow = 360.0 / 3600.0 * 1200.0
    expected_supply = 16.0
    assert h_ve == pytest.approx(expected_hve_full_flow)
    assert recovery.supply_temperature_c[0] == pytest.approx(expected_supply)
    expected_loss = expected_hve_full_flow * (20.0 - expected_supply)
    assert expected_loss == pytest.approx(480.0)
