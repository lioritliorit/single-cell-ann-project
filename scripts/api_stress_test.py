"""
Concurrent API smoke/stress test for member 4 backend integration.

Run after starting the Flask server:
    python app.py
    python scripts/api_stress_test.py --url http://127.0.0.1:5000 --requests 100 --workers 8
"""

import argparse
import csv
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List


def load_default_cell_id(metadata_path: str = "cleaned_cell_metadata.csv") -> str:
    with open(metadata_path, encoding="utf-8-sig", newline="") as file_obj:
        first = next(csv.DictReader(file_obj))
    return first["cell_id"]


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return {
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "body": json.loads(body) if body else {},
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "body": exc.read().decode("utf-8"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": 0,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "body": str(exc),
        }


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cell-id", default="")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output", default="docs/member4_concurrency_result.json")
    args = parser.parse_args()

    cell_id = args.cell_id or load_default_cell_id()
    payload = {"cell_id": cell_id, "k": args.k, "search_mode": "normal"}
    url = args.url.rstrip("/") + "/api/search"

    started = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(post_json, url, payload) for _ in range(args.requests)]
        for future in as_completed(futures):
            results.append(future.result())
    elapsed = time.perf_counter() - started

    latencies = [item["latency_ms"] for item in results]
    ok_count = sum(1 for item in results if item["ok"])
    summary = {
        "url": url,
        "requests": args.requests,
        "workers": args.workers,
        "success": ok_count,
        "failed": args.requests - ok_count,
        "success_rate": ok_count / max(1, args.requests),
        "total_elapsed_seconds": round(elapsed, 3),
        "throughput_rps": round(args.requests / max(elapsed, 0.001), 3),
        "latency_ms": {
            "min": round(min(latencies), 3),
            "avg": round(statistics.mean(latencies), 3),
            "p50": round(percentile(latencies, 50), 3),
            "p95": round(percentile(latencies, 95), 3),
            "max": round(max(latencies), 3),
        },
        "failed_statuses": sorted({item["status"] for item in results if not item["ok"]}),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if ok_count == args.requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
