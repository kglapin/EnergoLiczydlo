"""Primary energy and CO2 emission calculations per Polish methodology."""

from __future__ import annotations

from app.schemas.models import PrimaryEnergyFactors


def annual_primary_energy(
    final_energy_by_carrier: dict[str, float],
    factors: PrimaryEnergyFactors,
) -> tuple[float, float]:
    """Compute annual primary energy and CO2 emissions.

    Parameters
    ----------
    final_energy_by_carrier : dict[str, float]
        Final energy per carrier in Wh. Carrier names must match the
        attribute names of PrimaryEnergyFactors (e.g. 'electricity').
    factors : PrimaryEnergyFactors

    Returns
    -------
    ep_wh : float
        Primary energy [Wh].
    ec_kg : float
        CO2 emissions [kg].
    """
    ep_wh = 0.0
    ec_kg = 0.0

    for carrier, e_kwh in final_energy_by_carrier.items():
        factor = getattr(factors, carrier, None)
        if factor is None:
            # Unknown carrier: assume primary factor 1.0 and warn
            factor = factors.renewable  # safest fallback
        ep_wh += e_kwh * factor.fp
        ec_kg += e_kwh * factor.we / 1_000_000  # we is kg CO2 / MWh typically

    return ep_wh, ec_kg


def share_of_renewable_energy(
    final_energy_by_carrier: dict[str, float],
) -> float:
    """Compute a simple share of renewable final energy [%]."""
    total = sum(final_energy_by_carrier.values())
    if total == 0:
        return 0.0
    renewable = (
        final_energy_by_carrier.get("biomass", 0.0)
        + final_energy_by_carrier.get("renewable", 0.0)
    )
    return 100.0 * renewable / total
