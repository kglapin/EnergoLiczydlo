# Energoliczydło

Aplikacja webowa do obliczeń charakterystyki energetycznej budynków.

Projekt rozdziela trzy różne rodzaje wyników:

1. **wynik formalnej charakterystyki energetycznej w Polsce** – wyznaczany zgodnie z polską metodologią świadectw charakterystyki energetycznej,
2. **godzinową analizę fizyczną budynku** – wykonywaną dla 8760 godzin roku z wykorzystaniem modelu opartego na PN-EN ISO 52016-1,
3. **projektowe obciążenie cieplne** – osobne obliczenie mocy potrzebnej w zadanych warunkach projektowych.

Te wyniki nie są ze sobą utożsamiane. W trybie świadectwa główne wskaźniki formalne pochodzą z procedury wymaganej przez polską metodologię, natomiast wynik godzinowy pozostaje równoległą analizą techniczną.

## Najważniejsze wskaźniki

- **energia użytkowa (`Eu`)** – energia potrzebna do pokrycia potrzeb użytkowych budynku, m.in. ogrzewania, chłodzenia i przygotowania ciepłej wody użytkowej,
- **energia końcowa (`Ek`)** – energia dostarczona do systemów technicznych po uwzględnieniu ich sprawności i energii pomocniczej,
- **nieodnawialna energia pierwotna (`Ep`)** – energia końcowa przeliczona z użyciem właściwych współczynników nakładu dla zastosowanych nośników energii.

## Architektura

- **Frontend**: Next.js 14, TypeScript, Tailwind CSS, shadcn/ui.
- **Backend**: FastAPI, Python 3.11+.
- **Silnik godzinowy**: własna implementacja w Pythonie z użyciem NumPy i Pandas.
- **Formalny silnik świadectwa**: odrębna miesięczna procedura zgodna z polską metodologią.
- **Dane klimatyczne analizy godzinowej**: typowy rok meteorologiczny (TMY) zapisany w formacie EPW.

## Wymagania

- Python 3.11+
- Node.js 20+
- pnpm lub npm
- Docker i docker-compose – opcjonalnie

## Szybki start

### Instalacja zależności

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd ../frontend
pnpm install
```

### Uruchomienie

Z głównego katalogu projektu:

```bash
pnpm dev
```

Lub osobno:

```bash
# Backend
cd backend
PYTHONPATH=$(pwd) .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
pnpm dev --port 3001
```

Adresy:

- frontend: `http://localhost:3001`,
- dokumentacja API: `http://localhost:8000/docs`,
- kontrola działania backendu: `http://localhost:8000/api/health/`.

## Dokumentacja

Najważniejsze dokumenty:

- `docs/POLISH_CERTIFICATE_METHOD.md` – sposób działania formalnej metody świadectwa w Polsce,
- `docs/NORMATIVE_HOURLY_V2.md` – szczegółowa analiza godzinowa, grunt, odzysk ciepła i projektowe obciążenie cieplne,
- `docs/METHODOLOGY.md` – ogólna metodologia i relacje między poszczególnymi silnikami,
- `docs/COMPUTATION_LOGIC.md` – techniczny przebieg obliczeń,
- `docs/INPUT_SCHEMA.md` – dane wejściowe projektu,
- `docs/VALIDATION.md` – strategia testowania i walidacji,
- `docs/AUDIT_FIXES_2026-08-17.md` – poprawki wprowadzone po audycie obliczeń.

## Ważna zasada

Program nie powinien tworzyć pozornie formalnego wyniku na podstawie nieudokumentowanych wartości domyślnych. Jeżeli w trybie świadectwa brakuje danych wymaganych przez procedurę, obliczenie jest blokowane albo użytkownik musi jawnie podać brakującą wartość wraz ze źródłem.

## Status

Projekt jest rozwijanym narzędziem obliczeniowym. Przejście testów oprogramowania nie jest samo w sobie niezależnym potwierdzeniem zgodności każdej klauzuli normy lub aktu prawnego. W miejscach wymagających danych normowych, projektowych lub danych konkretnego urządzenia aplikacja wymaga ich jawnego podania i udokumentowania.
