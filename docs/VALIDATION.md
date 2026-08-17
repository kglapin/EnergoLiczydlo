# Strategia testowania i walidacji

## 1. Cel

Celem testów jest wykrywanie błędów obliczeniowych, błędów implementacji i nieprawidłowych danych wejściowych możliwie wcześnie.

Testy nie są samodzielnym dowodem pełnej zgodności z każdą klauzulą normy lub aktu prawnego. Formalna zgodność wymaga również właściwych danych wejściowych, aktualnej podstawy prawnej, właściwych wersji norm i niezależnej kontroli przypadków referencyjnych.

## 2. Co jest testowane osobno

Aplikacja ma trzy różne warstwy obliczeń, dlatego każda z nich wymaga osobnej walidacji.

### 2.1. Formalna charakterystyka energetyczna

Testy sprawdzają między innymi:

- miesięczny bilans ogrzewania,
- miesięczny bilans chłodzenia,
- wpływ miesięcznych współczynników wykorzystania zysków i strat,
- przeliczenie energii użytkowej na energię końcową,
- przeliczenie energii końcowej na nieodnawialną energię pierwotną,
- poprawność źródeł współczynników nakładu energii pierwotnej,
- blokowanie obliczenia przy braku wymaganych danych formalnych.

### 2.2. Godzinowa analiza fizyczna

Testy sprawdzają między innymi:

- kompletność 8760 godzin danych klimatycznych,
- godzinowy bilans cieplny,
- temperatury wewnętrzne,
- zyski słoneczne,
- zyski wewnętrzne,
- wentylację i infiltrację,
- odzysk ciepła,
- wymianę ciepła z gruntem,
- zgodność sum godzinowych z agregacją miesięczną i roczną.

### 2.3. Projektowe obciążenie cieplne

Testy sprawdzają między innymi:

- wpływ projektowej temperatury zewnętrznej,
- wpływ przegród do gruntu i przestrzeni nieogrzewanych,
- wpływ wentylacji,
- niezależność strat budynku od współczynnika COP pompy ciepła i sprawności źródła,
- poprawność sumowania wyników strefowych do wyniku całego budynku.

## 3. Testy jednostkowe

Każda funkcja fizyczna powinna mieć test z wartością analityczną albo dobrze zdefiniowanym przypadkiem referencyjnym.

Przykładowe obszary:

- `climate` – odczyt danych klimatycznych i promieniowanie słoneczne,
- `envelope` – przenikanie ciepła, powierzchnie netto i mostki cieplne,
- `solar` – zyski słoneczne,
- `ventilation` – wentylacja, infiltracja i odzysk ciepła,
- `ground_iso13370` – parametry wymiany ciepła z gruntem,
- `internal_gains` – zyski wewnętrzne,
- `thermal_balance` – godzinowy bilans cieplny,
- `systems` – sprawności systemów i ciepła woda użytkowa,
- `primary_energy` – przeliczenie na nieodnawialną energię pierwotną,
- `polish_certificate_monthly` – miesięczny silnik formalnej charakterystyki energetycznej,
- `design_load` – projektowe obciążenie cieplne.

## 4. Testy analityczne

Tam, gdzie to możliwe, wynik jest porównywany z prostym obliczeniem, które można wykonać ręcznie.

Przykłady:

### 4.1. Przenikanie przez przegrodę

```text
H = U × A
```

Jeżeli ściana ma powierzchnię 40 m² i współczynnik przenikania ciepła `U = 0,25 W/(m²·K)`, jej przewodność cieplna wynosi:

```text
H = 40 × 0,25 = 10 W/K
```

### 4.2. Okno zastępujące fragment ściany

Jeżeli 1 m² ściany o `U = 0,25 W/(m²·K)` zostanie zastąpiony 1 m² okna o `U = 1,00 W/(m²·K)`, przewodność cieplna powinna wzrosnąć o:

```text
1,00 - 0,25 = 0,75 W/K
```

### 4.3. Odzysk ciepła

Przy temperaturze zewnętrznej 0°C, temperaturze powietrza usuwanego 20°C i sprawności odzysku 80% temperatura nawiewu powinna wynieść:

```text
0 + 0,80 × (20 - 0) = 16°C
```

Takie testy są szczególnie ważne, ponieważ pozwalają wykryć błędy, które mogą nie być widoczne w dużym rocznym wyniku.

## 5. Testy integracyjne

Test integracyjny sprawdza pełną ścieżkę:

```text
dane projektu
→ walidacja
→ obliczenia
→ wynik
```

Sprawdzane są między innymi:

- kompletność odpowiedzi API,
- zgodność sum miesięcznych i rocznych,
- brak wartości `NaN` i nieskończonych,
- brak jednoczesnego dodatniego ogrzewania i chłodzenia w tej samej godzinie,
- zachowanie wyniku godzinowego po włączeniu formalnego silnika świadectwa,
- prawidłowe przełączenie głównych wskaźników `Eu`, `Ek`, `Ep` na wynik formalny w trybie świadectwa.

