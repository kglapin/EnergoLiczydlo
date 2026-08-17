"""Kompleksowe testy jednostkowe logiki obliczeniowej silnika.

Każdy test porównuje wynik z niezależnie wyliczoną wartością analityczną
(zgodnie ze strategią w docs/VALIDATION.md, sekcja "Testy jednostkowe").
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.engine.climate import (
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
    annual_dhw_useful_energy,
    constant_efficiency_final_energy,
    final_energy_dhw,
    heat_pump_cop_map,
)
from app.engine.thermal_balance import (
    TransmissionNetwork,
    opaque_external_conductance,
    solve_zone_5r1c,
    thermal_capacity,
    zone_thermal_properties,
)
from app.engine.ventilation import (
    ventilation_effective_supply_temperature,
    ventilation_heat_loss,
    ventilation_heat_transfer_coefficient,
    ventilation_operation_profile,
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
    VentilationOperationMode,
)

CP_VOLUMETRIC = 1200.0  # methodology value rho_a*c_a [J/(m3*K)]


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

    def test_disabled_ventilation_keeps_only_background_infiltration(self):
        vent = Ventilation(
            ventilation_type="none", airflow_rate=120.0, infiltration_rate=0.5
        )
        expected = (0.5 * 375.0 / 3600.0) * CP_VOLUMETRIC
        assert ventilation_heat_transfer_coefficient(vent, _zone()) == pytest.approx(expected)

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

    def test_ventilation_heat_loss_rejects_two_schedule_mechanisms(self):
        vent = Ventilation(airflow_rate=120.0, infiltration_rate=0.5)
        with pytest.raises(ValueError, match="either schedule_profile or operation_profile"):
            ventilation_heat_loss(
                vent,
                _zone(),
                np.full(2, 20.0),
                np.zeros(2),
                schedule_profile=np.ones(2),
                operation_profile=np.ones(2),
            )

    def test_ventilation_heat_loss_uses_supply_temperature_when_provided(self):
        vent = Ventilation(airflow_rate=120.0, infiltration_rate=0.5)
        zone = _zone()
        T_int = np.full(24, 20.0)
        T_e = np.full(24, 0.0)
        T_supply = np.full(24, 15.0)
        loss = ventilation_heat_loss(vent, zone, T_int, T_e, T_supply=T_supply)
        H_ve = (120.0 / 3600.0 + 0.5 * 375.0 / 3600.0) * CP_VOLUMETRIC
        np.testing.assert_allclose(loss, H_ve * 5.0)

    def test_supply_temperature_applies_only_to_mechanical_component(self):
        vent = Ventilation(
            ventilation_type="mechanical_with_recovery",
            airflow_rate=100.0,
            heat_recovery_efficiency=0.5,
            infiltration_rate=0.5,
            supply_temperature=20.0,
        )
        zone = _zone(volume=375.0)
        T_e = np.zeros(24)
        effective = ventilation_effective_supply_temperature(vent, zone, T_e)
        # Explicit T_supply replaces the equivalent (1 - eta) reduction;
        # otherwise the heat recovery would be counted twice.
        expected = (100.0 * 20.0) / (100.0 + 0.5 * 375.0)
        np.testing.assert_allclose(effective, expected)

    def test_periodic_supply_extract_matches_arcadia_weighted_hve(self):
        """Arcadia table-22 streams reproduce its Hve for a periodic office.

        Vve,1 = 19_715 m3/h, Vx,su = 0.04*V, Vinf = 0.20*V,
        beta = 0.30 and eta_oc = 0.73 give Hve = 972.21 W/K with
        the methodology's rho_a*c_a = 1200 J/(m3*K).
        """
        zone = _zone(floor_area=2935.0, volume=8682.26)
        vent = Ventilation(
            ventilation_type="mechanical_with_recovery",
            operation_mode=VentilationOperationMode.PERIODIC,
            airflow_rate=19715.0,
            heat_recovery_efficiency=0.73,
            infiltration_rate=0.20,
            fan_infiltration_rate=0.04,
        )
        datetimes = annual_hourly_index(2023)
        profile = ventilation_operation_profile(vent, datetimes, beta=0.30)
        h_ve = ventilation_heat_transfer_coefficient(
            vent,
            zone,
            operation_profile=profile,
        )

        expected = 1200.0 / 3600.0 * (
            0.30 * (19715.0 * (1.0 - 0.73) + 0.04 * 8682.26)
            + 0.70 * (0.20 * 8682.26)
        )
        np.testing.assert_allclose(profile, 0.30)
        np.testing.assert_allclose(h_ve, expected, rtol=1e-12)

    def test_periodic_profile_uses_operating_and_off_hours_streams(self):
        zone = _zone(floor_area=100.0, volume=300.0)
        vent = Ventilation(
            ventilation_type="mechanical_with_recovery",
            operation_mode="periodic",
            airflow_rate=1000.0,
            heat_recovery_efficiency=0.75,
            infiltration_rate=0.20,
            fan_infiltration_rate=0.04,
        )
        profile = np.array([1.0, 0.0])
        h_ve = ventilation_heat_transfer_coefficient(
            vent,
            zone,
            operation_profile=profile,
        )
        expected_on = (1000.0 * 0.25 + 0.04 * 300.0) / 3600.0 * CP_VOLUMETRIC
        expected_off = (0.20 * 300.0) / 3600.0 * CP_VOLUMETRIC
        np.testing.assert_allclose(h_ve, [expected_on, expected_off])

    def test_periodic_beta_fallback_is_distinct_from_explicit_constant_schedule(self):
        datetimes = annual_hourly_index(2023)
        fallback = ventilation_operation_profile(
            Ventilation(operation_mode="periodic"), datetimes, beta=0.3
        )
        explicit = ventilation_operation_profile(
            Ventilation(
                operation_mode="periodic",
                schedule=Schedule(type="constant", constant_value=1.0),
            ),
            datetimes,
            beta=0.3,
        )
        np.testing.assert_allclose(fallback, 0.3)
        np.testing.assert_allclose(explicit, 1.0)

    def test_hourly_schedule_is_evaluated_for_short_series(self):
        vent = Ventilation(
            ventilation_type="mechanical_with_recovery",
            operation_mode="periodic",
            schedule=Schedule(
                type="hourly_profile",
                weekday=[1.0] + [0.0] * 23,
            ),
        )
        datetimes = pd.date_range("2023-01-02", periods=24, freq="h")
        profile = ventilation_operation_profile(vent, datetimes, beta=0.3)
        np.testing.assert_array_equal(profile, [1.0] + [0.0] * 23)


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
        """T_gruntu = mean(T_e) - 5*cos(2*pi*(h-lag)/8760); minimum ~2 mies. po
        minimum fali zewnętrznej (opóźnienie fazowe przeguby gruntowej)."""
        from app.engine.envelope import GROUND_TEMP_LAG_HOURS

        floor = _opaque(
            element_type=ElementType.GROUND_FLOOR, inclination=180.0,
            adjacent_space_type=AdjacentSpaceType.GROUND,
        )
        T_e = np.full(8760, 8.0)
        T_adj = adjacent_temperature(floor, T_e)
        lag = int(GROUND_TEMP_LAG_HOURS)
        assert T_adj[lag] == pytest.approx(8.0 - 5.0)              # minimum
        assert T_adj[lag + 2190] == pytest.approx(8.0, abs=1e-9)   # cos(pi/2)=0
        assert T_adj[lag + 4380] == pytest.approx(8.0 + 5.0)       # maksimum
        # Minimum w lutym/marcu (a nie w styczniu jak temperatura zewnętrzna)
        assert np.argmin(T_adj[: 3 * 8760 // 12]) >= 31 * 24

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
        with pytest.raises(ValidationError):
            Schedule(type="hourly_profile", weekday=[1.1] * 24)

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
        # C_m = kappa * A_m = 165 kJ/(m2*K) * 2.5 * Af, zwrócone w Wh/K
        assert thermal_capacity(150.0) == pytest.approx(165_000.0 * 2.5 * 150.0 / 3600.0)

    def _net(self, drive: float, n: int = 8760) -> TransmissionNetwork:
        net = TransmissionNetwork()
        net.add_opaque(50.0, np.full(n, drive))
        net.add_surface(30.0, np.full(n, drive))
        return net

    def test_steady_state_heating_analytic(self):
        """Stan ustalony bez zysków: zapotrzebowanie > 0, powietrze dokładnie
        na setpoincie (węzły sieci mają gradienty, więc nie ma jednej
        lumped wartości oczekiwanej)."""
        n = 8760
        solution = solve_zone_5r1c(
            network=self._net(-10.0),
            h_ve=30.0,
            t_e=np.full(n, -10.0),
            phi_int=np.zeros(n),
            phi_sol=np.zeros(n),
            properties=zone_thermal_properties(100.0),
            t_set_heating=20.0,
            t_set_cooling=None,
        )
        assert np.all(solution.q_heating[500:] > 0.0)
        assert solution.q_cooling.sum() == 0.0
        np.testing.assert_allclose(solution.t_air[500:], 20.0, atol=1e-9)

    def test_hourly_h_ve_array_matches_constant_coefficient(self):
        """The 5R1C solver accepts a separate ventilation coefficient per hour."""
        n = 48
        network = self._net(-10.0, n=n)
        kwargs = {
            "network": network,
            "t_e": np.full(n, -10.0),
            "phi_int": np.zeros(n),
            "phi_sol": np.zeros(n),
            "properties": zone_thermal_properties(100.0),
            "t_set_heating": 20.0,
            "t_set_cooling": None,
        }
        scalar = solve_zone_5r1c(h_ve=30.0, **kwargs)
        hourly = solve_zone_5r1c(h_ve=np.full(n, 30.0), **kwargs)
        np.testing.assert_allclose(hourly.t_air, scalar.t_air)
        np.testing.assert_allclose(hourly.q_heating, scalar.q_heating)

    def test_supply_temperature_is_connected_to_air_node(self):
        n = 48
        network = TransmissionNetwork()
        kwargs = {
            "network": network,
            "h_ve": 120.0,
            "t_e": np.zeros(n),
            "phi_int": np.zeros(n),
            "phi_sol": np.zeros(n),
            "properties": zone_thermal_properties(100.0),
            "t_set_heating": 20.0,
            "t_set_cooling": None,
        }
        cold_supply = solve_zone_5r1c(t_supply=np.zeros(n), **kwargs)
        warm_supply = solve_zone_5r1c(t_supply=np.full(n, 20.0), **kwargs)
        assert np.sum(warm_supply.q_heating) < np.sum(cold_supply.q_heating)

    def test_steady_state_cooling_analytic(self):
        """Po rozruchu: chłodzenie > 0, powietrze na setpoincie 26°C."""
        n = 8760
        solution = solve_zone_5r1c(
            network=self._net(30.0),
            h_ve=30.0,
            t_e=np.full(n, 30.0),
            phi_int=np.full(n, 1500.0),
            phi_sol=np.zeros(n),
            properties=zone_thermal_properties(100.0),
            t_set_heating=20.0,
            t_set_cooling=26.0,
        )
        assert np.all(solution.q_cooling[:8] == 0.0)  # rozruch termiczny
        assert np.all(solution.q_cooling[3000:] > 0.0)
        assert solution.q_heating.sum() == 0.0
        np.testing.assert_allclose(solution.t_air[3000:], 26.0, atol=1e-9)

    def test_free_float_converges_to_analytic_equilibrium(self):
        """Swobodne wahania bez HVAC: brak zapotrzebowania, temperatura
        powietrza wokół T_e + zyski/H_tot."""
        n = 8760
        solution = solve_zone_5r1c(
            network=self._net(10.0),
            h_ve=30.0,
            t_e=np.full(n, 10.0),
            phi_int=np.full(n, 400.0),
            phi_sol=np.zeros(n),
            properties=zone_thermal_properties(100.0),
            t_set_heating=5.0,
            t_set_cooling=45.0,
        )
        assert solution.q_heating.sum() == 0.0
        assert solution.q_cooling.sum() == 0.0
        assert 13.0 < solution.t_air[-1] < 16.0
        assert abs(solution.t_air[-1] - solution.t_mass[-1]) < 2.0

    def test_energy_conservation_free_floating(self):
        """Bilans węzła masy w każdej godzinie (Crank-Nicolson):
        C_m/3600*(Tm[t]-Tm[t-1]) = phi_m + Hms*(Ts-Tm_avg) + Hem*(T_drive-Tm_avg)."""
        n = 8760
        hours = np.arange(n)
        T_e = 10.0 + 8.0 * np.sin(2 * np.pi * hours / 8760.0)
        Q = 300.0 + 200.0 * np.sin(2 * np.pi * (hours % 24) / 24.0)
        solution = solve_zone_5r1c(
            network=self._net(0.0),
            h_ve=30.0,
            t_e=T_e,
            phi_int=Q,
            phi_sol=np.zeros(n),
            properties=zone_thermal_properties(100.0),
            t_set_heating=0.0,
            t_set_cooling=45.0,  # swobodne wahania (T_air ~5-12°C)
        )
        assert solution.q_heating.sum() == 0.0 and solution.q_cooling.sum() == 0.0

        props = zone_thermal_properties(100.0)
        h_ms, h_em = props.h_tr_ms, opaque_external_conductance(50.0, props.h_tr_ms)
        t_s = solution.t_surface
        t_m = solution.t_mass
        # Warunek początkowy solvera: masa startuje od setpointu ogrzewania.
        t_m_prev = np.concatenate(([0.0], t_m[:-1]))
        t_m_avg = solution.t_mass_mean
        phi_m = (2.5 / 4.5) * (0.5 * Q + np.zeros(n))  # frac_mass*(0.5*phi_int+phi_sol)
        d_u = props.capacity / 3600.0 * (t_m - t_m_prev)
        flows = phi_m + h_ms * (t_s - t_m_avg) + h_em * (0.0 - t_m_avg)
        np.testing.assert_allclose(d_u, flows, atol=1e-6)

    def test_hvac_hours_pin_temperature_to_setpoint(self):
        n = 8760
        rng = np.random.default_rng(42)
        T_e = rng.uniform(-15.0, 35.0, n)
        Q_int = rng.uniform(0.0, 2000.0, n)
        solution = solve_zone_5r1c(
            network=self._net(0.0),
            h_ve=30.0,
            t_e=T_e,
            phi_int=Q_int,
            phi_sol=np.zeros(n),
            properties=zone_thermal_properties(100.0),
            t_set_heating=20.0,
            t_set_cooling=26.0,
        )
        # Tam gdzie jest zapotrzebowanie, temperatura powietrza = setpoint
        np.testing.assert_allclose(solution.t_air[solution.q_heating > 0], 20.0, atol=1e-9)
        np.testing.assert_allclose(solution.t_air[solution.q_cooling > 0], 26.0, atol=1e-9)
        # Nigdy ogrzewanie i chłodzenie jednocześnie
        assert np.all((solution.q_heating <= 0.0) | (solution.q_cooling <= 0.0))
        # Poza godzinami HVAC temperatura w paśmie komfortu
        idle = (solution.q_heating == 0.0) & (solution.q_cooling == 0.0)
        assert np.all(solution.t_air[idle] >= 20.0 - 1e-6)
        assert np.all(solution.t_air[idle] <= 26.0 + 1e-6)

    def test_cooling_disabled_returns_zero(self):
        n = 8760
        solution = solve_zone_5r1c(
            network=self._net(35.0),
            h_ve=30.0,
            t_e=np.full(n, 35.0),
            phi_int=np.full(n, 5000.0),
            phi_sol=np.zeros(n),
            properties=zone_thermal_properties(100.0),
            t_set_heating=20.0,
            t_set_cooling=None,
        )
        assert solution.q_heating.sum() == 0.0
        assert solution.q_cooling.sum() == 0.0  # chłodzenie wyłączone mimo przegrzewania


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

    def test_annual_dhw_useful_energy_single_family_analytic(self):
        """Tabela 27: VWi=1.40 dm³/(m²·d), kR=0.90 dla domu jednorodzinnego."""
        Q_wh = annual_dhw_useful_energy(150.0, "residential_single_family")
        expected = 1.40 * 150.0 * 4.19 * 1.0 * 45.0 * 0.90 * 365 / 3600 * 1000
        assert Q_wh == pytest.approx(expected, rel=1e-12)
        assert Q_wh == pytest.approx(3_613_089.375, rel=1e-6)  # ~3613 kWh/rok

    def test_annual_dhw_useful_energy_uses_selected_profile(self):
        office = annual_dhw_useful_energy(150.0, "office")
        house = annual_dhw_useful_energy(150.0, "residential_single_family")
        assert office == pytest.approx(
            0.35 * 150.0 * 4.19 * 1.0 * 45.0 * 0.70 * 365 / 3600 * 1000,
            rel=1e-12,
        )
        assert office < house

    def test_annual_dhw_useful_energy_rejects_unknown_profile(self):
        with pytest.raises(ValueError, match="Unsupported DHW usage profile"):
            annual_dhw_useful_energy(150.0, "production")

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


class TestNormativeGaps:
    """Uzupełnienia metodologiczne: tabela 13, tabela 20, tabele 21-25, LENI."""

    def test_storage_unit_loss_table_13_lookup(self):
        from app.engine.systems import storage_unit_loss_w_dm3

        # 200 dm3, nieogrzewana, pośredni, izolacja 50 mm -> 0,49 W/dm3
        assert storage_unit_loss_w_dm3(200.0, "unheated", "indirect", 50.0) == pytest.approx(0.49)
        # 80 dm3 zaokrągla w górę do wiersza 100 dm3
        assert storage_unit_loss_w_dm3(80.0, "heated", "indirect", 100.0) == pytest.approx(0.35)
        # elektryczny w miejscu poboru: stały w kolumnie
        assert storage_unit_loss_w_dm3(80.0, "unheated", "electric") == pytest.approx(2.80)
        assert storage_unit_loss_w_dm3(80.0, "heated", "electric") == pytest.approx(2.28)
        # gazowy 25 dm3 nieogrzewany -> 3,13
        assert storage_unit_loss_w_dm3(20.0, "unheated", "gas") == pytest.approx(3.13)
        # powyżej 2000 dm3 brak danych
        assert storage_unit_loss_w_dm3(5000.0, "unheated") is None

    def test_dhw_storage_standby_loss_formula_30(self):
        from app.engine.systems import dhw_storage_standby_loss_kwh

        # ΔQ = V_S·q_S·8760·1e-3: 200 dm3, 0,49 W/dm3 -> 858,5 kWh/rok
        assert dhw_storage_standby_loss_kwh(200.0, "unheated", "indirect", 50.0) == (
            pytest.approx(200.0 * 0.49 * 8760.0 / 1000.0)
        )

    def test_normative_airflow_residential_natural_tabela_24(self):
        from app.engine.ventilation import normative_airflow_rate_m3h

        # 0,31e-3 m3/(s·m2) ciągła dla mieszkalnego: 150 m2 -> 167,4 m3/h
        assert normative_airflow_rate_m3h(
            "residential_single_family", 150.0, "natural"
        ) == pytest.approx(0.31e-3 * 150.0 * 3600.0)

    def test_normative_airflow_office_beta_tabela_22_and_25(self):
        from app.engine.ventilation import normative_airflow_rate_m3h

        # biurowy 0,56e-3, grawitacyjna: udział β + 0,2(1-β) przy β=0,3 -> 0,44
        expected = 0.56e-3 * (0.3 + 0.7 * 0.2) * 1000.0 * 3600.0
        assert normative_airflow_rate_m3h(
            "office", 1000.0, "natural", beta=0.3
        ) == pytest.approx(expected)

    def test_normative_airflow_supply_extract_uses_rn(self):
        from app.engine.ventilation import normative_airflow_rate_m3h

        # nawiewno-wywiewna: r_n = 0,75, udział β (poza użytkowaniem 0)
        expected = 0.56e-3 * 0.75 * 0.3 * 1000.0 * 3600.0
        assert normative_airflow_rate_m3h(
            "office", 1000.0, "mechanical_with_recovery", beta=0.3
        ) == pytest.approx(expected)

    def test_auxiliary_demand_tabela_20(self):
        from app.engine.systems import (
            dhw_auxiliary_demand_wh,
            heating_auxiliary_demand_wh,
            ventilation_fan_hours_per_year,
            ventilation_fan_power_w_m2,
        )

        # kocioł, Af=150: w.7a (0,50; 2520)
        assert heating_auxiliary_demand_wh("gas_boiler", 150.0) == pytest.approx(
            0.50 * 2520.0 * 150.0
        )
        # Af=500: w.7b (0,15; 3900)
        assert heating_auxiliary_demand_wh("gas_boiler", 500.0) == pytest.approx(
            0.15 * 3900.0 * 500.0
        )
        # PC glikol: w.9 (0,45; 1600)
        assert heating_auxiliary_demand_wh("heat_pump_ground", 150.0) == pytest.approx(
            0.45 * 1600.0 * 150.0
        )
        # electric_direct: brak
        assert heating_auxiliary_demand_wh("electric_direct", 150.0) == 0.0
        # CWU kocioł + pompa ładująca (w.6a + w.4a), bez cyrkulacji
        assert dhw_auxiliary_demand_wh("gas_boiler", 150.0, "single_dwelling") == (
            pytest.approx((1.40 * 310.0 + 0.25 * 270.0) * 150.0)
        )
        # CWU z cyrkulacją ciągłą (w.3a)
        assert dhw_auxiliary_demand_wh(
            "gas_boiler", 150.0, "central_circulation_insulated"
        ) == pytest.approx((1.40 * 310.0 + 0.25 * 270.0 + 0.15 * 8760.0) * 150.0)
        # wentylatory: nawiewno-wywiewna >0,6 ACH -> 1,30 W/m2; wywiewna -> 0,40
        assert ventilation_fan_power_w_m2("mechanical_with_recovery", 1.5) == pytest.approx(1.30)
        assert ventilation_fan_power_w_m2("mechanical_with_recovery", 0.5) == pytest.approx(0.50)
        assert ventilation_fan_power_w_m2("exhaust", 0.5) == pytest.approx(0.40)
        assert ventilation_fan_power_w_m2("natural", 1.0) == 0.0
        assert ventilation_fan_hours_per_year(0.3) == pytest.approx(2628.0)


class TestPrimaryEnergy:
    def test_annual_primary_energy_analytic_mixed_carriers(self):
        carriers = {"electricity": 1000.0, "natural_gas": 2000.0}
        ep_wh, ec_t = annual_primary_energy(carriers, PrimaryEnergyFactors())
        # fp elektryczności = 2.50 wg aktualnej tabeli 1 (Dz.U. 2023 poz. 697)
        assert ep_wh == pytest.approx(1000.0 * 2.5 + 2000.0 * 1.1)  # 4700 Wh
        # we w kg CO2/kWh -> t CO2: 1 kWh*0.6 + 2 kWh*0.2 = 1.0 kg = 0.001 t
        assert ec_t == pytest.approx((1000.0 * 0.6 + 2000.0 * 0.2) / 1e6)

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
        """Zysk od przegrody nieprzezroczystej = A*alpha*U*Rse*I (sol-air);
        podłoga na gruncie nie otrzymuje promieniowania."""
        from app.engine.envelope import R_SE_M2K_W
        from app.engine.solar import total_solar_gains
        df = _climate_df(GHI=400.0, DNI=250.0, DHI=150.0)
        roof = _opaque(
            element_type=ElementType.ROOF, inclination=0.0, area=90.0,
            u_value=0.2, solar_absorptance=0.6,
        )
        ground_floor = _opaque(
            element_type=ElementType.GROUND_FLOOR, inclination=180.0, area=90.0,
            adjacent_space_type=AdjacentSpaceType.GROUND,
            solar_absorptance=0.9,
        )
        _, opaque_abs = total_solar_gains([], [roof, ground_floor], df)
        i_roof = radiation_on_surface(df, 0.0, 0.0).to_numpy()
        np.testing.assert_allclose(
            opaque_abs, 90.0 * 0.6 * 0.2 * R_SE_M2K_W * i_roof, rtol=1e-9
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
