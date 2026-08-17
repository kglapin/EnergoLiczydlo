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

Zgodnie z § 5.1 metodologii energia użytkowa jest sumą `QH,nd + QW,nd + QC,nd`.
Energia wbudowanego oświetlenia `Qk,L` oraz energia pomocnicza `Eel,pom` należą
do energii końcowej/pierwotnej i nie zwiększają `Eu`.

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

Dokładna forma równania zgodna z PN-EN ISO 52016-1 (uproszczona godzinowa
metoda sieci 5R1C wg ISO 13790 Annex C / ISO 52016-1) jest implementowana w
module `thermal_balance`. Sieć łączy węzły powietrza, powierzchni wewnętrznych
i masy termicznej przez H_ve, H_tr,is = 3,45·A_t, H_tr,w (okna), H_tr,ms = 9,1·A_m
i H_tr,em = 1/(1/H_tr,op − 1/H_tr,ms), przy domyślnych relacjach A_t = 4,5·A_f
i A_m = 2,5·A_f. Zyski dzielone są na węzły: Φ_ia = 0,5·Φ_int oraz Φ_m i Φ_st
proporcjonalnie do A_m/A_t (formuły C.2 normy). Równania węzłów rozwiązywane
są jednocześnie jako układ liniowy z dyskretyzacją Cranka–Nicolsona węzła
masy; zapotrzebowanie Φ_HC wynika z rozwiązania zamkniętego (bez iteracji).
Elementy przyległe do gruntu, przestrzeni nieogrzewanych i o stałej
temperaturze napędzane są własnymi temperaturami (grunt: sinusoida
średnioroczna z opóźnieniem ~2 mies.), a przegrody między strefami o tej
samej temperaturze nie przenoszą ciepła.

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
Q_ve(t) = H_ve · (T_int(t) - T_sup(t))
```

- `ρ_a·c_pa` – objętościowa pojemność cieplna powietrza, przyjmowana w silniku
  jako normowa wartość `1200 J/(m³·K)`,
- `q_v` – strumień powietrza wentylacyjnego [m³/s], z uwzględnieniem odzysku
  ciepła. W trybie okresowym strumień jest liczony godzinowo z profilu pracy;
  jeśli profilu nie podano, `β` jest jawnym przybliżeniem stałego strumienia
  uśrednionego w czasie.
- `T_sup` – temperatura powietrza nawiewanego; jeśli nie została podana,
  przyjmuje się `T_e` i stosuje równoważną redukcję strumienia `1−η`.
  Podanie rzeczywistej temperatury po centrali zastępuje tę redukcję, aby
  odzysk ciepła nie został uwzględniony podwójnie.

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
5. Zyski pochłonięte przez przegrody nieprzezroczyste: promieniowanie pochłone
   podnosi temperaturę powierzchni zewnętrznej (efekt sol-air), a dodatkowy
   przepływ do wewnątrz wynosi `q_in = A·α·U·R_se·I` (R_se = 0,04 m²K/W wg
   PN-EN ISO 6946). Dla dobrze ocieplonych przegród to ~0,8% pochłoniętego
   promieniowania; opóźnienie wynika z podziału zysków i pojemności cieplnej
   sieci 5R1C.

## Zyski wewnętrzne (wartości normowe)

Domyślne gęstości zysków wewnętrznych pochodzą z tabeli 26 rozporządzenia
(Dz.U. 2015 poz. 376): jednorodzinny 6,8 W/m², wielorodzinny 7,1 W/m²,
biurowy 5,7 W/m² (przykład standardowy P₁=0,6, β=0,3), pozostałe wiersze
wg wzorów q = a·β + b·(1−β) przy β = 0,3. Wartości są edytowalne w UI.

## Zyski wewnętrzne

Zyski od osób, oświetlenia i sprzętu obliczane są zgodnie z harmonogramem użytkowania:

```
Q_int(t) = φ_occ(t) · q_occ · A_floor + φ_light(t) · q_light · A_floor + φ_equip(t) · q_equip · A_floor
```

- `φ(t)` – współczynnik jednoczesności (0–1) dla danej godziny,
- `q` – gęstość obciążenia [W/m² powierzchni podłogi].

Wartość normowa `q_int` z tabeli 26 jest wartością uśrednioną. Dla pełnego
modelu godzinowego należy przekazać osobne harmonogramy `Schedule` dla osób,
oświetlenia i wyposażenia. Brak harmonogramu oznacza stałe wykorzystanie i nie
odtwarza rzeczywistych godzin użytkowania.

## Systemy techniczne i energia końcowa

Dla godzinowego bilansu zapotrzebowania:

```
Q_H(t), Q_C(t) = wynik godzinowego bilansu 5R1C
```

Końcowa energia systemów jest następnie wyznaczana z sezonowych sprawności
całkowitych `ηH,tot` i `ηC,tot` zgodnie z metodologią. Silnik nie tworzy
samodzielnie krzywej COP z temperatury zewnętrznej; jeśli projekt ma zweryfikowaną
charakterystykę godzinową producenta, wymaga ona osobnego, jawnego modelu danych.

Ciepła woda użytkowa:
- roczne zapotrzebowanie `Q_W,annual` obliczane jest z profilu normowego tabeli 27
  rozporządzenia,
- obecna implementacja rozdziela tę roczną wartość równomiernie na 8760 godzin;
  nie udaje pełnego godzinowego modelu poboru CWU.

## Energia pierwotna i emisje

```
E_p = Σ (E_k,i · f_p,i)
E_C = Σ (E_k,i · W_e,i)
```

- `f_p,i` – współczynnik przeliczenia energii końcowej `i` na energię pierwotną,
- `W_e,i` – wskaźnik emisji CO₂ dla nośnika `i`.

Wartości domyślne pochodzą z polskich aktów wykonawczych / konfiguracji projektu.
Wymagają kontroli i aktualizacji dla konkretnej daty sporządzenia świadectwa;
nie są samodzielnym dowodem aktualności danych KOBiZE.

## Ocena zgodności

Aplikacja pokazuje informacyjne kontrole wskaźników. Nie należy ich traktować
jak formalnego porównania z WT ani jako prawnego statusu `PASS` / `FAIL`;
aktualne wymagania zależą od zakresu oceny, daty i podstawy prawnej.

## Ograniczenia i założenia MVP

- Obliczenia dotyczą ciepła jawnego (sensible); wilgotność i obciążenia utajone nie są uwzględniane.
- Strefy termiczne traktowane są jako jednorodne pod względem temperatury (brak CFD).
- Domyślnie przyjmuje się dane TMYx z `climate.onebuilding.org`; wersja produkcyjna powinna wykorzystywać oficjalne polskie dane TLY / TMY (np. z projektu TLM2000).
- Przypadki, w których norma dopuszcza wiele wariantów obliczeń, są parametryzowane i jawnie udokumentowane.

## Zaimplementowane elementy uzupełniające (2026-08)

- **Straty zasobnika CWU (tabela 13, wzory 29–30)**: po podaniu pojemności
  zasobnika straty postoju ΔQ_W,s wyznaczane są z tabeli 13 (q_S wg
  lokalizacji, pojemności, rodzaju i izolacji), a energia końcowa
  Q_k,W = (Q_W,nd + ΔQ_W,d + ΔQ_W,s)/η_W,g.
- **Energia pomocnicza E_el,pom (tabela 20, wzory 37–39)**: pompy obiegowe
  (wiersze 1–2), napędy źródeł (kocioł, PC, węzeł) oraz wentylatory (wiersze
  12/13, czas pracy 8760·β) wliczane do energii końcowej elektrycznej. Formularz pozwala
  podać roczne zużycie `E_el,pom` osobno dla ogrzewania i chłodzenia; wartość
  jawna zastępuje fallback normatywny, a energia pomocnicza nie jest częścią
  `Eu`.
- **Sprawność całkowita systemu**: formularz pokazuje kontrolny iloczyn
  `η_tot = η_g/COP/SEER × η_d × η_s × η_e`; dla bilansu końcowej energii
  używany jest sezonowy COP/SEER podany w projekcie lub wynikający z katalogu
  metodologii.
- **Wentylacja normatywna (tabele 21/22/24/25)**: przy strumieniu 0 m³/h
  podstawowy strumień V0 pobierany jest wg profilu użytkowania budynku,
  z redukcją r_n = 0,75 dla nawiewno-wywiewnej i udziałem β poza okresem
  użytkowania (0,2·V0 / 0,1·V_ex / 0 zależnie od typu wentylacji).
- **Wentylacja okresowa w metodzie godzinowej**: dla `operation_mode =
  periodic` strumień nominalny, dodatkowa infiltracja przy pracy wentylatorów
  `Vx` i infiltracja poza pracą `Vinf` są składane godzinowo według profilu
  `Ventilation.schedule`; jeśli profil nie jest podany, β jest stosowane jako
  uśredniony godzinowy udział pracy. Współczynnik `H_ve` trafia bezpośrednio
  do godzinowego solvera 5R1C. Jawny harmonogram ma pierwszeństwo przed β.
  Dla danych ze zrzutu Arcadia odpowiada to: `airflow_rate = 19715 m³/h`,
  `η = 0,73`, `β = 0,30`, `infiltration_rate = 0,20 1/h` oraz
  `fan_infiltration_rate = 0,04 1/h`; średnia z tych strumieni daje
  `H_ve ≈ 972,21 W/K` przy `V = 8682,26 m³`. W metodzie godzinowej wartość
  `airflow_rate` pozostaje nominalna — nie pomniejsza się jej ręcznie o `β`
  ani o odzysk.
- **Infiltracja (wzory 69–70)**: przy braku jawnej wartości `n` silnik przyjmuje
  `0,2 1/h` dla budynków wzniesionych po 1995 r. i `0,3 1/h` dla starszych;
  wpisana wartość, w tym wynik próby szczelności, ma pierwszeństwo.
- **Oświetlenie wbudowane (wzór (35))**: Q_k,L = LENI·A_L wg PN-EN 15193;
  pole opcjonalne dla budynków niemieszkalnych (dla mieszkalnych nie wyznacza
  się wg metodologii).
- **Współczynnik energii pierwotnej**: domyślna wartość dla energii elektrycznej
  wynosi 2,50 wg tabeli 1 po nowelizacji Dz.U. 2023 poz. 697; współczynniki
  dostawcy/projektu mogą ją nadpisać.

## Pozostałe ograniczenia (świadome)

- **Pełny model gruntu ISO 13370** — podłogi gruntowane napędzane są
  sinusoidą średnioroczną (amp. 5 K, opóźnienie ~2 mies.) zamiast pełnym
  modelem równoważnej płyty (B', d_t); tekst normy jest płatny, a stałych
  nie wolno zgadywać. Wprowadzenie wymaga dostępu do PN-EN ISO 13370.
- **Straty przesyłu CWU z tabeli 10** (długości i izolacje odcinków) —
  aproksymowane multiplikatywną sprawnością ηW,d (tabela 12).
- **Infiltracja z tabeli 23** (V_inf wg wyposażenia w wiatrołapy) —
  przyjmowana jako zadana krotność wymian ACH.
- **Sprzężenie stref** — przegroda `heated_zone` jest pomijana wyłącznie dla
  stref o identycznych aktywnych setpointach; różne setpointy są odrzucane,
  ponieważ wymagają pełnego wielostrefowego solvera.
- **Promieniowanie długofalowe i grunt** — pole `emissivity` oraz uproszczony
  model temperatury gruntu nie zastępują pełnych procedur ISO 52016/13370;
  wymagają dodatkowych danych klimatycznych i parametrów konstrukcji.

## Benchmarki

Wyniki silnika porównywane są z:
- ręcznie zweryfikowanymi przykładami użytkownika,
- biblioteką `pyBuildingEnergy` (tam gdzie możliwe),
- przypadkami testowymi BESTEST/ASHRAE 140.

Automatyczna macierz `backend/tests/test_validation_matrix.py` wykonuje 72
pełne przebiegi roczne i sprawdza niezmienniki godzinowe, miesięczne oraz
bilans Eu. `backend/tests/test_external_bestest.py` zawiera mapowanie masy
cieplnej BESTEST 600/900 do parametrów 5R1C oraz opcjonalny test na publicznym
pliku `DRYCOLDTMY.epw` z repozytorium BESTEST-GSR:

```bash
cd backend
RUN_EXTERNAL_BENCHMARKS=1 PYTHONPATH=$(pwd) .venv/bin/pytest -q
```

Referencje zewnętrzne:

- [DOE: test procedures for building simulation tools](https://www.energy.gov/cmei/buildings/articles/test-procedures-building-energy-simulation-tools),
- [NREL BESTEST/ASHRAE 140 update](https://www1.eere.energy.gov/buildings/publications/pdfs/building_america/bestest_update_ashrae140.pdf),
- [LBL: opublikowane przedziały wyników Case 600](https://simulationresearch.lbl.gov/modelica/releases/v10.1.1/help/Buildings_ThermalZones_ISO13790_Validation_BESTEST_Data.html),
- [NREL BESTEST-GSR: plik EPW i wyniki EnergyPlus](https://github.com/NatLabRockies/BESTEST-GSR).

Porównanie BESTEST jest kontrolą regresji i wykrywaczem wyników odstających,
a nie dowodem formalnej zgodności z każdą procedurą ISO 52016/ASHRAE 140.
W szczególności plik IDF BESTEST opisuje optykę szyb warstwowo, natomiast
formularz aplikacji przyjmuje zintegrowany współczynnik `g`; ten krok jest w
teście jawnie oznaczony jako przybliżenie diagnostyczne. Nadal obowiązują
ograniczenia modelu gruntu, promieniowania długofalowego i uproszczonego
sprzężenia stref wymienione powyżej.

Pełna techniczna specyfikacja kolejności obliczeń, równań, jednostek, reguł
domyślnych i poziomu pewności znajduje się w
[`COMPUTATION_LOGIC.md`](COMPUTATION_LOGIC.md).
