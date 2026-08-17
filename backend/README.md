# EnergoLiczydlo — Backend

Backend API do obliczeń charakterystyki energetycznej budynków metodą godzinową PN-EN ISO 52016-1 oraz polską metodologią miesięczną.

## Stack

- Python 3.11+, FastAPI, Pydantic v2, NumPy, Pandas
- Silnik obliczeniowy: `app/engine/`
- API: `app/api/`

## Uruchomienie

```bash
PYTHONPATH=$(pwd) .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Pełna dokumentacja w katalogu `../docs/`.
