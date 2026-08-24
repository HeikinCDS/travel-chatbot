import importlib.util
import unittest

from nlp.intent_classifier import IntentClassifier


@unittest.skipUnless(
    importlib.util.find_spec("spacy"),
    "spaCy is not installed in this verification runtime",
)
class IntentClassifierRuntimeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.classifier = IntentClassifier()

    def test_model_produces_label_confidence_and_scores(self):
        prediction = self.classifier.predict(
            "Recommend a nature attraction in Johor"
        )
        self.assertIn(prediction.label, prediction.scores)
        self.assertGreaterEqual(prediction.confidence, 0.0)
        self.assertLessEqual(prediction.confidence, 1.0)
        self.assertEqual(len(prediction.scores), 9)
        self.assertIn("out_of_scope", prediction.scores)

    def test_empty_message_is_rejected(self):
        with self.assertRaises(ValueError):
            self.classifier.predict("   ")

    def test_jomvoyage_usage_question_is_classified_as_help(self):
        prediction = self.classifier.predict(
            "How can I use Maya to plan a trip?"
        )
        self.assertEqual(prediction.label, "help")

    def test_non_travel_question_is_classified_as_out_of_scope(self):
        prediction = self.classifier.predict(
            "How do I repair my laptop?"
        )
        self.assertEqual(prediction.label, "out_of_scope")

    def test_request_for_more_matching_places_is_an_alternative(self):
        prediction = self.classifier.predict(
            "Could you show more places that match these preferences?"
        )
        self.assertEqual(prediction.label, "request_alternative")

    def test_help_word_does_not_make_a_technology_question_help(self):
        prediction = self.classifier.predict(
            "Can you help me choose a graphics card?"
        )
        self.assertEqual(prediction.label, "out_of_scope")


if __name__ == "__main__":
    unittest.main()
