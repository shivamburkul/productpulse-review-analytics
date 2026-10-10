import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend import nlp_engine as nlp

S = os.path.join(ROOT, "sample_csv")
rows = list(csv.DictReader(open(os.path.join(S, "1_sentiment_test_synthetic.csv"), encoding="utf-8")))
ok = sum(nlp.sentiment(r["review_text"])["label"] == r["expected_sentiment"] for r in rows)
print("Synthetic labelled test set: %d/%d correct (%.1f%%)" % (ok, len(rows), 100 * ok / len(rows)))
for r in rows:
    got = nlp.sentiment(r["review_text"])["label"]
    if got != r["expected_sentiment"]:
        print("  wrong: expected %-8s got %-8s | %s" % (r["expected_sentiment"], got, r["review_text"]))
real = [r for r in csv.DictReader(open(os.path.join(S, "4_real_amazon_reviews_full.csv"), encoding="utf-8")) if r["human_label"] in ("positive", "negative")]
pred = [(nlp.sentiment(r["review_text"])["label"], r["human_label"]) for r in real]
decided = [(p, h) for p, h in pred if p in ("positive", "negative")]
print("Real reviews with a human positive/negative label: %d" % len(real))
print("  classifier gave positive/negative for %.1f%%; of those %.1f%% agree with the human label" % (100 * len(decided) / len(pred), 100 * sum(p == h for p, h in decided) / len(decided)))
print("  strict agreement (neutral/mixed counted as wrong): %.1f%%" % (100 * sum(p == h for p, h in pred) / len(pred)))