## 6. Niezmienniki fizyczne

Należy stosować tylko takie niezmienniki, które są prawdziwe dla danego modelu.

Nie należy przyjmować uniwersalnie:

```text
Ep ≥ Ek ≥ Eu
```

Taka relacja nie jest ogólnie prawdziwa.

Przykładowo:

- pompa ciepła może mieć energię końcową niższą od energii użytkowej, ponieważ pobiera część energii ze środowiska,
- współczynnik nakładu nieodnawialnej energii pierwotnej może być mniejszy od 1 dla wybranych nośników energii.

Poprawne przykładowe niezmienniki to:

- energie użytkowe nie mogą być ujemne,
- sprawności opisane jako liczby od 0 do 1 nie mogą wyjść poza ten zakres,
- powierzchnia netto ściany nie może być ujemna,
- powierzchnia otworów nie może przekraczać powierzchni ich przegrody nadrzędnej,
- zwiększenie oporu cieplnego tej samej przegrody nie powinno zwiększać jej przewodności cieplnej,
- zwiększenie projektowej różnicy temperatur nie powinno zmniejszać projektowego obciążenia cieplnego,
- obejście letnie wymiennika i aktywny odzysk ciepła nie powinny być jednocześnie traktowane jako dwa pełne tryby pracy tego samego strumienia,
- energia jednego centralnego urządzenia nie może być mnożona przez liczbę stref.

## 7. Testy regresyjne

Regresja oznacza, że znany przypadek obliczeniowy ma zachować oczekiwany wynik po zmianach w kodzie.

W projekcie utrzymywane są między innymi testy dotyczące:

- powierzchni brutto i netto przegród,
- przypisywania okien do ścian,
- mostków cieplnych,
- promieniowania na różne orientacje,
- odzysku ciepła,
- ochrony przed zamarzaniem,
- modelu gruntu,
- miesięcznego ogrzewania i chłodzenia,
- projektowego obciążenia cieplnego,
- energii pomocniczej,
- udziału odnawialnych nośników energii.

## 8. Benchmarki i porównania niezależne

Tam, gdzie są dostępne odpowiednie przypadki, wyniki powinny być porównywane z niezależnymi źródłami.

Mogą to być między innymi:

- przypadki BESTEST / ANSI/ASHRAE Standard 140,
- przykłady numeryczne z literatury,
- niezależne programy obliczeniowe,
- sprawdzone arkusze obliczeniowe,
- przypadki referencyjne przygotowane przez eksperta.

Benchmark nie powinien być traktowany jako dowód zgodności całego programu. Sprawdza tylko określony zakres modelu.

## 9. Testy losowych danych

Dla losowo generowanych, ale fizycznie sensownych projektów należy sprawdzać przede wszystkim:

- brak błędów numerycznych,
- brak ujemnych powierzchni i energii użytkowych,
- poprawność zakresów parametrów,
- stabilność solvera,
- poprawność walidacji geometrii.

## 10. Testy API

Testy API powinny obejmować między innymi:

- poprawny projekt,
- projekt z brakującymi danymi,
- projekt z błędną geometrią,
- projekt z niekompletnymi danymi trybu świadectwa,
- import i eksport danych projektu,
- poprawne komunikaty błędów.

## 11. Testy interfejsu

Testy końcowe interfejsu powinny sprawdzać:

- utworzenie projektu,
- wprowadzenie podstawowych danych budynku,
- wprowadzenie danych formalnych,
- uruchomienie obliczenia,
- rozróżnienie wyniku formalnego i godzinowego,
- czytelne wyświetlenie ostrzeżeń i błędów,
- import i eksport projektu,
- działanie na różnych szerokościach ekranu.

## 12. Tolerancje

Tolerancja musi wynikać z charakteru testu.

Nie należy stosować jednej wartości procentowej do wszystkich przypadków.

Przykładowo:

- test analityczny prostego wzoru może wymagać zgodności praktycznie dokładnej,
- porównanie miesięcznego wyniku z niezależnym programem może wymagać tolerancji procentowej,
- porównanie temperatur godzinowych może wymagać tolerancji w kelwinach.

Każdy benchmark powinien opisywać:

- źródło wartości referencyjnej,
- dane wejściowe,
- oczekiwany wynik,
- dopuszczalną tolerancję,
- uzyskany wynik,
- różnicę.

## 13. Proces przed scaleniem zmian

Zmiana w silniku obliczeniowym powinna przejść co najmniej:

```bash
cd backend
ruff check app tests
mypy app
pytest
```

Zmiana we frontendzie powinna przejść:

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

Nowa funkcja fizyczna powinna mieć test analityczny albo benchmark.

## 14. Raportowanie

Wyniki ważniejszych benchmarków należy dokumentować tak, aby można było odtworzyć:

- wersję kodu,
- dane wejściowe,
- źródło referencyjne,
- wynik oczekiwany,
- wynik programu,
- różnicę i tolerancję.
