import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.index import app


class MarketLensApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health_and_static_dashboard(self) -> None:
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Market overview", dashboard.text)

    def test_demo_starts_in_2021_and_reaches_today(self) -> None:
        response = self.client.get("/api/demo")

        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        self.assertEqual(rows[0]["Date"][:10], "2021-01-01")
        self.assertLessEqual(rows[-1]["Date"][:10], date.today().isoformat())
        self.assertGreater(len(rows), 1_000)

    @patch("api.index.get_usd_inr_rate", return_value=(90.0, "test update time"))
    def test_analyze_returns_converted_prices_and_unchanged_returns(self, mocked_rate) -> None:
        response = self.client.post(
            "/api/analyze",
            json={
                "rows": [
                    {"Date": "2024-01-01", "Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 100},
                    {"Date": "2024-01-02", "Open": 11, "High": 13, "Low": 10, "Close": 12, "Volume": 200},
                ],
                "short_window": 2,
                "long_window": 3,
                "currency": "USD",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual([row["Close"] for row in result["rows"]], [900.0, 1080.0])
        self.assertEqual([row["Volume"] for row in result["rows"]], [100, 200])
        self.assertAlmostEqual(result["rows"][1]["Daily Return"], 0.2)
        self.assertEqual(result["metrics"]["latest_close"], 1080)
        self.assertEqual(result["usd_inr_rate"], 90)
        mocked_rate.assert_called_once_with(False)

    def test_invalid_windows_and_date_range_return_actionable_errors(self) -> None:
        body = {
            "rows": [
                {"Date": "2024-01-01", "Close": 10},
                {"Date": "2024-01-02", "Close": 12},
            ],
            "short_window": 10,
            "long_window": 10,
            "currency": "INR",
        }
        invalid_windows = self.client.post("/api/analyze", json=body)
        self.assertEqual(invalid_windows.status_code, 422)
        self.assertIn("Short moving-average", invalid_windows.json()["detail"])

        body["short_window"] = 2
        body["long_window"] = 3
        body["start_date"] = "2025-01-01"
        body["end_date"] = "2025-01-31"
        outside_data = self.client.post("/api/analyze", json=body)
        self.assertEqual(outside_data.status_code, 422)
        self.assertIn("No valid trading observations", outside_data.json()["detail"])


if __name__ == "__main__":
    unittest.main()
