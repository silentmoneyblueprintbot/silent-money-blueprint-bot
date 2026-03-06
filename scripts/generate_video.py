from __future__ import annotations

import os
import random
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import requests

from content_factory import make_long, make_short
from validation import validate_artifacts

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()

OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)

MODE = os.getenv("VIDEO_MODE", "short")  # short | long

EDGE_VOICE_DEFAULT = os.getenv("EDGE_VOICE", "en-US-AriaNeural")
EDGE_RATE = os.getenv("EDGE_RATE", "+4%")
EDGE_VOLUME = os.getenv("EDGE_VOLUME", "+0%")

PIPER_BIN = Path("piper/piper/piper")
PIPER_VOICE = Path("voices/en_US-lessac-medium.onnx")


def run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def resolve_piper_bin() -> Path:
    if PIPER_BIN.exists():
        return PIPER_BIN
    for candidate in Path("piper").rglob("piper"):
        if candidate.is_file():
            return candidate
    return PIPER_BIN


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def write_text_file(path: Path, text: str) -> None:
    safe = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    path.write_text(safe, encoding="utf-8")


def normalize_text(text: str) -> str:
    replacements = {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2014": "-",
        "\u2013": "-",
        "â€™": "'",
        "â€œ": '"',
        "â€\x9d": '"',
        "â€“": "-",
        "â€”": "-",
    }
    normalized = text
    for bad, good in replacements.items():
        normalized = normalized.replace(bad, good)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def script_to_tts_text(script: str) -> str:
    lines = [ln.strip() for ln in script.splitlines() if ln.strip() and ln.strip() != "---"]
    spoken: List[str] = []
    for line in lines:
        clean = re.sub(r"^Topic:\s*", "", line, flags=re.IGNORECASE)
        clean = re.sub(r"^Lesson\s+\d+\s*$", "", clean, flags=re.IGNORECASE)
        clean = clean.strip()
        if not clean:
            continue

        if clean.endswith(":"):
            clean = clean[:-1] + "."
        if not re.search(r"[.!?]$", clean):
            clean += "."

        spoken.append(clean)

    text = "\n".join(spoken)
    text = re.sub(r"\n{2,}", "\n", text)
    return normalize_text(text)


def make_audio_edge(mp3_path: Path, text: str) -> str:
    voices = ["en-US-AriaNeural", "en-US-JennyNeural", "en-US-GuyNeural"]
    day_seed = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(day_seed)
    voice = os.getenv("EDGE_VOICE") or rng.choice(voices) or EDGE_VOICE_DEFAULT

    run(
        [
            "python",
            "-m",
            "edge_tts",
            "--voice",
            voice,
            "--rate",
            EDGE_RATE,
            "--volume",
            EDGE_VOLUME,
            "--text",
            text,
            "--write-media",
            str(mp3_path),
        ]
    )
    print(f"Audio via edge-tts ({voice}, rate={EDGE_RATE}, volume={EDGE_VOLUME})")
    return voice


def make_audio_piper(wav_path: Path, text: str) -> None:
    piper_bin = resolve_piper_bin()
    if not piper_bin.exists():
        raise FileNotFoundError(f"Piper binary not found at {piper_bin}")
    if not PIPER_VOICE.exists():
        raise FileNotFoundError(f"Piper voice not found at {PIPER_VOICE}")

    cmd = [str(piper_bin), "--model", str(PIPER_VOICE), "--output_file", str(wav_path)]
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _, err = process.communicate(text)
    if process.returncode != 0:
        raise RuntimeError(f"Piper failed: {err}")
    print("Audio via Piper fallback")


def make_audio(raw_path: Path, text: str) -> str:
    try:
        make_audio_edge(raw_path, text)
        return "edge"
    except Exception as exc:
        print(f"edge-tts failed, using Piper fallback: {exc}")

    wav = OUT_DIR / "audio_raw.wav"
    make_audio_piper(wav, text)
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(wav),
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            str(raw_path),
        ]
    )
    return "piper"


def post_process_audio(inp: Path, outp: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(inp),
            "-af",
            "highpass=f=65,lowpass=f=12500,"
            "acompressor=threshold=-20dB:ratio=2.2:attack=8:release=140,"
            "alimiter=limit=0.92",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            str(outp),
        ]
    )


def split_caption_lines(text: str, max_words: int = 9) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    lines: List[str] = []

    for sentence in sentences:
        words = sentence.strip().split()
        if not words:
            continue
        while words:
            chunk = words[:max_words]
            words = words[max_words:]
            lines.append(" ".join(chunk).strip())

    return lines


