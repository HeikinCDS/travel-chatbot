import unittest

import pandas as pd

from scripts.import_attractions import (
    ACCESSIBILITY_EXCEL_PATH,
    MASTER_EXCEL_PATH,
    _structured_accessibility,
    build_attraction_image_catalogue,
    build_attractions,
    load_image_library,
    load_master_candidates,
    load_verified_accessibility,
)


class ImportAttractionsTests(unittest.TestCase):
    def test_current_workbooks_supply_images_for_hundreds_of_attractions(self):
        master = load_master_candidates()
        libraries = [
            load_image_library(MASTER_EXCEL_PATH),
            load_image_library(ACCESSIBILITY_EXCEL_PATH),
        ]

        catalogue = build_attraction_image_catalogue(master, libraries)

        self.assertGreaterEqual(len(catalogue), 388)
        self.assertTrue(all(
            item["image_url"].startswith("https://")
            for item in catalogue.values()
        ))
        self.assertTrue(all(
            "thumb.wikimedia.org" not in item["image_url"]
            for item in catalogue.values()
        ))

    def test_local_curated_image_is_preferred_over_workbook_candidate(self):
        master = pd.DataFrame([{
            "candidate_id": "MC0001",
            "existing_record_id": "A001",
            "review_status": "Complete",
        }])
        library = pd.DataFrame([{
            "candidate_id": "MC0001",
            "image_number": 1,
            "display_url": "https://example.org/remote.jpg",
            "commons_file_page": "https://commons.wikimedia.org/wiki/File:Remote.jpg",
            "creator": "Example creator",
            "license": "CC BY 4.0",
        }])
        local = {
            "A001": {
                "image_url": "/static/images/attractions/A001.jpg",
                "image_attribution": "Local curator",
            }
        }

        catalogue = build_attraction_image_catalogue(master, [library], local)

        self.assertEqual(
            catalogue["A001"]["image_url"],
            "/static/images/attractions/A001.jpg",
        )

    def test_reviewed_accessibility_workbook_contains_57_unique_records(self):
        accessibility = load_verified_accessibility()

        self.assertEqual(len(accessibility), 57)
        self.assertEqual(accessibility["spot_id"].nunique(), 57)
        self.assertEqual(
            set(accessibility["recommendation_status"].str.casefold()),
            {
                "documented support - conditional",
                "reported support - confirm",
            },
        )

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
                "canonical_id": "MC0001",
                "record_relationship": "Related site or component",
                "related_site_id": "MC0099",
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
        self.assertEqual(attraction["canonical_id"], "MC0001")
        self.assertEqual(
            attraction["record_relationship"],
            "Related site or component",
        )
        self.assertEqual(attraction["related_site_id"], "MC0099")

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

    def test_explicit_elderly_screening_retains_status_for_runtime_filtering(self):
        master = pd.DataFrame([
            {
                "candidate_id": "MC0500",
                "attraction_name": "Accessible Place",
                "state_territory": "Perak",
                "primary_category": "Park",
                "review_status": "Complete",
                "elderly_recommendation_eligibility": "Eligible",
                "accessibility_evidence_source": "https://example.org/access",
                "accessibility_screening_notes": "A step-free route is recorded.",
                "accessibility_screening_date": "2026-08-16",
            },
            {
                "candidate_id": "MC0501",
                "attraction_name": "Unscreened Place",
                "state_territory": "Perak",
                "primary_category": "Nature",
                "review_status": "Complete",
                "elderly_recommendation_eligibility": "Excluded",
                "accessibility_screening_notes": "No documented feature recorded.",
            },
        ])

        result = build_attractions(master, pd.DataFrame())

        self.assertEqual(result["attraction_id"].tolist(), ["MC0500", "MC0501"])
        attraction = result.iloc[0]
        self.assertEqual(
            attraction["elderly_recommendation_eligibility"],
            "Eligible",
        )
        self.assertEqual(
            attraction["accessibility_evidence_source"],
            "https://example.org/access",
        )
        self.assertEqual(attraction["accessibility_screening_date"], "2026-08-16")
        self.assertEqual(
            result.iloc[1]["elderly_recommendation_eligibility"],
            "Excluded",
        )

    def test_accessibility_overlay_marks_only_matching_records_eligible(self):
        master = pd.DataFrame([
            {
                "candidate_id": "MC0100",
                "attraction_name": "Verified Place",
                "state_territory": "Penang",
                "primary_category": "Park",
                "review_status": "Complete",
            },
            {
                "candidate_id": "MC0101",
                "attraction_name": "General Place",
                "state_territory": "Penang",
                "primary_category": "Park",
                "review_status": "Complete",
            },
        ])
        accessibility = pd.DataFrame([{
            "spot_id": "MC0100",
            "attraction_name": "Verified Place",
            "evidence_tier": "Verified",
            "elderly_suitability": "Suitable with assistance",
            "documented_likely_accessibility_features": (
                "Step-free access (partial); Resting seats; "
                "Accessible toilet; Accessible parking"
            ),
            "elderly_accessibility_notes": (
                "The main visitor area has a lower-barrier route."
            ),
            "why_it_qualifies": "A documented visitor route is available.",
            "evidence_source_s": "https://example.org/accessibility",
            "more_info_link_s": "https://example.org/place",
            "recommendation_status": "Documented support - conditional",
        }])

        result = build_attractions(master, pd.DataFrame(), accessibility)
        verified = result[result["attraction_id"] == "MC0100"].iloc[0]
        general = result[result["attraction_id"] == "MC0101"].iloc[0]

        self.assertEqual(
            verified["elderly_recommendation_eligibility"],
            "Eligible",
        )
        self.assertEqual(verified["elderly_friendly"], "Partial")
        self.assertEqual(verified["step_free_access"], "Partial")
        self.assertEqual(verified["resting_seats_available"], "Yes")
        self.assertEqual(verified["accessible_toilet"], "Yes")
        self.assertEqual(verified["parking_proximity"], "Near")
        self.assertEqual(
            verified["accessibility_evidence_source"],
            "https://example.org/accessibility",
        )
        self.assertEqual(
            verified["documented_accessibility_features"],
            "Step-free access (partial); Resting seats; Accessible toilet; "
            "Accessible parking",
        )
        self.assertEqual(
            general["elderly_recommendation_eligibility"],
            "General only",
        )

    def test_structured_accessibility_keeps_unknown_features_conservative(self):
        values = _structured_accessibility(
            "Rest huts; Step-free/wheelchair access not documented",
            "Suitable with assistance",
        )

        self.assertEqual(values["elderly_friendly"], "Partial")
        self.assertEqual(values["wheelchair_accessible"], "Unknown")
        self.assertEqual(values["step_free_access"], "Unknown")
        self.assertEqual(values["shelter_available"], "Yes")

    def test_structured_accessibility_recognises_step_free_boardwalk(self):
        values = _structured_accessibility(
            "Wheelchair-accessible boardwalk; step-free flat wooden walkway",
            "Suitable",
        )

        self.assertEqual(values["elderly_friendly"], "Yes")
        self.assertEqual(values["wheelchair_accessible"], "Yes")
        self.assertEqual(values["step_free_access"], "Yes")

    def test_conditional_suitability_is_available_with_assistance(self):
        values = _structured_accessibility(
            "Mangrove boardwalk; parking; visitor facilities",
            "Conditional on mobility and route",
        )

        self.assertEqual(values["elderly_friendly"], "Partial")
        self.assertEqual(
            values["elderly_suitability"],
            "Suitable with assistance",
        )


if __name__ == "__main__":
    unittest.main()
