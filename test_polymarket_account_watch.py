import unittest

from polymarket_account_watch import format_messages, trade_key, unseen_trades


class AccountWatchTests(unittest.TestCase):
    def sample(self, timestamp=100, transaction="0xabc"):
        return {
            "timestamp": timestamp,
            "transaction_hash": transaction,
            "token_id": "1",
            "side": "BUY",
            "outcome": "Yes",
            "size": 10,
            "price": .25,
            "usdc_size": 2.5,
            "title": "Example market?",
            "event_slug": "example-market",
        }

    def test_seen_and_pre_start_trades_are_filtered(self):
        old = self.sample(timestamp=99, transaction="0xold")
        seen = self.sample(timestamp=101, transaction="0xseen")
        new = self.sample(timestamp=102, transaction="0xnew")
        self.assertEqual(unseen_trades([old, seen, new], [trade_key(seen)], 100), [new])

    def test_message_has_execution_details(self):
        message = format_messages("bilberry", [self.sample()])[0]
        self.assertIn("@bilberry", message)
        self.assertIn("买入 Yes", message)
        self.assertIn("成交价：0.250", message)
        self.assertIn("金额：$2.50", message)
        self.assertIn("https://polymarket.com/event/example-market", message)


if __name__ == "__main__":
    unittest.main()
