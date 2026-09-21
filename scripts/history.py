"""Histórico do canal: vídeos publicados e clips do Pexels já usados."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

HISTORY_PATH = Path("out/content_history.json")
MAX_PUBLISHED = 400
MAX_CLIP_IDS = 1500


def load_history() -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if HISTORY_PATH.exists():
        try:
            data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    published = data.get("published") if isinstance(data.get("published"), list) else []
    clip_ids = data.get("pexels_ids") if isinstance(data.get("pexels_ids"), list) else []
    # Formato antigo (v1): só listas de temas. Converte-os em títulos "já vistos".
    if not published and isinstance(data.get("topics"), list):
        published = [{"title": str(t), "topic": str(t)} for t in dict.fromkeys(data["topics"])]
    return {
        "published": [p for p in published if isinstance(p, dict)],
        "pexels_ids": [int(i) for i in clip_ids if str(i).isdigit()],
    }


def record_publish(meta: Dict[str, Any], video_id: str) -> None:
    history = load_history()
    history["published"].append(
        {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "video_id": str(video_id)[:20],
            "title": str(meta.get("title", ""))[:100],
            "topic": str(meta.get("topic", ""))[:60],
            "pillar": str(meta.get("pillar", ""))[:60],
            "angle": str(meta.get("angle", ""))[:120],
        }
    )
    ids: List[int] = history["pexels_ids"] + [int(i) for i in meta.get("pexels_ids", [])]
    compact = {
        "version": 2,
        "published": history["published"][-MAX_PUBLISHED:],
        "pexels_ids": list(dict.fromkeys(ids))[-MAX_CLIP_IDS:],
    }
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(compact, indent=2), encoding="utf-8")
