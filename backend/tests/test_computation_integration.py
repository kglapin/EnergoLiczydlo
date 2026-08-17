"""Integracyjne testy logiki obliczeniowej na syntetycznych latach klimatycznych.

Zgodnie z docs/VALIDATION.md (sekcja "Testy integracyjne"): stała temperatura
zewnętrzna, brak nasłonecznienia, stałe zyski wewnętrzne. Pozwala to wyliczyć
oczekiwane wskaźniki EU/EK/EP/EC analitycznie, wprost ze wzorów metodyki:

- H_tr = suma(A*U) + mostki;  H_ve = (q_mech*(1-eta) + n_inf*V)/3600 * rho*cp
- stan ustalony sieci 5R1C: niezależne rozwiązanie układu równań węzłów
  (patrz ``_steady_state_heating_w``) - powietrze przypięte do setpointu
- E_k = Q / (eta_g * eta_d * eta_s * eta_r)
- E_p = suma(E_k,i * f_p,i);  f_p(el) = 2.5 (current tabela 1, Dz.U. 2023 poz. 697)

Testy wielostrefowe pilnują, że podział na strefy nie zmienia bilansu całego
budynku (mostki i wentylacja liczone dokładnie raz).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pytest

from app.engine.calculator import calculate_building_energy
from app.engine.climate import make_synthetic_year
from app.engine.thermal_balance import opaque_external_conductance
from app.schemas.models import (
    BuildingProject,
    BuildingSystems,
    GeneralInfo,
    InternalGains,
    InternalGainSource,
    LinearThermalBridge,
    OpaqueElement,
    SystemDHW,
    SystemHeatingCooling,
    ThermalBridgeConfig,
    ThermalZone,
    TransparentElement,
    Ventilation,
)

WARSZAWA_STATION = "POL_MZ_Okecie-Warszawa-Chopina.Intl.AP.123750_TMYx.2009-2023"

# Analityczne współczynniki budynku referencyjnego (formuły niezależne od kodu)
H_TR = 2 * (40.0 * 0.25) + 90.0 * 0.18 + 90.0 * 0.25 + 10.0 * 1.0  # = 68.7 W/K
H_VE = (120.0 + 0.5 * 375.0) / 3600.0 * 1200.0  # = 102.444 W/K
Q_DHW_YEAR_WH = 1.40 * 150.0 * 4.19 * 1.0 * 45.0 * 0.90 * 365 / 3600 * 1000
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

FP_ELECTRICITY = 2.5  # tabela 1 rozporządzenia Dz.U. 2023 poz. 697


def _steady_state_heating_w(
    h_opaque: float,
    h_surface: float,
    h_ve: float,
    t_set: float,
    t_e: float,
    floor_area: float,
) -> float:
    """Niezależne (analityczne) rozwiązanie stanu ustalonego sieci 5R1C.

    Rozwiązuje wprost równania bilansu węzłów (masa / powierzchnia / powietrze
    przypięte do setpointu) wg definicji modelu z PN-EN ISO 52016-1 / ISO 13790:
    H_tr,is = 3.45*At, H_tr,ms = 9.1*Am, At = 4.5*Af, Am = 2.5*Af.
    """
    h_is = 3.45 * 4.5 * floor_area
    h_ms = 9.1 * 2.5 * floor_area
    h_em = opaque_external_conductance(h_opaque, h_ms)
    # niewiadome [Tm, ts]; ti = t_set
    a = np.array(
        [
            [h_ms + h_em, -h_ms],
            [h_ms, -(h_is + h_ms + h_surface)],
        ]
    )
    b = np.array([h_em * t_e, -h_is * t_set - h_surface * t_e])
    _, t_s = np.linalg.solve(a, b)
    return h_is * (t_set - t_s) + h_ve * (t_set - t_e)


def _reference_heating_wh() -> float:
    """Roczne zapotrzebowanie na ogrzewanie budynku referencyjnego (stan ustalony)."""
    q_h = _steady_state_heating_w(
        h_opaque=2 * (40.0 * 0.25) + 90.0 * 0.18 + 90.0 * 0.25,  # 58.7 W/K
        h_surface=10.0 * 1.0,
        h_ve=H_VE,
        t_set=20.0,
        t_e=0.0,
        floor_area=150.0,
    )
    return q_h * 8760.0


def _boiler_aux_wh() -> float:
    """E_el,pom,H dla kotła gazowego, Af = 150 m2 (tabela 20, wiersz 7a)."""
    return 0.50 * 2520.0 * 150.0


@lru_cache(maxsize=4)
def _synthetic(T_e: float):
    """Rok syntetyczny: stała temperatura, brak promieniowania."""
    return make_synthetic_year(T_e=T_e, GHI=0.0, DNI=0.0, DHI=0.0)


@pytest.fixture
def synthetic_climate(monkeypatch):
    def _patch(T_e: float) -> None:
        df = _synthetic(T_e)
        monkeypatch.setattr("app.engine.calculator._load_climate", lambda project: df)

    return _patch


def _base_project() -> BuildingProject:
    """Budynek referencyjny 150 m2, ogrzewanie gazowe, bez CWU, bez zysków.

    Scenariusz B: T_e = 0°C -> czysty bilans ogrzewania.
    """
    return BuildingProject(
        project_name="Scenariusz B",
        general=GeneralInfo(
            building_name="Dom referencyjny",
            building_type="residential",
            dhw_usage_profile="residential_single_family",
            construction_year=2020,
            conditioned_floor_area=150.0,
            usable_floor_area=150.0,
            heated_volume=375.0,
            number_of_storeys=1,
        ),
        climate_station_id=WARSZAWA_STATION,
        thermal_zones=[
            ThermalZone(
                id="zone_1",
                name="Strefa 1",
                zone_type="heated",
                floor_area=150.0,
                volume=375.0,
                setpoint_heating=20.0,
                setpoint_cooling=None,
                occupancy_density=0.03,
            )
        ],
        opaque_building_elements=[
            OpaqueElement(
                id="wall_n",
                name="Ściana N",
                zone_id="zone_1",
                orientation_azimuth=0.0,
                inclination=90.0,
                area=40.0,
                u_value=0.25,
            ),
            OpaqueElement(
                id="wall_s",
                name="Ściana S",
                zone_id="zone_1",
                orientation_azimuth=180.0,
                inclination=90.0,
                area=40.0,
                u_value=0.25,
            ),
            OpaqueElement(
                id="roof",
                name="Dach",
                zone_id="zone_1",
                orientation_azimuth=0.0,
                inclination=0.0,
                area=90.0,
                u_value=0.18,
            ),
            # Podłoga przy stałej 0°C: jednorodny napęd całej sieci, żeby stan
            # ustalony miał zamkniętą postać analityczną. Oddzielny test
            # sprawdza fizykę podłogi gruntowej (sinusoida z opóźnieniem).
            OpaqueElement(
                id="floor",
                name="Podłoga",
                zone_id="zone_1",
                orientation_azimuth=0.0,
                inclination=180.0,
                area=90.0,
                u_value=0.25,
                adjacent_space_type="constant_temperature",
                adjacent_temperature=0.0,
            ),
        ],
        transparent_building_elements=[
            TransparentElement(
                id="win_s",
                name="Okno S",
                zone_id="zone_1",
                orientation_azimuth=180.0,
                inclination=90.0,
                area=10.0,
                u_value=1.0,
                g_value=0.6,
            ),
        ],
        ventilation=Ventilation(
            ventilation_type="natural",
            airflow_rate=120.0,
            infiltration_rate=0.5,
        ),
        internal_gains=InternalGains(
            occupancy=InternalGainSource(power_density=0.0),
            lighting=InternalGainSource(power_density=0.0),
            equipment=InternalGainSource(power_density=0.0),
        ),
        systems=BuildingSystems(
            heating=SystemHeatingCooling(
                system_type="gas_boiler",
                fuel_or_carrier="natural_gas",
                generation_efficiency=0.9,
                distribution_efficiency=0.95,
                storage_efficiency=1.0,
                control_efficiency=1.0,
            ),
            cooling=None,
            dhw=SystemDHW(system_type="none"),
        ),
    )


def _scenario_a_project() -> BuildingProject:
    """T_e = 20°C -> brak ogrzewania i chłodzenia; EU = samo CWU."""
    p = _base_project()
    p.project_name = "Scenariusz A"
    p.thermal_zones[0].setpoint_cooling = 26.0
    p.internal_gains.occupancy.power_density = 80.0  # 80 W/os * 4.5 os = 360 W
    # Izotermiczne otoczenie: podłoga też przy 20°C, żeby cała obudowa była
    # w równowadze z setpointem i jedynym bilansem było CWU.
    p.opaque_building_elements[3].adjacent_temperature = 20.0
    p.systems.heating = SystemHeatingCooling(system_type="none")
    p.systems.dhw = SystemDHW(
        system_type="electric_storage",
        fuel_or_carrier="electricity",
        generation_efficiency=0.9,
        storage_efficiency=1.0,
        distribution_efficiency=0.6,
        utilization_efficiency=1.0,
    )
    return p


# ---------------------------------------------------------------------------
# Scenariusz A: T_e = 20°C, tylko CWU
# ---------------------------------------------------------------------------


class TestScenarioADhwOnly:
    @pytest.fixture(autouse=True)
    def _climate(self, synthetic_climate):
        synthetic_climate(20.0)

    def test_annual_indicators_analytic(self):
        result = calculate_building_energy(_scenario_a_project())
        ann = result.annual_indicators
        dhw_eff = 0.9 * 1.0 * 0.6 * 1.0
        assert ann.heating_kwh_m2_year == pytest.approx(0.0, abs=1e-9)
        assert ann.cooling_kwh_m2_year == pytest.approx(0.0, abs=1e-9)
        assert ann.eu_kwh_m2_year == pytest.approx(Q_DHW_YEAR_WH / 1000 / 150, rel=1e-6)
        assert ann.dhw_kwh_m2_year == pytest.approx(Q_DHW_YEAR_WH / 1000 / 150, rel=1e-6)
        assert ann.ek_kwh_m2_year == pytest.approx(Q_DHW_YEAR_WH / dhw_eff / 1000 / 150, rel=1e-6)
        assert ann.ep_kwh_m2_year == pytest.approx(
            Q_DHW_YEAR_WH / dhw_eff * FP_ELECTRICITY / 1000 / 150, rel=1e-6
        )
        assert ann.ec_tco2_m2_year == pytest.approx(
            Q_DHW_YEAR_WH / dhw_eff / 1e6 * 0.6 / 150, rel=1e-6
        )
        assert ann.u_oze_percent == 0.0

    @pytest.mark.parametrize("month", range(1, 13))
    def test_monthly_dhw_proportional_to_days(self, month):
        result = calculate_building_energy(_scenario_a_project())
        m = result.monthly[month - 1]
        assert m.month == month
        assert m.heating_kwh == pytest.approx(0.0, abs=1e-9)
        assert m.cooling_kwh == pytest.approx(0.0, abs=1e-9)
        assert m.dhw_kwh == pytest.approx(
            Q_DHW_YEAR_WH * DAYS[month - 1] * 24 / 8760 / 1000, rel=1e-6
        )
        # Zyski wewnętrzne: 360 W * godziny miesiąca
        assert m.internal_gains_kwh == pytest.approx(360.0 * DAYS[month - 1] * 24 / 1000, rel=1e-6)

    def test_monthly_sums_to_annual(self):
        result = calculate_building_energy(_scenario_a_project())
        assert sum(m.dhw_kwh for m in result.monthly) == pytest.approx(
            Q_DHW_YEAR_WH / 1000, rel=1e-6
        )
        assert sum(m.internal_gains_kwh for m in result.monthly) == pytest.approx(
            360.0 * 8760 / 1000, rel=1e-6
        )

    def test_legacy_per_person_inputs_do_not_change_normative_dhw_demand(self):
        p = _scenario_a_project()
        p.systems.dhw.daily_demand_per_person = 999.0
        p.systems.dhw.number_of_users = 100.0
        p.systems.dhw.target_temperature = 99.0
        p.systems.dhw.cold_water_temperature = -5.0
        result = calculate_building_energy(p)
        assert result.annual_indicators.eu_kwh_m2_year == pytest.approx(
            Q_DHW_YEAR_WH / 1000 / 150, rel=1e-6
        )


# ---------------------------------------------------------------------------
# Scenariusz B: T_e = 0°C, czyste ogrzewanie gazowe
# ---------------------------------------------------------------------------


class TestScenarioBHeatingOnly:
    @pytest.fixture(autouse=True)
    def _climate(self, synthetic_climate):
        synthetic_climate(0.0)

    def test_annual_indicators_analytic(self):
        result = calculate_building_energy(_base_project())
        ann = result.annual_indicators
        Q_wh = _reference_heating_wh()
        # rel=2e-3: rozruch termiczny masy (~15 kWh przy ~29.6 MWh rocznie)
        assert ann.heating_kwh_m2_year == pytest.approx(Q_wh / 1000 / 150, rel=2e-3)
        assert ann.eu_kwh_m2_year == pytest.approx(Q_wh / 1000 / 150, rel=2e-3)
        assert ann.dhw_kwh_m2_year == pytest.approx(0.0, abs=1e-9)
        assert ann.cooling_kwh_m2_year == pytest.approx(0.0, abs=1e-9)
        # kocioł gazowy: eta_g=0.9, eta_d=0.95 -> Q/0.855; + E_el,pom (tabela 20)
        assert ann.ek_kwh_m2_year == pytest.approx(
            (Q_wh / 0.855 + _boiler_aux_wh()) / 1000 / 150, rel=2e-3
        )
        assert ann.ep_kwh_m2_year == pytest.approx(
            (Q_wh / 0.855 * 1.1 + _boiler_aux_wh() * FP_ELECTRICITY) / 1000 / 150, rel=2e-3
        )
        assert ann.ec_tco2_m2_year == pytest.approx(
            (Q_wh / 0.855 * 0.2 + _boiler_aux_wh() * 0.6) / 1e6 / 150, rel=2e-3
        )
        # Niezmienniki metodologii (sprawność < 1, fp > 1)
        assert ann.ek_kwh_m2_year >= ann.eu_kwh_m2_year
        assert ann.ep_kwh_m2_year >= ann.ek_kwh_m2_year

    def test_hourly_heating_constant_and_equal_to_steady_state(self):
        result = calculate_building_energy(_base_project())
        q_h = np.asarray(result.hourly["Q_H"])
        assert len(q_h) == 8760
        expected = _reference_heating_wh() / 8760.0
        # Wolna stała czasowa masy (C_m/H_em ~ 12 dni): po ~4 miesiącach
        # każda godzina jest stanem ustalonym co do 1e-6.
        np.testing.assert_allclose(q_h[3000:], expected, rtol=1e-6)

    @pytest.mark.parametrize("month", range(2, 13))
    def test_monthly_heating_proportional_to_days(self, month):
        result = calculate_building_energy(_base_project())
        Q_wh = _reference_heating_wh()
        assert result.monthly[month - 1].heating_kwh == pytest.approx(
            Q_wh * DAYS[month - 1] * 24 / 8760 / 1000, rel=2e-3
        )

    def test_compliance_ep_fails_above_wt2021_limit(self):
        result = calculate_building_energy(_base_project())
        ep = result.annual_indicators.ep_kwh_m2_year
        ep_check = next(c for c in result.compliance if "EP" in c.name)
        assert ep > 75.0  # ~258 kWh/m2 dla tego budynku bez izolacji wzorcowej
        assert ep_check.passed is False
        assert str(round(ep, 2)) in ep_check.message

    def test_fan_energy_adds_exact_electricity(self):
        no_fan = calculate_building_energy(_base_project())
        p = _base_project()
        p.ventilation.ventilation_type = "exhaust"
        p.ventilation.mechanical_fan_power = 100.0
        with_fan = calculate_building_energy(p)
        # 100 W * 8760 h = 876 kWh -> +5.84 kWh/m2 (H_ve bez zmian)
        assert with_fan.annual_indicators.ek_kwh_m2_year == pytest.approx(
            no_fan.annual_indicators.ek_kwh_m2_year + 876.0 / 150, rel=1e-6
        )
        assert with_fan.annual_indicators.ep_kwh_m2_year == pytest.approx(
            no_fan.annual_indicators.ep_kwh_m2_year + 876.0 * FP_ELECTRICITY / 150,
            rel=1e-6,
        )
        assert with_fan.annual_indicators.ec_tco2_m2_year == pytest.approx(
            no_fan.annual_indicators.ec_tco2_m2_year + 0.876 * 0.6 / 150, rel=1e-6
        )

    def test_no_systems_still_reports_useful_demand_with_zero_final(self):
        p = _base_project()
        p.systems.heating = SystemHeatingCooling(system_type="none")
        result = calculate_building_energy(p)
        ann = result.annual_indicators
        Q_wh = _reference_heating_wh()
        assert ann.eu_kwh_m2_year == pytest.approx(Q_wh / 1000 / 150, rel=2e-3)
        assert ann.ek_kwh_m2_year == 0.0
        assert ann.ep_kwh_m2_year == 0.0
        assert ann.ec_tco2_m2_year == 0.0

    def test_hourly_output_t_int_is_indoor_temperature(self):
        result = calculate_building_energy(_base_project())
        t_int = np.asarray(result.hourly["T_int"])
        # Ogrzewanie utrzymuje 20°C, a T_e = 0°C przez cały rok
        np.testing.assert_allclose(t_int, 20.0, atol=0.01)

    def test_unheated_zone_does_not_add_heating_demand(self):
        p = _base_project()
        p.thermal_zones.append(
            ThermalZone(
                id="garage",
                name="Garaż",
                zone_type="unheated",
                floor_area=50.0,
                volume=125.0,
                occupancy_density=0.0,
            )
        )
        single = calculate_building_energy(_base_project())
        with_garage = calculate_building_energy(p)
        assert with_garage.annual_indicators.eu_kwh_m2_year == pytest.approx(
            single.annual_indicators.eu_kwh_m2_year, rel=1e-6
        )
        np.testing.assert_allclose(
            with_garage.hourly["Q_transmission"], single.hourly["Q_transmission"]
        )
        np.testing.assert_allclose(
            with_garage.hourly["Q_ventilation"], single.hourly["Q_ventilation"]
        )


# ---------------------------------------------------------------------------
# Scenariusz C: pompa ciepła (sezonowy COP metodologii)
# ---------------------------------------------------------------------------


class TestScenarioCHeatPump:
    @pytest.fixture(autouse=True)
    def _climate(self, synthetic_climate):
        synthetic_climate(0.0)

    def test_heat_pump_final_energy_uses_seasonal_cop(self):
        p = _base_project()
        p.systems.heating = SystemHeatingCooling(
            system_type="heat_pump_air",
            fuel_or_carrier="electricity",
            generation_efficiency=3.5,
            distribution_efficiency=0.95,
            storage_efficiency=1.0,
            control_efficiency=1.0,
            sink_temperature=35.0,
        )
        result = calculate_building_energy(p)
        Q_wh = _reference_heating_wh()
        assert result.annual_indicators.ek_kwh_m2_year == pytest.approx(
            Q_wh / 3.5 / 0.95 / 1000 / 150, rel=2e-3
        )
        assert result.annual_indicators.ep_kwh_m2_year == pytest.approx(
            Q_wh / 3.5 / 0.95 * FP_ELECTRICITY / 1000 / 150, rel=2e-3
        )


# ---------------------------------------------------------------------------
# Agregacja wielu stref
# ---------------------------------------------------------------------------


class TestMultiZoneAggregation:
    @pytest.fixture(autouse=True)
    def _climate(self, synthetic_climate):
        synthetic_climate(0.0)

    def _two_zone_project(self) -> BuildingProject:
        p = _base_project()
        p.ventilation.airflow_rate = 0.0  # infiltracja sumuje się 1:1 z objętością
        p.thermal_zones = [
            ThermalZone(
                id="zone_1",
                name="Z1",
                zone_type="heated",
                floor_area=75.0,
                volume=187.5,
                setpoint_heating=20.0,
                setpoint_cooling=None,
                occupancy_density=0.03,
            ),
            ThermalZone(
                id="zone_2",
                name="Z2",
                zone_type="heated",
                floor_area=75.0,
                volume=187.5,
                setpoint_heating=20.0,
                setpoint_cooling=None,
                occupancy_density=0.03,
            ),
        ]
        for el in p.opaque_building_elements:
            if el.id in {"wall_n", "floor"}:
                el.zone_id = "zone_1"
            else:
                el.zone_id = "zone_2"
        p.transparent_building_elements[0].zone_id = "zone_1"
        p.thermal_bridges = ThermalBridgeConfig(
            linear_bridges=[
                LinearThermalBridge(
                    id="lb", name="lb", psi_value=0.1, length=50.0, zone_id="zone_2"
                )
            ]
        )
        return p

    def test_two_zones_without_bridges_equal_single_zone(self):
        """Podział na strefy sam w sobie nie zmienia bilansu (bez mostków).

        Dwie strefy mają odrębne sieci 5R1C (inne A_m, A_t), więc równość jest
        przybliżona - pilnujemy braku podwójnego liczenia strat.
        """
        p = self._two_zone_project()
        p.thermal_bridges = ThermalBridgeConfig()
        two = calculate_building_energy(p)

        single = _base_project()
        single.ventilation.airflow_rate = 0.0
        one = calculate_building_energy(single)

        assert two.annual_indicators.heating_kwh_m2_year == pytest.approx(
            one.annual_indicators.heating_kwh_m2_year, rel=0.03
        )

    def test_bridges_counted_once_across_zones(self):
        two = calculate_building_energy(self._two_zone_project())

        single = _base_project()
        single.ventilation.airflow_rate = 0.0
        single.thermal_bridges = ThermalBridgeConfig(
            linear_bridges=[
                LinearThermalBridge(
                    id="lb", name="lb", psi_value=0.1, length=50.0, zone_id="zone_1"
                )
            ]
        )
        one = calculate_building_energy(single)

        assert two.annual_indicators.heating_kwh_m2_year == pytest.approx(
            one.annual_indicators.heating_kwh_m2_year, rel=0.03
        )


# ---------------------------------------------------------------------------
# Fizyka przyległości i podziału wentylacji (poprawki metodyczne)
# ---------------------------------------------------------------------------


class TestGroundAndVentilationPhysics:
    @pytest.fixture(autouse=True)
    def _climate(self, synthetic_climate):
        synthetic_climate(0.0)

    def test_ground_floor_driven_by_annual_mean_not_hourly_air(self):
        """Przy stałym T_e = 0°C podłoga gruntowa (sinusoida wokół średniej 0°C)
        daje ten sam roczny bilans co napęd stały 0°C - pilnuje, że solver
        napędza grunt średnioroczną sinusoidą, a nie godzinowym T_e."""
        constant = _base_project()
        ground = _base_project()
        ground.opaque_building_elements[3].adjacent_space_type = "ground"
        q_constant = calculate_building_energy(constant).annual_indicators.heating_kwh_m2_year
        q_ground = calculate_building_energy(ground).annual_indicators.heating_kwh_m2_year
        # Amplituda 5 K tylko przesuwa straty w czasie (masa je filtrowuje),
        # więc zgodność powinna być wysoka.
        assert q_ground == pytest.approx(q_constant, rel=0.05)

    def test_multi_zone_airflow_is_split_not_duplicated(self):
        """Budynkowy strumień 120 m3/h rozdzielony proporcjonalnie do powierzchni:
        dwie strefy po 75 m2 dostają po 60 m3/h (a nie 2 x 120 m3/h)."""
        p = _two_zone_split_project()
        single = _base_project()
        single.ventilation.infiltration_rate = 0.0  # porównywalny wariant
        two = calculate_building_energy(p)
        one = calculate_building_energy(single)
        # Strata wentylacyjna identyczna łącznie -> podobne zapotrzebowanie
        # (mimo dwóch sieci 5R1C, tolerancja jak w TestMultiZoneAggregation)
        assert two.annual_indicators.heating_kwh_m2_year == pytest.approx(
            one.annual_indicators.heating_kwh_m2_year, rel=0.05
        )

    def test_calculator_connects_explicit_supply_temperature_to_hourly_balance(self):
        project = _base_project()
        project.ventilation = Ventilation(
            ventilation_type="mechanical_with_recovery",
            operation_mode="periodic",
            airflow_rate=100.0,
            heat_recovery_efficiency=0.5,
            infiltration_rate=0.5,
            fan_infiltration_rate=0.04,
            supply_temperature=20.0,
            schedule={"type": "constant", "constant_value": 1.0},
        )
        result = calculate_building_energy(project)

        mechanical_flow = 100.0
        external_flow = 0.04 * 375.0
        expected_supply = mechanical_flow * 20.0 / (mechanical_flow + external_flow)
        expected_h_ve = (mechanical_flow + external_flow) / 3600.0 * 1200.0
        np.testing.assert_allclose(result.hourly["T_supply"], expected_supply)
        np.testing.assert_allclose(
            result.hourly["Q_ventilation"],
            expected_h_ve * (20.0 - expected_supply),
        )

    def test_ground_heat_pump_cop_is_not_driven_by_outdoor_air(self):
        """PC glikol/woda: bez podanej temperatury źródła COP = znamionowy
        (a nie mapowany z T_e, co zawalało COP zimą)."""
        p = _base_project()
        p.systems.heating = SystemHeatingCooling(
            system_type="heat_pump_ground",
            fuel_or_carrier="electricity",
            generation_efficiency=4.0,
            distribution_efficiency=0.95,
            storage_efficiency=1.0,
            control_efficiency=1.0,
        )
        result = calculate_building_energy(p)
        Q_wh = _reference_heating_wh()
        aux_wh = 0.45 * 1600.0 * 150.0  # tabela 20 w.9a: napęd PC glikol/woda
        assert result.annual_indicators.ek_kwh_m2_year == pytest.approx(
            (Q_wh / 4.0 / 0.95 + aux_wh) / 1000 / 150, rel=2e-3
        )


def _two_zone_split_project() -> BuildingProject:
    """Dwie równe strefy; strumień mechaniczny 120 m3/h dzieli się 60/60."""
    p = _base_project()
    p.ventilation.infiltration_rate = 0.0
    p.thermal_zones = [
        ThermalZone(
            id="zone_1",
            name="Z1",
            zone_type="heated",
            floor_area=75.0,
            volume=187.5,
            setpoint_heating=20.0,
            setpoint_cooling=None,
            occupancy_density=0.03,
        ),
        ThermalZone(
            id="zone_2",
            name="Z2",
            zone_type="heated",
            floor_area=75.0,
            volume=187.5,
            setpoint_heating=20.0,
            setpoint_cooling=None,
            occupancy_density=0.03,
        ),
    ]
    for el in p.opaque_building_elements:
        if el.id in {"wall_n", "floor"}:
            el.zone_id = "zone_1"
        else:
            el.zone_id = "zone_2"
    p.transparent_building_elements[0].zone_id = "zone_1"
    return p


class TestRegulationGaps:
    """Uzupełnienia metodologiczne w pełnym przepływie obliczeń."""

    @pytest.fixture(autouse=True)
    def _climate(self, synthetic_climate):
        synthetic_climate(20.0)

    def test_dhw_storage_losses_table_13_path(self):
        """Zasobnik 100 dm3 elektryczny w nieogrzewanej: ΔQ_W,s = 2452,8 kWh
        (wzór 30), E_k = (Q + ΔQ_d + ΔQ_s)/η_g zamiast Q/(ηg·ηd)."""
        from app.engine.systems import dhw_storage_standby_loss_kwh

        p = _scenario_a_project()  # T_e=20: samo CWU, ηg=0.9, ηd=0.6
        p.systems.dhw.storage_volume_dm3 = 100.0
        p.systems.dhw.storage_location = "unheated"
        result = calculate_building_energy(p)
        standby = dhw_storage_standby_loss_kwh(100.0, "unheated", "electric")
        assert standby == pytest.approx(100.0 * 2.80 * 8760.0 / 1000.0)
        q_kwh = Q_DHW_YEAR_WH / 1000.0
        delta_d = q_kwh * (1.0 / 0.6 - 1.0)
        expected_ek = (q_kwh + delta_d + standby) / 0.9 / 150.0
        assert result.annual_indicators.ek_kwh_m2_year == pytest.approx(expected_ek, rel=1e-6)

    def test_office_lighting_leni_enters_electricity_not_useful_energy(self):
        """Q_k,L = LENI·A_L (wzór 35) enters EK/EP, not EU."""
        p = _scenario_a_project()  # izotermiczne 20°C, bez ogrzewania
        p.general.building_type = "office"
        p.general.dhw_usage_profile = "office"
        p.general.lighting_indicator_leni = 15.0
        p.systems.dhw = SystemDHW(system_type="none")
        p.internal_gains.occupancy.power_density = 0.0
        result = calculate_building_energy(p)
        ann = result.annual_indicators
        e_l_m2 = 15.0 * 150.0 / 150.0  # A_L = Af = 150
        assert ann.eu_kwh_m2_year == pytest.approx(0.0, abs=1e-6)
        assert ann.ek_kwh_m2_year == pytest.approx(e_l_m2, rel=1e-6)
        assert ann.ep_kwh_m2_year == pytest.approx(e_l_m2 * FP_ELECTRICITY, rel=1e-6)

    def test_lighting_ignored_for_residential(self):
        p = _scenario_a_project()  # izotermiczne 20°C
        p.general.lighting_indicator_leni = 15.0  # mieszkalny: nie wyznacza się
        p.systems.dhw = SystemDHW(system_type="none")
        result = calculate_building_energy(p)
        # bez CWU i bez ogrzewania: EU = 0 (oświetlenie zignorowane)
        assert result.annual_indicators.eu_kwh_m2_year == pytest.approx(0.0, abs=1e-6)
        assert result.annual_indicators.ek_kwh_m2_year == pytest.approx(0.0, abs=1e-6)

    def test_zero_airflow_uses_normative_stream(self):
        """airflow_rate = 0 -> V0 z tabeli 24 (0,31e-3·Af) zamiast zera."""
        p = _scenario_a_project()
        p.ventilation.airflow_rate = 0.0
        result = calculate_building_energy(p)
        assert result.status == "success"
        # Strata wentylacyjna > 0 mimo zerowego wejścia (strumień normatywny)
        total_ve = sum(m.ventilation_losses_kwh for m in result.monthly)
        assert total_ve > 0.0
