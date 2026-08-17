"""Configuration models for normative hourly and Polish certificate calculations.

Advanced parameters live in ``BuildingProject.metadata["normative"]`` so old
project JSON remains valid. The hourly ISO 52016 analysis and the legally
prescribed Polish certificate calculation are deliberately represented as
separate calculation layers.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.models import BuildingProject

MONTHS = 12


def _validate_monthly_series(name: str, values: list[float]) -> None:
    if len(values) != MONTHS:
        raise ValueError(f"{name} must contain exactly 12 monthly values")


def _validate_monthly_map(name: str, values: dict[str, list[float]]) -> None:
    for key, series in values.items():
        _validate_monthly_series(f"{name}[{key}]", series)


class GroundElementSettings(BaseModel):
    exposed_perimeter_m: float | None = Field(None, gt=0.0)
    floor_thermal_resistance_m2k_w: float | None = Field(None, gt=0.0)
    basement_depth_m: float | None = Field(None, ge=0.0)
    periodic_amplitude_ratio: float | None = Field(None, ge=0.0, le=1.0)
    phase_shift_days: float | None = Field(None, ge=0.0, le=365.0)
    diagnostic_effective_depth_m: float | None = Field(None, gt=0.0)

    @model_validator(mode="after")
    def require_complete_periodic_pair(self) -> GroundElementSettings:
        if (self.periodic_amplitude_ratio is None) != (self.phase_shift_days is None):
            raise ValueError(
                "periodic_amplitude_ratio and phase_shift_days must be supplied together"
            )
        return self


class GroundISO13370Settings(BaseModel):
    enabled: bool = False
    certificate_mode: bool = False
    soil_conductivity_w_mk: float | None = Field(None, gt=0.0)
    soil_density_kg_m3: float | None = Field(None, gt=0.0)
    soil_specific_heat_j_kgk: float | None = Field(None, gt=0.0)
    external_wall_thickness_m: float | None = Field(None, ge=0.0)
    elements: dict[str, GroundElementSettings] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_material_inputs_when_enabled(self) -> GroundISO13370Settings:
        if not self.enabled:
            return self
        required = {
            "soil_conductivity_w_mk": self.soil_conductivity_w_mk,
            "soil_density_kg_m3": self.soil_density_kg_m3,
            "soil_specific_heat_j_kgk": self.soil_specific_heat_j_kgk,
            "external_wall_thickness_m": self.external_wall_thickness_m,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(
                "Ground ISO 13370 mode requires explicit material inputs: "
                + ", ".join(missing)
            )
        return self


class RecoveryEfficiencyPoint(BaseModel):
    outdoor_temperature_c: float
    efficiency: float = Field(..., ge=0.0, le=1.0)


FrostStrategy = Literal["none", "preheater", "reduce_recovery", "disable_recovery"]


class HeatRecoverySettings(BaseModel):
    enabled: bool = False
    certificate_mode: bool = False
    performance_source: str | None = None
    efficiency_curve: list[RecoveryEfficiencyPoint] = Field(default_factory=list)
    summer_bypass_enabled: bool = False
    bypass_min_outdoor_c: float | None = None
    bypass_max_outdoor_c: float | None = None
    bypass_indoor_margin_k: float = Field(1.0, ge=0.0)
    frost_strategy: FrostStrategy = "none"
    frost_exhaust_limit_c: float = 0.0
    indoor_relative_humidity: float | None = Field(None, gt=0.0, le=1.0)
    preheater_max_power_w: float | None = Field(None, ge=0.0)
    preheater_efficiency: float = Field(1.0, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_controls(self) -> HeatRecoverySettings:
        if not self.enabled:
            return self
        if self.certificate_mode and not (self.performance_source or "").strip():
            raise ValueError(
                "Certificate-grade heat recovery requires performance_source "
                "(manufacturer/test documentation reference)"
            )
        if self.summer_bypass_enabled:
            if self.bypass_min_outdoor_c is None or self.bypass_max_outdoor_c is None:
                raise ValueError(
                    "Dynamic summer bypass requires bypass_min_outdoor_c and "
                    "bypass_max_outdoor_c"
                )
            if self.bypass_min_outdoor_c >= self.bypass_max_outdoor_c:
                raise ValueError("bypass_min_outdoor_c must be below bypass_max_outdoor_c")
        if self.frost_strategy == "preheater" and self.preheater_max_power_w is None:
            raise ValueError("Preheater frost strategy requires preheater_max_power_w")
        if (
            self.certificate_mode
            and self.frost_strategy != "none"
            and self.indoor_relative_humidity is None
        ):
            raise ValueError(
                "Certificate-grade frost control requires indoor_relative_humidity"
            )
        return self


class DesignConditionsSettings(BaseModel):
    enabled: bool = False
    certificate_mode: bool = False
    outdoor_design_temperature_c: float | None = None
    source: str | None = None
    heat_up_power_by_zone_w: dict[str, float] = Field(default_factory=dict)
    unheated_adjacent_temperature_by_element_c: dict[str, float] = Field(
        default_factory=dict
    )
    ground_adjacent_temperature_by_element_c: dict[str, float] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def require_design_condition_source(self) -> DesignConditionsSettings:
        if not self.enabled:
            return self
        if self.outdoor_design_temperature_c is None:
            raise ValueError(
                "Design-load calculation requires outdoor_design_temperature_c"
            )
        if self.certificate_mode and not (self.source or "").strip():
            raise ValueError(
                "Certificate-grade design load requires the source of the design "
                "outdoor temperature / national-annex value"
            )
        if any(value < 0.0 for value in self.heat_up_power_by_zone_w.values()):
            raise ValueError("heat_up_power_by_zone_w values must be non-negative")
        return self


class PolishCertificateMonthlySettings(BaseModel):
    """Inputs for the legally prescribed monthly certificate calculation.

    Coefficients that the regulation delegates to a Polish Standard are not
    reverse-engineered here. In formal mode the verified monthly coefficients
    are explicit inputs with an evidence trail in ``legal``.
    """

    enabled: bool = False
    official_bip_climate_data: bool = False
    monthly_outdoor_temperature_c: list[float] = Field(default_factory=list)
    solar_irradiation_kwh_m2_by_element: dict[str, list[float]] = Field(
        default_factory=dict
    )
    heating_internal_temperature_c_by_zone: dict[str, list[float]] = Field(
        default_factory=dict
    )
    cooling_internal_temperature_c_by_zone: dict[str, list[float]] = Field(
        default_factory=dict
    )
    heating_gain_utilization_by_zone: dict[str, list[float]] = Field(
        default_factory=dict
    )
    cooling_loss_utilization_by_zone: dict[str, list[float]] = Field(
        default_factory=dict
    )
    beta_by_zone: dict[str, list[float]] = Field(default_factory=dict)
    recovery_effectiveness_by_zone: dict[str, list[float]] = Field(
        default_factory=dict
    )
    supply_extract_reduction_by_zone: dict[str, list[float]] = Field(
        default_factory=dict
    )
    unheated_adjacent_temperature_c_by_element: dict[str, list[float]] = Field(
        default_factory=dict
    )
    ground_adjacent_temperature_c_by_element: dict[str, list[float]] = Field(
        default_factory=dict
    )
    internal_gain_density_w_m2_by_zone: dict[str, float] = Field(default_factory=dict)
    preheater_electricity_kwh_by_month: list[float] = Field(default_factory=list)
    heating_useful_override_kwh_by_zone: dict[str, list[float]] = Field(
        default_factory=dict
    )
    cooling_useful_override_kwh_by_zone: dict[str, list[float]] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_monthly_data(self) -> PolishCertificateMonthlySettings:
        if not self.enabled:
            return self
        _validate_monthly_series(
            "monthly_outdoor_temperature_c", self.monthly_outdoor_temperature_c
        )
        if self.preheater_electricity_kwh_by_month:
            _validate_monthly_series(
                "preheater_electricity_kwh_by_month",
                self.preheater_electricity_kwh_by_month,
            )
        monthly_maps = {
            "solar_irradiation_kwh_m2_by_element": (
                self.solar_irradiation_kwh_m2_by_element
            ),
            "heating_internal_temperature_c_by_zone": (
                self.heating_internal_temperature_c_by_zone
            ),
            "cooling_internal_temperature_c_by_zone": (
                self.cooling_internal_temperature_c_by_zone
            ),
            "heating_gain_utilization_by_zone": self.heating_gain_utilization_by_zone,
            "cooling_loss_utilization_by_zone": self.cooling_loss_utilization_by_zone,
            "beta_by_zone": self.beta_by_zone,
            "recovery_effectiveness_by_zone": self.recovery_effectiveness_by_zone,
            "supply_extract_reduction_by_zone": self.supply_extract_reduction_by_zone,
            "unheated_adjacent_temperature_c_by_element": (
                self.unheated_adjacent_temperature_c_by_element
            ),
            "ground_adjacent_temperature_c_by_element": (
                self.ground_adjacent_temperature_c_by_element
            ),
            "heating_useful_override_kwh_by_zone": self.heating_useful_override_kwh_by_zone,
            "cooling_useful_override_kwh_by_zone": self.cooling_useful_override_kwh_by_zone,
        }
        for name, values in monthly_maps.items():
            _validate_monthly_map(name, values)
        bounded_maps = (
            self.heating_gain_utilization_by_zone,
            self.cooling_loss_utilization_by_zone,
            self.beta_by_zone,
            self.recovery_effectiveness_by_zone,
            self.supply_extract_reduction_by_zone,
        )
        if any(
            value < 0.0 or value > 1.0
            for mapping in bounded_maps
            for series in mapping.values()
            for value in series
        ):
            raise ValueError(
                "Monthly utilization, beta, recovery and reduction factors must be 0..1"
            )
        return self


class LegalProvenanceSettings(BaseModel):
    certificate_mode: bool = False
    calculation_date: date | None = None
    methodology_source: str | None = None
    climate_data_source: str | None = None
    utilization_factor_source: str | None = None
    ventilation_factor_source: str | None = None
    primary_energy_factor_sources: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_formal_provenance(self) -> LegalProvenanceSettings:
        if not self.certificate_mode:
            return self
        missing: list[str] = []
        if self.calculation_date is None:
            missing.append("calculation_date")
        if not (self.methodology_source or "").strip():
            missing.append("methodology_source")
        if not (self.climate_data_source or "").strip():
            missing.append("climate_data_source")
        if not (self.utilization_factor_source or "").strip():
            missing.append("utilization_factor_source")
        if not (self.ventilation_factor_source or "").strip():
            missing.append("ventilation_factor_source")
        if missing:
            raise ValueError(
                "Formal calculation mode requires provenance fields: "
                + ", ".join(missing)
            )
        return self


class NormativeSettings(BaseModel):
    ground: GroundISO13370Settings = GroundISO13370Settings.model_construct()
    heat_recovery: HeatRecoverySettings = HeatRecoverySettings.model_construct()
    design_conditions: DesignConditionsSettings = DesignConditionsSettings.model_construct()
    polish_certificate: PolishCertificateMonthlySettings = (
        PolishCertificateMonthlySettings.model_construct()
    )
    legal: LegalProvenanceSettings = LegalProvenanceSettings.model_construct()


def load_normative_settings(project: BuildingProject) -> NormativeSettings:
    raw = project.metadata.get("normative", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("metadata.normative must be an object")
    return NormativeSettings.model_validate(raw)
