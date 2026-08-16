# Energoliczydło

Aplikacja webowa do obliczania charakterystyki energetycznej budynków metodą godzinową zgodnie z normą **PN-EN ISO 52016-1** oraz polską metodologią wyznaczania charakterystyki energetycznej budynku.

## Architektura

- **Frontend**: Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui
- **Backend**: FastAPI (Python 3.11+)
- **Silnik obliczeniowy**: własna implementacja w Pythonie (NumPy / Pandas) z walidacją poprzez `pyBuildingEnergy`
- **Dane klimatyczne**: predefiniowane typowe lata meteorologiczne (TMY) dla polskich stacji meteorologicznych

## Wymagania

- Python 3.11+
- Node.js 20+
- pnpm (zalecany) lub npm
- Docker + docker-compose (opcjonalnie)

## Szybki start (lokalnie)

### 1. Pierwsza instalacja

Wymagania: Python 3.11+, Node.js 20+, pnpm.

```bash
# Zainstaluj wszystkie zależności (backend + frontend)
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd ../frontend
pnpm install
```

### 2. Uruchomienie

Z głównego katalogu projektu:

```bash
# Uruchamia backend (port 8000) i frontend (port 3001) jednocześnie
pnpm dev
```

Lub osobno w dwóch terminalach:

```bash
# Terminal 1 — backend
cd backend
PYTHONPATH=$(pwd) .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — frontend
cd frontend
pnpm dev --port 3001
```

Adresy:

- Frontend: http://localhost:3001
- Backend API docs: http://localhost:8000/docs
- Backend health: http://localhost:8000/api/health/

> Port `3000` jest często zajęty przez inne projekty, dlatego frontend domyślnie działa na `3001`.

### Docker (opcjonalnie)

```bash
docker-compose up --build
```

## Rozwój

Szczegóły architektury, modelu danych i planu testowania znajdują się w dokumentacji:

- `docs/INPUT_SCHEMA.md` – model danych wejściowych
- `docs/VALIDATION.md` – strategia testów i benchmarki
- `docs/METHODOLOGY.md` – opis zastosowanej metodologii normowej

## Status

Projekt w fazie MVP.
