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
    # SSML reduz “robótico”: pausas + rate + pitch
    safe = text.replace("&", "and")
    return f"""
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
  <voice name="en-US-JennyNeural">
    <prosody rate="-5%" pitch="+2st">
      {safe.replace("\n", "<break time='250ms'/>")}
    </prosody>
  </voice>
</speak>
""".strip()

def make_audio(mp3_path: Path, text: str):
    # 1) Tenta Edge Neural (melhor voz). Às vezes bloqueia no GitHub.
    try:
        run([
            "python", "-m", "edge_tts",
            "--voice", "en-US-JennyNeural",
            "--text", ssml(text),
            "--write-media", str(mp3_path),
            "--ssml"
        ])
        print("✅ Audio via edge-tts (Neural)")
        return
    except Exception as e:
        print("⚠️ edge-tts falhou, fallback gTTS:", e)

    # 2) Fallback gTTS
    from gtts import gTTS
    gTTS(text, lang="en").save(str(mp3_path))
    print("✅ Audio via gTTS")

def post_process_audio(inp: Path, outp: Path):
    # “Des-robótica”: compressão suave + EQ + leve reverb
    run([
        "ffmpeg", "-y",
        "-i", str(inp),
        "-af",
        "highpass=f=80, lowpass=f=12000, "
        "acompressor=threshold=-18dB:ratio=3:attack=10:release=120, "
        "equalizer=f=300:t=q:w=1:g=-2, "
        "equalizer=f=3000:t=q:w=1:g=2, "
        "aecho=0.8:0.9:35:0.12",
        str(outp)
    ])

def build_visual_filter(title: str):
    # Variantes visuais “b-roll” sem downloads:
    # 1) money rain ($)  2) chart line  3) soft gradient
    rng = random.Random(datetime.utcnow().strftime("%Y-%m-%d-%H"))
    style = rng.choice(["money_rain", "chart", "gradient"])

    title_text = title.replace(":", "\\:").replace("'", "\\'")

    base = "format=yuv420p"
    overlay_box = "drawbox=x=80:y=180:w=920:h=460:color=black@0.35:t=fill"
    draw_title = (
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"text='{title_text}':fontcolor=white:fontsize=64:"
        "x=(w-text_w)/2:y=240"
    )

    if style == "money_rain":
        # “Chover dinheiro”: chuva de símbolos $ a cair
        # (simples mas funciona bem em short)
        rain = (
            "geq=r='18+12*sin(2*PI*X/W+T/2)+20*(Y/H)':"
            "g='16+14*sin(2*PI*Y/H+T/3)+18*(X/W)':"
            "b='28+18*sin(2*PI*X/W+T/4)+18*(Y/H)',"
            "noise=alls=12:allf=t+u,"
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            "text='$  $   $  $   $':fontcolor=white@0.35:fontsize=80:"
            "x=mod(40*T*60\\,w):y=mod(220*T\\,h),"
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            "text='$$$':fontcolor=white@0.25:fontsize=120:"
            "x=mod(70*T*40\\,w):y=mod(260*T+400\\,h)"
        )
        return f"{rain},{base},{overlay_box},{draw_title}"

    if style == "chart":
        # Linha a “subir” (efeito de gráfico)
        chart = (
            "geq=r='10+10*(Y/H)':g='12+10*(X/W)':b='22+10*(Y/H)',"
            "noise=alls=8:allf=t+u,"
            "drawbox=x=120:y=820:w=840:h=520:color=black@0.25:t=fill,"
            "drawgrid=w=80:h=80:t=1:c=white@0.08,"
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
            "text='COMPOUNDING':fontcolor=white@0.35:fontsize=32:x=140:y=860"
        )
        return f"{chart},{base},{overlay_box},{draw_title}"

    # gradient default
    grad = (
        "geq=r='20+8*sin(2*PI*(X/W)+T/2)+12*(Y/H)':"
        "g='18+10*sin(2*PI*(Y/H)+T/3)+16*(X/W)':"
        "b='28+14*sin(2*PI*(X/W)+T/4)+18*(Y/H)',"
        "noise=alls=10:allf=t+u"
    )
    return f"{grad},{base},{overlay_box},{draw_title}"

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
