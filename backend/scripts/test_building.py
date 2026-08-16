"""Quick manual test of the calculation engine."""

from app.engine.calculator import calculate_building_energy
from app.schemas.models import (
    BuildingProject,
    GeneralInfo,
    OpaqueElement,
    ThermalZone,
    TransparentElement,
    Ventilation,
)


def make_test_project() -> BuildingProject:
    return BuildingProject(
        project_name="Test house Warsaw",
        general=GeneralInfo(
            building_name="Dom jednorodzinny",
            building_type="residential",
            dhw_usage_profile="residential_single_family",
            construction_year=2020,
            conditioned_floor_area=150.0,
            usable_floor_area=150.0,
            heated_volume=375.0,
            number_of_storeys=1,
        ),
        climate_station_id="POL_MZ_Okecie-Warszawa-Chopina.Intl.AP.123750_TMYx.2009-2023",
        thermal_zones=[
            ThermalZone(
                id="zone_1",
                name="Cały budynek",
                zone_type="heated",
                floor_area=150.0,
                volume=375.0,
                setpoint_heating=20.0,
                setpoint_cooling=26.0,
                occupancy_density=0.03,
            )
        ],
        opaque_building_elements=[
            OpaqueElement(
                id="wall_n",
                name="Ściana północna",
                zone_id="zone_1",
                element_type="external_wall",
                orientation_azimuth=0.0,
                inclination=90.0,
                area=40.0,
                u_value=0.25,
            ),
            OpaqueElement(
                id="wall_s",
                name="Ściana południowa",
                zone_id="zone_1",
                element_type="external_wall",
                orientation_azimuth=180.0,
                inclination=90.0,
                area=40.0,
                u_value=0.25,
            ),
            OpaqueElement(
                id="roof",
                name="Dach",
                zone_id="zone_1",
                element_type="roof",
                orientation_azimuth=0.0,
                inclination=0.0,
                area=90.0,
                u_value=0.18,
            ),
            OpaqueElement(
                id="floor",
                name="Podłoga na gruncie",
                zone_id="zone_1",
                element_type="ground_floor",
                orientation_azimuth=0.0,
                inclination=180.0,
                area=90.0,
                u_value=0.25,
                adjacent_space_type="ground",
            ),
        ],
        transparent_building_elements=[
            TransparentElement(
                id="win_s",
                name="Okno południowe",
                zone_id="zone_1",
                element_type="window",
                orientation_azimuth=180.0,
                inclination=90.0,
                area=10.0,
                u_value=1.0,
                g_value=0.6,
                frame_factor=0.2,
                shading_factor=1.0,
            ),
        ],
        ventilation=Ventilation(
            ventilation_type="natural",
            airflow_rate=120.0,
            infiltration_rate=0.5,
        ),
        systems={
            "heating": {
                "system_type": "heat_pump_air",
                "fuel_or_carrier": "electricity",
                "efficiency_or_cop_map": {"constant": True, "value": 3.5},
                "sink_temperature": 35.0,
            },
            "dhw": {
                "system_type": "electric_storage",
                "efficiency": 0.9,
            },
        },
    )


if __name__ == "__main__":
    project = make_test_project()
    result = calculate_building_energy(project)
    print("Annual indicators:")
    print(result.annual_indicators.model_dump())
    print("\nCompliance:")
    for check in result.compliance:
        print(check.model_dump())
    print("\nFirst 3 months:")
    for m in result.monthly[:3]:
        print(m.model_dump())
