from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class BuildingType(str, Enum):
    RESIDENTIAL = "residential"
    OFFICE = "office"
    SCHOOL = "school"
    RETAIL = "retail"
    HEALTHCARE = "healthcare"
    OTHER = "other"


class ZoneType(str, Enum):
    HEATED = "heated"
    COOLED = "cooled"
    HEATED_AND_COOLED = "heated_and_cooled"
    UNHEATED = "unheated"
    SEMI_HEATED = "semi_heated"


class AdjacentSpaceType(str, Enum):
    OUTDOOR = "outdoor"
    GROUND = "ground"
    UNHEATED_ZONE = "unheated_zone"
    HEATED_ZONE = "heated_zone"
    CONSTANT_TEMPERATURE = "constant_temperature"


class ElementType(str, Enum):
    EXTERNAL_WALL = "external_wall"
    ROOF = "roof"
    GROUND_FLOOR = "ground_floor"
    FLOOR_OVER_UNHEATED = "floor_over_unheated"
    INTERNAL_WALL = "internal_wall"
    BASEMENT_WALL = "basement_wall"
    PARTY_WALL = "party_wall"


class TransparentType(str, Enum):
    WINDOW = "window"
    GLASS_DOOR = "glass_door"
    SKYLIGHT = "skylight"


class VentilationType(str, Enum):
    NATURAL = "natural"
    MECHANICAL = "mechanical"
    HYBRID = "hybrid"
    NONE = "none"


class ScheduleType(str, Enum):
    CONSTANT = "constant"
    WEEKDAY_WEEKEND = "weekday_weekend"
    HOURLY_PROFILE = "hourly_profile"


class Schedule(BaseModel):
    type: ScheduleType = ScheduleType.CONSTANT
    constant_value: Optional[float] = Field(1.0, ge=0.0, le=1.0)
    weekday: Optional[List[float]] = None
    saturday: Optional[List[float]] = None
    sunday: Optional[List[float]] = None
    holiday: Optional[List[float]] = None

    @field_validator("weekday", "saturday", "sunday", "holiday")
    @classmethod
    def _check_hourly_length(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) != 24:
            raise ValueError("Hourly profile must contain exactly 24 values")
        return v


class GeneralInfo(BaseModel):
    building_name: str = ""
    building_type: BuildingType = BuildingType.RESIDENTIAL
    construction_year: int = Field(2020, ge=1900, le=2100)
    conditioned_floor_area: float = Field(..., gt=0.0)
    usable_floor_area: float = Field(..., gt=0.0)
    heated_volume: float = Field(..., gt=0.0)
    number_of_storeys: int = Field(1, ge=1)
    location_address: Optional[str] = None


class ThermalZone(BaseModel):
    id: str
    name: str
    zone_type: ZoneType = ZoneType.HEATED
    floor_area: float = Field(..., gt=0.0)
    volume: float = Field(..., gt=0.0)
    setpoint_heating: float = Field(20.0)
    setpoint_cooling: Optional[float] = Field(None)
    occupancy_density: float = Field(0.03, ge=0.0)


class OpaqueElement(BaseModel):
    id: str
    name: str
    zone_id: str
    element_type: ElementType = ElementType.EXTERNAL_WALL
    orientation_azimuth: float = Field(0.0, ge=0.0, lt=360.0)
    inclination: float = Field(90.0, ge=0.0, le=180.0)
    area: float = Field(..., gt=0.0)
    u_value: float = Field(..., gt=0.0)
    solar_absorptance: float = Field(0.6, ge=0.0, le=1.0)
    emissivity: float = Field(0.9, ge=0.0, le=1.0)
    adjacent_space_type: AdjacentSpaceType = AdjacentSpaceType.OUTDOOR
    adjacent_temperature: Optional[float] = None


class TransparentElement(BaseModel):
    id: str
    name: str
    zone_id: str
    element_type: TransparentType = TransparentType.WINDOW
    orientation_azimuth: float = Field(0.0, ge=0.0, lt=360.0)
    inclination: float = Field(90.0, ge=0.0, le=180.0)
    area: float = Field(..., gt=0.0)
    u_value: float = Field(..., gt=0.0)
    g_value: float = Field(..., ge=0.0, le=1.0)
    frame_factor: float = Field(0.2, ge=0.0, le=1.0)
    shading_factor: float = Field(1.0, ge=0.0, le=1.0)


