import argparse
import atexit
import csv
import json
import os
import sys
import tempfile
import time
from collections import Counter, defaultdict
from operator import add

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Spark's Windows launcher runs worker commands through the shell. A small
# wrapper outside the project path avoids both shell splitting and fallback to
# the Python executable on PATH when the project directory contains spaces.
PYTHON_EXECUTABLE = os.path.abspath(sys.executable)
PYTHON_WORKER = PYTHON_EXECUTABLE
if os.name == "nt" and " " in PYTHON_EXECUTABLE:
    PYTHON_WORKER = os.path.join(tempfile.gettempdir(), "productpulse-python-%d.cmd" % os.getpid())
    with open(PYTHON_WORKER, "w", encoding="ascii") as wrapper:
        wrapper.write('@echo off\r\ncall "%s" %%*\r\n' % PYTHON_EXECUTABLE)
    atexit.register(lambda: os.path.exists(PYTHON_WORKER) and os.remove(PYTHON_WORKER))
os.environ["PYSPARK_PYTHON"] = PYTHON_WORKER
os.environ["PYSPARK_DRIVER_PYTHON"] = PYTHON_EXECUTABLE
os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"
os.environ["PYTHONPATH"] = ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")

from backend import spark_compat

SERIALIZER = spark_compat.apply()

from pyspark.sql import SparkSession, Window, functions as F, types as T

import config
from backend import nlp_engine as nlp

LABELS = ["positive", "negative", "neutral", "mixed"]
STAGES = ["Reading rows", "Cleaning text", "Analysing sentiment and features", "Aggregating products", "Finding keywords", "Building summaries"]
RESULT = T.StructType([
    T.StructField("score", T.DoubleType()), T.StructField("label", T.StringType()), T.StructField("category", T.StringType()),
    T.StructField("aspects", T.ArrayType(T.StructType([T.StructField("category", T.StringType()), T.StructField("score", T.DoubleType())])))])


def analyse_text(text):
    s = nlp.sentiment(text)
    return (s["score"], s["label"], nlp.categorize(text), [(a["category"], a["score"]) for a in nlp.aspects(text)])


def stage(i):
    print("STAGE|%d|%d|%s" % (i, len(STAGES), STAGES[i - 1]), flush=True)


def rows(df):
    return [r.asDict() for r in df.collect()]


