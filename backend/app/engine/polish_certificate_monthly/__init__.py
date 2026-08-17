"""Formal monthly certificate wrapper with fail-closed override provenance."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_LEGACY_NAME = "app.engine._legacy_polish_certificate_monthly"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "polish_certificate_monthly.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load legacy monthly certificate from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)


def _unverified_override_zones(settings) -> list[str]:
    override_zones = set(settings.heating_useful_override_kwh_by_zone) | set(
        settings.cooling_useful_override_kwh_by_zone
    )
    evidence = getattr(settings, "useful_energy_override_evidence_by_zone", {}) or {}
    return sorted(
        zone for zone in override_zones if not str(evidence.get(zone, "")).strip()
    )


def calculate_polish_monthly_certificate(project, settings):
    """Calculate the monthly result, rejecting undocumented external overrides."""
    missing = _unverified_override_zones(settings)
    if missing:
        raise ValueError(
            "Monthly useful-energy override requires verified external-calculation "
            "evidence for: " + ", ".join(missing)
        )
    return _legacy.calculate_polish_monthly_certificate(project, settings)


_legacy.calculate_polish_monthly_certificate = calculate_polish_monthly_certificate
