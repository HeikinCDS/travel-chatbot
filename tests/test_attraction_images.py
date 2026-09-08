import unittest

from chatbot.attraction_images import get_attraction_image


class AttractionImageCatalogueTests(unittest.TestCase):
    def test_curated_image_includes_display_and_credit_fields(self):
        image = get_attraction_image("A082")

        self.assertEqual(
            image["image_url"],
            "/static/images/attractions/A082.jpg",
        )
        self.assertTrue(image["image_page_url"].startswith("https://"))
        self.assertTrue(image["image_attribution"])
        self.assertTrue(image["image_license"])

    def test_unknown_attraction_has_no_image(self):
        self.assertEqual(get_attraction_image("not-in-catalogue"), {})

    def test_updated_workbook_image_is_available_to_recommendation_cards(self):
        image = get_attraction_image("A001")

        self.assertTrue(image["image_url"].startswith("https://upload.wikimedia.org/"))
        self.assertTrue(image["image_page_url"].startswith("https://commons.wikimedia.org/"))
        self.assertTrue(image["image_attribution"])
        self.assertTrue(image["image_license"])


if __name__ == "__main__":
    unittest.main()
