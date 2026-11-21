"""The CKD care-gap agent: a fixed, step-by-step workflow built with LangGraph.

fetch -> facts -> check_gap -> (score) -> retrieve -> draft -> validate -> save
Rules decide the gap and the action. The model scores. Qwen only writes. A clinician approves.
"""
import json
import os
import re
import sqlite3
from datetime import datetime
from typing import TypedDict

import httpx
from langgraph.graph import END, StateGraph

from services.agent import fhir_client, guidelines, llm
from services.agent.labels import describe
from services.agent.patient_facts import care_gap, model_input, patient_facts

MODEL_API = os.getenv("MODEL_API_URL", "http://localhost:8000")
DB = os.getenv("AGENT_DB", "data/agent.db")

SEARCH_QUESTION = {
    "kidney_tests_overdue": "yearly kidney testing for diabetes or high blood pressure",
    "lab_ckd_not_diagnosed": "confirming CKD and when to refer to a kidney specialist",
}


class State(TypedDict, total=False):
    patient_id: str
    facts: dict
    gap: dict
    score: dict
    guidance: list
    draft: dict
    refused: str
    score_missing: str
    skip: str


# ---------- the steps ----------
def fetch_facts(s: State) -> State:
    facts = patient_facts(fhir_client.patient_resources(s["patient_id"]))
    return {"facts": facts, "skip": "deceased" if facts["deceased"] else ""}


def check_gap(s: State) -> State:
    return {"gap": care_gap(s["facts"])}


def score(s: State) -> State:
    """Cite-or-refuse for the model: score only when there is enough real data.
    If there isn't, the rule-based next step (order the tests) still goes to the clinician."""
    payload = model_input(s["facts"])
    measured = [k for k in ("sbp", "hba1c", "bmi", "hemoglobin") if payload.get(k) is not None]
    if payload.get("age") is None or len(measured) < 2:
        return {"score_missing": "risk not scored: fewer than 2 key measurements on record"}
    r = httpx.post(f"{MODEL_API}/score", json=payload, timeout=60)
    r.raise_for_status()
    return {"score": r.json()}


def retrieve(s: State) -> State:
    return {"guidance": guidelines.search(SEARCH_QUESTION[s["gap"]["gap"]], k=2)}


def evidence(s: State) -> str:
    """Labeled facts: the ONLY information Qwen may use."""
    f, g = s["facts"], s["gap"]
    has = [n for k, n in (("diabetes", "diabetes"), ("told_high_bp", "high blood pressure")) if f[k] == 1]
    has_not = [n for k, n in (("diabetes", "diabetes"), ("told_high_bp", "high blood pressure")) if f[k] != 1]
    lines = [describe("age", f["age"], f["female"]), f"sex: {'female' if f['female'] else 'male'}",
             f"has: {', '.join(has) or 'none of diabetes or high blood pressure'}",
             f"does not have: {', '.join(has_not) or 'nothing listed'}",
                          "care gap: " + re.sub(r"\d+\.\d+", lambda m: f"{float(m.group()):.0f}", g["reason"])]
    for name in ("hba1c", "sbp", "dbp", "bmi", "hemoglobin"):
        if f.get(name) is not None:
            lines.append(describe(name, f[name], f["female"]))
    if s.get("score"):
        lines.append(f"CKD risk score: {round(s['score']['risk'] * 100)}% ({s['score'].get('risk_level', '')})")
    elif s.get("score_missing"):
        lines.append(s["score_missing"])
    else:
        lines.append("CKD risk score: not used, because kidney lab results are already on record")
    return "\n".join(lines)


SYSTEM_PROMPT = (
    "You write a note for a busy primary care clinician. Write EXACTLY 2 sentences.\n"
    "Sentence 1: who the patient is (age, sex, what they have), the CKD risk score if given, "
    "and only the abnormal results (high, low, borderline, above normal). Skip normal results.\n"
    "Sentence 2: the recommended next step and the guideline reason, in plain words.\n"
    "Use the labels exactly as written. Do not add any number, diagnosis or medicine "
    "that is not in the facts. Do not repeat yourself.\n"
    "If the facts say the risk score is not used, do not mention a risk score.\n"
    "Example: A [age]-year-old man with high blood pressure, a moderate CKD risk score ([risk]%) "
    "and high systolic blood pressure has had no eGFR or UACR in the past year. "
    "Order eGFR and UACR, because guidelines advise yearly kidney testing for people with high blood pressure."
)


