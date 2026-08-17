"""Envelope heat-transfer calculations following PN-EN ISO 52016-1.

This module aggregates opaque and transparent building elements into heat
loss coefficients (H-values) and computes transmission heat flows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.engine.thermal_balance import TransmissionNetwork
from app.schemas.models import (
    AdjacentSpaceType,
    OpaqueElement,
    ThermalBridgeConfig,
    ThermalZone,
    TransparentElement,
)

# Legacy ground fallback retained for backwards compatibility only. The
# audited certificate-grade path attaches an element-specific ISO 13370
# periodic profile before this module is entered.
DEFAULT_GROUND_TEMP_AMPLITUDE = 5.0  # K
GROUND_TEMP_LAG_HOURS = 1460.0  # ~2 months

# External surface heat transfer resistance for horizontal / upward heat
# flow, PN-EN ISO 6946 Table A.1. Used to convert absorbed solar radiation
# on opaque surfaces into an extra inward heat flow (sol-air equivalent).
R_SE_M2K_W = 0.04


def ground_temperature(T_e: pd.Series | np.ndarray) -> np.ndarray:
    """Return the documented legacy ground-temperature fallback [°C]."""
    T_mean = float(np.mean(T_e))
    n = len(np.asarray(T_e))
    hours = np.arange(n)
    return T_mean - DEFAULT_GROUND_TEMP_AMPLITUDE * np.cos(
        2 * np.pi * (hours - GROUND_TEMP_LAG_HOURS) / 8760
    )


def adjacent_temperature(
    element: OpaqueElement,
    T_e: pd.Series | np.ndarray,
    unheated_zone_temperature: pd.Series | np.ndarray | None = None,
    T_int: pd.Series | np.ndarray | None = None,
) -> np.ndarray:
    """Return the adjacent-space temperature [°C] for an opaque element hour-by-hour."""
    adj = element.adjacent_space_type
    if adj == AdjacentSpaceType.OUTDOOR:
        return np.asarray(T_e, dtype=float)
    if adj == AdjacentSpaceType.GROUND:
        prepared = getattr(element, "_ground_temperature_profile", None)
        if prepared is not None:
            profile = np.asarray(prepared, dtype=float)
            if profile.shape != np.asarray(T_e).shape:
                raise ValueError(
                    f"Prepared ground profile for {element.id} does not match climate length"
                )
            return profile
        return ground_temperature(T_e)
    if adj == AdjacentSpaceType.UNHEATED_ZONE:
        if unheated_zone_temperature is None:
            # Approximation per EN ISO 13790 Annex G style buffer: the
            # unheated space floats close to outdoor air plus a few kelvin
            # from transmission through the heated envelope.
            return np.asarray(T_e, dtype=float) + 3.0
        return np.asarray(unheated_zone_temperature, dtype=float)
    if adj == AdjacentSpaceType.CONSTANT_TEMPERATURE:
        if element.adjacent_temperature is None:
            raise ValueError(
                f"Element {element.id} has CONSTANT_TEMPERATURE but adjacent_temperature is None"
            )
        return np.full(len(np.asarray(T_e)), element.adjacent_temperature)
    if adj == AdjacentSpaceType.HEATED_ZONE:
        # Internal partition between conditioned spaces: both sides share the
        # indoor temperature, so there is no net heat transfer (dT = 0).
        if T_int is None:
            raise ValueError(
                f"Element {element.id} has HEATED_ZONE adjacent space; "
                "T_int is required to evaluate the adjacent temperature"
            )
        return np.asarray(T_int, dtype=float)
    raise ValueError(f"Unknown adjacent_space_type: {adj}")


def compute_opaque_heat_loss(
    element: OpaqueElement,
    T_int: pd.Series | np.ndarray,
    T_e: pd.Series | np.ndarray,
    unheated_zone_temperature: pd.Series | np.ndarray | None = None,
) -> np.ndarray:
    """Hourly transmission heat loss [W] through one opaque element."""
    T_adj = adjacent_temperature(
        element, T_e, unheated_zone_temperature, T_int=np.asarray(T_int)
    )
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
    zone_id: str | None = None,
) -> float:
    """Total H_tr [W/K] for a zone (or the whole building) at design deltaT = 1 K.

    Includes opaque/transparent U*A and thermal bridges. When ``zone_id`` is
    given, only bridges assigned to that zone are included; when None, all
    bridges are counted (building-level total).

    Note: this is the aggregate coefficient used for reporting. Elements
    adjacent to other heated zones contribute no net transfer and are excluded.
    """
    network = zone_transmission_network(
        opaque_elements, transparent_elements, bridges, None, zone_id
    )
    return network.h_total


def zone_transmission_network(
    opaque_elements: list[OpaqueElement],
    transparent_elements: list[TransparentElement],
    bridges: ThermalBridgeConfig,
    T_e: pd.Series | np.ndarray | None,
    zone_id: str | None = None,
    unheated_zone_temperature: pd.Series | np.ndarray | None = None,
) -> TransmissionNetwork:
    """Build the 5R1C transmission network of a zone.

    Opaque elements (including thermal bridges, which act towards outdoor
    air) are lumped into ``h_opaque`` with a U*A-weighted driving temperature
    built from each element's adjacent-space temperature. Transparent
    elements couple the internal-surfaces node directly to outdoor air.
    Elements adjacent to another heated zone are excluded: with both sides at
    the same solved temperature they transfer no net heat.

    ``T_e`` may be None for aggregate non-simulated use; the driving
    temperatures are then placeholders and only the conductances are valid.
    """
    network = TransmissionNetwork()
    placeholder = np.zeros(1)

    def _driving(element: OpaqueElement) -> np.ndarray:
        if T_e is None:
            return placeholder
        return adjacent_temperature(
            element, T_e, unheated_zone_temperature, T_int=None
        )

    for el in opaque_elements:
        if zone_id is not None and el.zone_id != zone_id:
            continue
        conductance = el.area * el.u_value
        if el.adjacent_space_type == AdjacentSpaceType.HEATED_ZONE:
            continue
        network.add_opaque(conductance, _driving(el))

    bridge_conductance = 0.0
    for lb in bridges.linear_bridges:
        if zone_id is None or lb.zone_id == zone_id:
            bridge_conductance += lb.psi_value * lb.length
    for pb in bridges.point_bridges:
        if zone_id is None or pb.zone_id == zone_id:
            bridge_conductance += pb.chi_value * pb.count
    if bridge_conductance > 0.0:
        drive = placeholder if T_e is None else np.asarray(T_e, dtype=float)
        network.add_opaque(bridge_conductance, drive)

    for t_el in transparent_elements:
        if zone_id is not None and t_el.zone_id != zone_id:
            continue
        conductance = t_el.area * t_el.u_value
        drive = placeholder if T_e is None else np.asarray(T_e, dtype=float)
        network.add_surface(conductance, drive)

    return network
