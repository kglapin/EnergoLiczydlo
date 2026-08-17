"""Simple hourly thermal-balance solver: 5R1C network per PN-EN ISO 52016-1 / ISO 13790.

The zone is represented by the standard five-resistance / one-capacitance
network (ISO 13790:2008 Annex C, carried over to PN-EN ISO 52016-1):

- ``H_ve``   supply air node -> air node (ventilation),
- ``H_tr,is`` air node <-> internal-surfaces node (film coefficient 3.45 W/(m2*K)),
- ``H_tr,w`` transparent elements: surfaces node -> outdoor,
- ``H_tr,ms`` surfaces node <-> thermal-mass node (9.1 W/(m2*K) on A_m),
- ``H_tr,em`` mass node -> outdoor through the opaque envelope,
              ``1 / (1/H_tr,op - 1/H_tr,ms)``.

Heat gains are split between the nodes (ISO 13790 C.2):

- ``phi_ia = 0.5 * phi_int``
- ``phi_m  = (A_m / A_t) * (0.5 * phi_int + phi_sol)``
- ``phi_st = (1 - A_m/A_t - H_tr,w / (9.1 * A_t)) * (0.5 * phi_int + phi_sol)``

The three node temperatures (mass, air, surfaces) are solved simultaneously
as a linear system per hour (Crank-Nicolson on the mass node).  Because the
network is linear in the heating/cooling power, the power needed to hold the
air node exactly at a setpoint is obtained in closed form - no iteration.

Extension beyond the plain standard: opaque elements coupled to spaces other
than outdoor air (ground, unheated space, constant temperature) are lumped
into ``H_tr,op`` with an area-weighted driving temperature instead of
``theta_e``; internal partitions between equally conditioned zones transfer
no heat and are excluded.  Transparent elements always couple the surfaces
node to outdoor air, as in the standard.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Surface coupling coefficients, ISO 13790 Annex C (Table C.3).
H_IS_W_M2K = 3.45  # air <-> internal surfaces [W/(m2*K)]
H_MS_W_M2K = 9.1  # mass <-> internal surfaces [W/(m2*K)]

# Default geometry ratios (ISO 13790 Annex C, defaults when no detailed data).
AT_PER_FLOOR_AREA = 4.5  # total internal surface area A_t [-]
AM_PER_FLOOR_AREA = 2.5  # effective mass area A_m [-]

# Internal-heat-capacity classes kappa [kJ/(m2*K)] (ISO 13790 Table 12):
# 80 very light, 110 light, 165 medium, 260 heavy.
KAPPA_VERY_LIGHT_KJ_M2K = 80.0
KAPPA_LIGHT_KJ_M2K = 110.0
KAPPA_MEDIUM_KJ_M2K = 165.0
KAPPA_HEAVY_KJ_M2K = 260.0
DEFAULT_KAPPA_KJ_M2K = KAPPA_MEDIUM_KJ_M2K

SECONDS_PER_HOUR = 3600.0


def opaque_external_conductance(h_opaque: float, h_mass_surface: float) -> float:
    """Return ``H_tr,em`` for the standard 5R1C opaque path [W/K].

    ``h_opaque`` is the complete opaque transmission coefficient ``H_tr,op``
    and ``h_mass_surface`` is ``H_tr,ms``.  The latter is part of the fictive
    5R1C split, so the standard relationship is:

    ``H_tr,em = 1 / (1/H_tr,op - 1/H_tr,ms)``.

    The split is undefined when ``H_tr,op >= H_tr,ms``.  Silently switching to
    a different network in that case would change the physical model, so the
    caller receives an explicit validation error.
    """
    if h_opaque <= 0.0:
        return 0.0
    if h_mass_surface <= 0.0:
        raise ValueError("H_tr,ms must be positive when opaque transmission exists")
    denominator = 1.0 / h_opaque - 1.0 / h_mass_surface
    if denominator <= 0.0:
        raise ValueError(
            "5R1C opaque split requires H_tr,op < H_tr,ms; "
            f"got H_tr,op={h_opaque:g}, H_tr,ms={h_mass_surface:g}"
        )
    return 1.0 / denominator


@dataclass(frozen=True)
class ZoneThermalProperties:
    """Geometric and capacity properties of one thermal zone (5R1C inputs)."""

    floor_area: float  # conditioned floor area [m2]
    area_total_internal: float  # A_t, internal surfaces [m2]
    area_mass: float  # A_m, effective mass area [m2]
    capacity: float  # C_m [J/K]

    @property
    def h_tr_is(self) -> float:
        return H_IS_W_M2K * self.area_total_internal

    @property
    def h_tr_ms(self) -> float:
        return H_MS_W_M2K * self.area_mass


def zone_thermal_properties(
    floor_area: float,
    kappa_kj_m2k: float = DEFAULT_KAPPA_KJ_M2K,
    at_per_floor_area: float = AT_PER_FLOOR_AREA,
    am_per_floor_area: float = AM_PER_FLOOR_AREA,
) -> ZoneThermalProperties:
    """Build the 5R1C thermal properties of a zone.

    C_m = kappa * A_m per ISO 13790; the ratios A_t = 4.5*Af and A_m = 2.5*Af
    are the standard defaults when the internal geometry is not detailed.
    """
    if floor_area <= 0:
        raise ValueError("floor_area must be positive")
    area_total = at_per_floor_area * floor_area
    area_mass = am_per_floor_area * floor_area
    capacity = kappa_kj_m2k * 1000.0 * area_mass  # kJ/(m2*K) * m2 -> J/K
    return ZoneThermalProperties(
        floor_area=floor_area,
        area_total_internal=area_total,
        area_mass=area_mass,
        capacity=capacity,
    )


def thermal_capacity(floor_area: float, kappa_kj_m2k: float = DEFAULT_KAPPA_KJ_M2K) -> float:
    """Total thermal capacity C_m [Wh/K] of the zone (legacy helper)."""
    return zone_thermal_properties(floor_area, kappa_kj_m2k).capacity / SECONDS_PER_HOUR


@dataclass
class TransmissionNetwork:
    """Grouped transmission conductances of a zone with their driving temperatures.

    ``h_opaque`` is the total U*A of opaque elements (plus thermal bridges),
    driven by ``t_opaque`` - the U*A-weighted temperature of the adjacent
    spaces (outdoor, ground, unheated, constant-temperature).  It couples the
    mass node to the environment through H_tr,em.

    ``h_surface`` / ``t_surface`` describe additional conductances acting on
    the internal-surfaces node: transparent elements and any other element
    that must not be lumped into the opaque path.
    """

    h_opaque: float = 0.0
    t_opaque: np.ndarray | None = None
    h_surface: list[float] = field(default_factory=list)
    t_surface: list[np.ndarray] = field(default_factory=list)

    def add_opaque(self, conductance: float, driving_temperature: np.ndarray) -> None:
        """Merge an opaque conductance into the U*A-weighted average drive.

        Implemented as an incremental weighted mean of the driving
        temperatures, so the merged drive is exact when all inputs are added
        through this method.
        """
        if conductance <= 0:
            return
        total_new = self.h_opaque + conductance
        if self.h_opaque == 0.0 or self.t_opaque is None:
            self.t_opaque = np.asarray(driving_temperature, dtype=float).copy()
        else:
            self.t_opaque = (
                self.t_opaque * self.h_opaque
                + np.asarray(driving_temperature, dtype=float) * conductance
            ) / total_new
        self.h_opaque = total_new

    def add_surface(self, conductance: float, driving_temperature: np.ndarray) -> None:
        if conductance <= 0:
            return
        self.h_surface.append(float(conductance))
        self.t_surface.append(np.asarray(driving_temperature, dtype=float))

    @property
    def h_total(self) -> float:
        """Total transmission coefficient [W/K] (reporting/consistency checks)."""
        return self.h_opaque + sum(self.h_surface)


@dataclass
class ZoneSolution:
    """Hourly results of the 5R1C zone simulation."""

    t_air: np.ndarray  # indoor air temperature [degC]
    t_operative: np.ndarray  # operative temperature 0.3*t_air + 0.7*t_s [degC]
    t_mass: np.ndarray  # mass node temperature (instantaneous) [degC]
    t_mass_mean: np.ndarray  # mass node temperature averaged over each hour [degC]
    t_surface: np.ndarray  # central internal-surface node temperature [degC]
    q_heating: np.ndarray  # heating need [Wh] per hour (>= 0)
    q_cooling: np.ndarray  # cooling need [Wh] per hour (>= 0)


def solve_zone_5r1c(
    *,
    network: TransmissionNetwork,
    h_ve: float | np.ndarray,
    t_e: np.ndarray,
    phi_int: np.ndarray,
    phi_sol: np.ndarray,
    properties: ZoneThermalProperties,
    t_set_heating: float | None,
    t_set_cooling: float | None,
    t_supply: np.ndarray | None = None,
) -> ZoneSolution:
    """Simulate one zone over the climate series with the 5R1C network.

    Parameters
    ----------
    network : TransmissionNetwork
        Transmission conductances and driving temperatures (8760 h).
    h_ve : float or np.ndarray
        Ventilation heat transfer coefficient [W/K], either constant or one
        value per simulation hour.
    t_e : np.ndarray
        Outdoor air temperature [degC]; also the supply temperature unless
        ``t_supply`` is given.
    phi_int, phi_sol : np.ndarray
        Internal and solar heat gains [W].
    properties : ZoneThermalProperties
        Zone capacity and coupling areas.
    t_set_heating, t_set_cooling : float | None
        Air-temperature setpoints [degC]; ``None`` disables the service.
    t_supply : np.ndarray, optional
        Supply air temperature [degC] (defaults to ``t_e``).

    Returns
    -------
    ZoneSolution with hourly arrays.
    """
    t_e = np.asarray(t_e, dtype=float)
    t_sup = t_e if t_supply is None else np.asarray(t_supply, dtype=float)
    phi_int = np.asarray(phi_int, dtype=float)
    phi_sol = np.asarray(phi_sol, dtype=float)
    n = len(t_e)
    for name, values in (
        ("t_supply", t_sup),
        ("phi_int", phi_int),
        ("phi_sol", phi_sol),
    ):
        if values.shape != (n,):
            raise ValueError(f"{name} must contain one value per simulation hour")
        if not np.isfinite(values).all():
            raise ValueError(f"{name} must contain finite values")
    h_ve_input = np.asarray(h_ve, dtype=float)
    if h_ve_input.ndim == 0:
        h_ve_hourly = np.full(n, float(h_ve_input), dtype=float)
    elif h_ve_input.shape == (n,):
        h_ve_hourly = h_ve_input
    else:
        raise ValueError("h_ve must be a scalar or contain one value per hour")
    if not np.isfinite(h_ve_hourly).all() or np.any(h_ve_hourly < 0.0):
        raise ValueError("h_ve must contain finite non-negative values")

    h_is = properties.h_tr_is
    h_ms = properties.h_tr_ms
    h_op = network.h_opaque
    h_em = opaque_external_conductance(h_op, h_ms)
    h_surface_total = sum(network.h_surface)
    t_opaque = network.t_opaque if network.t_opaque is not None else np.zeros(n, dtype=float)

    # Gain splitting (ISO 13790 C.2).  The transparent (surface-coupled)
    # conductance plays the role of H_tr,w in the splitting factor.
    frac_mass = properties.area_mass / properties.area_total_internal
    frac_surface = max(
        0.0,
        1.0 - frac_mass - h_surface_total / (H_MS_W_M2K * properties.area_total_internal),
    )
    phi_ia = 0.5 * phi_int
    phi_rest = 0.5 * phi_int + phi_sol
    phi_m = frac_mass * phi_rest
    phi_st = frac_surface * phi_rest

    # Linear system for the hourly node temperatures x = [Tm_t, theta_air,
    # theta_s] (Crank-Nicolson on the mass node, simultaneous solve):
    #
    #  (A) [Cm + dt/2*(Hms+Hem)]*Tm_t           - dt*Hms*theta_s = b1
    #  (B)                        (His+Hve)*theta_i - His*theta_s = b2 + phi_HC
    #  (C) -Hms/2*Tm_t            - His*theta_i + (His+Hms+Hk)*theta_s = b3
    dt = SECONDS_PER_HOUR
    a11 = properties.capacity + 0.5 * dt * (h_ms + h_em)
    a11_rhs = properties.capacity - 0.5 * dt * (h_ms + h_em)
    a33 = h_is + h_ms + h_surface_total

    t_air = np.empty(n, dtype=float)
    t_op = np.empty(n, dtype=float)
    t_mass = np.empty(n, dtype=float)
    t_mass_mean = np.empty(n, dtype=float)
    t_surface = np.empty(n, dtype=float)
    q_h = np.zeros(n, dtype=float)
    q_c = np.zeros(n, dtype=float)

    # Initial mass temperature: setpoint in conditioned zones, otherwise the
    # first outdoor temperature (free-floating start).
    t_m_prev = float(t_set_heating) if t_set_heating is not None else float(t_e[0])

    for t in range(n):
        t_m_previous = t_m_prev
        h_ve_t = h_ve_hourly[t]
        matrix = np.array(
            [
                [a11, 0.0, -dt * h_ms],
                [0.0, h_is + h_ve_t, -h_is],
                [-0.5 * h_ms, -h_is, a33],
            ]
        )
        # Response of theta_air to unit heating power (network is linear).
        unit = np.linalg.solve(matrix, np.array([0.0, 1.0, 0.0]))
        d_theta_air_per_w = unit[1]
        if d_theta_air_per_w <= 0:
            raise ValueError("5R1C network is singular: air node insensitive to heating")

        surface_drive = sum(
            h * ts[t] for h, ts in zip(network.h_surface, network.t_surface, strict=True)
        )
        rhs = np.array(
            [
                a11_rhs * t_m_prev + dt * (phi_m[t] + h_em * t_opaque[t]),
                h_ve_t * t_sup[t] + phi_ia[t],
                phi_st[t] + surface_drive + 0.5 * h_ms * t_m_prev,
            ]
        )
        x0 = np.linalg.solve(matrix, rhs)
        theta_air_free = x0[1]

        phi_hc = 0.0
        # Epsilon suppresses numerical noise when the free temperature sits
        # exactly at a setpoint (linear-solve residuals ~1e-11 K).
        eps = 1e-9
        if t_set_heating is not None and theta_air_free < t_set_heating - eps:
            phi_hc = (t_set_heating - theta_air_free) / d_theta_air_per_w
            q_h[t] = phi_hc * 1.0  # dt = 1 h -> Wh
        elif t_set_cooling is not None and theta_air_free > t_set_cooling + eps:
            phi_hc = (t_set_cooling - theta_air_free) / d_theta_air_per_w
            q_c[t] = -phi_hc * 1.0  # Wh

        x = x0 if phi_hc == 0.0 else x0 + phi_hc * unit
        t_mass[t] = x[0]
        t_mass_mean[t] = 0.5 * (t_m_previous + x[0])
        t_surface[t] = x[2]
        t_air[t] = x[1]
        t_op[t] = 0.3 * x[1] + 0.7 * x[2]
        t_m_prev = float(x[0])

    return ZoneSolution(
        t_air=t_air,
        t_operative=t_op,
        t_mass=t_mass,
        t_mass_mean=t_mass_mean,
        t_surface=t_surface,
        q_heating=q_h,
        q_cooling=q_c,
    )
