"""Kompleksowe testy jednostkowe logiki obliczeniowej silnika.

Każdy test porównuje wynik z niezależnie wyliczoną wartością analityczną
(zgodnie ze strategią w docs/VALIDATION.md, sekcja "Testy jednostkowe").
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from app.engine.climate import (
    AIR_DENSITY_KG_M3,
    AIR_SPECIFIC_HEAT_J_KGK,
    annual_hourly_index,
    haversine_distance_km,
    make_synthetic_year,
    radiation_on_surface,
)
from app.engine.envelope import (
    adjacent_temperature,
    compute_opaque_heat_loss,
    compute_thermal_bridge_loss,
    compute_transparent_heat_loss,
    total_transmission_coefficient,
)
from app.engine.internal_gains import (
    evaluate_schedule,
    internal_gains,
    total_internal_gains,
)
from app.engine.primary_energy import (
    annual_primary_energy,
    share_of_renewable_energy,
)
from app.engine.systems import (
    constant_efficiency_final_energy,
    dhw_energy_demand,
    final_energy_dhw,
    heat_pump_cop_map,
)
from app.engine.thermal_balance import (
    solve_hourly_balance,
    thermal_capacity,
)
from app.engine.ventilation import (
    ventilation_heat_loss,
    ventilation_heat_transfer_coefficient,
)
from app.schemas.models import (
    AdjacentSpaceType,
    ElementType,
    InternalGains,
    InternalGainSource,
    LinearThermalBridge,
    OpaqueElement,
    PointThermalBridge,
    PrimaryEnergyFactors,
    Schedule,
    ThermalBridgeConfig,
    ThermalZone,
    TransparentElement,
    Ventilation,
)

CP_VOLUMETRIC = AIR_DENSITY_KG_M3 * AIR_SPECIFIC_HEAT_J_KGK  # 1206 J/(m3*K)


# ---------------------------------------------------------------------------
# Wentylacja
# ---------------------------------------------------------------------------


def _zone(**kwargs) -> ThermalZone:
    defaults = {"id": "z1", "name": "z1", "floor_area": 150.0, "volume": 375.0}
    defaults.update(kwargs)
    return ThermalZone(**defaults)


class TestVentilation:
    def test_h_ve_natural_with_infiltration_analytic(self):
        """H_ve = (q_mech*(1-eta) + 0.5*V)/3600 * rho*cp [W/K]."""
        vent = Ventilation(
            ventilation_type="natural", airflow_rate=120.0,
            heat_recovery_efficiency=0.0, infiltration_rate=0.5,
        )
        zone = _zone(volume=375.0)
        H_ve = ventilation_heat_transfer_coefficient(vent, zone)
        expected = (120.0 / 3600.0 + 0.5 * 375.0 / 3600.0) * CP_VOLUMETRIC
        assert H_ve == pytest.approx(expected, rel=1e-12)

    def test_h_ve_heat_recovery_reduces_mechanical_part(self):
        """Odzysk ciepła zmniejsza tylko strumień mechaniczny."""
        vent = Ventilation(
            ventilation_type="mechanical_with_recovery", airflow_rate=100.0,
            heat_recovery_efficiency=0.75, infiltration_rate=0.0,
        )
        H_ve = ventilation_heat_transfer_coefficient(vent, _zone())
        expected = (100.0 * (1 - 0.75) / 3600.0) * CP_VOLUMETRIC
        assert H_ve == pytest.approx(expected, rel=1e-12)

    def test_h_ve_full_recovery_zero_infiltration_is_zero(self):
        vent = Ventilation(
            ventilation_type="mechanical_with_recovery", airflow_rate=200.0,
            heat_recovery_efficiency=1.0, infiltration_rate=0.0,
        )
        assert ventilation_heat_transfer_coefficient(vent, _zone()) == 0.0

    def test_ventilation_heat_loss_analytic(self):
        vent = Ventilation(airflow_rate=120.0, infiltration_rate=0.5)
        zone = _zone()
        T_int = np.full(24, 20.0)
        T_e = np.full(24, 0.0)
        loss = ventilation_heat_loss(vent, zone, T_int, T_e)
        H_ve = (120.0 / 3600.0 + 0.5 * 375.0 / 3600.0) * CP_VOLUMETRIC
        np.testing.assert_allclose(loss, H_ve * 20.0)

    def test_ventilation_heat_loss_schedule_multiplier(self):
        vent = Ventilation(airflow_rate=120.0, infiltration_rate=0.5)
        zone = _zone()
        T_int = np.full(24, 20.0)
        T_e = np.full(24, 0.0)
        schedule = np.linspace(0.0, 1.0, 24)
        loss = ventilation_heat_loss(vent, zone, T_int, T_e, schedule_profile=schedule)
        H_ve = (120.0 / 3600.0 + 0.5 * 375.0 / 3600.0) * CP_VOLUMETRIC
        np.testing.assert_allclose(loss, schedule * H_ve * 20.0)


# ---------------------------------------------------------------------------
# Przegrody / bilans przenikania
# ---------------------------------------------------------------------------


def _opaque(**kwargs) -> OpaqueElement:
    defaults = {
        "id": "el", "name": "el", "zone_id": "z1",
        "element_type": ElementType.EXTERNAL_WALL,
        "orientation_azimuth": 0.0, "inclination": 90.0,
        "area": 10.0, "u_value": 0.2,
    }
    defaults.update(kwargs)
    return OpaqueElement(**defaults)


class TestEnvelope:
    def test_opaque_heat_loss_outdoor_analytic(self):
        wall = _opaque(area=10.0, u_value=0.2)
        loss = compute_opaque_heat_loss(wall, np.full(8760, 20.0), np.full(8760, 0.0))
        np.testing.assert_allclose(loss, 10.0 * 0.2 * 20.0)  # 40 W
        assert loss.sum() == pytest.approx(40.0 * 8760.0)  # 350.4 kWh/rok

    def test_transparent_heat_loss_analytic(self):
        win = TransparentElement(
            id="w", name="w", zone_id="z1", area=5.0, u_value=1.4, g_value=0.6,
        )
        loss = compute_transparent_heat_loss(win, np.full(8760, 20.0), np.full(8760, -5.0))
        np.testing.assert_allclose(loss, 5.0 * 1.4 * 25.0)  # 175 W

    def test_adjacent_temperature_ground_sinusoid_analytic(self):
        """T_gruntu = mean(T_e) - 5*cos(2*pi*h/8760); minimum w styczniu."""
        floor = _opaque(
            element_type=ElementType.GROUND_FLOOR, inclination=180.0,
            adjacent_space_type=AdjacentSpaceType.GROUND,
        )
        T_e = np.full(8760, 8.0)
        T_adj = adjacent_temperature(floor, T_e)
        assert T_adj[0] == pytest.approx(8.0 - 5.0)          # h=0: cos(0)=1
        assert T_adj[2190] == pytest.approx(8.0, abs=1e-9)   # równonoc: cos(pi/2)=0
        assert T_adj[4380] == pytest.approx(8.0 + 5.0)       # lipiec: cos(pi)=-1

    def test_adjacent_temperature_unheated_zone_plus_3k(self):
        wall = _opaque(adjacent_space_type=AdjacentSpaceType.UNHEATED_ZONE)
        T_adj = adjacent_temperature(wall, np.full(10, 2.0))
        np.testing.assert_allclose(T_adj, 5.0)

    def test_adjacent_temperature_constant(self):
        wall = _opaque(
            adjacent_space_type=AdjacentSpaceType.CONSTANT_TEMPERATURE,
            adjacent_temperature=12.0,
        )
        T_adj = adjacent_temperature(wall, np.full(10, 20.0))
        np.testing.assert_allclose(T_adj, 12.0)

    def test_adjacent_temperature_constant_without_value_raises(self):
        wall = _opaque(
            adjacent_space_type=AdjacentSpaceType.CONSTANT_TEMPERATURE,
            adjacent_temperature=None,
        )
        with pytest.raises(ValueError, match="CONSTANT_TEMPERATURE"):
            adjacent_temperature(wall, np.full(10, 20.0))

    def test_internal_partition_to_heated_zone_has_no_loss(self):
        """Fizyka: przegroda między dwiema strefami o tej samej temperaturie
        nie powinna generować strat ciepła (dT = 0)."""
        wall = _opaque(adjacent_space_type=AdjacentSpaceType.HEATED_ZONE)
        loss = compute_opaque_heat_loss(wall, np.full(8760, 20.0), np.full(8760, 0.0))
        np.testing.assert_allclose(loss, 0.0)

    def test_thermal_bridge_loss_analytic_and_zone_filtering(self):
        zone_a = _zone(id="za")
        zone_b = _zone(id="zb")
        bridges = ThermalBridgeConfig(
            linear_bridges=[
                LinearThermalBridge(id="a", name="a", psi_value=0.05, length=100.0, zone_id="za"),
                LinearThermalBridge(id="b", name="b", psi_value=0.10, length=50.0, zone_id="zb"),
            ],
            point_bridges=[
                PointThermalBridge(id="pa", name="pa", chi_value=0.6, count=6, zone_id="za"),
                PointThermalBridge(id="pb", name="pb", chi_value=0.9, count=2, zone_id="zb"),
            ],
        )
        T_int = np.full(8760, 20.0)
        T_e = np.full(8760, 0.0)
        loss_a = compute_thermal_bridge_loss(bridges, zone_a, T_int, T_e)
        loss_b = compute_thermal_bridge_loss(bridges, zone_b, T_int, T_e)
        np.testing.assert_allclose(loss_a, (0.05 * 100.0 + 0.6 * 6) * 20.0)  # 172 W
        np.testing.assert_allclose(loss_b, (0.10 * 50.0 + 0.9 * 2) * 20.0)  # 116 W

    def test_total_transmission_coefficient_analytic(self):
        opaque = [_opaque(area=10.0, u_value=0.2)]
        transparent = [
            TransparentElement(
                id="w", name="w", zone_id="z1", area=5.0, u_value=0.9, g_value=0.6
            )
        ]
        bridges = ThermalBridgeConfig(
            linear_bridges=[
                LinearThermalBridge(id="lb", name="lb", psi_value=0.05, length=10.0, zone_id="z1")
            ],
            point_bridges=[
                PointThermalBridge(id="pb", name="pb", chi_value=0.5, count=4, zone_id="z1")
            ],
        )
        H = total_transmission_coefficient(opaque, transparent, bridges)
        assert pytest.approx(10.0 * 0.2 + 5.0 * 0.9 + 0.05 * 10.0 + 0.5 * 4.0) == H  # 9.0 W/K


# ---------------------------------------------------------------------------
# Zyski wewnętrzne i harmonogramy
# ---------------------------------------------------------------------------


class TestInternalGains:
    def test_constant_schedule_full_power_analytic(self):
        """80 W/os * 0.03 os/m2 * 150 m2 = 360 W w każdej godzinie."""
        source = InternalGainSource(power_density=80.0)  # schedule constant = 1.0
        gains = internal_gains(0.03, 150.0, source, annual_hourly_index(), per_person=True)
        np.testing.assert_allclose(gains, 80.0 * 0.03 * 150.0)
        assert gains.sum() == pytest.approx(360.0 * 8760.0)

    def test_power_density_per_m2_for_lighting(self):
        """Dla oświetlenia/sprzętu gęstość mocy jest W/m2 (bez osób)."""
        source = InternalGainSource(power_density=10.0)
        gains = internal_gains(0.03, 150.0, source, annual_hourly_index())
        np.testing.assert_allclose(gains, 10.0 * 150.0)  # 1500 W

    def test_weekday_weekend_schedule(self):
        weekday = [0.0] * 8 + [1.0] * 10 + [0.0] * 6
        sunday = [0.0] * 24
        sched = Schedule(type="weekday_weekend", weekday=weekday, sunday=sunday)
        profile = evaluate_schedule(sched, annual_hourly_index(2023))
        # 2023-01-04 to środa, 2023-01-07 sobota, 2023-01-08 niedziela
        assert profile[3 * 24 + 9] == 1.0    # śro 09:00
        assert profile[3 * 24 + 3] == 0.0    # śro 03:00
        assert profile[6 * 24 + 9] == 0.0    # sob 09:00 (sunday)
        assert profile[7 * 24 + 9] == 0.0    # niedz 09:00

    def test_hourly_profile_with_separate_weekend_arrays(self):
        weekday = [0.5] * 24
        saturday = [0.7] * 24
        sunday = [0.3] * 24
        sched = Schedule(
            type="hourly_profile", weekday=weekday, saturday=saturday, sunday=sunday
        )
        profile = evaluate_schedule(sched, annual_hourly_index(2023))
        assert profile[3 * 24 + 12] == 0.5   # środa
        assert profile[6 * 24 + 12] == 0.7   # sobota
        assert profile[7 * 24 + 12] == 0.3   # niedziela

    def test_hourly_profile_saturday_falls_back_to_weekday(self):
        sched = Schedule(type="hourly_profile", weekday=[0.5] * 24)  # brak soboty
        profile = evaluate_schedule(sched, annual_hourly_index(2023))
        assert profile[6 * 24 + 12] == 0.5

    def test_missing_weekday_profile_raises(self):
        sched = Schedule(type="weekday_weekend", weekday=None)
        with pytest.raises(ValueError, match="weekday"):
            evaluate_schedule(sched, annual_hourly_index(2023))

    def test_total_internal_gains_sum_of_sources(self):
        gains = InternalGains(
            occupancy=InternalGainSource(power_density=80.0),
            lighting=InternalGainSource(power_density=10.0),
            equipment=InternalGainSource(power_density=5.0),
        )
        total = total_internal_gains(0.03, 150.0, gains, annual_hourly_index())
        expected = (80.0 * 0.03 + 10.0 + 5.0) * 150.0  # 2610 W
        np.testing.assert_allclose(total, expected)

    def test_schedule_validators(self):
        with pytest.raises(ValidationError):
            Schedule(type="constant", constant_value=1.5)  # poza [0, 1]
        with pytest.raises(ValidationError):
            Schedule(type="hourly_profile", weekday=[1.0] * 23)  # nie 24 wartości

    def test_constant_zero_schedule_means_zero_gains(self):
        source = InternalGainSource(
            power_density=80.0, schedule=Schedule(type="constant", constant_value=0.0)
        )
        gains = internal_gains(0.03, 150.0, source, annual_hourly_index())
        np.testing.assert_allclose(gains, 0.0)


# ---------------------------------------------------------------------------
# Godzinowy bilans ciepła
# ---------------------------------------------------------------------------


class TestThermalBalance:
    def test_thermal_capacity_analytic(self):
        assert thermal_capacity(150.0) == pytest.approx(150.0 * 60.0)

    def test_steady_state_heating_analytic(self):
        """Stan ustalony: Q_H/h = H*(T_set - T_e) = 80*30 = 2400 Wh."""
        n = 8760
        T_int, Q_H, Q_C, _ = solve_hourly_balance(
            H_tr=50.0, H_ve=30.0,
            Q_int=np.zeros(n), Q_sol=np.zeros(n), T_e=np.full(n, -10.0),
            T_set_heating=20.0, T_set_cooling=None, C_m=3000.0,
        )
        np.testing.assert_allclose(Q_H, 80.0 * 30.0)
        assert Q_C.sum() == 0.0
        np.testing.assert_allclose(T_int, 20.0)

    def test_steady_state_cooling_analytic(self):
        """Po rozruchu (~10 h od inicjalizacji w 20°C): Q_C/h = 1820 Wh."""
        n = 8760
        T_int, Q_H, Q_C, _ = solve_hourly_balance(
            H_tr=50.0, H_ve=30.0,
            Q_int=np.full(n, 1500.0), Q_sol=np.zeros(n), T_e=np.full(n, 30.0),
            T_set_heating=20.0, T_set_cooling=26.0, C_m=3000.0,
        )
        assert np.all(Q_C[:8] == 0.0)  # rozruch termiczny (pojemność cieplna)
        np.testing.assert_allclose(Q_C[24:], 1500.0 + 80.0 * (30.0 - 26.0))
        assert Q_H.sum() == 0.0
        np.testing.assert_allclose(T_int[24:], 26.0)

    def test_free_float_converges_to_analytic_equilibrium(self):
        """Swobodne wahania: T = T_e + (Q_int+Q_sol)/H = 10 + 400/80 = 15°C."""
        n = 8760
        T_int, Q_H, Q_C, _ = solve_hourly_balance(
            H_tr=50.0, H_ve=30.0,
            Q_int=np.full(n, 400.0), Q_sol=np.zeros(n), T_e=np.full(n, 10.0),
            T_set_heating=5.0, T_set_cooling=45.0, C_m=3000.0,
        )
        assert Q_H.sum() == 0.0
        assert Q_C.sum() == 0.0
        assert T_int[-1] == pytest.approx(15.0, abs=0.01)

    def test_energy_conservation_free_floating(self):
        """C_m*dT/dt = Q_int + Q_sol - H*(T_int - T_e) w każdej godzinie."""
        n = 8760
        hours = np.arange(n)
        T_e = 10.0 + 8.0 * np.sin(2 * np.pi * hours / 8760.0)
        Q = 300.0 + 200.0 * np.sin(2 * np.pi * (hours % 24) / 24.0)
        C_m, H = 3000.0, 80.0
        T_int, Q_H, Q_C, _ = solve_hourly_balance(
            H_tr=50.0, H_ve=30.0, Q_int=Q, Q_sol=np.zeros(n), T_e=T_e,
            T_set_heating=5.0, T_set_cooling=45.0, C_m=C_m,  # swobodne wahania
        )
        assert Q_H.sum() == 0.0 and Q_C.sum() == 0.0
        T_prev = np.concatenate(([5.0], T_int[:-1]))
        residual = C_m * (T_int - T_prev) - (Q - H * (T_int - T_e))
        assert np.max(np.abs(residual)) < 1e-6

    def test_hvac_hours_pin_temperature_to_setpoint(self):
        n = 8760
        rng = np.random.default_rng(42)
        T_e = rng.uniform(-15.0, 35.0, n)
        Q_int = rng.uniform(0.0, 2000.0, n)
        T_int, Q_H, Q_C, _ = solve_hourly_balance(
            H_tr=50.0, H_ve=30.0, Q_int=Q_int, Q_sol=np.zeros(n), T_e=T_e,
            T_set_heating=20.0, T_set_cooling=26.0, C_m=3000.0,
        )
        # Tam gdzie jest zapotrzebowanie, temperatura = setpoint
        assert np.all(T_int[Q_H > 0] == 20.0)
        assert np.all(T_int[Q_C > 0] == 26.0)
        # Nigdy ogrzewanie i chłodzenie jednocześnie
        assert np.all((Q_H <= 0.0) | (Q_C <= 0.0))
        # Poza godzinami HVAC temperatura w paśmie komfortu
        idle = (Q_H == 0.0) & (Q_C == 0.0)
        assert np.all(T_int[idle] >= 20.0 - 1e-9)
        assert np.all(T_int[idle] <= 26.0 + 1e-9)

    def test_cooling_disabled_returns_zero(self):
        n = 8760
        _, Q_H, Q_C, _ = solve_hourly_balance(
            H_tr=50.0, H_ve=30.0,
            Q_int=np.full(n, 5000.0), Q_sol=np.zeros(n), T_e=np.full(n, 35.0),
            T_set_heating=20.0, T_set_cooling=None, C_m=3000.0,
        )
        assert Q_H.sum() == 0.0
        assert Q_C.sum() == 0.0  # chłodzenie wyłączone mimo przegrzewania


# ---------------------------------------------------------------------------
# Systemy techniczne
# ---------------------------------------------------------------------------


class TestSystems:
    def test_constant_efficiency_final_energy_analytic(self):
        E_k = constant_efficiency_final_energy(
            np.array([1000.0, 0.0, -500.0]), efficiency=0.9, distribution_factor=0.95
        )
        np.testing.assert_allclose(E_k, [1000.0 / 0.9 / 0.95, 0.0, 0.0])

    def test_constant_efficiency_rejects_nonpositive(self):
        with pytest.raises(ValueError, match="positive"):
            constant_efficiency_final_energy(np.array([100.0]), efficiency=0.0)

    def test_cop_at_rated_point(self):
        cop = heat_pump_cop_map(
            np.array([7.0]), T_sink=35.0, source_type="air", rated_cop=3.5
        )
        assert cop[0] == pytest.approx(3.5, rel=1e-9)

    def test_cop_at_zero_degrees_analytic(self):
        """COP(0°C) = 3.5 * (273.15/35) / (280.15/28) = 2.7300."""
        cop = heat_pump_cop_map(np.array([0.0]), T_sink=35.0, rated_cop=3.5)
        expected = 3.5 * (273.15 / 35.0) / (280.15 / 28.0)
        assert cop[0] == pytest.approx(expected, rel=1e-12)
        assert cop[0] == pytest.approx(2.7300, abs=1e-4)

    def test_cop_monotonic_in_source_temperature_and_clipped(self):
        T_e = np.linspace(-40.0, 30.0, 71)
        cop = heat_pump_cop_map(T_e, T_sink=35.0, rated_cop=3.5)
        assert np.all(np.diff(cop) >= 0)          # nierosnąco... rosnąco ze źródłem
        mid = (T_e >= -20.0) & (T_e <= 10.0)      # poza plateau clipów
        assert np.all(np.diff(cop[mid]) > 0)
        assert np.all(cop >= 1.0) and np.all(cop <= 6.0)
        assert cop[0] == pytest.approx(1.0874, abs=1e-3)
        assert cop[-1] == 6.0                     # clip na górze

    def test_dhw_energy_demand_analytic(self):
        """4.5 osoby * 50 L/d * 365 d * 4180 J/(kg*K) * 45 K / 3600."""
        Q_wh = dhw_energy_demand(
            daily_demand_per_person=50.0, occupancy_density=0.03, floor_area=150.0,
            target_temperature=55.0, cold_water_temperature=10.0,
        )
        expected = 50.0 * 0.03 * 150.0 * 365 * 4180.0 * 45.0 / 3600.0
        assert Q_wh == pytest.approx(expected, rel=1e-12)
        assert Q_wh == pytest.approx(4_291_031.25, rel=1e-6)  # ~4291 kWh/rok

    def test_dhw_energy_demand_days_parameter(self):
        Q_100 = dhw_energy_demand(50.0, 0.03, 150.0, 55.0, 10.0, days=100)
        Q_365 = dhw_energy_demand(50.0, 0.03, 150.0, 55.0, 10.0, days=365)
        assert pytest.approx(Q_365 * 100.0 / 365.0, rel=1e-12) == Q_100

    def test_final_energy_dhw_analytic(self):
        E_k = final_energy_dhw(np.array([1000.0, 2000.0]), efficiency=0.9,
                               standby_loss_factor=1.05)
        np.testing.assert_allclose(E_k, [1000.0 / 0.9 * 1.05, 2000.0 / 0.9 * 1.05])

    def test_final_energy_dhw_rejects_nonpositive(self):
        with pytest.raises(ValueError, match="positive"):
            final_energy_dhw(1000.0, efficiency=0.0)


# ---------------------------------------------------------------------------
# Energia pierwotna i emisje
# ---------------------------------------------------------------------------


class TestPrimaryEnergy:
    def test_annual_primary_energy_analytic_mixed_carriers(self):
        carriers = {"electricity": 1000.0, "natural_gas": 2000.0}
        ep_wh, ec_kg = annual_primary_energy(carriers, PrimaryEnergyFactors())
        assert ep_wh == pytest.approx(1000.0 * 2.5 + 2000.0 * 1.1)  # 4900 Wh
        # we w kg CO2/MWh: 0.001 MWh * 0.6 + 0.002 MWh * 0.2 = 0.001 kg
        assert ec_kg == pytest.approx((1000.0 * 0.6 + 2000.0 * 0.2) / 1e6)

    def test_share_of_renewable_energy_analytic(self):
        assert share_of_renewable_energy(
            {"biomass": 30.0, "natural_gas": 70.0}
        ) == pytest.approx(30.0)
        assert share_of_renewable_energy({"biomass": 50.0, "renewable": 50.0}) == 100.0
        assert share_of_renewable_energy({}) == 0.0
        assert share_of_renewable_energy({"electricity": 100.0}) == 0.0


# ---------------------------------------------------------------------------
# Zyski słoneczne
# ---------------------------------------------------------------------------


def _climate_df(**kwargs) -> pd.DataFrame:  # noqa: F821
    base = {"latitude": 52.0, "longitude": 21.0, "elevation": 100.0}
    base.update(kwargs)
    return make_synthetic_year(**base)


class TestSolar:
    def test_horizontal_surface_equalsdni_cos_zenith_plus_diffuse(self):
        """Dla powierzchni poziomej: POA = DNI*cos(z) + DHI (geo. czysto analitycznie)."""
        df = _climate_df(GHI=500.0, DNI=300.0, DHI=200.0)
        poa = radiation_on_surface(df, surface_tilt=0.0, surface_azimuth=180.0)
        day = df["sun_zenith"].to_numpy() < 88.0  # tylko godziny dzienne
        expected = 300.0 * np.cos(np.deg2rad(df["sun_zenith"].to_numpy())) + 200.0
        np.testing.assert_allclose(poa.to_numpy()[day], expected[day], rtol=1e-6, atol=0.5)
        assert (poa.to_numpy() >= -1e-6).all()

    def test_south_facade_annual_gain_exceeds_north(self):
        # Promieniowanie tylko w godzinach dziennych (realny EPW ma DNI=0 w nocy)
        df = _climate_df()
        day = df["sun_zenith"].to_numpy() < 90.0
        df["GHI"] = np.where(day, 400.0, 0.0)
        df["DNI"] = np.where(day, 250.0, 0.0)
        df["DHI"] = np.where(day, 150.0, 0.0)

        def annual(tilt: float, azimuth: float) -> float:
            win = TransparentElement(
                id="w", name="w", zone_id="z1", orientation_azimuth=azimuth,
                inclination=tilt, area=1.0, u_value=1.0, g_value=1.0,
                frame_factor=0.0, shading_factor=1.0,
            )
            from app.engine.solar import solar_gains_transparent
            return solar_gains_transparent(win, df).sum()

        south, north = annual(90.0, 180.0), annual(90.0, 0.0)
        assert south > north
        assert south > 0.0

    def test_window_gain_formula_exact_with_frame_and_shading(self):
        df = _climate_df(GHI=400.0, DNI=250.0, DHI=150.0)
        win = TransparentElement(
            id="w", name="w", zone_id="z1", orientation_azimuth=180.0,
            inclination=90.0, area=10.0, u_value=1.0, g_value=0.6,
            frame_factor=0.2, shading_factor=0.7,
        )
        from app.engine.solar import solar_gains_transparent
        gains = solar_gains_transparent(win, df)
        i_surf = radiation_on_surface(df, 90.0, 180.0).to_numpy()
        np.testing.assert_allclose(gains, 10.0 * 0.8 * 0.6 * 0.7 * i_surf)

    def test_shading_factor_halves_gains_exactly(self):
        df = _climate_df(GHI=400.0, DNI=250.0, DHI=150.0)
        from app.engine.solar import solar_gains_transparent

        def total(shading: float) -> float:
            win = TransparentElement(
                id="w", name="w", zone_id="z1", area=5.0, u_value=1.0,
                g_value=0.6, frame_factor=0.2, shading_factor=shading,
            )
            return solar_gains_transparent(win, df).sum()

        assert total(0.5) == pytest.approx(total(1.0) * 0.5, rel=1e-12)

    def test_opaque_absorption_formula_and_ground_floor_excluded(self):
        from app.engine.solar import total_solar_gains
        df = _climate_df(GHI=400.0, DNI=250.0, DHI=150.0)
        roof = _opaque(
            element_type=ElementType.ROOF, inclination=0.0, area=90.0,
            solar_absorptance=0.6, solar_reduction_factor=0.08,
        )
        ground_floor = _opaque(
            element_type=ElementType.GROUND_FLOOR, inclination=180.0, area=90.0,
            adjacent_space_type=AdjacentSpaceType.GROUND,
            solar_absorptance=0.9, solar_reduction_factor=0.5,
        )
        _, opaque_abs = total_solar_gains([], [roof, ground_floor], df)
        i_roof = radiation_on_surface(df, 0.0, 0.0).to_numpy()
        np.testing.assert_allclose(
            opaque_abs, 90.0 * 0.6 * 0.08 * i_roof, rtol=1e-9
        )  # podłoga gruntowa wykluczona

    def test_zero_radiation_zero_gains(self):
        from app.engine.solar import total_solar_gains
        df = _climate_df(GHI=0.0, DNI=0.0, DHI=0.0)
        win = TransparentElement(
            id="w", name="w", zone_id="z1", area=10.0, u_value=1.0, g_value=0.6
        )
        trans, opaque = total_solar_gains([win], [], df)
        assert trans.sum() == 0.0
        assert opaque.sum() == 0.0


# ---------------------------------------------------------------------------
# Dane klimatyczne
# ---------------------------------------------------------------------------


class TestClimate:
    def test_haversine_one_degree_along_equator(self):
        # 1° łuku na równiku = R * pi/180 = 111.195 km
        d = haversine_distance_km(0.0, 0.0, 0.0, 1.0)
        assert d == pytest.approx(6371.0088 * np.pi / 180.0, rel=1e-6)

    def test_haversine_symmetry(self):
        assert haversine_distance_km(52.23, 21.01, 51.76, 19.46) == pytest.approx(
            haversine_distance_km(51.76, 19.46, 52.23, 21.01), rel=1e-12
        )

    def test_synthetic_year_length_and_broadcast(self):
        df = _climate_df(T_e=10.0)
        assert len(df) == 8760
        np.testing.assert_allclose(df["T_e"].to_numpy(), 10.0)
        zen = df["sun_zenith"].to_numpy()
        assert np.all(zen >= 0.0) and np.all(zen <= 180.0)
        assert np.all(np.isfinite(zen))

    def test_synthetic_year_rejects_wrong_length_array(self):
        with pytest.raises(ValueError, match="8760"):
            make_synthetic_year(T_e=np.full(100, 10.0))

    def test_annual_hourly_index_non_leap(self):
        idx = annual_hourly_index(2023)
        assert len(idx) == 8760
        assert str(idx[0]) == "2023-01-01 00:00:00"

    def test_load_epw_real_warsaw_file(self, project_root):
        from app.engine.climate import load_epw
        path = project_root / "data" / "tmy" / (
            "POL_MZ_Okecie-Warszawa-Chopina.Intl.AP.123750_TMYx.2009-2023.epw"
        )
        df = load_epw(path)
        assert len(df) == 8760
        T_e = df["T_e"].to_numpy()
        assert np.all(T_e > -35.0) and np.all(T_e < 45.0)
        assert not np.isnan(T_e).any()
        # Klimatycznie: styczeń zimniejszy od lipca (lipiec = dni 181-212)
        jan_mean = T_e[: 31 * 24].mean()
        jul_mean = T_e[181 * 24 : 212 * 24].mean()
        assert jan_mean < jul_mean
        assert (df["GHI"].to_numpy() >= 0).all()
