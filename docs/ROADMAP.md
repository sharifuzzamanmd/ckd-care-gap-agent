# Roadmap

Started: October 27, 2026

## Phase 1 — Fix and strengthen the model (weeks 1–6)
- [ ] Retrain the stacking ensemble with SMOTE inside training folds only (no data leakage)
- [ ] Build features and labels from NHANES (CKD = eGFR < 60 or UACR ≥ 30)
- [ ] Add XGBoost/LightGBM; calibrate probabilities
- [ ] Report AUC, sensitivity, calibration, and fairness by race, sex and age
- [ ] Add SHAP explanations; benchmark against KFRE

## Phase 2 — Synthetic patient records (weeks 4–8)
- [ ] Generate FHIR patients with Synthea
- [ ] Load them into a local HAPI FHIR server

## Phase 3 — Agent and app (weeks 8–20)
- [ ] Model API (FastAPI): score + explanation
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
