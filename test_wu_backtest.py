import unittest
from wu_backtest import TableParser

class TestWU(unittest.TestCase):
    def test_month_table(self):
        p=TableParser();p.feed('<table class="observations-table"><tr><td>8/1/2025</td><td>31 °C / 27 °C</td></tr></table>')
        self.assertEqual(p.rows,[["8/1/2025","31 °C / 27 °C"]])
if __name__=="__main__":unittest.main()
