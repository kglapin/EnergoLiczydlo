"""Configuration models for certificate-grade hourly extensions.

The public API schema stays backward compatible: advanced parameters live in
``BuildingProject.metadata["normative"]``. This lets older project files keep
working while the audited calculator can require additional normative inputs
when certificate-grade modes are enabled.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.models import BuildingProject


class GroundElementSettings(BaseModel):
    """ISO 13370 inputs that can vary between ground-coupled elements."""

    exposed_perimeter_m: float | None = Field(None, gt=0.0)
    floor_thermal_resistance_m2k_w: float | None = Field(None, gt=0.0)
    basement_depth_m: float | None = Field(None, ge=0.0)
    periodic_amplitude_ratio: float | None = Field(None, ge=0.0, le=1.0)
    phase_shift_days: float | None = Field(None, ge=0.0, le=365.0)
    diagnostic_effective_depth_m: float | None = Field(None, gt=0.0)


class GroundISO13370Settings(BaseModel):
    """Ground heat-transfer settings.

    ``certificate_mode`` deliberately requires periodic response coefficients
    for every slab element. ISO 13370 limits its normal seasonal calculation
    to monthly periods; sub-monthly dynamic use belongs to Annex D. The
    application therefore does not invent Annex-D coefficients in certificate
    mode. A diagnostic 1-D harmonic soil response is available only when
    ``certificate_mode`` is false.
    """

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
    """Dynamic heat-recovery controller used by the hourly solver."""

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
        if self.certificate_mode and self.frost_strategy != "none":
            if self.indoor_relative_humidity is None:
                raise ValueError(
                    "Certificate-grade frost control requires indoor_relative_humidity"
                )
        return self


class DesignConditionsSettings(BaseModel):
    """Explicit project conditions for PN-EN 12831-1 load calculations."""

    enabled: bool = False
    certificate_mode: bool = False
    outdoor_design_temperature_c: float | None = None
    source: str | None = None
    heat_up_power_by_zone_w: dict[str, float] = Field(default_factory=dict)
    unheated_adjacent_temperature_by_element_c: dict[str, float] = Field(
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


class NormativeSettings(BaseModel):
    """Advanced calculation settings read from ``metadata.normative``."""

    ground: GroundISO13370Settings = Field(default_factory=GroundISO13370Settings)
    heat_recovery: HeatRecoverySettings = Field(default_factory=HeatRecoverySettings)
    design_conditions: DesignConditionsSettings = Field(
        default_factory=DesignConditionsSettings
    )


def load_normative_settings(project: BuildingProject) -> NormativeSettings:
    """Parse advanced normative configuration from project metadata."""
    raw = project.metadata.get("normative", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("metadata.normative must be an object")
    return NormativeSettings.model_validate(raw)
