"""Clinician dashboard: review the agent's suggestions and approve, edit or reject them."""
import os

import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
AGENT = os.getenv("AGENT_API_URL", "http://localhost:8001")
HIGH_RISK = 0.288  # the model's top-20% threshold
GAP_NAMES = {
    "kidney_tests_overdue": "Kidney tests overdue",
    "lab_ckd_not_diagnosed": "Lab CKD, not diagnosed",
}
ABNORMAL = ("(high", "(low", "(borderline", "(above normal")

st.set_page_config(page_title="CKD Care-Gap Agent", layout="wide")


def api(method, path, timeout=30, **kw):
    """Call the agent API and show a clear message if something goes wrong."""
    try:
        r = httpx.request(method, f"{AGENT}{path}", timeout=timeout, **kw)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        st.error(f"Can't reach the agent API at {AGENT}. "
                 "Start it with: uvicorn services.agent.main:app --port 8001")
        st.stop()
    except httpx.HTTPStatusError as e:
        st.error(f"The API answered {e.response.status_code}: {e.response.text}")
        st.stop()


def risk_text(risk):
    return f"{risk:.0%}" if risk is not None else "not scored"


def gap_name(gap):
    return GAP_NAMES.get(gap, gap)


# ---------- sidebar: run the agent ----------
with st.sidebar:
    st.header("Run the agent")
    limit = st.number_input("Patients to scan", min_value=10, max_value=400, value=50, step=10)
    if st.button("Scan patients"):
        with st.spinner("Scanning. Qwen writes a note for each care gap, so this can take a few minutes..."):
            counts = api("POST", "/run_all", timeout=None, params={"limit": limit})
        st.success(f"Done: {counts}")

    st.divider()
    pid = st.text_input("Run one patient (patient ID)")
    if st.button("Run patient") and pid.strip():
        with st.spinner("Running..."):
            result = api("POST", f"/run/{pid.strip()}", timeout=300)
        st.success(f"Result: {gap_name(result['gap'])}")

# ---------- header and numbers ----------
st.title("CKD Care-Gap Agent")
st.caption("Research prototype on synthetic data. Every suggestion needs clinician approval.")

if "message" in st.session_state:
    st.success(st.session_state.pop("message"))

pending = api("GET", "/queue")
approved = api("GET", "/queue", params={"status": "approved"})
edited = api("GET", "/queue", params={"status": "edited"})
rejected = api("GET", "/queue", params={"status": "rejected"})

c1, c2, c3, c4 = st.columns(4)
c1.metric("Waiting for review", len(pending))
c2.metric("High risk waiting", sum((i["risk"] or 0) >= HIGH_RISK for i in pending))
c3.metric("Approved", len(approved) + len(edited))
c4.metric("Rejected", len(rejected))

worklist_tab, decisions_tab = st.tabs(["Worklist", "Decisions"])

# ---------- worklist ----------
with worklist_tab:
    if not pending:
        st.info("Nothing waiting for review. Use 'Scan patients' in the sidebar.")
    else:
        table = pd.DataFrame([{
            "Item": i["id"],
            "Patient": i["patient_id"][:8],
            "Care gap": gap_name(i["gap"]),
            "Risk": risk_text(i["risk"]),
            "Next step": i["payload"].get("next_step", ""),
        } for i in pending])
        st.dataframe(table, hide_index=True, width="stretch")

        chosen = st.selectbox(
            "Choose an item to review", pending,
            format_func=lambda i: f"#{i['id']} · {gap_name(i['gap'])} · risk {risk_text(i['risk'])} · patient {i['patient_id'][:8]}")
        p = chosen["payload"]

        left, right = st.columns([3, 2])
        with left:
            st.subheader("Suggested next step")
            st.markdown(f"**{p.get('next_step', '-')}**")
            st.markdown(f"**Why flagged:** {p.get('reason', '-')}")
            if p.get("refused"):
                st.error(f"No AI note: {p['refused']}")
            elif p.get("warning"):
                st.warning(p["warning"])
            if p.get("note"):
                st.info(p["note"])

            st.subheader("Evidence from the record")
            for line in p.get("evidence", "").splitlines():
                if any(flag in line for flag in ABNORMAL):
                    st.markdown(f":red[**{line}**]")  # abnormal values stand out
                else:
                    st.markdown(line)

        with right:
            if p.get("top_drivers"):
                st.subheader("Why the model scored this risk (SHAP)")
                st.dataframe(pd.DataFrame(p["top_drivers"]), hide_index=True, width="stretch")
            st.subheader("Guideline cited")
            for c in p.get("citations", []):
                st.markdown(f"> {c['text']}")
                st.caption(c["source"])

        st.subheader("Your decision")
        note = st.text_area("Note (required for Edit or Reject)", key=f"note_{chosen['id']}")
        b1, b2, b3 = st.columns(3)
        decision = None
        if b1.button("Approve", type="primary"):
            decision = "approved"
        if b2.button("Edit and approve"):
            decision = "edited"
        if b3.button("Reject"):
            decision = "rejected"

        if decision:
            if decision != "approved" and not note.strip():
                st.warning("Please write a note explaining your edit or rejection.")
            else:
                api("POST", f"/queue/{chosen['id']}/decision", json={"decision": decision, "note": note})
                st.session_state["message"] = f"Item #{chosen['id']}: {decision}"
                st.rerun()

# ---------- decisions (audit trail) ----------
with decisions_tab:
    decided = sorted(approved + edited + rejected, key=lambda i: i["decided"] or "", reverse=True)
    if not decided:
        st.info("No decisions yet.")
    else:
        st.dataframe(pd.DataFrame([{
            "Item": i["id"],
            "Patient": i["patient_id"][:8],
            "Care gap": gap_name(i["gap"]),
            "Decision": i["status"],
            "When": (i["decided"] or "")[:16].replace("T", " "),
            "Note": i["decision_note"] or "",
        } for i in decided]), hide_index=True, width="stretch")