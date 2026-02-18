import os
import random
import subprocess
from pathlib import Path
from datetime import datetime

from content_factory import make_short, make_long

OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)

MODE = os.getenv("VIDEO_MODE", "short")  # short | long


def run(cmd):
    subprocess.run(cmd, check=True)


# =========================
# 1) VOICE (less robotic)
# =========================
# -> keep SSML SIMPLE for GitHub runners (mstts can break)
# -> use Aria by default (usually more natural than Jenny)
EDGE_VOICE_DEFAULT = os.getenv("EDGE_VOICE", "en-US-AriaNeural")


def ssml(text: str, voice: str) -> str:
    safe = text.replace("&", "and").strip()
    # gentle pauses between lines
    safe = safe.replace("\n", " <break time='280ms'/> ")

    return f"""
<speak>
  <voice name="{voice}">
    <prosody rate="-1%" pitch="+0st">
      {safe}
    </prosody>
  </voice>
</speak>
""".strip()


def make_audio(mp3_path: Path, text: str):
    """
    Deterministic voice selection (daily) + SSML via file (stable on runner).
    IMPORTANT: if edge-tts fails, we FAIL the workflow (no gTTS robot uploads).
    """
    # rotate voice daily (optional) but keep it stable during the day
    voices = ["en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural"]
    day_seed = datetime.utcnow().strftime("%Y-%m-%d")
    rng = random.Random(day_seed)
    voice = os.getenv("EDGE_VOICE") or rng.choice(voices) or EDGE_VOICE_DEFAULT

    ssml_file = OUT_DIR / "voice.ssml"
    ssml_file.write_text(ssml(text, voice), encoding="utf-8")

    # FAIL if edge-tts fails (better than publishing robotic gTTS)
    run([
        "python", "-m", "edge_tts",
        "--voice", voice,
        "--file", str(ssml_file),
        "--write-media", str(mp3_path),
        "--ssml"
    ])
    print(f"✅ Audio via edge-tts (Neural) — {voice}")


def post_process_audio(inp: Path, outp: Path):
    """
    Light cleanup, keep it natural:
    - no echo / no aggressive normalization
    - bump bitrate & sample rate to reduce "cheap TTS" feeling
    """
    run([
        "ffmpeg", "-y",
        "-i", str(inp),
        "-af",
        "highpass=f=70, lowpass=f=12000, "
        "acompressor=threshold=-18dB:ratio=2.6:attack=10:release=120",
        "-ar", "44100",
        "-ac", "2",
        "-b:a", "192k",
        str(outp)
    ])


# =========================
# 2) TEXT files helpers
# =========================
def write_text_file(path: Path, text: str):
    safe = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    path.write_text(safe, encoding="utf-8")


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]).decode().strip()
    return float(out)


def write_srt(srt_path: Path, text: str, total_sec: float):
    """
    Creates readable captions from the script.
    Lines appear sequentially and stay centered near the bottom.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # weight by words so long lines stay longer
    weights = [max(1, len(ln.split())) for ln in lines]
    total_w = sum(weights) if weights else 1

    def ts(t):
        h = int(t // 3600)
        t -= h * 3600
        m = int(t // 60)
        t -= m * 60
        s = int(t)
        ms = int(round((t - s) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    t = 0.0
    with srt_path.open("w", encoding="utf-8") as f:
        for i, (ln, w) in enumerate(zip(lines, weights), start=1):
            dur = max(1.35, total_sec * (w / total_w))  # min display per line
            start = t
            end = min(total_sec, t + dur)
            f.write(f"{i}\n{ts(start)} --> {ts(end)}\n{ln}\n\n")
            t = end


# =========================
# 3) CLEAN FINANCE VISUALS
# =========================
def build_visual_filter(title: str, srt_path: Path):
    """
    Clean finance background (never black) + title for first seconds + captions.
    Avoids fragile crop/rotate/pixel chains that can produce black frames.
    """
    title_file = OUT_DIR / "title.txt"
    write_text_file(title_file, title)

    bg = (
        "geq=r='18+10*(Y/H)+6*sin(T/2)':"
        "g='16+10*(X/W)+6*sin(T/3)':"
        "b='26+12*(Y/H)+6*sin(T/4)',"
        "noise=alls=5:allf=t+u,"
        "eq=contrast=1.08:brightness=-0.02:saturation=1.05,"
        "format=yuv420p"
    )

    # Title (only first ~3.5s)
    title_overlay = (
        "drawbox=x=70:y=150:w=940:h=250:color=black@0.40:t=fill,"
        "drawtext=font=DejaVuSans-Bold:"
        f"textfile={title_file}:reload=0:"
        "fontcolor=white:fontsize=58:"
        "x=(w-text_w)/2:y=210:"
        "enable='lt(t,3.5)'"
    )

    # Captions from SRT (bottom centered)
    subs = (
        f"subtitles={srt_path}:"
        "force_style='FontName=DejaVu Sans,"
        "FontSize=52,"
        "PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H000000&,"
        "BorderStyle=1,Outline=3,Shadow=0,"
        "Alignment=2,MarginV=180'"
    )

    return f"{bg},{title_overlay},{subs}"


def main():
    if MODE == "long":
        title, text, tags = make_long()
    else:
        title, text, tags = make_short()

    raw_mp3 = OUT_DIR / "audio_raw.mp3"
    mp3 = OUT_DIR / "audio.mp3"
    mp4 = OUT_DIR / "video.mp4"
    srt = OUT_DIR / "captions.srt"

    # 1) audio
    make_audio(raw_mp3, text)
    post_process_audio(raw_mp3, mp3)

    # 2) captions timed to audio duration
    audio_sec = ffprobe_duration(mp3)
    write_srt(srt, text, audio_sec)

    # 3) visuals
    vf = build_visual_filter(title, srt)

    # create a canvas long enough; shortest trims to audio
    canvas_dur = int(audio_sec) + 2

    run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"nullsrc=s=1080x1920:d={canvas_dur}",
        "-i", str(mp3),
        "-vf", vf,
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(mp4)
    ])

    Path("meta_title.txt").write_text(title, encoding="utf-8")
    Path("meta_desc.txt").write_text(
        f"Silent Money Blueprint.\n\n{tags}",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
