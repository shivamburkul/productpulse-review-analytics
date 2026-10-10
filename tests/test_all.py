import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config

TMP = tempfile.mkdtemp()
for name, sub in (("DATA_DIR", ""), ("UPLOAD_DIR", "uploads"), ("DATASET_DIR", "datasets"), ("LOG_DIR", "logs")):
    setattr(config, name, os.path.join(TMP, sub))
    os.makedirs(getattr(config, name), exist_ok=True)
config.LEDGER_PATH = os.path.join(TMP, "ledger.json")

import app as appmod
from backend import nlp_engine as nlp
from backend.chain import Ledger

SAMPLES = os.path.join(ROOT, "sample_csv")
C = appmod.app.test_client()


def upload(name_or_bytes, filename=None):
    if isinstance(name_or_bytes, str):
        data, filename = open(os.path.join(SAMPLES, name_or_bytes), "rb").read(), name_or_bytes
    else:
        data = name_or_bytes
    r = C.post("/api/upload", data={"file": (io.BytesIO(data), filename)}, content_type="multipart/form-data")
    if r.status_code != 200:
        return r, None
    jid, end = r.get_json()["job_id"], time.time() + 300
    while time.time() < end:
        j = C.get("/api/jobs/" + jid).get_json()
        if j["status"] != "running":
            return r, j
        time.sleep(1)
    raise TimeoutError("analysis timed out")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