def write_srt(srt_path: Path, spoken_text: str, total_sec: float) -> None:
    lines = split_caption_lines(spoken_text)
    weights = [max(1, len(ln.split())) for ln in lines]
    total_weight = sum(weights) or 1

    def ts(seconds: float) -> str:
        h = int(seconds // 3600)
        seconds -= h * 3600
        m = int(seconds // 60)
        seconds -= m * 60
        s = int(seconds)
        ms = int(round((seconds - s) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    cursor = 0.0
    with srt_path.open("w", encoding="utf-8") as file:
        for idx, (line, weight) in enumerate(zip(lines, weights), start=1):
            duration = max(1.1, total_sec * (weight / total_weight))
            start = cursor
            end = min(total_sec, cursor + duration)
            file.write(f"{idx}\n{ts(start)} --> {ts(end)}\n{line}\n\n")
            cursor = end


def keywords_from_text(title: str, script: str) -> List[str]:
    source = f"{title} {script}".lower()
    choices = [
        "stock market chart",
        "financial planning",
        "city business",
        "calculator desk",
        "person budgeting",
        "money saving",
        "investing concept",
        "office laptop finance",
    ]
    selected = [item for item in choices if any(token in source for token in item.split()[:2])]
    if not selected:
        selected = ["financial planning", "money saving", "city business"]
    return selected


def download_pexels_video(query: str, output_path: Path) -> Optional[Path]:
    if not PEXELS_API_KEY:
        return None

    try:
        response = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={
                "query": query,
                "orientation": "portrait",
                "size": "large",
                "per_page": 20,
            },
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        print(f"Pexels search failed for '{query}': {exc}")
        return None

    videos = data.get("videos", [])
    if not videos:
        return None

    best_url = None
    best_score = -1

    for video in videos:
        duration = int(video.get("duration", 0))
        if duration < 5:
            continue

        for file_entry in video.get("video_files", []):
            link = file_entry.get("link")
            width = int(file_entry.get("width") or 0)
            height = int(file_entry.get("height") or 0)
            file_type = file_entry.get("file_type", "")
            if not link or file_type != "video/mp4":
                continue
            score = width * height
            if height > width:
                score += 500000
            if score > best_score:
                best_score = score
                best_url = link

    if not best_url:
        return None

    try:
        with requests.get(best_url, stream=True, timeout=60) as download:
            download.raise_for_status()
            with output_path.open("wb") as file:
                for chunk in download.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        file.write(chunk)
        return output_path
    except Exception as exc:
        print(f"Failed downloading Pexels video: {exc}")
        return None


def build_visual_filter(title: str, srt_path: Path, use_background_video: bool) -> str:
    title_file = OUT_DIR / "title.txt"
    write_text_file(title_file, normalize_text(title))

    base_filters: List[str] = []
    if use_background_video:
        base_filters.append("scale=1080:1920:force_original_aspect_ratio=increase")
        base_filters.append("crop=1080:1920")
        base_filters.append("eq=contrast=1.07:brightness=0.02:saturation=1.12")
    else:
        base_filters.append(
            "geq=r='55+35*(Y/H)+10*sin(T*0.8)':"
            "g='80+30*(X/W)+12*sin(T*0.7)':"
            "b='125+20*(Y/H)+10*sin(T*0.5)'"
        )
        base_filters.append("noise=alls=10:allf=t+u")
        base_filters.append("eq=contrast=1.04:brightness=0.03:saturation=1.10")

    overlays = [
        "drawbox=x=60:y=130:w=960:h=230:color=black@0.35:t=fill",
        "drawtext=font=DejaVuSans-Bold:"
        f"textfile={title_file.as_posix()}:reload=0:"
        "fontcolor=white:fontsize=56:"
        "x=(w-text_w)/2:y=185:enable='lt(t,3.8)'",
        "drawbox=x=0:y=h-350:w=w:h=350:color=black@0.22:t=fill",
        f"subtitles='{srt_path.as_posix()}':"
        "force_style='FontName=DejaVu Sans,FontSize=50,PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H000000&,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV=170'",
        "format=yuv420p",
    ]

    return ",".join(base_filters + overlays)


def render_video(mp3: Path, mp4: Path, vf: str, canvas_dur: float, background_video: Optional[Path]) -> None:
    if background_video and background_video.exists():
        run(
            [
                "ffmpeg",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(background_video),
                "-i",
                str(mp3),
                "-t",
                f"{canvas_dur:.2f}",
                "-vf",
                vf,
                "-r",
                "30",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(mp4),
            ]
        )
        return

    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"nullsrc=s=1080x1920:d={canvas_dur:.2f}",
            "-i",
            str(mp3),
            "-vf",
            vf,
            "-r",
            "30",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(mp4),
        ]
    )


def main() -> None:
    if MODE == "long":
        title, script, tags = make_long()
    else:
        title, script, tags = make_short()

    script = normalize_text(script)
    title = normalize_text(title)
    spoken_text = script_to_tts_text(script)

    raw_mp3 = OUT_DIR / "audio_raw.mp3"
    mp3 = OUT_DIR / "audio.mp3"
    mp4 = OUT_DIR / "video.mp4"
    srt = OUT_DIR / "captions.srt"
    bg_video = OUT_DIR / "background.mp4"

    write_text_file(OUT_DIR / "script.txt", script)
    write_text_file(OUT_DIR / "spoken_script.txt", spoken_text)

    tts_engine = make_audio(raw_mp3, spoken_text)
    print(f"TTS engine: {tts_engine}")

    post_process_audio(raw_mp3, mp3)
    audio_sec = ffprobe_duration(mp3)
    if audio_sec <= 0:
        raise RuntimeError("Generated audio has invalid duration")

    write_srt(srt, spoken_text, audio_sec)

    picked_bg = None
    for keyword in keywords_from_text(title, script):
        candidate = download_pexels_video(keyword, bg_video)
        if candidate:
            picked_bg = candidate
            print(f"Using Pexels background for query: {keyword}")
            break

    vf = build_visual_filter(title, srt, use_background_video=bool(picked_bg))
    canvas_dur = audio_sec + 0.8
    render_video(mp3, mp4, vf, canvas_dur, picked_bg)

    Path("meta_title.txt").write_text(title, encoding="utf-8")
    Path("meta_desc.txt").write_text(
        f"Silent Money Blueprint.\n\n{tags}",
        encoding="utf-8",
    )

    report = validate_artifacts(strict=True)
    print("Validation ok:", report["metrics"])


if __name__ == "__main__":
    main()
