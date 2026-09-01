import unittest
from telegram_polymarket_monitor import apply_market_fusion, candidates, condition_on_observed_max, execution_limit, fill_cost, format_alert


class MonitorTests(unittest.TestCase):
    def test_market_fusion_is_normalized(self):
        analysis={"ranking":[
            {"outcome":"30°C","weather_prob":.6,"market_prob":.4,"spread":.02,"bid_size":100,"ask_size":100},
            {"outcome":"31°C","weather_prob":.4,"market_prob":.6,"spread":.02,"bid_size":100,"ask_size":100}]}
        meta=apply_market_fusion(analysis,"3h")
        self.assertAlmostEqual(sum(x["prediction_prob"] for x in analysis["ranking"]),1)
        self.assertGreater(meta["market_weight"],.5)
        self.assertEqual(meta["base_weight"],.85)
    def test_current_day_max_conditions_distribution(self):
        analysis={"model_forecasts_c":{"a":29,"b":32},"ranking":[
            {"outcome":"29°C","weather_prob":.3},{"outcome":"30°C","weather_prob":.2},
            {"outcome":"31°C","weather_prob":.3},{"outcome":"32°C","weather_prob":.2}]}
        condition_on_observed_max(analysis,31)
        self.assertEqual(analysis["ranking"][0]["weather_prob"],0)
        self.assertAlmostEqual(analysis["ranking"][2]["weather_prob"],.6)
        self.assertEqual(analysis["model_forecasts_c"]["a"],31)
    def test_fill_cost_includes_depth(self):
        cost = fill_cost([{"price": .2, "size": 5}, {"price": .3, "size": 5}], 10)
        self.assertAlmostEqual(cost, 2.5)
        self.assertEqual(execution_limit([{"price": .2, "size": 5}, {"price": .3, "size": 5}], 10), .3)

    def test_adjacent_pair_net_edge(self):
        analysis = {"model_forecasts_c": {"a": 30, "b": 30.1, "c": 31, "d": 33, "e": 34}, "ranking": [
            {"outcome": "30°C", "weather_prob": .4, "ask_levels": [{"price": .2, "size": 10}]},
            {"outcome": "31°C", "weather_prob": .4, "ask_levels": [{"price": .3, "size": 10}]},
            {"outcome": "32°C", "weather_prob": .2, "ask_levels": [{"price": .5, "size": 10}]},
        ]}
        best = candidates(analysis, 10, .1, min_model_support=2)[0]
        self.assertEqual(best["outcomes"], ["30°C", "31°C"])
        self.assertTrue(best["qualifies"])
        self.assertTrue(best["contains_market_mode"])
        self.assertEqual(best["legs"][0]["limit_price"], .2)
        best["portfolio_available_cash_usd"] = 8
        message = format_alert({"contract_date":"2026-08-20","slug":"test"}, best)
        self.assertIn("下单前可用现金：$8.00", message)


if __name__ == "__main__":
    unittest.main()
