import csv
import copy
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid

from flask import Flask, Response, jsonify, render_template, request

import config
from backend import datasets as ds
from backend import nlp_engine as nlp
from backend import report
from backend.chain import Ledger

app = Flask(__name__, template_folder="frontend/templates", static_folder="frontend/static")
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024
ledger = Ledger(config.LEDGER_PATH, config.MINING_DIFFICULTY)
STATE = {"active": None}
JOBS = {}
LOCK = threading.Lock()
STAGES = ["Validating file", "Reading rows", "Cleaning text", "Analysing sentiment and features", "Aggregating products", "Finding keywords", "Building summaries"]


def err(msg, code=400, **extra):
    return jsonify({"error": msg, **extra}), code


def active_id():
    return STATE["active"]


def load_analytics(dataset_id=None):
    dataset_id = dataset_id or active_id()
    if not dataset_id:
        return None
    p = ds.dataset_path(dataset_id, "analytics.json")
    meta = ds.load_meta(dataset_id)
    if not os.path.exists(p) or not meta:
        return None
    with open(p, encoding="utf-8") as f:
        a = json.load(f)
    a["ingest"] = meta["ingest"]
    a["dataset"] = {k: meta[k] for k in ("dataset_id", "filename", "uploaded_at")}
    return a


def need_active():
    a = load_analytics()
    return a


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def state():
    a = load_analytics()
    job = next((j for j in JOBS.values() if j["status"] == "running"), None)
    return jsonify({"active": a["dataset"] | {"rows": a["overall"]["total"]} if a else None, "running_job": job and job["id"]})


# ---------------- upload and processing ----------------
def run_job(job, dataset_id, has_dates, has_id):
    out = ds.dataset_path(dataset_id)
    log_path = os.path.join(config.LOG_DIR, "%s.log" % dataset_id)
    try:
        cmd = [sys.executable, os.path.join(config.ROOT, "backend", "spark_job.py"), "--input", os.path.join(out, "canonical.csv"), "--out", out]
        if has_dates:
            cmd.append("--has-dates")
        if has_id:
            cmd.append("--has-id")
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, text=True, cwd=config.ROOT)
            for line in proc.stdout:
                if line.startswith("STAGE|"):
                    _, i, n, label = line.strip().split("|", 3)
                    job.update(stage=int(i), label=label)
            proc.wait()
        if proc.returncode != 0 or not os.path.exists(os.path.join(out, "analytics.json")):
            tail = open(log_path, encoding="utf-8", errors="replace").read()[-3000:]
            if re.search(r"JAVA_HOME|java: not found|Java gateway|not recognized", tail, re.I):
                msg = "The analysis engine needs Java (17 or 21) but could not start it. Check that Java is installed and reopen the terminal."
            else:
                msg = "The analysis could not be completed. Please check the CSV and try again."
            job.update(status="failed", error=msg, reference=dataset_id)
            return
        with LOCK:
            meta = ds.load_meta(dataset_id)
            meta["status"] = "ready"
            ds.save_meta(dataset_id, meta)
            STATE["active"] = dataset_id
        ds.prune({dataset_id} | {b["data"].get("dataset_id") for b in ledger.blocks})
        job.update(status="done", stage=len(STAGES), label="Done")
    except Exception as e:
        job.update(status="failed", error="Unexpected problem while processing. Please try again.", reference=dataset_id)
        with open(log_path, "a", encoding="utf-8") as log:
            log.write("\n%r\n" % e)


