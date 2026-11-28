# CKD Care-Gap Agent

An explainable AI agent that finds patients with **undiagnosed or untested chronic kidney disease (CKD)** in health records, explains why each one was flagged, cites the relevant guideline, and drafts the next step. **A clinician approves every suggestion.**

> **Status (November 2026): working end-to-end prototype.** Data pipeline, leakage-free risk model, explainable model API, FHIR records, guideline retrieval (RAG), a LangGraph agent with guardrails, an approval queue with an audit trail, and a clinician dashboard. The whole system starts with one command (Docker Compose). Started October 27, 2026. Research prototype on public and synthetic data, not a medical device.

## Why

- About **37 million US adults** have CKD, and about **9 in 10 don't know it** ([CDC](https://www.cdc.gov/kidney-disease/php/data-research/index.html)).
- Early CKD has no symptoms, and the urine test that catches it (UACR) is often never ordered.
- Finding CKD early gives time to slow it with proven treatments and avoid dialysis.

## How it works

For each patient, the agent:

1. Reads the record from a **FHIR** server.
2. Uses **rules** to find the care gap: kidney tests overdue, or lab results showing CKD with no diagnosis.
3. Scores risk with an **ML model** and explains it with **SHAP** (only for patients never tested; a lab result beats a prediction).
4. Retrieves the matching **guideline** from a vector database.
5. Has a **local LLM** (Qwen3-4B) write a 2-sentence note from labeled facts.
6. **Checks the note** and puts it in a queue for a clinician to approve, edit or reject.

The ML model calculates, rules decide the action, the LLM only writes, and a clinician decides.

| Service | Technology | Port |
| --- | --- | --- |
| Patient records | HAPI FHIR, 364 synthetic Synthea patients | 8080 |
| Guideline search | Qdrant + fastembed (bge-base) | 6333 |
| Risk model | FastAPI + scikit-learn + SHAP | 8000 |
| Agent + approval API | LangGraph + FastAPI + SQLite | 8001 |
| Clinician dashboard | Streamlit | 8501 |
| Local LLM | Qwen3-4B in Docker Model Runner (vLLM) | 12434 |

## What is built

| Step | What it does | Code |
| --- | --- | --- |
| Data | NHANES 2021–2023; race-free CKD-EPI 2021 eGFR; probable CKD = eGFR < 60 or UACR ≥ 30 | `scripts/download_nhanes.py`, `scripts/build_dataset.py` |
| Model | Stacking ensemble (LR + NB + GB), **no kidney labs as inputs**, SMOTE inside training folds only, isotonic calibration | `scripts/train_model.py` |
| Model API | `POST /score`: risk, risk level, top 5 SHAP reasons (missing values never shown) | `services/model_api/` |
| FHIR + care gaps | HAPI FHIR with Synthea patients; rules sort patients into care gaps | `scripts/load_synthea.py`, `services/agent/patient_facts.py`, `services/agent/fhir_codes.py` |
| Guidelines (RAG) | KDIGO 2024 / ADA notes in my own words, topic-labeled, searched by meaning | `guidelines/`, `scripts/ingest_guidelines.py`, `services/agent/guidelines.py` |
| Agent | LangGraph workflow: fetch → gap → score → retrieve → draft → validate → save | `services/agent/graph.py`, `services/agent/labels.py`, `services/agent/llm.py` |
| Approval API | Run the agent, worklist, approve/edit/reject with audit trail (409 on a second decision) | `services/agent/main.py` |
| Dashboard | Worklist by risk, note, evidence (abnormal values in red), SHAP, cited guideline, decision buttons | `services/dashboard/app.py` |
| Deployment | One command for all services | `docker-compose.yml` |
| Tests | 31 automated tests; agent tests use fake FHIR, model and LLM | `tests/` |

## Guardrails on the LLM

- **Labeled facts**: values arrive as "hemoglobin 11.9 g/dL (low)", so the LLM doesn't interpret numbers.
- **Cite-or-refuse**: no guideline found means no note.
- **Number check**: every number in the note must exist in the source facts, or the note is replaced.
- **Length limit in code**: at most 3 sentences.
- **Clinician approval**: nothing happens without a recorded decision.

## Results

Full log: [RESULTS.md](RESULTS.md).

**Dataset (NHANES 2021–2023, unweighted):** 5,343 adults aged 20+ with both kidney tests. 925 (17.3%) had probable CKD, and **793 of those (85.7%) had never been told**, close to the CDC's estimate.

**Model v1 (held-out test set):**

