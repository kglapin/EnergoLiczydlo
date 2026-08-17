"""Primary energy and CO2 emission calculations per Polish methodology."""

from __future__ import annotations

from app.schemas.models import PrimaryEnergyFactors


RENEWABLE_FINAL_ENERGY_CARRIERS = {
    "biomass",
    "biogas",
    "solar",
    "wind",
    "geothermal",
    "renewable",
}


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
        ``fp`` is the non-renewable primary energy factor [-] and ``we`` the
        CO2 emission indicator in kg CO2/kWh.

    Returns
    -------
    ep_wh : float
        Primary energy [Wh].
    ec_t : float
        CO2 emissions [tonnes].
    """
    ep_wh = 0.0
    ec_t = 0.0

    for carrier, e_wh in final_energy_by_carrier.items():
        factor = getattr(factors, carrier, None)
        if factor is None:
            # Unknown carriers stay explicit zero-primary only for backwards
            # compatibility. New carrier names should be added to the schema.
            factor = factors.renewable
        ep_wh += e_wh * factor.fp
        ec_t += e_wh / 1000.0 * factor.we / 1000.0  # Wh -> kWh -> t CO2

    return ep_wh, ec_t


def share_of_renewable_energy(
    final_energy_by_carrier: dict[str, float],
) -> float:
    """Compute renewable share of final energy [%] for all renewable carriers."""
    total = sum(final_energy_by_carrier.values())
    if total == 0:
        return 0.0
    renewable = sum(
        final_energy_by_carrier.get(carrier, 0.0)
        for carrier in RENEWABLE_FINAL_ENERGY_CARRIERS
    )
    return 100.0 * renewable / total
