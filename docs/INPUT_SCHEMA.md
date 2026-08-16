# Schema danych wejściowych (Input Schema)

Typy danych wejściowych są modelowane w backendzie za pomocą **Pydantic v2**, a w frontendzie za pomocą **Zod** (generowane ręcznie lub z OpenAPI).

## Główny model: `BuildingProject`

```json
{
  "version": "0.1.0",
  "project_name": "Budynek mieszkalny - Warszawa",
  "metadata": {
    "created_at": "2026-08-16T12:00:00Z",
    "norm_version": "PN-EN ISO 52016-1:2017",
    "regulation_version": "Dz.U. 2015 poz. 376 z późn. zm."
  },
  "general": { /* GeneralInfo */ },
  "climate_station_id": "warsaw-okecie-123750",
  "thermal_zones": [ /* ThermalZone[] */ ],
  "opaque_building_elements": [ /* OpaqueElement[] */ ],
  "transparent_building_elements": [ /* TransparentElement[] */ ],
  "thermal_bridges": { /* ThermalBridges */ },
  "ventilation": { /* Ventilation */ },
  "internal_gains": { /* InternalGains */ },
  "systems": { /* BuildingSystems */ },
  "primary_energy": { /* PrimaryEnergyFactors */ }
}
```

## GeneralInfo

| Pole | Typ | Opis |
|------|-----|------|
| `building_name` | `str` | Nazwa budynku / analizy |
| `building_type` | `enum` | `residential`, `office`, `school`, `retail`, `healthcare`, `other` |
| `construction_year` | `int` | Rok budowy |
| `conditioned_floor_area` | `float` | Powierzchnia o regulowanej temperaturze `Af` [m²] |
| `usable_floor_area` | `float` | Powierzchnia użytkowa `Au` [m²] |
| `heated_volume` | `float` | Kubatura ogrzewana [m³] |
| `number_of_storeys` | `int` | Liczba kondygnacji |
| `location_address` | `str` | Adres (opcjonalnie) |

## ThermalZone

| Pole | Typ | Opis |
|------|-----|------|
| `id` | `str` | Unikalny identyfikator |
| `name` | `str` | Nazwa strefy, np. "Parter" |
| `zone_type` | `enum` | `heated`, `cooled`, `heated_and_cooled`, `unheated`, `semi_heated` |
| `floor_area` | `float` | Powierzchnia podłogi [m²] |
| `volume` | `float` | Kubatura [m³] |
| `setpoint_heating` | `float` | Temperatura zadana ogrzewania [°C] |
| `setpoint_cooling` | `float` | Temperatura zadana chłodzenia [°C] |
| `occupancy_density` | `float` | Liczba osób / m² |
| `use_type` | `enum` | Kategoria użytkowania wg normy |

## OpaqueElement (przegrody nieprzezroczyste)

| Pole | Typ | Opis |
|------|-----|------|
| `id` | `str` | Unikalny identyfikator |
| `name` | `str` | Nazwa |
| `zone_id` | `str` | ID strefy, do której należy |
| `element_type` | `enum` | `external_wall`, `roof`, `ground_floor`, `floor_over_unheated`, `internal_wall`, `basement_wall`, `party_wall` |
| `orientation_azimuth` | `float` | Azymut od strony północy [°]; 0 = N, 90 = E, 180 = S, 270 = W |
| `inclination` | `float` | Nachylenie od poziomu [°]; 90 = pion, 0 = poziom |
| `area` | `float` | Powierzchnia [m²] |
| `u_value` | `float` | Współczynnik przenikania `U` [W/(m²·K)] |
| `solar_absorptance` | `float` | Współczynnik absorpcji promieniowania `α` [-] (0–1) |
| `emissivity` | `float` | Emisyjność powierzchni `ε` [-] (0–1) |
| `adjacent_space_type` | `enum` | `outdoor`, `ground`, `unheated_zone`, `heated_zone`, `constant_temperature` |
| `adjacent_temperature` | `float?` | Stała temperatura przestrzeni sąsiedniej [°C] |

## TransparentElement (okna, drzwi przeszklone, świetliki)

