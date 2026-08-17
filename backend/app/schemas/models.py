from __future__ import annotations

from enum import StrEnum
from math import isclose
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class BuildingType(StrEnum):
    RESIDENTIAL = "residential"
    OFFICE = "office"
    SCHOOL = "school"
    RETAIL = "retail"
    HEALTHCARE = "healthcare"
    OTHER = "other"


class DHWUsageProfile(StrEnum):
    """Standard hot-water-use profiles from table 27 of the methodology.

    The profile controls the annual useful DHW demand QW,nd.  It is separate
    from the DHW source because the source only converts useful energy to
    final and primary energy.
    """

    RESIDENTIAL_SINGLE_FAMILY = "residential_single_family"
    RESIDENTIAL_MULTI_FAMILY_LUMP_SUM = "residential_multi_family_lump_sum"
    RESIDENTIAL_MULTI_FAMILY_INDIVIDUAL_METERING = "residential_multi_family_individual_metering"
    OFFICE = "office"
    EDUCATION = "education"
    HEALTHCARE = "healthcare"
    RETAIL_SERVICES = "retail_services"
    COLLECTIVE_RESIDENTIAL = "collective_residential"
    WAREHOUSE = "warehouse"


class ZoneType(StrEnum):
    HEATED = "heated"
    COOLED = "cooled"
    HEATED_AND_COOLED = "heated_and_cooled"
    UNHEATED = "unheated"
    SEMI_HEATED = "semi_heated"


class AdjacentSpaceType(StrEnum):
    OUTDOOR = "outdoor"
    GROUND = "ground"
    UNHEATED_ZONE = "unheated_zone"
    HEATED_ZONE = "heated_zone"
    CONSTANT_TEMPERATURE = "constant_temperature"


class ElementType(StrEnum):
    EXTERNAL_WALL = "external_wall"
    ROOF = "roof"
    GROUND_FLOOR = "ground_floor"
    FLOOR_OVER_UNHEATED = "floor_over_unheated"
    INTERNAL_WALL = "internal_wall"
    BASEMENT_WALL = "basement_wall"
    PARTY_WALL = "party_wall"


class TransparentType(StrEnum):
    WINDOW = "window"
    GLASS_DOOR = "glass_door"
    SKYLIGHT = "skylight"


class VentilationType(StrEnum):
    NATURAL = "natural"
    MECHANICAL = "mechanical"
    MECHANICAL_WITH_RECOVERY = "mechanical_with_recovery"
    EXHAUST = "exhaust"
    HYBRID = "hybrid"
    NONE = "none"


class VentilationOperationMode(StrEnum):
    """Operating mode of mechanical ventilation."""

    CONTINUOUS = "continuous"
    PERIODIC = "periodic"


class EnergyCarrier(StrEnum):
    """Energy carriers used for the final and primary-energy balance."""

    ELECTRICITY = "electricity"
    NATURAL_GAS = "natural_gas"
    LPG = "lpg"
    HEATING_OIL = "heating_oil"
    HARD_COAL = "hard_coal"
    LIGNITE = "lignite"
    BIOMASS = "biomass"
    BIOGAS = "biogas"
    DISTRICT_HEATING = "district_heating"
    SOLAR = "solar"
    WIND = "wind"
    GEOTHERMAL = "geothermal"


class SystemSourceType(StrEnum):
    """Controlled source catalogue for heating and cooling systems."""

    NONE = "none"
    ELECTRIC_DIRECT = "electric_direct"
    GAS_BOILER = "gas_boiler"
    GAS_CONDENSING = "gas_condensing"
    OIL_BOILER = "oil_boiler"
    BIOMASS_BOILER = "biomass_boiler"
    COAL_BOILER = "coal_boiler"
    FIREPLACE = "fireplace"
    HEAT_PUMP_AIR = "heat_pump_air"
    HEAT_PUMP_GROUND = "heat_pump_ground"
    HEAT_PUMP_WATER = "heat_pump_water"
    DISTRICT_HEATING = "district_heating"
    SPLIT_AC = "split_ac"
    MULTISPLIT_VRV = "multisplit_vrv"
    VRV = "vrv"
    LIQUID_CHILLER_AIR = "liquid_chiller_air"
    LIQUID_CHILLER_WATER = "liquid_chiller_water"
    PASSIVE_GROUND_COOLING = "passive_ground_cooling"
    ABSORPTION_COOLING = "absorption_cooling"


