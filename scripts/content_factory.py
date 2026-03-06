from __future__ import annotations

import hashlib
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

HISTORY_PATH = Path("out/content_history.json")

CTA_OPTIONS = [
    "If this helped, follow for practical money systems.",
    "Save this for your next payday check-in.",
    "If you want part 2, follow and I will post it.",
    "Send this to one friend who keeps saying 'next month'.",
]

FORMATS = [
    "money_mistake",
    "myth_vs_reality",
    "quick_tip",
    "comparison",
    "rich_vs_poor_habit",
    "money_alert",
    "simple_explainer",
    "mini_case",
    "money_curiosity",
]

TOPIC_LIBRARY: List[Dict[str, str]] = [
    {
        "topic": "Emergency fund target",
        "mistake": "keeping every euro in checking and hoping no surprise happens",
        "myth": "you need to save 12 months before investing anything",
        "reality": "start with one month fast, then build to three while you keep investing",
        "quick_tip": "move 10% of your salary to a separate account 30 minutes after payday",
        "comparison": "saving manually once a month vs automatic transfer on payday",
        "rich_habit": "paying yourself first",
        "poor_habit": "waiting to see what is left at the end of the month",
        "alert": "one car repair can erase months of progress",
        "concept": "liquidity",
        "case": "Sara had 0 emergency buffer, then a 600 euro dentist bill forced credit card debt",
        "curiosity": "most households that avoid debt shocks keep at least one month of expenses in cash",
    },
    {
        "topic": "Credit card debt",
        "mistake": "paying only the minimum and calling it under control",
        "myth": "minimum payments protect your credit and solve the problem",
        "reality": "minimum payments mostly protect the bank, not your future",
        "quick_tip": "freeze the card for new spending and set a fixed weekly debt payment",
        "comparison": "buy-now-pay-later convenience vs interest-free life",
        "rich_habit": "using cards for cashback but clearing in full every month",
        "poor_habit": "using debt to maintain lifestyle",
        "alert": "high APR debt can grow faster than your investments",
        "concept": "APR",
        "case": "Tiago carried 2,400 euros at high APR and paid more interest than his yearly ETF gains",
        "curiosity": "small extra payments every week usually beat one big payment at month end",
    },
    {
        "topic": "Index investing",
        "mistake": "trying to pick the one perfect stock every month",
        "myth": "you need to be an expert to invest safely",
        "reality": "broad low-cost index funds remove most guesswork",
        "quick_tip": "set one recurring buy date and never skip it",
        "comparison": "timing the market vs time in the market",
        "rich_habit": "boring consistency",
        "poor_habit": "jumping between hot tips",
        "alert": "missing only a few strong market days can destroy long-term returns",
        "concept": "dollar-cost averaging",
        "case": "Andre invested monthly through bad headlines and ended the year ahead of his trader friend",
        "curiosity": "fees look tiny, but over decades they can eat a large part of gains",
    },
    {
        "topic": "Lifestyle inflation",
        "mistake": "increasing spending every time income grows",
        "myth": "a raise means you can finally upgrade everything",
        "reality": "a raise is a rare chance to lock in a higher savings rate",
        "quick_tip": "when salary increases, send at least half of the raise to investing",
        "comparison": "new salary used for status purchases vs used for assets",
        "rich_habit": "keeping core lifestyle stable while income climbs",
        "poor_habit": "upgrading fixed costs too fast",
        "alert": "fixed monthly costs are harder to reverse than impulse purchases",
        "concept": "savings rate",
        "case": "Rita got a raise, kept the same rent, and built her first 10k in 14 months",
        "curiosity": "people who automate raises into investments often feel richer with less stress",
    },
    {
        "topic": "Budgeting systems",
        "mistake": "tracking every cent manually and quitting after two weeks",
        "myth": "budgeting means no fun",
        "reality": "a good budget gives spending freedom with limits",
        "quick_tip": "use three buckets: essentials, future, guilt-free spending",
        "comparison": "strict spreadsheet punishment vs simple weekly cap",
        "rich_habit": "reviewing money once a week for 15 minutes",
        "poor_habit": "checking bank balance only when stressed",
        "alert": "invisible subscriptions can drain cash without notice",
        "concept": "cash flow",
        "case": "Miguel canceled five forgotten subscriptions and redirected 92 euros monthly to his ISA",
        "curiosity": "weekly money reviews tend to reduce financial anxiety faster than annual plans",
    },
    {
        "topic": "Retirement compounding",
        "mistake": "waiting for the 'perfect' income level before starting",
        "myth": "small monthly investments do not matter",
        "reality": "time often matters more than amount in early years",
        "quick_tip": "start with a tiny recurring amount today, increase every quarter",
        "comparison": "starting at 25 with small contributions vs starting at 35 with larger ones",
        "rich_habit": "starting early even with imperfect amounts",
        "poor_habit": "delaying until confidence is high",
        "alert": "every delayed year can cost thousands in future growth",
        "concept": "compound interest",
        "case": "Two friends invested differently; the earlier starter ended with more despite lower contributions",
        "curiosity": "the first years feel slow, then growth accelerates when compounding stacks",
    },
]


