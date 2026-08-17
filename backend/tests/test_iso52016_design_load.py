"""Procedure checks for PN-EN ISO 52016-1 hourly design sensible loads."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.engine.iso52016_design_load import calculate_iso52016_design_load
from app.schemas.models import (
    BuildingProject,
    BuildingSystems,
    GeneralInfo,
    InternalGainSource,
    InternalGains,
    OpaqueElement,
    SystemDHW,
    SystemHeatingCooling,
    ThermalBridgeConfig,
    ThermalZone,
    Ventilation,
)


def _climate(temperature: float) -> pd.DataFrame:
    index = pd.date_range("2023-01-01", periods=24, freq="h")
    return pd.DataFrame(
        {
            "T_e": np.full(24, temperature),
            "GHI": np.zeros(24),
            "DNI": np.zeros(24),
            "DHI": np.zeros(24),
            "sun_zenith": np.full(24, 90.0),
            "sun_azimuth": np.zeros(24),
        },
        index=index,
    )


def _project() -> BuildingProject:
    zone = ThermalZone(
        id="z1", name="Zone", floor_area=50.0, volume=125.0,
        setpoint_heating=20.0, setpoint_cooling=26.0,
        occupancy_density=0.0,
        air_furniture_heat_capacity_kj_m2k=10.0,
    )
    wall = OpaqueElement(
        id="wall", name="Wall", zone_id="z1", area=25.0, u_value=1.0,
        solar_absorptance=0.0,
        thermal_node_capacities_kj_m2k=[0.0, 20.0, 40.0, 20.0, 0.0],
        thermal_node_resistances_m2k_w=[0.2075, 0.2075, 0.2075, 0.2075],
        h_ci_w_m2k=2.5, h_ri_w_m2k=5.1923076923,
        h_ce_w_m2k=20.0, h_re_w_m2k=5.0,
        sky_view_factor=0.0,
    )
    return BuildingProject(
        project_name="ISO design test",
        general=GeneralInfo(
            building_name="Test", building_type="residential",
            dhw_usage_profile="residential_single_family",
            construction_year=2020, conditioned_floor_area=50.0,
            usable_floor_area=50.0, heated_volume=125.0, number_of_storeys=1,
        ),
        climate_station_id="design",
        thermal_zones=[zone],
        opaque_building_elements=[wall],
        transparent_building_elements=[],
        thermal_bridges=ThermalBridgeConfig(),
        ventilation=Ventilation(
            ventilation_type="none", airflow_rate=0.0,
            infiltration_rate=0.0, fan_infiltration_rate=0.0,
        ),
        internal_gains=InternalGains(
            occupancy=InternalGainSource(power_density=0.0),
            lighting=InternalGainSource(power_density=0.0),
            equipment=InternalGainSource(power_density=0.0),
            normative_power_density_w_m2=None,
        ),
        systems=BuildingSystems(
            heating=SystemHeatingCooling(system_type="none", fuel_or_carrier="electricity"),
            cooling=SystemHeatingCooling(system_type="none", fuel_or_carrier="electricity"),
            dhw=SystemDHW(system_type="none"),
        ),
    )


def test_strict_design_load_requires_weather_provenance() -> None:
    with pytest.raises(ValueError, match="provenance"):
        calculate_iso52016_design_load(
            _project(), _climate(-20.0),
            outdoor_design_temperature_c=-20.0,
            strict_conformance=True,
            climate_source=None,
        )


def test_heating_design_weather_mean_must_match_design_temperature() -> None:
    with pytest.raises(ValueError, match="mean"):
        calculate_iso52016_design_load(
            _project(), _climate(-18.0),
            outdoor_design_temperature_c=-20.0,
            strict_conformance=True,
            climate_source="ISO 15927 test sequence",
        )


def test_design_load_initializes_for_at_least_fourteen_days() -> None:
    result = calculate_iso52016_design_load(
        _project(), _climate(-20.0),
        outdoor_design_temperature_c=-20.0,
        strict_conformance=True,
        climate_source="ISO 15927 test sequence",
        sky_temperature_difference_k=0.0,
    )
    assert result.initialization_days >= 14
    assert result.heating_design_w > 0.0
    assert result.heating_profile_w.shape == (24,)
    assert result.heating_design_w == pytest.approx(np.max(result.heating_profile_w))
