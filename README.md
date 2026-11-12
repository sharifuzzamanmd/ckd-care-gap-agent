# CKD Care-Gap Agent

An explainable AI agent that finds patients with **undiagnosed or untested chronic kidney disease (CKD)** in routine health data and helps care teams close the testing gap. A clinician approves every action.

> **Status (November 2026): working prototype, in active development.** The data pipeline, a leakage-free risk model, a model API with SHAP explanations, and a first LLM note writer are built and tested. The FHIR integration, care-gap rules, guideline retrieval, and clinician dashboard are not built yet. Started October 27, 2026.

## Why

- About **37 million US adults** have CKD, and about **9 in 10 don't know it** ([CDC](https://www.cdc.gov/kidney-disease/php/data-research/index.html)).
- Early CKD has no symptoms, and the urine test that catches it (UACR) is often never ordered.
- Finding CKD early gives time to slow it with proven treatments and avoid dialysis.

## What is built so far

| Step | What it does | Code |
| --- | --- | --- |
| 1. Data | Downloads NHANES 2021–2023, calculates eGFR with the race-free CKD-EPI 2021 equation, and labels probable CKD (eGFR < 60 or UACR ≥ 30) | `scripts/download_nhanes.py`, `scripts/build_dataset.py` |
| 2. Model | Stacking ensemble (logistic regression + naive Bayes + gradient boosting) that estimates CKD risk **without kidney lab values**, for patients who were never tested. SMOTE runs inside training folds only; probabilities are calibrated. | `scripts/train_model.py` |
| 3. Model API | FastAPI service: `POST /score` returns the risk, a flag, and the top 5 SHAP reasons, using only values the patient actually has. Runs in Docker. | `services/model_api/` |
| 4. Note writer | A local LLM (Qwen3-4B) turns the model's facts into a 2–3 sentence clinician note. A safety check rejects any note containing a number that was not in the facts. | `services/agent/llm.py`, `scripts/write_note.py` |
| Tests | 5 automated tests covering the eGFR equation, the dataset labels, and the API | `tests/` |

## Results so far

Full log: [RESULTS.md](RESULTS.md).

**Dataset (NHANES August 2021–August 2023, unweighted):** 5,343 adults aged 20+ with both eGFR and UACR. 925 (17.3%) had probable CKD, and 793 of those (85.7%) had never been told by a doctor. This is close to the CDC's own estimate of 87% from the same survey cycle.

**Model v1 (held-out test set):**

| Measure | Result |
| --- | --- |
| AUC, 5-fold cross-validation | 0.785 ± 0.025 |
| AUC, test set | 0.789 |
| Average precision | 0.506 |
| Brier score | 0.114 |
| CKD cases caught when flagging the top 20% by risk | 51.4% |
| AUC by sex | men 0.817, women 0.766 |
| AUC by race/ethnicity group | 0.755 to 0.913 (small groups, wide uncertainty) |

**Comparison with a simple rule.** The rule "age 60+ OR diabetes OR high blood pressure" flags 59% of patients and catches 88.6% of CKD cases. The model, flagging the same share, catches 87.6%. So the model does not beat the rule for broad screening. Its value is ranking: telling a care team with limited capacity which patients to test first, and explaining why.

**These numbers are much lower than the 99% accuracy in my earlier paper, on purpose.** That paper used a small 400-patient dataset where kidney lab values were among the inputs. Here the kidney labs, creatinine and BUN are removed from the inputs because they define the label, SMOTE is applied only inside training folds, and the data is a national survey. An AUC near 0.79 is the honest result for predicting CKD in people who have never had a kidney test.

## Known limitations

- CKD is labeled from a single visit, so it is "probable" CKD. Guidelines require two abnormal results at least 3 months apart.
- Results are unweighted, so they describe the NHANES sample, not the US population.
- Some fairness subgroups are small, and their AUCs are uncertain. Fairness by age group is not reported yet.
- The note writer's number check cannot catch wrong words. In testing, the LLM called a hemoglobin of 11.9 "elevated" in one run and "normal" in another (it is slightly low). The planned fix is to label each fact as high, low or normal before it reaches the LLM. A clinician approves every note.
- No external validation yet, and no testing on real clinical records.