def _stable_seed(mode: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    return f"{mode}:{day}:{run_id}"


def _rng(mode: str) -> random.Random:
    return random.Random(_stable_seed(mode))


def _load_history() -> Dict[str, List[str]]:
    if not HISTORY_PATH.exists():
        return {"topics": [], "formats": [], "hooks": []}
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"topics": [], "formats": [], "hooks": []}


def _save_history(history: Dict[str, List[str]]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    compact = {
        "topics": history.get("topics", [])[-20:],
        "formats": history.get("formats", [])[-20:],
        "hooks": history.get("hooks", [])[-40:],
    }
    HISTORY_PATH.write_text(json.dumps(compact, indent=2), encoding="utf-8")


def _avoid_recent(options: List[str], recent: List[str], rng: random.Random, recent_window: int = 5) -> str:
    blocked = set(recent[-recent_window:])
    candidates = [item for item in options if item not in blocked]
    if not candidates:
        candidates = options
    return rng.choice(candidates)


def _pick_topic_and_format(mode: str) -> Tuple[Dict[str, str], str, Dict[str, List[str]]]:
    rng = _rng(mode)
    history = _load_history()

    available_topics = [item["topic"] for item in TOPIC_LIBRARY]
    topic_name = _avoid_recent(available_topics, history.get("topics", []), rng, recent_window=6)
    format_name = _avoid_recent(FORMATS, history.get("formats", []), rng, recent_window=4)

    topic_data = next(item for item in TOPIC_LIBRARY if item["topic"] == topic_name)
    return topic_data, format_name, history


def _number_from_text(text: str, start: int, end: int) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    n = int(digest[:8], 16)
    return start + (n % (end - start + 1))


def _hook(topic_data: Dict[str, str], format_name: str) -> str:
    topic = topic_data["topic"]
    templates = {
        "money_mistake": [
            "Most people lose money here: {mistake}.",
            "Quick reality check: this mistake keeps salaries feeling small.",
        ],
        "myth_vs_reality": [
            "Money myth in one line: {myth}.",
            "This finance myth sounds smart, but hurts your future.",
        ],
        "quick_tip": [
            "Try this 30-second money move today.",
            "One simple tweak can fix your cash flow this month.",
        ],
        "comparison": [
            "Two money paths, same income, very different outcome.",
            "This small choice quietly decides if you build wealth.",
        ],
        "rich_vs_poor_habit": [
            "One habit gap separates progress from paycheck stress.",
            "Rich habit vs poor habit, same salary.",
        ],
        "money_alert": [
            "Money alert: this risk looks harmless until it is expensive.",
            "If you ignore this, your future self pays the bill.",
        ],
        "simple_explainer": [
            "Let me explain {concept} without finance jargon.",
            "In plain words, this concept changes how fast money grows.",
        ],
        "mini_case": [
            "Real mini case, real numbers, real lesson.",
            "A quick story that shows why systems beat motivation.",
        ],
        "money_curiosity": [
            "Finance curiosity that can save you years.",
            "Most people hear this too late.",
        ],
    }
    seed_rng = _rng(f"hook:{topic}:{format_name}")
    raw = seed_rng.choice(templates[format_name])
    return raw.format(**topic_data)


def _body_short(topic_data: Dict[str, str], format_name: str) -> str:
    topic = topic_data["topic"]
    seed = f"{topic}:{format_name}"
    example_value = _number_from_text(seed, 80, 900)
    months = _number_from_text(seed + ":m", 6, 24)

    blocks = {
        "money_mistake": [
            f"Topic: {topic}.",
            f"The common mistake is {topic_data['mistake']}.",
            f"Simple fix: {topic_data['quick_tip']}.",
            f"Example: redirect {example_value} euros monthly for {months} months and you build a real safety buffer.",
            "Small systems beat random motivation every time.",
        ],
        "myth_vs_reality": [
            f"Topic: {topic}.",
            f"Myth: {topic_data['myth']}.",
            f"Reality: {topic_data['reality']}.",
            f"Practical move: {topic_data['quick_tip']}.",
            "Do not chase perfect plans, chase repeatable actions.",
        ],
        "quick_tip": [
            f"Topic: {topic}.",
            f"Do this: {topic_data['quick_tip']}.",
            "Set it once, then let automation carry the habit.",
            f"This one move can protect around {example_value} euros this year if you stay consistent.",
            "Easy to start, hard to regret.",
        ],
        "comparison": [
            f"Topic: {topic}.",
            f"Comparison: {topic_data['comparison']}.",
            "Path A feels easier today, Path B pays you back later.",
            f"After {months} months, the disciplined path usually creates visible momentum.",
            "Choose the system that works when motivation is low.",
        ],
        "rich_vs_poor_habit": [
            f"Topic: {topic}.",
            f"Rich habit: {topic_data['rich_habit']}.",
            f"Poor habit: {topic_data['poor_habit']}.",
            f"If you switch just this behavior, you can free up around {example_value} euros per month over time.",
            "Wealth is mostly behavior repeated for years.",
        ],
        "money_alert": [
            f"Topic: {topic}.",
            f"Alert: {topic_data['alert']}.",
            f"Protection plan: {topic_data['quick_tip']}.",
            f"One ignored risk can cost more than {example_value} euros unexpectedly.",
            "Defensive money habits are not boring, they are freedom.",
        ],
        "simple_explainer": [
            f"Topic: {topic_data['concept']}.",
            f"Simple explanation: {topic_data['concept']} is the rule behind {topic.lower()} progress.",
            f"In practice: {topic_data['quick_tip']}.",
            f"In {months} months, consistency matters more than intense one-off effort.",
            "Think less prediction, more repetition.",
        ],
        "mini_case": [
            f"Topic: {topic}.",
            f"Case: {topic_data['case']}.",
            f"What changed: {topic_data['quick_tip']}.",
            f"Result after {months} months: less stress and roughly {example_value} euros preserved or invested.",
            "Stories like this are built with small weekly decisions.",
        ],
        "money_curiosity": [
            f"Topic: {topic}.",
            f"Curiosity: {topic_data['curiosity']}.",
            f"Useful takeaway: {topic_data['quick_tip']}.",
            f"Tiny repeated actions can swing outcomes by hundreds of euros per year, often around {example_value} or more.",
            "The edge is consistency, not complexity.",
        ],
    }

    lines = blocks[format_name]
    return "\n".join(lines)


def _compose_short(topic_data: Dict[str, str], format_name: str) -> Tuple[str, str, str]:
    hook = _hook(topic_data, format_name)
    body = _body_short(topic_data, format_name)
    cta = _rng(f"cta:{topic_data['topic']}").choice(CTA_OPTIONS)

    title = f"{topic_data['topic']}: {format_name.replace('_', ' ').title()}"
    script = "\n".join([hook, body, cta])
    tags = "#shorts #money #personalfinance #investing #wealthbuilding"
    return title, script, tags


def _compose_long() -> Tuple[str, str, str]:
    parts: List[str] = []
    used_topics: List[str] = []
    used_formats: List[str] = []

    for idx in range(6):
        topic_data, format_name, _ = _pick_topic_and_format(mode=f"long:{idx}")
        used_topics.append(topic_data["topic"])
        used_formats.append(format_name)
        hook = _hook(topic_data, format_name)
        body = _body_short(topic_data, format_name)
        parts.append(f"Lesson {idx + 1}\n{hook}\n{body}")

    title = "Silent Money Blueprint: Weekly Finance Systems"
    outro = "If you want daily short versions, follow for one practical move each day."
    script = "\n\n---\n\n".join(parts) + "\n\n" + outro
    tags = "#money #personalfinance #investing #wealthbuilding"

    history = _load_history()
    history.setdefault("topics", []).extend(used_topics)
    history.setdefault("formats", []).extend(used_formats)
    history.setdefault("hooks", []).extend([p.splitlines()[1] for p in parts if len(p.splitlines()) > 1])
    _save_history(history)

    return title, script, tags


def make_short() -> Tuple[str, str, str]:
    topic_data, format_name, history = _pick_topic_and_format(mode="short")
    title, script, tags = _compose_short(topic_data, format_name)

    history.setdefault("topics", []).append(topic_data["topic"])
    history.setdefault("formats", []).append(format_name)
    history.setdefault("hooks", []).append(script.splitlines()[0])
    _save_history(history)

    return title, script, tags


def make_long() -> Tuple[str, str, str]:
    return _compose_long()
