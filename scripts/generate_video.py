"""SilentBlueprint v2: guião (Claude) -> voz (edge-tts) -> b-roll (Pexels) -> vídeo 1080x1920.

- Um clip diferente por frase do guião, com movimento suave (pan).
- Legendas "karaoke" sincronizadas palavra a palavra (tempos reais do TTS), em ASS
  com resolução nativa 1080x1920 (o tamanho da letra é o real, sem escalas estranhas).
- Qualquer falha (guião, voz ou imagens) faz o run falhar: nada de publicar lixo.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from history import load_history

OUT_DIR = Path("out")
CLIPS_DIR = OUT_DIR / "clips"
W, H, FPS = 1080, 1920, 30
TAIL_SEC = 0.6
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()
MAX_CLIP_BYTES = 90 * 1024 * 1024
FALLBACK_QUERIES = [
    "counting money", "city street people", "person using laptop", "coffee shop work",
    "shopping bags", "paying bills desk", "coins in jar", "walking city sunset",
]
CAPTION_FONT = os.getenv("CAPTION_FONT", "Montserrat Black")
HIGHLIGHT = "&H0000D7FF&"  # amarelo-dourado (formato ASS: BGR)


# --------------------------------------------------------------------------- utils
def run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)], text=True).strip()
    return float(out)


def snap(t: float) -> float:
    return round(t * FPS) / FPS


# ------------------------------------------------------------------ timeline/captions
def align_words(segments: List[Dict[str, str]], words: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """Associa cada palavra falada ao segmento do guião e à pontuação que a segue."""
    narration = ""
    seg_ranges: List[Tuple[int, int]] = []
    for seg in segments:
        start = len(narration)
        narration += seg["text"].strip() + " "
        seg_ranges.append((start, len(narration)))
    lower = narration.lower()

    cursor, seg_idx, timeline = 0, 0, []
    for w in words:
        token = str(w["text"]).strip()
        pos = lower.find(token.lower(), cursor) if token else -1
        if pos != -1 and pos - cursor < 60:
            end = pos + len(token)
            cursor = end
            while seg_idx < len(seg_ranges) - 1 and pos >= seg_ranges[seg_idx][1]:
                seg_idx += 1
            after = narration[end:end + 2].strip()[:1]
        else:
            after = ""
        timeline.append({**w, "seg": seg_idx, "punct": after in ".!?,;:"})
    return narration.strip(), timeline


def segment_bounds(n_segments: int, timeline: List[Dict[str, Any]], total: float) -> List[Tuple[float, float]]:
    starts = [0.0]
    for i in range(1, n_segments):
        first = next((w for w in timeline if w["seg"] == i), None)
        starts.append(snap(float(first["start"])) if first else starts[-1] + 1.0)
    starts = [max(s, starts[j - 1] + 0.8) if j else s for j, s in enumerate(starts)]
    ends = starts[1:] + [snap(total)]
    return [(s, e) for s, e in zip(starts, ends) if e - s > 0.3]


def _ass_time(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _caption_word(text: str) -> str:
    text = re.sub(r"[{}\\]", "", text)
    text = re.sub(r"[^\w$%'’\- ]", "", text)  # mantém espaços ("20 dollars" vem num só bloco)
    return re.sub(r"\s+", " ", text).strip().upper()


def group_words(timeline: List[Dict[str, Any]], max_words: int = 3, max_chars: int = 16) -> List[List[Dict[str, Any]]]:
    groups: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    for i, w in enumerate(timeline):
        if not _caption_word(str(w["text"])):
            continue
        current.append(w)
        chars = sum(len(_caption_word(str(x["text"]))) + 1 for x in current)
        nxt = timeline[i + 1] if i + 1 < len(timeline) else None
        gap = (float(nxt["start"]) - float(w["end"])) if nxt else 1.0
        if len(current) >= max_words or chars >= max_chars or w["punct"] or gap > 0.3 \
                or (nxt is not None and nxt["seg"] != w["seg"]):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def write_ass(timeline: List[Dict[str, Any]], total: float, path: Path) -> None:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{CAPTION_FONT},104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,0,0,0,0,100,100,1,0,1,8,4,5,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    groups = group_words(timeline)
    for gi, group in enumerate(groups):
        g_start = float(group[0]["start"])
        g_end = float(groups[gi + 1][0]["start"]) if gi + 1 < len(groups) else total
        g_end = min(g_end, float(group[-1]["end"]) + 0.6) if gi + 1 < len(groups) else g_end
        words = [_caption_word(str(w["text"])) for w in group]
        for k, w in enumerate(group):
            ev_start = g_start if k == 0 else float(w["start"])
            ev_end = float(group[k + 1]["start"]) if k + 1 < len(group) else g_end
            if ev_end - ev_start < 0.02:
                continue
            parts = [f"{{\\c{HIGHLIGHT}}}{t}{{\\c&H00FFFFFF&}}" if j == k else t for j, t in enumerate(words)]
            pop = "\\fscx86\\fscy86\\t(0,90,\\fscx100\\fscy100)" if k == 0 else ""
            text = f"{{\\an5\\pos({W // 2},{int(H * 0.60)}){pop}}}" + " ".join(parts)
            lines.append(f"Dialogue: 0,{_ass_time(ev_start)},{_ass_time(ev_end)},Cap,,0,0,0,,{text}\n")
    path.write_text("".join(lines), encoding="utf-8")


# ------------------------------------------------------------------------- b-roll
def _pick_file(video: Dict[str, Any]) -> Optional[str]:
    best, best_score = None, None
    for f in video.get("video_files", []):
        link = str(f.get("link") or "")
        host = urlparse(link).hostname or ""
        width, height = int(f.get("width") or 0), int(f.get("height") or 0)
        if f.get("file_type") != "video/mp4" or not link.startswith("https://") \
                or not (host == "pexels.com" or host.endswith(".pexels.com")) or height < 720:
            continue
        score = -abs(height - 1920) + (100000 if height > width else 0)
        if best_score is None or score > best_score:
            best, best_score = link, score
    return best


def _search_pexels(query: str, used: set, min_dur: float) -> Optional[Tuple[int, str]]:
    for page in (1, 2):
        try:
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": PEXELS_API_KEY},
                params={"query": query, "orientation": "portrait", "size": "medium",
                        "per_page": 15, "page": page},
                timeout=20,
            )
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
        except (requests.RequestException, ValueError) as exc:
            print(f"Pexels falhou para '{query}': {exc}")
            return None
        for video in videos:
            vid = int(video.get("id") or 0)
            if not vid or vid in used or float(video.get("duration") or 0) < min(min_dur, 4.0):
                continue
            link = _pick_file(video)
            if link:
                return vid, link
        if len(videos) < 15:
            break
    return None


def _download(url: str, dest: Path) -> bool:
    try:
        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            size = 0
            with dest.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    size += len(chunk)
                    if size > MAX_CLIP_BYTES:
                        raise ValueError("clip demasiado grande")
                    fh.write(chunk)
        return ffprobe_duration(dest) > 1.0
    except Exception as exc:  # noqa: BLE001
        print(f"Download falhou: {exc}")
        dest.unlink(missing_ok=True)
        return False


def fetch_broll(segments: List[Dict[str, str]], bounds: List[Tuple[float, float]]) -> Tuple[List[Optional[Path]], List[int]]:
    if not PEXELS_API_KEY:
        raise RuntimeError("Falta o secret PEXELS_API_KEY.")
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    used = set(load_history()["pexels_ids"])
    rng = random.Random(" ".join(s["broll"] for s in segments))
    clips: List[Optional[Path]] = []
    picked_ids: List[int] = []
    for i, (seg, (start, end)) in enumerate(zip(segments, bounds)):
        queries = [seg["broll"], " ".join(seg["broll"].split()[:2])] + rng.sample(FALLBACK_QUERIES, 2)
        clip: Optional[Path] = None
        for query in dict.fromkeys(q for q in queries if q.strip()):
            found = _search_pexels(query, used, end - start)
            if not found:
                continue
            vid, link = found
            used.add(vid)
            dest = CLIPS_DIR / f"clip_{i}.mp4"
            if _download(link, dest):
                clip = dest
                picked_ids.append(vid)
                print(f"Segmento {i + 1}: '{query}' -> pexels {vid}")
                break
        clips.append(clip)
    if sum(c is not None for c in clips) < max(2, len(clips) // 2):
        raise RuntimeError("Não foi possível obter imagens suficientes do Pexels.")
    return clips, picked_ids


# ------------------------------------------------------------------------- render
def render_segment(src: Path, dur: float, index: int, dest: Path) -> None:
    clip_dur = ffprobe_duration(src)
    loop = clip_dur < dur + 0.3
    offset = 0.0 if loop else round(min(1.0, clip_dur - dur - 0.2), 2)
    frames = max(1, round(dur * FPS))
    progress = f"min(1,n/{frames})"
    mode = index % 3
    if mode == 0:
        x, y = f"(iw-ow)*{progress}", "(ih-oh)/2"
    elif mode == 1:
        x, y = f"(iw-ow)*(1-{progress})", "(ih-oh)/2"
    else:
        x, y = "(iw-ow)/2", f"(ih-oh)*{progress}"
    vf = (
        f"fps={FPS},scale={int(W * 1.1)}:{int(H * 1.1)}:force_original_aspect_ratio=increase,"
        f"crop={int(W * 1.1)}:{int(H * 1.1)},crop={W}:{H}:x='{x}':y='{y}',"
        "eq=contrast=1.05:saturation=1.08:brightness=-0.03,setsar=1,format=yuv420p"
    )
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-ss", f"{offset}", "-i", str(src), "-frames:v", str(frames), "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), str(dest)]
    run(cmd)


def render_video(clips: List[Optional[Path]], bounds: List[Tuple[float, float]], audio: Path,
                 ass: Path, total: float, dest: Path) -> None:
    available = [c for c in clips if c is not None]
    parts: List[Path] = []
    for i, ((start, end), clip) in enumerate(zip(bounds, clips)):
        src = clip
        if src is None:  # reutiliza um clip que não esteja nos cortes vizinhos
            neighbours = {clips[j] for j in (i - 1, i + 1) if 0 <= j < len(clips)}
            options = [c for c in available if c not in neighbours] or available
            src = options[i % len(options)]
        part = OUT_DIR / f"part_{i:02d}.mp4"
        render_segment(src, end - start, i, part)
        parts.append(part)

    concat_list = OUT_DIR / "parts.txt"
    concat_list.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    body = OUT_DIR / "body.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", str(body)])

    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(body), "-i", str(audio),
        "-filter_complex", f"[0:v]ass={ass.as_posix()}[v];[1:a]apad[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(dest),
    ])
    for p in parts + [concat_list, body]:
        p.unlink(missing_ok=True)


def post_process_audio(inp: Path, outp: Path) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-i", str(inp),
         "-af", "highpass=f=70,acompressor=threshold=-18dB:ratio=2:attack=10:release=150,"
                "loudnorm=I=-14:TP=-1.5:LRA=9",
         "-ar", "44100", "-ac", "2", "-b:a", "192k", str(outp)])


# --------------------------------------------------------------------------- main
def build_metadata(script: Dict[str, Any], pexels_ids: List[int], voice: str) -> Dict[str, Any]:
    tags = [t for t in script["hashtags"] if t != "shorts"]
    description = (
        f"{script['description']}\n\n"
        "Educational content only, not financial advice.\n\n"
        "#shorts " + " ".join(f"#{t}" for t in tags)
    )
    return {
        "title": script["title"],
        "description": description,
        "tags": tags + ["personal finance", "money tips"],
        "topic": script["topic"],
        "pillar": script.get("pillar", ""),
        "angle": script.get("angle", ""),
        "pexels_ids": pexels_ids,
        "voice": voice,
    }


def main() -> None:
    from script_writer import write_script
    from tts import synthesize

    if shutil.which("fc-list"):
        fonts = subprocess.run(["fc-list"], capture_output=True, text=True).stdout
        if CAPTION_FONT.split()[0].lower() not in fonts.lower():
            print(f"AVISO: a fonte '{CAPTION_FONT}' não está instalada; as legendas usam a fonte por omissão.")

    OUT_DIR.mkdir(exist_ok=True)
    script = write_script()
    (OUT_DIR / "script.json").write_text(json.dumps(script, indent=2), encoding="utf-8")

    narration = " ".join(s["text"] for s in script["segments"])
    (OUT_DIR / "script.txt").write_text(narration, encoding="utf-8")

    raw_mp3, mp3 = OUT_DIR / "audio_raw.mp3", OUT_DIR / "audio.mp3"
    words, voice = synthesize(narration, raw_mp3)
    post_process_audio(raw_mp3, mp3)
    total = snap(ffprobe_duration(mp3) + TAIL_SEC)

    _, timeline = align_words(script["segments"], words)
    bounds = segment_bounds(len(script["segments"]), timeline, total)
    ass = OUT_DIR / "captions.ass"
    write_ass(timeline, total, ass)

    clips, pexels_ids = fetch_broll(script["segments"][:len(bounds)], bounds)
    render_video(clips, bounds, mp3, ass, total, OUT_DIR / "video.mp4")
    shutil.rmtree(CLIPS_DIR, ignore_errors=True)

    meta = build_metadata(script, pexels_ids, voice)
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    Path("meta_title.txt").write_text(meta["title"], encoding="utf-8")
    Path("meta_desc.txt").write_text(meta["description"], encoding="utf-8")
    print(f"Vídeo pronto: {meta['title']} ({total:.1f}s, {len(bounds)} cortes, voz {voice})")


if __name__ == "__main__":
    main()