| Pole | Typ | Opis |
|------|-----|------|
| `id` | `str` | Unikalny identyfikator |
| `name` | `str` | Nazwa |
| `zone_id` | `str` | ID strefy |
| `element_type` | `enum` | `window`, `glass_door`, `skylight` |
| `orientation_azimuth` | `float` | Azymut [°] |
| `inclination` | `float` | Nachylenie [°] |
| `area` | `float` | Powierzchnia [m²] |
| `u_value` | `float` | Współczynnik `U` [W/(m²·K)] |
| `g_value` | `float` | Całkowite przepuszczanie energii słonecznej `g` [-] |
| `frame_factor` | `float` | Udział ramy w powierzchni [-] (0–1) |
| `shading_factor` | `float` | Współczynnik ekranowania `F_sh` [-] (0–1) |
| `external_shading` | `object?` | Opis ekranowania zewnętrznego (gzymsy, rolety) |

## ThermalBridges

```json
{
  "auto_calculate": false,
  "linear_bridges": [
    {
      "id": "...",
      "name": "Mostek okienny",
      "psi_value": 0.05,
      "length": 24.0,
      "zone_id": "...",
      "element_id": "..."
    }
  ],
  "point_bridges": [
    {
      "id": "...",
      "name": "Słup metalowy",
      "chi_value": 0.5,
      "count": 4,
      "zone_id": "..."
    }
  ]
}
```

## Ventilation

| Pole | Typ | Opis |
|------|-----|------|
| `ventilation_type` | `enum` | `natural`, `mechanical`, `hybrid`, `none` |
| `airflow_rate` | `float` | Strumień powietrza wentylacyjnego [m³/h] |
| `heat_recovery_efficiency` | `float` | Sprawność odzysku ciepła `η` [-] (0–1) |
| `infiltration_rate` | `float` | Infiltracja [1/h] (n50 lub q50 po konwersji) |
| `supply_temperature` | `float?` | Temperatura nawiewu [°C] |
| `mechanical_fan_power` | `float?` | Moc wentylatorów [W] |
| `schedule` | `Schedule` | Harmonogram wentylacji |

## InternalGains

```json
{
  "occupancy": {
    "density_persons_per_m2": 0.03,
    "heat_gain_per_person": 80,
    "schedule": { /* Schedule */ }
  },
  "lighting": {
    "power_density": 10.0,
    "schedule": { /* Schedule */ }
  },
  "equipment": {
    "power_density": 5.0,
    "schedule": { /* Schedule */ }
  }
}
```

## Schedule

```json
{
  "type": "hourly_profile",
  "weekday": [0.0, 0.0, 0.0, ..., 1.0, ...],
  "saturday": [...],
  "sunday": [...],
  "holiday": [...]
}
```

Lub uproszczony typ `constant` / `weekday_weekend`.

## BuildingSystems

```json
{
  "heating": {
    "system_type": "heat_pump_air",
    "fuel_or_carrier": "electricity",
    "nominal_power": 10.0,
    "efficiency_or_cop": { "map_or_constant": "constant", "value": 3.5 },
    "distribution_loss_factor": 0.95,
    "control_factor": 1.0,
    "auxiliary_energy": 0.0
  },
  "cooling": { /* analogicznie */ },
  "dhw": {
    "system_type": "electric_storage",
    "daily_demand_per_person": 50,
    "target_temperature": 55,
    "cold_water_temperature": 10,
    "efficiency": 0.9
  },
  "ventilation_system": {
    "has_heating_coil": false,
    "has_cooling_coil": false,
    "fan_specific_power": 2.0
  }
}
```

## PrimaryEnergyFactors

```json
{
  "electricity": { "fp": 2.5, "we": 0.6 },
  "natural_gas": { "fp": 1.1, "we": 0.2 },
  "district_heating": { "fp": 1.2, "we": 0.25 },
  "biomass": { "fp": 1.0, "we": 0.05 },
  "renewable": { "fp": 1.0, "we": 0.0 }
}
```

Wartości domyślne pochodzą z polskich przepisów i mogą być nadpisane.

## Output: `CalculationResult`

```json
{
  "project_id": "...",
  "status": "success",
  "annual_indicators": {
    "eu_kwh_m2_year": 45.2,
    "ek_kwh_m2_year": 52.1,
    "ep_kwh_m2_year": 89.5,
    "ec_tco2_m2_year": 0.03,
    "u_oze_percent": 15.0
  },
  "monthly": [ /* 12 rekordów */ ],
  "hourly": { /* opcjonalnie kluczowe szeregi */ },
  "compliance": {
    "pass": false,
    "checks": [ /* lista testów z statusami */ ]
  }
}
```
