"""Integracyjne testy logiki obliczeniowej na syntetycznych latach klimatycznych.

Zgodnie z docs/VALIDATION.md (sekcja "Testy integracyjne"): stała temperatura
zewnętrzna, brak nasłonecznienia, stałe zyski wewnętrzne. Pozwala to wyliczyć
oczekiwane wskaźniki EU/EK/EP/EC analitycznie, wprost ze wzorów metodyki:

- H_tr = suma(A*U) + mostki
- H_ve = (q_mech*(1-eta) + n_inf*V)/3600 * rho*cp
- stan ustalony: Q_H/h = (H_tr + H_ve) * (T_set - T_e)
- E_k = Q / (eta_g * eta_d * eta_s * eta_r)
- E_p = suma(E_k,i * f_p,i),  E_C = suma(E_k,i * W_e,i) / 10^6

Testy wielostrefowe pilnują, że podział na strefy nie zmienia bilansu całego
budynku (mostki i wentylacja liczone dokładnie raz).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pytest

from app.engine.calculator import calculate_building_energy
from app.engine.climate import make_synthetic_year
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
H_VE = (120.0 + 0.5 * 375.0) / 3600.0 * (1.2 * 1005)  # = 102.957 W/K
H = H_TR + H_VE                                        # = 171.657 W/K
Q_DHW_YEAR_WH = 50.0 * 0.03 * 150.0 * 365 * 4180.0 * 45.0 / 3600.0  # 4.5 osoby
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


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
            building_name="Dom referencyjny", building_type="residential",
            construction_year=2020, conditioned_floor_area=150.0,
            usable_floor_area=150.0, heated_volume=375.0, number_of_storeys=1,
        ),
        climate_station_id=WARSZAWA_STATION,
        thermal_zones=[
            ThermalZone(
                id="zone_1", name="Strefa 1", zone_type="heated",
                floor_area=150.0, volume=375.0,
                setpoint_heating=20.0, setpoint_cooling=None, occupancy_density=0.03,
            )
        ],
        opaque_building_elements=[
            OpaqueElement(id="wall_n", name="Ściana N", zone_id="zone_1",
                          orientation_azimuth=0.0, inclination=90.0,
                          area=40.0, u_value=0.25),
            OpaqueElement(id="wall_s", name="Ściana S", zone_id="zone_1",
                          orientation_azimuth=180.0, inclination=90.0,
                          area=40.0, u_value=0.25),
            OpaqueElement(id="roof", name="Dach", zone_id="zone_1",
                          orientation_azimuth=0.0, inclination=0.0,
                          area=90.0, u_value=0.18),
            OpaqueElement(id="floor", name="Podłoga", zone_id="zone_1",
                          orientation_azimuth=0.0, inclination=180.0,
                          area=90.0, u_value=0.25, adjacent_space_type="ground"),
        ],
        transparent_building_elements=[
            TransparentElement(id="win_s", name="Okno S", zone_id="zone_1",
                               orientation_azimuth=180.0, inclination=90.0,
                               area=10.0, u_value=1.0, g_value=0.6),
        ],
        ventilation=Ventilation(
            ventilation_type="natural", airflow_rate=120.0, infiltration_rate=0.5,
        ),
        internal_gains=InternalGains(
            occupancy=InternalGainSource(power_density=0.0),
            lighting=InternalGainSource(power_density=0.0),
            equipment=InternalGainSource(power_density=0.0),
        ),
        systems=BuildingSystems(
            heating=SystemHeatingCooling(
                system_type="gas_boiler", fuel_or_carrier="natural_gas",
                generation_efficiency=0.9, distribution_efficiency=0.95,
                storage_efficiency=1.0, control_efficiency=1.0,
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
    p.systems.heating = SystemHeatingCooling(system_type="none")
    p.systems.dhw = SystemDHW(
        system_type="electric_storage", fuel_or_carrier="electricity",
        daily_demand_per_person=50.0, target_temperature=55.0,
        cold_water_temperature=10.0, generation_efficiency=0.9,
        storage_efficiency=1.0, distribution_efficiency=0.6,
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
        assert ann.ek_kwh_m2_year == pytest.approx(
            Q_DHW_YEAR_WH / dhw_eff / 1000 / 150, rel=1e-6
        )
        assert ann.ep_kwh_m2_year == pytest.approx(
            Q_DHW_YEAR_WH / dhw_eff * 2.5 / 1000 / 150, rel=1e-6
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
        assert m.internal_gains_kwh == pytest.approx(
            360.0 * DAYS[month - 1] * 24 / 1000, rel=1e-6
        )

    def test_monthly_sums_to_annual(self):
        result = calculate_building_energy(_scenario_a_project())
        assert sum(m.dhw_kwh for m in result.monthly) == pytest.approx(
            Q_DHW_YEAR_WH / 1000, rel=1e-6
        )
        assert sum(m.internal_gains_kwh for m in result.monthly) == pytest.approx(
            360.0 * 8760 / 1000, rel=1e-6
        )

    def test_number_of_users_overrides_density(self):
        p = _scenario_a_project()
        p.systems.dhw.number_of_users = 5.0
        result = calculate_building_energy(p)
        q_5_users = 50.0 * 5.0 * 365 * 4180.0 * 45.0 / 3600.0
        assert result.annual_indicators.eu_kwh_m2_year == pytest.approx(
            q_5_users / 1000 / 150, rel=1e-6
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
        Q_wh = H * 20.0 * 8760.0  # stan ustalony: H * dT * 8760 h
        assert ann.heating_kwh_m2_year == pytest.approx(Q_wh / 1000 / 150, rel=1e-6)
        assert ann.eu_kwh_m2_year == pytest.approx(Q_wh / 1000 / 150, rel=1e-6)
        assert ann.dhw_kwh_m2_year == pytest.approx(0.0, abs=1e-9)
        assert ann.cooling_kwh_m2_year == pytest.approx(0.0, abs=1e-9)
        # kocioł gazowy: eta_g=0.9, eta_d=0.95 -> E_k = Q / 0.855
        assert ann.ek_kwh_m2_year == pytest.approx(Q_wh / 0.855 / 1000 / 150, rel=1e-6)
        assert ann.ep_kwh_m2_year == pytest.approx(
            Q_wh / 0.855 * 1.1 / 1000 / 150, rel=1e-6
        )
        assert ann.ec_tco2_m2_year == pytest.approx(
            Q_wh / 0.855 / 1e6 * 0.2 / 150, rel=1e-6
        )
        # Niezmienniki metodologii (sprawność < 1, fp > 1)
        assert ann.ek_kwh_m2_year >= ann.eu_kwh_m2_year
        assert ann.ep_kwh_m2_year >= ann.ek_kwh_m2_year

    def test_hourly_heating_constant_and_equal_to_h_delta_t(self):
        result = calculate_building_energy(_base_project())
        q_h = np.asarray(result.hourly["Q_H"])
        assert len(q_h) == 8760
        np.testing.assert_allclose(q_h, H * 20.0, rtol=1e-6)

    @pytest.mark.parametrize("month", range(1, 13))
    def test_monthly_heating_proportional_to_days(self, month):
        result = calculate_building_energy(_base_project())
        Q_wh = H * 20.0 * 8760.0
        assert result.monthly[month - 1].heating_kwh == pytest.approx(
            Q_wh * DAYS[month - 1] * 24 / 8760 / 1000, rel=1e-6
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
            no_fan.annual_indicators.ep_kwh_m2_year + 876.0 * 2.5 / 150, rel=1e-6
        )
        assert with_fan.annual_indicators.ec_tco2_m2_year == pytest.approx(
            no_fan.annual_indicators.ec_tco2_m2_year + 0.876 * 0.6 / 150, rel=1e-6
        )

    def test_no_systems_still_reports_useful_demand_with_zero_final(self):
        p = _base_project()
        p.systems.heating = SystemHeatingCooling(system_type="none")
        result = calculate_building_energy(p)
        ann = result.annual_indicators
        Q_wh = H * 20.0 * 8760.0
        assert ann.eu_kwh_m2_year == pytest.approx(Q_wh / 1000 / 150, rel=1e-6)
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
                id="garage", name="Garaż", zone_type="unheated",
                floor_area=50.0, volume=125.0, occupancy_density=0.0,
            )
        )
        single = calculate_building_energy(_base_project())
        with_garage = calculate_building_energy(p)
        assert with_garage.annual_indicators.eu_kwh_m2_year == pytest.approx(
            single.annual_indicators.eu_kwh_m2_year, rel=1e-6
        )


# ---------------------------------------------------------------------------
# Scenariusz C: pompa ciepła (COP z mapy temperatur)
# ---------------------------------------------------------------------------


class TestScenarioCHeatPump:
    @pytest.fixture(autouse=True)
    def _climate(self, synthetic_climate):
        synthetic_climate(0.0)

    def test_heat_pump_final_energy_with_cop_at_zero(self):
        p = _base_project()
        p.systems.heating = SystemHeatingCooling(
            system_type="heat_pump_air", fuel_or_carrier="electricity",
            generation_efficiency=3.5, distribution_efficiency=0.95,
            storage_efficiency=1.0, control_efficiency=1.0, sink_temperature=35.0,
        )
        result = calculate_building_energy(p)
        Q_wh = H * 20.0 * 8760.0
        cop_at_0 = 3.5 * (273.15 / 35.0) / (280.15 / 28.0)  # 2.7300 wg mapy COP
        assert result.annual_indicators.ek_kwh_m2_year == pytest.approx(
            Q_wh / cop_at_0 / 0.95 / 1000 / 150, rel=1e-6
        )
        assert result.annual_indicators.ep_kwh_m2_year == pytest.approx(
            Q_wh / cop_at_0 / 0.95 * 2.5 / 1000 / 150, rel=1e-6
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
            ThermalZone(id="zone_1", name="Z1", zone_type="heated",
                        floor_area=75.0, volume=187.5, setpoint_heating=20.0,
                        setpoint_cooling=None, occupancy_density=0.03),
            ThermalZone(id="zone_2", name="Z2", zone_type="heated",
                        floor_area=75.0, volume=187.5, setpoint_heating=20.0,
                        setpoint_cooling=None, occupancy_density=0.03),
        ]
        for el in p.opaque_building_elements:
            if el.id in {"wall_n", "floor"}:
                el.zone_id = "zone_1"
            else:
                el.zone_id = "zone_2"
        p.transparent_building_elements[0].zone_id = "zone_1"
        p.thermal_bridges = ThermalBridgeConfig(
            linear_bridges=[
                LinearThermalBridge(id="lb", name="lb", psi_value=0.1,
                                    length=50.0, zone_id="zone_2")
            ]
        )
        return p

    def test_two_zones_without_bridges_equal_single_zone(self):
        """Podział na strefy sam w sobie nie zmienia bilansu (bez mostków)."""
        p = self._two_zone_project()
        p.thermal_bridges = ThermalBridgeConfig()
        two = calculate_building_energy(p)

        single = _base_project()
        single.ventilation.airflow_rate = 0.0
        one = calculate_building_energy(single)

        assert two.annual_indicators.heating_kwh_m2_year == pytest.approx(
            one.annual_indicators.heating_kwh_m2_year, rel=1e-6
        )

    def test_bridges_counted_once_across_zones(self):
        two = calculate_building_energy(self._two_zone_project())

        single = _base_project()
        single.ventilation.airflow_rate = 0.0
        single.thermal_bridges = ThermalBridgeConfig(
            linear_bridges=[
                LinearThermalBridge(id="lb", name="lb", psi_value=0.1,
                                    length=50.0, zone_id="zone_1")
            ]
        )
        one = calculate_building_energy(single)

        assert two.annual_indicators.heating_kwh_m2_year == pytest.approx(
            one.annual_indicators.heating_kwh_m2_year, rel=1e-6
        )
