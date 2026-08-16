# AGENTS.md – Wskazówki dla asystentów AI

## Cel projektu

Budowa aplikacji webowej do obliczeń charakterystyki energetycznej budynków zgodnie z PN-EN ISO 52016-1 oraz polską metodologią. Poprawność obliczeń jest krytyczna – wszystkie zmiany w silniku obliczeniowym muszą być pokryte testami i benchmarkami.

## Architektura

- `backend/app/engine` – silnik obliczeniowy (Python, Pydantic, NumPy, Pandas).
- `backend/app/api` – endpointy FastAPI.
- `backend/app/schemas` – modele Pydantic dla API.
- `backend/data/tmy` – predefiniowane dane klimatyczne TMY (EPW).
- `frontend/app` – aplikacja Next.js (App Router).
- `frontend/components` – komponenty React (preferowane shadcn/ui).
- `frontend/lib` – utils, typy TypeScript, API client.

## Uruchamianie lokalne

```bash
# Terminal 1: backend
cd backend
source .venv/bin/activate
PYTHONPATH=$(pwd) uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2: frontend
cd frontend
pnpm dev --port 3001   # port 3000 jest często zajęty
```

Backend udostępnia API pod `http://localhost:8000` (np. `/api/calculate/`, `/api/climate/stations`).
Frontend domyślnie startuje na `http://localhost:3001`.

## Konwencje

- Python: Ruff, mypy strict, type hints, docstrings dla funkcji fizycznych.
- TypeScript: strict mode, Zod do walidacji formularzy.
- UI: shadcn/ui + Tailwind CSS; formularze podzielone na kroki.
- Testy: pytest (backend), Playwright (e2e).

## Ważne zasady

- Nie zgaduj wartości fizycznych / normowych. Jeśli brakuje danych, zostaw placeholder z TODO i komentarz.
- Każda nowa funkcja w silniku musi mieć test jednostkowy z porównaniem do wartości analitycznej lub benchmarku.
- Dane klimatyczne muszą być weryfikowane pod kątem kompletności 8760 godzin.
- Zmiany w frontendzie muszą przechodzić `pnpm lint` i `pnpm typecheck`.

## Polecenia weryfikacji

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
