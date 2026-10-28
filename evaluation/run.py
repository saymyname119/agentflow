"""Reproducible synthetic evaluation; not evidence of production impact."""
import json
import platform
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from approvalflow.models import Policy, Snapshot
from approvalflow.policy import evaluate

ROOT = Path(__file__).resolve().parents[1]


def load_cases():
    base = json.loads((ROOT / "examples/docs-pr.json").read_text())
    cases = json.loads((ROOT / "evaluation/scenarios.json").read_text())
    result = []
    for case in cases:
        data = json.loads(json.dumps(base))
        change = case["changes"]
        data["files"][0].update(change.get("file", {}))
        data["checks"][0].update(change.get("check", {}))
        if "extra_test" in change:
            data["files"].append({"filename": change["extra_test"], "additions": 1, "deletions": 0, "patch": "+assert expected == actual"})
        if "extra_check" in change:
            data["checks"].append(change["extra_check"])
        data.update(change.get("snapshot", {}))
        result.append((case, Snapshot.model_validate(data)))
    return result


def baseline(snapshot):
    """Naive baseline: any named test check succeeded, without risk inspection."""
    return "READY" if any(c.name == "test" and c.conclusion == "success" for c in snapshot.checks) else "BLOCKED"


def main():
    policy = Policy.model_validate_json((ROOT / "policy.json").read_text())
    cases = load_cases()
    results = []
    for case, snapshot in cases:
        rec = evaluate(snapshot, policy)
        results.append({"id": case["id"], "expected": case["expected"], "actual": rec.outcome,
                        "baseline": baseline(snapshot), "why": case["why"],
                        "finding_codes": [f.code for f in rec.findings]})
    for _ in range(5):  # Warmup, excluded from measurements.
        for _, snapshot in cases:
            evaluate(snapshot, policy)
    samples = []
    for _ in range(50):
        for _, snapshot in cases:
            start = time.perf_counter_ns()
            evaluate(snapshot, policy)
            samples.append((time.perf_counter_ns() - start) / 1_000_000)
    unsafe = sum(r["expected"] != "READY" for r in results)
    false_ready = lambda name: sum(r[name] == "READY" and r["expected"] != "READY" for r in results)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "dataset": "40 hand-authored synthetic scenarios",
        "limitations": "Policy regression fixtures authored with the implementation, not an independent or real-world safety benchmark. Timing measures the in-process policy function only; excludes GitHub, HTTP, database and queue time.",
        "python": platform.python_version(), "platform": platform.platform(), "policy_version": policy.version,
        "cases": len(results), "expected_distribution": dict(Counter(r["expected"] for r in results)),
        "matching_expected": sum(r["expected"] == r["actual"] for r in results),
        "unsafe_cases": unsafe, "baseline_unsafe_ready": false_ready("baseline"),
        "agent_unsafe_ready": false_ready("actual"),
        "agent_false_escalations": sum(r["expected"] == "READY" and r["actual"] != "READY" for r in results),
        "latency": {"samples": len(samples), "p50_ms": round(statistics.median(samples), 4),
                    "p95_ms": round(sorted(samples)[int(len(samples) * .95) - 1], 4)}, "results": results,
    }
    output = ROOT / "evaluation/results.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    if report["matching_expected"] != len(results):
        raise SystemExit("Evaluation mismatch; inspect results.json")


if __name__ == "__main__":
    main()
