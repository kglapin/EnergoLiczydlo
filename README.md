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

## Szybki start

### Lokalnie (bez Docker)

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (w osobnym terminalu)
cd frontend
pnpm install
pnpm dev
```

### Docker

```bash
docker-compose up --build
```

Frontend: http://localhost:3000  
Backend API: http://localhost:8000/docs

## Rozwój

Szczegóły architektury, modelu danych i planu testowania znajdują się w dokumentacji:

- `docs/INPUT_SCHEMA.md` – model danych wejściowych
- `docs/VALIDATION.md` – strategia testów i benchmarki
- `docs/METHODOLOGY.md` – opis zastosowanej metodologii normowej

## Status

Projekt w fazie MVP.
