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

def make_short():
    rng = random.Random()
    rng.seed(datetime.utcnow().strftime("%Y-%m-%d-%H"))  # muda todos os posts

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

    tags = "#money #wealth #investing #personalfinance #shorts"
    return title, body, tags

def make_long():
    # Long: 6–8 min (junta 6 shorts num só)
    titles = []
    parts = []
    for _ in range(6):
        t, b, _ = make_short()
        titles.append(t)
        parts.append(b)

    title = "Silent Money Blueprint — Weekly Money Systems (6 Lessons)"
    body = "\n\n---\n\n".join(parts)
    tags = "#money #wealth #investing #personalfinance"
    return title, body, tags
