# Spike results (throwaway)

## Automated checks (2026-10-10, vosk-model-small-en-us-0.15)

- `Model.vosk_model_find_word` exists and works (returns -1 for unknown words). Task 10's `is_known` can rely on it.
- `KaldiRecognizer(model, 16000, grammar_json)` accepts a runtime grammar with the small model.
- Not in vocabulary: `bloodletter`, `judicator`, `galatine`, `clarent`.
  Respell with known words: `blood letter`, `judge`, etc.
- In vocabulary: single letters `e r d f q w`, plus `hell`, `ion`, `blood`, `letter`, `cowl`, `fury`, `clear`, `all`.

## Voice accuracy / latency (user run, 2026-10-10)

- Accuracy: 21/22 = 95% with vosk-model-small-en-us-0.15. The one miss ("blood letter e" heard as
  "blood letter") was the speaker cutting the phrase short, not a recognition error.
- Recognition time: avg 54 ms, max 63 ms (after the audio ends).

Decision: keep the small model (≥ 90%). No change to MODEL_NAME or pvptimer.spec.