def run_python(input_path, out_dir, has_dates, has_id):
    """Run the same analytics without a PySpark Python worker on Windows 3.14."""
    started = time.time()
    stage(1)
    with open(input_path, newline="", encoding="utf-8") as f:
        source = list(csv.DictReader(f))
    rows_read = len(source)

    stage(2)
    cleaned, seen = [], set()
    for row in source:
        text, product = row.get("text") or "", row.get("product") or ""
        clean_text = nlp.clean(text)
        if not text or not product or len(clean_text) < 10:
            continue
        key = (product, clean_text, row.get("rating", ""), row.get("date", "")) + ((row.get("review_id", ""),) if has_id else ())
        if key in seen:
            continue
        seen.add(key)
        row = dict(row)
        row["clean_text"] = clean_text
        cleaned.append(row)
    after_short = sum(bool(row.get("text") and row.get("product") and len(nlp.clean(row.get("text"))) >= 10) for row in source)

    stage(3)
    analysed = []
    for row in cleaned:
        sent = nlp.sentiment(row["text"])
        aspects = [{"category": a["category"], "score": a["score"]} for a in nlp.aspects(row["text"])]
        analysed.append({**row, "score": sent["score"], "sentiment": sent["label"], "category": nlp.categorize(row["text"]), "aspects": aspects})
    total = len(analysed)

    stage(4)
    products, by_product = [], defaultdict(list)
    for row in analysed:
        by_product[row["product"]].append(row)
    labels = ["positive", "negative", "neutral", "mixed"]
    for product in sorted(by_product):
        group = by_product[product]
        counts = Counter(row["sentiment"] for row in group)
        scores = [row["score"] for row in group]
        ratings = [float(row["rating"]) for row in group if row.get("rating")]
        item = {"product": product, "total": len(group), **{label: counts[label] for label in labels},
                "avg_score": round(sum(scores) / len(scores), 3), "avg_length": round(sum(len(row["text"]) for row in group) / len(group), 1),
                "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None}
        for label in labels:
            item[label + "_pct"] = round(100.0 * item[label] / item["total"], 1)
        products.append(item)
    overall_counts = Counter(row["sentiment"] for row in analysed)
    avg = sum(row["score"] for row in analysed) / total if total else 0
    feature_rows = []
    category_by_product = []
    for product, group in by_product.items():
        feature_scores = defaultdict(list)
        for row in group:
            for aspect in row["aspects"]:
                feature_scores[aspect["category"]].append(aspect["score"])
        for category, scores in feature_scores.items():
            item = {"product": product, "category": category, "count": len(scores), "avg_score": round(sum(scores) / len(scores), 3)}
            category_by_product.append(item)
            feature_rows.append({"category": category, "count": len(scores), "avg_score": item["avg_score"]})
    categories = []
    for category in sorted({row["category"] for row in category_by_product}):
        scores = [aspect["score"] for group in by_product.values() for review in group for aspect in review["aspects"] if aspect["category"] == category]
        categories.append({"category": category, "count": len(scores), "avg_score": round(sum(scores) / len(scores), 3)})
    categories.sort(key=lambda item: (-item["count"], item["category"]))
    leaderboard = [{"product": item["product"], "n": item["total"], "avg_score": item["avg_score"], "pos_pct": item["positive_pct"]}
                   for item in sorted(products, key=lambda item: (-item["avg_score"], item["product"]))]
    no_aspect = sum(not row["aspects"] for row in analysed)
    trends, category_trends = [], []
    for product, group in by_product.items():
        buckets = defaultdict(list)
        for index, row in enumerate(group, 1):
            period = row.get("date", "")[:7] if has_dates else "Group %d" % (int((index - 1) * 5 / len(group)) + 1)
            buckets[period].append(row)
        for period, bucket in sorted(buckets.items()):
            trends.append({"product": product, "period": period, "count": len(bucket), "avg_score": round(sum(r["score"] for r in bucket) / len(bucket), 3),
                           "positive": sum(r["sentiment"] == "positive" for r in bucket), "negative": sum(r["sentiment"] == "negative" for r in bucket)})
    feature_buckets = defaultdict(list)
    for row in analysed:
        period = row.get("date", "")[:7] if has_dates else "Group 1"
        for aspect in row["aspects"]:
            feature_buckets[(period, aspect["category"])].append(aspect["score"])
    for (period, category), scores in sorted(feature_buckets.items()):
        category_trends.append({"period": period, "category": category, "count": len(scores), "avg_score": round(sum(scores) / len(scores), 3)})

    stage(5)
    kw, global_words = {}, Counter()
    for product, group in by_product.items():
        counter = Counter(word for row in group for word in nlp.remove_stopwords(nlp.tokenize(row["clean_text"])))
        kw[product] = [{"word": word, "count": count} for word, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:10]]
        global_words.update(counter)
    pc = {}
    for product, group in by_product.items():
        good = [row for row in group if 25 < len(row["text"]) < 220]
        pc[product] = {"pros": [{"text": row["text"], "score": row["score"], "category": row["category"]} for row in sorted(good, key=lambda row: -row["score"]) if row["sentiment"] == "positive"][:3],
                       "cons": [{"text": row["text"], "score": row["score"], "category": row["category"]} for row in sorted(good, key=lambda row: row["score"]) if row["sentiment"] == "negative"][:3]}

    stage(6)
    summaries = {}
    for item in products:
        feats = [row for row in category_by_product if row["product"] == item["product"]]
        text, best, worst = nlp.product_summary(item["product"], item["total"], item["positive_pct"], item["negative_pct"], item["avg_score"], feats, [row["word"] for row in kw.get(item["product"], [])])
        summaries[item["product"]] = {"text": text, "strengths": best, "complaints": worst}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "processed.csv.tmp"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["review_id", "product", "text", "clean_text", "score", "sentiment", "category", "rating", "date"])
        for row in analysed[:config.PREVIEW_CAP]:
            writer.writerow([row.get(k, "") for k in ["review_id", "product", "text", "clean_text", "score", "sentiment", "category", "rating", "date"]])
    os.replace(os.path.join(out_dir, "processed.csv.tmp"), os.path.join(out_dir, "processed.csv"))
    result = {"spark": {"rows_read": rows_read, "too_short_removed": rows_read - after_short, "duplicates_removed": after_short - total,
                        "analysed": total, "seconds": round(time.time() - started, 1), "version": "python-fallback", "serializer": SERIALIZER,
                        "processed_rows_saved": min(total, config.PREVIEW_CAP)},
              "overall": {**{label: overall_counts[label] for label in labels}, "total": total, "avg_score": round(avg, 3),
                          "products": len(products), "label": "positive" if avg >= 0.1 else "negative" if avg <= -0.1 else "neutral/mixed",
                          "top_feature": categories[0]["category"] if categories else "None"},
              "products": products, "leaderboard": leaderboard, "categories": categories, "no_feature_comments": no_aspect,
              "category_by_product": category_by_product, "trends": trends, "category_trends": category_trends,
              "time_based": bool(has_dates), "pros_cons": pc, "keywords_by_product": kw,
              "keywords_global": [{"word": word, "count": count} for word, count in sorted(global_words.items(), key=lambda item: (-item[1], item[0]))[:25]],
              "summaries": summaries}
    with open(os.path.join(out_dir, "analytics.json.tmp"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    os.replace(os.path.join(out_dir, "analytics.json.tmp"), os.path.join(out_dir, "analytics.json"))
    print("DONE", flush=True)


def run(input_path, out_dir, has_dates, has_id):
    if os.name == "nt" and sys.version_info >= (3, 14):
        return run_python(input_path, out_dir, has_dates, has_id)
    started = time.time()
    spark = (SparkSession.builder.master("local[*]").appName("ProductPulse")
             .config("spark.sql.shuffle.partitions", "8").config("spark.ui.enabled", "false").config("spark.ui.showConsoleProgress", "false")
             .config("spark.driver.bindAddress", "127.0.0.1").config("spark.driver.host", "127.0.0.1")
             .config("spark.pyspark.python", PYTHON_WORKER)
             .config("spark.pyspark.driver.python", PYTHON_EXECUTABLE).getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    stage(1)
    raw = spark.read.option("header", True).option("multiLine", True).option("quote", '"').option("escape", '"').csv(input_path)
    raw = raw.withColumn("row_no", F.col("row_no").cast("int"))
    rows_read = raw.count()

    stage(2)
    cleaned = (raw.filter(F.col("text").isNotNull() & F.col("product").isNotNull())
               .withColumn("clean_text", F.lower("text"))
               .withColumn("clean_text", F.regexp_replace("clean_text", r"https?://\S+|www\.\S+", " "))
               .withColumn("clean_text", F.regexp_replace("clean_text", r"<[^>]+>", " "))
               .withColumn("clean_text", F.regexp_replace("clean_text", r"[^a-z0-9' ]", " "))
               .withColumn("clean_text", F.trim(F.regexp_replace("clean_text", r"\s+", " ")))
               .filter(F.length("clean_text") >= 10))
    after_short = cleaned.count()
    keys = ["product", "clean_text", "rating", "date"] + (["review_id"] if has_id else [])
    key = Window.partitionBy(*keys).orderBy("row_no")
    cleaned = cleaned.withColumn("dup", F.row_number().over(key)).filter("dup = 1").drop("dup")

    stage(3)
    analyse = F.udf(analyse_text, RESULT)
    df = (cleaned.withColumn("a", analyse("text"))
          .select("row_no", "review_id", "product", "text", "clean_text", "rating", "date",
                  F.col("a.score").alias("score"), F.col("a.label").alias("sentiment"), F.col("a.category").alias("category"), F.col("a.aspects").alias("aspects"))
          .withColumn("rating_num", F.col("rating").cast("double")).cache())
    total = df.count()

    stage(4)
    cnt = lambda lab: F.sum(F.when(F.col("sentiment") == lab, 1).otherwise(0)).alias(lab)
    overall = df.agg(*[cnt(l) for l in LABELS], F.avg("score").alias("avg_score"), F.countDistinct("product").alias("products")).first().asDict()
    products = rows(df.groupBy("product").agg(F.count("*").alias("total"), *[cnt(l) for l in LABELS], F.round(F.avg("score"), 3).alias("avg_score"),
                                              F.round(F.avg(F.length("text")), 1).alias("avg_length"), F.round(F.avg("rating_num"), 2).alias("avg_rating")).orderBy(F.desc("total"), "product"))
    for p in products:
        for l in LABELS:
            p[l + "_pct"] = round(100.0 * p[l] / p["total"], 1)
    asp = df.select("product", F.explode("aspects").alias("a")).select("product", F.col("a.category").alias("category"), F.col("a.score").alias("score"))
    cat_by_product = rows(asp.groupBy("product", "category").agg(F.count("*").alias("count"), F.round(F.avg("score"), 3).alias("avg_score")))
    categories = rows(asp.groupBy("category").agg(F.count("*").alias("count"), F.round(F.avg("score"), 3).alias("avg_score")).orderBy(F.desc("count")))
    no_aspect = df.filter(F.size("aspects") == 0).count()
    df.createOrReplaceTempView("comments")
    leaderboard = rows(spark.sql("SELECT product, COUNT(*) AS n, ROUND(AVG(score),3) AS avg_score, "
                                 "ROUND(100*AVG(CASE WHEN sentiment='positive' THEN 1 ELSE 0 END),1) AS pos_pct "
                                 "FROM comments GROUP BY product ORDER BY avg_score DESC, product"))
    if has_dates:
        per = df.withColumn("period", F.date_format(F.to_date("date"), "yyyy-MM")).filter(F.col("period").isNotNull())
    else:
        w = Window.partitionBy("product").orderBy("row_no")
        per = (df.withColumn("rn", F.row_number().over(w)).withColumn("n", F.count("*").over(Window.partitionBy("product")))
               .withColumn("period", F.concat(F.lit("Group "), (F.floor((F.col("rn") - 1) * 5 / F.col("n")) + 1).cast("string"))))
    trends = rows(per.groupBy("product", "period").agg(F.count("*").alias("count"), F.round(F.avg("score"), 3).alias("avg_score"), cnt("positive"), cnt("negative")).orderBy("product", "period"))
    cat_trends = rows(per.select("period", F.explode("aspects").alias("a")).select("period", F.col("a.category").alias("category"), F.col("a.score").alias("score"))
                      .groupBy("period", "category").agg(F.count("*").alias("count"), F.round(F.avg("score"), 3).alias("avg_score")).orderBy("period", "category"))

    good = df.filter((F.length("text") > 25) & (F.length("text") < 220))
    pc = {}
    for order, lab, kind in ((F.desc("score"), "positive", "pros"), (F.asc("score"), "negative", "cons")):
        ranked = good.filter(F.col("sentiment") == lab).withColumn("r", F.row_number().over(Window.partitionBy("product").orderBy(order, "row_no")))
        for r in rows(ranked.filter("r <= 3").select("product", "text", "score", "category")):
            pc.setdefault(r["product"], {"pros": [], "cons": []})[kind].append({"text": r["text"], "score": r["score"], "category": r["category"]})

    stage(5)
    stop = sorted(nlp.STOPWORDS)
    words = (df.select("product", F.explode(F.split("clean_text", " ")).alias("word")).withColumn("word", F.regexp_replace("word", "'", ""))
             .filter((F.length("word") > 2) & F.col("word").rlike("^[a-z]+$") & ~F.col("word").isin(stop)))
    rank = Window.partitionBy("product").orderBy(F.desc("count"), "word")
    kw = {}
    for r in rows(words.groupBy("product", "word").count().withColumn("r", F.row_number().over(rank)).filter("r <= 10").select("product", "word", "count")):
        kw.setdefault(r["product"], []).append({"word": r["word"], "count": r["count"]})
    rdd = (df.select("clean_text").rdd.flatMap(lambda r: nlp.remove_stopwords(nlp.tokenize(r[0]))).map(lambda w: (w, 1)).reduceByKey(add)
           .takeOrdered(25, key=lambda x: (-x[1], x[0])))

    stage(6)
    summaries = {}
    for p in products:
        feats = [c for c in cat_by_product if c["product"] == p["product"]]
        text, best, worst = nlp.product_summary(p["product"], p["total"], p["positive_pct"], p["negative_pct"], p["avg_score"], feats, [k["word"] for k in kw.get(p["product"], [])])
        summaries[p["product"]] = {"text": text, "strengths": best, "complaints": worst}

    os.makedirs(out_dir, exist_ok=True)
    saved = 0
    with open(os.path.join(out_dir, "processed.csv.tmp"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "product", "text", "clean_text", "score", "sentiment", "category", "rating", "date"])
        for r in df.orderBy("row_no").select("review_id", "product", "text", "clean_text", "score", "sentiment", "category", "rating", "date").limit(config.PREVIEW_CAP).toLocalIterator():
            w.writerow(list(r))
            saved += 1
    os.replace(os.path.join(out_dir, "processed.csv.tmp"), os.path.join(out_dir, "processed.csv"))
    feature_rows = [c for c in categories]
    avg = overall["avg_score"] or 0.0
    result = {
        "spark": {"rows_read": rows_read, "too_short_removed": rows_read - after_short, "duplicates_removed": after_short - total, "analysed": total,
                  "seconds": round(time.time() - started, 1), "version": spark.version, "serializer": SERIALIZER, "processed_rows_saved": saved},
        "overall": {**{l: overall[l] or 0 for l in LABELS}, "total": total, "avg_score": round(avg, 3), "products": overall["products"],
                    "label": "positive" if avg >= 0.1 else "negative" if avg <= -0.1 else "neutral/mixed", "top_feature": feature_rows[0]["category"] if feature_rows else "None"},
        "products": products, "leaderboard": leaderboard, "categories": categories, "no_feature_comments": no_aspect, "category_by_product": cat_by_product,
        "trends": trends, "category_trends": cat_trends, "time_based": bool(has_dates), "pros_cons": pc, "keywords_by_product": kw,
        "keywords_global": [{"word": w, "count": c} for w, c in rdd], "summaries": summaries,
    }
    with open(os.path.join(out_dir, "analytics.json.tmp"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    os.replace(os.path.join(out_dir, "analytics.json.tmp"), os.path.join(out_dir, "analytics.json"))
    spark.stop()
    print("DONE", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--has-dates", action="store_true")
    ap.add_argument("--has-id", action="store_true")
    a = ap.parse_args()
    run(a.input, a.out, a.has_dates, a.has_id)
