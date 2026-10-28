import json
from pathlib import Path
import runpy

import pytest

from approvalflow.models import Policy
from approvalflow.policy import evaluate

ROOT = Path(__file__).resolve().parents[1]
load_cases = runpy.run_path(str(ROOT / "evaluation/run.py"))["load_cases"]


@pytest.mark.parametrize("case,snapshot", load_cases(), ids=lambda x: x.get("id", "") if isinstance(x, dict) else "snapshot")
def test_labeled_scenarios(case, snapshot):
    policy = Policy.model_validate_json((ROOT / "policy.json").read_text())
    assert evaluate(snapshot, policy).outcome == case["expected"]
