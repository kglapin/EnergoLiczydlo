"""Internal heat gains and occupancy schedules for ISO 52016-1 hourly method."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from app.schemas.models import (
    BuildingType,
    DHWUsageProfile,
    InternalGainSource,
    Schedule,
    ScheduleType,
)

if TYPE_CHECKING:
    from app.schemas.models import InternalGains


# Normative internal heat gains q_int [W/m2], tabela 26 of the methodology
# (rozporządzenie Dz.U. 2015 poz. 376).  Rows given as q = a*beta + b*(1-beta)
# depend on beta - the monthly share of building usage time (§ 5.5.2).
DEFAULT_USAGE_SHARE_BETA = 0.3  # standard example given in the regulation
_OCCUPANT_HEAT_W = 80.0  # W/person, keeps the occupancy source meaningful
_DEFAULT_OCCUPANCY_DENSITY = 0.03  # person/m2 - ThermalZone default


def _beta_row(a: float, b: float, beta: float) -> float:
    return a * beta + b * (1.0 - beta)


def normative_internal_gain_w_m2(
    building_type: BuildingType | str,
    dhw_usage_profile: DHWUsageProfile | str | None = None,
    beta: float = DEFAULT_USAGE_SHARE_BETA,
) -> float:
    """Normative internal-gain density q_int [W/m2] from tabela 26.

    Residential buildings are disambiguated by the DHW usage profile
    (single-family 6.8, multi-family 7.1 W/m2).  ``beta`` is the share of
    usage time; the regulation's worked example uses 0.3 for offices.
    """
    if not 0.0 <= beta <= 1.0:
        raise ValueError("beta must be between 0 and 1")

    profile = str(getattr(dhw_usage_profile, "value", dhw_usage_profile) or "")
    btype = str(getattr(building_type, "value", building_type))

    if btype == "residential":
        if profile == "residential_multi_family_lump_sum" or profile == (
            "residential_multi_family_individual_metering"
        ):
            return 7.1  # wielorodzinny (lokale mieszkalne)
        return 6.8  # jednorodzinny

    if btype == "office":
        # (20*P1 + 8*(1-P1))*beta + (2*P1 + 1*(1-P1))*(1-beta) at P1 = 0.6
        return _beta_row(20.0 * 0.6 + 8.0 * 0.4, 2.0 * 0.6 + 1.0 * 0.4, beta)
    if btype == "school":
        return _beta_row(12.0, 1.0, beta)
    if btype == "healthcare":
        return 8.0
    if btype == "retail":
        return _beta_row(10.0, 1.0, beta)
    return 6.8  # "other": fall back to the residential single-family value


def normative_internal_gains(
    building_type: BuildingType | str,
    dhw_usage_profile: DHWUsageProfile | str | None = None,
    beta: float = DEFAULT_USAGE_SHARE_BETA,
) -> InternalGains:
    """Default three-source split reproducing the tabela 26 q_int density."""
    # Imported lazily because schemas import this module only while
    # populating omitted project defaults.
    from app.schemas.models import InternalGains, InternalGainSource

    q_int = normative_internal_gain_w_m2(building_type, dhw_usage_profile, beta)
    occupancy_part = min(q_int, _OCCUPANT_HEAT_W * _DEFAULT_OCCUPANCY_DENSITY)
    remainder = q_int - occupancy_part
    return InternalGains(
        occupancy=InternalGainSource(power_density=_OCCUPANT_HEAT_W),
        lighting=InternalGainSource(power_density=round(0.3 * remainder, 2)),
        equipment=InternalGainSource(power_density=round(0.7 * remainder, 2)),
        normative_power_density_w_m2=q_int,
    )


def evaluate_schedule(schedule: Schedule, datetimes: pd.DatetimeIndex) -> np.ndarray:
    """Evaluate a schedule for every hour of a year.

    Parameters
    ----------
    schedule : Schedule
    datetimes : pd.DatetimeIndex
        8760 hourly timestamps.

    Returns
    -------
    np.ndarray
        Hourly profile values in [0, 1] (or arbitrary if constant_value).
    """
    if schedule.type == ScheduleType.CONSTANT:
        value = schedule.constant_value if schedule.constant_value is not None else 1.0
        return np.full(len(datetimes), value)

    if schedule.type == ScheduleType.HOURLY_PROFILE:
        profile = np.empty(len(datetimes), dtype=float)
        for i, dt in enumerate(datetimes):
            hour = dt.hour
            dow = dt.weekday()
            if dow < 5:
                arr = schedule.weekday
            elif dow == 5:
                arr = schedule.saturday or schedule.weekday
            else:
                arr = schedule.sunday or schedule.weekday
            if arr is None:
                raise ValueError(f"Schedule missing profile for weekday {dow}")
            profile[i] = arr[hour]
        return profile

    if schedule.type == ScheduleType.WEEKDAY_WEEKEND:
        profile = np.empty(len(datetimes), dtype=float)
        for i, dt in enumerate(datetimes):
            dow = dt.weekday()
            arr = schedule.weekday if dow < 5 else schedule.sunday or schedule.weekday
            if arr is None:
                raise ValueError("WEEKDAY_WEEKEND schedule requires weekday profile")
            profile[i] = arr[dt.hour]
        return profile

    raise ValueError(f"Unsupported schedule type: {schedule.type}")


def internal_gains(
    occupancy_density: float,
    floor_area: float,
    source: InternalGainSource,
    datetimes: pd.DatetimeIndex,
    per_person: bool = False,
) -> np.ndarray:
    """Compute hourly internal gains [W] for one source.

    Parameters
    ----------
    occupancy_density : float
        Persons per m2 of floor area (used only for occupancy source).
    floor_area : float
        Zone floor area [m2].
    source : InternalGainSource
        Power density and schedule.
    datetimes : pd.DatetimeIndex
        8760 hourly datetimes.
    per_person : bool
        True for the occupancy source, where ``power_density`` is W per
        person; False for lighting/equipment, where ``power_density`` is
        W per m2 of floor area.

    Returns
    -------
    np.ndarray
        Hourly gains [W].
    """
    profile = evaluate_schedule(source.schedule, datetimes)
    if per_person:
        total_power = source.power_density * occupancy_density * floor_area
    else:
        total_power = source.power_density * floor_area
    return np.asarray(total_power * profile, dtype=float)


def total_internal_gains(
    occupancy_density: float,
    floor_area: float,
    gains: InternalGains,  # noqa: F821
    datetimes: pd.DatetimeIndex,
) -> np.ndarray:
    """Sum hourly internal gains [W] from occupancy, lighting and equipment."""
    normative_target = gains.normative_power_density_w_m2
    if normative_target is not None:
        # This marker is set only for the automatically generated normative
        # profile.  Its three source fields remain useful for display/editing,
        # but the regulatory q_int is a floor-area density and must not vary
        # with an unrelated zone occupancy-density input.
        schedules = (gains.occupancy.schedule, gains.lighting.schedule, gains.equipment.schedule)
        profiles = [evaluate_schedule(schedule, datetimes) for schedule in schedules]
        if all(np.allclose(profile, 1.0) for profile in profiles):
            return np.full(len(datetimes), normative_target * floor_area, dtype=float)

    return np.asarray(
        internal_gains(occupancy_density, floor_area, gains.occupancy, datetimes, per_person=True)
        + internal_gains(occupancy_density, floor_area, gains.lighting, datetimes)
        + internal_gains(occupancy_density, floor_area, gains.equipment, datetimes),
        dtype=float,
    )
