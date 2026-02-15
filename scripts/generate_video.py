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

def main():
    mp3 = OUT_DIR / "audio.mp3"
    mp4 = OUT_DIR / "video.mp4"

    run([
        "python", "-m", "edge_tts",
        "--voice", "en-US-GuyNeural",
        "--text", TEXT,
        "--write-media", str(mp3)
    ])

    run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "color=c=#0b0f14:s=1080x1920:d=60",
        "-i", str(mp3),
        "-vf", "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='Most People Stay Broke':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=200",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        str(mp4)
    ])

    Path("meta_title.txt").write_text(TITLE)
    Path("meta_desc.txt").write_text(
        "Welcome to Silent Money Blueprint.\n\n#money #investing #shorts"
    )

if __name__ == "__main__":
    main()
