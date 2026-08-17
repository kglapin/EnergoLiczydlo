# Dane wejściowe projektu

## 1. Cel dokumentu

Ten dokument opisuje najważniejsze dane wejściowe aplikacji Energoliczydło.

Nazwy pól w pliku JSON pozostają zgodne z kodem i dlatego część z nich jest po angielsku. Przy każdym polu podano jednak jasne polskie znaczenie.

Projekt składa się z dwóch głównych warstw danych:

1. **podstawowych danych budynku i systemów technicznych**,
2. **zaawansowanych danych normowych i formalnych** zapisanych w `metadata.normative`.

## 2. Główny obiekt projektu

Uproszczona struktura:

```json
{
  "version": "0.1.0",
  "project_name": "Przykładowy budynek",
  "metadata": {
    "created_at": "2026-08-17T10:00:00Z",
    "norm_version": "PN-EN ISO 52016-1",
    "regulation_version": "aktualna metodologia charakterystyki energetycznej",
    "normative": {}
  },
  "general": {},
  "climate_station_id": "...",
  "thermal_zones": [],
  "opaque_building_elements": [],
  "transparent_building_elements": [],
  "thermal_bridges": {},
  "ventilation": {},
  "internal_gains": {},
  "systems": {},
  "primary_energy": {}
}
```

## 3. Dane ogólne budynku – `general`

Najważniejsze pola:

| Pole | Znaczenie |
|---|---|
| `building_name` | nazwa budynku lub analizy |
| `building_type` | rodzaj budynku, np. mieszkalny, biurowy, szkoła |
| `dhw_usage_profile` | profil użytkowania ciepłej wody użytkowej |
| `construction_year` | rok budowy |
| `conditioned_floor_area` | powierzchnia o regulowanej temperaturze w m² |
| `usable_floor_area` | powierzchnia użytkowa w m² |
| `heated_volume` | kubatura ogrzewana w m³ |
| `number_of_storeys` | liczba kondygnacji |
| `location_address` | adres budynku, jeżeli jest podany |

Suma powierzchni stref kondycjonowanych musi być zgodna z `conditioned_floor_area`.

Suma kubatur stref kondycjonowanych musi być zgodna z `heated_volume`.

## 4. Strefy termiczne – `thermal_zones`

Każda strefa ma między innymi:

| Pole | Znaczenie |
|---|---|
| `id` | unikalny identyfikator strefy |
| `name` | nazwa strefy |
| `zone_type` | sposób użytkowania cieplnego strefy |
| `floor_area` | powierzchnia strefy w m² |
| `volume` | kubatura strefy w m³ |
| `setpoint_heating` | zadana temperatura ogrzewania w °C |
| `setpoint_cooling` | zadana temperatura chłodzenia w °C |
| `occupancy_density` | liczba osób na m² |
| `use_type` | profil użytkowania strefy |

Przykładowe typy stref:

- `heated` – strefa ogrzewana,
- `cooled` – strefa chłodzona,
- `heated_and_cooled` – strefa ogrzewana i chłodzona,
- `unheated` – strefa nieogrzewana,
- `semi_heated` – strefa częściowo ogrzewana.

## 5. Przegrody nieprzezroczyste – `opaque_building_elements`

Przykłady: ściany zewnętrzne, dach, podłoga na gruncie, strop nad przestrzenią nieogrzewaną.

Najważniejsze pola:

| Pole | Znaczenie |
|---|---|
| `id` | unikalny identyfikator przegrody |
| `name` | nazwa przegrody |
| `zone_id` | strefa, do której należy przegroda |
| `element_type` | rodzaj przegrody |
| `orientation_azimuth` | azymut: 0° północ, 90° wschód, 180° południe, 270° zachód |
| `inclination` | nachylenie od poziomu: 0° poziomo, 90° pionowo |
| `height` | pierwszy wymiar przegrody w m |
| `width` | drugi wymiar przegrody w m |
| `area` | powierzchnia w m² |
| `u_value` | współczynnik przenikania ciepła w W/(m²·K) |
| `solar_absorptance` | współczynnik pochłaniania promieniowania słonecznego |
| `emissivity` | emisyjność powierzchni |
| `adjacent_space_type` | rodzaj przestrzeni po drugiej stronie przegrody |
| `adjacent_temperature` | stała temperatura po drugiej stronie, jeżeli jest wymagana |

