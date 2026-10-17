# api/

FastAPI backend. Mirrors CivicLens `answers/`.

Planned files:
- `main.py`: app and endpoints (sites, scores, alerts, reports, ask)
- `llm.py`: the one wrapper every Gemini call goes through
- `sql_guard.py`: port of CivicLens's guard to Postgres (read-only role + statement_timeout)
- `schema.py`: schema description handed to the model

Rule: the model writes the query, the database produces the numbers.
