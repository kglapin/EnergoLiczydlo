"""Extended normative settings for the repaired calculation runtime.

This package keeps backwards compatibility with the historical
``normative_models.py`` module while adding explicit controls for the detailed
hourly construction-node calculation and evidence for externally supplied
monthly useful-energy values.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from pydantic import BaseModel, Field

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


class HourlyISO52016Settings(BaseModel):
    """Controls the detailed per-construction hourly nodal calculation.

    Direct low-level core calls keep this solver opt-in for regression and
    legacy comparisons. The public audited calculation path selects it by
    default unless a project explicitly sets ``enabled``. ``certificate_mode``
    is stricter and requires explicit five-node construction data.
    """

    enabled: bool = False
    certificate_mode: bool = False
    max_warmup_cycles: int = Field(20, ge=2, le=100)
    warmup_tolerance_k: float = Field(0.01, gt=0.0, le=1.0)


class PolishCertificateMonthlySettings(_legacy.PolishCertificateMonthlySettings):
    """Monthly certificate inputs plus evidence for external overrides."""

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
    ground: _legacy.GroundISO13370Settings = Field(
        default_factory=_legacy.GroundISO13370Settings
    )
    heat_recovery: _legacy.HeatRecoverySettings = Field(
        default_factory=_legacy.HeatRecoverySettings
    )
    design_conditions: _legacy.DesignConditionsSettings = Field(
        default_factory=_legacy.DesignConditionsSettings
    )
    polish_certificate: PolishCertificateMonthlySettings = Field(
        default_factory=PolishCertificateMonthlySettings
    )
    legal: _legacy.LegalProvenanceSettings = Field(
        default_factory=_legacy.LegalProvenanceSettings
    )
    hourly_iso52016: HourlyISO52016Settings = Field(
        default_factory=HourlyISO52016Settings
    )

    def __getattribute__(self, name: str):
        if name == "legal":
            legal = super().__getattribute__(name)
            if legal.certificate_mode:
                certificate = super().__getattribute__("polish_certificate")
                missing = certificate.unverified_override_zones()
                if missing:
                    raise ValueError(
                        "Formal certificate mode rejects unverified useful-energy "
                        "override values. Provide "
                        "useful_energy_override_evidence_by_zone for: "
                        + ", ".join(missing)
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


NormativeSettings.model_rebuild()
