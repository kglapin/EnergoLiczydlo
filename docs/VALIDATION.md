# Strategia testowania i walidacji

## Cele

1. Upewnić się, że obliczenia są **zgodne z PN-EN ISO 52016-1** i polską metodologią.
2. Wykryć błędy na najwcześniejszym etapie (testy jednostkowe, integracyjne, regresyjne).
3. Porównać wyniki z niezależnymi benchmarkami i przykładami użytkownika.
4. Zapewnić stabilność obliczeń przy zmianach kodu.

## Warstwy testów

### 1. Testy jednostkowe (pytest)

Każdy moduł silnika ma testy jednostkowe:

- `climate` – wczytywanie EPW, położenie słońca, promieniowanie na powierzchnie pochylone.
- `envelope` – obliczenia `U` w tym mostków, powierzchnie, orientacje.
- `solar` – zyski słoneczne, kąty padania, ekranowanie.
- `ventilation` – straty ciepła, odzysk ciepła, infiltracja.
- `internal_gains` – harmonogramy, gęstości obciążeń.
- `thermal_balance` – bilans godzinowy, stabilność numeryczna.
- `systems` – sprawności, COP pompy ciepła, C.W.U.
- `primary_energy` – przeliczenia `Ep`, `EC`.

Każdy test:
- podaje konkretne dane wejściowe,
- porównuje wynik z wartością analityczną lub referencyjną,
- określa dopuszczalną tolerancję.

### 2. Testy integracyjne

- Pełny przepływ: dane wejściowe `BuildingProject` → silnik → `CalculationResult`.
- Testy na „sztucznych latach”:
  - stała temperatura zewnętrzna przez cały rok,
  - brak nasłonecznienia,
  - stałe zyski wewnętrzne,
  - bardzo zimny rok / bardzo ciepły rok.
- Sprawdzenie niezmienników fizycznych:
  - `Ek >= Eu` (przy sprawnościach ≤ 1),
  - `Ep >= Ek` (przy współczynnikach fp ≥ 1),
  - roczne zapotrzebowanie nieujemne,
  - temperatury wewnętrzne w sensownym zakresie.

### 3. Testy regresyjne / benchmarki

- **Przypadki użytkownika** – jeśli dostarczone, każdy przypadek to osobny test z tolerancją ±2% dla wskaźników rocznych.
- **pyBuildingEnergy** – dla uproszczonego budynku referencyjnego porównujemy zapotrzebowanie na ogrzewanie/chłodzenie.
- **BESTEST** – standardowe przypadki testowe ISO 14955 / ANSI/ASHRAE Standard 140.
- **Publikacje** – porównanie z przykładami numerycznymi z literatury (np. Narowski, „Dane klimatyczne do obliczeń energetycznych w budownictwie”).

### 4. Testy property-based (hypothesis)

- Generowanie losowych, ale sensownych danych wejściowych.
- Sprawdzenie niezmienników (np. `Ep >= Ek >= Eu >= 0`).
- Wykrywanie ekstremalnych przypadków prowadzących do błędów numerycznych.

### 5. Testy API

- `pytest` z `TestClient` FastAPI:
  - walidacja błędnych danych wejściowych (HTTP 422),
  - poprawność odpowiedzi dla przykładowego budynku,
  - import / eksport JSON.

### 6. Testy frontend (Playwright)

- Przepływ użytkownika: utworzenie nowej analizy, wypełnienie kreatora, uruchomienie obliczeń, wyświetlenie wyników.
- Testy importu / eksportu JSON.
- Testy responsywności.

## Tolerancje

| Wielkość | Tolerancja względem benchmarku |
|----------|---------------------------------|
| Wskaźniki roczne `Eu`, `Ek`, `Ep` | ±2% |
| Miesięczne wartości energii | ±5% |
| Szczytowe obciążenie ogrzewania / chłodzenia | ±5% |
| Temperatura wewnętrzna (godzinowa) | ±0.5 K |

## Proces testowania

1. Każda nowa funkcja silnika musi mieć test jednostkowy przed merge.
2. Przy każdym push uruchamiane są wszystkie testy (GitHub Actions).
3. Zmiana w silniku obliczeniowym wymaga ponownego uruchomienia benchmarków i aktualizacji `VALIDATION.md`.
4. Każdy benchmark opisany jest w dokumencie: dane wejściowe, źródło, oczekiwany wynik, uzyskany wynik, różnica.

## Lista benchmarków do zaimplementowania

- [ ] Budynek referencyjny 1: prostopadłościan, jedna strefa, Warszawa TMYx, ogrzewanie gazowe.
- [ ] Budynek referencyjny 2: ten sam budynek, pompa ciepła powietrze-woda.
- [ ] Budynek z dużą ilością okien południowych – test zysków słonecznych.
- [ ] Budynek bardzo dobrze zaizolowany – test minimalnych strat.
- [ ] Przypadek użytkownika #1 (do uzupełnienia).
- [ ] Przypadek użytkownika #2 (do uzupełnienia).
- [ ] Porównanie z `pyBuildingEnergy` dla budynku referencyjnego.
- [ ] Porównanie z BESTEST (jeśli dostępne dane).

## Raportowanie

Wyniki walidacji zapisywane są w:
- `backend/tests/benchmarks/RESULTS.md`
- CI generuje raport pokrycia testów.
