"""Generate src/pvptimer/data/ready.wav: two short rising tones."""
import math
import struct
import wave
from pathlib import Path

RATE = 44100
OUT = Path(__file__).resolve().parents[1] / "src" / "pvptimer" / "data" / "ready.wav"


def tone(freq: float, duration: float, volume: float = 0.5):
    n = int(RATE * duration)
    fade = int(RATE * 0.01)
    for i in range(n):
        envelope = min(1.0, i / fade, (n - i) / fade)
        yield volume * envelope * math.sin(2 * math.pi * freq * i / RATE)


def main() -> None:
    samples = [*tone(880, 0.09), *([0.0] * int(RATE * 0.04)), *tone(1320, 0.12)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