Jeżeli podano jednocześnie `height` i `width`, powierzchnia jest wyliczana jako ich iloczyn.

## 6. Przegrody przezroczyste – `transparent_building_elements`

Przykłady: okna, drzwi przeszklone, świetliki.

Najważniejsze pola:

| Pole | Znaczenie |
|---|---|
| `id` | unikalny identyfikator otworu |
| `name` | nazwa otworu |
| `zone_id` | strefa, do której należy otwór |
| `element_type` | rodzaj otworu |
| `orientation_azimuth` | azymut powierzchni |
| `inclination` | nachylenie powierzchni |
| `height` | wysokość w m |
| `width` | szerokość w m |
| `area` | powierzchnia w m² |
| `u_value` | współczynnik przenikania ciepła |
| `g_value` | całkowity współczynnik przepuszczania energii słonecznej |
| `frame_factor` | udział ramy w powierzchni elementu |
| `shading_factor` | współczynnik redukcji zysków przez zacienienie |

Otwory są odejmowane od powierzchni brutto odpowiedniej przegrody nieprzezroczystej.

Jeżeli przypisanie otworu do przegrody nie jest jednoznaczne, można wskazać je w `metadata.opening_hosts`.

Przykład:

```json
{
  "metadata": {
    "opening_hosts": {
      "window_1": "wall_south_1"
    }
  }
}
```

## 7. Mostki cieplne – `thermal_bridges`

Mostki cieplne nie są automatycznie zgadywane z geometrii.

Użytkownik może podać:

- mostki liniowe – współczynnik `psi_value` i długość,
- mostki punktowe – współczynnik `chi_value` i liczbę wystąpień.

Brak mostków oznacza w obliczeniu wartość 0 W/K i jest sygnalizowany jako założenie wymagające kontroli.

## 8. Wentylacja – `ventilation`

Najważniejsze pola:

| Pole | Znaczenie |
|---|---|
| `ventilation_type` | rodzaj wentylacji |
| `operation_mode` | praca ciągła albo okresowa |
| `airflow_rate` | nominalny strumień powietrza w m³/h |
| `heat_recovery_efficiency` | podstawowa sprawność odzysku ciepła |
| `infiltration_rate` | krotność infiltracji w 1/h |
| `fan_infiltration_rate` | dodatkowa infiltracja związana z pracą wentylatorów |
| `supply_temperature` | jawnie podana temperatura nawiewu, jeżeli jest znana |
| `mechanical_fan_power` | moc elektryczna wentylatorów w W |
| `schedule` | harmonogram pracy wentylacji |

Szczegółowy model rekuperatora znajduje się w `metadata.normative.heat_recovery`.

## 9. Zyski wewnętrzne – `internal_gains`

Zyski wewnętrzne mogą obejmować:

- ludzi,
- oświetlenie,
- urządzenia.

Dla każdego źródła można podać poziom mocy oraz harmonogram godzinowy.

Jeżeli szczegółowe dane nie są podane, silnik może korzystać z jawnie określonego profilu właściwego dla danego trybu obliczeń.

## 10. Systemy techniczne – `systems`

Obiekt zawiera między innymi:

- system ogrzewania,
- system chłodzenia,
- system przygotowania ciepłej wody użytkowej,
- dane systemu wentylacyjnego.

Dla systemów przechowywane są między innymi:

- rodzaj źródła,
- nośnik energii,
- sprawność albo współczynnik efektywności,
- sprawność dystrybucji,
- sprawność magazynowania,
- sprawność regulacji,
- energia pomocnicza, jeżeli jest znana.

## 11. Współczynniki energii pierwotnej – `primary_energy`

Ta sekcja zawiera wartości używane do przeliczenia energii końcowej na nieodnawialną energię pierwotną oraz emisję dwutlenku węgla.

W trybie świadectwa sama liczba nie jest wystarczająca. Źródło wartości jest przechowywane osobno w części formalnej `metadata.normative.legal`.

---

# 12. Zaawansowane dane – `metadata.normative`

Główna struktura:

```json
{
  "metadata": {
    "normative": {
      "ground": {},
      "heat_recovery": {},
      "design_conditions": {},
      "polish_certificate": {},
      "legal": {}
    }
  }
}
```

Każda sekcja ma inne przeznaczenie.

## 13. Grunt – `metadata.normative.ground`

Przykład:

