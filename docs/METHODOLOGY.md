# Metodologia obliczeń

## 1. Cel dokumentu

Ten dokument opisuje sposób, w jaki aplikacja Energoliczydło rozdziela i wykonuje różne rodzaje obliczeń energetycznych budynku.

Najważniejsza zasada projektu brzmi:

**formalna charakterystyka energetyczna, godzinowa analiza fizyczna i projektowe obciążenie cieplne są trzema różnymi wynikami.**

Nie należy ich ze sobą utożsamiać ani przedstawiać jako zamiennych.

## 2. Trzy rodzaje obliczeń

### 2.1. Formalna charakterystyka energetyczna w Polsce

W trybie świadectwa główne wskaźniki:

- energia użytkowa (`Eu`),
- energia końcowa (`Ek`),
- nieodnawialna energia pierwotna (`Ep`)

są wyznaczane zgodnie z polską metodologią charakterystyki energetycznej.

Formalny silnik działa w ujęciu miesięcznym. Dane i współczynniki wymagane przez metodologię muszą być jawnie podane lub wynikać z udokumentowanego źródła.

Szczegółowy opis znajduje się w `POLISH_CERTIFICATE_METHOD.md`.

### 2.2. Godzinowa analiza fizyczna

Równolegle aplikacja wykonuje szczegółową analizę 8760 godzin roku z wykorzystaniem modelu opartego na PN-EN ISO 52016-1.

Model godzinowy służy do analizy:

- temperatur wewnętrznych,
- zapotrzebowania na ogrzewanie i chłodzenie w kolejnych godzinach,
- wpływu pojemności cieplnej budynku,
- zysków słonecznych,
- zysków wewnętrznych,
- wentylacji i infiltracji,
- odzysku ciepła,
- wymiany ciepła z gruntem.

W trybie świadectwa wynik godzinowy jest zachowywany jako analiza równoległa i kontrolna, ale nie zastępuje formalnej procedury miesięcznej.

### 2.3. Projektowe obciążenie cieplne

Projektowe obciążenie cieplne opisuje moc potrzebną do utrzymania wymaganych warunków wewnętrznych w określonych warunkach projektowych.

Nie jest to energia roczna i nie jest dodawane do `Eu`, `Ek` ani `Ep`.

Projektowe obciążenie cieplne nie może być utożsamiane z największą godzinową stratą występującą w typowym roku meteorologicznym.

## 3. Dokumenty i zakresy metodologiczne

Projekt wykorzystuje i rozdziela zakresy wynikające między innymi z:

- polskiego rozporządzenia w sprawie metodologii wyznaczania charakterystyki energetycznej budynku lub części budynku oraz świadectw charakterystyki energetycznej,
- PN-EN ISO 52016-1 – godzinowe potrzeby ogrzewania i chłodzenia, temperatury wewnętrzne i analiza dynamiczna,
- PN-EN ISO 52010-1 – dane klimatyczne i promieniowanie słoneczne,
- PN-EN ISO 13370 – wymiana ciepła z gruntem,
- PN-EN 12831-1 – projektowe obciążenie cieplne,
- właściwych norm systemowych i badawczych dotyczących urządzeń grzewczych, chłodniczych, wentylacyjnych i przygotowania ciepłej wody użytkowej.

Pełne teksty norm nie są przechowywane w repozytorium. Jeżeli dana wartość musi pochodzić z procedury normowej albo dokumentacji konkretnego urządzenia, aplikacja wymaga jej jawnego podania i zapisania źródła.

## 4. Godzinowy bilans cieplny strefy

Dla każdej godziny i każdej strefy kondycjonowanej analizowane są między innymi:

- straty przez przenikanie,
- straty i zyski związane z wentylacją,
- zyski wewnętrzne,
- zyski słoneczne,
- pojemność cieplna budynku,
- energia dostarczana przez ogrzewanie,
- energia odbierana przez chłodzenie.

Uproszczony zapis bilansu ma postać:

```text
bilans cieplny
=
zyski wewnętrzne
+ zyski słoneczne
- przenikanie
- wentylacja
+ ogrzewanie
- chłodzenie
```

W kodzie szczegółowy model godzinowy jest realizowany przez sieć cieplną 5R1C.

