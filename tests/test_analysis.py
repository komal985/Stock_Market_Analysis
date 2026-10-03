import unittest

import pandas as pd

from analysis import (
    calculate_metrics,
    clean_stock_data,
    convert_price_values,
    enrich_stock_data,
    monthly_returns,
)


class StockAnalysisTests(unittest.TestCase):
    def test_cleaning_normalizes_aliases_and_removes_invalid_or_duplicate_rows(self) -> None:
        raw = pd.DataFrame(
            {
                " timestamp ": ["2024-01-03", "invalid", "2024-01-02", "2024-01-03"],
                "Adj Close": ["12", "10", "11", "13"],
                "Volume": [100, 200, 150, 110],
            }
        )

        cleaned = clean_stock_data(raw)

        self.assertEqual(cleaned["Date"].tolist(), [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")])
        self.assertEqual(cleaned["Close"].tolist(), [11, 13])
        self.assertEqual(cleaned["Open"].tolist(), [11, 13])

    def test_cleaning_rejects_missing_required_columns_and_empty_valid_data(self) -> None:
        with self.assertRaisesRegex(ValueError, "Date"):
            clean_stock_data(pd.DataFrame({"Close": [10]}))
        with self.assertRaisesRegex(ValueError, "No valid rows"):
            clean_stock_data(pd.DataFrame({"Date": ["not a date"], "Close": [10]}))

    def test_cleaning_prefers_close_when_adjusted_close_is_also_present(self) -> None:
        cleaned = clean_stock_data(
            pd.DataFrame(
                {"Date": ["2024-01-02"], "Adj Close": [9], "Close": [10]}
            )
        )

        self.assertEqual(cleaned["Close"].iloc[0], 10)

    def test_cleaning_drops_non_finite_prices(self) -> None:
        cleaned = clean_stock_data(
            pd.DataFrame(
                {"Date": ["2024-01-02", "2024-01-03"], "Close": [10, float("inf")]}
            )
        )

        self.assertEqual(cleaned["Close"].tolist(), [10])

    def test_metrics_and_derived_series(self) -> None:
        cleaned = clean_stock_data(
            pd.DataFrame(
                {
                    "Date": pd.date_range("2024-01-01", periods=3),
                    "Close": [100, 110, 99],
                    "Volume": [1000, 1500, 2000],
                }
            )
        )

        enriched = enrich_stock_data(cleaned, moving_averages=(2,))
        metrics = calculate_metrics(enriched)

        self.assertAlmostEqual(metrics["period_return"], -0.01)
        self.assertAlmostEqual(metrics["max_drawdown"], -0.10)
        self.assertEqual(metrics["average_volume"], 1500)
        self.assertAlmostEqual(enriched["Daily Return"].iloc[1], 0.10)
        self.assertAlmostEqual(enriched["MA 2"].iloc[-1], 104.5)
        self.assertTrue(enriched["RSI 14"].isna().all())

    def test_rsi_handles_sustained_gains_and_losses(self) -> None:
        rising = clean_stock_data(
            pd.DataFrame({"Date": pd.date_range("2024-01-01", periods=16), "Close": range(100, 116)})
        )
        falling = clean_stock_data(
            pd.DataFrame({"Date": pd.date_range("2024-01-01", periods=16), "Close": range(116, 100, -1)})
        )

        self.assertEqual(enrich_stock_data(rising)["RSI 14"].iloc[-1], 100)
        self.assertEqual(enrich_stock_data(falling)["RSI 14"].iloc[-1], 0)

    def test_currency_conversion_scales_prices_only(self) -> None:
        enriched = enrich_stock_data(
            clean_stock_data(
                pd.DataFrame(
                    {
                        "Date": pd.date_range("2024-01-01", periods=2),
                        "Open": [10, 12],
                        "High": [11, 13],
                        "Low": [9, 11],
                        "Close": [10, 12],
                        "Volume": [100, 200],
                    }
                )
            ),
            moving_averages=(2,),
        )

        converted = convert_price_values(enriched, 90.0)

        self.assertEqual(converted["Close"].tolist(), [900, 1080])
        self.assertEqual(converted["MA 2"].tolist(), [900, 990])
        self.assertEqual(converted["Volume"].tolist(), [100, 200])
        self.assertTrue(converted["Daily Return"].equals(enriched["Daily Return"]))
        self.assertEqual(enriched["Close"].tolist(), [10, 12])

    def test_currency_conversion_rejects_invalid_rates(self) -> None:
        data = pd.DataFrame({"Close": [10.0]})
        for rate in (0, -1, float("nan"), float("inf")):
            with self.subTest(rate=rate), self.assertRaisesRegex(ValueError, "finite positive"):
                convert_price_values(data, rate)

    def test_monthly_returns_need_at_least_two_months(self) -> None:
        one_month = clean_stock_data(
            pd.DataFrame({"Date": ["2024-01-02", "2024-01-31"], "Close": [100, 110]})
        )
        self.assertTrue(monthly_returns(one_month).empty)

        multiple_months = clean_stock_data(
            pd.DataFrame(
                {"Date": ["2024-01-02", "2024-01-31", "2024-02-01", "2024-02-29"], "Close": [100, 110, 110, 121]}
            )
        )
        table = monthly_returns(multiple_months)
        self.assertAlmostEqual(table.loc[2024, 2], 0.10)

    def test_metrics_support_a_single_observation(self) -> None:
        cleaned = clean_stock_data(pd.DataFrame({"Date": ["2024-01-02"], "Close": [100]}))
        metrics = calculate_metrics(enrich_stock_data(cleaned))

        self.assertEqual(metrics["period_return"], 0)
        self.assertEqual(metrics["annualized_volatility"], 0)
        self.assertEqual(metrics["max_drawdown"], 0)


if __name__ == "__main__":
    unittest.main()
