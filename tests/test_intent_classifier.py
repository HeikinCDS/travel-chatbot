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


if __name__ == "__main__":
    unittest.main()