## 5. Model 5R1C

Model 5R1C opisuje budynek za pomocą kilku powiązanych oporów cieplnych i jednej pojemności cieplnej.

W praktyce rozróżnia między innymi:

- temperaturę powietrza wewnętrznego,
- temperaturę powierzchni wewnętrznych,
- temperaturę masy cieplnej budynku,
- wymianę ciepła przez przegrody,
- wymianę ciepła przez okna,
- wymianę ciepła przez wentylację.

Zyski wewnętrzne i słoneczne są rozdzielane pomiędzy odpowiednie węzły modelu.

## 6. Powierzchnie przegród i otworów

Powierzchnia nieprzezroczysta ściany jest liczona jako powierzchnia brutto ściany pomniejszona o powierzchnię przypisanych do niej okien, drzwi przeszklonych i świetlików.

Oznacza to, że okno nie jest liczone dodatkowo „nałożone” na pełną powierzchnię ściany.

Jeżeli otwór jest większy niż jego przegroda nadrzędna albo nie można jednoznacznie określić, do której przegrody należy, obliczenie jest blokowane.

## 7. Przenikanie ciepła

Dla pojedynczej przegrody podstawowa przewodność cieplna wynika z iloczynu:

```text
H = U × A
```

gdzie:

- `H` – przewodność cieplna przegrody w watach na kelwin,
- `U` – współczynnik przenikania ciepła w watach na metr kwadratowy i kelwin,
- `A` – powierzchnia przegrody w metrach kwadratowych.

Mostki cieplne są uwzględniane osobno przez współczynniki liniowe i punktowe.

Brak wprowadzonych mostków oznacza wartość zero i jest sygnalizowany w audycie jako założenie wymagające weryfikacji.

## 8. Wymiana ciepła z gruntem

Dawny uproszczony model gruntu oparty na jednej globalnej sinusoidzie nie jest traktowany jako model formalny.

Rozszerzony model wykorzystuje dane geometryczne i cieplne właściwe dla przegrody, w tym między innymi:

- powierzchnię podłogi,
- obwód wystawiony na kontakt z gruntem,
- opór cieplny warstw podłogi,
- przewodność cieplną gruntu,
- gęstość i ciepło właściwe gruntu,
- parametry okresowej odpowiedzi cieplnej.

Szczegóły opisuje `NORMATIVE_HOURLY_V2.md`.

## 9. Wentylacja

Straty wentylacyjne wynikają z rzeczywistego strumienia powietrza i różnicy temperatur między powietrzem wewnętrznym a powietrzem nawiewanym.

Podstawowa zależność ma postać:

```text
Hve = ρ × cp × qv
```

gdzie:

- `Hve` – przewodność cieplna wentylacji,
- `ρ × cp` – objętościowa pojemność cieplna powietrza,
- `qv` – strumień objętościowy powietrza.

W silniku stosowana jest wartość objętościowej pojemności cieplnej powietrza równoważna `1200 J/(m³·K)`.

## 10. Odzysk ciepła w wentylacji

W szczegółowym modelu odzysku ciepła pełny fizyczny strumień powietrza pozostaje w obliczeniu.

Odzysk ciepła zmienia temperaturę powietrza nawiewanego, a nie samą ilość wymienianego powietrza.

Model może uwzględniać:

- zmienną sprawność wymiennika,
- obejście letnie wymiennika,
- ochronę przed zamarzaniem,
- nagrzewnicę wstępną,
- ograniczenie mocy urządzenia.

Energia nagrzewnicy wstępnej jest energią systemową. Zwiększa energię końcową i może zwiększać nieodnawialną energię pierwotną, ale nie zwiększa energii użytkowej.

## 11. Zyski słoneczne

Dla analizy godzinowej promieniowanie słoneczne jest wyznaczane dla rzeczywistej orientacji i nachylenia każdej przegrody.

Dla okna zysk zależy między innymi od:

- powierzchni przeszklenia,
- całkowitego współczynnika przepuszczania energii słonecznej,
- udziału ramy,
- współczynnika zacienienia,
- promieniowania padającego na daną powierzchnię.

Dane godzinowe wykorzystywane w tej analizie nie są automatycznie przenoszone do formalnego silnika świadectwa.