@app.route("/api/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return err("Please choose a CSV file.")
    if not f.filename.lower().endswith((".csv", ".txt")):
        return err("Only .csv files are supported.")
    if any(j["status"] == "running" for j in JOBS.values()):
        return err("Another dataset is still being processed. Please wait for it to finish.", 409)
    dataset_id = ds.new_dataset_id()
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", f.filename)[:80]
    os.makedirs(ds.dataset_path(dataset_id), exist_ok=True)
    original = os.path.join(config.UPLOAD_DIR, "%s__%s" % (dataset_id, safe))
    f.save(original)
    try:
        stats = ds.canonicalize(original, ds.dataset_path(dataset_id, "canonical.csv"), ds.dataset_path(dataset_id, "rejected.csv"))
    except ds.UploadError as e:
        os.remove(original)
        import shutil
        shutil.rmtree(ds.dataset_path(dataset_id), ignore_errors=True)
        return err(str(e))
    ds.reset_demo(dataset_id)
    ds.save_meta(dataset_id, {"dataset_id": dataset_id, "filename": f.filename, "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"), "status": "processing", "ingest": stats})
    job = {"id": uuid.uuid4().hex[:10], "dataset_id": dataset_id, "status": "running", "stage": 1, "label": STAGES[1], "stages": STAGES, "ingest": stats, "filename": f.filename}
    JOBS[job["id"]] = job
    threading.Thread(target=run_job, args=(job, dataset_id, stats["has_dates"], "review_id" in stats["columns_found"]), daemon=True).start()
    return jsonify({"job_id": job["id"], "ingest": stats})


@app.route("/api/jobs/<job_id>")
def job_status(job_id):
    j = JOBS.get(job_id)
    return jsonify(j) if j else err("Unknown job", 404)


# ---------------- analytics ----------------
@app.route("/api/analytics")
def analytics():
    a = need_active()
    return jsonify(a) if a else err("Upload a dataset to see analytics.", 404, reason="no_dataset")


