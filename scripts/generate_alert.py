"""Gera o alerta sonoro exclusivo do Pomodoro (WAV local).

O som tem duas chamadas curtas e intencionais: uma para avisar que o tempo
acabou e outra para lembrar a pessoa de voltar ao app.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "audio" / "pomodoro-alert.wav"
SAMPLE_RATE = 44100
DURATION = 5.2
PEAK = 0.82

# Duas frases musicais curtas, com timbre de sino suave e um toque de madeira.
NOTES = (
    (523.25, 0.00, 0.34, 0.65),   # C5
    (659.25, 0.15, 0.30, 0.60),   # E5
    (783.99, 0.30, 0.28, 0.60),   # G5
    (1046.50, 0.58, 0.34, 1.10),  # C6
    (1046.50, 2.00, 0.28, 0.55),  # C6
    (783.99, 2.15, 0.30, 0.55),   # G5
    (659.25, 2.30, 0.32, 0.60),   # E5
    (523.25, 2.48, 0.34, 0.70),   # C5
    (1046.50, 2.72, 0.38, 1.25),  # C6
)
THUMPS = ((130.81, 0.00, 0.16, 0.20), (130.81, 2.00, 0.14, 0.20))
SHIMMERS = ((2093.00, 0.58, 0.045, 0.9), (2093.00, 2.72, 0.05, 0.9))


def _envelope(t: float, start: float, amplitude: float, decay: float) -> float:
    local = t - start
    if local < 0:
        return 0.0
    attack = min(1.0, local / 0.012)
    return amplitude * attack * math.exp(-local / decay)


def main() -> None:
    frames = bytearray()
    total = int(SAMPLE_RATE * DURATION)
    for index in range(total):
        t = index / SAMPLE_RATE
        sample = 0.0
        for frequency, start, amplitude, decay in NOTES:
            env = _envelope(t, start, amplitude, decay)
            if env <= 0:
                continue
            sample += env * (
                math.sin(2 * math.pi * frequency * t)
                + 0.22 * math.sin(2 * math.pi * frequency * 2 * t)
                + 0.08 * math.sin(2 * math.pi * frequency * 3 * t)
            )
        for frequency, start, amplitude, decay in THUMPS:
            env = _envelope(t, start, amplitude, decay)
            if env > 0:
                sample += env * math.sin(2 * math.pi * frequency * t)
        for frequency, start, amplitude, decay in SHIMMERS:
            env = _envelope(t, start, amplitude, decay)
            if env > 0:
                sample += env * math.sin(2 * math.pi * frequency * t)
        sample = max(-1.0, min(1.0, sample * PEAK))
        frames.extend(struct.pack("<h", int(sample * 32767)))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(frames)
    print(f"gerado {OUT} ({len(frames) / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
