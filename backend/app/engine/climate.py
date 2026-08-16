"""Climate data handling: load TMY/EPW files and compute solar geometry.

Implements helpers required by PN-EN ISO 52010-1 / 52016-1 hourly calculations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pvlib

# Approximate physical constants
AIR_DENSITY_KG_M3 = 1.2  # kg/m3
AIR_SPECIFIC_HEAT_J_KGK = 1005  # J/(kg*K)


def load_epw(path: str | Path) -> pd.DataFrame:
    """Load an EnergyPlus Weather (EPW) file into a pandas DataFrame.

    Returns a DataFrame indexed by datetime with the standard EPW columns,
    plus derived columns for the solar position and radiation components.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"EPW file not found: {path}")

    df, meta = pvlib.iotools.read_epw(str(path), coerce_year=2023)
    # Ensure a clean hourly index (pvlib returns a DatetimeIndex)
    df.index = pd.date_range(
        start="2023-01-01 00:00:00", periods=len(df), freq="h", tz=df.index.tz
    )

    # Standard EPW column names used by pvlib:
    # temp_air, temp_dew, relative_humidity, atmospheric_pressure,
    # ghi, dni, dhi, wind_speed, wind_direction, ...
    df = df.rename(
        columns={
            "temp_air": "T_e",
            "temp_dew": "T_dew",
            "relative_humidity": "RH",
            "atmospheric_pressure": "P_atm",
            "ghi": "GHI",
            "dni": "DNI",
            "dhi": "DHI",
            "wind_speed": "v_wind",
            "wind_direction": "dir_wind",
            "total_sky_cover": "sky_cover",
        }
    )

    # Add solar position from EPW metadata
    solar_pos = pvlib.solarposition.get_solarposition(
        time=df.index,
        latitude=meta["latitude"],
        longitude=meta["longitude"],
        altitude=meta["altitude"],
    )
    df["sun_zenith"] = solar_pos["apparent_zenith"]
    df["sun_azimuth"] = solar_pos["azimuth"]

    return df


def annual_hourly_index(year: int = 2023) -> pd.DatetimeIndex:
    """Return a standard 8760-hour index for a non-leap year."""
    return pd.date_range(start=f"{year}-01-01 00:00:00", periods=8760, freq="h")


def radiation_on_surface(
    df: pd.DataFrame,
    surface_tilt: float,
    surface_azimuth: float,
    ground_reflectance: float = 0.2,
) -> pd.Series:
    """Compute total solar irradiance [W/m2] on a tilted surface.

    Parameters
    ----------
    df : DataFrame
        Must contain columns 'GHI', 'DNI', 'DHI', 'sun_zenith', 'sun_azimuth'.
    surface_tilt : float
        Tilt from horizontal [deg]. 0 = horizontal, 90 = vertical.
    surface_azimuth : float
        Surface azimuth [deg]. 0 = North, 90 = East, 180 = South, 270 = West.
    ground_reflectance : float
        Albedo of the ground [-].

    Returns
    -------
    pd.Series
        Total irradiance on the surface [W/m2].
    """
    # Ensure extraterrestrial irradiance is available
    if "dni_extra" not in df.columns:
        df["dni_extra"] = pvlib.irradiance.get_extra_radiation(df.index)

    # Use the Hay-Davies transposition model
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        solar_zenith=df["sun_zenith"],
        solar_azimuth=df["sun_azimuth"],
        dni=df["DNI"],
        ghi=df["GHI"],
        dhi=df["DHI"],
        dni_extra=df["dni_extra"],
        model="haydavies",
        albedo=ground_reflectance,
    )
    return poa["poa_global"]


def make_synthetic_year(
    *,
    T_e: float | np.ndarray = 10.0,
    GHI: float | np.ndarray = 0.0,
    DNI: float | np.ndarray = 0.0,
    DHI: float | np.ndarray = 0.0,
    v_wind: float | np.ndarray = 1.0,
    RH: float | np.ndarray = 50.0,
    latitude: float = 52.2297,
    longitude: float = 21.0122,
    elevation: float = 110.0,
    year: int = 2023,
) -> pd.DataFrame:
    """Create a synthetic 8760-hour climate DataFrame for unit tests.

    All scalar inputs are broadcast to 8760 values.
    """
    index = annual_hourly_index(year)
    n = len(index)

    def _to_array(x: float | np.ndarray) -> np.ndarray:
        if isinstance(x, (int, float)):
            return np.full(n, x, dtype=float)
        arr = np.asarray(x, dtype=float)
        if arr.shape != (n,):
            raise ValueError("Array input must have length 8760")
        return arr

    data: dict[str, Any] = {
        "T_e": _to_array(T_e),
        "T_dew": _to_array(T_e) - 5.0,
        "RH": _to_array(RH),
        "P_atm": np.full(n, 101325.0),
        "GHI": _to_array(GHI),
        "DNI": _to_array(DNI),
        "DHI": _to_array(DHI),
        "v_wind": _to_array(v_wind),
        "dir_wind": np.zeros(n),
        "sky_cover": np.zeros(n),
        "latitude": np.full(n, latitude),
        "longitude": np.full(n, longitude),
        "elevation": np.full(n, elevation),
    }
    df = pd.DataFrame(data, index=index)
    solar_pos = pvlib.solarposition.get_solarposition(
        time=index, latitude=latitude, longitude=longitude, altitude=elevation
    )
    df["sun_zenith"] = solar_pos["apparent_zenith"]
    df["sun_azimuth"] = solar_pos["azimuth"]
    # Physical realism: no solar radiation while the sun is below the horizon.
    # Without this, a constant DNI broadcast at night produces spurious direct
    # irradiance on vertical surfaces (pvlib does not clip the beam projection
    # for a sun below the horizon).
    night = df["sun_zenith"] >= 90.0
    df.loc[night, ["GHI", "DNI", "DHI"]] = 0.0
    return df