## 12. Zyski wewnętrzne

Zyski wewnętrzne obejmują energię cieplną pochodzącą między innymi od:

- ludzi,
- oświetlenia,
- urządzeń i wyposażenia.

Jeżeli użytkownik nie poda szczegółowych harmonogramów, aplikacja może korzystać z jawnie określonych wartości profilowych zgodnie z przyjętą metodą obliczeniową.

W trybie formalnym wymagane dane i źródła są kontrolowane osobno.

## 13. Ogrzewanie i chłodzenie

W modelu godzinowym system ogrzewania lub chłodzenia reaguje na temperaturę strefy i zadane temperatury graniczne.

Godzinowe zapotrzebowanie użytkowe jest następnie sumowane do wartości miesięcznych i rocznych dla potrzeb analizy technicznej.

W trybie świadectwa formalne wartości miesięczne są jednak liczone przez osobny silnik zgodny z polską metodologią.

## 14. Ciepła woda użytkowa

Zapotrzebowanie na energię użytkową do przygotowania ciepłej wody użytkowej jest obliczane osobno od ogrzewania i chłodzenia.

Przeliczenie na energię końcową uwzględnia parametry systemu, w tym sprawność źródła, dystrybucji, magazynowania i wykorzystania.

Jeżeli system z zasobnikiem nie ma danych potrzebnych do wyznaczenia strat postojowych, aplikacja zgłasza to jako brak albo jawne założenie zamiast ukrywać problem.

## 15. Energia użytkowa, końcowa i pierwotna

### Energia użytkowa (`Eu`)

Opisuje potrzeby użytkowe budynku przed uwzględnieniem strat i sprawności instalacji.

### Energia końcowa (`Ek`)

Opisuje energię dostarczaną do systemów technicznych po uwzględnieniu sprawności, strat i energii pomocniczej.

### Nieodnawialna energia pierwotna (`Ep`)

Opisuje energię końcową przeliczoną za pomocą właściwych współczynników nakładu nieodnawialnej energii pierwotnej.

Nie istnieje uniwersalna zasada, że `Ep ≥ Ek ≥ Eu`. Na przykład pompa ciepła może mieć energię końcową niższą od energii użytkowej, ponieważ część energii pobiera ze środowiska.

## 16. Współczynniki nakładu energii pierwotnej

Dla każdego nośnika energii stosowana jest odpowiednia wartość współczynnika nakładu nieodnawialnej energii pierwotnej.

W trybie świadectwa zapisuje się nie tylko wartość, ale także jej źródło.

Nie należy traktować wartości domyślnej jako wystarczającego dowodu poprawności dla konkretnego świadectwa.

## 17. Kontrola kompletności danych

Przed właściwym obliczeniem aplikacja wykonuje kontrolę danych wejściowych.

Kontrola może wykrywać między innymi:

- niespójne powierzchnie przegród i otworów,
- brakujące części obudowy budynku,
- nietypową relację powierzchni do kubatury,
- brak mostków cieplnych,
- brak danych zasobnika ciepłej wody użytkowej,
- brak rodzaju instalacji potrzebnego do oceny energii pomocniczej,
- brak danych normowych wymaganych w trybie świadectwa.

Część problemów powoduje ostrzeżenie, a część blokuje obliczenie.

## 18. Zasada blokowania wyniku formalnego

Jeżeli użytkownik włączy tryb świadectwa, aplikacja nie może tworzyć formalnego wyniku na podstawie nieudokumentowanych wartości zastępczych.

Jeżeli brakuje danych wymaganych do poprawnego formalnego obliczenia, wynik jest blokowany do czasu uzupełnienia danych.

## 19. Powiązane dokumenty

- `POLISH_CERTIFICATE_METHOD.md` – formalna metoda świadectwa,
- `NORMATIVE_HOURLY_V2.md` – model godzinowy, grunt, odzysk ciepła i projektowe obciążenie cieplne,
- `COMPUTATION_LOGIC.md` – techniczny przebieg obliczeń,
- `INPUT_SCHEMA.md` – struktura danych wejściowych,
- `VALIDATION.md` – testowanie i walidacja,
- `AUDIT_FIXES_2026-08-17.md` – poprawki wykonane po audycie obliczeń.
