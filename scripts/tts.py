"""Narração com edge-tts (voz neural) + tempo exato de cada palavra.

Sem fallback robótico: se o edge-tts falhar, o run falha e nada é publicado.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple, Union

import edge_tts

VOICES = [v.strip() for v in os.getenv(
    "EDGE_VOICES", "en-US-AndrewMultilingualNeural,en-US-BrianMultilingualNeural,en-US-GuyNeural"
).split(",") if v.strip()]
RATE = os.getenv("EDGE_RATE", "+8%")
TICKS = 10_000_000  # o edge-tts mede o tempo em unidades de 100 ns

Word = Dict[str, Union[float, str]]


async def _synthesize(text: str, voice: str, mp3_path: Path) -> List[Word]:
    communicate = edge_tts.Communicate(text, voice, rate=RATE, boundary="WordBoundary")
    words: List[Word] = []
    with mp3_path.open("wb") as fh:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS
                words.append({
                    "text": str(chunk["text"]),
                    "start": start,
                    "end": start + chunk["duration"] / TICKS,
                })
    return words


def synthesize(text: str, mp3_path: Path) -> Tuple[List[Word], str]:
    last_error: Exception | None = None
    for voice in VOICES:
        for attempt in range(1, 4):
            try:
                words = asyncio.run(_synthesize(text, voice, mp3_path))
                if mp3_path.stat().st_size < 4096 or len(words) < 10:
                    raise RuntimeError("edge-tts devolveu áudio ou tempos incompletos")
                print(f"Voz: {voice} ({len(words)} palavras com tempo, tentativa {attempt})")
                return words, voice
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                print(f"edge-tts falhou ({voice}, tentativa {attempt}): {exc}")
                time.sleep(3 * attempt)
    raise RuntimeError(f"Narração falhou em todas as vozes: {last_error}")