```json
{
  "enabled": true,
  "certificate_mode": false,
  "soil_conductivity_w_mk": 2.0,
  "soil_density_kg_m3": 1800,
  "soil_specific_heat_j_kgk": 900,
  "external_wall_thickness_m": 0.30,
  "elements": {
    "floor_ground_1": {
      "exposed_perimeter_m": 42.0,
      "floor_thermal_resistance_m2k_w": 4.5,
      "periodic_amplitude_ratio": 0.30,
      "phase_shift_days": 45
    }
  }
}
```

Znaczenie najważniejszych pól:

| Pole | Znaczenie |
|---|---|
| `enabled` | włącza rozszerzony model gruntu |
| `certificate_mode` | wymaga danych odpowiednich do kontrolowanego wariantu obliczeń |
| `soil_conductivity_w_mk` | przewodność cieplna gruntu |
| `soil_density_kg_m3` | gęstość gruntu |
| `soil_specific_heat_j_kgk` | ciepło właściwe gruntu |
| `external_wall_thickness_m` | grubość ściany zewnętrznej |
| `exposed_perimeter_m` | obwód podłogi wystawiony na wymianę z gruntem |
| `floor_thermal_resistance_m2k_w` | opór cieplny warstw podłogi |
| `periodic_amplitude_ratio` | współczynnik tłumienia rocznej zmiany temperatury |
| `phase_shift_days` | przesunięcie czasowe odpowiedzi gruntu w dniach |

## 14. Odzysk ciepła – `metadata.normative.heat_recovery`

Przykład:

```json
{
  "enabled": true,
  "certificate_mode": false,
  "performance_source": "Karta techniczna centrali",
  "efficiency_curve": [
    {"outdoor_temperature_c": -10, "efficiency": 0.78},
    {"outdoor_temperature_c": 0, "efficiency": 0.82},
    {"outdoor_temperature_c": 10, "efficiency": 0.84}
  ],
  "summer_bypass_enabled": true,
  "bypass_min_outdoor_c": 14,
  "bypass_max_outdoor_c": 24,
  "frost_strategy": "preheater",
  "frost_exhaust_limit_c": 0,
  "indoor_relative_humidity": 0.45,
  "preheater_max_power_w": 1200,
  "preheater_efficiency": 1.0
}
```

Najważniejsze pola:

| Pole | Znaczenie |
|---|---|
| `performance_source` | źródło charakterystyki urządzenia |
| `efficiency_curve` | punkty sprawności dla różnych temperatur zewnętrznych |
| `summer_bypass_enabled` | włącza obejście letnie wymiennika |
| `bypass_min_outdoor_c` | dolna temperatura pracy obejścia |
| `bypass_max_outdoor_c` | górna temperatura pracy obejścia |
| `frost_strategy` | sposób ochrony przed zamarzaniem |
| `indoor_relative_humidity` | wilgotność względna powietrza usuwanego jako liczba 0–1 |
| `preheater_max_power_w` | maksymalna moc nagrzewnicy wstępnej |

Możliwe strategie ochrony przed zamarzaniem:

- `none` – brak aktywnej ochrony,
- `preheater` – nagrzewnica wstępna,
- `reduce_recovery` – ograniczenie odzysku ciepła,
- `disable_recovery` – czasowe wyłączenie odzysku ciepła.

## 15. Warunki projektowe – `metadata.normative.design_conditions`

Ta sekcja służy do projektowego obciążenia cieplnego.

Najważniejsze pola:

| Pole | Znaczenie |
|---|---|
| `enabled` | włącza obliczenie projektowego obciążenia cieplnego |
| `certificate_mode` | wymaga udokumentowanego źródła warunków projektowych |
| `outdoor_design_temperature_c` | projektowa temperatura zewnętrzna |
| `source` | źródło projektowej temperatury zewnętrznej |
| `heat_up_power_by_zone_w` | dodatkowa moc ponownego nagrzania dla stref |
| `unheated_adjacent_temperature_by_element_c` | temperatura przestrzeni nieogrzewanej po drugiej stronie konkretnej przegrody |
| `ground_adjacent_temperature_by_element_c` | projektowa temperatura po stronie gruntu dla konkretnej przegrody |

## 16. Dane formalnego świadectwa – `metadata.normative.polish_certificate`

Ta sekcja przechowuje dane miesięczne dla formalnego silnika charakterystyki energetycznej.

Każda miesięczna seria musi zawierać dokładnie 12 wartości.

Najważniejsze pola:

