import os
import random
from datetime import datetime


TOPICS = [
    "Money rain: why cash flow beats hustle",
    "The 3 silent habits of wealthy people",
    "ETF myth that keeps people broke",
    "Why most budgets fail (and what works)",
    "The 'one account' rule for saving fast",
    "Stop buying motivation. Build systems.",
    "The 2% rule that compounds your life",
    "Rich people protect attention, not time",
    "Lifestyle inflation: the invisible tax",
    "How to automate wealth in 15 minutes",
]

HOOKS = [
    "Here’s the truth nobody tells you:",
    "If you want money to grow quietly, do this:",
    "This is why most people stay broke:",
    "If your paycheck disappears, listen:",
    "This single shift changes everything:",
]

CTA = [
    "Follow Silent Money Blueprint for daily systems.",
    "Save this and watch it again tomorrow.",
    "Comment 'BLUEPRINT' and I’ll drop a checklist.",
    "Share this with someone who needs structure.",
]


def _rng_seed() -> str:
    """
    Evita repetição:
    - Em GitHub Actions, usa GITHUB_RUN_ID (único por execução)
    - Fora disso, usa minuto UTC (muda a cada minuto)
    """
    run_id = os.getenv("GITHUB_RUN_ID")
    if run_id:
        return run_id
    return datetime.utcnow().strftime("%Y-%m-%d-%H-%M")


def make_short():
    rng = random.Random()
    rng.seed(_rng_seed())

    topic = rng.choice(TOPICS)
    hook = rng.choice(HOOKS)
    cta = rng.choice(CTA)

    title = topic.replace(":", " —").strip()

    body = (
        f"{hook} {topic}.\n\n"
        "Most people chase motivation, but motivation expires.\n"
        "Systems don’t.\n\n"
        "Automate saving first.\n"
        "Cap lifestyle inflation.\n"
        "Invest consistently.\n"
        "Let compounding do the heavy lifting.\n\n"
        f"{cta}"
    )

    # Shorts: põe #shorts no início para ajudar a classificar
    tags = "#shorts #money #wealth #investing #personalfinance"
    return title, body, tags


def make_long():
    # Long: 6–8 min (junta 6 shorts num só)
    # Para não repetir as mesmas 6 peças, fixa um seed por execução e avança por índice.
    rng = random.Random()
    base_seed = _rng_seed()
    rng.seed(base_seed)

    parts = []
    for i in range(6):
        # “salta” o RNG um pouco para variar mais entre partes
        rng.seed(f"{base_seed}-{i}")

        topic = rng.choice(TOPICS)
        hook = rng.choice(HOOKS)
        cta = rng.choice(CTA)

        part = (
            f"{hook} {topic}.\n\n"
            "Most people chase motivation, but motivation expires.\n"
            "Systems don’t.\n\n"
            "Automate saving first.\n"
            "Cap lifestyle inflation.\n"
            "Invest consistently.\n"
            "Let compounding do the heavy lifting.\n\n"
            f"{cta}"
        )
        parts.append(part)

    title = "Silent Money Blueprint — Weekly Money Systems (6 Lessons)"
    body = "\n\n---\n\n".join(parts)
    tags = "#money #wealth #investing #personalfinance"
    return title, body, tags