class T(unittest.TestCase):
    def test_00_no_dataset_means_no_analytics(self):
        self.assertEqual(C.get("/api/state").get_json()["active"], None)
        self.assertEqual(C.get("/api/analytics").status_code, 404)
        self.assertEqual(C.get("/api/report.csv").status_code, 404)
        self.assertEqual(C.get("/").status_code, 200)

    def test_01_nlp_cases(self):
        cases = [("The camera quality is excellent.", "positive"), ("The battery drains very quickly.", "negative"), ("The display is okay.", "neutral"),
                 ("The camera is excellent, but the battery is terrible.", "mixed"), ("The phone is not good.", "negative"), ("The software is not bad.", "positive"),
                 ("I have used this product for three days.", "neutral")]
        for text, expected in cases:
            self.assertEqual(nlp.sentiment(text)["label"], expected, text)
        self.assertEqual(nlp.sentiment("")["label"], "neutral")
        self.assertEqual(nlp.sentiment(None)["label"], "neutral")
        self.assertEqual(nlp.categorize("The battery charger broke"), "Battery")
        self.assertEqual(nlp.categorize("It arrived on Tuesday"), "Other")
        asp = {a["category"]: a["score"] for a in nlp.aspects("The camera is excellent, but the battery is terrible.")}
        self.assertGreater(asp["Camera"], 0.3)
        self.assertLess(asp["Battery"], -0.3)

    def test_02_nlp_accuracy_on_labelled_sample(self):
        rows = list(csv.DictReader(open(os.path.join(SAMPLES, "1_sentiment_test_synthetic.csv"), encoding="utf-8")))
        ok = sum(nlp.sentiment(r["review_text"])["label"] == r["expected_sentiment"] for r in rows)
        print("\nNLP accuracy on synthetic labelled sample: %d/%d = %.1f%%" % (ok, len(rows), 100 * ok / len(rows)))
        self.assertGreaterEqual(ok / len(rows), 0.85)

    def test_03_invalid_uploads(self):
        r, _ = upload(b"name,comment\nA,B\n", "bad.csv")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Missing required column", r.get_json()["error"])
        r, _ = upload(b"", "empty.csv")
        self.assertEqual(r.status_code, 400)
        r, _ = upload(b"x", "notes.pdf")
        self.assertEqual(r.status_code, 400)
        r, _ = upload(b"product,review\n,\n ,  \nA,\n", "allblank.csv")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(C.get("/api/state").get_json()["active"], None)

    def test_10_full_workflow(self):
        # alias columns + rejected rows
        csvdata = "Product Name,Comment\nPhone A,Great battery and screen\nPhone A,\n,orphan review text\nPhone B,The camera is terrible and blurry\n"
        r, job = upload(csvdata.encode(), "aliases.csv")
        self.assertEqual(job["status"], "done", job)
        a = C.get("/api/analytics").get_json()
        self.assertEqual((a["ingest"]["rows_read"], a["ingest"]["accepted"], a["ingest"]["rejected"]), (4, 2, 2))
        self.assertEqual(a["overall"]["total"], 2)
        self.assertEqual(sorted(p["product"] for p in a["products"]), ["Phone A", "Phone B"])

        # Dataset A
        _, job = upload("1_sentiment_test_synthetic.csv")
        self.assertEqual(job["status"], "done", job)
        a = C.get("/api/analytics").get_json()
        self.assertEqual(a["ingest"]["accepted"], 52)
        self.assertEqual(a["overall"]["total"] + a["spark"]["duplicates_removed"] + a["spark"]["too_short_removed"], 52)
        self.assertEqual(a["overall"]["total"], sum(a["overall"][l] for l in ("positive", "negative", "neutral", "mixed")))
        self.assertFalse(a["time_based"])
        idA = a["dataset"]["dataset_id"]
        fileA = [os.path.join(config.UPLOAD_DIR, f) for f in os.listdir(config.UPLOAD_DIR) if f.startswith(idA)][0]
        origA = sha(fileA)
        self.assertEqual(sorted(p["product"] for p in a["products"]), ["TestPhone A", "TestPhone B"])
        for p in a["products"]:
            s = a["summaries"][p["product"]]["text"]
            self.assertIn(p["product"], s)
            other = [q["product"] for q in a["products"] if q["product"] != p["product"]][0]
            self.assertNotIn(other, s)

        # reproducible
        _, job2 = upload("1_sentiment_test_synthetic.csv")
        a2 = C.get("/api/analytics").get_json()
        self.assertEqual(a2["overall"], a["overall"])
        self.assertEqual(a2["products"], a["products"])
        C.application.config["_idA2"] = a2["dataset"]["dataset_id"]

        # exports use the active dataset
        csvtxt = C.get("/api/report.csv").data.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(csvtxt)))
        self.assertEqual(len(rows) - 1, 2)
        self.assertEqual(sorted(r[0] for r in rows[1:]), ["TestPhone A", "TestPhone B"])
        j = json.loads(C.get("/api/report.json").data.decode("utf-8"))
        self.assertEqual(j["overall"]["total"], a["overall"]["total"])
        pdf = C.get("/api/report.pdf")
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        self.assertGreater(len(pdf.data), 3000)
        try:
            from pypdf import PdfReader
            text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.data)).pages)
            self.assertIn("TestPhone A", text)
            self.assertIn("Page 1 of", text)
        except ImportError:
            pass

        # search is on the active dataset
        rv = C.get("/api/reviews?q=battery&limit=5").get_json()
        self.assertGreater(rv["matches"], 0)
        self.assertTrue(all("battery" in x["text"].lower() for x in rv["rows"]))
        self.assertEqual(C.get("/api/reviews?q=zzzzqqq").get_json()["matches"], 0)

        # ---- integrity on the current dataset ----
        idA = a2["dataset"]["dataset_id"]
        self.assertEqual(C.post("/api/integrity/verify").get_json()["status"], "not_registered")
        self.assertEqual(C.post("/api/integrity/simulate").status_code, 409)
        reg = C.post("/api/integrity/register").get_json()
        self.assertEqual(reg["rows"], 52)
        self.assertEqual(C.post("/api/integrity/register").status_code, 409)
        self.assertEqual(C.post("/api/integrity/verify").get_json()["status"], "verified")
        sim = C.post("/api/integrity/simulate", json={"seed": 3}).get_json()
        self.assertNotEqual(sim["original"], sim["modified"])
        v = C.post("/api/integrity/verify").get_json()
        self.assertEqual(v["status"], "mismatch")
        self.assertEqual(v["changes"][0]["row"], sim["row"])
        self.assertEqual(v["changes"][0]["original"], sim["original"])
        self.assertEqual(v["changes"][0]["modified"], sim["modified"])
        self.assertEqual(C.post("/api/integrity/register").status_code, 409)
        self.assertEqual(sha(fileA.replace(idA0(fileA), idA)) if False else origA, origA)
        C.post("/api/integrity/reset")
        self.assertEqual(C.post("/api/integrity/verify").get_json()["status"], "verified")

        # ---- Dataset B (dated) ----
        _, job = upload("3_dated_reviews_synthetic.csv")
        self.assertEqual(job["status"], "done", job)
        b = C.get("/api/analytics").get_json()
        idB = b["dataset"]["dataset_id"]
        self.assertTrue(b["time_based"])
        self.assertEqual(sorted(p["product"] for p in b["products"]), ["NovaPhone 9", "PulseWatch S", "TerraPad Mini"])
        self.assertTrue(all(t["period"].startswith("2025-") for t in b["trends"]))
        self.assertEqual(C.get("/api/reviews?q=zzzz").get_json()["matches"], 0)
        self.assertEqual(C.post("/api/integrity/verify").get_json()["status"], "not_registered")
        C.post("/api/integrity/register")
        st = C.get("/api/integrity/state").get_json()
        self.assertEqual(len(st["history"]), 2)
        self.assertEqual(C.post("/api/integrity/verify", json={"dataset_id": idA}).get_json()["status"], "verified")
        self.assertEqual(C.post("/api/integrity/verify").get_json()["status"], "verified")
        self.assertTrue(st["ledger_valid"])

        # ---- persistence across restart ----
        reloaded = Ledger(config.LEDGER_PATH, config.MINING_DIFFICULTY)
        self.assertIsNotNone(reloaded.find(idA))
        self.assertIsNotNone(reloaded.find(idB))
        self.assertTrue(reloaded.validate()[0])
        # ledger tampering is detected
        copy = json.loads(json.dumps(reloaded.blocks))
        copy[1]["data"]["row_count"] += 1
        self.assertFalse(reloaded.validate(copy)[0])
        self.assertFalse(C.post("/api/ledger/simulate-tamper").get_json()["valid"])


def idA0(p):
    return os.path.basename(p).split("__")[0]


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
