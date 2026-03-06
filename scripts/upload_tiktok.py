from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from validation import assert_ready_for_upload

API_BASE = "https://open.tiktokapis.com"
CREATOR_INFO_ENDPOINT = f"{API_BASE}/v2/post/publish/creator_info/query/"
VIDEO_INIT_ENDPOINT = f"{API_BASE}/v2/post/publish/video/init/"
STATUS_ENDPOINT = f"{API_BASE}/v2/post/publish/status/fetch/"


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


def load_meta(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def auth_headers(access_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def tiktok_post(access_token: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(endpoint, headers=auth_headers(access_token), json=payload, timeout=45)
    text_preview = response.text[:600]
    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"TikTok API invalid JSON ({response.status_code}): {text_preview}") from exc

    if response.status_code >= 400:
        raise RuntimeError(f"TikTok API HTTP {response.status_code}: {json.dumps(data)}")

    err = data.get("error", {})
    code = (err.get("code") or "").lower()
    if code and code != "ok":
        raise RuntimeError(f"TikTok API error {err.get('code')}: {err.get('message')} (log_id={err.get('log_id')})")

    return data


def get_creator_info(access_token: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    data = tiktok_post(access_token, CREATOR_INFO_ENDPOINT, payload)
    creator = data.get("data", {})
    if not creator:
        raise RuntimeError("TikTok creator_info response missing data")
    return creator


def choose_privacy_level(creator_info: Dict[str, Any]) -> str:
    options = creator_info.get("privacy_level_options") or []
    preferred = os.getenv("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY").strip()

    if preferred and preferred in options:
        return preferred

    for candidate in ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "PUBLIC_TO_EVERYONE"]:
        if candidate in options:
            return candidate

    if options:
        return str(options[0])

    return "SELF_ONLY"


def sanitize_title_for_tiktok(text: str) -> str:
    title = " ".join(text.split())
    max_chars = int(os.getenv("TIKTOK_TITLE_MAX_CHARS", "120"))
    if len(title) > max_chars:
        title = title[: max_chars - 1].rstrip() + "..."
    return title


def init_direct_post(access_token: str, title: str, video_path: Path, creator_info: Dict[str, Any]) -> Dict[str, Any]:
    size_bytes = video_path.stat().st_size
    if size_bytes <= 0:
        raise RuntimeError("Video file is empty")

    post_info = {
        "title": title,
        "privacy_level": choose_privacy_level(creator_info),
        "disable_duet": bool(creator_info.get("duet_disabled", False)),
        "disable_comment": bool(creator_info.get("comment_disabled", False)),
        "disable_stitch": bool(creator_info.get("stitch_disabled", False)),
        "video_cover_timestamp_ms": 800,
    }

    payload = {
        "post_info": post_info,
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size_bytes,
            "chunk_size": size_bytes,
            "total_chunk_count": 1,
        },
    }

    data = tiktok_post(access_token, VIDEO_INIT_ENDPOINT, payload)
    result = data.get("data", {})
    if not result.get("upload_url") or not result.get("publish_id"):
        raise RuntimeError(f"TikTok init response missing upload_url/publish_id: {json.dumps(data)}")
    return result


def upload_binary(upload_url: str, video_path: Path) -> None:
    size_bytes = video_path.stat().st_size
    headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(size_bytes),
        "Content-Range": f"bytes 0-{size_bytes - 1}/{size_bytes}",
    }

    with video_path.open("rb") as media:
        response = requests.put(upload_url, headers=headers, data=media, timeout=180)

    if response.status_code not in (200, 201, 202, 204):
        raise RuntimeError(f"TikTok upload failed HTTP {response.status_code}: {response.text[:500]}")


def fetch_status(access_token: str, publish_id: str) -> Dict[str, Any]:
    payload = {"publish_id": publish_id}
    data = tiktok_post(access_token, STATUS_ENDPOINT, payload)
    return data.get("data", {})


def wait_for_terminal_status(access_token: str, publish_id: str) -> Dict[str, Any]:
    interval = int(os.getenv("TIKTOK_STATUS_POLL_INTERVAL_SEC", "8"))
    attempts = int(os.getenv("TIKTOK_STATUS_POLL_ATTEMPTS", "15"))

    terminal_tokens = (
        "complete",
        "published",
        "success",
        "failed",
        "rejected",
        "cancel",
    )

    latest: Dict[str, Any] = {}
    for _ in range(attempts):
        latest = fetch_status(access_token, publish_id)
        status = str(latest.get("status", "")).lower()
        if any(token in status for token in terminal_tokens):
            return latest
        time.sleep(interval)

    return latest


def main() -> None:
    assert_ready_for_upload()

    access_token = os.getenv("TIKTOK_ACCESS_TOKEN", "").strip()
    if not access_token:
        raise RuntimeError("Missing TIKTOK_ACCESS_TOKEN")

    video_path = Path("out/video.mp4")
    if not video_path.exists():
        raise FileNotFoundError("Missing out/video.mp4")

    title = load_meta(Path("meta_title.txt"))
    if not title:
        title = "Daily finance short"

    creator_info = get_creator_info(access_token)
    max_duration = int(creator_info.get("max_video_post_duration_sec") or 0)
    video_sec = ffprobe_duration(video_path)
    if max_duration and video_sec > max_duration:
        raise RuntimeError(
            f"Video duration ({video_sec:.2f}s) exceeds creator max ({max_duration}s)."
        )

    safe_title = sanitize_title_for_tiktok(title)
    init_data = init_direct_post(access_token, safe_title, video_path, creator_info)
    publish_id = str(init_data["publish_id"])
    upload_url = str(init_data["upload_url"])

    upload_binary(upload_url, video_path)

    status_data = wait_for_terminal_status(access_token, publish_id)
    print("TikTok publish_id:", publish_id)
    print("TikTok status:", json.dumps(status_data, ensure_ascii=False))


if __name__ == "__main__":
    main()

