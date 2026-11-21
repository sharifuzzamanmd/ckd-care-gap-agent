"""Agent API tests: the approval queue, with no servers needed."""
import json
import sqlite3
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Use fake search and Qwen while importing (same idea as test_agent.py), then put the real ones back.
fakes = {"services.agent.guidelines": types.ModuleType("services.agent.guidelines"),
         "services.agent.llm": types.ModuleType("services.agent.llm")}
fakes["services.agent.guidelines"].search = lambda q, k=2: [{"text": "Yearly testing in diabetes: test eGFR and UACR once a year.",
                                                              "source": "test", "score": 0.9}]
fakes["services.agent.llm"].ask = lambda system, user, max_tokens=400: "Patient has diabetes; order eGFR and UACR."
saved = {name: sys.modules.get(name) for name in fakes}
if "services.agent.graph" not in sys.modules:  # test_agent.py may have loaded it already
    sys.modules.update(fakes)
from services.agent import graph, main  # noqa: E402
for name, original in saved.items():
    if original is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = original
import services.agent as _pkg  # noqa: E402
for name, fake in fakes.items():
    if getattr(_pkg, name.rsplit(".", 1)[1], None) is fake:
        delattr(_pkg, name.rsplit(".", 1)[1])


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = str(tmp_path / "agent.db")
    monkeypatch.setattr(graph, "DB", db)
    con = sqlite3.connect(db)
    con.execute(main.TABLE)
    con.execute("INSERT INTO queue (patient_id, gap, risk, payload, status, created) VALUES (?,?,?,?,?,?)",
                ("p1", "kidney_tests_overdue", 0.48, json.dumps({"note": "test"}), "pending_approval", "now"))
    con.commit()
    con.close()
    return TestClient(main.app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_queue_and_approve(client):
    items = client.get("/queue").json()
    assert len(items) == 1 and items[0]["payload"]["note"] == "test"
    r = client.post(f"/queue/{items[0]['id']}/decision", json={"decision": "approved", "note": "ok"})
    assert r.json()["status"] == "approved"
    assert client.get("/queue").json() == []
    assert len(client.get("/queue", params={"status": "approved"}).json()) == 1


def test_cannot_decide_twice(client):
    item = client.get("/queue").json()[0]
    client.post(f"/queue/{item['id']}/decision", json={"decision": "rejected"})
    assert client.post(f"/queue/{item['id']}/decision", json={"decision": "approved"}).status_code == 409


def test_bad_decision_is_refused(client):
    item = client.get("/queue").json()[0]
    assert client.post(f"/queue/{item['id']}/decision", json={"decision": "maybe"}).status_code == 422