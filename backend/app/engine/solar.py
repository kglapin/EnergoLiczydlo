"""Solar gain calculations for PN-EN ISO 52016-1 hourly method.

Computes solar heat gains through transparent elements and absorption by
opaque surfaces based on hourly climate data and surface orientation.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from app.engine.climate import radiation_on_surface
from app.engine.envelope import R_SE_M2K_W
from app.schemas.models import OpaqueElement, TransparentElement


def _direct_surface_irradiance_and_incidence_rad(
    df: pd.DataFrame,
    surface_tilt: float,
    surface_azimuth: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return direct POA irradiance and beam incidence angle [rad]."""
    zenith = np.deg2rad(np.asarray(df["sun_zenith"], dtype=float))
    solar_azimuth = np.deg2rad(np.asarray(df["sun_azimuth"], dtype=float))
    tilt = np.deg2rad(float(surface_tilt))
    azimuth = np.deg2rad(float(surface_azimuth))
    cos_incidence = np.cos(zenith) * np.cos(tilt) + np.sin(zenith) * np.sin(tilt) * np.cos(
        solar_azimuth - azimuth
    )
    front_cosine = np.clip(cos_incidence, 0.0, 1.0)
    direct = np.maximum(np.asarray(df["DNI"], dtype=float), 0.0) * front_cosine
    incidence = np.arccos(front_cosine)
    return direct, incidence


def _incidence_modifier(
    incidence_rad: np.ndarray,
    coefficients: Sequence[float],
) -> np.ndarray:
    """Evaluate an ascending-power incidence-angle polynomial and clamp to 0..1."""
    if not coefficients:
        raise ValueError("Incidence-angle coefficient sequence cannot be empty")
    modifier = np.zeros_like(incidence_rad, dtype=float)
    for power, coefficient in enumerate(coefficients):
        modifier += float(coefficient) * np.power(incidence_rad, power)
    return np.clip(modifier, 0.0, 1.0)


def solar_gains_transparent(
    element: TransparentElement,
    df: pd.DataFrame,
    ground_reflectance: float = 0.2,
    direct_incidence_coefficients: Sequence[float] | None = None,
) -> np.ndarray:
    """Hourly solar heat gain [W] through a transparent element.

    ``direct_incidence_coefficients`` optionally defines a polynomial in beam
    incidence angle [rad], with coefficients ordered from constant term upward.
    The modifier is applied only to direct beam irradiance. Diffuse-sky and
    ground-reflected irradiance remain unchanged, matching the physical split
    used by BESTEST reference implementations.

    Parameters
    ----------
    element : TransparentElement
        Window / skylight with g-value, frame factor and shading factor.
    df : DataFrame
        Climate DataFrame containing solar position and GHI/DNI/DHI.
    ground_reflectance : float
        Ground albedo (default 0.2).
    direct_incidence_coefficients : Sequence[float] | None
        Optional ascending-power polynomial coefficients for the direct-beam
        incidence-angle modifier.

    Returns
    -------
    np.ndarray
        Hourly solar heat gain [W].
    """
    total_irradiance = np.asarray(
        radiation_on_surface(
            df,
            surface_tilt=element.inclination,
            surface_azimuth=element.orientation_azimuth,
            ground_reflectance=ground_reflectance,
        ),
        dtype=float,
    )
    effective_irradiance = total_irradiance
    if direct_incidence_coefficients is not None:
        direct, incidence = _direct_surface_irradiance_and_incidence_rad(
            df,
            element.inclination,
            element.orientation_azimuth,
        )
        diffuse_and_reflected = np.maximum(total_irradiance - direct, 0.0)
        modifier = _incidence_modifier(incidence, direct_incidence_coefficients)
        effective_irradiance = diffuse_and_reflected + direct * modifier

    # Net transparent area = total area * (1 - frame factor)
    net_area = element.area * (1.0 - element.frame_factor)
    # Total energy transmittance including shading
    g_total = element.g_value * element.shading_factor
    return net_area * g_total * effective_irradiance


def solar_absorption_opaque(
    element: OpaqueElement,
    df: pd.DataFrame,
    ground_reflectance: float = 0.2,
) -> np.ndarray:
    """Hourly solar heat gain [W] flowing inward through an opaque element.

    Absorbed solar radiation raises the external surface temperature
    (sol-air effect); the extra inward heat flow through the construction is

        q_in = A * alpha * U * R_se * I_surf

    with R_se the external surface resistance (PN-EN ISO 6946).  For a
    well-insulated wall (U ~ 0.2 W/(m2*K)) only ~0.8 % of the absorbed
    radiation reaches the interior, mostly delayed by the construction mass;
    the 5R1C gain splitting and mass node provide that delay.

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
        Solar heat gain at the interior [W].
    """
    I_surf = radiation_on_surface(
        df,
        surface_tilt=element.inclination,
        surface_azimuth=element.orientation_azimuth,
        ground_reflectance=ground_reflectance,
    )
    return (
        element.area * element.solar_absorptance * element.u_value * R_SE_M2K_W * np.asarray(I_surf)
    )


def total_solar_gains(
    transparent_elements: list[TransparentElement],
    opaque_elements: list[OpaqueElement],
    df: pd.DataFrame,
    ground_reflectance: float = 0.2,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (total_transparent_gains, total_opaque_absorption) in [W]."""
    trans_gains = np.zeros(len(df), dtype=float)
    for t_el in transparent_elements:
        trans_gains += solar_gains_transparent(t_el, df, ground_reflectance)

    opaque_abs = np.zeros(len(df), dtype=float)
    for o_el in opaque_elements:
        adjacent = str(getattr(o_el.adjacent_space_type, "value", o_el.adjacent_space_type))
        if adjacent == "outdoor":
            opaque_abs += solar_absorption_opaque(o_el, df, ground_reflectance)

    return trans_gains, opaque_abs
