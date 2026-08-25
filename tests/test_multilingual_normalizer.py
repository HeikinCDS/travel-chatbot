import unittest

from nlp.entity_extractor import extract_preferences
from nlp.multilingual_normalizer import normalize_user_input


class MultilingualNormalizerTests(unittest.TestCase):
    def test_english_input_is_unchanged(self):
        text = "Recommend a nature place in Johor"
        self.assertEqual(normalize_user_input(text, "en"), text)

    def test_malay_recommendation_extracts_travel_preferences(self):
        normalized = normalize_user_input(
            "Cadangkan tempat alam semula jadi mesra warga emas di Pulau Pinang",
            "ms",
        )
        preferences = extract_preferences(normalized)
        self.assertEqual(preferences.state, "Penang")
        self.assertEqual(preferences.interests, ("nature",))
        self.assertTrue(preferences.elderly_friendly)

    def test_malay_accessibility_needs_are_normalized(self):
        normalized = normalize_user_input(
            "Saya mahu tempat dengan berjalan kaki minimum, tempat duduk berdekatan dan tandas OKU di Johor",
            "ms",
        )
        preferences = extract_preferences(normalized)
        self.assertEqual(preferences.state, "Johor")
        self.assertEqual(
            preferences.accessibility_needs,
            ("low_walking", "seating", "accessible_toilet"),
        )

    def test_malay_show_more_command_is_normalized(self):
        self.assertEqual(
            normalize_user_input("Tunjukkan lebih banyak pilihan", "ms"),
            "show me more options",
        )

    def test_chinese_recommendation_extracts_travel_preferences(self):
        normalized = normalize_user_input("推荐槟城适合长者的自然景点", "zh")
        preferences = extract_preferences(normalized)
        self.assertEqual(preferences.state, "Penang")
        self.assertEqual(preferences.interests, ("nature",))
        self.assertTrue(preferences.elderly_friendly)

    def test_chinese_states_are_supported(self):
        cases = {
            "推荐柔佛的景点": "Johor",
            "推荐沙巴的景点": "Sabah",
            "推荐砂拉越的景点": "Sarawak",
            "推荐吉隆坡的景点": "Kuala Lumpur",
            "推荐森美兰的景点": "Negeri Sembilan",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                preferences = extract_preferences(normalize_user_input(text, "zh"))
                self.assertEqual(preferences.state, expected)

    def test_chinese_accessibility_needs_are_normalized(self):
        normalized = normalize_user_input(
            "推荐柔佛少走路有休息座椅和无障碍厕所的景点",
            "zh",
        )
        preferences = extract_preferences(normalized)
        self.assertEqual(preferences.state, "Johor")
        self.assertEqual(
            preferences.accessibility_needs,
            ("low_walking", "seating", "accessible_toilet"),
        )

    def test_chinese_show_more_command_is_normalized(self):
        self.assertEqual(
            normalize_user_input("显示更多选择", "zh"),
            "show me more options",
        )

    def test_unknown_words_are_preserved(self):
        self.assertIn(
            "Penang Hill",
            normalize_user_input("介绍一下 Penang Hill", "zh"),
        )

    def test_unsupported_language_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_user_input("Bonjour", "fr")


if __name__ == "__main__":
    unittest.main()
