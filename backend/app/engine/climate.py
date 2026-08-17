"""Climate data handling: load TMY/EPW files and compute solar geometry.

Implements helpers required by PN-EN ISO 52010-1 / 52016-1 hourly calculations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from io import StringIO
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import pvlib
except ModuleNotFoundError:  # pragma: no cover - exercised in WASIX deployment
    pvlib = None

# Approximate physical constants
AIR_DENSITY_KG_M3 = 1.2  # kg/m3
AIR_SPECIFIC_HEAT_J_KGK = 1005  # J/(kg*K)
EARTH_RADIUS_KM = 6371.0088

_EPW_DATA_COLUMNS = [
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "data_source_unct",
    "temp_air",
    "temp_dew",
    "relative_humidity",
    "atmospheric_pressure",
    "etr",
    "etrn",
    "ghi_infrared",
    "ghi",
    "dni",
    "dhi",
    "global_hor_illum",
    "direct_normal_illum",
    "diffuse_horizontal_illum",
    "zenith_luminance",
    "wind_direction",
    "wind_speed",
    "total_sky_cover",
    "opaque_sky_cover",
    "visibility",
    "ceiling_height",
    "present_weather_observation",
    "present_weather_codes",
    "precipitable_water",
    "aerosol_optical_depth",
    "snow_depth",
    "days_since_last_snowfall",
    "albedo",
    "liquid_precipitation_depth",
    "liquid_precipitation_quantity",
]


def _load_epw_legacy_width(
    path: Path, coerce_year: int | None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read older 32-column EPW files accepted by the EPW specification.

    Some published BESTEST weather files omit the final optional liquid-
    precipitation fields.  Recent pvlib versions correctly reject those
    files because they declare the modern 35-column layout.  The omitted
    fields are not used by this engine, so they are padded as missing values
    while all thermal and solar columns retain their documented positions.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 9:
        raise ValueError(f"EPW file has no hourly data rows: {path}")
    row_widths = {len(line.split(",")) for line in lines[8:] if line.strip()}
    if len(row_widths) != 1 or row_widths.pop() not in {32, 35}:
        raise ValueError(
            "EPW fallback accepts a consistently 32- or 35-column file; "
            f"got row widths {sorted(row_widths)}"
        )
    header = ["loc", "city", "state-prov", "country", "data_type", "WMO_code",
              "latitude", "longitude", "TZ", "altitude"]
    meta: dict[str, Any] = dict(zip(header, lines[0].split(","), strict=False))
    meta["altitude"] = float(meta["altitude"])
    meta["latitude"] = float(meta["latitude"])
    meta["longitude"] = float(meta["longitude"])
    meta["TZ"] = float(meta["TZ"])
    width = len(lines[8].split(","))
    data = pd.read_csv(StringIO("\n".join(lines[8:])), header=None, names=_EPW_DATA_COLUMNS[:width])
    for column in _EPW_DATA_COLUMNS[width:]:
        data[column] = np.nan
    if coerce_year is not None:
        data["year"] = coerce_year
    dts = data[["month", "day"]].astype(str).apply(lambda x: x.str.zfill(2))
    hrs = (data["hour"] - 1).astype(str).str.zfill(2)
    dtscat = data["year"].astype(str) + dts["month"] + dts["day"] + hrs
    index = pd.to_datetime(dtscat, format="%Y%m%d%H")
    data.index = index.dt.tz_localize(int(meta["TZ"] * 3600))
    return data, meta


def _solar_position_approximation(
    index: pd.DatetimeIndex,
    latitude: float,
    longitude: float,
) -> pd.DataFrame:
    """Return approximate solar position without SciPy/pvlib.

    This is a deployment fallback for WASIX, where the SciPy wheel required by
    pvlib is not available.  The NOAA/Spencer-style equations are sufficient
    for the hourly POA radiation used by the application; the normal local
    runtime continues to use pvlib's implementation.
    """
    n = len(index)
    day = index.dayofyear.to_numpy(dtype=float)
    local_hour = (
        index.hour.to_numpy(dtype=float)
        + index.minute.to_numpy(dtype=float) / 60.0
        + index.second.to_numpy(dtype=float) / 3600.0
    )
    gamma = 2.0 * np.pi / 365.0 * (day - 1.0 + (local_hour - 12.0) / 24.0)
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * np.cos(gamma)
        - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2.0 * gamma)
        - 0.040849 * np.sin(2.0 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2.0 * gamma)
        + 0.000907 * np.sin(2.0 * gamma)
        - 0.002697 * np.cos(3.0 * gamma)
        + 0.001480 * np.sin(3.0 * gamma)
    )
    timezone_hours = 0.0
    if index.tz is not None and n:
        offset = index[0].utcoffset()
        timezone_hours = 0.0 if offset is None else offset.total_seconds() / 3600.0
    true_solar_minutes = (
        local_hour * 60.0
        + equation_of_time
        + 4.0 * longitude
        - 60.0 * timezone_hours
    )
    hour_angle = np.radians(true_solar_minutes / 4.0 - 180.0)
    latitude_rad = np.radians(latitude)
    cos_zenith = (
        np.sin(latitude_rad) * np.sin(declination)
        + np.cos(latitude_rad) * np.cos(declination) * np.cos(hour_angle)
    )
    cos_zenith = np.clip(cos_zenith, -1.0, 1.0)
    zenith = np.degrees(np.arccos(cos_zenith))
    azimuth = np.degrees(
        np.arctan2(
            np.sin(hour_angle),
            np.cos(hour_angle) * np.sin(latitude_rad)
            - np.tan(declination) * np.cos(latitude_rad),
        )
    ) + 180.0
    return pd.DataFrame(
        {"apparent_zenith": zenith, "azimuth": np.mod(azimuth, 360.0)},
        index=index,
    )


def _extra_irradiance(index: pd.DatetimeIndex) -> np.ndarray:
    """Approximate extraterrestrial normal irradiance [W/m²]."""
    day = index.dayofyear.to_numpy(dtype=float)
    return np.asarray(1367.0 * (1.0 + 0.033 * np.cos(2.0 * np.pi * day / 365.0)))


def _hay_davies_fallback(
    df: pd.DataFrame,
    surface_tilt: float,
    surface_azimuth: float,
    ground_reflectance: float,
) -> pd.Series:
    """Compute Hay–Davies POA irradiance using only NumPy/Pandas."""
    zenith = np.radians(np.asarray(df["sun_zenith"], dtype=float))
    sun_azimuth = np.radians(np.asarray(df["sun_azimuth"], dtype=float))
    tilt = radians(surface_tilt)
    azimuth = radians(surface_azimuth)
    cos_zenith = np.cos(zenith)
    cos_incidence = (
        cos_zenith * cos(tilt)
        + np.sin(zenith) * sin(tilt) * np.cos(sun_azimuth - azimuth)
    )
    beam = np.asarray(df["DNI"], dtype=float) * np.maximum(cos_incidence, 0.0)
    dhi = np.maximum(np.asarray(df["DHI"], dtype=float), 0.0)
    ghi = np.maximum(np.asarray(df["GHI"], dtype=float), 0.0)
    dni = np.maximum(np.asarray(df["DNI"], dtype=float), 0.0)
    dni_extra = _extra_irradiance(df.index)
    anisotropy = np.clip(dni / np.maximum(dni_extra, 1.0), 0.0, 1.0)
    rb = np.divide(
        np.maximum(cos_incidence, 0.0),
        np.maximum(cos_zenith, 1.0e-6),
        out=np.zeros_like(cos_incidence),
        where=cos_zenith > 0.0,
    )
    diffuse = dhi * (
        anisotropy * rb + (1.0 - anisotropy) * (1.0 + cos(tilt)) / 2.0
    )
    reflected = ghi * ground_reflectance * (1.0 - cos(tilt)) / 2.0
    return pd.Series(np.maximum(beam + diffuse + reflected, 0.0), index=df.index)


@dataclass(frozen=True)
class ClimateStation:
    """Location of a weather station used by the climate-data selector."""

    station_id: str
    name: str
    latitude: float
    longitude: float


def haversine_distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return the great-circle distance between two WGS84 points in kilometres."""
    lat_delta = radians(latitude_b - latitude_a)
    lon_delta = radians(longitude_b - longitude_a)
    latitude_a_rad = radians(latitude_a)
    latitude_b_rad = radians(latitude_b)

    haversine = (
        sin(lat_delta / 2) ** 2
        + cos(latitude_a_rad) * cos(latitude_b_rad) * sin(lon_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(haversine))


def nearest_climate_station(
    latitude: float,
    longitude: float,
    stations: Sequence[ClimateStation],
) -> tuple[ClimateStation, float]:
    """Select the closest station and return it with its distance in kilometres."""
    if not stations:
        raise ValueError("At least one climate station is required")

    nearest = min(
        stations,
        key=lambda station: haversine_distance_km(
            latitude, longitude, station.latitude, station.longitude
        ),
    )
    distance = haversine_distance_km(latitude, longitude, nearest.latitude, nearest.longitude)
    return nearest, distance


def load_epw(path: str | Path) -> pd.DataFrame:
    """Load an EnergyPlus Weather (EPW) file into a pandas DataFrame.

    Returns a DataFrame indexed by datetime with the standard EPW columns,
    plus derived columns for the solar position and radiation components.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"EPW file not found: {path}")

    if pvlib is None:
        df, meta = _load_epw_legacy_width(path, coerce_year=2023)
    else:
        try:
            df, meta = pvlib.iotools.read_epw(str(path), coerce_year=2023)
        except pd.errors.ParserError:
            df, meta = _load_epw_legacy_width(path, coerce_year=2023)
    if len(df) != 8760:
        raise ValueError(
            f"EPW climate data must contain exactly 8760 hourly records; got {len(df)}"
        )
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
    if pvlib is None:
        solar_pos = _solar_position_approximation(
            df.index,
            latitude=float(meta["latitude"]),
            longitude=float(meta["longitude"]),
        )
    else:
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
    if pvlib is None:
        return _hay_davies_fallback(
            df, surface_tilt, surface_azimuth, ground_reflectance
        )

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
    if pvlib is None:
        solar_pos = _solar_position_approximation(index, latitude, longitude)
    else:
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
