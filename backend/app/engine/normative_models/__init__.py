"""Normative settings for the audited calculation runtime.

ISO 52016 analysis and the legally prescribed Polish certificate calculation
remain separate layers. Strict ISO mode fails closed when inputs delegated to
other EPB modules have not been supplied with the project.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from app.schemas.models import BuildingProject

_LEGACY_NAME = "app.engine._legacy_normative_models"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "normative_models.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load legacy normative settings from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)
for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)


class GroundElementSettings(_legacy.GroundElementSettings):
    """ISO 13370/13789 outputs consumed by ISO 52016 clause 6.5.8.2."""

    virtual_ground_resistance_m2k_w: float | None = Field(None, gt=0.0)
    virtual_ground_temperature_c_by_month: list[float] | None = None
    fixed_soil_layer_capacity_kj_m2k: float | None = Field(None, ge=0.0)

    @model_validator(mode="after")
    def validate_virtual_ground_boundary(self) -> GroundElementSettings:
        if (
            self.virtual_ground_temperature_c_by_month is not None
            and len(self.virtual_ground_temperature_c_by_month) != 12
        ):
            raise ValueError("virtual_ground_temperature_c_by_month must contain 12 values")
        return self


class GroundISO13370Settings(_legacy.GroundISO13370Settings):
    elements: dict[str, GroundElementSettings] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_iso52016_ground_outputs(self) -> GroundISO13370Settings:
        if self.enabled and self.certificate_mode:
            incomplete = [
                element_id
                for element_id, item in self.elements.items()
                if item.virtual_ground_resistance_m2k_w is None
                or item.virtual_ground_temperature_c_by_month is None
            ]
            if incomplete:
                raise ValueError(
                    "Certificate-grade ISO 52016 ground integration requires virtual "
                    "ground resistance and 12 monthly virtual temperatures for: "
                    + ", ".join(sorted(incomplete))
                )
        return self


class HourlyISO52016Settings(BaseModel):
    enabled: bool = False
    certificate_mode: bool = False
    strict_conformance: bool = False
    internal_convective_fraction: float = Field(0.40, ge=0.0, le=1.0)
    solar_convective_fraction: float = Field(0.10, ge=0.0, le=1.0)
    hvac_convective_fraction: float = Field(1.00, ge=0.0, le=1.0)
    operative_air_weight: float = Field(0.50, ge=0.0, le=1.0)
    air_furniture_heat_capacity_kj_m2k_by_zone: dict[str, float] = Field(default_factory=dict)
    sky_temperature_difference_k: float | None = Field(None, ge=0.0)
    solar_radiant_distribution_by_zone: dict[str, dict[str, float]] = Field(default_factory=dict)
    max_heating_power_w_by_zone: dict[str, float] = Field(default_factory=dict)
    max_cooling_power_w_by_zone: dict[str, float] = Field(default_factory=dict)
    max_warmup_cycles: int = Field(20, ge=2, le=100)
    warmup_tolerance_k: float = Field(0.01, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_detailed_inputs(self) -> HourlyISO52016Settings:
        for mapping_name, mapping in (
            (
                "air_furniture_heat_capacity_kj_m2k_by_zone",
                self.air_furniture_heat_capacity_kj_m2k_by_zone,
            ),
            ("max_heating_power_w_by_zone", self.max_heating_power_w_by_zone),
            ("max_cooling_power_w_by_zone", self.max_cooling_power_w_by_zone),
        ):
            if any(value < 0.0 for value in mapping.values()):
                raise ValueError(f"{mapping_name} values must be non-negative")
        for zone_id, distribution in self.solar_radiant_distribution_by_zone.items():
            if any(value < 0.0 for value in distribution.values()):
                raise ValueError(f"solar radiant factors for '{zone_id}' must be non-negative")
            if distribution and abs(sum(distribution.values()) - 1.0) > 1e-6:
                raise ValueError(f"solar radiant factors for '{zone_id}' must sum to 1.0")
        if self.certificate_mode:
            self.strict_conformance = True
        if self.strict_conformance and self.sky_temperature_difference_k is None:
            raise ValueError(
                "Strict ISO 52016 mode requires sky_temperature_difference_k from the "
                "applicable EPB/national input"
            )
        return self


class MoistureISO52016Settings(BaseModel):
    """Clause 6.5.14 moisture-balance inputs."""

    enabled: bool = False
    strict_conformance: bool = False
    latent_heat_vaporization_j_kg: float = Field(2_500_000.0, gt=0.0)
    moisture_generation_kg_s_by_zone: dict[str, float] = Field(default_factory=dict)
    moisture_buffer_kg_s_by_zone: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_moisture_sources(self) -> MoistureISO52016Settings:
        if any(value < 0.0 for value in self.moisture_generation_kg_s_by_zone.values()):
            raise ValueError("moisture generation values must be non-negative")
        return self


class MonthlyISO52016Settings(BaseModel):
    """Clause 6.6 calculation choices; kept separate from the Polish certificate."""

    enabled: bool = False
    strict_conformance: bool = False
    heating_reference_parameter_a0: float | None = Field(None, gt=0.0)
    heating_reference_time_constant_h: float | None = Field(None, gt=0.0)
    cooling_reference_parameter_a0: float | None = Field(None, gt=0.0)
    cooling_reference_time_constant_h: float | None = Field(None, gt=0.0)

    @model_validator(mode="after")
    def require_reference_parameters(self) -> MonthlyISO52016Settings:
        if self.enabled and self.strict_conformance:
            required = (
                self.heating_reference_parameter_a0,
                self.heating_reference_time_constant_h,
                self.cooling_reference_parameter_a0,
                self.cooling_reference_time_constant_h,
            )
            if any(value is None for value in required):
                raise ValueError(
                    "Strict ISO 52016 monthly mode requires the reference parameters "
                    "selected from the applicable Annex-A/national choices"
                )
        return self


class PolishCertificateMonthlySettings(_legacy.PolishCertificateMonthlySettings):
    useful_energy_override_evidence_by_zone: dict[str, str] = Field(default_factory=dict)

    def unverified_override_zones(self) -> list[str]:
        override_zones = set(self.heating_useful_override_kwh_by_zone) | set(
            self.cooling_useful_override_kwh_by_zone
        )
        return sorted(
            zone
            for zone in override_zones
            if not str(self.useful_energy_override_evidence_by_zone.get(zone, "")).strip()
        )


class NormativeSettings(_legacy.NormativeSettings):
    ground: GroundISO13370Settings = Field(default_factory=GroundISO13370Settings)
    heat_recovery: _legacy.HeatRecoverySettings = Field(
        default_factory=_legacy.HeatRecoverySettings
    )
    design_conditions: _legacy.DesignConditionsSettings = Field(
        default_factory=_legacy.DesignConditionsSettings
    )
    polish_certificate: PolishCertificateMonthlySettings = Field(
        default_factory=PolishCertificateMonthlySettings
    )
    legal: _legacy.LegalProvenanceSettings = Field(default_factory=_legacy.LegalProvenanceSettings)
    hourly_iso52016: HourlyISO52016Settings = Field(default_factory=HourlyISO52016Settings)
    moisture_iso52016: MoistureISO52016Settings = Field(default_factory=MoistureISO52016Settings)
    monthly_iso52016: MonthlyISO52016Settings = Field(default_factory=MonthlyISO52016Settings)

    def __getattribute__(self, name: str):
        if name == "legal":
            legal = super().__getattribute__(name)
            if legal.certificate_mode:
                certificate = super().__getattribute__("polish_certificate")
                missing = certificate.unverified_override_zones()
                if missing:
                    raise ValueError(
                        "Formal certificate mode rejects unverified useful-energy override values. "
                        "Provide useful_energy_override_evidence_by_zone for: " + ", ".join(missing)
                    )
            return legal
        return super().__getattribute__(name)


def load_normative_settings(project: BuildingProject) -> NormativeSettings:
    raw = project.metadata.get("normative", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("metadata.normative must be an object")
    return NormativeSettings.model_validate(raw)


GroundElementSettings.model_rebuild()
GroundISO13370Settings.model_rebuild()
NormativeSettings.model_rebuild()
