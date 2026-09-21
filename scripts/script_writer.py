"""Escreve o guião diário com o Claude (claude -p, autenticado pela subscrição).

Segurança:
- O Claude corre SEM ferramentas e sem MCP, numa pasta temporária vazia e com um
  ambiente mínimo: não vê os outros secrets (YouTube, Pexels) nem o repositório.
- A resposta é tratada como dados não confiáveis: é validada, limpa de caracteres
  de controlo, URLs e marcação, e rejeitada se violar as regras.
- Se falhar, o run falha e NADA é publicado (melhor saltar um dia do que publicar lixo).
"""
from __future__ import annotations

import difflib
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

from history import load_history

MODEL = os.getenv("SCRIPT_MODEL", "sonnet")
MAX_ATTEMPTS = 3

PILLARS = [
    "emergency funds", "high-interest debt", "index fund investing", "compound interest",
    "lifestyle inflation", "budgeting that actually sticks", "subscriptions and hidden costs",
    "salary negotiation and raises", "retirement accounts basics", "saving on groceries and food",
    "car ownership costs", "housing costs and rent", "impulse buying psychology",
    "investment fees", "inflation and cash savings", "side income basics", "credit scores",
    "automating money habits", "planning big purchases", "money mindset myths",
]

ANGLES = [
    "a costly mistake most people make and the simple fix",
    "a common myth that sounds smart but is wrong",
    "a surprising but true money fact, explained simply",
    "two choices compared side by side with simple math",
    "one 30-second action the viewer can do today",
    "a short relatable story about one person and one decision",
    "one concept explained in plain words with an everyday example",
]

BANNED_PATTERNS = [
    r"guarantee", r"risk[- ]free", r"get rich quick", r"can'?t lose", r"100% safe",
    r"\bbuy (?:this|these) (?:stock|coin|crypto)", r"financial advice", r"https?://", r"www\.",
    r"\bstudies show\b", r"\bresearch shows\b", r"\bsubscribe\b",
]

SYSTEM_PROMPT = """You write scripts for "Silent Money Blueprint", a faceless YouTube Shorts channel about practical personal finance for young adults.

Voice: calm, clear, confident, friendly. Plain English, short sentences. Sound like a smart friend, never like a template or an ad.

Rules:
- 5 to 8 segments. Segment 1 is the hook: at most 12 words, creates curiosity or tension in the first 2 seconds. Never start with "Did you know", "Hey guys", "In this video" or "Topic".
- Total narration 75 to 115 words across all segments. Each segment is 1 or 2 short spoken sentences.
- Never read out labels like "Topic:", "Myth:", "Reality:", "Step 1:". Write natural speech.
- At most 2 concrete numbers, always framed as illustrative examples ("say you put 200 dollars a month aside"). Keep arithmetic correct and conservative, round down and say "about". Write amounts so a narrator reads them naturally ("200 dollars").
- Never invent statistics, studies, quotes, laws or named sources. No stock, coin or product recommendations. No promises of returns. Educational only.
- The last segment ends with a short, natural line inviting the viewer to follow for more, worded differently each time. Do not use the word "subscribe".
- No emojis, hashtags, URLs, curly braces or backslashes in any text.
- "broll": a 2-4 word stock-footage search phrase showing a real, filmable scene that matches the segment (e.g. "woman checking phone", "grocery store aisle", "coins in jar"). No text, charts, logos or brand names.
- "title": natural and curiosity-driven, at most 70 characters, honest, no ALL CAPS, no emojis.
- "description": 1 or 2 sentences summarising the takeaway. No links.
- "hashtags": 3 to 6 relevant tags, lowercase, no # sign, no spaces.

Reply with ONLY one JSON object, no markdown fences, exactly in this shape:
{"topic": "...", "title": "...", "segments": [{"text": "...", "broll": "..."}], "description": "...", "hashtags": ["...", "..."]}
"""

_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _clean(text: Any, max_len: int) -> str:
    text = _CTRL.sub(" ", str(text or ""))
    text = text.replace("{", "(").replace("}", ")").replace("\\", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len].strip()


def _clean_tag(tag: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(tag).lower())[:30]


def _pick_brief(history: Dict[str, Any]) -> Dict[str, str]:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(f"{day}:{os.getenv('GITHUB_RUN_ID', '')}")
    recent_pillars = [p.get("pillar", "") for p in history["published"][-12:]]
    pillars = [p for p in PILLARS if p not in recent_pillars] or PILLARS
    recent_angles = [p.get("angle", "") for p in history["published"][-3:]]
    angles = [a for a in ANGLES if a not in recent_angles] or ANGLES
    return {"pillar": rng.choice(pillars), "angle": rng.choice(angles)}


def _user_prompt(brief: Dict[str, str], recent_titles: List[str], feedback: str) -> str:
    recent = "\n".join(f"- {t}" for t in recent_titles[-40:]) or "- (none yet)"
    prompt = (
        "Write today's Short.\n"
        f"Theme area: {brief['pillar']}\n"
        f"Angle: {brief['angle']}\n"
        "Pick ONE specific, fresh topic inside the theme area. It must be clearly different "
        f"from these already-published videos:\n{recent}\n"
    )
    if feedback:
        prompt += f"\nYour previous attempt was rejected because: {feedback}. Fix that.\n"
    return prompt


