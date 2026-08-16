# Metodologia obliczeń

## Cel dokumentu

Opis metodologii stosowanej w silniku obliczeniowym `energoliczydlo` do wyznaczania charakterystyki energetycznej budynków. Silnik implementuje metodę godzinową z normy **PN-EN ISO 52016-1** oraz uwzględnia polską metodologię wyznaczania charakterystyki energetycznej budynku lub części budynku (rozporządzenie Ministra Infrastruktury i Rozwoju z dnia 27 lutego 2015 r. w sprawie metodologii wyznaczania charakterystyki energetycznej budynku lub części budynku oraz świadectw charakterystyki energetycznej, z późn. zm.).

## Normy i dokumenty źródłowe

- PN-EN ISO 52016-1:2017/2020 – *Energetyczne właściwości użytkowe budynków – Zapotrzebowanie na energię do ogrzewania i chłodzenia, wewnętrzne temperatury oraz jawne i utajone obciążenia cieplne – Część 1: Procedury obliczania*
- PN-EN ISO 52010-1:2018 – dane klimatyczne i promieniowanie słoneczne
- PN-EN ISO 12831-3 – instalacje ciepłej wody użytkowej
- EN 15316-1, EN 15316-2, EN 15316-4 – systemy grzewcze, chłodnicze i generacja
- Rozporządzenie w sprawie metodologii charakterystyki energetycznej (Dz.U. 2015 poz. 376 z późn. zm.)

## Założenia metodologiczne

1. Obliczenia prowadzone są z krokiem **godzinowym** przez cały rok (8760 godzin).
2. Budynek dzielony jest na **strefy termiczne** (ogrzewane, chłodzone, nieogrzewane).
3. Dla każdej strefy prowadzony jest bilans ciepła uwzględniający:
   - straty przez przenikanie,
   - straty przez wentylację,
   - zyski wewnętrzne,
   - zyski od nasłonecznienia,
   - pojemność cieplną budynku.
4. System ogrzewania / chłodzenia włącza się, gdy temperatura wewnętrzna wykracza poza zadany zakres komfortu.
5. Wynikiem końcowym są roczne wskaźniki `Eu`, `Ek`, `Ep` oraz ewentualnie `EC` i `Uoze`.

## Bilans ciepła strefy (uproszczony zapis koncepcyjny)

Dla każdej godziny `t` i strefy `z`:

```
Q_bal(t) = Q_int(t) + Q_sol(t) - Q_tr(t) - Q_ve(t) + Q_H(t) - Q_C(t)
```

gdzie:
- `Q_int(t)` – zyski ciepła od wewnętrznych źródeł (ludzie, oświetlenie, sprzęt),
- `Q_sol(t)` – zyski ciepła od nasłonecznienia (przez okna i pochłonięte przez przegrody),
- `Q_tr(t)` – straty ciepła przez przenikanie przez przegrody,
- `Q_ve(t)` – straty ciepła przez wentylację i infiltrację,
- `Q_H(t)` – energia dostarczona przez ogrzewanie (≥ 0),
- `Q_C(t)` – energia odjęta przez chłodzenie (≥ 0).

Temperatura wewnętrzna `T_int(t)` wyznaczana jest z równania bilansu ciepła z uwzględnieniem pojemności cieplnej `C_m`:

```
C_m · (T_int(t) - T_int(t-1)) / Δt = Q_bal(t)
```

Po obliczeniu `T_int(t)`:
- jeśli `T_int(t) < T_int,H,set` → `Q_H(t) = (T_int,H,set - T_int(t)) · (H_tr + H_ve)` oraz korekta `T_int(t) = T_int,H,set`,
- jeśli `T_int(t) > T_int,C,set` → `Q_C(t) = (T_int(t) - T_int,C,set) · (H_tr + H_ve)` oraz korekta `T_int(t) = T_int,C,set`.

Dokładna forma równania zgodna z PN-EN ISO 52016-1 (model wielowęzłowy lub uproszczony 5R1C) jest implementowana w module `thermal_balance`.

## Straty przez przenikanie

Dla każdej przegrody `j`:

```
Q_tr,j(t) = A_j · U_j · (T_int(t) - T_adj,j(t))
```

- `A_j` – powierzchnia przegrody [m²],
- `U_j` – współczynnik przenikania ciepła [W/(m²·K)],
- `T_adj,j(t)` – temperatura przestrzeni sąsiedniej (zewnętrzna, grunt, nieogrzewana strefa).

Poprawki na mostki cieplne:

