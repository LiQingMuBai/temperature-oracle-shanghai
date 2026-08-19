import datetime as dt, unittest
import app

class TestCore(unittest.TestCase):
    def test_decision(self):
        self.assertEqual(app.decision(37)["level"], "红色")
        self.assertEqual(app.decision(34)["level"], "黄色")
    def test_ridge(self):
        xs = [[1, i] for i in range(20)]; ys = [2 + 3*i for i in range(20)]
        m = app.fit_ridge(xs, ys, alpha=0)
        self.assertAlmostEqual(app.predict(m, [1, 21]), 65, places=5)

if __name__ == "__main__": unittest.main()
