import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import streamlit as st
from streamlit.testing.v1 import AppTest


class DashboardAppTests(unittest.TestCase):
    def test_demo_dashboard_and_interactive_controls(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        response = Mock()
        response.json.return_value = {
            "result": "success",
            "base_code": "USD",
            "rates": {"INR": 90.0},
            "time_last_update_utc": "Sat, 03 Oct 2026 00:02:32 +0000",
        }
        st.cache_data.clear()
        with patch("requests.get", return_value=response) as get_rate:
            app = AppTest.from_file(str(app_path)).run(timeout=15)

            self.assertFalse(app.exception, [str(error.message) for error in app.exception])
            self.assertEqual(app.selectbox(key="period").value, "All time")
            self.assertTrue(any("Jan 2021" in item.value for item in app.caption))
            self.assertTrue(any("Live reference rate" in item.value for item in app.caption))
            self.assertTrue(any(item.label == "Latest close" and item.value.startswith("₹") for item in app.metric))

            app.selectbox(key="period").select("3M").run(timeout=15)
            app.selectbox(key="chart_style").select("Candlestick").run(timeout=15)
            app.checkbox(key="show_rsi").check().run(timeout=15)
            app.selectbox(key="return_filter").select("Up sessions").run(timeout=15)

            self.assertFalse(app.exception, [str(error.message) for error in app.exception])
            self.assertEqual(app.selectbox(key="period").value, "3M")
            self.assertEqual(app.selectbox(key="chart_style").value, "Candlestick")
            self.assertTrue(app.checkbox(key="show_rsi").value)
            self.assertEqual(app.selectbox(key="return_filter").value, "Up sessions")
            get_rate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