def _extract_json(raw: str) -> Dict[str, Any]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("reply did not contain a JSON object")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("reply JSON is not an object")
    return data


def _run_claude(user_prompt: str) -> Dict[str, Any]:
    if shutil.which("claude") is None:
        raise RuntimeError("Claude Code CLI ('claude') não está instalado no runner.")
    # Remove espaços/quebras de linha que entram ao copiar o token do Terminal.
    token = re.sub(r"\s+", "", os.getenv("CLAUDE_CODE_OAUTH_TOKEN", ""))
    if not token:
        raise RuntimeError("Falta o secret CLAUDE_CODE_OAUTH_TOKEN.")

    with tempfile.TemporaryDirectory(prefix="smb-claude-") as sandbox:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": sandbox,
            "CLAUDE_CODE_OAUTH_TOKEN": token,
            "DISABLE_AUTOUPDATER": "1",
            "DISABLE_TELEMETRY": "1",
            "DISABLE_ERROR_REPORTING": "1",
        }
        cmd = [
            "claude", "-p", user_prompt,
            "--output-format", "json",
            "--system-prompt", SYSTEM_PROMPT,
            "--tools", "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--max-turns", "2",
            "--model", MODEL,
        ]
        proc = subprocess.run(
            cmd, cwd=sandbox, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=300, check=False,
        )

    stdout = (proc.stdout or "").strip()
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        tail = (proc.stderr or stdout)[-300:].replace(token, "***")
        raise RuntimeError(f"resposta inválida do claude -p (exit {proc.returncode}): {tail}")

    if not isinstance(envelope, dict) or envelope.get("is_error") or proc.returncode != 0:
        detail = str(envelope.get("result") or envelope.get("subtype") or "erro desconhecido")
        raise RuntimeError(f"claude -p falhou: {detail[:300]}")

    return _extract_json(str(envelope.get("result", "")))


def _validate(data: Dict[str, Any], recent_titles: List[str], recent_topics: List[str]) -> Dict[str, Any]:
    segments_in = data.get("segments")
    if not isinstance(segments_in, list) or not 5 <= len(segments_in) <= 8:
        raise ValueError("it must have 5 to 8 segments")

    segments = []
    for seg in segments_in:
        if not isinstance(seg, dict):
            raise ValueError("every segment must be an object with text and broll")
        text = _clean(seg.get("text"), 220)
        broll = _clean(seg.get("broll"), 40)
        if len(text.split()) < 2 or len(broll) < 3:
            raise ValueError("a segment text or broll is empty")
        segments.append({"text": text, "broll": broll})

    title = _clean(data.get("title"), 70)
    topic = _clean(data.get("topic"), 60)
    description = _clean(data.get("description"), 300)
    tags_in = data.get("hashtags") if isinstance(data.get("hashtags"), list) else []
    hashtags = [t for t in (_clean_tag(h) for h in tags_in) if len(t) >= 2][:6]

    words = sum(len(s["text"].split()) for s in segments)
    if not 65 <= words <= 130:
        raise ValueError(f"the narration has {words} words, it must have 75 to 115")
    if len(segments[0]["text"].split()) > 14:
        raise ValueError("the hook (segment 1) must have at most 12 words")
    if len(title) < 15 or title.isupper():
        raise ValueError("the title must be 15-70 characters and not ALL CAPS")
    if len(description) < 20:
        raise ValueError("the description is too short")

    full = " ".join([title, description] + [s["text"] for s in segments]).lower()
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, full):
            raise ValueError(f"it contains forbidden wording matching '{pattern}'")
    if re.search(r"\b(topic|myth|reality|step \d)\s*:", full):
        raise ValueError("it reads template labels aloud")
    if re.search(r"[^\x20-\x7E‘’“”–—]", full):
        raise ValueError("it contains emojis or unusual characters")

    for old in recent_titles[-80:] + recent_topics[-80:]:
        if not old:
            continue
        if difflib.SequenceMatcher(None, title.lower(), old.lower()).ratio() > 0.72 or \
                difflib.SequenceMatcher(None, topic.lower(), old.lower()).ratio() > 0.85:
            raise ValueError(f"it is too similar to an already published video ('{old}')")

    return {
        "topic": topic,
        "title": title,
        "segments": segments,
        "description": description,
        "hashtags": hashtags or ["personalfinance", "money", "savings"],
    }


def write_script() -> Dict[str, Any]:
    history = load_history()
    recent_titles = [p.get("title", "") for p in history["published"]]
    recent_topics = [p.get("topic", "") for p in history["published"]]
    brief = _pick_brief(history)
    print(f"Brief: {brief}")

    feedback = ""
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = _run_claude(_user_prompt(brief, recent_titles, feedback))
            script = _validate(raw, recent_titles, recent_topics)
            script.update(brief)
            print(f"Guião aceite na tentativa {attempt}: {script['title']}")
            return script
        except (ValueError, json.JSONDecodeError) as exc:
            feedback = str(exc)
            last_error = exc
            print(f"Tentativa {attempt} rejeitada: {exc}")
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            last_error = exc
            print(f"Tentativa {attempt} falhou: {exc}")
    raise RuntimeError(f"Não foi possível obter um guião válido: {last_error}")


if __name__ == "__main__":
    print(json.dumps(write_script(), indent=2))