## Run it yourself

Requires Python 3.12+. No patient data or trained model is stored in this repo; the steps below download public NHANES files and train the model locally.

```bash
git clone https://github.com/sharifuzzamanmd/ckd-care-gap-agent.git
cd ckd-care-gap-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/download_nhanes.py   # public NHANES files -> data/raw/
python scripts/build_dataset.py     # -> data/processed/nhanes_ckd.csv
python scripts/train_model.py       # prints metrics, saves models/ckd_untested_v1.joblib

pytest                              # run after the three steps above; tests need the dataset and model
```

Start the model API:

```bash
uvicorn services.model_api.main:app --port 8000
# or with Docker:
docker build -f services/model_api/Dockerfile -t ckd-model-api .
docker run -p 8000:8000 ckd-model-api
```

Score one patient:

```bash
curl -X POST http://localhost:8000/score -H "Content-Type: application/json" \
  -d '{"age": 67, "female": 1, "sbp": 152, "dbp": 84, "diabetes": 1, "told_high_bp": 1, "hba1c": 8.1, "bmi": 33, "hemoglobin": 11.9}'
```

This returns a risk of about 0.48, `"flag": true`, and the top reasons with their SHAP values.

Optional, the note writer: copy `.env.example` to `.env`, point it at any OpenAI-compatible LLM server, and with the API running, run `python scripts/write_note.py`.

## What comes next

1. Pull patient records (labs, diagnoses, medicines) through FHIR, using Synthea synthetic patients
2. Care-gap rules (e.g., diabetes with no UACR this year; abnormal eGFR with no diagnosis)
3. Look up the relevant KDIGO guideline (RAG)
4. Agent that drafts the next step: a test order, referral, or patient message
5. **Clinician approves, edits, or rejects** — nothing is automatic
6. Dashboard to track results and update the worklist

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full plan and progress.

## Tech stack

| Layer | In use now | Planned |
| --- | --- | --- |
| ML | Python, scikit-learn, imbalanced-learn, SHAP | XGBoost/LightGBM, MLflow |
| Services | FastAPI, Docker | Java Spring Boot, HAPI FHIR, PostgreSQL |
| LLM and agent | Local Qwen3-4B through an OpenAI-compatible API | LangGraph, Qdrant, HIPAA-eligible LLM |
| Front end | — | React + TypeScript, SMART on FHIR |
| Testing and infrastructure | pytest | AWS, Terraform, GitHub Actions |
| Data | NHANES (public) | Synthea (synthetic FHIR patients) |

## Repository layout

```
scripts/              Data download, dataset build, model training, note writer demo
services/model_api/   FastAPI model service and Dockerfile
services/agent/       LLM helper for the agent
tests/                Automated tests (pytest)
docs/ROADMAP.md       Plan and progress
RESULTS.md            Results log, one entry per step
guidelines/           Guideline documents for retrieval (empty for now)
```

`data/` and `models/` are created locally by the scripts and are not uploaded.

## Research background

Builds on: M. Sharifuzzaman et al., "Optimized Machine Learning Models and Stacking Hybrid Approach for Chronic Kidney Disease Prediction," *AIAI 2025*, Springer. DOI: [10.1007/978-3-031-96235-6_15](https://doi.org/10.1007/978-3-031-96235-6_15)

## Disclaimer

This is a research project, not a medical device. It is not intended for clinical use. No real patient data is stored in this repository.

## Author

**Md Sharifuzzaman** — [Website](https://sharifuzzamanmd.github.io/) · [Google Scholar](https://scholar.google.com/citations?user=JUlEjLwAAAAJ&hl=en) · [LinkedIn](http://www.linkedin.com/in/md-sharifuzzaman-sourov/)