```
ΣQ_bridges = Σ(l_k · Ψ_k) · ΔT + Σ(χ_n) · ΔT
```

gdzie `Ψ_k` – liniowy współczynnik mostka cieplnego [W/(m·K)], `χ_n` – punktowy [W/K].

## Straty przez wentylację

```
H_ve = ρ_a · c_pa · q_v
Q_ve(t) = H_ve · (T_int(t) - T_e(t))
```

- `ρ_a` – gęstość powietrza [kg/m³], przyjmowana 1.2 kg/m³,
- `c_pa` – ciepło właściwe powietrza [J/(kg·K)], przyjmowane 1005 J/(kg·K),
- `q_v` – strumień powietrza wentylacyjnego [m³/s], z uwzględnieniem odzysku ciepła: `q_v,net = q_v · (1 - η_rec)`.

## Zyski od nasłonecznienia

1. Dla każdej godziny obliczane są położenie słońca (azymut, kąt wysokości) na podstawie długości i szerokości geograficznej stacji.
2. Promieniowanie słoneczne na powierzchni poziomej z pliku TMY/EPW dzielone jest na bezpośrednie `I_dir` i rozproszone `I_dif` (lub modelowane metodą Perez).
3. Dla powierzchni pochylonej (okno, ściana) o azymucie `γ` i nachyleniu `β`:
   ```
   I_surface = I_dir · cos(θ) / cos(θ_z) + I_dif · R_dif + I_ref · R_ref
   ```
4. Zyski przez okno:
   ```
   Q_sol,win = A_win · g_total · I_surface · F_sh
   ```
   `g_total` – całkowity współczynnik przepuszczania energii słonecznej; `F_sh` – czynnik ekranowania.
5. Zyski pochłonięte przez przegrody nieprzezroczyste są częściowo opóźnione (pojemność cieplna) zgodnie z modelem węzłowym.

## Zyski wewnętrzne

Zyski od osób, oświetlenia i sprzętu obliczane są zgodnie z harmonogramem użytkowania:

```
Q_int(t) = φ_occ(t) · q_occ · A_floor + φ_light(t) · q_light · A_floor + φ_equip(t) · q_equip · A_floor
```

- `φ(t)` – współczynnik jednoczesności (0–1) dla danej godziny,
- `q` – gęstość obciążenia [W/m² powierzchni podłogi].

## Systemy techniczne i energia końcowa

Dla każdej godziny:

```
E_k,H(t) = Q_H(t) / η_H(t)
E_k,C(t) = Q_C(t) / η_C(t)
```

Sprawności / COP mogą zależeć od temperatury zewnętrznej i obciążenia (dla pomp ciepła).

Ciepła woda użytkowa:
- roczne zapotrzebowanie `Q_W,annual` obliczane zgodnie z PN-EN ISO 12831-3 lub na podstawie profilu godzinowego,
- podział na godziny zgodnie z harmonogramem poboru wody.

## Energia pierwotna i emisje

```
E_p = Σ (E_k,i · f_p,i)
E_C = Σ (E_k,i · W_e,i)
```

- `f_p,i` – współczynnik przeliczenia energii końcowej `i` na energię pierwotną,
- `W_e,i` – wskaźnik emisji CO₂ dla nośnika `i`.

Wartości domyślne pochodzą z polskich aktów wykonawczych / KOBiZE i są przechowywane w pliku konfiguracyjnym `data/primary_energy_factors.json`.

## Ocena zgodności

Aplikacja porównuje obliczone wskaźniki `Eu`, `Ek`, `Ep` z wymaganiami prawnymi dla danego typu budynku (np. WT 2021). Wynikiem jest status `PASS` / `FAIL` z uzasadnieniem.

## Ograniczenia i założenia MVP

- Obliczenia dotyczą ciepła jawnego (sensible); wilgotność i obciążenia utajone nie są uwzględniane.
- Strefy termiczne traktowane są jako jednorodne pod względem temperatury (brak CFD).
- Domyślnie przyjmuje się dane TMYx z `climate.onebuilding.org`; wersja produkcyjna powinna wykorzystywać oficjalne polskie dane TLY / TMY (np. z projektu TLM2000).
- Przypadki, w których norma dopuszcza wiele wariantów obliczeń, są parametryzowane i jawnie udokumentowane.

## Benchmarki

Wyniki silnika porównywane są z:
- ręcznie zweryfikowanymi przykładami użytkownika,
- biblioteką `pyBuildingEnergy` (tam gdzie możliwe),
- przypadkami testowymi BESTEST.