@app.route("/api/reviews")
def reviews():
    dataset_id = active_id()
    p = dataset_id and ds.dataset_path(dataset_id, "processed.csv")
    if not p or not os.path.exists(p):
        return err("Upload a dataset first.", 404)
    product, q = request.args.get("product", ""), request.args.get("q", "").strip().lower()
    limit = max(1, min(int(request.args.get("limit", 25)), 200))
    out, matches = [], 0
    with open(p, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (not product or r["product"] == product) and (not q or q in r["text"].lower()):
                matches += 1
                if len(out) < limit:
                    out.append({k: r[k] for k in ("review_id", "product", "text", "sentiment", "score", "category")})
    a = load_analytics()
    return jsonify({"rows": out, "matches": matches, "shown": len(out), "dataset_rows": a["overall"]["total"], "searchable_rows": a["spark"]["processed_rows_saved"]})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    text = str((request.get_json(silent=True) or {}).get("text") or "").strip()
    if len(text) < 3:
        return err("Enter or select a review first.")
    return jsonify(nlp.analyze(text[:5000]))


@app.route("/api/diagnostics")
def diagnostics():
    import platform
    try:
        import pyspark
        java = subprocess.run(["java", "-version"], capture_output=True, text=True)
        return jsonify({"python": platform.python_version(), "pyspark": pyspark.__version__, "java": (java.stderr or java.stdout).splitlines()[0]})
    except Exception as e:
        return jsonify({"python": platform.python_version(), "error": str(e)})


# ---------------- integrity ----------------
def _target():
    did = (request.get_json(silent=True) or {}).get("dataset_id") or active_id()
    return did if did and ds.load_meta(did) else None


def _describe(did):
    meta, block = ds.load_meta(did), ledger.find(did)
    return {"dataset_id": did, "filename": meta["filename"], "uploaded_at": meta["uploaded_at"], "rows": meta["ingest"]["accepted"],
            "registered": bool(block), "merkle_root": block["data"]["merkle_root"] if block else None, "block_index": block["index"] if block else None,
            "transaction": block["hash"] if block else None, "registered_at": block["data"].get("registered_at") if block else None, "demo": ds.demo_info(did)}


@app.route("/api/integrity/state")
def integrity_state():
    did = request.args.get("dataset_id") or active_id()
    ok, bad = ledger.validate()
    history = [b["data"] | {"block_index": b["index"], "transaction": b["hash"]} for b in ledger.blocks if b["data"].get("type") == "DATASET_REGISTRATION"]
    return jsonify({"current": _describe(did) if did and ds.load_meta(did) else None, "history": history[::-1], "ledger_valid": ok, "bad_block": bad, "blocks": len(ledger.blocks)})


@app.route("/api/integrity/register", methods=["POST"])
def integrity_register():
    did = _target()
    if not did:
        return err("Upload and analyse a dataset first.")
    if ledger.find(did):
        return err("This dataset is already registered. Registrations cannot be changed.", 409)
    if ds.demo_info(did):
        return err("Reset the demonstration copy before registering.", 409)
    leaves, root = ds.register_leaves(did)
    meta = ds.load_meta(did)
    block = ledger.register({"type": "DATASET_REGISTRATION", "dataset_id": did, "filename": meta["filename"], "row_count": len(leaves), "merkle_root": root,
                             "registered_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return jsonify({"dataset_id": did, "merkle_root": root, "rows": len(leaves), "block_index": block["index"], "transaction": block["hash"]})


@app.route("/api/integrity/verify", methods=["POST"])
def integrity_verify():
    did = _target()
    if not did:
        return err("Upload and analyse a dataset first.")
    try:
        res = ds.verify_dataset(did, ledger)
    except Exception:
        res = {"status": "failed", "title": "Verification Failed", "message": "The verification could not be completed."}
    res["ledger_valid"] = ledger.validate()[0]
    return jsonify(res)


@app.route("/api/integrity/simulate", methods=["POST"])
def integrity_simulate():
    did = _target()
    if not did:
        return err("Upload and analyse a dataset first.")
    if not ledger.find(did):
        return err("Register the dataset first, then simulate a modification.", 409)
    return jsonify(ds.simulate_modification(did, (request.get_json(silent=True) or {}).get("seed")))


@app.route("/api/integrity/reset", methods=["POST"])
def integrity_reset():
    did = _target()
    if not did:
        return err("No dataset selected.")
    ds.reset_demo(did)
    return jsonify({"reset": True})


@app.route("/api/ledger")
def ledger_info():
    ok, bad = ledger.validate()
    return jsonify({"valid": ok, "bad_block": bad, "length": len(ledger.blocks), "blocks": ledger.blocks[-15:][::-1]})


@app.route("/api/ledger/simulate-tamper", methods=["POST"])
def simulate_tamper():
    blocks = copy.deepcopy(ledger.blocks)
    if len(blocks) < 2:
        return err("Register a dataset first.")
    blocks[1]["data"]["row_count"] = blocks[1]["data"].get("row_count", 0) + 1
    ok, bad = ledger.validate(blocks)
    return jsonify({"valid": ok, "bad_block": bad})


# ---------------- reports ----------------
def _download(body, mime, ext):
    a = load_analytics()
    base = re.sub(r"[^A-Za-z0-9_-]", "_", os.path.splitext(a["dataset"]["filename"])[0])
    return Response(body, mimetype=mime, headers={"Content-Disposition": "attachment; filename=ProductPulse_%s.%s" % (base, ext)})


@app.route("/api/report.csv")
def report_csv():
    a = load_analytics()
    return _download(report.product_csv(a).encode("utf-8"), "text/csv; charset=utf-8", "csv") if a else err("Upload a dataset first.", 404)


@app.route("/api/report.json")
def report_json():
    a = load_analytics()
    return _download(report.analytics_json(a).encode("utf-8"), "application/json; charset=utf-8", "json") if a else err("Upload a dataset first.", 404)


@app.route("/api/report.pdf")
def report_pdf():
    a = load_analytics()
    return _download(report.pdf_bytes(a, a["dataset"]["filename"]), "application/pdf", "pdf") if a else err("Upload a dataset first.", 404)


@app.errorhandler(413)
def too_big(e):
    return err("The file is too large (limit %d MB)." % config.MAX_UPLOAD_MB, 413)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
