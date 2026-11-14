# CKD Care-Gap Agent

An explainable AI agent that finds patients with **undiagnosed or untested chronic kidney disease (CKD)** in routine health data and helps care teams close the testing gap. A clinician approves every action.

> **Status (November 2026): working prototype, in active development.** The data pipeline, a leakage-free risk model, a model API with SHAP explanations, a first LLM note writer, and a FHIR server with synthetic patients and care-gap rules are built and tested. Guideline retrieval, the agent itself, and the clinician dashboard are not built yet. Started October 27, 2026.

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
| 5. FHIR data and care gaps | A HAPI FHIR server in Docker holds 364 synthetic patients from Synthea. The loader slims each record 13x. Care-gap rules sort each patient into: kidney disease already diagnosed, labs show CKD without a diagnosis, or kidney tests overdue. | `scripts/load_synthea.py`, `scripts/summarize_patients.py`, `services/agent/patient_facts.py`, `services/agent/fhir_codes.py` |
| Tests | 18 automated tests covering the eGFR equation, the dataset labels, the API, and the care-gap rules | `tests/` |

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

**Synthetic patients (Synthea, 300 living, aged 40–85):** 50 (17%) already have a kidney diagnosis, 58 (19%) have diabetes or high blood pressure with kidney tests overdue, and 1 has CKD in their labs without a diagnosis. Building this step exposed two problems in Synthea's data, both now handled and recorded in [RESULTS.md](RESULTS.md): its creatinine values don't match its own eGFR, and it almost never leaves CKD undiagnosed.

**These numbers are much lower than the 99% accuracy in my earlier paper, on purpose.** That paper used a small 400-patient dataset where kidney lab values were among the inputs. Here the kidney labs, creatinine and BUN are removed from the inputs because they define the label, SMOTE is applied only inside training folds, and the data is a national survey. An AUC near 0.79 is the honest result for predicting CKD in people who have never had a kidney test.

## Known limitations

- CKD is labeled from a single visit, so it is "probable" CKD. Guidelines require two abnormal results at least 3 months apart.
- Results are unweighted, so they describe the NHANES sample, not the US population.
- Some fairness subgroups are small, and their AUCs are uncertain. Fairness by age group is not reported yet.
- The note writer's number check cannot catch wrong words. In testing, the LLM called a hemoglobin of 11.9 "elevated" in one run and "normal" in another (it is slightly low). The planned fix is to label each fact as high, low or normal before it reaches the LLM. A clinician approves every note.
- Model scores on Synthea patients are not real risks. Synthea's lab values differ from NHANES, and the calibration step lets scores reach 1.00, so the top overdue patients all scored 1.00. Use scores only to rank for now; a calibration fix is planned.
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

Step 6, synthetic patients (needs Docker and Java 17+):

```bash
docker run -d --name fhir -p 8080:8080 hapiproject/hapi:latest
curl -L -o synthea/synthea-with-dependencies.jar https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar
(cd synthea && java -jar synthea-with-dependencies.jar -p 300 -a 40-85 -s 42 Massachusetts)
python scripts/load_synthea.py          # waits for the server, then loads (~4 min)
python scripts/summarize_patients.py --score   # care gaps; --score needs the model API running
```

Optional, the note writer: copy `.env.example` to `.env`, point it at any OpenAI-compatible LLM server, and with the API running, run `python scripts/write_note.py`.

## What comes next

1. Look up the relevant KDIGO guideline (RAG)
2. Agent that drafts the next step: a test order, referral, or patient message
3. **Clinician approves, edits, or rejects** — nothing is automatic
4. Dashboard to track results and update the worklist

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full plan and progress.

## Tech stack

| Layer | In use now | Planned |
| --- | --- | --- |
| ML | Python, scikit-learn, imbalanced-learn, SHAP | XGBoost/LightGBM, MLflow |
| Services | FastAPI, Docker, HAPI FHIR | Java Spring Boot, PostgreSQL |
| LLM and agent | Local Qwen3-4B through an OpenAI-compatible API | LangGraph, Qdrant, HIPAA-eligible LLM |
| Front end | — | React + TypeScript, SMART on FHIR |
| Testing and infrastructure | pytest | AWS, Terraform, GitHub Actions |
| Data | NHANES (public), Synthea (synthetic FHIR patients) | Real health system data (pilot) |

## Repository layout

```
scripts/              Data download, dataset build, model training, note writer demo,
                      Synthea loader, care-gap summary
services/model_api/   FastAPI model service and Dockerfile
services/agent/       LLM helper, FHIR codes, patient facts and care-gap rules
tests/                Automated tests (pytest)
docs/ROADMAP.md       Plan and progress
RESULTS.md            Results log, one entry per step
guidelines/           Guideline documents for retrieval (empty for now)
```

`data/`, `models/` and `synthea/` are created locally by the scripts and are not uploaded.

## Research background

Builds on: M. Sharifuzzaman et al., "Optimized Machine Learning Models and Stacking Hybrid Approach for Chronic Kidney Disease Prediction," *AIAI 2025*, Springer. DOI: [10.1007/978-3-031-96235-6_15](https://doi.org/10.1007/978-3-031-96235-6_15)

## Disclaimer

This is a research project, not a medical device. It is not intended for clinical use. No real patient data is stored in this repository.

## Author

**Md Sharifuzzaman** — [Website](https://sharifuzzamanmd.github.io/) · [Google Scholar](https://scholar.google.com/citations?user=JUlEjLwAAAAJ&hl=en) · [LinkedIn](http://www.linkedin.com/in/md-sharifuzzaman-sourov/)
