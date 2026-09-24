"""Append-only, hash-chained JSONL. Nothing here rewrites or deletes a row."""
import hashlib, json, os
Z = "0" * 64
def _h(r): return hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()
def read(path): return [json.loads(l) for l in open(path)] if os.path.exists(path) else []
def append(path, rec):
    rows = read(path); rec = {**rec, "prev_hash": rows[-1]["row_hash"] if rows else Z}
    rec["row_hash"] = _h(rec)
    with open(path, "a") as f: f.write(json.dumps(rec) + "\n")
def verify(path):
    prev = Z
    for r in read(path):
        h = r.pop("row_hash")
        if r["prev_hash"] != prev or _h(r) != h: return False
        prev = h
    return True
