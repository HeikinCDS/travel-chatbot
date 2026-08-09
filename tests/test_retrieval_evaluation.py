import unittest

from scripts.evaluate_retrieval import rank_metrics, summarise


class RetrievalEvaluationTests(unittest.TestCase):
    def test_rank_metrics(self):
        self.assertEqual(rank_metrics(["A2"], ["A1", "A2", "A3"]), (1, 0.5))
        self.assertEqual(rank_metrics(["A4"], ["A1", "A2", "A3"]), (0, 0.0))

    def test_summary(self):
        summary = summarise([
            {"hit": 1, "reciprocal_rank": 1.0, "elapsed_ms": 10.0},
            {"hit": 0, "reciprocal_rank": 0.0, "elapsed_ms": 20.0},
        ])
        self.assertEqual(summary["hit_at_3"], 0.5)
        self.assertEqual(summary["mrr"], 0.5)
        self.assertEqual(summary["average_ms"], 15.0)
        self.assertEqual(summary["warm_average_ms"], 20.0)
        self.assertEqual(summary["median_ms"], 15.0)
        self.assertEqual(summary["maximum_ms"], 20.0)


if __name__ == "__main__":
    unittest.main()
