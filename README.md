# CKD Care-Gap Agent

An explainable AI agent that finds patients with **undiagnosed or untested chronic kidney disease (CKD)** in routine health data and helps care teams close the testing gap. A clinician approves every action.

> **Status:** Project started October 27, 2026. Early planning stage — code coming soon.

## Why

- About **37 million US adults** have CKD, and **9 in 10 don't know it** (CDC).
- Early CKD has no symptoms, and the urine test that catches it (UACR) is often never ordered.
- Finding CKD early gives time to slow it with proven treatments and avoid dialysis.

## What it will do

1. Pull patient records (labs, diagnoses, medicines) through FHIR
2. Check care gaps (e.g., diabetes with no UACR this year; abnormal eGFR with no diagnosis)
3. Score CKD risk with a stacking ensemble model
4. Explain each score with SHAP, citing the patient's own lab values
5. Look up the relevant KDIGO guideline (RAG)
6. Draft the next step: a test order, referral, or patient message
7. **Clinician approves, edits, or rejects** — nothing is automatic
8. Track results and update the worklist

If key labs are missing, the agent does not guess a score; it drafts an order for the missing test instead.

## Planned tech stack

| Layer | Technology |
| --- | --- |
| ML and agent | Python, scikit-learn, XGBoost/LightGBM, SHAP, FastAPI, LangGraph |
| Back end | Java Spring Boot, HAPI FHIR, PostgreSQL |
| Front end | React + TypeScript, SMART on FHIR |
| Retrieval | Qdrant + HIPAA-eligible LLM |
| Infrastructure | AWS, Docker, Terraform, GitHub Actions, MLflow |
| Data (development) | NHANES (public), Synthea (synthetic FHIR patients) |

## Repository layout

```
docs/        Product notes and roadmap
data/        Data download scripts (no patient data is stored in this repo)
notebooks/   Model experiments
src/         Application code (model service, agent, API, front end)
```

## Research background

Builds on: M. Sharifuzzaman et al., "Optimized Machine Learning Models and Stacking Hybrid Approach for Chronic Kidney Disease Prediction," *AIAI 2025*, Springer. DOI: [10.1007/978-3-031-96235-6_15](https://doi.org/10.1007/978-3-031-96235-6_15)

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md).

## Disclaimer

This is a research project, not a medical device. It is not intended for clinical use. No real patient data is stored in this repository.

## Author

**Md Sharifuzzaman** — [Website](https://sharifuzzamanmd.github.io/) · [Google Scholar](https://scholar.google.com/citations?user=JUlEjLwAAAAJ&hl=en) · [LinkedIn](http://www.linkedin.com/in/md-sharifuzzaman-sourov/)
