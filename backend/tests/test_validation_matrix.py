"""Professional validation matrix for the hourly 5R1C calculation path.

The matrix intentionally varies independent physical inputs instead of only
repeating one happy-path fixture.  It is run against a deterministic
synthetic 8760-hour climate so failures identify the calculation engine, not a
changing weather download.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pytest

from app.engine.calculator import calculate_building_energy
from app.engine.climate import make_synthetic_year
from app.engine.ventilation import ventilation_heat_transfer_coefficient
from app.schemas.models import (
    BuildingProject,
    BuildingSystems,
    GeneralInfo,
    InternalGains,
    InternalGainSource,
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
    VentilationOperationMode,
    VentilationType,
    ZoneType,
)


@dataclass(frozen=True)
class MatrixVariant:
    """One complete annual calculation scenario."""

    ventilation: str
    glazing: str
    bridges: bool
    service: str

    @property
    def name(self) -> str:
        return f"{self.service}-{self.ventilation}-{self.glazing}-bridges={self.bridges}"


MATRIX_VARIANTS = tuple(
    MatrixVariant(*values)
    for values in product(
        (
            "natural",
            "exhaust",
            "mechanical",
            "mechanical_with_recovery",
            "mechanical_periodic",
            "none",
        ),
        ("none", "south", "north"),
        (False, True),
        ("heating", "cooling"),
    )
)


assert len(MATRIX_VARIANTS) == 72


def _matrix_climate() -> object:
    hours = np.arange(8760, dtype=float)
    outdoor = 8.0 + 18.0 * np.sin(2.0 * np.pi * hours / 8760.0)
    return make_synthetic_year(T_e=outdoor, GHI=300.0, DNI=0.0, DHI=300.0)


def _zero_gains() -> InternalGains:
    return InternalGains(
        occupancy=InternalGainSource(power_density=0.0),
        lighting=InternalGainSource(power_density=0.0),
        equipment=InternalGainSource(power_density=0.0),
        normative_power_density_w_m2=None,
    )


def _make_matrix_project(variant: MatrixVariant) -> BuildingProject:
    area = 120.0
    volume = 360.0
    zone_type = (
        ZoneType.HEATED if variant.service == "heating" else ZoneType.COOLED
    )
    zone = ThermalZone(
        id="zone",
        name="Validation zone",
        zone_type=zone_type,
        floor_area=area,
        volume=volume,
        setpoint_heating=20.0,
        setpoint_cooling=25.0,
        occupancy_density=0.03,
    )

    wall_area = 60.0
    opaque = [
        OpaqueElement(
            id="north-wall",
            name="North wall",
            zone_id="zone",
            orientation_azimuth=0.0,
            inclination=90.0,
            area=wall_area,
            u_value=0.24,
        ),
        OpaqueElement(
            id="south-wall",
            name="South wall",
            zone_id="zone",
            orientation_azimuth=180.0,
            inclination=90.0,
            area=wall_area,
            u_value=0.24,
        ),
        OpaqueElement(
            id="east-wall",
            name="East wall",
            zone_id="zone",
            orientation_azimuth=90.0,
            inclination=90.0,
            area=wall_area,
            u_value=0.24,
        ),
        OpaqueElement(
            id="west-wall",
            name="West wall",
            zone_id="zone",
            orientation_azimuth=270.0,
            inclination=90.0,
            area=wall_area,
            u_value=0.24,
        ),
        OpaqueElement(
            id="roof",
            name="Roof",
            zone_id="zone",
            element_type="roof",
            inclination=0.0,
            area=area,
            u_value=0.18,
        ),
        OpaqueElement(
            id="floor",
            name="Ground floor",
            zone_id="zone",
            element_type="ground_floor",
            inclination=180.0,
            area=area,
            u_value=0.25,
            adjacent_space_type="ground",
        ),
    ]

    transparent: list[TransparentElement] = []
    if variant.glazing != "none":
        azimuth = {"south": 180.0, "north": 0.0}[variant.glazing]
        transparent.append(
            TransparentElement(
                id="window",
                name=f"{variant.glazing} window",
                zone_id="zone",
                orientation_azimuth=azimuth,
                inclination=90.0,
                area=24.0,
                u_value=1.0,
                g_value=0.55,
                frame_factor=0.2,
                shading_factor=0.8,
            )
        )

    bridge_config = ThermalBridgeConfig()
    if variant.bridges:
        bridge_config = ThermalBridgeConfig(
            linear_bridges=[
                LinearThermalBridge(
                    id="junctions",
                    name="Envelope junctions",
                    zone_id="zone",
                    psi_value=0.05,
                    length=120.0,
                )
            ],
            point_bridges=[
                PointThermalBridge(
                    id="anchors",
                    name="Point bridges",
                    zone_id="zone",
                    chi_value=0.01,
                    count=24,
                )
            ],
        )

    ventilation_type = variant.ventilation
    periodic = ventilation_type == "mechanical_periodic"
    if periodic:
        ventilation_type = "mechanical_with_recovery"
    schedule = None
    if periodic:
        weekday = [1.0 if 7 <= hour < 19 else 0.0 for hour in range(24)]
        schedule = Schedule(
            type="hourly_profile",
            weekday=weekday,
            saturday=[0.0] * 24,
            sunday=[0.0] * 24,
        )
    airflow = 0.0 if ventilation_type == "none" else 360.0
    ventilation = Ventilation(
        ventilation_type=VentilationType(ventilation_type),
        operation_mode=(
            VentilationOperationMode.PERIODIC
            if periodic
            else VentilationOperationMode.CONTINUOUS
        ),
        airflow_rate=airflow,
        heat_recovery_efficiency=0.73 if "recovery" in ventilation_type else 0.0,
        infiltration_rate=0.2,
        fan_infiltration_rate=0.05 if periodic else 0.0,
        usage_share_beta=0.3,
        mechanical_fan_power=0.0,
        schedule=schedule,
    )

    heating = SystemHeatingCooling(
        system_type=("gas_boiler" if variant.service == "heating" else "none"),
        generation_efficiency=0.87 if variant.service == "heating" else 1.0,
        distribution_efficiency=0.95,
        auxiliary_energy_kwh_year=0.0,
    )
    cooling = None
    if variant.service == "cooling":
        cooling = SystemHeatingCooling(
            system_type="split_ac",
            fuel_or_carrier="electricity",
            generation_efficiency=4.0,
            distribution_efficiency=0.9,
            storage_efficiency=0.95,
            control_efficiency=0.95,
            auxiliary_energy_kwh_year=0.0,
        )

    return BuildingProject(
        project_name=variant.name,
        general=GeneralInfo(
            building_name="Validation matrix project",
            building_type="office",
            dhw_usage_profile="office",
            construction_year=2020,
            conditioned_floor_area=area,
            usable_floor_area=area,
            heated_volume=volume,
            number_of_storeys=1,
        ),
        climate_station_id="synthetic-validation-climate",
        thermal_zones=[zone],
        opaque_building_elements=opaque,
        transparent_building_elements=transparent,
        thermal_bridges=bridge_config,
        ventilation=ventilation,
        internal_gains=_zero_gains(),
        systems=BuildingSystems(
            heating=heating,
            cooling=cooling,
            dhw=SystemDHW(system_type="none"),
        ),
    )


@pytest.mark.parametrize(
    "variant",
    MATRIX_VARIANTS,
    ids=lambda variant: variant.name,
)
def test_72_annual_variants_conserve_the_hourly_energy_balance(
    monkeypatch: pytest.MonkeyPatch,
    variant: MatrixVariant,
) -> None:
    climate = _matrix_climate()
    monkeypatch.setattr(
        "app.engine.calculator._load_climate",
        lambda project: climate.copy(deep=True),
    )
    project = _make_matrix_project(variant)
    result = calculate_building_energy(project)
    hourly = result.hourly
    assert hourly is not None

    q_h = np.asarray(hourly["Q_H"], dtype=float)
    q_c = np.asarray(hourly["Q_C"], dtype=float)
    for key in ("T_int", "T_op", "T_supply", "Q_transmission", "Q_ventilation"):
        values = np.asarray(hourly[key], dtype=float)
        assert values.shape == (8760,)
        assert np.isfinite(values).all(), f"non-finite {key} in {variant.name}"

    assert q_h.shape == (8760,)
    assert q_c.shape == (8760,)
    assert np.isfinite(q_h).all() and np.isfinite(q_c).all()
    assert np.all(q_h >= -1e-9)
    assert np.all(q_c >= -1e-9)
    assert np.all((q_h <= 1e-9) | (q_c <= 1e-9))
    assert len(result.monthly) == 12
    assert sum(month.heating_kwh for month in result.monthly) * 1000.0 == pytest.approx(
        q_h.sum(), rel=1e-10, abs=1e-7
    )
    assert sum(month.cooling_kwh for month in result.monthly) * 1000.0 == pytest.approx(
        q_c.sum(), rel=1e-10, abs=1e-7
    )

    expected_eu = (q_h.sum() + q_c.sum()) / 1000.0 / project.general.conditioned_floor_area
    assert result.annual_indicators.eu_kwh_m2_year == pytest.approx(expected_eu, rel=1e-10)
    assert result.design_heating_power_kw >= 0.0


def test_recovery_reduces_heating_demand_without_changing_the_external_climate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    climate = make_synthetic_year(T_e=0.0, GHI=0.0, DNI=0.0, DHI=0.0)
    monkeypatch.setattr(
        "app.engine.calculator._load_climate",
        lambda project: climate.copy(deep=True),
    )
    base = _make_matrix_project(
        MatrixVariant("mechanical", "none", False, "heating")
    )
    recovered = base.model_copy(deep=True)
    recovered.ventilation = recovered.ventilation.model_copy(
        update={
            "ventilation_type": "mechanical_with_recovery",
            "heat_recovery_efficiency": 0.73,
        }
    )
    q_base = np.sum(calculate_building_energy(base).hourly["Q_H"])
    q_recovered = np.sum(calculate_building_energy(recovered).hourly["Q_H"])
    assert q_recovered < q_base


def test_thermal_bridges_increase_heating_demand(monkeypatch: pytest.MonkeyPatch) -> None:
    climate = make_synthetic_year(T_e=0.0, GHI=0.0, DNI=0.0, DHI=0.0)
    monkeypatch.setattr(
        "app.engine.calculator._load_climate",
        lambda project: climate.copy(deep=True),
    )
    without = _make_matrix_project(MatrixVariant("none", "none", False, "heating"))
    with_bridges = _make_matrix_project(MatrixVariant("none", "none", True, "heating"))
    q_without = np.sum(calculate_building_energy(without).hourly["Q_H"])
    q_with = np.sum(calculate_building_energy(with_bridges).hourly["Q_H"])
    assert q_with > q_without


def test_periodic_ventilation_schedule_changes_hourly_demand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    climate = make_synthetic_year(T_e=0.0, GHI=0.0, DNI=0.0, DHI=0.0)
    monkeypatch.setattr(
        "app.engine.calculator._load_climate",
        lambda project: climate.copy(deep=True),
    )
    operating = _make_matrix_project(
        MatrixVariant("mechanical_periodic", "none", False, "heating")
    )
    off = operating.model_copy(deep=True)
    off.ventilation.schedule = Schedule(
        type="hourly_profile",
        weekday=[0.0] * 24,
        saturday=[0.0] * 24,
        sunday=[0.0] * 24,
    )
    q_on = np.sum(calculate_building_energy(operating).hourly["Q_H"])
    q_off = np.sum(calculate_building_energy(off).hourly["Q_H"])
    assert q_on > q_off


def test_total_ventilation_coefficient_is_conserved_when_airflow_is_split_between_zones() -> None:
    ventilation = Ventilation(
        ventilation_type="mechanical",
        airflow_rate=600.0,
        infiltration_rate=0.2,
    )
    zone_a = ThermalZone(id="a", name="A", floor_area=60.0, volume=180.0)
    zone_b = ThermalZone(id="b", name="B", floor_area=60.0, volume=180.0)
    total_area = 120.0
    h_a = ventilation_heat_transfer_coefficient(ventilation, zone_a, total_area)
    h_b = ventilation_heat_transfer_coefficient(ventilation, zone_b, total_area)
    whole_zone = ThermalZone(id="whole", name="Whole building", floor_area=120.0, volume=360.0)
    whole = ventilation_heat_transfer_coefficient(ventilation, whole_zone)
    assert h_a + h_b == pytest.approx(whole)


def test_system_efficiency_product_is_the_only_heating_conversion_factor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    climate = make_synthetic_year(T_e=0.0, GHI=0.0, DNI=0.0, DHI=0.0)
    monkeypatch.setattr(
        "app.engine.calculator._load_climate",
        lambda project: climate.copy(deep=True),
    )
    project = _make_matrix_project(MatrixVariant("none", "none", False, "heating"))
    project.systems.heating = SystemHeatingCooling(
        system_type="electric_direct",
        fuel_or_carrier="electricity",
        generation_efficiency=0.98,
        distribution_efficiency=0.92,
        storage_efficiency=0.96,
        control_efficiency=0.94,
        auxiliary_energy_kwh_year=0.0,
    )
    before = project.model_dump(mode="json")
    result = calculate_building_energy(project)
    after = project.model_dump(mode="json")
    q_h = np.sum(np.asarray(result.hourly["Q_H"], dtype=float))
    total_efficiency = 0.98 * 0.92 * 0.96 * 0.94
    expected_ek = q_h / total_efficiency / 1000.0 / 120.0
    assert result.annual_indicators.ek_kwh_m2_year == pytest.approx(expected_ek, rel=1e-10)
    assert before == after
