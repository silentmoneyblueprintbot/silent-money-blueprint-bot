from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Dict, List

ROOT = Path(".")
OUT_DIR = ROOT / "out"
REPORT_PATH = OUT_DIR / "validation_report.json"


def ffprobe_duration(path: Path) -> float:
    output = subprocess.check_output(
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
    return float(output)


def black_ratio(path: Path, duration: float) -> float:
    if duration <= 0:
        return 1.0

    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-vf",
            "blackdetect=d=0.12:pic_th=0.92:pix_th=0.10",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    stderr = proc.stderr or ""

    total_black = 0.0
    for line in stderr.splitlines():
        if "black_duration:" not in line:
            continue
        try:
            value = line.split("black_duration:", 1)[1].strip().split()[0]
            total_black += float(value)
        except Exception:
            continue

    return min(1.0, total_black / duration)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def _append_error(errors: List[str], msg: str) -> None:
    if msg not in errors:
        errors.append(msg)


def validate_artifacts(strict: bool = True) -> Dict[str, object]:
    errors: List[str] = []
    warnings: List[str] = []

    script_text = read_text(OUT_DIR / "script.txt")
    title = read_text(ROOT / "meta_title.txt")
    description = read_text(ROOT / "meta_desc.txt")

    if len(script_text.split()) < 35:
        _append_error(errors, "Script is too short or empty.")
    if len(title) < 12:
        _append_error(errors, "Title is too short.")
    if "#shorts" not in description.lower():
        warnings.append("Description does not include #shorts.")

    audio_path = OUT_DIR / "audio.mp3"
    video_path = OUT_DIR / "video.mp4"

    for required in [audio_path, video_path, ROOT / "meta_title.txt", ROOT / "meta_desc.txt"]:
        if not required.exists():
            _append_error(errors, f"Missing required file: {required}")

    audio_seconds = 0.0
    video_seconds = 0.0
    video_black_ratio = 1.0

    if audio_path.exists():
        audio_seconds = ffprobe_duration(audio_path)
        if audio_seconds < 4.0:
            _append_error(errors, f"Audio is too short ({audio_seconds:.2f}s).")

    if video_path.exists():
        video_seconds = ffprobe_duration(video_path)
        if video_seconds < 4.0:
            _append_error(errors, f"Video is too short ({video_seconds:.2f}s).")

    if audio_seconds > 0 and video_seconds > 0:
        drift = abs(video_seconds - audio_seconds)
        if drift > 3.0:
            warnings.append(
                f"Video/audio duration drift is high ({drift:.2f}s)."
            )

    if video_path.exists() and video_seconds > 0:
        video_black_ratio = black_ratio(video_path, video_seconds)
        if video_black_ratio > 0.45:
            _append_error(
                errors,
                f"Video likely too dark/black (black ratio {video_black_ratio:.2%}).",
            )

    ok = len(errors) == 0
    result = {
        "ok": ok,
        "strict": strict,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "audio_seconds": round(audio_seconds, 3),
            "video_seconds": round(video_seconds, 3),
            "video_black_ratio": round(video_black_ratio, 4),
            "script_word_count": len(script_text.split()),
        },
    }

    OUT_DIR.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if strict and not ok:
        raise RuntimeError("Validation failed: " + " | ".join(errors))

    return result


def assert_ready_for_upload() -> Dict[str, object]:
    return validate_artifacts(strict=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail process on validation errors")
    args = parser.parse_args()

    result = validate_artifacts(strict=args.strict)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
