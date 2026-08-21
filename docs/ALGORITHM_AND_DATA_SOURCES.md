# Algorytm obliczeniowy i źródła danych

Niniejszy dokument opisuje algorytmy obliczeniowe zaimplementowane w silniku EnergoLiczydło, stałe normatywne oraz źródła danych, na których bazuje aplikacja. Dokument ma charakter techniczny i jest przeznaczony dla inżynierów oraz audytorów obliczeń.

## Spis treści

1. [Podstawy prawne i normatywne](#1-podstawy-prawne-i-normatywne)
2. [Dane klimatyczne](#2-dane-klimatyczne)
3. [Modele obliczeniowe](#3-modele-obliczeniowe)
4. [Stałe fizyczne](#4-stae-fizyczne)
5. [Stałe normatywne — sprawności systemów](#5-stae-normatywne--sprawnoci-systemów)
6. [Stałe normatywne — ciepła woda użytkowa](#6-stae-normatywne--ciepa-woda-uytkowa)
7. [Stałe normatywne — zyski wewnętrzne](#7-stae-normatywne--zyski-wewntrzne)
8. [Stałe normatywne — wentylacja i infiltracja](#8-stae-normatywne--wentylacja-i-infiltracja)
9. [Stałe normatywne — energia pomocnicza](#9-stae-normatywne--energia-pomocnicza)
10. [Stałe normatywne — energia pierwotna i emisje](#10-stae-normatywne--energia-pierwotna-i-emisje)
11. [Mostki cieplne](#11-mostki-cieplne)
12. [Zyski słoneczne](#12-zyski-soneczne)
13. [Odzysk ciepła z wentylacji](#13-odzysk-ciepa-z-wentylacji)
14. [API](#14-api)

---

## 1. Podstawy prawne i normatywne

Silnik bazuje na następujących aktach prawnych i normach technicznych:

| Akt | Zakres |
|---|---|
| **Rozporządzenie Ministra Infrastruktury i Rozwoju z dnia 27 lutego 2015 r. w sprawie metodologii wyznaczania charakterystyki energetycznej budynku lub części budynku oraz świadectw charakterystyki energetycznej** (Dz.U. 2015 poz. 376 z późn. zm.) | Polska metodologia miesięczna, tabele 1–27 (sprawności, straty zasobnika, energia pomocnicza, zyski wewnętrzne, profile CWU, strumienie powietrza) |
| **Rozporządzenie Ministra Klimatu i Środowiska z dnia 8 kwietnia 2022 r. w sprawie świadectwa charakterystyki energetycznej budynku lub części budynku** (Dz.U. 2022 poz. 1285) | Wymagania dotyczące świadectwa, wskaźniki nieodnawialnej energii pierwotnej |
| **PN-EN ISO 52016-1:2017-09** — Energetyczne właściwości budynków — Zapotrzebowanie na energię do ogrzewania i chłodzenia, wewnętrzne temperatury oraz jawne i utajone obciążenia cieplne — Część 1: Nowe procedury obliczeń | Model godzinowy, sieć węzłów, bilans dynamiczny |
| **PN-EN ISO 13790:2008** — (wycofana, zachowana jako model uproszczony 5R1C) | Sieć 5 rezystancji i 1 pojemności, klasy kappa |
| **PN-EN 12831-1:2017-09** — Metoda obliczania projektowego obciążenia cieplnego | Projektowe obciążenie cieplne, temperatura projektowa |
| **PN-EN ISO 6946:2017-09** — Opór cieplny i współczynnik przenikania ciepła | Opory powierzchni zewnętrznych (`R_se`) |
| **PN-EN ISO 15927-5** — Dane klimatyczne — Część 5: Dane projektowe | Sekwencje projektowe dla obciążenia cieplnego |

### Tryby pracy silnika

Silnik pracuje w dwóch trybach:

- **Tryb ścisły** — wymagane są wszystkie jawne dane konstruktorskie (współczynniki filmowe, rezystancje rdzenia, pojemności cieplne). Brakujące dane blokują obliczenie.
- **Tryb zgodności (compatibility)** — brakujące dane są inferowane z uproszczonych założeń (oznaczane jako `inferred=True`). Obliczenie jest możliwe, ale wynik ma charakter diagnostyczny, a nie formalny.

---

## 2. Dane klimatyczne

### 2.1. Format i źródło

Dane klimatyczne pochodzą z plików **EnergyPlus Weather (EPW)** reprezentujących **typowy rok meteorologiczny (TMY)**. Pliki są generowane przez **NCEI ISD / ERA5** i obejmują 15-letni okres (2009–2023).

### 2.2. Dostępne stacje

Pliki znajdują się w katalogu `backend/data/tmy/`. Każdy plik zawiera dokładnie **8760 wierszy godzinowych** (weryfikowane w `app/engine/climate.py`, linia 287).

| Stacja | Kod WMO | Szerokość | Długość | Wysokość |
|---|---|---|---|---|
| Warszawa–Okęcie | 123750 | 52,163°N | 20,961°E | 110,3 m |
| Poznań–Ławica | 123300 | 52,417°N | 16,835°E | 93,9 m |

### 2.3. Odczytywane kolumny EPW

| Pole EPW | Nazwa wewnętrzna | Jednostka | Zastosowanie |
|---|---|---|---|
| Dry bulb temperature | `T_e` | °C | Bilans cieplny, projektowe obciążenie |
| Dew point temperature | `T_dew` | °C | Odzysk ciepła (ochrona przed szronem) |
| Relative humidity | `RH` | % | Odzysk ciepła (punkt rosy) |
| Atmospheric pressure | `P_atm` | Pa | Diagnostyka |
| Global horizontal irradiance | `GHI` | W/m² | Zyski słoneczne |
| Direct normal irradiance | `DNI` | W/m² | Zyski słoneczne na powierzchniach pochylonych |
| Diffuse horizontal irradiance | `DHI` | W/m² | Zyski słoneczne rozproszone |
| Wind speed | `v_wind` | m/s | Współczynniki filmowe zewnętrzne |
| Wind direction | `dir_wind` | ° | Diagnostyka |
| Total sky cover | `sky_cover` | okta | Model promieniowania rozproszonego |

### 2.4. Wybór stacji

Stacja jest wybierana na podstawie współrzędnych geograficznych budynku:

1. Geokodowanie adresu przez **Open-Meteo Geocoding API** (`app/api/climate.py`, funkcja `_geocode_location`).
2. Wybór najbliższej stacji metodą odległości wielkiego koła (wzór haversine, `app/engine/climate.py`, linia 232).
3. Wynik zwraca odległość w kilometrach — użytkownik ocenia, czy jest akceptowalna.

### 2.5. Stałe fizyczne atmosfery

| Stała | Wartość | Jednostka | Plik |
|---|---|---|---|
| Gęstość powietrza | 1,2 | kg/m³ | `climate.py:24` |
| Ciepło właściwe powietrza | 1005 | J/(kg·K) | `climate.py:25` |
| Objętościowe ciepło właściwe powietrza | 1200 | J/(m³·K) | `ventilation.py:25` |
| Promień Ziemi | 6371,0088 | km | `climate.py:26` |
| Albedo gruntu (domyślne) | 0,2 | — | `solar.py:54` |

---

## 3. Modele obliczeniowe

EnergoLiczydło implementuje **trzy równoległe procedury obliczeniowe**, które należy rozróżniać w wynikach:

### 3.1. Model godzinowy PN-EN ISO 52016-1

**Plik:** `app/engine/iso52016_hourly.py`

**Charakter:** fizyczna analiza dynamiczna, 8760 godzin.

**Sieć węzłów (klauzula 6.5 normy):**
- 1 węzeł powietrza/mebli z pojemnością cieplną
- 5 węzłów na każdy element nieprzezroczysty (z zewnątrz do wewnątrz)
- 2 węzły zerowej pojemności na każdy element przezroczysty

**Współczynniki filmowe (tryb zgodności, `iso52016_hourly.py:125–150`):**

| Inklinacja | Opór wewnętrzny `R_si` [m²·K/W] |
|---|---|
| < 60° (sufit) | 0,10 |
| 60–120° (ściana) | 0,13 |
| > 120° (podłoga) | 0,17 |

Opór powierzchni zewnętrznej `R_se = 0,04 m²·K/W` (PN-EN ISO 6946, `envelope.py:30`).

**Rezystancje rdzenia elementu (tryb zgodności):**

```
R_core = 1/U − 1/(h_ci + h_ri) − 1/(h_ce + h_re)
```

Podział na 4 równe części, jeśli nie podano szczegółowo.

**Pojemności cieplne węzłów (tryb zgodności):**

Rozkład masy w 5 węzłach zależnie od położenia warstwy izolacji:

| Położenie izolacji | Frakcje pojemności (zewnątrz → wewnątrz) |
|---|---|
| zewnętrzna (`external`) | [0,55; 0,25; 0,12; 0,06; 0,02] |
| środkowa (`middle`) | [0,05; 0,15; 0,60; 0,15; 0,05] |
| wewnętrzna (`internal`) | [0,02; 0,06; 0,12; 0,25; 0,55] |
| rozłożona (`distributed`) | [0,20; 0,20; 0,20; 0,20; 0,20] |

**Widok nieba:**

```
sky_view_factor = 0,5 · (1 + cos(tilt))
```

**Symulacja:**
- Krok czasowy: 1 godzina (3600 s)
- Inicjalizacja okresowa: do 20 cykli rozgrzewania, tolerancja zbieżności 0,01 K
- Sterowanie HVAC na temperaturze operacyjnej
- Rozwiązanie układu liniowego z cache'owaną odwrotnością macierzy dla unikalnych `H_ve`

### 3.2. Uproszczony model 5R1C (PN-EN ISO 13790)

**Plik:** `app/engine/thermal_balance.py`

**Charakter:** uproszczona sieć 5 rezystancji i 1 pojemności, używana jako fallback.

**Węzły:**
- powietrze (`theta_air`)
- powierzchnia (`theta_s`)
- masa (`T_m`)

**Rezystancje jednostkowe:**

| Rezystancja | Wartość | Jednostka | Plik |
|---|---|---|---|
| `H_IS` (powietrze ↔ powierzchnia) | 3,45 | W/(m²·K) | `thermal_balance.py:38` |
| `H_MS` (masa ↔ powierzchnia) | 9,1 | W/(m²·K) | `thermal_balance.py:39` |

**Geometria efektywna:**

| Wielkość | Wzór |
|---|---|
| Całkowita powierzchnia wewnętrzna `A_t` | 4,5 · `A_f` |
| Efektywna powierzchnia masy `A_m` | 2,5 · `A_f` |

**Klasy pojemności wewnętrznej kappa [kJ/(m²·K)] (ISO 13790 Tabela 12):**

| Klasa | kappa | Plik |
|---|---|---|
| Bardzo lekka | 80 | `thermal_balance.py:46` |
| Lekka | 110 | `thermal_balance.py:47` |
| Średnia (domyślna) | 165 | `thermal_balance.py:48` |
| Ciężka | 260 | `thermal_balance.py:49` |

Pojemność cieplna: `C_m = kappa · A_m · 1000` [J/K].

**Podział zysków ciepła (ISO 13790 Załącznik C.2):**

```
phi_ia = 0,5 · phi_int          (do powietrza)
phi_rest = 0,5 · phi_int + phi_sol
phi_m = (A_m / A_t) · phi_rest   (do masy)
phi_st = (1 − A_m/A_t − H_tr,w / (9,1 · A_t)) · phi_rest   (do powierzchni)
```

**Równanie różniczkowe (Crank-Nicolson na węźle masy, `dt = 3600 s`):**

Układ liniowy 3 równań rozwiązywany w postaci zamkniętej (bez iteracji).

### 3.3. Polska metodologia miesięczna (świadectwo charakterystyki)

**Plik:** `app/engine/polish_certificate_monthly.py`

**Charakter:** formalna metoda świadectwa, 12 miesięcy, model statyczny.

**Podstawa prawna:** Załącznik 1 do rozporządzenia Dz.U. 2015 poz. 376.

**Dni w miesiącu (`polish_certificate_monthly.py:45`):**

```
DAYS_PER_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
```

**Bilans energetyczny strefy (linia 349):**

Energia użytkowa ogrzewania:

```
Q_h,m = max(Q_tr,h,m + Q_ve,h,m − η_gains · Q_gains,m, 0)
```

Energia użytkowa chłodzenia:

```
Q_c,m = max(Q_gains,m − η_losses · (Q_tr,c,m + Q_ve,c,m), 0)
```

gdzie:
- `η_gains` — współczynnik wykorzystania zysków (ogrzewanie)
- `η_losses` — współczynnik wykorzystania strat (chłodzenie)
- `Q_gains,m = Q_sol,m + Q_int,m`

**Zyski słoneczne miesięczne (linia 119):**

```
Q_sol,m = Σ [A · (1 − f_frame) · g · f_shading · I_rad,m]
```

**Straty przez przenikanie (linia 174):**

```
Q_tr,m = Σ [A · U · (T_int − T_adj) · H_m / 1000]
```

Temperatura sąsiednia `T_adj` zależy od typu przestrzeni:
- `OUTDOOR` — temperatura zewnętrzna miesięczna
- `GROUND` — temperatura gruntu
- `UNHEATED_ZONE` — temperatura przestrzeni nieogrzewanej
- `HEATED_ZONE` — pomijane (brak transferu między równo kondycjonowanymi strefami)
- `CONSTANT_TEMPERATURE` — wartość stała elementu

**Straty wentylacyjne (linia 256):**

```
Q_ve,m = H_ve · (T_int − T_e) · H_m / 1000
H_ve = V_eff / 3600 · 1200   [W/K]
```

### 3.4. Projektowe obciążenie cieplne

**Pliki:** `app/engine/design_load.py` (PN-EN 12831-1), `app/engine/iso52016_design_load.py` (ISO 52016-1)

**Charakter:** moc projektowa [W], nie energia [kWh].

**Metoda PN-EN 12831-1 (`design_load.py`):**

```
Q_total = Q_tr + Q_ve + Q_heat_up
```

gdzie:
- `Q_tr = Σ A · U · max(T_int − T_design, 0) + (Σ ψ·L + Σ χ·n) · max(T_int − T_design, 0)`
- `Q_ve = H_ve · max(T_int − T_supply, 0)`
- `Q_heat_up` — moc rozgrzewcza (jeśli podana)

Temperatura projektowa zewnętrzna musi być podana jawnie (`outdoor_design_temperature_c`).

**Metoda ISO 52016-1 (`iso52016_design_load.py`):**

- Redukcja zysków wewnętrznych: `internal_gain_factor = 0,40`
- Minimalna inicjalizacja: 14 dni
- Pełna dostawa konwekcyjna: `hvac_convective_fraction = 1,0`
- Wynik: maksimum z ostatniego niepowtórzonego cyklu sekwencji projektowej

---

## 4. Stałe fizyczne

### 4.1. Woda (CWU)

| Stała | Wartość | Jednostka | Plik |
|---|---|---|---|
| Ciepło właściwe wody | 4,19 | kJ/(kg·K) | `systems.py:146` |
| Gęstość wody | 1,0 | kg/L | `systems.py:147` |
| Temperatura wody kranowej | 55,0 | °C | `systems.py:148` |
| Temperatura wody zimnej | 10,0 | °C | `systems.py:149` |
| Dni w roku | 365 | dni/rok | `systems.py:150` |
| Godziny w roku (zasobnik) | 8760 | h/rok | `systems.py:151` |

### 4.2. Powietrze

| Stała | Wartość | Jednostka | Plik |
|---|---|---|---|
| Objętościowe ciepło właściwe | 1200 | J/(m³·K) | `ventilation.py:25` |
| Gęstość | 1,2 | kg/m³ | `climate.py:24` |
| Ciepło właściwe masowe | 1005 | J/(kg·K) | `climate.py:25` |

### 4.3. Przegrody

| Stała | Wartość | Jednostka | Plik |
|---|---|---|---|
| Opór powierzchni zewnętrznej `R_se` | 0,04 | m²·K/W | `envelope.py:30` |
| Amplituda temperatury gruntu | 5,0 | K | `envelope.py:24` |
| Opóźnienie temperatury gruntu | 1460 | h (~2 miesiące) | `envelope.py:25` |

---

## 5. Stałe normatywne — sprawności systemów

### 5.1. Sprawność generacji ogrzewania/chłodzenia (tabele 2–26 rozporządzenia)

**Plik:** `app/engine/systems.py`, linie 19–42

| Typ źródła | ηH,g / COP / SEER | Plik |
|---|---|---|
| Elektryczne bezpośrednie | 0,99 | `systems.py:20` |
| Kocioł gazowy | 0,87 | `systems.py:21` |
| Kocioł gazowy kondensacyjny | 0,94 | `systems.py:22` |
| Kocioł olejowy | 0,87 | `systems.py:23` |
| Kocioł na biomasę | 0,70 | `systems.py:24` |
| Kocioł węglowy | 0,82 | `systems.py:25` |
| Kominek | 0,70 | `systems.py:26` |
| Pompa ciepła powietrze | 3,0 | `systems.py:27` |
| Pompa ciepła grunt | 4,0 | `systems.py:28` |
| Pompa ciepła woda | 4,0 | `systems.py:29` |
| Ciepłownia | 0,98 | `systems.py:30` |
| Klimatyzator split | 3,9 | `systems.py:31` |
| Multisplit/VRV | 4,1 | `systems.py:32` |
| Chiller powietrzny | 4,0 | `systems.py:34` |
| Chiller wodny | 5,6 | `systems.py:35` |
| Pasywne chłodzenie gruntowe | 10,0 | `systems.py:36` |
| Chłodzenie absorpcyjne | 0,8 | `systems.py:37` |

### 5.2. Sprawność generacji CWU (tabela 6 metodologii)

**Plik:** `app/engine/systems.py`, linie 47–54

| Typ źródła | ηW,g | Plik |
|---|---|---|
| Kocioł gazowy | 0,83 | `systems.py:48` |
| Kocioł gazowy kondensacyjny | 0,85 | `systems.py:49` |
| Pompa ciepła powietrze | 2,6 | `systems.py:50` |
| Pompa ciepła grunt | 3,0 | `systems.py:51` |
| Pompa ciepła woda | 3,0 | `systems.py:52` |
| Ciepłownia | 0,97 | `systems.py:53` |
| Elektryczny zasobnikowy | 0,96 | `systems.py:39` |
| Elektryczny przepływowy | 0,99 | `systems.py:40` |
| Gazowy przepływowy | 0,85 | `systems.py:41` |

### 5.3. Sprawność całkowita systemu

```
η_total = η_generacji · η_dystrybucji · η_magazynowania · η_regulacji
```

Funkcja `total_system_efficiency()` w `app/engine/systems.py`.

---

## 6. Stałe normatywne — ciepła woda użytkowa

### 6.1. Profile zużycia CWU (tabela 27 rozporządzenia)

**Plik:** `app/engine/systems.py`, linie 237–247

Parametry: (`V_d` — jednostkowe zużycie wody [dm³/(m²·d)], `β` — udział użytkowania)

| Profil | `V_d` | `β` | Plik |
|---|---|---|---|
| Mieszkalny jednorodzinny | 1,40 | 0,90 | `systems.py:238` |
| Mieszkalny wielorodzinny (ryczałt) | 2,00 | 0,90 | `systems.py:239` |
| Mieszkalny wielorodzinny (indywidualne liczniki) | 1,60 | 0,90 | `systems.py:240` |
| Biuro | 0,35 | 0,70 | `systems.py:241` |
| Edukacja | 0,80 | 0,55 | `systems.py:242` |
| Ochrona zdrowia | 6,50 | 1,00 | `systems.py:243` |
| Handel i usługi | 0,60 | 0,78 | `systems.py:244` |
| Zbiorowe mieszkalne | 3,75 | 0,60 | `systems.py:245` |
| Magazyn | 0,10 | 0,70 | `systems.py:246` |

**Wzór na roczne zapotrzebowanie użyteczne CWU:**

```
Q_W,nd = V_d · A_f · ρ · c_p · (T_tap − T_cold) · 365 / 1000   [kWh/rok]
```

### 6.2. Straty zasobnika CWU (tabela 13 rozporządzenia)

**Plik:** `app/engine/systems.py`, linie 157–174

Jednostkowa strata ciepła `q_S` [W/dm³] zależy od:
- lokalizacji zasobnika (ogrzewana / nieogrzewana przestrzeń),
- pojemności zasobnika [dm³],
- grubości izolacji (100 mm / 50 mm / 20 mm / elektryczny / gazowy).

Pełna tabela zawiera 72 wartości. Przykładowe wartości dla zasobnika 200 dm³, izolacja 100 mm:

| Lokalizacja | `q_S` [W/dm³] |
|---|---|
| Nieogrzewana | 0,34 |
| Ogrzewana | 0,28 |

**Roczne straty zasobnika (wzór 30):**

```
ΔQ_W,s = q_S · V_storage · t_sW / 1000   [kWh/rok]
```

gdzie `t_sW = 8760 h/rok`.

### 6.3. Sprawność całkowita CWU

```
ηW,tot = ηW,g · ηW,s · ηW,d · ηW,e
```

Gdy podano jawną pojemność zasobnika, straty postoju są liczone z tabeli 13, a `ηW,tot` jest wyznaczana jako:

```
ηW,tot = Q_W,nd / E_k,DHW
```

(wartość efektywna, nie iloczyn czterech sprawności sezonowych).

---

## 7. Stałe normatywne — zyski wewnętrzne

### 7.1. Gęstość zysków (tabela 26 rozporządzenia)

**Plik:** `app/engine/internal_gains.py`, linie 34–67

| Typ budynku | `q_int` [W/m²] | Plik |
|---|---|---|
| Mieszkalny jednorodzinny | 6,8 | `internal_gains.py:56` |
| Mieszkalny wielorodzinny | 7,1 | `internal_gains.py:55` |
| Biuro | 12,8·β + 1,6·(1−β) | `internal_gains.py:60` |
| Edukacja | 12,0·β + 1,0·(1−β) | `internal_gains.py:62` |
| Ochrona zdrowia | 8,0 | `internal_gains.py:64` |
| Handel | 10,0·β + 1,0·(1−β) | `internal_gains.py:66` |
| Inne | 6,8 (fallback mieszkalny) | `internal_gains.py:67` |

gdzie `β` — udział użytkowania (domyślnie 0,3, `internal_gains.py:25`).

### 7.2. Stałe zysków

| Stała | Wartość | Jednostka | Plik |
|---|---|---|---|
| Ciepło osoby | 80,0 | W/osoba | `internal_gains.py:26` |
| Domyślna gęstość obsadzenia | 0,03 | osoba/m² | `internal_gains.py:27` |
| Domyślny udział użytkowania `β` | 0,3 | — | `internal_gains.py:25` |

### 7.3. Podział na źródła (linia 70)

```
q_occupancy = min(q_int, 80 · 0,03) = min(q_int, 2,4)   [W/m²]
reszta = q_int − q_occupancy
q_lighting = 0,3 · reszta
q_equipment = 0,7 · reszta
```

### 7.4. Harmonogramy

Trzy typy harmonogramów (`ScheduleType`):

| Typ | Opis |
|---|---|
| `CONSTANT` | Stała wartość (domyślnie 1,0) |
| `WEEKDAY_WEEKEND` | Profil dzień roboczy + profil weekend (niedziela) |
| `HOURLY_PROFILE` | 24 wartości na dzień roboczy, opcjonalnie sobota i niedziela |

Dla `HOURLY_PROFILE`:
- brak profilu soboty → powielenie profilu dnia roboczego,
- brak profilu niedzieli → powielenie profilu dnia roboczego,
- profil z samymi zerami → brak aktywności tego dnia (różne od powielenia).

---

## 8. Stałe normatywne — wentylacja i infiltracja

### 8.1. Normatywne strumienie powietrza (tabele 24/25 rozporządzenia)

**Plik:** `app/engine/ventilation.py`, linie 30–40

| Profil | Strumień [m³/(s·m²)] | Tabela |
|---|---|---|
| Mieszkalny jednorodzinny | 0,31·10⁻³ | 24 |
| Mieszkalny wielorodzinny (ryczałt) | 0,31·10⁻³ | 24 |
| Mieszkalny wielorodzinny (liczniki) | 0,31·10⁻³ | 24 |
| Biuro | 0,56·10⁻³ | 25 |
| Edukacja | 0,56·10⁻³ | 25 |
| Ochrona zdrowia | 0,42·10⁻³ | 25 |
| Handel i usługi | 0,33·10⁻³ | 25 |
| Zbiorowe mieszkalne | 0,42·10⁻³ | 25 |
| Magazyn | 0,08·10⁻³ | 25 |

### 8.2. Infiltracja normatywna

**Plik:** `app/engine/ventilation.py`, linia 47

| Rok budowy | `n_inf` [1/h] |
|---|---|
| ≤ 1995 | 0,3 |
| > 1995 | 0,2 |

### 8.3. Redukcja nawiewu/wywiewu

| Stała | Wartość | Plik |
|---|---|---|
| `SUPPLY_EXTRACT_FLOW_REDUCTION` | 0,75 | `ventilation.py:42` |

Stosowana gdy strumień nawiewu i wywiewu różnią się — domyślny współczynnik redukcji dla wentylacji mechanicznej.

### 8.4. Współczynnik przenikania ciepła wentylacji

```
H_ve = (V_mech + V_ext) / 3600 · 1200   [W/K]
```

### 8.5. Temperatura nawiewu efektywna

| Rodzaj wentylacji | Temperatura nawiewu |
|---|---|
| Naturalna, wywiewna, mechaniczna bez odzysku | temperatura zewnętrzna `T_e` |
| Mechaniczna z odzyskiem (model uproszczony) | liczona z `η_rec`: `T_supply = T_e + η_rec · (T_int − T_e)` |
| Mechaniczna z odzyskiem (model szczegółowy) | liczona z `heat_recovery_state()` |
| Jawna temperatura nawiewu | stała wartość podana przez użytkownika |

**Ważne:** pole `supply_temperature` zastępuje model odzysku ciepła. Wpisanie temperatury wewnętrznej (np. 20°C) jest błędem — pole opisuje temperaturę powietrza dostarczanego do strefy, a nie temperaturę w pomieszczeniu.

---

## 9. Stałe normatywne — energia pomocnicza

### 9.1. Energia pomocnicza ogrzewania (tabela 20 rozporządzenia)

**Plik:** `app/engine/systems.py`, linie 300–339

Parametry: (`P_spec` — moc jednostkowa [W/m²], `t_op` — czas pracy [h/rok])

| System | Powierzchnia | `P_spec` | `t_op` | Wiersz tabeli |
|---|---|---|---|---|
| Kocioł gazowy | ≤ 250 m² | 0,50 | 2520 | 7 |
| Kocioł gazowy | > 250 m² | 0,15 | 3900 | 7 |
| Pompa ciepła woda | — | 0,70 | 1600 | — |
| Pompa ciepła grunt | — | 0,45 | 1600 | — |
| Ciepłownia | — | 0,09 | 8760 | 10 |
| Ogrzewanie grzejnikowe | ≤ 250 m² | 0,30 | 5700 | 1–2 |
| Ogrzewanie grzejnikowe | > 250 m² | 0,15 | 4700 | 1–2 |
| Ogrzewanie powierzchniowe | ≤ 250 m² | 0,50 | 6700 | 1–2 |

**Wzór:**

```
E_el,pom,H = P_spec · A_f · t_op   [Wh/rok]
```

### 9.2. Energia pomocnicza CWU (tabela 20 rozporządzenia)

**Plik:** `app/engine/systems.py`, linie 342–369

| System | Powierzchnia | `P_spec` | `t_op` | Wiersz |
|---|---|---|---|---|
| Kocioł gazowy + zasobnik | ≤ 250 m² | 1,40 | 310 | 6 |
| Kocioł gazowy + zasobnik | > 250 m² | 0,50 | 410 | 6 |
| Kocioł gazowy bez zasobnika | ≤ 250 m² | 0,25 | 270 | 4 |
| Kocioł gazowy bez zasobnika | > 250 m² | 0,20 | 580 | 4 |
| Pompa ciepła woda | — | 0,70 | 400 | — |
| Pompa ciepła grunt | — | 0,45 | 400 | — |
| Ciepłownia | — | 0,09 | 8760 | 10 |
| Cyrkulacja CWU | ≤ 250 m² | 0,15 | 8760 | 3 |
| Cyrkulacja CWU | > 250 m² | 0,04 | 7300 | 3 |

### 9.3. Energia pomocnicza wentylacji (tabela 20 rozporządzenia)

**Plik:** `app/engine/systems.py`, linie 372–379

| Rodzaj wentylacji | Wymiana [1/h] | Moc [W/m²] | Wiersz |
|---|---|---|---|
| Mechaniczna | ≤ 0,6 | 0,50 | 12 |
| Mechaniczna | > 0,6 | 1,30 | 12 |
| Wywiewna/hybrydowa | ≤ 0,6 | 0,40 | 13 |
| Wywiewna/hybrydowa | > 0,6 | 0,90 | 13 |

Czas pracy wentylatorów: `t_fan = 8760 · β` [h/rok].

### 9.4. Nadpisywanie energii pomocniczej

Użytkownik może podać jawną wartość `auxiliary_energy_kwh_year`:
- **puste pole** — stosowana wartość normatywna z tabeli 20,
- **zero** — brak energii pomocniczej,
- **wartość > 0** — nadpisuje wartość normatywną.

---

## 10. Stałe normatywne — energia pierwotna i emisje

### 10.1. Współczynniki energii pierwotnej

**Plik:** `app/schemas/models.py`, linie 509–537

Współczynniki `fp` (nieodnawialna energia pierwotna) i `we` (emisja CO₂) są **parametrami wejściowymi użytkownika**, a nie stałymi w silniku. Wartości domyślne zgodne z tabelą 1 rozporządzenia Dz.U. 2023 poz. 697:

| Nośnik energii | `fp` | `we` [kgCO₂/kWh] |
|---|---|---|
| Energia elektryczna | 2,5 | 0,6 |
| Gaz ziemny | 1,1 | 0,20 |
| LPG | 1,1 | 0,20 |
| Olej opałowy | 1,1 | 0,27 |
| Węgiel kamienny | 1,1 | 0,34 |
| Węgiel brunatny | 1,1 | 0,34 |
| Ciepło sieciowe | 1,2 | 0,25 |
| Biomasa | 0,2 | 0,05 |
| Biogaz | 0,5 | 0,05 |
| Energia słoneczna | 0,0 | 0,0 |
| Energia wiatrowa | 0,0 | 0,0 |
| Geotermia | 0,0 | 0,0 |

### 10.2. Wzory

**Nieodnawialna energia pierwotna:**

```
Ep = Σ E_k,i · fp,i   [Wh/rok]
```

**Emisja CO₂:**

```
EC = Σ (E_k,i / 1000) · we,i / 1000   [t/rok]
```

**Udział OZE:**

```
U_OZE = 100 · E_renewable / E_total   [%]
```

Nośniki odnawialne: biomasa, biogaz, solar, wiatr, geotermia, odnawialna.

---

## 11. Mostki cieplne

Mostki cieplne są obliczane w locie w trzech modułach:

### 11.1. Metoda miesięczna (`polish_certificate_monthly.py:213`)

```
H_bridge = Σ ψ_i · L_i + Σ χ_j · n_j   [W/K]
Q_bridge,m = H_bridge · (T_int − T_e) · H_m / 1000   [kWh]
```

### 11.2. Model godzinowy ISO 52016 (`iso52016_hourly.py:223`)

Mostki dodawane do macierzy przewodnictwa jako dodatkowe przewodnictwo na węzeł powietrza. Temperatura graniczna zależy od typu przestrzeni sąsiedniej. Pomijane dla `HEATED_ZONE` (przegrody między równo kondycjonowanymi strefami).

### 11.3. Obciążenie projektowe (`design_load.py:182`)

```
Q_bridge = (Σ ψ·L + Σ χ·n) · max(T_int − T_design, 0)   [W]
```

---

## 12. Zyski słoneczne

**Plik:** `app/engine/solar.py`

### 12.1. Promieniowanie na powierzchni pochylonej

Model **Hay-Davies** (implementacja `pvlib` z fallbackiem NumPy w `climate.py:337`).

```
cos(θ) = cos(zenith)·cos(tilt) + sin(zenith)·sin(tilt)·cos(az_sun − az_surf)
I_direct = DNI · max(cos(θ), 0)
```

### 12.2. Zyski przez elementy przezroczyste (linia 51)

```
Q_sol = A · (1 − f_frame) · g · f_shading · I_effective
```

gdzie `I_effective = I_diffuse + I_direct · modifier(θ)`, a `modifier(θ)` jest wielomianem w kącie padania.

### 12.3. Absorpcja przez elementy nieprzezroczyste (linia 109)

Efekt sol-air:

```
Q_in = A · α · U · R_se · I_surf
```

gdzie `α` — absorpcyjność słoneczna (domyślnie 0,6), `R_se = 0,04 m²·K/W`.

Dla dobrze izolowanej ściany (U ≈ 0,2) około 0,8% absorbowanej energii dociera do wnętrza.

### 12.4. Rozkład promieniowania między powierzchnie

Domyślnie: proporcjonalnie do powierzchni. Można podać jawną mapę `solar_distribution` (musi sumować się do 1).

---

## 13. Odzysk ciepła z wentylacji

**Plik:** `app/engine/heat_recovery.py`

### 13.1. Model szczegółowy

Funkcja `heat_recovery_state()` (linia 111) oblicza godzinowo:

- **Krzywą sprawności** od temperatury zewnętrznej (`efficiency_curve`)
- **Bypass letni** (`summer_bypass`) — wyłączenie odzysku gdy `T_e` w zakresie `[bypass_min, bypass_max]`
- **Ochronę przed szronem** (`frost_strategy`):
  - `disable_recovery` — wyłączenie odzysku
  - `reduce_recovery` — redukcja sprawności
  - `preheater` — nagrzewnica wstępna (`preheater_max_power_w`)
- **Temperaturę punktu rosy** — aproksymacja Magnusa (`dew_point_temperature_c`, linia 51)

### 13.2. Wynik

`HeatRecoveryState`:
- `supply_temperature_c` — temperatura nawiewu [°C]
- `exhaust_outlet_temperature_c` — temperatura wyrzutu [°C]
- `effective_efficiency` — efektywna sprawność [-]
- `bypass_active` — czy bypass aktywny
- `frost_risk` — czy ryzyko szronu
- `preheater_power_w` — moc nagrzewnicy wstępnej [W]

### 13.3. Parametry szczegółowe (`normative_models.py:83`)

| Parametr | Opis |
|---|---|
| `efficiency_curve` | Krzywa sprawności od temperatury zewnętrznej |
| `summer_bypass_enabled` | Włączenie bypassu letniego |
| `bypass_min_outdoor_c` | Dolna granica temperatury bypassu |
| `bypass_max_outdoor_c` | Górna granica temperatury bypassu |
| `frost_strategy` | Strategia ochrony przed szronem |
| `frost_exhaust_limit_c` | Limit temperatury wyrzutu |
| `indoor_relative_humidity` | Wilgotność wewnętrzna |
| `preheater_max_power_w` | Moc nagrzewnicy wstępnej |
| `preheater_efficiency` | Sprawność nagrzewnicy |

---

## 14. API

### 14.1. `POST /api/calculate`

**Przyjmuje:** `BuildingProject` — pełny model projektu budynku.

**Zwraca:** `CalculationResult`:
- `design_heating_power_kw` — projektowa moc grzewcza [kW]
- `annual_indicators` — roczne wskaźniki (Eu, Ek, Ep, ec, U_OZE, ηW,tot, energia pomocnicza)
- `monthly` — wyniki miesięczne (metoda świadectwa)
- `hourly` — wyniki godzinowe (model ISO 52016, opcjonalnie)
- `compliance` — sprawdzenie wymagań WT

**Kody błędów:**
- 404 — brak pliku EPW dla stacji
- 422 — brakujące lub niejednoznaczne dane modelowania
- 500 — inne błędy

### 14.2. `GET /api/climate/stations`

Zwraca listę dostępnych stacji TMY z polami: `id`, `name`, `latitude`, `longitude`.

### 14.3. `GET /api/climate/resolve-location?location=...`

Geokoduje adres (Open-Meteo API) i zwraca najbliższą stację TMY z odległością w kilometrach.

### 14.4. `GET /api/climate/stations/{station_id}/summary`

Zwraca roczne podsumowanie stacji: średnia/maks/min temperatura, roczne promieniowanie poziome [kWh/m²].

---

## Podsumowanie źródeł danych

| Dane | Źródło | Plik |
|---|---|---|
| Dane klimatyczne godzinowe | TMY/EPW (NCEI ISD / ERA5, 2009–2023) | `backend/data/tmy/*.epw` |
| Geokodowanie adresów | Open-Meteo Geocoding API | `app/api/climate.py` |
| Sprawności systemów | Tabele 2–26 rozporządzenia Dz.U. 2015 poz. 376 | `app/engine/systems.py` |
| Profile CWU | Tabela 27 rozporządzenia | `app/engine/systems.py` |
| Straty zasobnika CWU | Tabela 13 rozporządzenia | `app/engine/systems.py` |
| Zyski wewnętrzne | Tabela 26 rozporządzenia | `app/engine/internal_gains.py` |
| Strumienie powietrza | Tabele 24/25 rozporządzenia | `app/engine/ventilation.py` |
| Energia pomocnicza | Tabela 20 rozporządzenia | `app/engine/systems.py` |
| Współczynniki energii pierwotnej | Tabela 1 rozporządzenia Dz.U. 2023 poz. 697 | `app/schemas/models.py` |
| Model godzinowy | PN-EN ISO 52016-1:2017 | `app/engine/iso52016_hourly.py` |
| Model uproszczony 5R1C | PN-EN ISO 13790:2008 | `app/engine/thermal_balance.py` |
| Metoda miesięczna | Załącznik 1 do rozporządzenia Dz.U. 2015 poz. 376 | `app/engine/polish_certificate_monthly.py` |
| Obciążenie projektowe | PN-EN 12831-1:2017 | `app/engine/design_load.py` |
| Opory powierzchni | PN-EN ISO 6946:2017 | `app/engine/envelope.py` |

---

*Uwaga: Wszystkie wartości normatywne pochodzą z aktów prawnych wskazanych w sekcji 1. W przypadku zmian w rozporządzeniach lub normach, stałe w kodzie muszą zostać zaktualizowane i pokryte testami jednostkowymi z porównaniem do wartości analitycznej.*
