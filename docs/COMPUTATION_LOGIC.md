# Logika obliczeniowa silnika godzinowego

## 1. Cel i status dokumentu

Ten dokument jest techniczną specyfikacją aktualnej implementacji w
`backend/app/engine`. Opisuje kolejność obliczeń, znaczenie danych wejściowych,
jednostki, równania, reguły domyślne, kontrolę bilansów oraz ograniczenia.
Dokument należy czytać razem z:

- [`METHODOLOGY.md`](METHODOLOGY.md) — opis założeń metodologicznych i stanu
  zgodności,
- [`INPUT_SCHEMA.md`](INPUT_SCHEMA.md) — opis pól formularza i JSON,
- testami w `backend/tests`, które są wykonywalnym uzupełnieniem tej
  specyfikacji.

Silnik jest godzinowym modelem jawnego zapotrzebowania na ogrzewanie i
chłodzenie opartym na sieci 5R1C. Rok obliczeniowy ma 8760 godzin i nie jest
rokiem przestępnym. Wyniki godzinowe są następnie agregowane do miesięcy i
roku.

„100% prawidłowości” nie może być potwierdzone wyłącznie przez przejście testów
oprogramowania. Formalne potwierdzenie wymagałoby co najmniej pełnego,
licencjonowanego tekstu właściwych norm, kompletnych przypadków normowych,
zweryfikowanych danych klimatycznych, porównania z niezależnym narzędziem oraz
niezależnego przeglądu eksperta. Poniżej wyraźnie rozdzielono elementy
zaimplementowane, diagnostycznie zweryfikowane i uproszczone.

## 2. Hierarchia źródeł

### 2.1. Źródła normowe i prawne