def draft(s: State) -> State:
    if s.get("refused"):
        return {}
    ev = evidence(s)
    cites = "\n".join(f"- {c['text']}" for c in s["guidance"])
    note = llm.ask(
        SYSTEM_PROMPT,
        f"Patient facts:\n{ev}\n\nGuideline:\n{cites}\n\nRecommended next step: {s['gap']['next_step']}\n"
        "Write the 2-sentence note.",
        max_tokens=150)
    return {"draft": {"next_step": s["gap"]["next_step"], "note": note,
                      "evidence": ev, "citations": s["guidance"]}}


def validate(s: State) -> State:
    """Cite-or-refuse: a guideline must be cited, and every number must come from the evidence."""
    if s.get("refused"):
        return {}
    d = s["draft"]
    if not d["citations"]:
        return {"refused": "No guideline found to cite"}
    nums = lambda text: {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}
    allowed = nums(d["evidence"] + " " + " ".join(c["text"] for c in d["citations"]) + " " + d["next_step"])
    sentences = re.split(r"(?<=[.!?])\s+", d["note"].strip())
    if len(sentences) > 3:  # keep notes short even if Qwen writes too much
        d = {**d, "note": " ".join(sentences[:3])}
    invented = sorted(nums(d["note"]) - allowed)
    if invented:
        d = {**d, "note": "Flagged by rules. Evidence: " + d["evidence"].replace("\n", "; "),
             "warning": f"AI note replaced: it contained numbers not in the evidence {invented}"}
    return {"draft": d}

def save(s: State) -> State:
    """Put the suggestion in the approval queue (one pending item per patient)."""
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY, patient_id TEXT, gap TEXT, risk REAL, payload TEXT,
        status TEXT, created TEXT, decided TEXT, decision_note TEXT)""")
    con.execute("DELETE FROM queue WHERE patient_id=? AND status IN ('pending_approval','refused')",
                (s["patient_id"],))
    payload = s.get("draft") or {"next_step": s["gap"]["next_step"], "refused": s.get("refused")}
    payload["reason"] = s["gap"]["reason"]
    if s.get("score"):
        payload["top_drivers"] = s["score"]["top_drivers"]
    con.execute("INSERT INTO queue (patient_id, gap, risk, payload, status, created) VALUES (?,?,?,?,?,?)",
                (s["patient_id"], s["gap"]["gap"], (s.get("score") or {}).get("risk"),
                 json.dumps(payload, default=str),
                 "refused" if s.get("refused") else "pending_approval", datetime.now().isoformat()))
    con.commit()
    con.close()
    return {}


# ---------- the routes between steps ----------
def after_facts(s: State) -> str:
    return "end" if s.get("skip") else "check_gap"


def after_gap(s: State) -> str:
    gap = s["gap"]["gap"]
    if gap == "kidney_tests_overdue":
        return "score"
    if gap == "lab_ckd_not_diagnosed":
        return "retrieve"
    return "end"  # no_gap, or kidney disease already on record


def build_graph():
    g = StateGraph(State)
    for name, fn in [("fetch_facts", fetch_facts), ("check_gap", check_gap), ("score", score),
                     ("retrieve", retrieve), ("draft", draft), ("validate", validate), ("save", save)]:
        g.add_node(name, fn)
    g.set_entry_point("fetch_facts")
    g.add_conditional_edges("fetch_facts", after_facts, {"end": END, "check_gap": "check_gap"})
    g.add_conditional_edges("check_gap", after_gap, {"end": END, "score": "score", "retrieve": "retrieve"})
    g.add_edge("score", "retrieve")
    g.add_edge("retrieve", "draft")
    g.add_edge("draft", "validate")
    g.add_edge("validate", "save")
    g.add_edge("save", END)
    return g.compile()


agent = build_graph()


def run(patient_id: str) -> dict:
    """Run the agent for one patient and return a short summary."""
    s = agent.invoke({"patient_id": patient_id})
    return {"patient_id": patient_id, "gap": (s.get("gap") or {}).get("gap", s.get("skip")),
            "risk": (s.get("score") or {}).get("risk"), "refused": s.get("refused"),
            "score_missing": s.get("score_missing"), "next_step": (s.get("gap") or {}).get("next_step"),
            "note": (s.get("draft") or {}).get("note")}