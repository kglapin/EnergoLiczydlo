"""Envelope heat-transfer calculations following PN-EN ISO 52016-1.

This module aggregates opaque and transparent building elements into heat
loss coefficients (H-values) and computes transmission heat flows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.schemas.models import (
    AdjacentSpaceType,
    OpaqueElement,
    ThermalBridgeConfig,
    ThermalZone,
    TransparentElement,
)

# Ground temperature model: deep-ground temperature approximated as
# average annual outdoor temperature + a seasonal sinusoidal term.
# This is a placeholder; proper implementation should use ISO 13370 / 52016-1 Annex.
DEFAULT_GROUND_TEMP_AMPLITUDE = 5.0  # K


def adjacent_temperature(
    element: OpaqueElement,
    T_e: pd.Series | np.ndarray,
    unheated_zone_temperature: pd.Series | np.ndarray | None = None,
) -> np.ndarray:
    """Return the adjacent-space temperature [°C] for an opaque element hour-by-hour."""
    adj = element.adjacent_space_type
    if adj == AdjacentSpaceType.OUTDOOR:
        return np.asarray(T_e, dtype=float)
    if adj == AdjacentSpaceType.GROUND:
        # Simplified ground model: annual mean outdoor temperature
        T_mean = float(np.mean(T_e))
        n = len(np.asarray(T_e))
        hours = np.arange(n)
        return T_mean - DEFAULT_GROUND_TEMP_AMPLITUDE * np.cos(
            2 * np.pi * hours / 8760
        )
    if adj == AdjacentSpaceType.UNHEATED_ZONE:
        if unheated_zone_temperature is None:
            # Approximation: unheated zone = outdoor + 3 K buffer
            return np.asarray(T_e, dtype=float) + 3.0
        return np.asarray(unheated_zone_temperature, dtype=float)
    if adj == AdjacentSpaceType.CONSTANT_TEMPERATURE:
        if element.adjacent_temperature is None:
            raise ValueError(
                f"Element {element.id} has CONSTANT_TEMPERATURE but adjacent_temperature is None"
            )
        return np.full(len(np.asarray(T_e)), element.adjacent_temperature)
    if adj == AdjacentSpaceType.HEATED_ZONE:
        # Internal partition: no heat transfer across zones in simplified model
        return np.zeros(len(np.asarray(T_e)))
    raise ValueError(f"Unknown adjacent_space_type: {adj}")


def compute_opaque_heat_loss(
    element: OpaqueElement,
    T_int: pd.Series | np.ndarray,
    T_e: pd.Series | np.ndarray,
    unheated_zone_temperature: pd.Series | np.ndarray | None = None,
) -> np.ndarray:
    """Hourly transmission heat loss [W] through one opaque element."""
    T_adj = adjacent_temperature(element, T_e, unheated_zone_temperature)
    delta_T = np.asarray(T_int) - T_adj
    return np.asarray(element.area * element.u_value * delta_T, dtype=float)


def compute_transparent_heat_loss(
    element: TransparentElement,
    T_int: pd.Series | np.ndarray,
    T_e: pd.Series | np.ndarray,
) -> np.ndarray:
    """Hourly transmission heat loss [W] through one transparent element."""
    delta_T = np.asarray(T_int) - np.asarray(T_e)
    return np.asarray(element.area * element.u_value * delta_T, dtype=float)


def compute_thermal_bridge_loss(
    bridges: ThermalBridgeConfig,
    zone: ThermalZone,
    T_int: pd.Series | np.ndarray,
    T_e: pd.Series | np.ndarray,
) -> np.ndarray:
    """Hourly heat loss [W] from thermal bridges in a zone.

    Linear bridges: Psi [W/(m*K)] * length [m] * dT.
    Point bridges: Chi [W/K] * count * dT.
    """
    T_int_arr = np.asarray(T_int)
    T_e_arr = np.asarray(T_e)
    dT = T_int_arr - T_e_arr
    loss = np.zeros_like(dT, dtype=float)

    for lb in bridges.linear_bridges:
        if lb.zone_id != zone.id:
            continue
        loss += lb.psi_value * lb.length * dT
    for pb in bridges.point_bridges:
        if pb.zone_id != zone.id:
            continue
        loss += pb.chi_value * pb.count * dT
    return np.asarray(loss, dtype=float)


def total_transmission_coefficient(
    opaque_elements: list[OpaqueElement],
    transparent_elements: list[TransparentElement],
    bridges: ThermalBridgeConfig,
) -> float:
    """Total H_tr [W/K] for the building at design deltaT = 1 K.

    Includes opaque/transparent U*A and thermal bridges.
    """
    h_opaque = sum(el.area * el.u_value for el in opaque_elements)
    h_transparent = sum(el.area * el.u_value for el in transparent_elements)
    h_bridges = sum(
        lb.psi_value * lb.length for lb in bridges.linear_bridges
    ) + sum(pb.chi_value * pb.count for pb in bridges.point_bridges)
    return h_opaque + h_transparent + h_bridges
