"""Summarize saved synthetic evaluation artifacts; never execute model code."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREFIXES = ("hard-", "time-extended-", "budget16k-", "budget32k-")
ORIGINAL_NEW = {"qwen3.8-27b-q8_0", "ornith-1.5-35b"}

def summarize():
    records = []
    for folder in sorted(ROOT.iterdir()):
        if not folder.is_dir() or not (folder.name in ORIGINAL_NEW or folder.name.startswith(PREFIXES)):
            continue
        grades = {}
        for name in ("partial-acceptance.json", "acceptance.json", "real-helper-acceptance.json", "hard-acceptance.json"):
            path = folder / name
            if path.exists():
                raw = json.loads(path.read_text())
                grades.update({"real-helper": raw} if name == "real-helper-acceptance.json" else raw)
        for request in sorted(folder.glob("*-request.json")):
            task = request.name.removesuffix("-request.json")
            body = json.loads(request.read_text())
            record = dict(folder=folder.name, task=task, model=body["model"], think=body.get("think"), options=body["options"], request_sha256=hashlib.sha256(request.read_bytes()).hexdigest(), prompt_sha256=hashlib.sha256(body["messages"][0]["content"].encode()).hexdigest(), status="pending")
            for kind in ("result", "error"):
                path = folder / (task + "-" + kind + ".json")
                if not path.exists():
                    continue
                raw = json.loads(path.read_text())
                record.update(status=kind, wall_seconds=raw.get("wall_seconds", raw.get("elapsed_seconds")), deadline_seconds=raw.get("request_deadline_seconds"), done_reason=raw.get("done_reason"), output_tokens=raw.get("eval_count"), load_seconds=raw.get("load_duration", 0)/1e9, generation_seconds=raw.get("eval_duration", 0)/1e9, error_type=raw.get("error_type"), server_error=raw.get("bounded_server_error"))
                if kind == "result":
                    record["final_answer_bytes"] = len(raw.get("message", {}).get("content", "").encode())
                    samples = raw.get("memory_samples", [])
                    record["sampled_allocation_bytes"] = sorted({v["size"] for v in samples if isinstance(v.get("size"), int)})
                    record["sampled_vram_bytes"] = sorted({v["size_vram"] for v in samples if isinstance(v.get("size_vram"), int)})
            if task in grades:
                checks = grades[task]
                record["acceptance"] = dict(passed=sum(c["passed"] for c in checks), cases=len(checks), failures=[c for c in checks if not c["passed"]])
            records.append(record)
    manual = json.loads((ROOT / "hard-review-manual.json").read_text())
    complete = (ROOT / "extension-completion.json").exists() and len(records) == 44 and all(r["status"] != "pending" and ("acceptance" in r or r["status"] == "error") for r in records)
    result = dict(status="author_grading_complete" if complete else "in_progress", grading="author grading; original38 reviewer signoff does not cover extensions", memory_note="sampled Ollama allocation only; not total memory or proof of no swapping", inventory=json.loads((ROOT/"inventory.json").read_text()), records=records, hard_manual_reviews=manual)
    (ROOT / "extension-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(requests=len(records), pending=sum(r["status"] == "pending" for r in records), results=sum(r["status"] == "result" for r in records), errors=sum(r["status"] == "error" for r in records))))

if __name__ == "__main__":
    summarize()
