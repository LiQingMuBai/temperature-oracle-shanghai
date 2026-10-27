import tempfile
import unittest
from pathlib import Path

from polymarket_account_db import dashboard_data, record_trades
from polymarket_account_watch import trade_key


class AccountDbTests(unittest.TestCase):
    def test_repeated_buys_are_aggregated_and_colored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trades.sqlite3"
            base = {"token_id": "1", "condition_id": "c", "event_slug": "event",
                    "slug": "market", "title": "Market", "outcome": "Yes",
                    "side": "BUY", "price": .5, "size": 120, "usdc_size": 60}
            trades = [{**base, "timestamp": 1, "transaction_hash": "a"},
                      {**base, "timestamp": 2, "transaction_hash": "b"}]
            self.assertEqual(record_trades(path, "alice", "0x1", trades, trade_key), 2)
            data = dashboard_data(path)
            item = data["groups"][0]
            self.assertEqual(item["buy_count"], 2)
            self.assertEqual(item["buy_usdc"], 120)
            self.assertEqual(item["size_tier"], "large")
            self.assertTrue(item["is_repeated"])


if __name__ == "__main__":
    unittest.main()
