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


def ssml(text: str) -> str:
    safe = text.replace("&", "and").strip()
    safe = safe.replace("\n", " <break time='300ms'/> ")

    return f"""
<speak>
  <voice name="en-US-JennyNeural">
    <prosody rate="-2%" pitch="+1st">
      {safe}
    </prosody>
  </voice>
</speak>
""".strip()




EDGE_VOICES = [
    "en-US-JennyNeural",
    "en-US-AriaNeural",
    "en-US-GuyNeural",
]

def make_audio(mp3_path: Path, text: str):
    ssml_content = ssml(text)
    ssml_file = OUT_DIR / "voice.ssml"
    ssml_file.write_text(ssml_content, encoding="utf-8")

    try:
        run([
            "python", "-m", "edge_tts",
            "--voice", "en-US-JennyNeural",
            "--file", str(ssml_file),
            "--write-media", str(mp3_path),
            "--ssml"
        ])
        print("✅ Audio via edge-tts (Neural)")
        return
    except Exception as e:
        print("⚠️ edge-tts falhou, fallback gTTS:", e)

    from gtts import gTTS
    gTTS(text, lang="en").save(str(mp3_path))
    print("✅ Audio via gTTS")




def post_process_audio(inp: Path, outp: Path):
    run([
        "ffmpeg", "-y",
        "-i", str(inp),
        "-af",
        "highpass=f=70, lowpass=f=12000, "
        "afftdn=nf=-25, "
        "acompressor=threshold=-18dB:ratio=3:attack=10:release=140, "
        "dynaudnorm=f=150:g=7, "
        "equalizer=f=220:t=q:w=1:g=-2, "
        "equalizer=f=3500:t=q:w=1:g=2",
        str(outp)
    ])



def write_text_file(path: Path, text: str):
    # ffmpeg drawtext é muito mais estável com textfile=
    safe = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    path.write_text(safe, encoding="utf-8")


def build_visual_filter(title: str, duration_sec: int = 120):
    """
    Fundo procedural estilo Minecraft/parkour:
    """

    rng = random.Random(datetime.utcnow().strftime("%Y-%m-%d-%H"))
    seed = rng.randint(1, 99999)

    title_file = OUT_DIR / "title.txt"
    write_text_file(title_file, title)

    base = "format=yuv420p"
    overlay_box = "drawbox=x=80:y=180:w=920:h=460:color=black@0.38:t=fill"

    draw_title = (
    "drawtext=font=DejaVuSans-Bold:"
    f"textfile={title_file}:reload=0:"
    "fontcolor=white:fontsize=64:"
    "x=(w-text_w)/2:y=240"
)


    mc = (
    "geq=r='14+6*(Y/H)':g='14+7*(X/W)':b='18+8*(Y/H)',"
    "noise=alls=10:allf=t+u,"
    "lutrgb=r='(val/48)*48':g='(val/48)*48':b='(val/48)*48',"
    "eq=contrast=1.10:brightness=-0.015:saturation=1.05,"
    "scale=iw/14:ih/14:flags=neighbor,"
    "scale=iw*14:ih*14:flags=neighbor,"
    "scale=1080:3840:flags=neighbor,"
    "crop=1080:1920:x=0:y='mod(t*420,ih-1920)',"
    "rotate='0.006*sin(t*1.1)':c=black@0"
)


    return f"{mc},{base},{overlay_box},{draw_title}"



def main():
    if MODE == "long":
        title, text, tags = make_long()
    else:
        title, text, tags = make_short()

    raw_mp3 = OUT_DIR / "audio_raw.mp3"
    mp3 = OUT_DIR / "audio.mp3"
    mp4 = OUT_DIR / "video.mp4"

    make_audio(raw_mp3, text)
    post_process_audio(raw_mp3, mp3)

    vf = build_visual_filter(title)

    run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "nullsrc=s=1080x1920:d=120",  # grande; corta no áudio
        "-i", str(mp3),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
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
