# Results log

## Step 2: NHANES 2021-2023 dataset (unweighted)
- Adults aged 20+ with eGFR and UACR: 5,343
- Probable CKD (eGFR < 60 or UACR >= 30, single visit): 925 (17.3%)
- Never told by a doctor (undiagnosed among CKD): 793 (85.7%)
- Notes: unweighted sample; single measurement, so "probable" CKD; eGFR uses race-free CKD-EPI 2021.
- Tests: tests/test_build_dataset.py (2 passed)

## Step 3: Model v1 (ckd_untested_v1), no kidney lab values as inputs
- Inputs: age, sex, SBP, DBP, diabetes, high BP diagnosis, HbA1c, BMI, hemoglobin, potassium, sodium
- Stacking ensemble (LR + NB + GB), SMOTE inside training folds only, isotonic calibration
- 5-fold CV AUC: 0.785 +/- 0.025 | Test AUC: 0.789 | Average precision: 0.506 | Brier: 0.114
- Flagging top 20% by risk catches 51.4% of CKD cases
- Simple rule (age 60+ OR diabetes OR high BP) flags 59%, catches 88.6%; model at same share catches 87.6%
- Conclusion: model matches the rule at broad screening; its value is ranking who to test first
- Fairness AUC: men 0.817, women 0.766; race/ethnicity groups 0.755 to 0.913 (small groups, wide uncertainty)

## Step 4: Model API (FastAPI + SHAP), runs in Docker
- Endpoints: GET /health, POST /score (risk, flag, top 5 reasons)
- Example: 67-year-old woman with diabetes, HbA1c 8.1, high BP -> risk 0.481, flagged
- Example: 32-year-old man, normal values -> risk 0.03, not flagged
- Missing values are never shown as reasons
- Docker image ckd-model-api; package versions pinned (added pyarrow)

## Step 5: Local Qwen note writer
- Qwen3-4B (Docker Model Runner, vLLM backend) writes a 2-3 sentence clinician note from model facts only
- Safety check: every number in the note must appear in the facts -> PASSED on test patient (2 runs)
- Issue found: Qwen described hemoglobin 11.9 as "elevated" in one run and "normal" in another (it is slightly low).
  The number check cannot catch wrong words, and wording varies between runs.
- Fix planned for Step 8: label each fact (high / low / normal) before sending to Qwen; clinician approves every note

## Step 6: FHIR server and synthetic patients
- HAPI FHIR server in Docker; Synthea: 364 patients aged 40-85 (300 living), seed 42
- Loader slims each bundle to patients, visits, diagnoses, medicines and needed labs:
  2.25 GB -> 0.17 GB; all 366 bundles loaded in 253 s, 0 failures; safe to rerun (no duplicates)
- Care gaps among 300 living patients (scripts/summarize_patients.py, read back from the server):
  kidney diagnosis on record 50 (17%) | lab CKD not diagnosed 1 (0%) | kidney tests overdue 58 (19%) | no gap 191 (64%)
- Model inputs available: BP, BMI, hemoglobin 100%; potassium, sodium 83%; HbA1c 72%
- Codes checked against the data; guide's table corrected: sodium/potassium also use 2947-0/2823-3,
  BP is inside panel 85354-9, and kidney diagnoses include ESRD, diabetic kidney disease and transplant codes
- Synthea data issues found:
  1. Creatinine values do not match Synthea's own eGFR (median creatinine 2.5 mg/dL with eGFR ~85),
     and hospital panels report eGFR in mL/min with values 5-15. Fix: use only lab-reported eGFR
     in mL/min/1.73m2. Before the fix, ~60 healthy patients were wrongly flagged as undiagnosed CKD.
  2. Synthea almost always records a CKD diagnosis when eGFR falls (1 undiagnosed case vs 85.7% in NHANES),
     so it tests the "tests overdue" path well but the "undiagnosed" path barely. Unit tests cover that path.
- Model on Synthea patients with overdue tests: top 5 all scored risk 1.00, top reasons sodium, age, potassium.
  Only 0.1% of NHANES adults score that high. Causes: isotonic calibration's top step is 1.0, and Synthea's
  lab values differ from NHANES (e.g., potassium higher, HbA1c as low as 2.3%). Scores on synthetic data are
  not real risks; use them only to rank. Fix planned: cap or re-calibrate scores (model v2).
- Tests: tests/test_patient_facts.py (13 passed)

## Step 7: Guideline search (RAG) with Qdrant
- 9 guideline notes written in my own words (KDIGO 2024, ADA), stored in Qdrant with source citations
- Retrieval test failed at first: "send a patient to a kidney specialist" returned the yearly-testing note
- Debugging: storage and database were correct; the small embedding model (bge-small) scored all notes 0.65-0.73
- Fix: topic-labeled notes + bge-base embedding model + query/passage embeddings -> referral note now ranks first (0.707 vs 0.668)
- 4 automated retrieval tests added


## Step 8 Part A: The agent (LangGraph)

Ran the agent on 100 Synthea patients:

| Result | Count |
| --- | --- |
| No gap | 63 |
| Deceased (skipped) | 13 |
| Kidney disease on record | 12 |
| Kidney tests overdue | 11 |
| Lab CKD not diagnosed | 1 |

- Every note passed the cite-or-refuse safety check (no invented numbers).
- Labeled facts (high/low/normal) stopped Qwen from mislabeling values.
- Prompt tightening (example + "has / does not have" + code limit of 3 sentences) cut notes from 5-7 sentences to 2.
- Found and fixed: for the lab-CKD patient (never scored), Qwen invented a "moderate" risk level. The number check could not catch it because it is a word. Fixed by stating "risk score not used" in the facts and adding a prompt rule. Also added low blood pressure labels (a diastolic of 39 mmHg was labeled normal).
- Known limitation: the 4B model sometimes adds small extra reasoning or skips an abnormal value. Clinician approval and the shown evidence and citation cover this; LoRA fine-tuning is planned.

## Step 8 Part B: Agent API and approval queue

FastAPI service on port 8001:

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | API is alive |
| `POST /run/{patient_id}` | Run the agent for one patient |
| `POST /run_all?limit=N` | Run the agent for many patients |
| `GET /queue?status=...` | Worklist, highest risk first |
| `POST /queue/{id}/decision` | Clinician approves, edits or rejects |
| `GET /patient/{patient_id}` | One patient's suggestions and decisions |

- Every decision stores the time and a note (audit trail).
- Tested by hand: approved items 29 and 34; a second decision on the same item returned 409 "Already decided".
- Invalid input is refused: non-number item id, or a decision other than approved/edited/rejected (422).
- Learned: in FHIR search results, the first `id` belongs to the Bundle (the envelope), not a patient. Patient IDs come after `"resourceType": "Patient"`.

## Step 9: Clinician dashboard (Streamlit)

Web page on port 8501 that calls the agent API (port 8001):

- Numbers: waiting for review, high risk waiting, approved, rejected.
- Worklist sorted by risk; review panel with next step, AI note, evidence (abnormal values in red), SHAP reasons and cited guideline.
- Approve / Edit and approve / Reject; edit and reject require a note.
- Decisions tab shows the audit trail (decision, time, note).
- Sidebar runs the agent for one patient or a batch.
- Tested by hand: approved and rejected items; reject without a note was blocked; decisions appeared in the audit trail.