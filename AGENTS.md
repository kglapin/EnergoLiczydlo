# AGENTS.md – wskazówki dla asystentów AI

## Cel projektu

Budowa aplikacji webowej do obliczeń charakterystyki energetycznej budynków z wykorzystaniem modelu godzinowego PN-EN ISO 52016-1 oraz polskiej metodologii wyznaczania charakterystyki energetycznej.

Poprawność obliczeń jest krytyczna. Wszystkie zmiany w silniku obliczeniowym muszą być pokryte testami i, tam gdzie jest to możliwe, porównaniem z wartością analityczną albo niezależnym przypadkiem referencyjnym.

## Architektura

- `backend/app/engine` – silnik obliczeniowy w Pythonie z użyciem Pydantic, NumPy i Pandas.
- `backend/app/api` – endpointy FastAPI.
- `backend/app/schemas` – modele Pydantic dla API.
- `backend/data/tmy` – dane klimatyczne typowego roku meteorologicznego.
- `frontend/app` – aplikacja Next.js z App Router.
- `frontend/components` – komponenty React, preferowane shadcn/ui.
- `frontend/lib` – funkcje pomocnicze, typy TypeScript i klient API.

## Uruchamianie lokalne

Najszybszy sposób – jednoczesne uruchomienie backendu i frontendu:

```bash
# Z głównego katalogu projektu
pnpm dev
```

Osobno:

```bash
# Terminal 1 – backend
cd backend
PYTHONPATH=$(pwd) .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 – frontend
cd frontend
pnpm dev --port 3001
```

Backend udostępnia API pod `http://localhost:8000`, a frontend domyślnie pod `http://localhost:3001`.

## Weryfikacja po zmianach

```bash
# Backend
cd backend
ruff check app tests
mypy app
pytest

# Frontend
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

## Konwencje techniczne

- Python: Ruff, mypy w trybie ścisłym, type hints i docstringi dla funkcji fizycznych.
- TypeScript: tryb ścisły, Zod do walidacji formularzy.
- Interfejs: shadcn/ui i Tailwind CSS; rozbudowane formularze dzielone na logiczne kroki.
- Testy: pytest po stronie backendu, Playwright dla testów końcowych interfejsu.

## Zasady dotyczące obliczeń

- Nie zgaduj wartości fizycznych, prawnych ani normowych.
- Jeżeli wymaganej wartości nie można bezpiecznie wyznaczyć, obliczenie formalne ma zostać zablokowane albo pole ma pozostać jawnie wymagane.
- Każda nowa funkcja w silniku musi mieć test jednostkowy z porównaniem do wartości analitycznej albo benchmarku.
- Dane klimatyczne dla modelu godzinowego muszą być weryfikowane pod kątem kompletności 8760 godzin.
- Wynik formalnej charakterystyki energetycznej i wynik godzinowej analizy fizycznej muszą być opisywane jako dwa różne wyniki, jeżeli korzystają z różnych procedur obliczeniowych.

## Zasady dokumentacji i tekstów w interfejsie

- Opisy przeznaczone dla użytkownika oraz dokumentacja projektu mają być pisane po polsku.
- Tekst ma być możliwie jasny i jednoznaczny. Nie używaj niepotrzebnego żargonu ani skrótów bez wyjaśnienia.
- Przy pierwszym użyciu skrótu należy podać pełną nazwę, np. „energia użytkowa (`Eu`)”, „energia końcowa (`Ek`)”, „nieodnawialna energia pierwotna (`Ep`)”, „typowy rok meteorologiczny (TMY)”.
- Unikaj angielskich określeń, jeżeli istnieje jasny polski odpowiednik. Zamiast `fail-closed` pisz „blokada obliczenia przy braku wymaganych danych”, zamiast `design load` – „projektowe obciążenie cieplne”, zamiast `preheater` – „nagrzewnica wstępna”, a zamiast `dual-engine` – „dwa równoległe silniki obliczeniowe”.
- Nazwy technicznych pól JSON i kodu mogą pozostać angielskie, ale w dokumentacji należy obok nich wyjaśnić ich znaczenie po polsku.
- Każdy opis wyniku ma jasno wskazywać, czy jest to wynik formalnej metody świadectwa, wynik godzinowej analizy fizycznej, czy wynik projektowego obciążenia cieplnego.
