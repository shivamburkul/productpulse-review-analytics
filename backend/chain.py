import hashlib
import json
import os
import threading
import time


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def merkle_root(hashes):
    if not hashes:
        return sha256_text("")
    level = list(hashes)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha256_text(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


class Ledger:
    """Append-only local ledger: every block stores the hash of the previous block (proof-of-work)."""

    def __init__(self, path, difficulty=3):
        self.path, self.difficulty, self.lock = path, difficulty, threading.RLock()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.blocks = json.load(f)
        else:
            self.blocks = []
            genesis = {"index": 0, "timestamp": time.time(), "prev_hash": "0" * 64, "data": {"type": "GENESIS"}, "nonce": 0}
            self._mine(genesis)
            self.blocks.append(genesis)
            self._save()

    @staticmethod
    def block_hash(b):
        body = {k: b[k] for k in ("index", "timestamp", "prev_hash", "data", "nonce")}
        return sha256_text(json.dumps(body, sort_keys=True))

    def _mine(self, block):
        prefix = "0" * self.difficulty
        block["nonce"] = 0
        while True:
            h = self.block_hash(block)
            if h.startswith(prefix):
                block["hash"] = h
                return
            block["nonce"] += 1

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.blocks, f, indent=1)
        os.replace(tmp, self.path)

    def find(self, dataset_id):
        for b in self.blocks:
            if b["data"].get("dataset_id") == dataset_id:
                return b
        return None

    def register(self, data):
        with self.lock:
            if self.find(data["dataset_id"]):
                raise ValueError("This dataset is already registered. Registrations cannot be changed.")
            block = {"index": len(self.blocks), "timestamp": time.time(), "prev_hash": self.blocks[-1]["hash"], "data": data, "nonce": 0}
            self._mine(block)
            self.blocks.append(block)
            self._save()
            return block

    def validate(self, blocks=None):
        blocks = self.blocks if blocks is None else blocks
        prefix = "0" * self.difficulty
        for i, b in enumerate(blocks):
            if self.block_hash(b) != b["hash"] or not b["hash"].startswith(prefix):
                return False, i
            if i > 0 and b["prev_hash"] != blocks[i - 1]["hash"]:
                return False, i
        return True, None
