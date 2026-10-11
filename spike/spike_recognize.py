"""THROWAWAY spike: how well does Vosk + a grammar recognize Albion callouts on this mic?

Run:  .venv/Scripts/python spike/spike_recognize.py models/vosk-model-small-en-us-0.15 spike/phrases.txt
For each prompt: press Enter, then say the phrase. Recording lasts 2.5 s.
"""
import json
import sys
import time

import sounddevice as sd
import vosk

RATE = 16000
RECORD_S = 2.5
ROUNDS = 2


def recognize(rec: vosk.KaldiRecognizer, audio: bytes) -> str:
    parts = []
    if rec.AcceptWaveform(audio):
        parts.append(json.loads(rec.Result())["text"])
    parts.append(json.loads(rec.FinalResult())["text"])
    rec.Reset()
    return " ".join(p for p in parts if p).strip()


def main(model_path: str, phrases_path: str) -> None:
    vosk.SetLogLevel(-1)
    model = vosk.Model(model_path)
    print("Model.vosk_model_find_word available:", hasattr(model, "vosk_model_find_word"))
    with open(phrases_path, encoding="utf-8") as f:
        phrases = [line.strip().lower() for line in f if line.strip() and not line.startswith("#")]
    words = sorted({w for p in phrases for w in p.split()})
    unknown = [w for w in words if model.vosk_model_find_word(w) == -1]
    print("words NOT in vocabulary:", unknown or "none")
    usable = [p for p in phrases if not set(p.split()) & set(unknown)]
    print(f"{len(usable)}/{len(phrases)} phrases usable in the grammar\n")
    rec = vosk.KaldiRecognizer(model, RATE, json.dumps(usable + ["[unk]"]))

    results = []
    for round_no in range(1, ROUNDS + 1):
        for phrase in usable:
            input(f'[{round_no}/{ROUNDS}] Press Enter, then say: "{phrase}"')
            with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16") as stream:
                data, _ = stream.read(int(RECORD_S * RATE))
            t0 = time.perf_counter()
            heard = recognize(rec, bytes(data))
            ms = (time.perf_counter() - t0) * 1000
            ok = heard == phrase
            results.append((phrase, heard, ok, ms))
            print(f'   heard "{heard}"  {"OK" if ok else "MISS"}  ({ms:.0f} ms)')

    hits = sum(r[2] for r in results)
    print(f"\naccuracy: {hits}/{len(results)} = {hits / len(results):.0%}")
    print(f"recognition time: avg {sum(r[3] for r in results) / len(results):.0f} ms, "
          f"max {max(r[3] for r in results):.0f} ms")
    for phrase, heard, ok, _ in results:
        if not ok:
            print(f'   MISS "{phrase}" -> "{heard}"')


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