class DHWSourceType(StrEnum):
    NONE = "none"
    ELECTRIC_STORAGE = "electric_storage"
    ELECTRIC_INSTANTANEOUS = "electric_instantaneous"
    GAS_INSTANTANEOUS = "gas_instantaneous"
    GAS_BOILER = "gas_boiler"
    GAS_CONDENSING = "gas_condensing"
    HEAT_PUMP_AIR = "heat_pump_air"
    HEAT_PUMP_GROUND = "heat_pump_ground"
    HEAT_PUMP_WATER = "heat_pump_water"
    DISTRICT_HEATING = "district_heating"


class DHWDistributionType(StrEnum):
    """Distribution variants represented in table 12 of the methodology."""

    POINT_OF_USE = "point_of_use"
    SINGLE_DWELLING = "single_dwelling"
    CENTRAL_NO_CIRCULATION = "central_no_circulation"
    CENTRAL_CIRCULATION_UNINSULATED = "central_circulation_uninsulated"
    CENTRAL_CIRCULATION_INSULATED = "central_circulation_insulated"
    CENTRAL_CIRCULATION_TIME_LIMITED = "central_circulation_time_limited"


class ScheduleType(StrEnum):
    CONSTANT = "constant"
    WEEKDAY_WEEKEND = "weekday_weekend"
    HOURLY_PROFILE = "hourly_profile"