| Measure | Result |
| --- | --- |
| AUC, 5-fold cross-validation | 0.785 ± 0.025 |
| AUC, test set | 0.789 |
| Brier score | 0.114 |
| CKD cases caught when flagging the top 20% | 51.4% |
| AUC by sex | men 0.817, women 0.766 |

The model matches a simple rule (age 60+ OR diabetes OR high blood pressure) for broad screening. Its value is **ranking** who to test first, with reasons. These numbers are lower than the 99% in my earlier paper **on purpose**: kidney labs are no longer inputs, SMOTE no longer leaks into testing, and the data is national.

**Agent on 100 synthetic patients:** 63 no gap, 13 deceased (skipped), 12 kidney disease on record, **11 kidney tests overdue, 1 lab CKD not diagnosed**. Every note passed the safety checks; notes went from 5–7 sentences to 2 after adding labeled facts and a length limit.

## Known limitations

- CKD is labeled from one visit ("probable" CKD); guidelines need two results 3+ months apart.
- NHANES results are unweighted; some fairness subgroups are small.
- Model scores on Synthea patients are for ranking only (Synthea lab values differ from NHANES; calibration fix planned).
- The number check can't catch wrong **words**: in testing, the LLM once wrote "moderate risk" for an unscored patient (fixed in the facts and prompt). Clinician approval remains the final guardrail.
- No login yet, no EHR integration, no external validation on real clinical records.

## Run it yourself

Needs Python 3.12+, Docker Desktop (with Model Runner enabled), and Java 17+ for Synthea. No patient data or trained model is stored in this repo.

```bash
git clone https://github.com/sharifuzzamanmd/ckd-care-gap-agent.git
cd ckd-care-gap-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 1. Data and model (needed before building the model API image)
python scripts/download_nhanes.py
python scripts/build_dataset.py
python scripts/train_model.py

# 2. Synthetic patients
curl -L -o synthea/synthea-with-dependencies.jar https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar
(cd synthea && java -jar synthea-with-dependencies.jar -p 300 -a 40-85 -s 42 Massachusetts)

# 3. Local LLM
docker model pull huggingface.co/mlx-community/qwen3-4b-4bit

# 4. Start everything
docker compose up -d --build

# 5. Load data once (wait ~2 minutes for FHIR to start)
python scripts/load_synthea.py
python scripts/ingest_guidelines.py

pytest
```

Open the dashboard at **http://localhost:8501** and click **Scan patients**. The agent API docs are at **http://localhost:8001/docs**. Stop with `docker compose down` (don't add `-v`, which deletes the FHIR data).

## Tech stack

| Layer | In use | Planned |
| --- | --- | --- |
| ML | scikit-learn, imbalanced-learn, SHAP | XGBoost/LightGBM, MLflow, better calibration |
| LLM and agent | Qwen3-4B (local, vLLM), LangGraph, Qdrant, fastembed | LoRA fine-tuning, HIPAA-eligible hosted LLM |
| Services | FastAPI, SQLite, HAPI FHIR, Docker Compose | PostgreSQL, login and roles |
| Front end | Streamlit | SMART on FHIR app inside the EHR |
| Testing and infrastructure | pytest | GitHub Actions, AWS, Terraform |
| Data | NHANES (public), Synthea (synthetic FHIR) | Real health system data (pilot) |

## Repository layout

```
scripts/              Data, training, Synthea loader, guideline ingest, agent runner
services/model_api/   Risk model API (FastAPI + SHAP) and Dockerfile
services/agent/       Agent (LangGraph), FHIR client, labels, guidelines, LLM, approval API, Dockerfile
services/dashboard/   Clinician dashboard (Streamlit) and Dockerfile
guidelines/           Guideline notes for retrieval
tests/                Automated tests (pytest)
docker-compose.yml    Starts all services
RESULTS.md            Results log, one entry per step
docs/ROADMAP.md       Plan and progress
```

`data/`, `models/`, `synthea/` and `qdrant_data/` are created locally and not uploaded.

## Research background

Builds on: M. Sharifuzzaman et al., "Optimized Machine Learning Models and Stacking Hybrid Approach for Chronic Kidney Disease Prediction," *AIAI 2025*, Springer. DOI: [10.1007/978-3-031-96235-6_15](https://doi.org/10.1007/978-3-031-96235-6_15)

## Disclaimer

This is a research project, not a medical device. It is not intended for clinical use. No real patient data is stored in this repository.

## Author

**Md Sharifuzzaman** — [Website](https://sharifuzzamanmd.github.io/) · [Google Scholar](https://scholar.google.com/citations?user=JUlEjLwAAAAJ&hl=en) · [LinkedIn](http://www.linkedin.com/in/md-sharifuzzaman-sourov/)