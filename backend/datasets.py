import csv
import io
import json
import os
import random
import re
import shutil
import time
import unicodedata
import uuid
from datetime import datetime

import config
from backend.chain import merkle_root, sha256_text

csv.field_size_limit(10 ** 8)
ALIASES = {
    "product": ["product", "product_name", "productname", "item", "item_name", "model"],
    "text": ["text", "review", "comment", "review_text", "reviewtext", "comment_text", "content", "body", "review_body"],
    "rating": ["rating", "stars", "score", "star_rating"],
    "date": ["date", "review_date", "timestamp", "time", "created_at", "reviewdate"],
    "review_id": ["review_id", "reviewid", "id", "comment_id", "commentid"],
}
CANON_COLS = ["row_no", "review_id", "product", "text", "rating", "date"]
HASH_COLS = ["review_id", "product", "text", "rating", "date"]
DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]


class UploadError(Exception):
    pass


def _norm(h):
    return re.sub(r"[^a-z0-9]+", "_", h.strip().lower().lstrip("\ufeff")).strip("_")


def normalize_text(s):
    s = unicodedata.normalize("NFC", str(s or "")).replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", s).strip()


def parse_date(s):
    s = str(s or "").strip()
    if not s:
        return ""
    s2 = s.replace("Z", "")[:19]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s2 if "T" in fmt or ":" in fmt else s[:len(s)], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "")).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _decode(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue


def canonicalize(upload_path, out_path, rejected_path):
    """Validate the upload, map column aliases and write a clean canonical CSV. Returns statistics."""
    content = _decode(upload_path)
    if not content.strip():
        raise UploadError("The file is empty.")
    try:
        dialect = csv.Sniffer().sniff(content[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(content, newline=""), dialect)
    try:
        header = next(reader)
    except StopIteration:
        raise UploadError("The file has no header row.")
    names = [_norm(h) for h in header]
    col = {}
    for key, options in ALIASES.items():
        for o in options:
            if o in names:
                col[key] = names.index(o)
                break
    missing = [k for k in ("product", "text") if k not in col]
    if missing:
        raise UploadError("Missing required column(s): %s. Found columns: %s. Accepted names - product: product, product_name; "
                          "review text: review, comment, text, review_text." % (", ".join(missing), ", ".join(h for h in header if h.strip()) or "none"))
    reasons, rejected, accepted, rows_read, dated, ratings = {}, [], 0, 0, 0, 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CANON_COLS)
        for line_no, row in enumerate(reader, start=2):
            if not any(c.strip() for c in row):
                continue
            rows_read += 1
            get = lambda k: row[col[k]] if k in col and col[k] < len(row) else ""
            product, text = normalize_text(get("product")), normalize_text(get("text"))
            reason = "missing product" if not product else "missing review text" if not text else None
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
                if len(rejected) < 500:
                    rejected.append([line_no, reason, " | ".join(row)[:200]])
                continue
            accepted += 1
            rid = normalize_text(get("review_id")) or "R%06d" % accepted
            try:
                rating = str(float(get("rating"))) if str(get("rating")).strip() else ""
            except ValueError:
                rating = ""
            d = parse_date(get("date"))
            dated += bool(d)
            ratings += bool(rating)
            w.writerow([accepted, rid, product, text, rating, d])
    with open(rejected_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["line", "reason", "row"])
        w.writerows(rejected)
    if accepted == 0:
        raise UploadError("No usable rows found. Every row was missing a product or a review text.")
    return {"rows_read": rows_read, "accepted": accepted, "rejected": rows_read - accepted, "reject_reasons": reasons,
            "has_rating": ratings > 0, "dated_rows": dated, "has_dates": dated >= 0.5 * accepted, "columns_found": {k: header[v] for k, v in col.items()}}


def read_canonical(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_canonical(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CANON_COLS)
        w.writeheader()
        w.writerows(rows)


def row_hash(row):
    return sha256_text("\x1f".join(normalize_text(row.get(c, "")) for c in HASH_COLS))


def leaves_of(path):
    return [row_hash(r) for r in read_canonical(path)]


def dataset_path(dataset_id, *parts):
    return os.path.join(config.DATASET_DIR, dataset_id, *parts)


def new_dataset_id():
    return "DS-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:6])


def save_meta(dataset_id, meta):
    tmp = dataset_path(dataset_id, "meta.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    os.replace(tmp, dataset_path(dataset_id, "meta.json"))


def load_meta(dataset_id):
    p = dataset_path(dataset_id, "meta.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def prune(keep_ids, limit=None):
    limit = limit or config.KEEP_DATASETS
    items = sorted((d for d in os.listdir(config.DATASET_DIR) if d.startswith("DS-")), reverse=True)
    for d in items[limit:]:
        if d not in keep_ids:
            shutil.rmtree(dataset_path(d), ignore_errors=True)
            for u in os.listdir(config.UPLOAD_DIR):
                if u.startswith(d + "__"):
                    os.remove(os.path.join(config.UPLOAD_DIR, u))


# ---------------- integrity (Merkle) ----------------
def register_leaves(dataset_id):
    leaves = leaves_of(dataset_path(dataset_id, "canonical.csv"))
    with open(dataset_path(dataset_id, "leaves.json"), "w") as f:
        json.dump(leaves, f)
    return leaves, merkle_root(leaves)


def verify_dataset(dataset_id, ledger):
    block = ledger.find(dataset_id)
    if not block:
        return {"status": "not_registered", "title": "Not Registered", "message": "This dataset has no registered fingerprint yet."}
    work = dataset_path(dataset_id, "working.csv")
    ref_path = dataset_path(dataset_id, "leaves.json")
    if not os.path.exists(work) or not os.path.exists(ref_path):
        return {"status": "failed", "title": "Verification Failed", "message": "The stored dataset files could not be found."}
    with open(ref_path) as fh:
        ref = json.load(fh)
    reg_root = block["data"]["merkle_root"]
    if merkle_root(ref) != reg_root:
        return {"status": "failed", "title": "Verification Failed", "message": "The saved comparison data does not match the ledger, so rows cannot be compared reliably."}
    cur_rows = read_canonical(work)
    cur = [row_hash(r) for r in cur_rows]
    root = merkle_root(cur)
    res = {"dataset_id": dataset_id, "registered_root": reg_root, "current_root": root, "registered_rows": len(ref), "current_rows": len(cur),
           "block_index": block["index"], "transaction": block["hash"]}
    if root == reg_root:
        return {**res, "status": "verified", "title": "Verified — No Changes Detected", "message": "Every row matches the registered fingerprint.", "changes": []}
    orig = read_canonical(dataset_path(dataset_id, "canonical.csv"))
    changes = []
    for i in range(max(len(ref), len(cur))):
        if i >= len(cur):
            changes.append({"row": i + 1, "kind": "removed", "original": orig[i]["text"] if i < len(orig) else ""})
        elif i >= len(ref):
            changes.append({"row": i + 1, "kind": "added", "modified": cur_rows[i]["text"]})
        elif cur[i] != ref[i]:
            changes.append({"row": i + 1, "kind": "changed", "review_id": cur_rows[i]["review_id"], "product": cur_rows[i]["product"],
                            "original": orig[i]["text"] if i < len(orig) else "", "modified": cur_rows[i]["text"]})
    return {**res, "status": "mismatch", "title": "Mismatch — Dataset Has Changed", "changes": changes[:50], "total_changes": len(changes),
            "message": "The data differs from the registered version. A mismatch shows that the data changed, not why it changed."}


_SWAPS = [("excellent", "terrible"), ("great", "awful"), ("good", "bad"), ("love", "hate"), ("best", "worst"), ("easy", "difficult"), ("happy", "unhappy")]


def simulate_modification(dataset_id, seed=None):
    work = dataset_path(dataset_id, "working.csv")
    rows = read_canonical(work)
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    cand = [i for i, r in enumerate(rows) if len(r["text"]) >= 15]
    i = rng.choice(cand or list(range(len(rows))))
    original = rows[i]["text"]
    modified = original
    for a, b in _SWAPS:
        if re.search(r"\b%s\b" % a, original, re.I):
            modified = re.sub(r"\b%s\b" % a, b, original, count=1, flags=re.I)
            break
    if modified == original:
        modified = original + " (edited after registration)"
    rows[i]["text"] = modified
    write_canonical(work, rows)
    info = {"row": i + 1, "review_id": rows[i]["review_id"], "product": rows[i]["product"], "original": original, "modified": modified}
    with open(dataset_path(dataset_id, "demo.json"), "w", encoding="utf-8") as f:
        json.dump(info, f)
    return info


def demo_info(dataset_id):
    p = dataset_path(dataset_id, "demo.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def reset_demo(dataset_id):
    shutil.copyfile(dataset_path(dataset_id, "canonical.csv"), dataset_path(dataset_id, "working.csv"))
    p = dataset_path(dataset_id, "demo.json")
    if os.path.exists(p):
        os.remove(p)