class Schedule(BaseModel):
    type: ScheduleType = ScheduleType.CONSTANT
    constant_value: float | None = 1.0
    weekday: list[float] | None = None
    saturday: list[float] | None = None
    sunday: list[float] | None = None
    holiday: list[float] | None = None

    @field_validator("constant_value")
    @classmethod
    def _check_constant_value(cls, v: float | None) -> float | None:
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError("constant_value must be between 0.0 and 1.0")
        return v

    @field_validator("weekday", "saturday", "sunday", "holiday")
    @classmethod
    def _check_hourly_length(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and len(v) != 24:
            raise ValueError("Hourly profile must contain exactly 24 values")
        if v is not None and any(value < 0.0 or value > 1.0 for value in v):
            raise ValueError("Hourly profile values must be between 0.0 and 1.0")
        return v


class GeneralInfo(BaseModel):
    building_name: str = ""
    building_type: BuildingType = BuildingType.RESIDENTIAL
    dhw_usage_profile: DHWUsageProfile = DHWUsageProfile.RESIDENTIAL_SINGLE_FAMILY
    construction_year: int = Field(2020, ge=1900, le=2100)
    conditioned_floor_area: float = Field(..., gt=0.0)
    usable_floor_area: float = Field(..., gt=0.0)
    heated_volume: float = Field(..., gt=0.0)
    number_of_storeys: int = Field(1, ge=1)
    location_address: str | None = None
    # Wskaźnik LENI [kWh/(m2·rok)] wg PN-EN 15193 dla wbudowanej instalacji
    # oświetlenia (wzór (35)). Stosowany wyłącznie dla budynków
    # niemieszkalnych; None = oświetlenie nie jest liczone.
    lighting_indicator_leni: float | None = Field(None, ge=0.0)
    # Powierzchnia pomieszczeń z oświetleniem A_L [m2]; domyślnie Af.
    lighting_area_m2: float | None = Field(None, gt=0.0)


class ThermalZone(BaseModel):
    id: str = Field(..., min_length=1)
    name: str
    zone_type: ZoneType = ZoneType.HEATED
    floor_area: float = Field(..., gt=0.0)
    volume: float = Field(..., gt=0.0)
    setpoint_heating: float = Field(20.0)
    setpoint_cooling: float | None = Field(None)
    occupancy_density: float = Field(0.03, ge=0.0)


class OpaqueElement(BaseModel):
    id: str
    name: str
    zone_id: str = Field(..., min_length=1)
    element_type: ElementType = ElementType.EXTERNAL_WALL
    orientation_azimuth: float = Field(0.0, ge=0.0, lt=360.0)
    inclination: float = Field(90.0, ge=0.0, le=180.0)
    height: float | None = Field(None, gt=0.0)
    width: float | None = Field(None, gt=0.0)
    area: float = Field(..., gt=0.0)
    u_value: float = Field(..., gt=0.0)
    solar_absorptance: float = Field(0.6, ge=0.0, le=1.0)
    emissivity: float = Field(0.9, ge=0.0, le=1.0)
    # Deprecated: retained only so older project files keep validating. The
    # engine derives the inward solar fraction physically from U * R_se and
    # ignores this field.
    solar_reduction_factor: float = Field(0.08, ge=0.0, le=1.0, deprecated=True)
    adjacent_space_type: AdjacentSpaceType = AdjacentSpaceType.OUTDOOR
    adjacent_temperature: float | None = None

    @model_validator(mode="after")
    def calculate_area_from_dimensions(self) -> OpaqueElement:
        """Derive the envelope area from height and width when supplied."""
        if (self.height is None) != (self.width is None):
            raise ValueError("Both height and width must be provided together")
        if self.height is not None and self.width is not None:
            self.area = self.height * self.width
        return self


class TransparentElement(BaseModel):
    id: str
    name: str
    zone_id: str = Field(..., min_length=1)
    element_type: TransparentType = TransparentType.WINDOW
    orientation_azimuth: float = Field(0.0, ge=0.0, lt=360.0)
    inclination: float = Field(90.0, ge=0.0, le=180.0)
    height: float | None = Field(None, gt=0.0)
    width: float | None = Field(None, gt=0.0)
    area: float = Field(..., gt=0.0)
    u_value: float = Field(..., gt=0.0)
    g_value: float = Field(..., ge=0.0, le=1.0)
    frame_factor: float = Field(0.2, ge=0.0, le=1.0)
    shading_factor: float = Field(1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def calculate_area_from_dimensions(self) -> TransparentElement:
        """Derive the glazed area from height and width when supplied."""
        if (self.height is None) != (self.width is None):
            raise ValueError("Both height and width must be provided together")
        if self.height is not None and self.width is not None:
            self.area = self.height * self.width
        return self


class LinearThermalBridge(BaseModel):
    id: str
    name: str
    psi_value: float = Field(..., ge=0.0)
    length: float = Field(..., ge=0.0)
    zone_id: str
    element_id: str | None = None


class PointThermalBridge(BaseModel):
    id: str
    name: str
    chi_value: float = Field(..., ge=0.0)
    count: int = Field(1, ge=0)
    zone_id: str


class ThermalBridgeConfig(BaseModel):
    auto_calculate: bool = False
    linear_bridges: list[LinearThermalBridge] = []
    point_bridges: list[PointThermalBridge] = []


class Ventilation(BaseModel):
    ventilation_type: VentilationType = VentilationType.NATURAL
    operation_mode: VentilationOperationMode = VentilationOperationMode.CONTINUOUS
    # Budynkowy nominalny strumień powietrza [m3/h] podczas pracy wentylatorów.
    # Wartość 0 oznacza pobranie strumienia normatywnego z tabel 21/22/24/25
    # rozporządzenia; dla trybu okresowego jest to strumień w okresie użytkowania.
    airflow_rate: float = Field(0.0, ge=0.0)
    heat_recovery_efficiency: float = Field(0.0, ge=0.0, le=1.0)
    # Infiltracja przy wyłączonej wentylacji mechanicznej [1/h], tj. V_inf/V.
    # Modern buildings default to the methodology value n = 0.2 1/h. The
    # calculator switches an omitted field to n = 0.3 1/h for buildings from
    # before 1996; an explicitly entered value always takes precedence.
    infiltration_rate: float = Field(0.2, ge=0.0)
    # Dodatkowa infiltracja przy pracy wentylatorów [1/h], tj. V_x,su/V lub
    # V_x,ex/V. Zero oznacza brak danych o dodatkowym strumieniu.
    fan_infiltration_rate: float = Field(0.0, ge=0.0)
    # Udział czasu użytkowania budynku β (§ 5.5.2). None = 1,0 dla
    # mieszkalnych (praca ciągła), 0,3 dla pozostałych (analogicznie do
    # przykładu standardowego z tabeli 26).
    usage_share_beta: float | None = Field(None, ge=0.0, le=1.0)
    supply_temperature: float | None = None
    mechanical_fan_power: float | None = Field(0.0, ge=0.0)
    # None means that no hourly operating profile was supplied; in periodic
    # mode the calculator then uses the regulatory time-share beta as an
    # explicit average-flow fallback.  A supplied constant/profile is used
    # literally and is never silently replaced by beta.
    schedule: Schedule | None = None


class InternalGainSource(BaseModel):
    power_density: float = Field(..., ge=0.0)
    schedule: Schedule = Schedule()


class InternalGains(BaseModel):
    """Internal heat gains; defaults reproduce tabela 26 of the methodology.

    The automatically generated project default carries the normative q_int
    total from table 26 alongside a display-oriented three-source split. The
    total is kept independent of a zone's user-entered occupancy density.
    Other building types should use ``normative_internal_gains`` from
    app.engine.internal_gains.
    """

    occupancy: InternalGainSource = InternalGainSource(power_density=80.0)
    lighting: InternalGainSource = InternalGainSource(power_density=2.0)
    equipment: InternalGainSource = InternalGainSource(power_density=2.4)
    # When the project omits an explicit internal-gains breakdown, the
    # methodology supplies one total q_int [W/m²].  Keep that target alongside
    # the UI-friendly source split so changing a zone's occupancy density does
    # not silently change the normative total.
    normative_power_density_w_m2: float | None = Field(None, ge=0.0)


class SystemHeatingCooling(BaseModel):
    """Heating/cooling source and seasonal system-efficiency parameters.

    ``generation_efficiency`` is ηH,g for heating and SEER for cooling.
    The remaining fields correspond to the distribution, storage and
    regulation/use components of the seasonal efficiency. The total efficiency
    is their product. ``installation_type`` classifies the terminal installation
    and selects the corresponding Table 20 circulation-pump fallback when
    auxiliary electricity is not entered explicitly.
    """

    system_type: SystemSourceType = SystemSourceType.HEAT_PUMP_AIR
    installation_type: str | None = Field(None)
    fuel_or_carrier: EnergyCarrier = EnergyCarrier.ELECTRICITY
    # Retained only to import older JSON files. It is ignored: heating power
    # is derived from calculated peak heat losses and cooling Q_C,nd is
    # obtained from the hourly thermal balance.
    nominal_power: float | None = Field(None, deprecated=True)
    generation_efficiency: float | None = Field(None, gt=0.0)
    distribution_efficiency: float | None = Field(None, gt=0.0, le=1.0)
    storage_efficiency: float = Field(1.0, gt=0.0, le=1.0)
    control_efficiency: float = Field(1.0, gt=0.0, le=1.0)
    # Legacy input retained for imported JSON files from the previous schema.
    efficiency_or_cop_map: dict[str, Any] = Field(
        default_factory=lambda: {"constant": True, "value": 3.0}
    )
    distribution_loss_factor: float | None = Field(None, gt=0.0, le=1.0)
    control_factor: float | None = Field(None, gt=0.0)
    sink_temperature: float = Field(35.0, gt=0.0)
    # Constant heat-source temperature [degC] for ground/water heat pumps
    # (brine or water).  When None, a ground/water heat pump runs at its
    # rated COP all year instead of following the outdoor air temperature.
    source_temperature: float | None = Field(None)
    # Explicit annual final electricity for pumps, controls and other system
    # auxiliaries [kWh/year]. None keeps the legacy/methodology fallback; zero
    # is an explicit statement that no auxiliary electricity is required.
    auxiliary_energy_kwh_year: float | None = Field(None, ge=0.0)
    # Legacy field in Wh/year retained for older JSON imports. It is used only
    # when auxiliary_energy_kwh_year is omitted and the value is positive.
    auxiliary_energy: float = Field(0.0, ge=0.0, deprecated=True)

    @model_validator(mode="after")
    def infer_carrier_when_omitted(self) -> SystemHeatingCooling:
        """Keep source defaults consistent with their physical carrier."""
        if "fuel_or_carrier" not in self.model_fields_set:
            self.fuel_or_carrier = {
                SystemSourceType.GAS_BOILER: EnergyCarrier.NATURAL_GAS,
                SystemSourceType.GAS_CONDENSING: EnergyCarrier.NATURAL_GAS,
                SystemSourceType.OIL_BOILER: EnergyCarrier.HEATING_OIL,
                SystemSourceType.BIOMASS_BOILER: EnergyCarrier.BIOMASS,
                SystemSourceType.COAL_BOILER: EnergyCarrier.HARD_COAL,
                SystemSourceType.FIREPLACE: EnergyCarrier.BIOMASS,
                SystemSourceType.DISTRICT_HEATING: EnergyCarrier.DISTRICT_HEATING,
            }.get(self.system_type, EnergyCarrier.ELECTRICITY)
        return self


class SystemDHW(BaseModel):
    """DHW source and ηW,g/ηW,s/ηW,d/ηW,e input parameters."""

    system_type: DHWSourceType = DHWSourceType.ELECTRIC_STORAGE
    fuel_or_carrier: EnergyCarrier = EnergyCarrier.ELECTRICITY
    # Legacy demand inputs are intentionally ignored. Q_W,nd is calculated
    # from GeneralInfo.dhw_usage_profile and Af according to § 5.3/table 27.
    daily_demand_per_person: float | None = Field(None, deprecated=True)
    number_of_users: float | None = Field(None, deprecated=True)
    target_temperature: float | None = Field(None, deprecated=True)
    cold_water_temperature: float | None = Field(None, deprecated=True)
    generation_efficiency: float | None = Field(None, gt=0.0)
    storage_efficiency: float = Field(1.0, gt=0.0, le=1.0)
    distribution_efficiency: float = Field(0.6, gt=0.0, le=1.0)
    utilization_efficiency: float = Field(1.0, gt=0.0, le=1.0)
    distribution_type: DHWDistributionType = DHWDistributionType.CENTRAL_NO_CIRCULATION
    # Straty zasobnika wg tabeli 13 / wzoru (30). Gdy objętość jest podana,
    # straty postoju ΔQ_W,s wyznaczane są z tabeli 13 (ηW,s z wzoru (29));
    # w przeciwnym razie stosowane jest pole storage_efficiency.
    storage_volume_dm3: float | None = Field(None, gt=0.0)
    storage_location: str | None = Field(None)  # "heated" / "unheated"
    storage_insulation_mm: float | None = Field(None, gt=0.0)  # 100/50/20
    # Legacy input retained for imported JSON files from the previous schema.
    efficiency: float | None = Field(None, gt=0.0)

    @model_validator(mode="after")
    def validate_storage_inputs(self) -> SystemDHW:
        """Do not invent storage location or insulation data."""
        if self.storage_volume_dm3 is None or self.system_type == DHWSourceType.NONE:
            return self
        if self.storage_location is None:
            raise ValueError("storage_location is required when storage_volume_dm3 is provided")
        requires_insulation = self.system_type in {
            DHWSourceType.HEAT_PUMP_AIR,
            DHWSourceType.HEAT_PUMP_GROUND,
            DHWSourceType.HEAT_PUMP_WATER,
            DHWSourceType.DISTRICT_HEATING,
        }
        if requires_insulation and self.storage_insulation_mm is None:
            raise ValueError("storage_insulation_mm is required for an indirect DHW storage tank")
        return self

    @model_validator(mode="after")
    def infer_carrier_when_omitted(self) -> SystemDHW:
        """Keep DHW source defaults consistent with their physical carrier."""
        if "fuel_or_carrier" not in self.model_fields_set:
            self.fuel_or_carrier = {
                DHWSourceType.GAS_INSTANTANEOUS: EnergyCarrier.NATURAL_GAS,
                DHWSourceType.GAS_BOILER: EnergyCarrier.NATURAL_GAS,
                DHWSourceType.GAS_CONDENSING: EnergyCarrier.NATURAL_GAS,
                DHWSourceType.DISTRICT_HEATING: EnergyCarrier.DISTRICT_HEATING,
            }.get(self.system_type, EnergyCarrier.ELECTRICITY)
        return self


HEATING_SOURCE_TYPES = frozenset(
    {
        SystemSourceType.NONE,
        SystemSourceType.ELECTRIC_DIRECT,
        SystemSourceType.GAS_BOILER,
        SystemSourceType.GAS_CONDENSING,
        SystemSourceType.OIL_BOILER,
        SystemSourceType.BIOMASS_BOILER,
        SystemSourceType.COAL_BOILER,
        SystemSourceType.FIREPLACE,
        SystemSourceType.HEAT_PUMP_AIR,
        SystemSourceType.HEAT_PUMP_GROUND,
        SystemSourceType.HEAT_PUMP_WATER,
        SystemSourceType.DISTRICT_HEATING,
    }
)

COOLING_SOURCE_TYPES = frozenset(
    {
        SystemSourceType.NONE,
        SystemSourceType.SPLIT_AC,
        SystemSourceType.MULTISPLIT_VRV,
        SystemSourceType.VRV,
        SystemSourceType.LIQUID_CHILLER_AIR,
        SystemSourceType.LIQUID_CHILLER_WATER,
        SystemSourceType.PASSIVE_GROUND_COOLING,
        SystemSourceType.ABSORPTION_COOLING,
    }
)


class BuildingSystems(BaseModel):
    """Technical systems used by the three energy-service calculations."""

    heating: SystemHeatingCooling = Field(
        default_factory=lambda: SystemHeatingCooling.model_construct()
    )
    cooling: SystemHeatingCooling | None = None
    dhw: SystemDHW = Field(default_factory=lambda: SystemDHW.model_construct())

    @model_validator(mode="after")
    def validate_service_sources(self) -> BuildingSystems:
        if self.heating.system_type not in HEATING_SOURCE_TYPES:
            raise ValueError(f"Invalid heating system source: {self.heating.system_type}")
        if self.cooling is not None and self.cooling.system_type not in COOLING_SOURCE_TYPES:
            raise ValueError(f"Invalid cooling system source: {self.cooling.system_type}")
        return self


class PrimaryEnergyFactor(BaseModel):
    fp: float = Field(..., ge=0.0)
    we: float = Field(..., ge=0.0)


class PrimaryEnergyFactors(BaseModel):
    """Non-renewable primary energy factors w_i and CO2 emission indicators.

    ``fp`` defaults follow the current tabela 1 (Dz.U. 2023 poz. 697):
    electricity 2.50, local fossil fuels 1.10, biomass 0.20, biogas 0.50.
    District heating depends on the source plant (cogeneration 0.80 coal/gas
    or 0.15 biomass; heat-only plant 1.30 coal or 1.20 gas/oil) - 1.20 is
    kept as a neutral default that the user should adjust per project.
    ``we`` is expressed in kg CO2/kWh; override with current KOBiZE values.
    """

    electricity: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=2.5, we=0.6)
    natural_gas: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=1.1, we=0.2)
    lpg: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=1.1, we=0.2)
    heating_oil: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=1.1, we=0.27)
    hard_coal: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=1.1, we=0.34)
    lignite: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=1.1, we=0.34)
    district_heating: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=1.2, we=0.25)
    biomass: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=0.2, we=0.05)
    biogas: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=0.5, we=0.05)
    solar: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=0.0, we=0.0)
    wind: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=0.0, we=0.0)
    geothermal: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=0.0, we=0.0)
    renewable: PrimaryEnergyFactor = PrimaryEnergyFactor(fp=0.0, we=0.0)


