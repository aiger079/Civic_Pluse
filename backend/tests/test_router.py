import unittest
from router import haversine_distance, HelperRouter

class TestHelperRouter(unittest.TestCase):
    def test_haversine_distance(self):
        # 2 points roughly 100-200m apart
        d = haversine_distance(28.4595, 77.0266, 28.4598, 77.0270)
        self.assertGreater(d, 40)
        self.assertLess(d, 100)

    def test_match_helpers(self):
        router = HelperRouter()
        # Incident in Block B
        results = router.match_helpers(28.4595, 77.0266, required_capability="drainage_pump", top_k=3)
        self.assertGreater(len(results), 0)
        self.assertLessEqual(len(results), 3)
        # Check first match has drainage_pump
        self.assertIn("drainage_pump", results[0]["capabilities"])
        # Helper h_106 is unavailable and should NOT be in results
        result_ids = [r["id"] for r in results]
        self.assertNotIn("h_106", result_ids)

if __name__ == "__main__":
    unittest.main()
