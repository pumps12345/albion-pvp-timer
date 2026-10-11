# Spike results (throwaway)

## Automated checks (2026-10-10, vosk-model-small-en-us-0.15)

- `Model.vosk_model_find_word` exists and works (returns -1 for unknown words). Task 10's `is_known` can rely on it.
- `KaldiRecognizer(model, 16000, grammar_json)` accepts a runtime grammar with the small model.
- Not in vocabulary: `bloodletter`, `judicator`, `galatine`, `clarent`.
  Respell with known words: `blood letter`, `judge`, etc.
- In vocabulary: single letters `e r d f q w`, plus `hell`, `ion`, `blood`, `letter`, `cowl`, `fury`, `clear`, `all`.

## Voice accuracy / latency

PENDING: the user runs
`.venv/Scripts/python spike/spike_recognize.py models/vosk-model-small-en-us-0.15 spike/phrases.txt`
and pastes the output here. Decision rule: ≥ 90% → keep the small model; otherwise try
`vosk-model-en-us-0.22-lgraph`.