class LinearThermalBridge(BaseModel):
    id: str
    name: str
    psi_value: float = Field(..., ge=0.0)
    length: float = Field(..., ge=0.0)
    zone_id: str
    element_id: Optional[str] = None


class PointThermalBridge(BaseModel):
    id: str
    name: str
    chi_value: float = Field(..., ge=0.0)
    count: int = Field(1, ge=0)
    zone_id: str


class ThermalBridgeConfig(BaseModel):
    auto_calculate: bool = False
    linear_bridges: List[LinearThermalBridge] = []
    point_bridges: List[PointThermalBridge] = []


class Ventilation(BaseModel):
    ventilation_type: VentilationType = VentilationType.NATURAL
    airflow_rate: float = Field(0.0, ge=0.0)
    heat_recovery_efficiency: float = Field(0.0, ge=0.0, le=1.0)
    infiltration_rate: float = Field(0.5, ge=0.0)
    supply_temperature: Optional[float] = None
    mechanical_fan_power: Optional[float] = Field(0.0, ge=0.0)
    schedule: Schedule = Schedule()


class InternalGainSource(BaseModel):
    power_density: float = Field(..., ge=0.0)
    schedule: Schedule = Schedule()


class InternalGains(BaseModel):
    occupancy: InternalGainSource = InternalGainSource(power_density=80.0)
    lighting: InternalGainSource = InternalGainSource(power_density=10.0)
    equipment: InternalGainSource = InternalGainSource(power_density=5.0)


class SystemHeatingCooling(BaseModel):
    system_type: str = "heat_pump_air"
    fuel_or_carrier: str = "electricity"
    nominal_power: float = Field(10.0, gt=0.0)
    efficiency_or_cop_map: dict = {"constant": True, "value": 3.0}
    distribution_loss_factor: float = Field(0.95, ge=0.0, le=1.0)
    control_factor: float = Field(1.0, ge=0.0)
    auxiliary_energy: float = Field(0.0, ge=0.0)


class SystemDHW(BaseModel):
    system_type: str = "electric_storage"
    daily_demand_per_person: float = Field(50.0, ge=0.0)
    target_temperature: float = Field(55.0)
    cold_water_temperature: float = Field(10.0)
    efficiency: float = Field(0.9, ge=0.0, le=1.0)


class PrimaryEnergyFactor(BaseModel):
    fp: float = Field(..., ge=0.0)
    we: float = Field(..., ge=0.0)


class PrimaryEnergyFactors(BaseModel):
    electricity: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=2.5, we=0.6)
    natural_gas: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=1.1, we=0.2)
    district_heating: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=1.2, we=0.25)
    biomass: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=1.0, we=0.05)
    renewable: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=1.0, we=0.0)


class BuildingProject(BaseModel):
    version: str = "0.1.0"
    project_name: str = ""
    metadata: dict = {}
    general: GeneralInfo
    climate_station_id: str
    thermal_zones: List[ThermalZone]
    opaque_building_elements: List[OpaqueElement]
    transparent_building_elements: List[TransparentElement]
    thermal_bridges: ThermalBridgeConfig = ThermalBridgeConfig()
    ventilation: Ventilation
    internal_gains: InternalGains = InternalGains()
    systems: dict = {}  # Will be refined once schema is stable
    primary_energy: PrimaryEnergyFactors = PrimaryEnergyFactors()


class MonthlyResult(BaseModel):
    month: int
    heating_kwh: float
    cooling_kwh: float
    dhw_kwh: float
    internal_gains_kwh: float
    solar_gains_kwh: float
    transmission_losses_kwh: float
    ventilation_losses_kwh: float


class AnnualIndicators(BaseModel):
    eu_kwh_m2_year: float
    ek_kwh_m2_year: float
    ep_kwh_m2_year: float
    ec_tco2_m2_year: float
    u_oze_percent: float
    heating_kwh_m2_year: float
    cooling_kwh_m2_year: float
    dhw_kwh_m2_year: float


class ComplianceCheck(BaseModel):
    name: str
    passed: bool
    message: str


class CalculationResult(BaseModel):
    project_id: str
    status: str
    annual_indicators: AnnualIndicators
    monthly: List[MonthlyResult]
    hourly: Optional[dict] = None
    compliance: List[ComplianceCheck]