class BuildingProject(BaseModel):
    version: str = "0.1.0"
    project_name: str = ""
    metadata: dict[str, Any] = {}
    general: GeneralInfo
    climate_station_id: str
    thermal_zones: list[ThermalZone]
    opaque_building_elements: list[OpaqueElement]
    transparent_building_elements: list[TransparentElement]
    thermal_bridges: ThermalBridgeConfig = ThermalBridgeConfig()
    ventilation: Ventilation
    internal_gains: InternalGains = Field(
        default_factory=lambda: InternalGains(normative_power_density_w_m2=None)
    )
    systems: BuildingSystems = Field(default_factory=BuildingSystems)
    primary_energy: PrimaryEnergyFactors = PrimaryEnergyFactors()

    @model_validator(mode="after")
    def validate_zone_references(self) -> BuildingProject:
        # If a caller omits the input, derive the norm-specific default from
        # the building type instead of always using the single-family
        # 6.8 W/m² fallback.  The local import avoids a schema-module cycle.
        if "internal_gains" not in self.model_fields_set:
            from app.engine.internal_gains import normative_internal_gains

            profile = str(
                getattr(self.general.dhw_usage_profile, "value", self.general.dhw_usage_profile)
            )
            beta = (
                self.ventilation.usage_share_beta
                if self.ventilation.usage_share_beta is not None
                else (1.0 if profile.startswith("residential") else 0.3)
            )
            self.internal_gains = normative_internal_gains(
                self.general.building_type,
                self.general.dhw_usage_profile,
                beta=beta,
            )

        zone_ids = [zone.id for zone in self.thermal_zones]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("Thermal zone IDs must be unique")

        referenced_zone_ids = [element.zone_id for element in self.opaque_building_elements] + [
            element.zone_id for element in self.transparent_building_elements
        ]
        referenced_zone_ids.extend(bridge.zone_id for bridge in self.thermal_bridges.linear_bridges)
        referenced_zone_ids.extend(bridge.zone_id for bridge in self.thermal_bridges.point_bridges)
        missing_zone_ids = sorted(set(referenced_zone_ids) - set(zone_ids))
        if missing_zone_ids:
            missing = ", ".join(missing_zone_ids)
            raise ValueError(f"Unknown thermal zone ID referenced by an element: {missing}")

        conditioned_types = {
            ZoneType.HEATED,
            ZoneType.COOLED,
            ZoneType.HEATED_AND_COOLED,
            ZoneType.SEMI_HEATED,
        }
        conditioned_zones = [
            zone for zone in self.thermal_zones if zone.zone_type in conditioned_types
        ]
        if not conditioned_zones:
            raise ValueError("BuildingProject requires at least one conditioned thermal zone")
        zone_area = sum(zone.floor_area for zone in conditioned_zones)
        if not isclose(
            zone_area,
            self.general.conditioned_floor_area,
            rel_tol=1e-6,
            abs_tol=0.01,
        ):
            raise ValueError(
                "Conditioned floor area must equal the sum of conditioned zone areas; "
                f"got Af={self.general.conditioned_floor_area:g}, zones={zone_area:g}"
            )
        zone_volume = sum(zone.volume for zone in conditioned_zones)
        if not isclose(zone_volume, self.general.heated_volume, rel_tol=1e-6, abs_tol=0.01):
            raise ValueError(
                "Heated volume must equal the sum of conditioned zone volumes; "
                f"got V={self.general.heated_volume:g}, zones={zone_volume:g}"
            )

        # The current 5R1C implementation treats a heated-zone partition as
        # zero net flow.  That is valid only when the conditioned spaces have
        # the same active temperature limits; otherwise a coupled multi-zone
        # solver is required and silently dropping the partition is unsafe.
        has_heated_partition = any(
            element.adjacent_space_type == AdjacentSpaceType.HEATED_ZONE
            for element in self.opaque_building_elements
        )
        if has_heated_partition:
            conditioned_limits = {
                (
                    zone.setpoint_heating
                    if zone.zone_type
                    in {
                        ZoneType.HEATED,
                        ZoneType.HEATED_AND_COOLED,
                        ZoneType.SEMI_HEATED,
                    }
                    else None,
                    zone.setpoint_cooling
                    if zone.zone_type in {ZoneType.COOLED, ZoneType.HEATED_AND_COOLED}
                    else None,
                )
                for zone in self.thermal_zones
                if zone.zone_type
                in {
                    ZoneType.HEATED,
                    ZoneType.HEATED_AND_COOLED,
                    ZoneType.COOLED,
                    ZoneType.SEMI_HEATED,
                }
            }
            if len(conditioned_limits) > 1:
                raise ValueError(
                    "Partitions adjacent to heated zones require identical "
                    "active heating/cooling setpoints in all conditioned zones"
                )
        return self


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
    design_heating_power_kw: float = Field(0.0, ge=0.0)
    annual_indicators: AnnualIndicators
    monthly: list[MonthlyResult]
    hourly: dict[str, Any] | None = None
    compliance: list[ComplianceCheck]
