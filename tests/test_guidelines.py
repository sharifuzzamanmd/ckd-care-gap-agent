"""Checks that guideline search returns the right note. Needs Qdrant running."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from services.agent.guidelines import search
    search("test")
except Exception:  # Qdrant not running or not loaded
    pytest.skip("Qdrant not available", allow_module_level=True)


@pytest.mark.parametrize("question, must_contain", [
    ("diabetic patient never had a urine test", "yearly testing in diabetes"),
    ("when should I send a patient to a kidney specialist", "refer to a nephrologist"),
    ("one abnormal kidney result", "repeated within 3 months"),
    ("medicine for CKD with type 2 diabetes", "sglt2"),
])
def test_top_result_is_the_right_guideline(question, must_contain):
    top = search(question, k=1)[0]["text"].lower()
    assert must_contain in top