| Pole | Znaczenie |
|---|---|
| `enabled` | włącza miesięczny silnik formalny |
| `official_bip_climate_data` | potwierdzenie użycia odpowiednich oficjalnych danych klimatycznych |
| `monthly_outdoor_temperature_c` | 12 miesięcznych temperatur zewnętrznych |
| `solar_irradiation_kwh_m2_by_element` | miesięczne promieniowanie słoneczne dla konkretnych przegród przezroczystych |
| `heating_internal_temperature_c_by_zone` | miesięczne temperatury wewnętrzne dla ogrzewania |
| `cooling_internal_temperature_c_by_zone` | miesięczne temperatury wewnętrzne dla chłodzenia |
| `heating_gain_utilization_by_zone` | miesięczne współczynniki wykorzystania zysków przy ogrzewaniu |
| `cooling_loss_utilization_by_zone` | miesięczne współczynniki wykorzystania strat przy chłodzeniu |
| `beta_by_zone` | miesięczny udział czasu użytkowania |
| `recovery_effectiveness_by_zone` | miesięczna skuteczność odzysku ciepła |
| `supply_extract_reduction_by_zone` | miesięczne współczynniki redukcyjne instalacji nawiewno-wywiewnej |
| `unheated_adjacent_temperature_c_by_element` | miesięczne temperatury przestrzeni nieogrzewanych |
| `ground_adjacent_temperature_c_by_element` | miesięczne temperatury gruntu |
| `internal_gain_density_w_m2_by_zone` | gęstość zysków wewnętrznych dla stref |
| `preheater_electricity_kwh_by_month` | 12 miesięcznych wartości zużycia energii przez nagrzewnicę wstępną |
| `heating_useful_override_kwh_by_zone` | opcjonalne, zewnętrznie zweryfikowane miesięczne wartości ogrzewania |
| `cooling_useful_override_kwh_by_zone` | opcjonalne, zewnętrznie zweryfikowane miesięczne wartości chłodzenia |

Wartości współczynników takich jak wykorzystanie zysków, wykorzystanie strat, udział czasu działania i skuteczność odzysku muszą mieścić się w zakresie od 0 do 1.

## 17. Ślad dokumentacyjny – `metadata.normative.legal`

Przykład:

```json
{
  "certificate_mode": true,
  "calculation_date": "2026-08-17",
  "methodology_source": "wskazanie zastosowanego aktu i wersji metodologii",
  "climate_data_source": "źródło danych klimatycznych",
  "utilization_factor_source": "źródło współczynników wykorzystania zysków i strat",
  "ventilation_factor_source": "źródło danych i współczynników wentylacyjnych",
  "primary_energy_factor_sources": {
    "electricity": "źródło współczynnika dla energii elektrycznej"
  }
}
```

Znaczenie pól:

| Pole | Znaczenie |
|---|---|
| `certificate_mode` | włącza formalną kontrolę kompletności danych |
| `calculation_date` | data wykonania obliczenia |
| `methodology_source` | źródło zastosowanej metodologii |
| `climate_data_source` | źródło danych klimatycznych |
| `utilization_factor_source` | źródło współczynników wykorzystania zysków i strat |
| `ventilation_factor_source` | źródło współczynników i danych wentylacyjnych |
| `primary_energy_factor_sources` | źródło współczynnika nakładu nieodnawialnej energii pierwotnej dla każdego używanego nośnika |

## 18. Zasada działania trybu świadectwa

Po ustawieniu:

```text
metadata.normative.legal.certificate_mode = true
```

aplikacja sprawdza kompletność wymaganych danych.

Jeżeli brakuje wartości potrzebnej do formalnego obliczenia, aplikacja nie powinna zgadywać jej na podstawie nieudokumentowanego ustawienia domyślnego.

W takiej sytuacji użytkownik otrzymuje błąd wskazujący brakujące dane.

## 19. Ważna zasada dotycząca opisów

Nazwy pól kodu, np. `heating_gain_utilization_by_zone`, mogą pozostać angielskie, ponieważ są częścią API.

W interfejsie i dokumentacji nie należy jednak pokazywać użytkownikowi samej nazwy technicznej bez wyjaśnienia.

Poprawny opis:

> Miesięczny współczynnik wykorzystania zysków ciepła dla ogrzewania (`heating_gain_utilization_by_zone`).

Niepoprawny opis:

> `etaH,gn` / utilization factor.
