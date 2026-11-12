# Roadmap

Started: October 27, 2026 · Last updated: November 12, 2026

Results for each finished item are in [RESULTS.md](../RESULTS.md).

## Phase 1 — Fix and strengthen the model (weeks 1–6)
- [x] Retrain the stacking ensemble with SMOTE inside training folds only (no data leakage)
- [x] Build features and labels from NHANES (CKD = eGFR < 60 or UACR ≥ 30)
- [x] Calibrate probabilities (isotonic)
- [x] Report AUC, sensitivity, calibration, and fairness by race and sex
- [x] Compare against a simple screening rule (age 60+ OR diabetes OR high BP)
- [x] Add SHAP explanations
- [ ] Report fairness by age group
- [ ] Add XGBoost/LightGBM
- [ ] Benchmark against KFRE
- [ ] Apply NHANES survey weights

## Phase 2 — Synthetic patient records (weeks 4–8)
- [ ] Generate FHIR patients with Synthea
- [ ] Load them into a local HAPI FHIR server

## Phase 3 — Agent and app (weeks 8–20)
- [x] Model API (FastAPI): score + explanation, with tests and Docker
- [x] Local LLM note writer with a number safety check (first piece of the agent)
- [ ] Label each fact as high / low / normal before it reaches the LLM
- [ ] Care-gap rules engine
- [ ] Agent: fetch → score → explain → guideline → draft → clinician approval
- [ ] Clinician dashboard (React)

## Phase 4 — Production readiness (weeks 16–28)
- [ ] HIPAA safeguards, audit logs
- [ ] CI/CD, model versioning, drift monitoring
- [ ] Model card

## Phase 5 — Validate and pilot (months 7–12)
- [ ] Publish validation results
- [ ] Demo video and one-page summary
- [ ] Silent pilot with a partner
