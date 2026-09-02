"""
RECON OS — Phase 4 (PROVE): Evaluation runner.

    python -m evaluation.runner            (from apps/api)

Executes every scenario in scenarios.py against the REAL pipeline, prints a
human-readable report, and writes a machine-readable JSON report next to
this file. Category percentages are computed from actual pass/fail results
— never hardcoded.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.getLogger("recon").setLevel(logging.CRITICAL)   # scenarios intentionally trigger
                                                          # warnings (timeouts, failures) —
                                                          # the report itself is the record.

from evaluation.scenarios import ScenarioResult, run_all

CATEGORY_LABELS = {
    "diagnosis": "Diagnosis correctness",
    "prediction": "Prediction correctness",
    "strategy": "Strategy correctness",
    "policy_safety": "Policy safety",
    "action_safety": "Action safety",
    "verification": "Verification correctness",
    "recovery_outcome": "Recovery outcome",
    "idempotency": "Idempotency",
    "unknown_safety": "UNKNOWN safety",
    "approval_safety": "Approval safety",
    "communication": "Communication safety",
}


def _category_rates(results: list[ScenarioResult]) -> dict[str, float]:
    totals: dict[str, int] = {}
    passed: dict[str, int] = {}
    for res in results:
        for tag in res.tags:
            totals[tag] = totals.get(tag, 0) + 1
            if res.passed:
                passed[tag] = passed.get(tag, 0) + 1
    return {
        tag: round(100.0 * passed.get(tag, 0) / total, 1)
        for tag, total in totals.items()
    }


def _print_report(results: list[ScenarioResult], rates: dict[str, float]) -> None:
    total = len(results)
    ok = sum(1 for r in results if r.passed)
    failed = total - ok

    print("Evaluation")
    print("-" * 60)
    print(f"Scenarios: {total}")
    print(f"Passed: {ok}")
    print(f"Failed: {failed}")
    print()
    for label_key, label in CATEGORY_LABELS.items():
        if label_key in rates:
            print(f"{label}: {rates[label_key]}%")
    print()

    if failed:
        print("Failed scenarios:")
        print("-" * 60)
        for r in results:
            if r.passed:
                continue
            print(f"  [{r.scenario_id:02d}] {r.name}")
            if r.error:
                print(f"        ERROR: {r.error}")
            for name, passed, detail in r.checks:
                if not passed:
                    print(f"        FAIL: {name}" + (f" ({detail})" if detail else ""))
        print()


def run(write_json: bool = True) -> tuple[list[ScenarioResult], dict[str, float]]:
    results = run_all()
    rates = _category_rates(results)
    _print_report(results, rates)

    if write_json:
        out_path = Path(__file__).parent / "last_run.json"
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scenarios": total_count(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "category_rates": rates,
            "results": [
                {
                    "id": r.scenario_id,
                    "name": r.name,
                    "tags": r.tags,
                    "passed": r.passed,
                    "error": r.error,
                    "checks": [
                        {"name": n, "passed": p, "detail": d} for n, p, d in r.checks
                    ],
                }
                for r in results
            ],
        }
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"Machine-readable report written to {out_path}")

    return results, rates


def total_count(results: list[ScenarioResult]) -> int:
    return len(results)


def main() -> int:
    results, _ = run()
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
