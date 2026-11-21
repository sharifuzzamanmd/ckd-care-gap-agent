"""Agent tests with fake FHIR, model, guideline search and Qwen (no servers needed)."""
import sqlite3
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Fake guideline search and Qwen so this test needs no Qdrant or Docker.
# The fakes are used only while importing the agent, then the real modules are put back,
# so other test files (like test_guidelines.py) still test the real search.
fake_guidelines = types.ModuleType("services.agent.guidelines")
fake_guidelines.search = lambda q, k=2: [{"text": "Yearly testing in diabetes: test eGFR and UACR once a year.",
                                          "source": "test", "score": 0.9}]
fake_llm = types.ModuleType("services.agent.llm")
fake_llm.ask = lambda system, user, max_tokens=400: "Patient has diabetes; order eGFR and UACR."

FAKES = {"services.agent.guidelines": fake_guidelines, "services.agent.llm": fake_llm}
saved = {name: sys.modules.get(name) for name in FAKES}
sys.modules.update(FAKES)
sys.modules.pop("services.agent.graph", None)
from services.agent import graph  # noqa: E402  (the agent now holds the fakes)
from services.agent.labels import describe, label  # noqa: E402

for name, original in saved.items():  # put the real modules back for other tests
    if original is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = original
import services.agent as _pkg  # noqa: E402
for name in FAKES:
    attr = name.rsplit(".", 1)[1]
    if getattr(_pkg, attr, None) in FAKES.values():
        delattr(_pkg, attr)


def test_labels():
    assert label("hemoglobin", 11.9, female=1) == "low"
    assert label("hemoglobin", 13.5, female=0) == "normal"
    assert label("hba1c", 8.1, female=1).startswith("high")
    assert describe("hemoglobin", 11.9, 1) == "hemoglobin: 11.9 g/dL (low)"


def test_validate_replaces_invented_numbers():
    s = {"draft": {"note": "Risk is 99%.", "evidence": "age: 67", "next_step": "order eGFR and UACR",
                   "citations": [{"text": "test yearly"}]}}
    out = graph.validate(s)["draft"]
    assert "warning" in out and "99" not in out["note"]


def test_agent_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(graph, "DB", str(tmp_path / "agent.db"))
    monkeypatch.setattr(graph, "patient_facts", lambda resources: {
        "patient_id": "p1", "deceased": False, "age": 67, "female": 1, "diabetes": 1, "told_high_bp": 1,
        "kidney_diagnoses": [], "egfr_history": [], "uacr_history": [],
        "sbp": 152.0, "dbp": 84.0, "hba1c": 8.1, "bmi": 33.0, "hemoglobin": 11.9, "potassium": None, "sodium": None})
    monkeypatch.setattr(graph.fhir_client, "patient_resources", lambda pid: [])

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"risk": 0.481, "risk_level": "high", "top_drivers": [{"feature": "hba1c"}]}

    monkeypatch.setattr(graph.httpx, "post", lambda *a, **k: FakeResponse())

    result = graph.run("p1")
    assert result["gap"] == "kidney_tests_overdue"
    assert result["risk"] == 0.481
    row = sqlite3.connect(tmp_path / "agent.db").execute("SELECT status FROM queue").fetchone()
    assert row[0] == "pending_approval"



def test_validate_trims_long_notes():
    s = {"draft": {"note": "One. Two. Three. Four. Five.", "evidence": "age: 67", "next_step": "order eGFR and UACR",
                   "citations": [{"text": "test yearly"}]}}
    assert graph.validate(s)["draft"]["note"] == "One. Two. Three."


def test_describe_rounds():
    assert describe("hemoglobin", 12.195, 0) == "hemoglobin: 12.2 g/dL (low)"