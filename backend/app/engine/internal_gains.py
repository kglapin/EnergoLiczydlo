"""Internal heat gains and occupancy schedules for ISO 52016-1 hourly method."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from app.schemas.models import InternalGainSource, Schedule, ScheduleType

if TYPE_CHECKING:
    from app.schemas.models import InternalGains


HOURS_IN_YEAR = 8760


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
        return np.full(HOURS_IN_YEAR, value)

    if schedule.type == ScheduleType.HOURLY_PROFILE:
        profile = np.empty(HOURS_IN_YEAR, dtype=float)
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
        profile = np.empty(HOURS_IN_YEAR, dtype=float)
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
    return np.asarray(
        internal_gains(occupancy_density, floor_area, gains.occupancy, datetimes,
                       per_person=True)
        + internal_gains(occupancy_density, floor_area, gains.lighting, datetimes)
        + internal_gains(occupancy_density, floor_area, gains.equipment, datetimes),
        dtype=float,
    )
