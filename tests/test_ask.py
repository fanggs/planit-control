"""POST /ask, with Gemini and the restricted database faked.

Run: .venv/bin/python -m unittest tests.test_ask -v
"""
import importlib
import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import ask, llm
from db.ask_query import validate_query

SQL = "SELECT s.name, max(f.wind_mph) AS max_wind FROM public.weather_forecasts f JOIN public.sites s ON s.site_id = f.site_id GROUP BY s.name"
ROWS = [{"name": "Turkey Point", "max_wind": 21.93}, {"name": "Douglas", "max_wind": 0.0}]


def fake_llm(sql=SQL, answers=("Turkey Point peaks at 21.93 mph.",)):
    """Stand-in for llm.ask_json: first the SQL step, then the answer step(s)."""
    replies = iter(answers)

    def ask_json(prompt, shape):
        if shape is ask._SQL:
            return ask._SQL(sql=sql)
        return ask._Answer(answer=next(replies))
    return patch.object(llm, "ask_json", side_effect=ask_json)


def fake_db(rows=ROWS, truncated=False):
    return patch.object(ask, "run", return_value={"columns": list(rows[0]) if rows else [],
                                                  "rows": rows, "truncated": truncated})


class AskTest(unittest.TestCase):
    def test_grounded_answer_with_sql_and_sources(self):
        with fake_llm(), fake_db(), patch.object(ask, "sources", return_value=[{"label": "Open-Meteo", "url": "https://open-meteo.com/"}]):
            r = ask.answer("Which plant has the strongest wind?")
        self.assertEqual(r["answer"], "Turkey Point peaks at 21.93 mph.")
        self.assertEqual(r["sql"], SQL)
        self.assertEqual(r["sources"][0]["label"], "Open-Meteo")

    def test_made_up_number_falls_back_to_the_rows(self):
        with fake_llm(answers=("Turkey Point peaks at 45 mph.", "Still 45 mph.")), fake_db(), \
             patch.object(ask, "sources", return_value=[]):
            r = ask.answer("Which plant has the strongest wind?")
        self.assertNotIn("45", r["answer"])
        self.assertIn("Turkey Point", r["answer"])

    def test_no_sql_means_cannot_answer(self):
        with fake_llm(sql=None):
            self.assertEqual(ask.answer("What's the CEO's favorite color?"),
                             {"answer": None, "reason": "cannot_answer"})

    def test_rejected_twice_means_cannot_answer(self):
        with fake_llm(), patch.object(ask, "run", side_effect=ValueError("Relation is not allowlisted")) as run:
            self.assertEqual(ask.answer("Show me crew reports")["reason"], "cannot_answer")
        self.assertEqual(run.call_count, 2)  # one retry with the guard's message

    def test_guard_blocks_writes_and_private_tables(self):
        for bad in ("DELETE FROM public.alerts",
                    "SELECT * FROM public.hazard_reports",
                    "SELECT 1; DROP TABLE public.sites",
                    "SELECT * FROM public.sites FOR UPDATE"):
            with self.assertRaises(ValueError, msg=bad):
                validate_query(bad)

    def test_numbers_must_come_from_rows(self):
        rows = [{"name": "Yucca", "heat_index_f": 87.38, "valid_at": "2026-10-18T21:00:00Z"}]
        self.assertEqual(ask.ungrounded("Yucca reaches 87.38°F around 21:00.", rows, "hottest?"), [])
        self.assertEqual(ask.ungrounded("Yucca reaches 90°F.", rows, "hottest?"), ["90"])

    def test_values_rounded_and_zero_kept(self):
        self.assertEqual(ask._plain(Decimal("21.93440")), 21.93)
        self.assertEqual(ask._plain(0.0), 0.0)

    def test_sources_come_from_rows_and_model_provenance(self):
        rows = [{"name": "Yucca", "source_name": "Open-Meteo", "source_url": "https://open-meteo.com/"}]
        sql = "SELECT s.name, f.source_name, f.source_url FROM public.weather_forecasts f JOIN public.screening_predictions p ON true"
        labels = [s["label"] for s in ask.sources(sql, rows)]
        self.assertEqual(labels, ["Open-Meteo", ask.PROVENANCE["screening_predictions"]["label"]])


class AskRouteTest(unittest.TestCase):
    def setUp(self):
        # Other tests reload api.main under their own settings; start from a clean one.
        with patch.dict("os.environ", {"PLANIT_DATA": "sample"}, clear=True):
            self.main = importlib.reload(importlib.import_module("api.main"))
        self.main.app.dependency_overrides[self.main._require_data_viewer] = lambda: None
        self.client = TestClient(self.main.app)

    def test_route_returns_contract_shapes(self):
        with patch.object(ask, "answer", return_value={"answer": None, "reason": "cannot_answer"}):
            r = self.client.post("/ask", json={"question": "favorite color?"})
        self.assertEqual(r.json(), {"answer": None, "reason": "cannot_answer"})

    def test_unconfigured_login_is_503(self):
        with fake_llm(), patch.dict("os.environ", {"PLANIT_ASK_DATABASE_URL": "", "PLANIT_ASK_PASSWORD": ""}):
            r = self.client.post("/ask", json={"question": "How many plants?"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["code"], "service_unavailable")

    def test_requires_login(self):
        self.main.app.dependency_overrides.clear()
        self.assertIn(TestClient(self.main.app).post("/ask", json={"question": "How many plants?"}).status_code, (401, 503))


if __name__ == "__main__":
    unittest.main()
