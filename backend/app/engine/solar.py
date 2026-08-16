"""Solar gain calculations for PN-EN ISO 52016-1 hourly method.

Computes solar heat gains through transparent elements and absorption by
opaque surfaces based on hourly climate data and surface orientation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.engine.climate import radiation_on_surface
from app.schemas.models import OpaqueElement, TransparentElement


def solar_gains_transparent(
    element: TransparentElement,
    df: pd.DataFrame,
    ground_reflectance: float = 0.2,
) -> np.ndarray:
    """Hourly solar heat gain [W] through a transparent element.

    Parameters
    ----------
    element : TransparentElement
        Window / skylight with g-value, frame factor and shading factor.
    df : DataFrame
        Climate DataFrame containing solar position and GHI/DNI/DHI.
    ground_reflectance : float
        Ground albedo (default 0.2).

    Returns
    -------
    np.ndarray
        Hourly solar heat gain [W].
    """
    I_surf = radiation_on_surface(
        df,
        surface_tilt=element.inclination,
        surface_azimuth=element.orientation_azimuth,
        ground_reflectance=ground_reflectance,
    )
    # Net transparent area = total area * (1 - frame factor)
    net_area = element.area * (1.0 - element.frame_factor)
    # Total energy transmittance including shading
    g_total = element.g_value * element.shading_factor
    return net_area * g_total * np.asarray(I_surf)


def solar_absorption_opaque(
    element: OpaqueElement,
    df: pd.DataFrame,
    ground_reflectance: float = 0.2,
) -> np.ndarray:
    """Hourly solar heat gain [W] reaching the interior through an opaque element.

    Implements the ISO 52016-1 reduction concept: only the fraction
    ``solar_reduction_factor`` of absorbed radiation is treated as an
    instantaneous internal heat gain; the rest is stored/delayed by the
    construction mass.

    Parameters
    ----------
    element : OpaqueElement
    df : DataFrame
        Climate DataFrame with solar position and irradiance.
    ground_reflectance : float
        Ground albedo.

    Returns
    -------
    np.ndarray
        Effective solar heat gain at the internal air node [W].
    """
    I_surf = radiation_on_surface(
        df,
        surface_tilt=element.inclination,
        surface_azimuth=element.orientation_azimuth,
        ground_reflectance=ground_reflectance,
    )
    return (
        element.area
        * element.solar_absorptance
        * element.solar_reduction_factor
        * np.asarray(I_surf)
    )


def total_solar_gains(
    transparent_elements: list[TransparentElement],
    opaque_elements: list[OpaqueElement],
    df: pd.DataFrame,
    ground_reflectance: float = 0.2,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (total_transparent_gains, total_opaque_absorption) in [W]."""
    trans_gains = np.zeros(len(df), dtype=float)
    for el in transparent_elements:
        trans_gains += solar_gains_transparent(el, df, ground_reflectance)

    opaque_abs = np.zeros(len(df), dtype=float)
    for el in opaque_elements:
        if el.adjacent_space_type.value == "outdoor":
            opaque_abs += solar_absorption_opaque(el, df, ground_reflectance)

    return trans_gains, opaque_abs
