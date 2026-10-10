import re
from collections import Counter

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

STOPWORDS = set("""a about above after again all also am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here hers him his how i if in
into is it its just me more most my no nor not now of off on once only or other our out over own same she should so some such than
that the their them then there these they this those through to too under until up very was we were what when where which while who
whom why will with would you your yours get got one two thing things really much even still ive im dont didnt doesnt isnt wasnt
cant couldnt wont s t""".split())

CATEGORIES = {
    "Battery": "battery batteries charge charger charging charged recharge rechargeable power life aa",
    "Camera": "camera cameras picture pictures photo photos lens zoom flash megapixel image images video shot shots focus resolution shutter",
    "Display": "screen display lcd backlight brightness viewfinder monitor",
    "Performance": "fast slow speed performance lag laggy freeze freezes processor memory boot quick quickly transfer reliable crash crashes crashed",
    "Design": "design size weight light compact look looks style small sleek button buttons shape color",
    "Price": "price cost cheap expensive money value worth deal priced pay paid overpriced",
    "Software": "software firmware driver drivers install installed update upgrade interface menu menus program setup application settings",
    "Build Quality": "build plastic sturdy durable broke broken flimsy solid material warranty defect repair return replaced metal",
    "Audio": "sound audio music headphone headphones speaker bass volume playback song songs earphone mp3 equalizer",
}
FEATURES = list(CATEGORIES)
KEYWORD_TO_CATEGORY = {w: c for c, ws in CATEGORIES.items() for w in ws.split()}

DOMAIN_LEXICON = {"drains": -1.8, "drain": -1.5, "drained": -1.5, "crashes": -2.0, "crashed": -2.0, "freezes": -1.8, "laggy": -1.8,
                  "sluggish": -1.8, "flimsy": -1.8, "overpriced": -1.8, "okay": 0.0, "ok": 0.0, "average": 0.0, "mediocre": -0.8}
_analyzer = SentimentIntensityAnalyzer()
_analyzer.lexicon.update(DOMAIN_LEXICON)

POS_T, NEG_T = 0.1, -0.1
CLAUSE_T = 0.3
_SPLIT = re.compile(r"[.!?;\n]+|\b(?:but|however|although|though|whereas|except)\b", re.I)


def clean(text):
    text = str(text or "").lower()
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9' ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text):
    return [t for t in clean(text).replace("'", "").split(" ") if t]


def remove_stopwords(tokens):
    return [t for t in tokens if t not in STOPWORDS and len(t) > 2 and t.isalpha()]


def raw_score(text):
    return _analyzer.polarity_scores(str(text or ""))["compound"]


def clauses(text):
    return [c.strip(" ,:-") for c in _SPLIT.split(str(text or "")) if c and len(c.strip(" ,:-")) > 3]


def sentiment(text):
    text = str(text or "").strip()
    if not text:
        return {"score": 0.0, "label": "neutral"}
    parts = clauses(text)
    scores = [raw_score(p) for p in parts] if len(parts) > 1 else []
    if scores and max(scores) >= CLAUSE_T and min(scores) <= -CLAUSE_T:
        return {"score": round(sum(scores) / len(scores), 4), "label": "mixed"}
    s = raw_score(text)
    return {"score": round(s, 4), "label": "positive" if s >= POS_T else "negative" if s <= NEG_T else "neutral"}


def sentiment_score(text):
    return sentiment(text)["score"]


def sentiment_label(score):
    return "positive" if score >= POS_T else "negative" if score <= NEG_T else "neutral"


def categorize_text(text):
    hits = Counter(KEYWORD_TO_CATEGORY[t] for t in tokenize(text) if t in KEYWORD_TO_CATEGORY)
    return hits.most_common(1)[0][0] if hits else None


def aspects(text):
    out = []
    for p in clauses(text) or [str(text or "")]:
        c = categorize_text(p)
        if c:
            out.append({"category": c, "score": round(raw_score(p), 4)})
    return out


def categorize(text):
    asp = aspects(text)
    if not asp:
        return "Other"
    return Counter(a["category"] for a in asp).most_common(1)[0][0]


def keywords(text, n=5):
    return [w for w, _ in Counter(remove_stopwords(tokenize(text))).most_common(n)]


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if len(s.strip()) > 10]


def review_summary(text, sent, asp):
    pos = sorted({a["category"] for a in asp if a["score"] >= CLAUSE_T})
    neg = sorted({a["category"] for a in asp if a["score"] <= -CLAUSE_T})
    bits = ["Overall tone: %s." % sent["label"]]
    if pos:
        bits.append("Praises: %s." % ", ".join(pos))
    if neg:
        bits.append("Criticises: %s." % ", ".join(neg))
    if not pos and not neg:
        bits.append("No strong opinion about a specific feature.")
    return " ".join(bits)


def analyze(text):
    sent = sentiment(text)
    toks = tokenize(text)
    asp = aspects(text)
    return {
        "original": text, "cleaned": clean(text), "tokens": toks, "tokens_without_stopwords": remove_stopwords(toks),
        "sentiment": sent["label"], "score": sent["score"],
        "category": categorize(text), "keywords": keywords(text),
        "aspects": asp,
        "clauses": [{"text": c, "score": round(raw_score(c), 3), "label": sentiment_label(raw_score(c)), "category": categorize_text(c) or "Other"} for c in (clauses(text) or [str(text)])],
        "opinion_words": [{"word": t, "valence": _analyzer.lexicon[t]} for t in toks if _analyzer.lexicon.get(t)],
        "summary": review_summary(text, sent, asp),
    }


def _join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def product_summary(name, total, pos_pct, neg_pct, avg_score, features, keywords_):
    """features: list of dicts {category, count, avg_score}"""
    solid = [f for f in features if f["count"] >= max(3, 0.02 * total)]
    best = [f["category"].lower() for f in sorted(solid, key=lambda f: -f["avg_score"]) if f["avg_score"] >= 0.15][:2]
    worst = [f["category"].lower() for f in sorted(solid, key=lambda f: f["avg_score"]) if f["avg_score"] <= 0.05 and f["category"].lower() not in best][:2]
    busy = [f["category"].lower() for f in sorted(features, key=lambda f: -f["count"])][:3]
    tone = "mostly positive" if avg_score >= 0.15 else "mostly negative" if avg_score <= -0.05 else "mixed"
    parts = ["Customer opinion about %s is %s: %.0f%% of %d reviews are positive and %.0f%% are negative." % (name, tone, pos_pct, total, neg_pct)]
    if best:
        parts.append("Customers appreciate its %s." % _join(best))
    if worst:
        parts.append("The most common concerns relate to %s." % _join(worst))
    if busy:
        parts.append("The most discussed features are %s." % _join(busy))
    if keywords_:
        parts.append("Frequently mentioned words include %s." % _join(keywords_[:4]))
    return " ".join(parts), best, worst
