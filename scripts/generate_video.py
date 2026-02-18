import os
import random
import subprocess
from pathlib import Path
from datetime import datetime

from content_factory import make_short, make_long

OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)

MODE = os.getenv("VIDEO_MODE", "short")  # short | long

# Edge TTS (online) — may 403 on GitHub Actions
EDGE_VOICE_DEFAULT = os.getenv("EDGE_VOICE", "en-US-AriaNeural")

# Piper (offline) paths (as installed by workflow)
PIPER_BIN = Path("piper/piper")  # from ./piper_linux_x86_64.tar.gz
PIPER_VOICE = Path("voices/en_US-lessac-medium.onnx")

def run(cmd):
    subprocess.run(cmd, check=True)

def run_capture(cmd) -> str:
    return subprocess.check_output(cmd).decode("utf-8", errors="ignore")

def make_audio_edge(mp3_path: Path, text: str):
    voices = ["en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural"]
    day_seed = datetime.utcnow().strftime("%Y-%m-%d")
    rng = random.Random(day_seed)
    voice = os.getenv("EDGE_VOICE") or rng.choice(voices) or EDGE_VOICE_DEFAULT

    clean = text.replace("&", "and").strip()

    run([
        "python", "-m", "edge_tts",
        "--voice", voice,
        "--text", clean,
        "--write-media", str(mp3_path),
    ])
    print(f"✅ Audio via edge-tts (Neural) — {voice}")

def make_audio_piper(wav_path: Path, text: str):
    """
    Offline TTS using Piper -> outputs WAV.
    """
    if not PIPER_BIN.exists():
        raise FileNotFoundError(f"Piper binary not found at {PIPER_BIN}")
    if not PIPER_VOICE.exists():
        raise FileNotFoundError(f"Piper voice not found at {PIPER_VOICE}")

    clean = text.replace("&", "and").strip()

    # Piper reads from stdin and writes WAV to file
    cmd = [str(PIPER_BIN), "--model", str(PIPER_VOICE), "--output_file", str(wav_path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate(clean)
    if p.returncode != 0:
        raise RuntimeError(f"Piper failed: {err}")
    print("✅ Audio via Piper (offline)")

def make_audio(raw_path: Path, text: str):
    """
    Try edge-tts first; if it fails (403 etc.), fallback to Piper.
    raw_path extension decides output type:
      - if raw_path ends with .mp3 -> edge-tts writes mp3
      - piper writes wav (we'll convert)
    """
    # try edge-tts
    try:
        make_audio_edge(raw_path, text)
        return "edge"
    except Exception as e:
        print("⚠️ edge-tts falhou (normal em GitHub Actions):", e)

    # fallback to piper (wav), then convert to mp3
    wav = OUT_DIR / "audio_raw.wav"
    make_audio_piper(wav, text)

    run([
        "ffmpeg", "-y",
        "-i", str(wav),
        "-ar", "44100",
        "-ac", "2",
        "-b:a", "192k",
        str(raw_path)
    ])
    return "piper"

def post_process_audio(inp: Path, outp: Path):
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
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    weights = [max(1, len(ln.split())) for ln in lines]
    total_w = sum(weights) if weights else 1

    def ts(t):
        h = int(t // 3600); t -= h * 3600
        m = int(t // 60); t -= m * 60
        s = int(t); ms = int(round((t - s) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    t = 0.0
    with srt_path.open("w", encoding="utf-8") as f:
        for i, (ln, w) in enumerate(zip(lines, weights), start=1):
            dur = max(1.35, total_sec * (w / total_w))
            start = t
            end = min(total_sec, t + dur)
            f.write(f"{i}\n{ts(start)} --> {ts(end)}\n{ln}\n\n")
            t = end

def build_visual_filter(title: str, srt_path: Path):
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

    title_overlay = (
        "drawbox=x=70:y=150:w=940:h=250:color=black@0.40:t=fill,"
        "drawtext=font=DejaVuSans-Bold:"
        f"textfile={title_file}:reload=0:"
        "fontcolor=white:fontsize=58:"
        "x=(w-text_w)/2:y=210:"
        "enable='lt(t,3.5)'"
    )

    subs = (
        f"subtitles='{srt_path.as_posix()}':"
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

    engine = make_audio(raw_mp3, text)
    print("TTS engine:", engine)

    post_process_audio(raw_mp3, mp3)

    audio_sec = ffprobe_duration(mp3)
    write_srt(srt, text, audio_sec)

    vf = build_visual_filter(title, srt)
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
