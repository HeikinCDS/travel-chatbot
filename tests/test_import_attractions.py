import unittest

import pandas as pd

from scripts.import_attractions import build_attractions


class ImportAttractionsTests(unittest.TestCase):
    def test_merge_preserves_verified_legacy_fields_and_excludes_rejected(self):
        legacy = pd.DataFrame([{
            "attraction_id": "A001",
            "attraction_name": "Old Name",
            "entrance_fee_status": "Paid",
            "min_fee_myr": 10.0,
            "elderly_friendly": "Yes",
            "wheelchair_accessible": "Partial",
            "latitude": 1.5,
            "longitude": 103.7,
            "completeness": 90.0,
        }])
        master = pd.DataFrame([
            {
                "candidate_id": "MC0001",
                "existing_record_id": "A001",
                "attraction_name": "Confirmed Name",
                "state_territory": "Johor",
                "city_district": "Johor Bahru",
                "primary_category": "Park",
                "interests_tags": "nature; family",
                "setting": "Outdoor",
                "candidate_description": "A confirmed description.",
                "review_status": "Complete",
                "discovery_source_link_s": "https://example.org/place",
            },
            {
                "candidate_id": "MC0002",
                "attraction_name": "Duplicate",
                "review_status": "Rejected",
            },
        ])

        result = build_attractions(master, legacy)

        self.assertEqual(len(result), 1)
        attraction = result.iloc[0]
        self.assertEqual(attraction["attraction_id"], "A001")
        self.assertEqual(attraction["attraction_name"], "Confirmed Name")
        self.assertEqual(attraction["min_fee_myr"], 10.0)
        self.assertEqual(attraction["elderly_friendly"], "Yes")
        self.assertEqual(attraction["official_url"], "https://example.org/place")

    def test_new_candidate_uses_unknown_for_unconfirmed_facts(self):
        master = pd.DataFrame([{
            "candidate_id": "MC0431",
            "attraction_name": "New Place",
            "state_territory": "Sabah",
            "city_district": "Rural District",
            "primary_category": "Nature",
            "interests_tags": "forest; walking",
            "setting": "Outdoor",
            "candidate_description": "A confirmed candidate place.",
            "review_status": "Complete",
            "discovery_source_link_s": "https://www.google.com/maps/search/?q=place",
        }])

        result = build_attractions(master, pd.DataFrame())
        attraction = result.iloc[0]

        self.assertEqual(attraction["attraction_id"], "MC0431")
        self.assertEqual(attraction["entrance_fee_status"], "Unknown")
        self.assertEqual(attraction["elderly_friendly"], "Unknown")
        self.assertEqual(attraction["wheelchair_accessible"], "Unknown")
        self.assertEqual(attraction["walking_difficulty"], "Unknown")
        self.assertEqual(attraction["step_free_access"], "Unknown")
        self.assertEqual(attraction["resting_seats_available"], "Unknown")
        self.assertEqual(attraction["accessible_toilet"], "Unknown")
        self.assertEqual(attraction["parking_proximity"], "Unknown")
        self.assertEqual(attraction["shelter_available"], "Unknown")
        self.assertEqual(attraction["elderly_suitability"], "Unknown")
        self.assertIsNone(attraction["official_url"])
        self.assertIn("google.com/maps", attraction["source_url"])

    def test_formal_kuala_lumpur_label_matches_chatbot_state_name(self):
        master = pd.DataFrame([{
            "candidate_id": "MC0400",
            "attraction_name": "City Place",
            "state_territory": "W.P. Kuala Lumpur",
            "city_district": "Kuala Lumpur",
            "primary_category": "Heritage",
            "review_status": "Complete",
        }])

        result = build_attractions(master, pd.DataFrame())

        self.assertEqual(result.iloc[0]["state_territory"], "Kuala Lumpur")


if __name__ == "__main__":
    unittest.main()