1. **PN-EN ISO 52016-1** — procedury wyznaczania potrzeb energii do
   ogrzewania i chłodzenia, temperatury wewnętrznej oraz obciążeń; norma
   przewiduje obliczenia godzinowe lub miesięczne i pracę na poziomie stref
   termicznych. Oficjalny opis zakresu:
   [ISO 52016-1:2017](https://www.iso.org/standard/65696.html?browse=ics).
2. **Polska metodologia świadectw** — rozporządzenie z 27 lutego 2015 r.,
   Dz.U. 2015 poz. 376, wraz z późniejszymi zmianami. Tekst w ELI:
   [Dz.U. 2015 poz. 376](https://eli.gov.pl/api/acts/DU/2015/376/text.html).
3. **Nowelizacja z 2023 r.** — w szczególności aktualizacja danych używanych
   przy wyznaczaniu energii pierwotnej. Tekst w ELI:
   [Dz.U. 2023 poz. 697](https://eli.gov.pl/api/acts/DU/2023/697/text.html).
4. Dane promieniowania i geometria słoneczna są obsługiwane w sposób zgodny
   z przeznaczeniem ISO 52010-1 przez bibliotekę `pvlib`; plik wejściowy ma
   format EPW.

### 2.2. Walidacja niezależna

Do testów diagnostycznych wykorzystano publiczne materiały BESTEST/ASHRAE
140:

- [ASHRAE 140 — oficjalne pliki zasobów i zakres testu](https://data.ashrae.org/standard140/),
- [DOE — cel i zastosowanie BESTEST/ASHRAE 140](https://www.energy.gov/cmei/buildings/articles/test-procedures-building-energy-simulation-tools),
- [NREL — aktualizacja przypadków BESTEST](https://www1.eere.energy.gov/buildings/publications/pdfs/building_america/bestest_update_ashrae140.pdf),
- [LBL — opublikowane przedziały wyników Case 600](https://simulationresearch.lbl.gov/modelica/releases/v10.1.1/help/Buildings_ThermalZones_ISO13790_Validation_BESTEST_Data.html),
- [BESTEST-GSR — publiczne pliki EPW, IDF i wyniki EnergyPlus](https://github.com/NatLabRockies/BESTEST-GSR).

ASHRAE opisuje Standard 140 jako metodę wskazywania błędów, ograniczeń,
różnic algorytmicznych, problemów implementacji i błędów danych. Nie testuje
on wszystkich algorytmów programu. Dlatego wynik BESTEST w tym projekcie jest
regresją i wykrywaniem wartości odstających, a nie dowodem zgodności z każdą
częścią PN-EN ISO 52016-1.

## 3. Jednostki i konwencje

| Wielkość | Jednostka w modelu | Zasada |
|---|---:|---|
| czas kroku | h | dokładnie 1 h |
| rok | h | 8760 godzin |
| temperatura | °C | różnice temperatur mogą być używane jako K |
| przepływ powietrza | m³/h | przed przeliczeniem na H_ve |
| przewodność cieplna | W/K | `U·A`, `ψ·l`, `χ·n` |
| moc zysków i strat | W | wartości chwilowe w danej godzinie |
| energia godzinowa | Wh | moc razy 1 h |
| energia roczna/miesięczna | kWh | suma Wh podzielona przez 1000 |
| sprawność | bezwymiarowa | dla źródła może być `η`, COP lub SEER |
| energia pierwotna | Wh | `E_k · f_p` |

Pojedyncza wartość zerowa nie oznacza braku danych w każdym polu. Dla pól,
w których zero jest fizycznie dopuszczalną wartością, zero jest wartością
jawną. Puste pola opcjonalne uruchamiają tylko te domyślne, które są opisane w
tej specyfikacji.

## 4. Przepływ obliczeń

Cały przebieg `calculate_building_energy(project)` ma następującą kolejność:

1. Wczytanie pliku EPW i kontrola, czy zawiera dokładnie 8760 rekordów.
2. Wyznaczenie pozycji słońca i promieniowania na powierzchniach.
3. Rozstrzygnięcie wartości normatywnych wentylacji, infiltracji i udziału
   czasu użytkowania.
4. Dla każdej strefy kondycjonowanej zbudowanie sieci przenikania i tablic
   godzinowych zysków.
5. Rozwiązanie godzinowego bilansu 5R1C oraz wyznaczenie `Q_H(t)` i `Q_C(t)`.
6. Wyznaczenie energii końcowej ogrzewania, chłodzenia, CWU, oświetlenia,
   wentylatorów i pozostałej energii pomocniczej.
7. Grupowanie energii końcowej według nośnika.
8. Przeliczenie na energię pierwotną, emisję CO₂ i udział OZE.
9. Agregacja do 12 miesięcy oraz utworzenie wskaźników na m² powierzchni o
   regulowanej temperaturze.
10. Kontrola podstawowych niezmienników: skończoność, nieujemność, brak
    jednoczesnego ogrzewania i chłodzenia oraz zgodność sum godzinowych,
    miesięcznych i rocznych.

Strefy `unheated` nie są niezależnie rozwiązywane. Są traktowane jako warunek
brzegowy wtedy, gdy przegroda strefy kondycjonowanej wskazuje przestrzeń
nieogrzewaną.

## 5. Walidacja danych wejściowych

Modele Pydantic w `backend/app/schemas/models.py` wymuszają m.in.:

- dodatnie powierzchnie, kubatury, wartości U i powierzchnie stref,
- zgodność sumy powierzchni stref kondycjonowanych z `Af`,
- zgodność sumy kubatur stref kondycjonowanych z kubaturą ogrzewaną,
- unikalne identyfikatory stref i poprawne odwołania elementów do stref,
- zakresy 0–1 dla współczynników `g`, ramy, zacienienia, odzysku i profili,
- dokładnie 24 wartości w każdym profilu godzinowym,
- temperaturę sąsiedniej przestrzeni dla typu `constant_temperature`,
- lokalizację i wymagane dane izolacji zasobnika CWU,
- niejednoznaczne przegrody między strefami o różnych aktywnych nastawach.

Jeżeli podano jednocześnie `height` i `width` elementu, powierzchnia jest
wyznaczana jako `height · width`; wpisana wcześniej wartość `area` nie ma wtedy
pierwszeństwa. Dzięki temu przypadek okien na całej szerokości ściany i o
wysokości 9 m jest liczony z wymiarów, a nie z nieaktualnej powierzchni.

Mostki cieplne nie są automatycznie wyznaczane z geometrii. Każdy wpis musi
zawierać jawną wartość `ψ` i długość albo `χ` i liczbę wystąpień. Pusty wykaz
oznacza brak wprowadzonych mostków, czyli 0 W/K, a nie automatyczne przyjęcie
wartości normowej.

## 6. Klimat i promieniowanie

`load_epw()`:

1. odczytuje `T_e`, `GHI`, `DNI`, `DHI`, wilgotność i dane stacji;
2. wymaga 8760 godzin;
3. ustawia jednolity indeks godzinowy roku nieprzestępnego;
4. wyznacza zenit i azymut słońca na podstawie współrzędnych stacji;
5. funkcja `radiation_on_surface()` wyznacza promieniowanie na powierzchni
   pochylonej modelem Hay–Davies, z uwzględnieniem albedo gruntu.

Promieniowanie na powierzchni jest w W/m². Nie jest ono dodatkowo mnożone
przez 3600, ponieważ zysk jest wprowadzany do równania jako moc w danej
godzinie, a dopiero wynik solvera jest interpretowany jako Wh za godzinę.

## 7. Przenikanie i mostki cieplne

### 7.1. Przewodności

Dla przegrody nieprzezroczystej:

```text
H_j = U_j · A_j
```

Dla mostków:

```text
H_bridge = Σ(ψ_k · l_k) + Σ(χ_n · count_n)
```

Mostki przypisane do strefy są doliczane raz do ścieżki nieprzezroczystej i
mają temperaturę zewnętrzną jako temperaturę napędową. Nie są jednocześnie
doliczane jako osobna strata w godzinowym solverze.

Przegroda do `heated_zone` jest pomijana, bo przy jednakowych aktywnych
nastawach model zakłada zerowy przepływ netto. Przy różnych nastawach model
odrzuca projekt; nie udaje obliczenia sprzężenia wielostrefowego.

### 7.2. Temperatura sąsiednia

- `outdoor`: `T_adj = T_e`;
- `ground`: uproszczona sinusoida średniorocznej temperatury z amplitudą 5 K
  i opóźnieniem około dwóch miesięcy;
- `unheated_zone`: `T_adj = T_e + 3 K`, jeżeli nie podano osobnej serii;
- `constant_temperature`: stała wartość z pola `adjacent_temperature`;
- `heated_zone`: przegroda pomijana w obecnym solverze.

Temperatury gruntu i przestrzeni nieogrzewanej są założeniami aplikacji, a nie
pełnym modelem ISO 13370 lub pełnym modelem strefy buforowej.

### 7.3. Sieć 5R1C

Domyślne właściwości strefy:

```text
A_t = 4.5 · A_f
A_m = 2.5 · A_f
C_m = κ · 1000 · A_m                 [J/K]
H_tr,is = 3.45 · A_t                  [W/K]
H_tr,ms = 9.1 · A_m                    [W/K]
H_tr,em = 1 / (1/H_tr,op - 1/H_tr,ms)  [W/K]
```

`H_tr,op` jest sumą przewodności przegród nieprzezroczystych i mostków. Jeżeli
`H_tr,op >= H_tr,ms`, rozdział 5R1C jest nieokreślony i silnik zgłasza błąd;
nie przełącza po cichu na inny model.

Okna są podłączone do węzła powierzchni przez `H_tr,w = Σ(U_w · A_w)`.
Przewodności przegród nieprzezroczystych są agregowane z temperaturą ważoną
przez `U·A`, więc grunt, przestrzeń nieogrzewana i temperatura stała nie są
bezpodstawnie zastępowane temperaturą zewnętrzną.

### 7.4. Podział zysków

Dla `Φ_int` i `Φ_sol`:

```text
Φ_ia = 0.5 · Φ_int
Φ_m  = (A_m/A_t) · (0.5 · Φ_int + Φ_sol)
Φ_st = (1 - A_m/A_t - H_tr,w/(9.1·A_t)) · (0.5 · Φ_int + Φ_sol)
```

Zyski są rozdzielane do węzła powietrza, masy i powierzchni. Węzeł masy jest
aktualizowany z krokiem 1 h przy dyskretyzacji Cranka–Nicolsona. Węzły masy,
powietrza i powierzchni są rozwiązywane jednocześnie jako układ liniowy.

W każdej godzinie solver:

1. rozwiązuje temperaturę swobodną bez mocy HVAC;
2. oblicza odpowiedź temperatury powietrza na 1 W dodatkowego ogrzewania;
3. dobiera dokładną moc potrzebną do osiągnięcia nastawy ogrzewania lub
   chłodzenia;
4. ponownie wyznacza trzy temperatury z tą mocą.

Wynik `q_heating` i `q_cooling` jest mocą pomnożoną przez czas kroku 1 h,
czyli ma jednostkę Wh. Solver nie dopuszcza do dodatnich wartości obu usług w
tej samej godzinie.

## 8. Wentylacja i infiltracja

### 8.1. Współczynnik wentylacyjny

Podstawowe równanie jest następujące:

```text
H_ve = 1200 · V_eff / 3600       [W/K]
```

`V_eff` jest w m³/h. W modelu rozdzielane są:

- strumień mechaniczny po równoważnym uwzględnieniu odzysku,
- strumień powietrza zewnętrznego bez odzysku: infiltracja, infiltracja od
  wentylatora, wywiew lub wentylacja naturalna.

Jeżeli nie podano temperatury nawiewu:

```text
V_mech,eff = V_mech · (1 - η_oc)
T_sup = T_e
```

Jeżeli podano rzeczywistą temperaturę po centrali, odzysk nie jest ponownie
mnożony przez `1 - η_oc`; temperatura zastępcza jest ważona strumieniami:

```text
T_sup = (V_mech · T_supply + V_ext · T_e) / (V_mech + V_ext)
```

To zapobiega podwójnemu uwzględnieniu odzysku.

### 8.2. Strumień nominalny a strumień efektywny

`airflow_rate` jest nominalnym strumieniem podczas pracy [m³/h]. Nie należy
w formularzu ręcznie mnożyć go przez `β` ani przez `(1 - η_oc)`. Te operacje
wykonuje silnik w odpowiednich miejscach:

- `β` wpływa na profil pracy lub normatywny udział czasu;
- odzysk wpływa na równoważny strumień cieplny;
- infiltracja jest liczona osobno.

Przy `airflow_rate = 0` silnik pobiera normatywny strumień z profilu
użytkowania. Dla przykładu, dla biura wartość bazowa w kodzie wynosi
`0.56·10⁻³ m³/(s·m²)`. Dla nawiewno-wywiewnej wentylacji stosowana jest
redukcja `r_n = 0.75`, a przy pracy okresowej osobny profil godzinowy.

### 8.3. Infiltracja

Jeżeli pole `infiltration_rate` nie było jawnie podane, silnik przyjmuje:

```text
n = 0.20 1/h  dla budynku po 1995 r.
n = 0.30 1/h  dla budynku z 1995 r. lub starszego
```

Wartość jawna, w tym zero, ma pierwszeństwo. Strumień infiltracji wynosi
`n·V_zone`. Dodatkowa infiltracja przy pracy wentylatorów jest liczona jako
`fan_infiltration_rate·V_zone`.

### 8.4. Tryb okresowy

W trybie `periodic` pierwszeństwo ma jawny `Schedule`. Jeżeli harmonogramu
nie ma, `usage_share_beta` jest stosowane jako stały godzinowy udział pracy.
W czasie pracy i poza pracą składniki są następujące:

- nawiewno-wywiewna: mechaniczny strumień i infiltracja wentylatorowa w czasie
  pracy, sama infiltracja tła poza pracą;
- wywiewna/hybrydowa: pełny strumień w czasie pracy, 10% strumienia bazowego
  poza pracą oraz infiltracja tła;
- naturalna: strumień bazowy i infiltracja są traktowane jako powietrze
  zewnętrzne.

## 9. Zyski słoneczne

### 9.1. Przegrody transparentne

Dla każdego okna lub drzwi przeszklonych:

```text
Φ_sol,win = A · (1 - F_frame) · g · F_sh · I_POA
```

`I_POA` jest promieniowaniem na płaszczyźnie elementu w W/m². Azymut jest
liczony od północy: 0° północ, 90° wschód, 180° południe, 270° zachód.

### 9.2. Przegrody nieprzezroczyste

Dla przegród zewnętrznych dodatkowy zysk wewnętrzny jest modelowany przez
efekt sol-air:

```text
Φ_sol,opaque = A · α · U · R_se · I_POA
R_se = 0.04 m²K/W
```

Wartość `solar_reduction_factor` zachowana w schemacie dla zgodności ze
starszym JSON-em jest ignorowana przez silnik; współczynnik jest wyznaczany z
`U·R_se`. Opaque elements do gruntu, przestrzeni nieogrzewanej i temperatury
stałej nie dostają tego zysku w obecnej implementacji.

## 10. Zyski wewnętrzne i harmonogramy

Dla jawnego podziału źródeł:

```text
Φ_occ(t)   = q_occ · density · A_f · profile_occ(t)
Φ_light(t) = q_light · A_f · profile_light(t)
Φ_equip(t) = q_equip · A_f · profile_equip(t)
Φ_int(t)   = Φ_occ(t) + Φ_light(t) + Φ_equip(t)
```

`q_occ` ma jednostkę W/osobę, a `q_light` i `q_equip` W/m². Profil jest
ograniczony do zakresu 0–1 i może być stały, weekday/weekend albo pełny
profil 24-godzinny dla dni roboczych, soboty i niedzieli.

Jeżeli projekt nie podał `internal_gains`, schema generuje normowy poziom
`q_int` z tabeli 26 i oznacza go `normative_power_density_w_m2`. Jeżeli
wszystkie trzy profile są stałe i równe 1, silnik używa bezpośrednio normowego
`q_int·A_f`, niezależnie od pomocniczej gęstości osób w strefie. Po podaniu
jawnych harmonogramów działa wzór źródłowy powyżej. Nie należy interpretować
normowej wartości średniej jako automatycznego profilu obecności w każdej
godzinie.

## 11. Energia użytkowa i systemy techniczne

### 11.1. Potrzeby użytkowe

Z bilansu 5R1C wynikają:

```text
Q_H,nd = Σ_t Q_H(t)
Q_C,nd = Σ_t Q_C(t)
Q_W,nd = energia użytkowa CWU z tabeli 27
E_u    = Q_H,nd + Q_C,nd + Q_W,nd
```

Oświetlenie wbudowane i energia pomocnicza nie zwiększają `E_u`.

### 11.2. Ogrzewanie i chłodzenie

Jeżeli źródło jest aktywne, energia końcowa jest liczona godzinowo z
sezonowego iloczynu sprawności:

```text
η_H,tot = η_H,g · η_H,d · η_H,s · η_H,e
η_C,tot = SEER · η_C,d · η_C,s · η_C,e
E_k,H(t) = Q_H(t) / η_H,tot
E_k,C(t) = Q_C(t) / η_C,tot
```

Dla pompy ciepła `η_H,g` jest COP, a dla chłodzenia `η_C,g` jest SEER.
Silnik nie tworzy automatycznie godzinowej krzywej COP z temperatury
zewnętrznej. Funkcja `heat_pump_cop_map()` jest pomocniczym modelem
diagnostycznym i nie jest używana w głównym certyfikacyjnym bilansie.

Moc projektowa ogrzewania jest osobnym wynikiem. Jest to maksimum dodatnich
strat przez przenikanie i wentylację w warunkach serii klimatycznej,
podzielone przez sprawność przesyłu, magazynowania i regulacji. Sprawność
generacji/COP nie zmniejsza wymaganej mocy cieplnej źródła.

### 11.3. CWU

Roczne zapotrzebowanie użytkowe jest wyznaczane z profilu `dhw_usage_profile`:

```text
Q_W,nd = V_Wi · A_f · c_W · ρ_W · (θ_W - θ_0) · k_R · t_R / 3600
```

W implementacji używane są: `c_W = 4.19 kJ/(kg·K)`, `ρ_W = 1 kg/l`,
`θ_W = 55°C`, `θ_0 = 10°C`, `t_R = 365 dni`. Silnik rozdziela roczną
wartość równomiernie na 8760 godzin tylko na potrzeby wspólnego formatu
wyników; nie ma obecnie godzinowego modelu poboru CWU.

Bez jawnej geometrii zasobnika:

```text
η_W,tot = η_W,g · η_W,s · η_W,d · η_W,e
E_k,W = Q_W,nd / η_W,tot
```

Po podaniu pojemności zasobnika, lokalizacji i wymaganej izolacji strata
postoju jest liczona według tabeli 13 i wzoru:

```text
ΔQ_W,s = V_S · q_S · 8760 · 10⁻³   [kWh/rok]
ΔQ_W,d = Q_W,nd · (1/η_W,d - 1)
E_k,W = (Q_W,nd + ΔQ_W,d + ΔQ_W,s) / η_W,g
```

W tej gałęzi straty magazynowania są liczone z tabeli, a nie przez ponowne
mnożenie przez `storage_efficiency`.

### 11.4. Oświetlenie i energia pomocnicza

Dla budynku niemieszkalnego, gdy podano `LENI`:

```text
E_k,L = LENI · A_L · 1000   [Wh/rok]
```

Energia pomocnicza jest doliczana do energii końcowej jako energia elektryczna:

- ogrzewanie: wartość jawna albo normatywne wiersze tabeli 20 dla źródła i,
  jeżeli podano, instalacji odbiorczej;
- chłodzenie: tylko wartość jawna, jeżeli została podana;
- CWU: normatywne wiersze tabeli 20 zależne od źródła i cyrkulacji;
- wentylacja: `q_el · A_f · t_el`, przy czym `t_el` wynika z sumy godzinowego
  profilu pracy.

Wpis `auxiliary_energy_kwh_year = 0` jest świadomym zerem. Brak wartości nie
jest tym samym co zero dla gałęzi, która ma normatywny fallback.

## 12. Energia końcowa, pierwotna i emisje

Energia końcowa jest najpierw grupowana według nośnika. Do nośnika
`electricity` trafiają m.in. energia elektryczna systemów, wentylatory,
oświetlenie i energia pomocnicza.

Następnie:

```text
E_p = Σ_i E_k,i · f_p,i
E_CO2 = Σ_i E_k,i[kWh] · w_e,i[kg/kWh] / 1000
```

`f_p` i `w_e` są danymi projektu. Domyślne współczynniki muszą być traktowane
jako konfiguracja do kontroli i aktualizacji, szczególnie dla energii z sieci
ciepłowniczej i wskaźnika emisji. Udział OZE w obecnym kodzie jest liczony z
końcowej energii przypisanej nośnikom `biomass` i `renewable`; nie jest to pełny
model gwarancji pochodzenia ani bilans importu/eksportu.

## 13. Agregacja i kontrola bilansu

Każda tablica godzinowa ma 8760 elementów. Miesiące są tworzone przez sumowanie
bloków 31/28/31/30/31/30/31/31/30/31/30/31 dni. Suma miesięczna musi być
równa sumie rocznej tej samej tablicy.

Kontrolowane niezmienniki:

- `Q_H >= 0`, `Q_C >= 0`;
- w jednej godzinie nie występuje jednocześnie dodatnie `Q_H` i `Q_C`;
- `E_u` jest równe sumie rocznych potrzeb ogrzewania, chłodzenia i CWU;
- serie temperatur, zysków i strat są skończone;
- odzysk ciepła zmniejsza zapotrzebowanie ogrzewania w scenariuszu testowym;
- dodanie mostków zwiększa straty dla dodatniej różnicy temperatur;
- okno południowe i północne reagują różnie na ten sam klimat;
- podział strumienia wentylacji między strefy nie zwielokrotnia strumienia
  budynkowego;
- zmiana sprawności zmienia energię końcową, ale nie użyteczne `E_u`;
- zmiana harmonogramu okresowego zmienia godziny pracy, a nie liczbę godzin w
  pliku klimatycznym.

## 14. Stan weryfikacji

### Zweryfikowane automatycznie

- 72 pełne roczne warianty w `test_validation_matrix.py`:
  6 wariantów wentylacji × 3 warianty oszklenia × 2 stany mostków × 2 usługi
  (ogrzewanie/chłodzenie);
- testy jednostkowe jednostek, odzysku, mostków, harmonogramów, sprawności,
  energii pomocniczej, CWU, klimatu i 5R1C;
- publiczny plik `DRYCOLDTMY.epw` BESTEST-GSR, kontrolowany sumą SHA-256 i
  długością 8760 godzin;
- mapowanie opublikowanych parametrów masy BESTEST Case 600 i Case 900;
- diagnostyczny Case 600 w paśmie opublikowanych przedziałów LBL oraz
  porównanie z wynikiem EnergyPlus BESTEST-GSR z tolerancją diagnostyczną 25%.

Uruchomienie testu z plikiem zewnętrznym:

```bash
cd backend
RUN_EXTERNAL_BENCHMARKS=1 PYTHONPATH=$(pwd) .venv/bin/pytest -q
```

Test zewnętrzny używa zintegrowanego `g` dla szyby, podczas gdy plik BESTEST
opisuje optykę warstwowo. Jest to jawne przybliżenie diagnostyczne. Nie wolno
traktować tego porównania jako formalnego testu tolerancji dla każdego budynku.

### Częściowo odwzorowane

- polska metodologia potrzeb użytkowych i współczynników systemowych jest
  odwzorowana tam, gdzie pola wejściowe i tabele są obecnie modelowane;
- sieć 5R1C i obliczenia godzinowe są spójne z przyjętym wariantem modelu,
  ale nie są niezależną implementacją każdej opcji ISO 52016-1;
- energia pomocnicza obejmuje obsługiwane wiersze tabeli 20, a brakujące
  klasyfikacje wymagają jawnego zużycia od użytkownika;
- transparentne zyski słoneczne są liczone godzinowo, ale dane wejściowe `g`
  są zintegrowanym współczynnikiem, nie pełną optyką warstwową.

### Poza zakresem obecnej implementacji

- pełny okresowy model podłogi i gruntu według ISO 13370;
- pełne promieniowanie długofalowe z emisyjnością i wymianą radiacyjną nieba;
- pełne dynamiczne sprzężenie wielu stref o różnych temperaturach;
- dynamiczny model temperatury i poboru CWU;
- godzinowe krzywe sprawności, COP/SEER, mocy częściowej i ograniczeń źródeł;
- wilgotność, ciepło utajone i osuszanie;
- automatyczne wyznaczanie `ψ` i `χ` z geometrii oraz szczegółowych mostków;
- formalna ocena wymagań WT/świadectwa — obecny check EP jest informacyjny,
  a nie prawnym pass/fail.

## 15. Wymagania do formalnego podniesienia poziomu pewności

Przed użyciem jako narzędzia do formalnych świadectw należy:

1. zamknąć wersje obowiązujących aktów, norm i współczynników nośników;
2. pozyskać pełny tekst PN-EN ISO 52016-1, ISO 13370 i pozostałych norm
   potrzebnych dla deklarowanego zakresu;
3. dodać referencyjne przypadki godzinowe z akceptacją eksperta domenowego;
4. zastąpić uproszczenie gruntu pełnym modelem odpowiednim do rodzaju
   przegrody;
5. dodać kontrolowany model wielu stref i jawny model CWU;
6. rozdzielić sezonowe i godzinowe modele systemów oraz wprowadzić dane
   producenta/EN 14825 tam, gdzie wymagane;
7. wykonać niezależne porównanie z drugim silnikiem na identycznym pliku
   wejściowym i identycznych warunkach brzegowych;
8. przeprowadzić przegląd wyników i dokumentacji przez uprawnionego eksperta.

Do czasu wykonania tych punktów aplikację należy opisywać jako dokładny,
testowany silnik godzinowy dla jawnie określonego zakresu, a nie jako dowolnie
uniwersalny dowód zgodności normowej.
