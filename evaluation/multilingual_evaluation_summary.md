# Multilingual Input Evaluation

## Evaluation design

JomVoyage was evaluated using a fixed holdout of 54 messages that are not present in the spaCy intent-classifier training dataset. The holdout contains 27 Bahasa Melayu and 27 Simplified Chinese messages. Each language contains three examples for all nine supported intents. Twelve cases additionally test extraction of state, interest, budget and elderly-accessibility preferences.

The evaluated pipeline is the same hybrid path used by the application: deterministic offline language normalization, production rule-based intent routing and the deployed spaCy classifier. No paid translation API or online language model is used.

## Results

| Measurement | Result |
|---|---:|
| Overall routed-intent accuracy | 100.00% |
| Overall macro F1 | 100.00% |
| Bahasa Melayu routed-intent accuracy | 100.00% |
| Simplified Chinese routed-intent accuracy | 100.00% |
| Entity-field accuracy | 100.00% (22/22) |
| Fully correct entity cases | 12/12 |
| Exact overlap with intent training examples | 0 |

## Interpretation and limitations

These results demonstrate reliable handling of the controlled vocabulary and phrase patterns currently supported by the prototype. They do not prove unrestricted fluency in Malay or Chinese. Real users may use dialects, spelling variations, mixed languages or phrases outside the current normalization vocabulary. The holdout should therefore be expanded using messages collected from elderly-user usability testing. Attraction names and stored descriptions may also remain in English even when the interface language changes.

## Reproduction

Run `python scripts/evaluate_multilingual_input.py` from the project root. Complete per-message predictions are saved in `evaluation/multilingual_evaluation_results.json`.
