"""Agent API: run the care-gap agent and let a clinician approve or reject its suggestions."""
import json
import sqlite3
from datetime import datetime
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from services.agent import fhir_client, graph  # noqa: E402

app = FastAPI(title="CKD Care-Gap Agent API", version="1.0")

TABLE = """CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY, patient_id TEXT, gap TEXT, risk REAL, payload TEXT,
    status TEXT, created TEXT, decided TEXT, decision_note TEXT)"""


def db():
    con = sqlite3.connect(graph.DB)
    con.row_factory = sqlite3.Row  # rows behave like dicts
    con.execute(TABLE)
    return con


class Decision(BaseModel):
    decision: Literal["approved", "edited", "rejected"]
    note: str = ""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run/{patient_id}")
def run_one(patient_id: str):
    """Run the agent for one patient."""
    return graph.run(patient_id)


@app.post("/run_all")
def run_all(limit: int = 100):
    """Run the agent for many patients and count the results."""
    counts = {}
    for pid in fhir_client.list_patient_ids(limit=limit):
        gap = graph.run(pid)["gap"]
        counts[gap] = counts.get(gap, 0) + 1
    return counts


@app.get("/queue")
def queue(status: str = "pending_approval"):
    """The clinician's worklist: suggestions with a given status, highest risk first."""
    con = db()
    rows = con.execute("SELECT * FROM queue WHERE status=? ORDER BY risk IS NULL, risk DESC, id",
                       (status,)).fetchall()
    con.close()
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


@app.post("/queue/{item_id}/decision")
def decide(item_id: int, d: Decision):
    """A clinician approves, edits or rejects one suggestion. The decision is recorded for audit."""
    con = db()
    row = con.execute("SELECT status FROM queue WHERE id=?", (item_id,)).fetchone()
    if row is None:
        con.close()
        raise HTTPException(404, "No such item")
    if row["status"] != "pending_approval":
        con.close()
        raise HTTPException(409, f"Already decided: {row['status']}")
    con.execute("UPDATE queue SET status=?, decided=?, decision_note=? WHERE id=?",
                (d.decision, datetime.now().isoformat(), d.note, item_id))
    con.commit()
    con.close()
    return {"id": item_id, "status": d.decision}

@app.get("/patient/{patient_id}")
def patient_history(patient_id: str):
    """Everything the agent suggested for one patient, newest first, with any decisions."""
    con = db()
    rows = con.execute("SELECT * FROM queue WHERE patient_id=? ORDER BY id DESC", (patient_id,)).fetchall()
    con.close()
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]