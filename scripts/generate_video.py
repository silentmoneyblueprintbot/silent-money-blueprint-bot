import subprocess
from pathlib import Path

OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)

TITLE = "Most People Stay Broke For One Reason"
TEXT = (
    "Most people stay broke because they optimize for comfort, not systems. "
    "If your money disappears after every paycheck, you don't need more motivation. "
    "You need structure. Automate saving. Limit lifestyle inflation. "
    "And invest consistently. Wealth is built quietly."
)

def run(cmd):
    subprocess.run(cmd, check=True)

def make_audio(mp3_path: Path):
    # Edge TTS (tenta) -> gTTS (fallback)
    try:
        run([
            "python", "-m", "edge_tts",
            "--voice", "en-US-GuyNeural",
            "--text", TEXT,
            "--write-media", str(mp3_path)
        ])
        print("✅ Audio via edge-tts")
        return
    except Exception as e:
        print("⚠️ edge-tts falhou, a usar gTTS:", e)

    from gtts import gTTS
    gTTS(TEXT, lang="en").save(str(mp3_path))
    print("✅ Audio via gTTS")

def main():
    mp3 = OUT_DIR / "audio.mp3"
    mp4 = OUT_DIR / "video.mp4"

    make_audio(mp3)

    # Fundo: gradiente animado (subtle) + grain leve
    # - Gradiente via geq em RGB e animação via senos
    bg = (
        "geq=r='20+8*sin(2*PI*(X/W)+T/2)+10*(Y/H)':"
        "g='18+10*sin(2*PI*(Y/H)+T/3)+18*(X/W)':"
        "b='28+14*sin(2*PI*(X/W)+T/4)+22*(Y/H)',"
        "format=yuv420p,"
        "noise=alls=10:allf=t+u"
    )

    # Texto: título + subtitle (2 linhas), com caixa translúcida
    title_text = TITLE.replace(":", "\\:").replace("'", "\\'")
    subtitle = "Build systems. Compound quietly."
    subtitle_text = subtitle.replace(":", "\\:").replace("'", "\\'")

    vf = (
        f"{bg},"
        "drawbox=x=90:y=210:w=900:h=430:color=black@0.35:t=fill,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"text='{title_text}':fontcolor=white:fontsize=64:"
        "x=(w-text_w)/2:y=260,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        f"text='{subtitle_text}':fontcolor=white@0.95:fontsize=40:"
        "x=(w-text_w)/2:y=380"
    )

    # 60s canvas vertical; -shortest corta pelo áudio
    run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "nullsrc=s=1080x1920:d=60",
        "-i", str(mp3),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-shortest",
        str(mp4)
    ])

    Path("meta_title.txt").write_text(TITLE, encoding="utf-8")
    Path("meta_desc.txt").write_text(
        "Welcome to Silent Money Blueprint.\n\n#money #investing #wealth #shorts",
        encoding="utf-8"
    )

if __name__ == "__main__":
    main()

