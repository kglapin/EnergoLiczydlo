"""Climate compatibility layer using Perez diffuse-sky transposition.

ISO 52010-1 requires a defined conversion of horizontal/direct/diffuse solar
data to an arbitrarily oriented surface. The former runtime explicitly used
Hay-Davies. This layer switches the operational path to Perez and fails closed
when pvlib is unavailable instead of silently falling back to a different sky
model.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_LEGACY_NAME = "app.engine._legacy_climate"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "climate.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load legacy climate module from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)


def radiation_on_surface(
    df,
    surface_tilt: float,
    surface_azimuth: float,
    ground_reflectance: float = 0.2,
):
    """Compute plane-of-array irradiance [W/m²] with Perez transposition."""
    if pvlib is None:
        raise RuntimeError(
            "Perez solar transposition requires pvlib; no alternative sky model "
            "is used in the audited calculation path"
        )
    if "dni_extra" not in df.columns:
        df["dni_extra"] = pvlib.irradiance.get_extra_radiation(df.index)

    zenith = np.asarray(df["sun_zenith"], dtype=float)
    relative_airmass = np.asarray(
        pvlib.atmosphere.get_relative_airmass(zenith),
        dtype=float,
    )
    relative_airmass = np.where(
        np.isfinite(relative_airmass) & (zenith < 90.0),
        relative_airmass,
        0.0,
    )
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        solar_zenith=df["sun_zenith"],
        solar_azimuth=df["sun_azimuth"],
        dni=df["DNI"],
        ghi=df["GHI"],
        dhi=df["DHI"],
        dni_extra=df["dni_extra"],
        airmass=relative_airmass,
        model="perez",
        albedo=ground_reflectance,
    )
    result = poa["poa_global"].astype(float)
    # Guard against model-domain artefacts at night or in malformed weather
    # records. Irradiance cannot be negative.
    return result.fillna(0.0).clip(lower=0.0)


_legacy.radiation_on_surface = radiation_on_surface
