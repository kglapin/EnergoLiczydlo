"""Benchmark against a real Polish energy certificate for an office building in Łódź.

The certificate (ŚChE_Biuro - magisterka-wariant 4-Certyfikat.pdf) reports:
- Location: Łódź, climate station Poznań
- Conditioned floor area Af = 3162.85 m²
- Volume = 9482.46 m³
- EU = 49.1 kWh/(m²·rok)
- EK = 26.5 kWh/(m²·rok)
- EP = 56.6 kWh/(m²·rok)

Because the full input file (.thb) is a proprietary binary format and cannot be
parsed, this test uses approximate geometry reconstructed from the certificate
and checks that the model produces values of the same order of magnitude.
"""

import pytest

from app.engine.calculator import calculate_building_energy
from app.schemas.models import (
    BuildingProject,
    GeneralInfo,
    InternalGains,
    OpaqueElement,
    PrimaryEnergyFactors,
    ThermalBridgeConfig,
    ThermalZone,
    TransparentElement,
    Ventilation,
)


@pytest.fixture
def office_project() -> BuildingProject:
    floor_area = 3162.85
    volume = 9482.46
    wall_u = 0.20
    roof_u = 0.15
    ground_u = 0.30
    window_u = 0.90

    # Approximate envelope: assume square footprint per storey, 3 storeys
    # height ~ 9.5 m, average floor area per storey ~ 1054 m²
    # envelope area ~ 4 * sqrt(1054) * 9.5 * 3 (shared among 3 storeys) ~ 3700 m²
    # split: walls 2600 m², roof 1050 m², ground 1050 m²
    wall_area = 2600.0
    roof_area = 1054.28
    ground_area = 1054.28
    # Window-to-wall ratio ~ 30%
    window_area = wall_area * 0.30
    wall_area -= window_area

    return BuildingProject(
        project_name="Benchmark office Łódź",
        general=GeneralInfo(
            building_name="Biurowiec Łódź",
            building_type="office",
            construction_year=2025,
            conditioned_floor_area=floor_area,
            usable_floor_area=floor_area,
            heated_volume=volume,
            number_of_storeys=3,
        ),
        climate_station_id="POL_WP_Poznan-Lawica-Wieniawski.AP.123300_TMYx.2009-2023",
        thermal_zones=[
            ThermalZone(
                id="open_office",
                name="Open office",
                zone_type="heated_and_cooled",
                floor_area=floor_area,
                volume=volume,
                setpoint_heating=20.0,
                setpoint_cooling=26.0,
                occupancy_density=0.05,
            )
        ],
        opaque_building_elements=[
            OpaqueElement(
                id="walls",
                name="Ściany zewnętrzne",
                zone_id="open_office",
                element_type="external_wall",
                orientation_azimuth=180.0,
                inclination=90.0,
                area=wall_area,
                u_value=wall_u,
            ),
            OpaqueElement(
                id="roof",
                name="Dach",
                zone_id="open_office",
                element_type="roof",
                orientation_azimuth=0.0,
                inclination=0.0,
                area=roof_area,
                u_value=roof_u,
            ),
            OpaqueElement(
                id="ground_floor",
                name="Podłoga na gruncie",
                zone_id="open_office",
                element_type="ground_floor",
                orientation_azimuth=0.0,
                inclination=180.0,
                area=ground_area,
                u_value=ground_u,
                adjacent_space_type="ground",
            ),
        ],
        transparent_building_elements=[
            TransparentElement(
                id="windows_south",
                name="Okna",
                zone_id="open_office",
                element_type="window",
                orientation_azimuth=180.0,
                inclination=90.0,
                area=window_area,
                u_value=window_u,
                g_value=0.63,
                frame_factor=0.2,
                shading_factor=0.5,
            )
        ],
        thermal_bridges=ThermalBridgeConfig(),
        ventilation=Ventilation(
            ventilation_type="mechanical",
            airflow_rate=volume * 1.5,  # 1.5 ach in m3/h
            infiltration_rate=0.2,
            heat_recovery_efficiency=0.6,
            mechanical_fan_power=0.5 * floor_area,  # 0.5 W/m2
        ),
        internal_gains=InternalGains(
            occupancy=InternalGains.model_fields["occupancy"].default,
            lighting=InternalGains.model_fields["lighting"].default,
            equipment=InternalGains.model_fields["equipment"].default,
        ),
        systems={
            "heating": {
                "system_type": "heat_pump_air",
                "fuel_or_carrier": "electricity",
                "nominal_power": 200.0,
                "efficiency_or_cop_map": {"constant": True, "value": 4.1},
                "sink_temperature": 35.0,
                "distribution_loss_factor": 0.95,
            },
            "cooling": {
                "system_type": "vrv",
                "fuel_or_carrier": "electricity",
                "nominal_power": 150.0,
                "efficiency_or_cop_map": {"constant": True, "value": 4.1},
            },
            "dhw": {
                "system_type": "electric_storage",
                "daily_demand_per_person": 10.0,
                "target_temperature": 55.0,
                "cold_water_temperature": 10.0,
                "efficiency": 4.5,
            },
        },
        primary_energy=PrimaryEnergyFactors(),
    )


def test_office_benchmark_order_of_magnitude(office_project: BuildingProject) -> None:
    result = calculate_building_energy(office_project)
    assert result.status == "success"
    ann = result.annual_indicators
    # Sanity checks against the certificate values; tolerance is wide because
    # many details (exact window areas, orientations, schedules) are unknown.
    assert 15.0 < ann.eu_kwh_m2_year < 150.0
    assert 5.0 < ann.ek_kwh_m2_year < 100.0
    assert 15.0 < ann.ep_kwh_m2_year < 220.0
