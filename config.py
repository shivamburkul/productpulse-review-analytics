import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DATASET_DIR = os.path.join(DATA_DIR, "datasets")
LOG_DIR = os.path.join(DATA_DIR, "logs")
LEDGER_PATH = os.path.join(DATA_DIR, "ledger.json")
MINING_DIFFICULTY = 3
MAX_UPLOAD_MB = 100
KEEP_DATASETS = 25
PREVIEW_CAP = 50000

for _d in (DATA_DIR, UPLOAD_DIR, DATASET_DIR, LOG_DIR):
    os.makedirs(_d, exist_ok=True)
